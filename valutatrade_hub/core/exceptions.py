class InsufficientFundsError(ValueError):
    """Недостаточный баланс для списания указанной суммы."""

    def __init__(self, available: float, required: float, code: str):
        """Сохраняет доступную сумму, требуемую сумму и валюту."""
        self.available = available
        self.required = required
        self.code = code
        super().__init__(
            f"Недостаточно средств: доступно {available:g} {code}, "
            f"требуется {required:g} {code}"
        )


class CurrencyNotFoundError(ValueError):
    """Запрошенная валюта отсутствует в реестре."""

    def __init__(self, code: str):
        """Сохраняет неизвестный код валюты."""
        self.code = code
        super().__init__(f"Неизвестная валюта '{code}'")


class ApiRequestError(Exception):
    """Источник курсов не смог предоставить корректные данные."""

    def __init__(self, reason: str):
        """Добавляет к причине ошибки единый префикс сообщения."""
        super().__init__(f"Ошибка при обращении к внешнему API: {reason}")
