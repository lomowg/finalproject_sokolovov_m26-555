import hashlib
import hmac
import secrets
from datetime import UTC, datetime

from valutatrade_hub.core.currencies import get_currency
from valutatrade_hub.core.exceptions import ApiRequestError, InsufficientFundsError
from valutatrade_hub.core.utils import EXCHANGE_RATES, number

MIN_PASSWORD_LENGTH = 4
PASSWORD_SALT_BYTES = 16


class User:
    """Пользователь с хешем пароля, индивидуальной солью и датой регистрации."""

    def __init__(
        self,
        user_id: int,
        username: str,
        hashed_password: str,
        salt: str,
        registration_date: datetime,
    ):
        """Восстанавливает пользователя из сохранённых атрибутов."""
        if isinstance(user_id, bool) or not isinstance(user_id, int) or user_id <= 0:
            raise ValueError(
                "Идентификатор пользователя должен быть положительным целым числом"
            )
        if not isinstance(hashed_password, str) or not hashed_password:
            raise ValueError("Хеш пароля не может быть пустым")
        if not isinstance(salt, str) or not salt:
            raise ValueError("Соль не может быть пустой")
        if not isinstance(registration_date, datetime):
            raise TypeError("Дата регистрации должна иметь тип datetime")
        self._user_id = user_id
        self.username = username
        self._hashed_password = hashed_password
        self._salt = salt
        self._registration_date = registration_date

    @classmethod
    def create(cls, user_id: int, username: str, password: str):
        """Создаёт пользователя, генерируя соль и хеш SHA-256."""
        cls._validate_password(password)
        salt = secrets.token_hex(PASSWORD_SALT_BYTES)
        hashed = hashlib.sha256((password + salt).encode()).hexdigest()
        return cls(user_id, username, hashed, salt, datetime.now(UTC))

    @staticmethod
    def _validate_password(password):
        if not isinstance(password, str) or len(password) < MIN_PASSWORD_LENGTH:
            raise ValueError(
                f"Пароль должен быть не короче {MIN_PASSWORD_LENGTH} символов"
            )

    @property
    def user_id(self):
        """Уникальный идентификатор пользователя."""
        return self._user_id

    @property
    def username(self):
        """Непустое имя пользователя без пробелов по краям."""
        return self._username

    @username.setter
    def username(self, value):
        """Непустое имя пользователя без пробелов по краям."""
        if not isinstance(value, str) or not value.strip():
            raise ValueError("Имя пользователя не может быть пустым")
        self._username = value.strip()

    @property
    def hashed_password(self):
        """Хеш пароля SHA-256 для сохранения в хранилище."""
        return self._hashed_password

    @property
    def salt(self):
        """Индивидуальная соль, используемая при хешировании пароля."""
        return self._salt

    @property
    def registration_date(self):
        """Дата и время регистрации пользователя."""
        return self._registration_date

    def get_user_info(self) -> dict:
        """Возвращает публичные данные с ISO-датой, без хеша и соли."""
        return {
            "user_id": self.user_id,
            "username": self.username,
            "registration_date": self.registration_date.isoformat(),
        }

    def change_password(self, new_password: str) -> None:
        """Проверяет новый пароль и заменяет его хеш и соль."""
        self._validate_password(new_password)
        self._salt = secrets.token_hex(PASSWORD_SALT_BYTES)
        self._hashed_password = hashlib.sha256(
            (new_password + self.salt).encode()
        ).hexdigest()

    def verify_password(self, password: str) -> bool:
        """Проверяет пароль по сохранённым хешу и соли."""
        if not isinstance(password, str):
            return False
        hashed = hashlib.sha256((password + self.salt).encode()).hexdigest()
        return hmac.compare_digest(hashed, self.hashed_password)

    def to_dict(self) -> dict:
        """Возвращает данные пользователя для сериализации в JSON."""
        return {
            **self.get_user_info(),
            "hashed_password": self.hashed_password,
            "salt": self.salt,
        }

    @classmethod
    def from_dict(cls, data):
        """Восстанавливает пользователя из JSON-совместимого словаря."""
        return cls(
            data["user_id"],
            data["username"],
            data["hashed_password"],
            data["salt"],
            datetime.fromisoformat(data["registration_date"]),
        )


