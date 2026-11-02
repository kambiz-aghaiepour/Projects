#!/usr/bin/env python3
"""Bank account manager with an abstract Account hierarchy.

``Account`` defines the deposit/withdraw template and the transaction journal.
Three concrete accounts apply different rules:

* ``CheckingAccount`` - overdraft up to a limit, flat overdraft fee.
* ``SavingsAccount``  - minimum balance, monthly interest, limited free
  withdrawals.
* ``BusinessAccount`` - credit line, monthly fee, per-debit transaction fee.

``Bank`` coordinates accounts, transfers and month-end processing.  The CLI is
an ATM-style menu; ``--demo`` runs a deterministic scripted session.
"""

from __future__ import annotations

import argparse
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Callable

MoneyLike = Decimal | int | float | str
Clock = Callable[[], datetime]


class BankError(Exception):
    """Raised when a banking operation is invalid."""


def q(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def money(value: Decimal) -> str:
    sign = "-" if value < 0 else ""
    return f"{sign}${abs(value):,.2f}"


def signed_money(value: Decimal) -> str:
    return f"{'+' if value >= 0 else '-'}${abs(value):,.2f}"


def as_money(value: MoneyLike, field: str = "amount") -> Decimal:
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise ValueError(f"{field} must be a number") from None
    if not result.is_finite():
        raise ValueError(f"{field} must be a finite number")
    return q(result)


def as_rate(value: MoneyLike, field: str = "rate") -> Decimal:
    """Parse a rate as a decimal fraction without rounding to cents."""
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise ValueError(f"{field} must be a number") from None
    if not result.is_finite() or result < 0:
        raise ValueError(f"{field} must be a non-negative finite number")
    return result


@dataclass(frozen=True)
class Transaction:
    """A single journal entry.  ``amount`` is signed."""

    when: datetime
    kind: str
    amount: Decimal
    balance_after: Decimal
    note: str = ""

    def line(self) -> str:
        return (
            f"{self.when:%Y-%m-%d %H:%M}  {self.kind:<12} "
            f"{signed_money(self.amount):>12}  {money(self.balance_after):>12}  {self.note}"
        )


class Account(ABC):
    """Abstract bank account: shared ledger, template withdraw logic."""

    kind = "Account"

    def __init__(
        self,
        number: str,
        owner: str,
        opening: MoneyLike = Decimal("0"),
        clock: Clock | None = None,
    ) -> None:
        if not number.strip():
            raise ValueError("account number must not be empty")
        if not owner.strip():
            raise ValueError("account owner must not be empty")
        self.number = number.strip().upper()
        self.owner = owner.strip()
        self._clock = clock or datetime.now
        self._balance = as_money(opening, "opening balance")
        if self._balance < 0:
            raise ValueError("opening balance must not be negative")
        self._history: list[Transaction] = []
        if self._balance:
            self._record("OPENING", self._balance, "account opened")

    @property
    def balance(self) -> Decimal:
        return self._balance

    @property
    def history(self) -> tuple[Transaction, ...]:
        return tuple(self._history)

    @property
    @abstractmethod
    def rules(self) -> str:
        """One-line description of this account's fee/interest rules."""

    @abstractmethod
    def _authorize(self, amount: Decimal) -> None:
        """Raise :class:`BankError` if a withdrawal of ``amount`` is not allowed."""

    def _settle_withdrawal(self, amount: Decimal, prior_balance: Decimal) -> None:
        """Hook for fees triggered by a completed withdrawal."""

    def _record(self, kind: str, amount: Decimal, note: str = "") -> Transaction:
        transaction = Transaction(
            when=self._clock(),
            kind=kind,
            amount=q(amount),
            balance_after=self._balance,
            note=note,
        )
        self._history.append(transaction)
        return transaction

    def deposit(self, amount: MoneyLike, note: str = "") -> Transaction:
        value = as_money(amount)
        if value <= 0:
            raise BankError("deposit amount must be positive")
        self._balance += value
        return self._record("DEPOSIT", value, note)

    def withdraw(self, amount: MoneyLike, note: str = "") -> Transaction:
        value = as_money(amount)
        if value <= 0:
            raise BankError("withdrawal amount must be positive")
        self._authorize(value)
        prior = self._balance
        self._balance -= value
        transaction = self._record("WITHDRAWAL", -value, note)
        self._settle_withdrawal(value, prior)
        return transaction

    def charge_fee(self, amount: MoneyLike, reason: str) -> Transaction:
        value = as_money(amount)
        if value <= 0:
            raise BankError("fee must be positive")
        self._balance -= value
        return self._record("FEE", -value, reason)

    def credit_interest(self, amount: MoneyLike) -> Transaction:
        value = as_money(amount)
        if value <= 0:
            raise BankError("interest must be positive")
        self._balance += value
        return self._record("INTEREST", value, "monthly interest")

    def monthly_close(self) -> list[Transaction]:
        """Apply monthly interest/fees; base accounts have none."""
        return []

    def statement(self, limit: int | None = None) -> str:
        header = (
            f"{self.kind} {self.number} - {self.owner}\n"
            f"{self.rules}\n"
            f"Balance: {money(self._balance)}"
        )
        lines = [
            "",
            f"{'WHEN':<16}  {'TYPE':<12} {'AMOUNT':>12}  {'BALANCE':>12}  NOTE",
            "-" * 78,
        ]
        entries = self._history if limit is None else self._history[-limit:]
        lines.extend(entry.line() for entry in entries)
        return header + "\n".join(lines)

    def __str__(self) -> str:
        return f"{self.number} {self.kind} ({self.owner}) {money(self._balance)}"


class CheckingAccount(Account):
    """Everyday account with a bounded overdraft and flat overdraft fee."""

    kind = "Checking"

    def __init__(
        self,
        number: str,
        owner: str,
        opening: MoneyLike = Decimal("0"),
        *,
        overdraft_limit: MoneyLike = Decimal("500"),
        overdraft_fee: MoneyLike = Decimal("35"),
        clock: Clock | None = None,
    ) -> None:
        super().__init__(number, owner, opening, clock)
        self.overdraft_limit = as_money(overdraft_limit, "overdraft limit")
        self.overdraft_fee = as_money(overdraft_fee, "overdraft fee")

    @property
    def rules(self) -> str:
        return (
            f"Overdraft up to {money(self.overdraft_limit)}; "
            f"{money(self.overdraft_fee)} fee when an overdraft begins."
        )

    def _authorize(self, amount: Decimal) -> None:
        projected = self._balance - amount
        fee = (
            self.overdraft_fee
            if self._balance >= 0 and projected < 0
            else Decimal("0")
        )
        if projected - fee < -self.overdraft_limit:
            available = self._balance + self.overdraft_limit - fee
            raise BankError(
                f"{self.number}: insufficient funds (available {money(available)})"
            )

    def _settle_withdrawal(self, amount: Decimal, prior_balance: Decimal) -> None:
        if prior_balance >= 0 and self._balance < 0:
            self.charge_fee(self.overdraft_fee, "overdraft fee")


class SavingsAccount(Account):
    """Interest-bearing account with a minimum balance and withdrawal limit."""

    kind = "Savings"
    FREE_WITHDRAWALS = 6

    def __init__(
        self,
        number: str,
        owner: str,
        opening: MoneyLike = Decimal("0"),
        *,
        annual_rate: MoneyLike = Decimal("0.025"),
        minimum_balance: MoneyLike = Decimal("100"),
        extra_withdrawal_fee: MoneyLike = Decimal("10"),
        clock: Clock | None = None,
    ) -> None:
        super().__init__(number, owner, opening, clock)
        self.annual_rate = as_rate(annual_rate, "annual rate")
        self.minimum_balance = as_money(minimum_balance, "minimum balance")
        self.extra_withdrawal_fee = as_money(extra_withdrawal_fee, "withdrawal fee")
        if self.annual_rate > 1:
            raise ValueError("annual rate must be a decimal fraction or percent <= 100")

    @property
    def rules(self) -> str:
        return (
            f"Min balance {money(self.minimum_balance)}; {self.annual_rate:.2%} APY; "
            f"{self.FREE_WITHDRAWALS} free withdrawals/month, then "
            f"{money(self.extra_withdrawal_fee)} each."
        )

    def _authorize(self, amount: Decimal) -> None:
        fee = (
            self.extra_withdrawal_fee
            if self._withdrawals_this_month() >= self.FREE_WITHDRAWALS
            else Decimal("0")
        )
        if self._balance - amount - fee < self.minimum_balance:
            raise BankError(
                f"{self.number}: withdrawal would breach minimum balance "
                f"{money(self.minimum_balance)}"
            )

    def _withdrawals_this_month(self) -> int:
        now = self._clock()
        return sum(
            1
            for entry in self._history
            if entry.kind == "WITHDRAWAL"
            and entry.when.year == now.year
            and entry.when.month == now.month
        )

    def _settle_withdrawal(self, amount: Decimal, prior_balance: Decimal) -> None:
        if self._withdrawals_this_month() > self.FREE_WITHDRAWALS:
            self.charge_fee(self.extra_withdrawal_fee, "extra withdrawal fee")

    def monthly_close(self) -> list[Transaction]:
        interest = q(self._balance * self.annual_rate / Decimal("12"))
        return [self.credit_interest(interest)] if interest > 0 else []


class BusinessAccount(Account):
    """Business account with a credit line, monthly fee and debit fees."""

    kind = "Business"

    def __init__(
        self,
        number: str,
        owner: str,
        opening: MoneyLike = Decimal("0"),
        *,
        credit_line: MoneyLike = Decimal("5000"),
        monthly_fee: MoneyLike = Decimal("25"),
        transaction_fee: MoneyLike = Decimal("0.75"),
        clock: Clock | None = None,
    ) -> None:
        super().__init__(number, owner, opening, clock)
        self.credit_line = as_money(credit_line, "credit line")
        self.monthly_fee = as_money(monthly_fee, "monthly fee")
        self.transaction_fee = as_money(transaction_fee, "transaction fee")

    @property
    def rules(self) -> str:
        return (
            f"Credit line {money(self.credit_line)}; "
            f"{money(self.monthly_fee)}/month; "
            f"{money(self.transaction_fee)} per debit."
        )

    def _authorize(self, amount: Decimal) -> None:
        projected = self._balance - amount - self.transaction_fee
        if projected < -self.credit_line:
            available = self._balance + self.credit_line - self.transaction_fee
            raise BankError(
                f"{self.number}: credit line exhausted (available {money(available)})"
            )

    def _settle_withdrawal(self, amount: Decimal, prior_balance: Decimal) -> None:
        self.charge_fee(self.transaction_fee, "transaction fee")

    def monthly_close(self) -> list[Transaction]:
        return [self.charge_fee(self.monthly_fee, "monthly account fee")]


class Bank:
    """Owns accounts and performs transfers and month-end processing."""

    def __init__(self, name: str, clock: Clock | None = None) -> None:
        if not name.strip():
            raise ValueError("bank name must not be empty")
        self.name = name.strip()
        self._clock = clock or datetime.now
        self.accounts: dict[str, Account] = {}
        self._counters = {"checking": 1000, "savings": 2000, "business": 3000}
        self._prefixes = {"checking": "CHK", "savings": "SAV", "business": "BUS"}

    def _next_number(self, kind: str) -> str:
        self._counters[kind] += 1
        return f"{self._prefixes[kind]}-{self._counters[kind]}"

    def add_account(self, account: Account) -> Account:
        if account.number in self.accounts:
            raise BankError(f"account {account.number} already exists")
        self.accounts[account.number] = account
        return account

    def open_account(
        self,
        kind: str,
        owner: str,
        opening: MoneyLike = Decimal("0"),
        **options,
    ) -> Account:
        """Create and register an account of ``kind``."""
        key = kind.strip().lower()
        builders = {
            "checking": CheckingAccount,
            "savings": SavingsAccount,
            "business": BusinessAccount,
        }
        if key not in builders:
            raise BankError(f"unknown account type: {kind}")
        account = builders[key](
            self._next_number(key), owner, opening, clock=self._clock, **options
        )
        return self.add_account(account)

    def get(self, number: str) -> Account:
        key = number.strip().upper()
        try:
            return self.accounts[key]
        except KeyError:
            raise BankError(f"unknown account: {key}") from None

    def transfer(
        self, source: str, destination: str, amount: MoneyLike
    ) -> tuple[Transaction, Transaction]:
        src = self.get(source)
        dst = self.get(destination)
        if src is dst:
            raise BankError("cannot transfer to the same account")
        value = as_money(amount)
        if value <= 0:
            raise BankError("transfer amount must be positive")
        out = src.withdraw(value, f"transfer to {dst.number}")
        incoming = dst.deposit(value, f"transfer from {src.number}")
        return out, incoming

    def month_end(self) -> list[Transaction]:
        """Run monthly close on every account and return new entries."""
        applied: list[Transaction] = []
        for account in self.accounts.values():
            applied.extend(account.monthly_close())
        return applied

    @property
    def total_deposits(self) -> Decimal:
        return q(sum((account.balance for account in self.accounts.values()), Decimal("0")))

    def summary_report(self) -> str:
        header = f"{'ACCOUNT':<10} {'TYPE':<10} {'OWNER':<16} {'BALANCE':>12}  RULES"
        lines = [header, "-" * (len(header) + 20)]
        for account in self.accounts.values():
            lines.append(
                f"{account.number:<10} {account.kind:<10} {account.owner:<16} "
                f"{money(account.balance):>12}  {account.rules}"
            )
        if not self.accounts:
            lines.append("(no accounts)")
        return "\n".join(lines)


class FixedClock:
    """Deterministic clock that advances one minute per transaction."""

    def __init__(self, start: datetime) -> None:
        self._current = start

    def __call__(self) -> datetime:
        self._current += timedelta(minutes=1)
        return self._current


def build_demo_bank() -> Bank:
    """Create the demo bank and its three accounts."""
    clock = FixedClock(datetime(2026, 6, 30, 9, 0))
    bank = Bank("Harbor Community Bank", clock)
    bank.open_account("checking", "Alice Nguyen", "1200")
    bank.open_account("savings", "Alice Nguyen", "5000")
    bank.open_account("business", "Acme Design LLC", "8000")
    return bank


def run_demo() -> int:
    """Exercise deposits, overdrafts, fees, transfers and month-end."""
    bank = build_demo_bank()
    checking = bank.get("CHK-1001")
    savings = bank.get("SAV-2001")
    business = bank.get("BUS-3001")
    assert isinstance(checking, CheckingAccount)
    assert isinstance(savings, SavingsAccount)
    assert isinstance(business, BusinessAccount)

    print(f"== {bank.name} - ATM Demo ==")
    print("\n-- Accounts opened --")
    print(bank.summary_report())

    print("\n-- Checking activity --")
    print(f"  deposit $500        -> {money(checking.deposit('500').balance_after)}")
    print(f"  withdraw $200       -> {money(checking.withdraw('200').balance_after)}")
    overdraft = checking.withdraw("1800", "rent")
    print(f"  withdraw $1,800     -> {money(overdraft.balance_after)} "
          f"(overdraft fee {money(checking.overdraft_fee)} applied)")
    print(f"  deposit $400        -> {money(checking.deposit('400').balance_after)}")

    print("\n-- Savings activity (7 x $20, 6 free per month) --")
    for _ in range(7):
        savings.withdraw("20")
    print(f"  balance after 7 withdrawals: {money(savings.balance)} "
          f"(includes one {money(savings.extra_withdrawal_fee)} fee)")

    print("\n-- Business activity --")
    business.withdraw("1000", "supplier payment")
    print(f"  withdraw $1,000 -> {money(business.balance)} "
          f"(includes {money(business.transaction_fee)} debit fee)")
    bank.transfer("BUS-3001", "CHK-1001", "500")
    print(f"  transfer $500 business -> checking -> "
          f"checking {money(checking.balance)}, business {money(business.balance)}")

    print("\n-- Rejected operations --")
    for label, action in (
        ("overdraft limit", lambda: checking.withdraw("5000")),
        ("below minimum", lambda: savings.withdraw("4900")),
        ("credit exhausted", lambda: business.withdraw("20000")),
        ("negative deposit", lambda: checking.deposit("-10")),
        ("self transfer", lambda: bank.transfer("CHK-1001", "CHK-1001", "10")),
    ):
        try:
            action()
            print(f"  {label:<16} -> unexpectedly succeeded")
        except BankError as exc:
            print(f"  {label:<16} -> {exc}")

    balance_before = bank.total_deposits
    print("\n-- Month-end processing --")
    for entry in bank.month_end():
        print(f"  {entry.kind:<11} {signed_money(entry.amount):>10}  {entry.note}")
    print(f"  Total bank deposits: {money(balance_before)} -> {money(bank.total_deposits)}")

    print("\n-- Statements --")
    print(checking.statement())
    print()
    print(savings.statement(limit=6))
    print("\n  (showing last 6 of "
          f"{len(savings.history)} savings entries)")
    print()
    print(business.statement())
    return 0


def prompt_account(bank: Bank, message: str = "Account number") -> Account:
    return bank.get(input(f"{message}: ").strip())


def interactive(bank_name: str) -> int:
    """ATM-style menu over a fresh bank."""
    bank = Bank(bank_name)
    menu = (
        "\n1) Accounts        2) Open account    3) Deposit\n"
        "4) Withdraw        5) Transfer        6) Statement\n"
        "7) Month-end       8) Quit"
    )
    print(f"Welcome to {bank.name}.")
    while True:
        print(menu)
        try:
            choice = input("Choice: ").strip()
        except EOFError:
            print()
            return 0
        try:
            if choice == "1":
                print(bank.summary_report())
            elif choice == "2":
                kind = input("Type (checking/savings/business): ").strip()
                owner = input("Owner name: ").strip()
                opening = input("Opening balance [0]: ").strip() or "0"
                account = bank.open_account(kind, owner, opening)
                print(f"Opened {account.number} with {money(account.balance)}.")
            elif choice == "3":
                account = prompt_account(bank)
                amount = input("Amount: ").strip()
                entry = account.deposit(amount)
                print(f"Deposited; balance {money(entry.balance_after)}.")
            elif choice == "4":
                account = prompt_account(bank)
                amount = input("Amount: ").strip()
                entry = account.withdraw(amount)
                print(f"Withdrew; balance {money(entry.balance_after)}.")
            elif choice == "5":
                source = input("From account: ").strip()
                destination = input("To account: ").strip()
                amount = input("Amount: ").strip()
                bank.transfer(source, destination, amount)
                print(f"Transferred {money(as_money(amount))}.")
            elif choice == "6":
                account = prompt_account(bank)
                print(account.statement())
            elif choice == "7":
                for entry in bank.month_end():
                    print(f"  {entry.kind} {signed_money(entry.amount)} {entry.note}")
            elif choice == "8":
                print("Goodbye.")
                return 0
            else:
                print("Please choose 1-8.")
        except (BankError, ValueError) as exc:
            print(f"Error: {exc}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Manage checking, savings and business accounts with an ATM-style CLI.",
        epilog="Run without arguments for the interactive ATM menu.",
    )
    parser.add_argument("--demo", action="store_true", help="run the scripted demo")
    parser.add_argument(
        "--bank", default="Harbor Community Bank", help="bank name for interactive mode"
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.demo:
        return run_demo()
    try:
        return interactive(args.bank)
    except KeyboardInterrupt:
        print("\nInterrupted.")
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
