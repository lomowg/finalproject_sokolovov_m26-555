import tomllib
from copy import deepcopy
from pathlib import Path
from threading import RLock
from typing import Any

DEFAULT_SETTINGS = {
    "data_dir": "data",
    "users_file": "users.json",
    "portfolios_file": "portfolios.json",
    "rates_file": "rates.json",
    "rates_ttl_seconds": 300,
    "default_base_currency": "USD",
    "log_file": "logs/actions.log",
    "log_format": "json",
    "log_level": "INFO",
    "log_max_bytes": 1048576,
    "log_backup_count": 3,
}


class SettingsLoader:
    """Единственный кеш конфигурации из секции tool.valutatrade."""

    _instance = None
    _lock = RLock()

    def __new__(cls):
        """Создаёт и загружает единственный экземпляр при первом обращении."""
        with cls._lock:
            if cls._instance is None:
                instance = super().__new__(cls)
                instance._config_path = Path.cwd() / "pyproject.toml"
                instance.reload()
                cls._instance = instance
            return cls._instance

    def get(self, key: str, default: Any = None) -> Any:
        """Возвращает копию значения настройки или default."""
        with self._lock:
            return deepcopy(self._settings.get(key, default))

    def reload(self) -> None:
        """Перечитывает настройки, проверяя пути, TTL и параметры логов."""
        with self._lock:
            settings = DEFAULT_SETTINGS.copy()
            if self._config_path.exists():
                with self._config_path.open("rb") as stream:
                    document = tomllib.load(stream)
                section = document.get("tool", {}).get("valutatrade", {})
                if not isinstance(section, dict):
                    raise ValueError("tool.valutatrade должен быть таблицей TOML")
                settings.update(section)
            for key in ("rates_ttl_seconds", "log_max_bytes", "log_backup_count"):
                value = settings[key]
                if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                    raise ValueError(
                        f"Настройка {key} должна быть положительным целым числом"
                    )
            if settings["log_format"] != "json":
                raise ValueError("Поддерживаемый формат логов: json")
            if settings["log_level"] not in (
                "DEBUG",
                "INFO",
                "WARNING",
                "ERROR",
                "CRITICAL",
            ):
                raise ValueError("Неизвестный уровень логирования")
            from valutatrade_hub.core.currencies import get_currency

            get_currency(settings["default_base_currency"])
            for key in (
                "data_dir",
                "users_file",
                "portfolios_file",
                "rates_file",
                "log_file",
            ):
                value = settings[key]
                if not isinstance(value, str) or not value.strip():
                    raise ValueError(f"Настройка {key} должна содержать путь")
            root = self._config_path.parent
            settings["data_dir"] = (root / settings["data_dir"]).resolve()
            settings["log_file"] = (root / settings["log_file"]).resolve()
            for key in ("users_file", "portfolios_file", "rates_file"):
                settings[key] = (settings["data_dir"] / settings[key]).resolve()
            if (
                len(
                    {
                        settings[key]
                        for key in (
                            "users_file",
                            "portfolios_file",
                            "rates_file",
                            "log_file",
                        )
                    }
                )
                != 4
            ):
                raise ValueError("Файлы данных и логов должны иметь разные пути")
            self._settings = settings
