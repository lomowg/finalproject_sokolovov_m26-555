import json
import math
import re
from datetime import UTC, datetime
from pathlib import Path
from tempfile import NamedTemporaryFile

RATE_CACHE_TTL_SECONDS = 300

EXCHANGE_RATES = {
    "USD": 1.0,
    "EUR": 1.0786,
    "BTC": 59337.21,
    "RUB": 0.01016,
    "ETH": 3720.0,
}


def currency_code(value: str) -> str:
    """Проверяет формат кода валюты и возвращает исходную строку."""
    if not isinstance(value, str) or not re.fullmatch(r"[A-Z]+", value):
        raise ValueError(
            "Код валюты должен быть непустой строкой из латинских букв в верхнем регистре"
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


def make_rate_provider(path: Path, ttl: int = RATE_CACHE_TTL_SECONDS):
    """Кеш курсов с обновлением из фиксированного источника."""
    cached = None

    def get_rate(source: str, target: str) -> dict:
        nonlocal cached
        source, target = currency_code(source), currency_code(target)
        now = datetime.now(UTC)
        if cached is None:
            cached = read_json(path, {})
            if not isinstance(cached, dict):
                raise ValueError("Файл rates.json должен содержать объект")

        def lookup(left, right):
            if left == right:
                if left in EXCHANGE_RATES:
                    return 1.0, now, "FixedRates"
                return None
            entry = cached.get(f"{left}_{right}")
            if not isinstance(entry, dict):
                return None
            try:
                rate = number(entry["rate"])
                updated = datetime.fromisoformat(entry["updated_at"])
                if updated.tzinfo is None:
                    updated = updated.replace(tzinfo=UTC)
                age = (now - updated).total_seconds()
                if 0 <= age < ttl:
                    return rate, updated, cached.get("source", "LocalCache")
            except (KeyError, TypeError, ValueError):
                pass
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
            if source not in EXCHANGE_RATES or target not in EXCHANGE_RATES:
                raise ValueError(
                    f"Курс {source}→{target} недоступен. Повторите попытку позже."
                )
            stamp = now.isoformat()
            refreshed = {
                f"{code}_USD": {"rate": rate, "updated_at": stamp}
                for code, rate in EXCHANGE_RATES.items()
            }
            refreshed.update(source="FixedRates", last_refresh=stamp)
            write_json(path, refreshed)
            cached = refreshed
            result = (
                EXCHANGE_RATES[source] / EXCHANGE_RATES[target],
                now,
                "FixedRates",
            )
        return {
            "rate": number(result[0]),
            "updated_at": result[1].isoformat(),
            "source": result[2],
        }

    return get_rate
