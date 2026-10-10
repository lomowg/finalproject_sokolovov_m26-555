"""Периодическое обновление: python -m valutatrade_hub.parser_service.scheduler."""

from threading import Event

from valutatrade_hub.core.exceptions import ApiRequestError
from valutatrade_hub.core.utils import number
from valutatrade_hub.parser_service.config import ParserConfig
from valutatrade_hub.parser_service.updater import RatesUpdater


def run_scheduler(interval=None, stop_event=None):
    """Обновляет курсы с заданным интервалом до остановки или Ctrl+C."""
    interval = number(ParserConfig().UPDATE_INTERVAL if interval is None else interval)
    stop_event = stop_event if stop_event is not None else Event()
    updater = RatesUpdater()
    try:
        while not stop_event.is_set():
            try:
                updater.run_update()
            except (ApiRequestError, OSError, ValueError, TypeError, KeyError) as error:
                updater.logger.error("Scheduled update failed: %s", error)
            stop_event.wait(interval)
    except KeyboardInterrupt:
        updater.logger.info("Scheduler stopped")


if __name__ == "__main__":
    run_scheduler()
