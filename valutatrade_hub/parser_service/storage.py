"""Атомарное сохранение снимка курсов и истории измерений."""

from datetime import datetime
from pathlib import Path

from valutatrade_hub.core.utils import currency_code, number, read_json, write_json
from valutatrade_hub.parser_service.config import ParserConfig


class RatesStorage:
    """Сохраняет последний срез каждой пары и историю без повторяющихся ID."""

    def __init__(self, config=None):
        """Подключает пути к кешу и истории из конфигурации."""
        config = config if config is not None else ParserConfig()
        self.rates_path = Path(config.RATES_FILE_PATH)
        self.history_path = Path(config.HISTORY_FILE_PATH)

    def save(self, records, last_refresh):
        """Проверяет записи, дополняет историю и заменяет только более старые пары."""
        snapshot = read_json(self.rates_path, {})
        history = read_json(self.history_path, [])
        if not isinstance(snapshot, dict) or not isinstance(history, list):
            raise TypeError("Некорректная структура кеша или истории курсов")
        pairs = snapshot.get("pairs")
        if pairs is None:
            pairs = {
                key: {**value, "source": snapshot.get("source", "LocalCache")}
                for key, value in snapshot.items()
                if "_" in key and isinstance(value, dict)
            }
        if not isinstance(pairs, dict):
            raise TypeError("Некорректный список пар в кеше")
        if any(not isinstance(row, dict) or "id" not in row for row in history):
            raise ValueError("Некорректная запись истории курсов")
        ids = {row["id"] for row in history}
        updated_count = 0
        for record in records:
            source = currency_code(record["from_currency"])
            target = currency_code(record["to_currency"])
            rate = number(record["rate"])
            stamp = datetime.fromisoformat(record["timestamp"])
            if stamp.tzinfo is None:
                raise ValueError("Время измерения должно содержать часовой пояс")
            pair = f"{source}_{target}"
            identifier = f"{pair}_{record['timestamp']}"
            if identifier not in ids:
                history.append({**record, "id": identifier})
                ids.add(identifier)
            previous = pairs.get(pair)
            if previous is None or stamp > datetime.fromisoformat(
                previous["updated_at"]
            ):
                pairs[pair] = {
                    "rate": rate,
                    "updated_at": record["timestamp"],
                    "source": record["source"],
                }
                updated_count += 1
        write_json(self.history_path, history)
        write_json(self.rates_path, {"pairs": pairs, "last_refresh": last_refresh})
        return updated_count
