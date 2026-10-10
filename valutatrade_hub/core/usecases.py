from functools import wraps

from valutatrade_hub.core.currencies import CryptoCurrency, get_currency
from valutatrade_hub.core.exceptions import InsufficientFundsError
from valutatrade_hub.core.models import Portfolio, User, Wallet
from valutatrade_hub.core.utils import make_rate_provider, number
from valutatrade_hub.decorators import log_action
from valutatrade_hub.infra.database import DatabaseManager
from valutatrade_hub.infra.settings import SettingsLoader
from valutatrade_hub.logging_config import setup_logging


def authenticated(method):
    """Ограничивает доступ к операции текущей авторизованной сессией."""

    @wraps(method)
    def wrapped(self, *args, **kwargs):
        if self.current_user is None:
            raise ValueError("Сначала выполните login")
        return method(self, *args, **kwargs)

    return wrapped


class WalletService:
    """Операции с пользователями и портфелями через единое JSON-хранилище."""

    def __init__(self):
        """Подключает синглтоны настроек и хранилища и настраивает журнал."""
        self.settings = SettingsLoader()
        self.database = DatabaseManager()
        self.current_user = None
        self._rate_provider = make_rate_provider(self.database, self.settings)
        setup_logging()

    def get_rate(self, source: str, target: str) -> dict:
        """Проверяет валюты и возвращает свежий курс, время и источник."""
        get_currency(source)
        get_currency(target)
        return self._rate_provider(source, target)

    def show_rates(self, currency=None, top=None, base="USD"):
        """Фильтрует кеш, пересчитывает базу и выбирает самые дорогие криптовалюты."""
        if top is not None and (
            isinstance(top, bool) or not isinstance(top, int) or top <= 0
        ):
            raise ValueError("'top' должен быть положительным целым числом")
        snapshot = self.database.read("rates")
        pairs = snapshot.get("pairs", snapshot)
        codes = {
            key.split("_")[0] for key in pairs if "_" in key and key != "last_refresh"
        }
        if not codes:
            raise ValueError(
                "Локальный кеш курсов пуст. Выполните 'update-rates', "
                "чтобы загрузить данные."
            )
        if currency is not None:
            if currency not in codes:
                raise ValueError(f"Курс для '{currency}' не найден в кеше.")
            codes = {currency}
        get_currency(base)
        rows = []
        for code in sorted(codes):
            if top is not None and not isinstance(get_currency(code), CryptoCurrency):
                continue
            result = self.get_rate(code, base)
            rows.append({"pair": f"{code}_{base}", **result})
        if top is not None:
            rows = sorted(rows, key=lambda row: row["rate"], reverse=True)[:top]
        return {"rates": rows, "last_refresh": snapshot.get("last_refresh")}

    def register(self, username, password):
        """Сохраняет пользователя и пустой портфель в одной операции хранилища."""
        with self.database.transaction("users", "portfolios") as data:
            users = data["users"]
            user = User.create(
                max((entry["user_id"] for entry in users), default=0) + 1,
                username,
                password,
            )
            if any(entry["username"] == user.username for entry in users):
                raise ValueError(f"Имя пользователя '{user.username}' уже занято")
            users.append(user.to_dict())
            data["portfolios"].append(Portfolio(user).to_dict())
        return user.get_user_info()

    def login(self, username, password):
        """Проверяет учётные данные и устанавливает текущего пользователя."""
        if not isinstance(username, str) or not username.strip():
            raise ValueError("Имя пользователя не может быть пустым")
        username = username.strip()
        for entry in self.database.read("users"):
            if entry["username"] == username:
                user = User.from_dict(entry)
                if not user.verify_password(password):
                    raise ValueError("Неверный пароль")
                self.current_user = user
                return user.get_user_info()
        raise ValueError(f"Пользователь '{username}' не найден")

    def _portfolio(self, records):
        for entry in records:
            if entry["user_id"] == self.current_user.user_id:
                wallets = {
                    code: Wallet(code, data["balance"])
                    for code, data in entry["wallets"].items()
                }
                return Portfolio(self.current_user, wallets)
        raise ValueError("Портфель пользователя не найден")

    @authenticated
    def show_portfolio(self, base=None):
        """Возвращает балансы и стоимость в базовой валюте из настроек или команды."""
        base = self.settings.get("default_base_currency") if base is None else base
        get_currency(base)
        base_rate = self.get_rate(base, "USD")["rate"]
        portfolio = self._portfolio(self.database.read("portfolios"))
        rows = []
        rates = {base: base_rate}
        for code, wallet in portfolio.wallets.items():
            value = 0.0
            if wallet.balance:
                rates[code] = self.get_rate(code, "USD")["rate"]
                value = wallet.balance * rates[code] / base_rate
            rows.append({"currency": code, "balance": wallet.balance, "value": value})
        return {
            "username": self.current_user.username,
            "base": base,
            "wallets": rows,
            "total": portfolio.get_total_value(base, rates),
        }

    @log_action("BUY", verbose=True)
    @authenticated
    def buy(self, currency, amount):
        """Покупает указанное количество валюты за USD и журналирует результат."""
        return self._trade(currency, amount, buying=True)

    @log_action("SELL", verbose=True)
    @authenticated
    def sell(self, currency, amount):
        """Продаёт валюту с начислением USD и журналирует результат."""
        return self._trade(currency, amount, buying=False)

    def _trade(self, currency, amount, *, buying):
        currency = get_currency(currency).code
        amount = number(amount)
        with self.database.transaction("portfolios") as data:
            portfolio = self._portfolio(data["portfolios"])
            wallet = portfolio.wallets.get(currency)
            if not buying and wallet is None:
                raise InsufficientFundsError(0.0, amount, currency)
            rate = self.get_rate(currency, "USD")
            cost = number(amount * rate["rate"])
            before = wallet.balance if wallet is not None else 0.0
            try:
                if buying:
                    usd = portfolio.wallets.get("USD", Wallet("USD"))
                    usd.withdraw(cost)
                    if wallet is None:
                        wallet = portfolio.add_currency(currency)
                    wallet.deposit(amount)
                else:
                    wallet.withdraw(amount)
                    usd = (
                        portfolio.get_wallet("USD")
                        if "USD" in portfolio.wallets
                        else portfolio.add_currency("USD")
                    )
                    usd.deposit(cost)
            except InsufficientFundsError as error:
                error.rate = rate["rate"]
                raise
            for index, entry in enumerate(data["portfolios"]):
                if entry["user_id"] == portfolio.user_id:
                    data["portfolios"][index] = portfolio.to_dict()
                    break
        return {
            "currency": currency,
            "amount": amount,
            "rate": rate["rate"],
            "base": "USD",
            "source": rate["source"],
            "cost": cost,
            "before": before,
            "after": wallet.balance,
            "usd_balance": usd.balance,
        }
