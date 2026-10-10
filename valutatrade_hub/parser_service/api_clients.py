"""API-клиенты с единым форматом курсов и доменными ошибками."""

from abc import ABC, abstractmethod
from datetime import UTC, datetime
from time import perf_counter

import requests

from valutatrade_hub.core.exceptions import ApiRequestError
from valutatrade_hub.core.utils import number
from valutatrade_hub.parser_service.config import ParserConfig


class BaseApiClient(ABC):
    """Возвращает курсы FROM_BASE и метаданные последнего успешного запроса."""

    source = ""

    def __init__(self, config=None):
        """Принимает конфигурацию источника."""
        self.config = config if config is not None else ParserConfig()
        self.updated_at = None
        self.meta = {}

    def _request(self, url, params=None):
        start = perf_counter()
        try:
            response = requests.get(
                url, params=params, timeout=self.config.REQUEST_TIMEOUT
            )
        except requests.exceptions.Timeout:
            raise ApiRequestError(f"{self.source}: превышено время ожидания") from None
        except requests.exceptions.RequestException:
            # Исключение requests может содержать URL с секретным API-ключом.
            raise ApiRequestError(f"{self.source}: ошибка сети") from None
        if response.status_code != 200:
            reasons = {
                401: "неверный API-ключ",
                403: "доступ запрещён",
                429: "превышен лимит запросов; повторите позже",
            }
            reason = reasons.get(response.status_code, "сервис недоступен")
            raise ApiRequestError(
                f"{self.source}: HTTP {response.status_code}, {reason}"
            )
        try:
            payload = response.json()
        except ValueError:
            raise ApiRequestError(f"{self.source}: некорректный JSON") from None
        if not isinstance(payload, dict):
            raise ApiRequestError(f"{self.source}: ожидался JSON-объект")
        self.updated_at = datetime.now(UTC).isoformat().replace("+00:00", "Z")
        self.meta = {
            "request_ms": round((perf_counter() - start) * 1000),
            "status_code": response.status_code,
        }
        if response.headers.get("ETag"):
            self.meta["etag"] = response.headers["ETag"]
        return payload

    @abstractmethod
    def fetch_rates(self) -> dict:
        """Возвращает словарь валютных пар с положительными числовыми курсами."""


class CoinGeckoClient(BaseApiClient):
    """Получает стоимость криптовалют через CoinGecko Simple Price."""

    source = "CoinGecko"

    def fetch_rates(self) -> dict:
        """Сопоставляет ID монет с тикерами и проверяет курсы."""
        config = self.config
        try:
            ids = [config.CRYPTO_ID_MAP[code] for code in config.CRYPTO_CURRENCIES]
            data = self._request(
                config.COINGECKO_URL,
                {
                    "ids": ",".join(ids),
                    "vs_currencies": config.BASE_CURRENCY.lower(),
                },
            )
            return {
                f"{code}_{config.BASE_CURRENCY}": number(
                    data[config.CRYPTO_ID_MAP[code]][config.BASE_CURRENCY.lower()]
                )
                for code in config.CRYPTO_CURRENCIES
            }
        except (KeyError, TypeError, ValueError, OverflowError):
            raise ApiRequestError(f"{self.source}: некорректные курсы") from None


class ExchangeRateApiClient(BaseApiClient):
    """Получает фиатные курсы и переводит BASE_FROM в FROM_BASE."""

    source = "ExchangeRate-API"

    def fetch_rates(self) -> dict:
        """Запрашивает latest/BASE; ключ не попадает в сообщения об ошибках."""
        config = self.config
        if not config.EXCHANGERATE_API_KEY:
            raise ApiRequestError("задайте EXCHANGERATE_API_KEY в окружении или .env")
        url = (
            f"{config.EXCHANGERATE_API_URL}/{config.EXCHANGERATE_API_KEY}"
            f"/latest/{config.BASE_CURRENCY}"
        )
        data = self._request(url)
        if data.get("result") != "success":
            reasons = {
                "invalid-key": "неверный API-ключ",
                "inactive-account": "подтвердите регистрацию аккаунта",
                "quota-reached": "превышен лимит запросов; повторите позже",
                "unsupported-code": "неподдерживаемая базовая валюта",
            }
            reason = reasons.get(data.get("error-type"), "API отклонил запрос")
            raise ApiRequestError(f"{self.source}: {reason}")
        try:
            if data["base_code"] != config.BASE_CURRENCY:
                raise ValueError("Неверная базовая валюта")
            rates = data.get("conversion_rates", data.get("rates"))
            result = {
                f"{code}_{config.BASE_CURRENCY}": number(1 / number(rates[code]))
                for code in config.FIAT_CURRENCIES
            }
        except (KeyError, TypeError, ValueError, OverflowError):
            raise ApiRequestError(f"{self.source}: некорректные курсы") from None
        # TTL отсчитывается от получения; время публикации остаётся в истории.
        self.meta["provider_updated_at"] = data.get("time_last_update_utc")
        return result