class Wallet:
    """Кошелёк одной валюты с конечным неотрицательным балансом."""

    def __init__(self, currency_code: str, balance: float = 0.0):
        """Создаёт кошелёк с проверенным кодом валюты и балансом."""
        self._currency_code = get_currency(currency_code).code
        self.balance = balance

    @property
    def currency_code(self):
        """Код валюты кошелька, неизменяемый после создания."""
        return self._currency_code

    @property
    def balance(self):
        """Конечный неотрицательный баланс кошелька."""
        return self._balance

    @balance.setter
    def balance(self, value):
        """Конечный неотрицательный баланс кошелька."""
        self._balance = number(value, positive=False)

    def deposit(self, amount: float) -> None:
        """Увеличивает баланс на положительную конечную сумму."""
        self.balance += number(amount)

    def withdraw(self, amount: float) -> None:
        """Списывает положительную сумму при достаточном остатке."""
        amount = number(amount)
        if amount > self.balance:
            raise InsufficientFundsError(self.balance, amount, self.currency_code)
        self.balance -= amount

    def get_balance_info(self) -> str:
        """Возвращает строку с кодом валюты и текущим балансом."""
        return f"{self.currency_code}: {self.balance:.4f}"


class Portfolio:
    """Набор кошельков пользователя с уникальными кодами валют."""

    def __init__(self, user: User, wallets: dict[str, Wallet] | None = None):
        """Привязывает портфель к пользователю и проверяет кошельки."""
        if not isinstance(user, User):
            raise TypeError("Владелец портфеля должен быть объектом User")
        self._user = user
        self._user_id = user.user_id
        self._wallets = dict(wallets) if wallets is not None else {}
        for code, wallet in self._wallets.items():
            get_currency(code)
            if not isinstance(wallet, Wallet) or wallet.currency_code != code:
                raise ValueError("Код кошелька должен совпадать с ключом словаря")

    @property
    def user_id(self):
        """Идентификатор владельца портфеля."""
        return self._user_id

    @property
    def user(self):
        """Объект владельца портфеля без возможности перезаписи."""
        return self._user

    @property
    def wallets(self):
        """Копия словаря, содержащая объекты кошельков портфеля."""
        return self._wallets.copy()

    def add_currency(self, code: str) -> Wallet:
        """Создаёт кошелёк; повторный код вызывает ValueError."""
        code = get_currency(code).code
        if code in self._wallets:
            raise ValueError(f"Кошелёк '{code}' уже существует")
        wallet = Wallet(code)
        self._wallets[code] = wallet
        return wallet

    def get_wallet(self, code: str) -> Wallet:
        """Возвращает кошелёк или сообщает об отсутствии валюты."""
        code = get_currency(code).code
        if code not in self._wallets:
            raise ValueError(
                f"У вас нет кошелька '{code}'. Добавьте валюту: "
                "она создаётся автоматически при первой покупке."
            )
        return self._wallets[code]

    def get_total_value(self, base="USD", exchange_rates=None) -> float:
        """Считает стоимость портфеля по курсам валют к USD."""
        base = get_currency(base).code
        rates = EXCHANGE_RATES if exchange_rates is None else exchange_rates
        if base not in rates:
            raise ApiRequestError(f"нет курса для {base}→USD")
        base_rate = number(rates[base])
        total = 0.0
        for code, wallet in self._wallets.items():
            if wallet.balance == 0:
                continue
            if code not in rates:
                raise ApiRequestError(f"нет курса для {code}→{base}")
            total += wallet.balance * number(rates[code]) / base_rate
        return number(total, positive=False)

    def to_dict(self):
        """Возвращает идентификатор и балансы для записи в JSON."""
        return {
            "user_id": self.user_id,
            "wallets": {
                code: {"balance": wallet.balance}
                for code, wallet in self._wallets.items()
            },
        }
