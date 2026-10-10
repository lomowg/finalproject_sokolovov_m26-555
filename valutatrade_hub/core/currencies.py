from abc import ABC, abstractmethod
from dataclasses import dataclass

from valutatrade_hub.core.exceptions import CurrencyNotFoundError
from valutatrade_hub.core.utils import currency_code, number


@dataclass(frozen=True)
class Currency(ABC):
    """Общий интерфейс валюты с именем и кодом длиной от 2 до 5 символов."""

    name: str
    code: str

    def __post_init__(self):
        """Проверяет общие инварианты валюты."""
        currency_code(self.code)
        if not isinstance(self.name, str) or not self.name.strip():
            raise ValueError("Название валюты не может быть пустым")

    @abstractmethod
    def get_display_info(self) -> str:
        """Возвращает описание валюты для интерфейса и логов."""


@dataclass(frozen=True)
class FiatCurrency(Currency):
    """Фиатная валюта с указанием страны или зоны эмиссии."""

    issuing_country: str

    def __post_init__(self):
        """Проверяет код, название и страну эмиссии."""
        super().__post_init__()
        if (
            not isinstance(self.issuing_country, str)
            or not self.issuing_country.strip()
        ):
            raise ValueError("Страна или зона эмиссии не может быть пустой")

    def get_display_info(self) -> str:
        """Возвращает описание в формате FIAT с зоной эмиссии."""
        return f"[FIAT] {self.code} — {self.name} (Issuing: {self.issuing_country})"


@dataclass(frozen=True)
class CryptoCurrency(Currency):
    """Криптовалюта с алгоритмом и последней известной капитализацией."""

    algorithm: str
    market_cap: float

    def __post_init__(self):
        """Проверяет алгоритм и неотрицательную конечную капитализацию."""
        super().__post_init__()
        if not isinstance(self.algorithm, str) or not self.algorithm.strip():
            raise ValueError("Алгоритм не может быть пустым")
        number(self.market_cap, positive=False)

    def get_display_info(self) -> str:
        """Возвращает описание CRYPTO с краткой капитализацией."""
        mantissa, exponent = f"{self.market_cap:.2e}".split("e")
        market_cap = f"{mantissa.rstrip('0').rstrip('.')}e{int(exponent)}"
        return (
            f"[CRYPTO] {self.code} — {self.name} "
            f"(Algo: {self.algorithm}, MCAP: {market_cap})"
        )


CURRENCIES = {
    "USD": FiatCurrency("US Dollar", "USD", "United States"),
    "EUR": FiatCurrency("Euro", "EUR", "Eurozone"),
    "RUB": FiatCurrency("Russian Ruble", "RUB", "Russia"),
    "BTC": CryptoCurrency("Bitcoin", "BTC", "SHA-256", 1.12e12),
    "ETH": CryptoCurrency("Ethereum", "ETH", "Ethash", 0.0),
}


def get_currency(code: str) -> Currency:
    """Возвращает зарегистрированную валюту или CurrencyNotFoundError."""
    try:
        return CURRENCIES[currency_code(code)]
    except (ValueError, KeyError) as error:
        raise CurrencyNotFoundError(code) from error
