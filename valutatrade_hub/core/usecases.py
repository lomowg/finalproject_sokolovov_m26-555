from functools import wraps
from pathlib import Path

from valutatrade_hub.core.models import Portfolio, User, Wallet
from valutatrade_hub.core.utils import (
    currency_code,
    make_rate_provider,
    number,
    read_json,
    write_json,
)


def authenticated(method):
    """Ограничивает доступ к операции текущей авторизованной сессией."""

    @wraps(method)
    def wrapped(self, *args, **kwargs):
        if self.current_user is None:
            raise ValueError("Сначала выполните login")
        return method(self, *args, **kwargs)

    return wrapped


class WalletService:
    """Операции с пользователями, портфелями и локальным кешем курсов."""

    def __init__(self, data_dir="data"):
        """Задаёт каталог данных и создаёт неавторизованную сессию."""
        self.data_dir = Path(data_dir)
        self.current_user = None
        self._rate_provider = make_rate_provider(self.data_dir / "rates.json")

    def get_rate(self, source: str, target: str) -> dict:
        """Возвращает курс, время обновления и источник данных."""
        return self._rate_provider(source, target)

    def _records(self, name):
        records = read_json(self.data_dir / name, [])
        if not isinstance(records, list) or any(
            not isinstance(item, dict) for item in records
        ):
            raise ValueError(f"Файл {name} должен содержать список объектов")
        return records

    def register(self, username, password):
        """Сохраняет нового пользователя и создаёт пустой портфель."""
        users = self._records("users.json")
        user = User.create(
            max((item["user_id"] for item in users), default=0) + 1,
            username,
            password,
        )
        if any(item["username"] == user.username for item in users):
            raise ValueError(f"Имя пользователя '{user.username}' уже занято")
        portfolios = self._records("portfolios.json")
        updated = portfolios + [Portfolio(user).to_dict()]
        write_json(self.data_dir / "portfolios.json", updated)
        try:
            write_json(self.data_dir / "users.json", users + [user.to_dict()])
        except OSError:
            write_json(self.data_dir / "portfolios.json", portfolios)
            raise
        return user.get_user_info()

    def login(self, username, password):
        """Проверяет учётные данные и устанавливает текущего пользователя."""
        if not isinstance(username, str) or not username.strip():
            raise ValueError("Имя пользователя не может быть пустым")
        username = username.strip()
        for entry in self._records("users.json"):
            if entry["username"] == username:
                user = User.from_dict(entry)
                if not user.verify_password(password):
                    raise ValueError("Неверный пароль")
                self.current_user = user
                return user.get_user_info()
        raise ValueError(f"Пользователь '{username}' не найден")

    @authenticated
    def _portfolio(self):
        for entry in self._records("portfolios.json"):
            if entry["user_id"] == self.current_user.user_id:
                wallets = {
                    code: Wallet(code, data["balance"])
                    for code, data in entry["wallets"].items()
                }
                return Portfolio(self.current_user, wallets)
        raise ValueError("Портфель пользователя не найден")

    def _save_portfolio(self, portfolio):
        records = self._records("portfolios.json")
        for index, entry in enumerate(records):
            if entry["user_id"] == portfolio.user_id:
                records[index] = portfolio.to_dict()
                write_json(self.data_dir / "portfolios.json", records)
                return
        raise ValueError("Портфель пользователя не найден")

    @authenticated
    def show_portfolio(self, base="USD"):
        """Возвращает балансы и стоимость портфеля в выбранной валюте."""
        base = currency_code(base)
        try:
            base_rate = self.get_rate(base, "USD")
        except ValueError as error:
            raise ValueError(f"Неизвестная базовая валюта '{base}'") from error
        portfolio = self._portfolio()
        rows = []
        rates = {base: base_rate["rate"]}
        for code, wallet in portfolio.wallets.items():
            if wallet.balance == 0:
                value = 0.0
            else:
                rates[code] = self.get_rate(code, "USD")["rate"]
                value = wallet.balance * rates[code] / rates[base]
            rows.append({"currency": code, "balance": wallet.balance, "value": value})
        return {
            "username": self.current_user.username,
            "base": base,
            "wallets": rows,
            "total": portfolio.get_total_value(base, rates),
        }

    @authenticated
    def buy(self, currency, amount):
        """Покупает указанное количество валюты за средства USD-кошелька."""
        return self._trade(currency, amount, buying=True)

    @authenticated
    def sell(self, currency, amount):
        """Продаёт указанное количество валюты с начислением USD."""
        return self._trade(currency, amount, buying=False)

    def _trade(self, currency, amount, *, buying):
        currency = currency_code(currency)
        amount = number(amount)
        rate = self.get_rate(currency, "USD")
        cost = number(amount * rate["rate"])
        portfolio = self._portfolio()
        if buying:
            usd = portfolio.wallets.get("USD", Wallet("USD"))
            usd.withdraw(cost)
            wallet = (
                portfolio.get_wallet(currency)
                if currency in portfolio.wallets
                else portfolio.add_currency(currency)
            )
            before = wallet.balance
            wallet.deposit(amount)
        else:
            wallet = portfolio.get_wallet(currency)
            before = wallet.balance
            wallet.withdraw(amount)
            usd = (
                portfolio.get_wallet("USD")
                if "USD" in portfolio.wallets
                else portfolio.add_currency("USD")
            )
            usd.deposit(cost)
        self._save_portfolio(portfolio)
        return {
            "currency": currency,
            "amount": amount,
            "rate": rate["rate"],
            "source": rate["source"],
            "cost": cost,
            "before": before,
            "after": wallet.balance,
            "usd_balance": usd.balance,
        }
