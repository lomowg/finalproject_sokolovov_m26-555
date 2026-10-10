# ValutaTrade Hub

Учебное консольное приложение для торговли фиатными валютами и криптовалютами.
Поддерживает регистрацию, вход, покупку, продажу и оценку портфеля.
Новый пользователь получает стартовый учебный баланс 10 000 USD.

## Установка и запуск

Нужны Python 3.11+ и [uv](https://docs.astral.sh/uv/).
В каталоге проекта выполните:

```powershell
uv sync
uv run valutatrade
```

Для выхода нажмите `Ctrl+C`.

## Asciinema
Запись с показом возможностей - https://asciinema.org/a/aOqNjvGRrGoVyji1

## Настройка API

Создайте файл `.env` в корне проекта и укажите свой ключ ExchangeRate-API:

```dotenv
EXCHANGERATE_API_KEY=ваш_ключ
```

Ключ можно также задать переменной окружения. `.env` исключён из Git.
Фиатные курсы загружаются из ExchangeRate-API, криптовалютные - из CoinGecko
без ключа. Настройки источников находятся в `valutatrade_hub/parser_service/config.py`.


## Кеш и обновление курсов

Основной сервис читает `data/rates.json`. Срок актуальности курсов - 300 секунд
(`rates_ttl_seconds` в `pyproject.toml`). Если курс устарел, выполните `update-rates`.
История измерений хранится в `data/exchange_rates.json`.

Для автоматического обновления каждые 300 секунд запустите в отдельном терминале:

```powershell
uv run python -m valutatrade_hub.parser_service.scheduler
```

## Структура

```text
valutatrade_hub/
  core/            # модели, валюты и торговые операции
  infra/           # настройки и JSON-хранилище
  parser_service/  # API-клиенты, обновление, история и планировщик
  cli/             # интерактивный интерфейс
  logging_config.py
  decorators.py
data/              # пользователи, портфели, кеш и история курсов
main.py
pyproject.toml
uv.lock
```

Журналы операций и обновлений: `logs/actions.log` и `logs/parser.log`.
Стартовый баланс задаётся параметром `initial_usd_balance` в `pyproject.toml`.
