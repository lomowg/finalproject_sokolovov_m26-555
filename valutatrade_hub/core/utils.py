import json
import math
import re
from datetime import UTC, datetime
from pathlib import Path
from tempfile import NamedTemporaryFile

EXCHANGE_RATES = {
    "USD": 1.0,
    "EUR": 1.0786,
    "GBP": 1.27,
    "BTC": 59337.21,
    "RUB": 0.01016,
    "ETH": 3720.0,
    "SOL": 145.12,
}


def currency_code(value: str) -> str:
    """Проверяет формат кода валюты и возвращает исходную строку."""
    if not isinstance(value, str) or not re.fullmatch(r"[A-Z]{2,5}", value):
        raise ValueError(
            "Код валюты должен содержать от 2 до 5 латинских букв в верхнем регистре"
        )
    return value


def number(value: float, *, positive: bool = True) -> float:
    """Проверяет числовую сумму и возвращает её как конечный float."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError("Сумма должна быть числом")
    try:
        result = float(value)
    except OverflowError as error:
        raise ValueError("Сумма слишком велика") from error
    if not math.isfinite(result) or result < 0 or (positive and result == 0):
        message = "'amount' должен быть положительным числом"
        raise ValueError(
            message
            if positive
            else "Баланс должен быть конечным неотрицательным числом"
        )
    return result


def read_json(path: Path, default):
    """Читает JSON; для отсутствующего файла возвращает default."""
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeError) as error:
        raise ValueError(f"Некорректный JSON в файле {path.name}") from error


def write_json(path: Path, data) -> None:
    """Сохраняет JSON атомарной заменой файла в том же каталоге."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=path.parent, suffix=".tmp", delete=False
        ) as stream:
            temporary = Path(stream.name)
            json.dump(data, stream, ensure_ascii=False, indent=2, allow_nan=False)
            stream.write("\n")
        temporary.replace(path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def make_rate_provider(database, settings):
    """Читает курсы Parser Service с TTL; устаревший кеш требует update-rates."""
    from copy import deepcopy

    from valutatrade_hub.core.currencies import get_currency
    from valutatrade_hub.core.exceptions import ApiRequestError

    cached_snapshot = None
    cached_results = {}

    def get_rate(source: str, target: str) -> dict:
        nonlocal cached_snapshot
        get_currency(source)
        get_currency(target)
        now = datetime.now(UTC)
        ttl = settings.get("rates_ttl_seconds")
        rates = database.read("rates")
        pairs = rates.get("pairs", rates)
        if cached_snapshot != rates:
            cached_results.clear()
            cached_snapshot = deepcopy(rates)
        key = (source, target)
        previous = cached_results.get(key)
        if previous is not None:
            age = (now - datetime.fromisoformat(previous["updated_at"])).total_seconds()
            if 0 <= age < ttl:
                return previous.copy()

        def lookup(left, right):
            if left == right:
                return 1.0, now, "Identity"
            entry = pairs.get(f"{left}_{right}")
            if not isinstance(entry, dict):
                return None
            try:
                rate = number(entry["rate"])
                updated = datetime.fromisoformat(entry["updated_at"])
                if updated.tzinfo is None:
                    updated = updated.replace(tzinfo=UTC)
                age = (now - updated).total_seconds()
                if 0 <= age < ttl:
                    return (
                        rate,
                        updated,
                        entry.get("source", rates.get("source", "LocalCache")),
                    )
            except (KeyError, TypeError, ValueError, OverflowError):
                return None
            return None

        result = lookup(source, target)
        if result is None:
            reverse = lookup(target, source)
            if reverse is not None:
                result = (1 / reverse[0], reverse[1], reverse[2])
        if result is None:
            left, right = lookup(source, "USD"), lookup(target, "USD")
            if left and right:
                result = (
                    left[0] / right[0],
                    min(left[1], right[1]),
                    left[2] if left[2] == right[2] else "MixedCache",
                )
        if result is None:
            raise ValueError(
                f"Курс {source}→{target} отсутствует или устарел. "
                "Выполните 'update-rates', чтобы обновить кеш."
            )
        try:
            response = {
                "rate": number(result[0]),
                "updated_at": result[1].isoformat(),
                "source": result[2],
            }
        except (ValueError, TypeError, OverflowError) as error:
            raise ApiRequestError(f"некорректный курс {source}→{target}") from error
        cached_results[key] = response
        return response.copy()

    return get_rate
