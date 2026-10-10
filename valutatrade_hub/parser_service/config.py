"""Настройки источников курсов и локального хранилища."""

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

from valutatrade_hub.infra.settings import SettingsLoader


def _api_key():
    load_dotenv(Path(__file__).resolve().parents[2] / ".env", override=False)
    return os.getenv("EXCHANGERATE_API_KEY", "")


@dataclass
class ParserConfig:
    """Хранит параметры API; окружение имеет приоритет над локальным .env."""

    EXCHANGERATE_API_KEY: str = field(default_factory=_api_key, repr=False)
    COINGECKO_URL: str = "https://api.coingecko.com/api/v3/simple/price"
    EXCHANGERATE_API_URL: str = "https://v6.exchangerate-api.com/v6"
    BASE_CURRENCY: str = "USD"
    FIAT_CURRENCIES: tuple = ("EUR", "GBP", "RUB")
    CRYPTO_CURRENCIES: tuple = ("BTC", "ETH", "SOL")
    CRYPTO_ID_MAP: dict = field(
        default_factory=lambda: {
            "BTC": "bitcoin",
            "ETH": "ethereum",
            "SOL": "solana",
        }
    )
    RATES_FILE_PATH: Path = field(
        default_factory=lambda: SettingsLoader().get("rates_file")
    )
    HISTORY_FILE_PATH: Path = field(
        default_factory=lambda: SettingsLoader().get("data_dir") / "exchange_rates.json"
    )
    REQUEST_TIMEOUT: int = 10
    UPDATE_INTERVAL: int = 300
