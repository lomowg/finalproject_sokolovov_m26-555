import argparse
import shlex

from prettytable import PrettyTable

from valutatrade_hub.core.currencies import CURRENCIES
from valutatrade_hub.core.exceptions import (
    ApiRequestError,
    CurrencyNotFoundError,
    InsufficientFundsError,
)
from valutatrade_hub.core.usecases import WalletService
from valutatrade_hub.parser_service.updater import update_rates


class CommandParser(argparse.ArgumentParser):
    """Парсер аргументов, сохраняющий сеанс CLI при ошибках ввода."""

    def __init__(self, *args, **kwargs):
        """Создаёт парсер без дополнительных команд и флагов справки."""
        kwargs["add_help"] = False
        super().__init__(*args, **kwargs)

    def error(self, message):
        """Передаёт ошибку аргументов обработчику пользовательского ввода."""
        raise ValueError(message)


def build_parser():
    """Создаёт парсер команд валютного кошелька."""
    parser = CommandParser(prog="", description="Валютный кошелёк")
    commands = parser.add_subparsers(
        dest="command", required=True, parser_class=CommandParser
    )
    for name in ("register", "login"):
        command = commands.add_parser(name)
        command.add_argument("--username", required=True)
        command.add_argument("--password", required=True)
    command = commands.add_parser("show-portfolio")
    command.add_argument("--base")
    for name in ("buy", "sell"):
        command = commands.add_parser(name)
        command.add_argument("--currency", required=True)
        command.add_argument("--amount", type=float, required=True)
    command = commands.add_parser("get-rate")
    command.add_argument("--from", dest="source", required=True)
    command.add_argument("--to", dest="target", required=True)
    command = commands.add_parser("update-rates")
    command.add_argument("--source", choices=("coingecko", "exchangerate"))
    command = commands.add_parser("show-rates")
    command.add_argument("--currency")
    command.add_argument("--top", type=int)
    command.add_argument("--base", default="USD")
    return parser


class CLI:
    """Интерактивный интерфейс к операциям WalletService."""

    def __init__(self, service=None):
        """Подключает сервис кошелька и парсер команд."""
        self.service = service if service is not None else WalletService()
        self.parser = build_parser()

    def execute(self, line):
        """Разбирает команду, вызывает сервис и выводит результат или ошибку."""
        try:
            args = self.parser.parse_args(shlex.split(line))
            command = args.command
            if command == "register":
                user = self.service.register(args.username, args.password)
                print(
                    f"Пользователь '{user['username']}' зарегистрирован (id={user['user_id']}). "
                    f"Войдите: login --username {user['username']} --password ****"
                )
            elif command == "login":
                user = self.service.login(args.username, args.password)
                print(f"Вы вошли как '{user['username']}'")
            elif command == "show-portfolio":
                result = self.service.show_portfolio(args.base)
                print(
                    f"Портфель пользователя '{result['username']}' (база: {result['base']}):"
                )
                if not result["wallets"]:
                    print("Портфель пуст")
                else:
                    table = PrettyTable(
                        ["Валюта", "Баланс", f"Стоимость ({result['base']})"]
                    )
                    for row in result["wallets"]:
                        table.add_row(
                            [
                                row["currency"],
                                f"{row['balance']:.8f}",
                                f"{row['value']:,.2f}",
                            ]
                        )
                    print(table)
                print(f"ИТОГО: {result['total']:,.2f} {result['base']}")
            elif command in ("buy", "sell"):
                operation = self.service.buy if command == "buy" else self.service.sell
                result = operation(args.currency, args.amount)
                label = "Покупка" if command == "buy" else "Продажа"
                print(
                    f"{label} выполнена: {result['amount']:.4f} {result['currency']} "
                    f"по курсу {result['rate']:.8f} USD/{result['currency']}"
                )
                print(
                    f"Изменения в портфеле: {result['before']:.4f} → {result['after']:.4f}"
                )
                print(
                    f"Стоимость: {result['cost']:,.2f} USD; "
                    f"баланс USD: {result['usd_balance']:,.2f}"
                )
            elif command == "update-rates":
                result = update_rates(args.source)
                print(
                    f"Обновлено курсов: {result['updated']}. "
                    f"Последнее обновление: {result['last_refresh']}"
                )
                if result["errors"]:
                    print(
                        "Обновление завершено с ошибками. Подробности: logs/parser.log"
                    )
                    for error in result["errors"]:
                        print(error)
                else:
                    print("Обновление успешно завершено.")
            elif command == "show-rates":
                result = self.service.show_rates(args.currency, args.top, args.base)
                print(f"Курсы из кеша (обновлено: {result['last_refresh']}):")
                table = PrettyTable(["Пара", "Курс", "Обновлено", "Источник"])
                for row in result["rates"]:
                    table.add_row(
                        [
                            row["pair"],
                            f"{row['rate']:.8f}",
                            row["updated_at"],
                            row["source"],
                        ]
                    )
                print(table)
            elif command == "get-rate":
                result = self.service.get_rate(args.source, args.target)
                print(
                    f"Курс {args.source}→{args.target}: {result['rate']:.8f} "
                    f"(обновлено: {result['updated_at']})"
                )
                print(
                    f"Обратный курс {args.target}→{args.source}: {1 / result['rate']:.8f}"
                )
        except InsufficientFundsError as error:
            print(str(error))
        except CurrencyNotFoundError as error:
            print(str(error))
            print("Поддерживаемые валюты: " + ", ".join(sorted(CURRENCIES)))
        except ApiRequestError as error:
            print(str(error))
            print("Повторите попытку позже или проверьте подключение к сети.")
        except (ValueError, OSError, KeyError, TypeError, OverflowError) as error:
            print(f"Ошибка: {error}")

    def run(self):
        """Обрабатывает команды до конца ввода или прерывания с клавиатуры."""
        while True:
            try:
                line = input("> ")
            except (EOFError, KeyboardInterrupt):
                print()
                break
            if line.strip():
                self.execute(line)


def main():
    """Запускает интерактивный командный интерфейс."""
    try:
        CLI().run()
    except (ValueError, OSError) as error:
        print(f"Ошибка настройки приложения: {error}")
