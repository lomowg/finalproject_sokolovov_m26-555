"""Координация обновления курсов из независимых источников."""

from datetime import UTC, datetime

from valutatrade_hub.core.exceptions import ApiRequestError
from valutatrade_hub.logging_config import setup_logging
from valutatrade_hub.parser_service.api_clients import (
    CoinGeckoClient,
    ExchangeRateApiClient,
)
from valutatrade_hub.parser_service.config import ParserConfig
from valutatrade_hub.parser_service.storage import RatesStorage


class RatesUpdater:
    """Обновляет доступные источники даже при сбое одного из клиентов."""

    def __init__(self, clients=None, storage=None, config=None):
        """Принимает API-клиенты, хранилище и общую конфигурацию."""
        config = config if config is not None else ParserConfig()
        self.clients = (
            clients
            if clients is not None
            else [
                CoinGeckoClient(config),
                ExchangeRateApiClient(config),
            ]
        )
        self.storage = storage if storage is not None else RatesStorage(config)
        self.logger = setup_logging("valutatrade.parser", "parser.log")

    def run_update(self):
        """Получает курсы, сохраняет историю и возвращает итог обновления."""
        self.logger.info("Starting rates update")
        records, errors = [], []
        for client in self.clients:
            self.logger.info("Fetching from %s", client.source)
            try:
                rates = client.fetch_rates()
                if not rates:
                    raise ApiRequestError(f"{client.source}: пустой ответ с курсами")
            except ApiRequestError as error:
                errors.append(str(error))
                self.logger.error("Failed to fetch from %s: %s", client.source, error)
                continue
            for pair, rate in rates.items():
                source, target = pair.split("_")
                meta = client.meta.copy()
                if isinstance(client, CoinGeckoClient):
                    meta["raw_id"] = client.config.CRYPTO_ID_MAP[source]
                records.append(
                    {
                        "from_currency": source,
                        "to_currency": target,
                        "rate": rate,
                        "timestamp": client.updated_at,
                        "source": client.source,
                        "meta": meta,
                    }
                )
            self.logger.info("%s: OK (%s rates)", client.source, len(rates))
        if not records:
            self.logger.error("No rates received; cache unchanged")
            raise ApiRequestError("не удалось обновить курсы. " + "; ".join(errors))
        refreshed = datetime.now(UTC).isoformat().replace("+00:00", "Z")
        self.logger.info("Writing %s rates", len(records))
        try:
            count = self.storage.save(records, refreshed)
        except (OSError, ValueError, TypeError, KeyError):
            self.logger.exception("Failed to save rates")
            raise
        self.logger.info("Update completed: %s rates, %s errors", count, len(errors))
        return {"updated": count, "last_refresh": refreshed, "errors": errors}


def update_rates(source=None):
    """Обновляет все источники либо один источник, выбранный в CLI."""
    config = ParserConfig()
    clients = {
        "coingecko": CoinGeckoClient(config),
        "exchangerate": ExchangeRateApiClient(config),
    }
    if source is not None and source not in clients:
        raise ValueError("Источник должен быть coingecko или exchangerate")
    selected = list(clients.values()) if source is None else [clients[source]]
    return RatesUpdater(selected, config=config).run_update()
