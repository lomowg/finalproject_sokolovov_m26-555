import json
import logging
from datetime import UTC, datetime
from logging.handlers import RotatingFileHandler
from threading import RLock

from valutatrade_hub.infra.settings import SettingsLoader

LOGGER_NAME = "valutatrade.actions"
_CONFIG_LOCK = RLock()


class JsonFormatter(logging.Formatter):
    """Форматирует одну операцию как одну JSON-строку с ISO-временем UTC."""

    def format(self, record: logging.LogRecord) -> str:
        """Сериализует поля действия, уровень и время события."""
        fields = {
            "timestamp": datetime.fromtimestamp(record.created, UTC).isoformat(),
            "level": record.levelname,
            **getattr(record, "action_data", {"message": record.getMessage()}),
        }
        return json.dumps(fields, ensure_ascii=False, default=str, allow_nan=False)


def setup_logging() -> logging.Logger:
    """Настраивает JSON-лог с ротацией по размеру без повторных обработчиков."""
    settings = SettingsLoader()
    path = settings.get("log_file")
    signature = (
        str(path),
        settings.get("log_level"),
        settings.get("log_max_bytes"),
        settings.get("log_backup_count"),
    )
    with _CONFIG_LOCK:
        logger = logging.getLogger(LOGGER_NAME)
        if getattr(logger, "_valutatrade_config", None) == signature:
            return logger
        path.parent.mkdir(parents=True, exist_ok=True)
        handler = RotatingFileHandler(
            path, maxBytes=signature[2], backupCount=signature[3], encoding="utf-8"
        )
        handler.setFormatter(JsonFormatter())
        for previous in logger.handlers[:]:
            logger.removeHandler(previous)
            previous.close()
        logger.addHandler(handler)
        logger.setLevel(signature[1])
        logger.propagate = False
        logger._valutatrade_config = signature
        return logger
