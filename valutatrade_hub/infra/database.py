from contextlib import contextmanager
from copy import deepcopy
from threading import RLock

from valutatrade_hub.core.utils import read_json, write_json
from valutatrade_hub.infra.settings import SettingsLoader


class DatabaseManager:
    """Единая точка доступа к JSON."""

    _instance = None
    _creation_lock = RLock()

    def __new__(cls):
        """Создаёт единственный менеджер и общую блокировку хранилища."""
        with cls._creation_lock:
            if cls._instance is None:
                instance = super().__new__(cls)
                instance._settings = SettingsLoader()
                instance._lock = RLock()
                cls._instance = instance
            return cls._instance

    def _path(self, name):
        if name not in ("users", "portfolios", "rates"):
            raise ValueError(f"Неизвестное хранилище: {name}")
        return self._settings.get(f"{name}_file")

    def _read(self, name):
        expected = dict if name == "rates" else list
        data = read_json(self._path(name), expected())
        self._validate(name, data)
        return data

    @staticmethod
    def _validate(name, data):
        expected = dict if name == "rates" else list
        if not isinstance(data, expected):
            raise TypeError(f"Некорректная структура хранилища {name}")
        if expected is list and any(not isinstance(item, dict) for item in data):
            raise ValueError(f"Хранилище {name} должно содержать список объектов")

    def read(self, name: str):
        """Читает независимый снимок хранилища users, portfolios или rates."""
        with self._lock:
            return self._read(name)

    def write(self, name: str, data) -> None:
        """Проверяет структуру и атомарно заменяет один JSON-файл."""
        with self._lock:
            self._validate(name, data)
            write_json(self._path(name), data)

    @contextmanager
    def transaction(self, *names):
        """Блокирует чтение и изменение. При ошибке записи восстанавливает файлы.

        Блокировка действует внутри процесса. При аварийном завершении процесса
        атомарность гарантируется только для каждого отдельного JSON-файла.
        """
        with self._lock:
            original = {name: self._read(name) for name in names}
            existed = {name: self._path(name).exists() for name in names}
            working = deepcopy(original)
            yield working
            for name in names:
                self._validate(name, working[name])
            written = []
            try:
                for name in names:
                    if working[name] != original[name]:
                        self.write(name, working[name])
                        written.append(name)
            except (OSError, ValueError, TypeError):
                for name in reversed(written):
                    if existed[name]:
                        self.write(name, original[name])
                    else:
                        self._path(name).unlink(missing_ok=True)
                raise
