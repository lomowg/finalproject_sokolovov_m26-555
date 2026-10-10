import inspect
import math
from functools import wraps

from valutatrade_hub.logging_config import setup_logging


def log_action(action: str, *, verbose: bool = False):
    """Записывает исход операции; verbose добавляет балансы до и после сделки."""

    def decorate(method):
        signature = inspect.signature(method)

        @wraps(method)
        def wrapped(self, *args, **kwargs):
            logger = setup_logging()
            arguments = signature.bind(self, *args, **kwargs).arguments
            user = self.current_user
            amount = arguments.get("amount")
            if isinstance(amount, float) and not math.isfinite(amount):
                amount = str(amount)
            fields = {
                "action": action.upper(),
                "username": user.username if user is not None else None,
                "currency_code": arguments.get("currency"),
                "amount": amount,
                "rate": None,
                "base": "USD",
            }
            try:
                result = method(self, *args, **kwargs)
            except Exception as error:
                fields["rate"] = getattr(error, "rate", None)
                fields.update(
                    result="ERROR",
                    error_type=type(error).__name__,
                    error_message=str(error),
                )
                logger.info("%s", action, extra={"action_data": fields})
                raise
            fields.update(
                result="OK", rate=result.get("rate"), base=result.get("base", "USD")
            )
            if verbose:
                fields["context"] = {
                    key: result[key]
                    for key in ("before", "after", "usd_balance")
                    if key in result
                }
            logger.info("%s", action, extra={"action_data": fields})
            return result

        return wrapped

    return decorate
