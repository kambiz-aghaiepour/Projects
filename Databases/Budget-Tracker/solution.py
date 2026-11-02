#!/usr/bin/env python3
"""Budget Tracker: household accounts, transactions, recurring costs, reports.

Amounts are stored as integer cents.  Transactions are actual income/expense
entries; recurring schedules are projections used to estimate committed costs
in a date range.  Reports show actual cash flow, recurring obligations, the
resulting projected net, savings rate, category breakdowns, monthly trends, and
account balances.  Transactions can be exported to and imported from CSV.
"""

from __future__ import annotations

import argparse
import calendar
import csv
import sqlite3
import sys
import tempfile
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path
from typing import Iterable, Sequence

DEFAULT_DB = Path("budget.db")
ACCOUNT_KINDS = ("checking", "savings", "credit", "cash")
FREQUENCIES = ("weekly", "monthly", "yearly")
CSV_HEADERS = ["date", "type", "account", "category", "description", "amount"]

SCHEMA = """
CREATE TABLE IF NOT EXISTS accounts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    kind TEXT NOT NULL DEFAULT 'checking',
    opening_cents INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS categories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    kind TEXT NOT NULL CHECK (kind IN ('income', 'expense'))
);
CREATE TABLE IF NOT EXISTS transactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    account_id INTEGER NOT NULL REFERENCES accounts(id),
    category_id INTEGER NOT NULL REFERENCES categories(id),
    date TEXT NOT NULL,
    type TEXT NOT NULL CHECK (type IN ('income', 'expense')),
    amount_cents INTEGER NOT NULL CHECK (amount_cents > 0),
    description TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS recurring (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    account_id INTEGER NOT NULL REFERENCES accounts(id),
    category_id INTEGER NOT NULL REFERENCES categories(id),
    description TEXT NOT NULL,
    amount_cents INTEGER NOT NULL CHECK (amount_cents > 0),
    frequency TEXT NOT NULL CHECK (frequency IN ('weekly', 'monthly', 'yearly')),
    next_due TEXT NOT NULL,
    active INTEGER NOT NULL DEFAULT 1
);
CREATE INDEX IF NOT EXISTS idx_transactions_date ON transactions(date);
"""


@dataclass
class RecurringRow:
    id: int
    description: str
    category: str
    account: str
    amount_cents: int
    frequency: str
    next_due: date


def connect(db_path: Path) -> sqlite3.Connection:
    """Open the budget database, creating the schema if needed."""
    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.executescript(SCHEMA)
    return connection


def parse_amount(text: str, allow_zero: bool = False) -> int:
    """Parse a dollar amount ('1,234.56', '$12') into cents."""
    cleaned = str(text).replace("$", "").replace(",", "").strip()
    try:
        value = Decimal(cleaned)
    except InvalidOperation as exc:
        raise ValueError(f"invalid amount '{text}'") from exc
    if not value.is_finite():
        raise ValueError(f"invalid amount '{text}'")
    if value < 0 or (value == 0 and not allow_zero):
        raise ValueError("amount must be greater than zero" if not allow_zero
                         else "amount must not be negative")
    return int((value * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def money(cents: int) -> str:
    sign = "-" if cents < 0 else ""
    return f"{sign}${abs(cents) / 100:,.2f}"


def parse_date(text: str, label: str = "date") -> date:
    try:
        return date.fromisoformat(text.strip())
    except ValueError as exc:
        raise ValueError(f"{label} must be YYYY-MM-DD, got '{text}'") from exc


def add_months(moment: date, months: int) -> date:
    index = moment.month - 1 + months
    year = moment.year + index // 12
    month = index % 12 + 1
    day = min(moment.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def advance(moment: date, frequency: str) -> date:
    if frequency == "weekly":
        from datetime import timedelta
        return moment + timedelta(days=7)
    if frequency == "monthly":
        return add_months(moment, 1)
    try:
        return moment.replace(year=moment.year + 1)
    except ValueError:
        return moment.replace(year=moment.year + 1, day=28)


def get_or_create_account(conn: sqlite3.Connection, name: str, kind: str = "checking") -> int:
    row = conn.execute("SELECT id FROM accounts WHERE name = ?", (name,)).fetchone()
    if row:
        return int(row["id"])
    if kind not in ACCOUNT_KINDS:
        raise ValueError(f"account kind must be one of {', '.join(ACCOUNT_KINDS)}")
    cursor = conn.execute("INSERT INTO accounts(name, kind) VALUES (?, ?)", (name, kind))
    return int(cursor.lastrowid or 0)


def get_or_create_category(conn: sqlite3.Connection, name: str, kind: str) -> int:
    row = conn.execute("SELECT id, kind FROM categories WHERE name = ?", (name,)).fetchone()
    if row:
        if row["kind"] != kind:
            raise ValueError(f"category '{name}' already exists as {row['kind']}")
        return int(row["id"])
    if kind not in {"income", "expense"}:
        raise ValueError("category kind must be income or expense")
    cursor = conn.execute("INSERT INTO categories(name, kind) VALUES (?, ?)", (name, kind))
    return int(cursor.lastrowid or 0)


def add_account(conn: sqlite3.Connection, name: str, kind: str = "checking",
                opening: int = 0) -> int:
    """Create an account; opening balance is in cents (may be negative)."""
    if not name.strip():
        raise ValueError("account name must not be empty")
    if kind not in ACCOUNT_KINDS:
        raise ValueError(f"account kind must be one of {', '.join(ACCOUNT_KINDS)}")
    try:
        cursor = conn.execute(
            "INSERT INTO accounts(name, kind, opening_cents) VALUES (?, ?, ?)",
            (name.strip(), kind, opening),
        )
    except sqlite3.IntegrityError as exc:
        raise ValueError(f"account '{name}' already exists") from exc
    conn.commit()
    return int(cursor.lastrowid or 0)


def resolve_account(conn: sqlite3.Connection, account: str) -> str:
    """Use the only existing account when the default 'Checking' is absent."""
    if account != "Checking":
        return account
    names = [row["name"] for row in conn.execute("SELECT name FROM accounts ORDER BY id")]
    if "Checking" not in names and len(names) == 1:
        return names[0]
    return account


def add_transaction(conn: sqlite3.Connection, txn_date: date, txn_type: str,
                    amount_cents: int, category: str, account: str = "Checking",
                    description: str = "") -> int:
    """Record income or an expense against an account/category."""
    if txn_type not in {"income", "expense"}:
        raise ValueError("type must be income or expense")
    if amount_cents <= 0:
        raise ValueError("amount must be greater than zero")
    account_id = get_or_create_account(conn, resolve_account(conn, account))
    category_id = get_or_create_category(conn, category, txn_type)
    cursor = conn.execute(
        """INSERT INTO transactions(account_id, category_id, date, type, amount_cents, description)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (account_id, category_id, txn_date.isoformat(), txn_type, amount_cents, description.strip()),
    )
    conn.commit()
    return int(cursor.lastrowid or 0)


def add_recurring(conn: sqlite3.Connection, description: str, amount_cents: int,
                  frequency: str, next_due: date, category: str,
                  account: str = "Checking") -> int:
    """Add a recurring expense projection."""
    if amount_cents <= 0:
        raise ValueError("amount must be greater than zero")
    if frequency not in FREQUENCIES:
        raise ValueError(f"frequency must be one of {', '.join(FREQUENCIES)}")
    if not description.strip():
        raise ValueError("description must not be empty")
    account_id = get_or_create_account(conn, resolve_account(conn, account))
    category_id = get_or_create_category(conn, category, "expense")
    cursor = conn.execute(
        """INSERT INTO recurring(account_id, category_id, description, amount_cents,
                                 frequency, next_due, active)
           VALUES (?, ?, ?, ?, ?, ?, 1)""",
        (account_id, category_id, description.strip(), amount_cents, frequency,
         next_due.isoformat()),
    )
    conn.commit()
    return int(cursor.lastrowid or 0)


def stop_recurring(conn: sqlite3.Connection, recurring_id: int) -> bool:
    cursor = conn.execute("UPDATE recurring SET active = 0 WHERE id = ?", (recurring_id,))
    conn.commit()
    return cursor.rowcount > 0


def recurring_rows(conn: sqlite3.Connection) -> list[RecurringRow]:
    rows = conn.execute(
        """SELECT r.*, c.name AS category_name, a.name AS account_name
           FROM recurring r JOIN categories c ON c.id = r.category_id
           JOIN accounts a ON a.id = r.account_id
           WHERE r.active = 1 ORDER BY r.next_due, r.description"""
    ).fetchall()
    return [
        RecurringRow(int(row["id"]), row["description"], row["category_name"],
                     row["account_name"], int(row["amount_cents"]), row["frequency"],
                     date.fromisoformat(row["next_due"]))
        for row in rows
    ]


def recurring_in_range(schedule: RecurringRow, start: date, end: date) -> int:
    """Count occurrences of a schedule within the inclusive range."""
    current = schedule.next_due
    guard = 0
    while current < start and guard < 5000:
        current = advance(current, schedule.frequency)
        guard += 1
    count = 0
    while current <= end and count < 1000:
        count += 1
        current = advance(current, schedule.frequency)
    return count


def month_keys(start: date, end: date) -> list[str]:
    keys = []
    year, month = start.year, start.month
    while (year, month) <= (end.year, end.month):
        keys.append(f"{year:04d}-{month:02d}")
        month += 1
        if month == 13:
            year, month = year + 1, 1
    return keys


def text_table(headers: Sequence[str], rows: Iterable[Sequence[object]],
               right: Iterable[int] = ()) -> str:
    right_set = set(right)
    body = [[str(value) for value in row] for row in rows]
    widths = [len(header) for header in headers]
    for row in body:
        widths = [max(width, len(value)) for width, value in zip(widths, row)]
    line = "+" + "+".join("-" * (width + 2) for width in widths) + "+"

    def render(values: Sequence[str]) -> str:
        cells = []
        for index, (value, width) in enumerate(zip(values, widths)):
            cells.append(value.rjust(width) if index in right_set else value.ljust(width))
        return "| " + " | ".join(cells) + " |"

    output = [line, render(list(headers)), line]
    output.extend(render(row) for row in body)
    output.append(line)
    return "\n".join(output)


@dataclass
class BudgetReport:
    start: date
    end: date
    income: int
    expenses: int
    recurring_total: int
    recurring_count: int
    categories: list[tuple[str, str, int]]
    monthly: list[tuple[str, int, int]]
    accounts: list[tuple[str, str, int]]
    schedules: list[tuple[str, str, str, int, int, int]]

    @property
    def net(self) -> int:
        return self.income - self.expenses

    @property
    def projected_net(self) -> int:
        return self.net - self.recurring_total

    @property
    def savings_rate(self) -> float | None:
        if self.income <= 0:
            return None
        return self.projected_net / self.income * 100.0


def build_report(conn: sqlite3.Connection, start: date, end: date,
                 include_recurring: bool = True) -> BudgetReport:
    """Compute all report figures for the inclusive range."""
    params = (start.isoformat(), end.isoformat())
    income = int(conn.execute(
        "SELECT COALESCE(SUM(amount_cents), 0) FROM transactions "
        "WHERE type = 'income' AND date BETWEEN ? AND ?", params
    ).fetchone()[0])
    expenses = int(conn.execute(
        "SELECT COALESCE(SUM(amount_cents), 0) FROM transactions "
        "WHERE type = 'expense' AND date BETWEEN ? AND ?", params
    ).fetchone()[0])

    categories = [
        (row["kind"], row["name"], int(row["total"]))
        for row in conn.execute(
            """SELECT c.kind, c.name, SUM(t.amount_cents) AS total
               FROM transactions t JOIN categories c ON c.id = t.category_id
               WHERE t.date BETWEEN ? AND ?
               GROUP BY c.id ORDER BY c.kind, total DESC""", params
        )
    ]
    monthly_rows = conn.execute(
        """SELECT substr(date, 1, 7) AS month,
                  SUM(CASE WHEN type = 'income' THEN amount_cents ELSE 0 END),
                  SUM(CASE WHEN type = 'expense' THEN amount_cents ELSE 0 END)
           FROM transactions WHERE date BETWEEN ? AND ? GROUP BY month ORDER BY month""", params
    ).fetchall()
    monthly_map = {row["month"]: (int(row[1]), int(row[2])) for row in monthly_rows}
    monthly = [(key, *monthly_map.get(key, (0, 0))) for key in month_keys(start, end)]

    accounts = [
        (row["name"], row["kind"], int(row["balance"]))
        for row in conn.execute(
            """SELECT a.name, a.kind,
                      a.opening_cents + COALESCE(SUM(CASE WHEN t.type = 'income'
                          THEN t.amount_cents ELSE -t.amount_cents END), 0) AS balance
               FROM accounts a
               LEFT JOIN transactions t ON t.account_id = a.id AND t.date <= ?
               GROUP BY a.id ORDER BY a.name""", (end.isoformat(),)
        )
    ]

    recurring_total = 0
    recurring_count = 0
    schedules = []
    if include_recurring:
        for schedule in recurring_rows(conn):
            count = recurring_in_range(schedule, start, end)
            if count:
                recurring_total += count * schedule.amount_cents
                recurring_count += count
                schedules.append((schedule.description, schedule.category,
                                  schedule.frequency, schedule.amount_cents, count,
                                  count * schedule.amount_cents))

    return BudgetReport(
        start=start, end=end, income=income, expenses=expenses,
        recurring_total=recurring_total, recurring_count=recurring_count,
        categories=categories, monthly=monthly, accounts=accounts, schedules=schedules,
    )


def render_report(report: BudgetReport, include_recurring: bool = True) -> str:
    """Render the budget report as text."""
    lines = [
        "=" * 74,
        f"BUDGET REPORT  {report.start.isoformat()} to {report.end.isoformat()}".center(74),
        "=" * 74,
        f"Income (actual):              {money(report.income)}",
        f"Expenses (actual):            {money(report.expenses)}",
        f"Net cash flow:                {money(report.net)}",
    ]
    if include_recurring:
        lines.append(f"Recurring commitments:        {money(report.recurring_total)}"
                     f"  ({report.recurring_count} charge(s) in range)")
        lines.append(f"Projected net after recurring: {money(report.projected_net)}")
    rate = report.savings_rate if include_recurring else (
        report.net / report.income * 100 if report.income > 0 else None)
    lines.append("Savings rate:                 "
                 + ("n/a (no income)" if rate is None else f"{rate:.1f}% of income"))
    lines.append("")
    lines.append("SPENDING BY CATEGORY")
    category_rows = []
    for kind, name, total in report.categories:
        share = total / (report.income if kind == "income" else report.expenses or 1) * 100
        category_rows.append((kind.title(), name, money(total), f"{share:.1f}%"))
    lines.append(text_table(["Type", "Category", "Amount", "Share"], category_rows, (2, 3)))
    lines.append("")
    lines.append("MONTHLY TREND")
    lines.append(text_table(
        ["Month", "Income", "Expenses", "Net"],
        [(month, money(inc), money(exp), money(inc - exp)) for month, inc, exp in report.monthly],
        (1, 2, 3),
    ))
    if include_recurring:
        lines.append("")
        lines.append("RECURRING COST PROJECTION")
        if report.schedules:
            lines.append(text_table(
                ["Description", "Category", "Frequency", "Amount", "Charges", "Total"],
                [(desc, cat, freq, money(amount), str(count), money(total))
                 for desc, cat, freq, amount, count, total in report.schedules],
                (3, 4, 5),
            ))
        else:
            lines.append("  (no recurring costs fall in this range)")
    lines.append("")
    lines.append("ACCOUNT BALANCES (through " + report.end.isoformat() + ")")
    lines.append(text_table(["Account", "Kind", "Balance"],
                            [(name, kind, money(balance)) for name, kind, balance in report.accounts],
                            (2,)))
    return "\n".join(lines)


def export_csv(conn: sqlite3.Connection, path: Path) -> int:
    """Write all transactions to CSV; return the row count."""
    rows = conn.execute(
        """SELECT t.date, t.type, a.name, c.name, t.description, t.amount_cents
           FROM transactions t JOIN accounts a ON a.id = t.account_id
           JOIN categories c ON c.id = t.category_id
           ORDER BY t.date, t.id"""
    ).fetchall()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(CSV_HEADERS)
        for row in rows:
            writer.writerow([row[0], row[1], row[2], row[3], row[4],
                             f"{row[5] / 100:.2f}"])
    return len(rows)


def import_csv(conn: sqlite3.Connection, path: Path) -> int:
    """Import transactions from CSV after validating every row."""
    try:
        with path.open(newline="", encoding="utf-8-sig") as handle:
            reader = csv.DictReader(handle)
            missing = [header for header in CSV_HEADERS if header not in (reader.fieldnames or [])]
            if missing:
                raise ValueError("CSV is missing column(s): " + ", ".join(missing))
            raw_rows = list(reader)
    except OSError as exc:
        raise ValueError(f"cannot read {path}: {exc}") from exc

    parsed = []
    for line_number, row in enumerate(raw_rows, start=2):
        if not any((value or "").strip() for value in row.values()):
            continue
        try:
            txn_type = (row["type"] or "").strip().lower()
            if txn_type not in {"income", "expense"}:
                raise ValueError("type must be income or expense")
            parsed.append({
                "date": parse_date(row["date"] or "", f"row {line_number} date"),
                "type": txn_type,
                "account": (row["account"] or "Checking").strip() or "Checking",
                "category": (row["category"] or "Uncategorized").strip() or "Uncategorized",
                "description": (row["description"] or "").strip(),
                "amount": parse_amount(row["amount"] or ""),
                "line": line_number,
            })
        except ValueError as exc:
            raise ValueError(f"CSV row {line_number}: {exc}") from exc

    for item in parsed:
        account_id = get_or_create_account(conn, item["account"])
        category_id = get_or_create_category(conn, item["category"], item["type"])
        conn.execute(
            """INSERT INTO transactions(account_id, category_id, date, type,
                                        amount_cents, description)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (account_id, category_id, item["date"].isoformat(), item["type"],
             item["amount"], item["description"]),
        )
    conn.commit()
    return len(parsed)


def list_accounts(conn: sqlite3.Connection) -> str:
    rows = conn.execute(
        """SELECT a.name, a.kind, a.opening_cents,
                  a.opening_cents + COALESCE(SUM(CASE WHEN t.type = 'income'
                      THEN t.amount_cents ELSE -t.amount_cents END), 0) AS balance
           FROM accounts a LEFT JOIN transactions t ON t.account_id = a.id
           GROUP BY a.id ORDER BY a.name"""
    ).fetchall()
    if not rows:
        return "No accounts yet."
    return text_table(["Account", "Kind", "Opening", "Current balance"],
                      [(row[0], row[1], money(int(row[2])), money(int(row[3]))) for row in rows],
                      (2, 3))


def seed_demo(conn: sqlite3.Connection) -> None:
    """Create a three-month household budget with salary and recurring costs."""
    add_account(conn, "Checking", "checking", opening=250_000)
    add_account(conn, "Savings", "savings", opening=800_000)
    add_account(conn, "Credit Card", "credit", opening=0)

    for month, day in ((1, 1), (2, 1), (3, 1)):
        add_transaction(conn, date(2026, month, day), "income", 420_000, "Salary",
                        "Checking", "Monthly salary")
    add_transaction(conn, date(2026, 2, 15), "income", 60_000, "Freelance",
                    "Checking", "Website project")

    groceries = [("2026-01-08", 14_350), ("2026-01-22", 12_100), ("2026-02-06", 15_600),
                 ("2026-02-20", 13_250), ("2026-03-06", 14_800), ("2026-03-21", 13_900)]
    for day, amount in groceries:
        add_transaction(conn, date.fromisoformat(day), "expense", amount, "Groceries",
                        "Checking", "Weekly groceries")
    for month, amount in ((1, 12_000), (2, 13_500), (3, 11_800)):
        add_transaction(conn, date(2026, month, 12), "expense", amount, "Utilities",
                        "Checking", "Electricity and water")
    for month, amount in ((1, 6_500), (2, 7_200), (3, 5_900), (3, 8_100)):
        add_transaction(conn, date(2026, month, 18), "expense", amount, "Dining",
                        "Credit Card", "Restaurants")
    for month, amount in ((1, 4_500), (2, 4_500), (3, 4_500)):
        add_transaction(conn, date(2026, month, 3), "expense", amount, "Transport",
                        "Checking", "Transit pass")
    add_transaction(conn, date(2026, 2, 9), "expense", 3_000, "Entertainment",
                    "Credit Card", "Cinema")

    add_recurring(conn, "Rent", 145_000, "monthly", date(2026, 1, 1), "Rent", "Checking")
    add_recurring(conn, "Internet", 6_000, "monthly", date(2026, 1, 5), "Utilities", "Checking")
    add_recurring(conn, "Gym membership", 4_500, "monthly", date(2026, 1, 7), "Health", "Checking")


def run_demo() -> int:
    """Seed a sample budget, print a report, and round-trip CSV import/export."""
    print("Budget Tracker — demo")
    with tempfile.TemporaryDirectory(prefix="budget-tracker-") as tmp:
        db_path = Path(tmp) / "budget.db"
        with connect(db_path) as conn:
            seed_demo(conn)
            print("Seeded 3 accounts, 3 recurring costs, and 3 months of transactions\n")
            report = build_report(conn, date(2026, 1, 1), date(2026, 3, 31))
            print(render_report(report))
            print("\n--- ACCOUNTS ---")
            print(list_accounts(conn))

            csv_path = Path(tmp) / "transactions.csv"
            exported = export_csv(conn, csv_path)
            print(f"\nExported {exported} transactions to CSV ({csv_path.stat().st_size:,} bytes)")

            second_path = Path(tmp) / "imported.db"
            with connect(second_path) as second:
                imported = import_csv(second, csv_path)
                copy_report = build_report(second, date(2026, 1, 1), date(2026, 3, 31))
                print(f"Imported {imported} transactions into a fresh database")
                print(f"Round-trip totals match: "
                      f"{copy_report.income == report.income and copy_report.expenses == report.expenses}"
                      f" (income {money(copy_report.income)}, expenses {money(copy_report.expenses)})")
        print("\nDemo complete. Real use: python3 solution.py --db budget.db --report "
              "--from 2026-01-01 --to 2026-03-31")
    return 0


def interactive(db_path: Path) -> int:
    """Small menu-driven budget entry tool."""
    with connect(db_path) as conn:
        while True:
            print("\n1) report  2) add transaction  3) add recurring  4) add account"
                  "  5) accounts  6) export CSV  0) quit")
            choice = input("Choose: ").strip()
            try:
                if choice == "0":
                    return 0
                if choice == "1":
                    start = parse_date(input("From (YYYY-MM-DD): "))
                    end = parse_date(input("To (YYYY-MM-DD): "))
                    print(render_report(build_report(conn, start, end)))
                elif choice == "2":
                    txn_type = input("Type [expense]: ").strip() or "expense"
                    amount = parse_amount(input("Amount: "))
                    category = input("Category: ").strip() or "Uncategorized"
                    account = input("Account [Checking]: ").strip() or "Checking"
                    day = parse_date(input("Date (YYYY-MM-DD): "))
                    description = input("Description: ")
                    add_transaction(conn, day, txn_type, amount, category, account, description)
                    print("Transaction recorded.")
                elif choice == "3":
                    description = input("Description: ")
                    amount = parse_amount(input("Amount: "))
                    frequency = input("Frequency (weekly/monthly/yearly) [monthly]: ").strip() or "monthly"
                    next_due = parse_date(input("Next due (YYYY-MM-DD): "))
                    category = input("Category: ").strip() or "Uncategorized"
                    add_recurring(conn, description, amount, frequency, next_due, category)
                    print("Recurring cost added.")
                elif choice == "4":
                    name = input("Account name: ")
                    kind = input(f"Kind {ACCOUNT_KINDS} [checking]: ").strip() or "checking"
                    opening = parse_amount(input("Opening balance [$0]: ") or "0", allow_zero=True)
                    add_account(conn, name, kind, opening)
                    print("Account added.")
                elif choice == "5":
                    print(list_accounts(conn))
                elif choice == "6":
                    path = Path(input("CSV path [transactions.csv]: ") or "transactions.csv")
                    print(f"Exported {export_csv(conn, path)} transactions.")
                else:
                    print("Unknown choice.")
            except (ValueError, sqlite3.Error, OSError) as exc:
                print(f"error: {exc}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="solution.py",
        description="Track accounts, income, expenses, and recurring costs; report savings over time.",
    )
    parser.add_argument("--db", type=Path, default=DEFAULT_DB, help="SQLite database (default: budget.db)")
    parser.add_argument("--add-account", metavar="NAME", help="create an account")
    parser.add_argument("--kind", choices=ACCOUNT_KINDS, default="checking", help="account kind")
    parser.add_argument("--opening", default="0", help="opening balance in dollars (default 0)")
    parser.add_argument("--add-txn", action="store_true", help="record a transaction")
    parser.add_argument("--date", help="transaction date YYYY-MM-DD (default today)")
    parser.add_argument("--type", choices=("income", "expense"), default="expense")
    parser.add_argument("--amount", help="amount in dollars, e.g. 42.50")
    parser.add_argument("--category", help="category name (created if missing)")
    parser.add_argument("--account", default="Checking", help="account name (created if missing)")
    parser.add_argument("--description", default="", help="transaction description")
    parser.add_argument("--add-recurring", action="store_true", help="add a recurring expense")
    parser.add_argument("--frequency", choices=FREQUENCIES, default="monthly")
    parser.add_argument("--next-due", help="first recurring date YYYY-MM-DD")
    parser.add_argument("--stop-recurring", type=int, metavar="ID", help="deactivate a recurring cost")
    parser.add_argument("--accounts", action="store_true", help="list accounts and balances")
    parser.add_argument("--report", action="store_true", help="show a budget report")
    parser.add_argument("--from", dest="start", metavar="YYYY-MM-DD", help="report start date")
    parser.add_argument("--to", dest="end", metavar="YYYY-MM-DD", help="report end date")
    parser.add_argument("--no-recurring", action="store_true",
                        help="exclude recurring projections from the report")
    parser.add_argument("--export-csv", type=Path, metavar="FILE", help="export transactions to CSV")
    parser.add_argument("--import-csv", type=Path, metavar="FILE", help="import transactions from CSV")
    parser.add_argument("--demo", action="store_true", help="run the scripted demo")
    args = parser.parse_args(argv)

    if args.demo:
        return run_demo()
    if len(sys.argv) == 1 and argv is None:
        return interactive(args.db)
    try:
        with connect(args.db) as conn:
            if args.add_account:
                opening = parse_amount(args.opening, allow_zero=True)
                account_id = add_account(conn, args.add_account, args.kind, opening)
                print(f"Added account #{account_id} '{args.add_account}'.")
                return 0
            if args.add_txn:
                if not args.amount or not args.category:
                    parser.error("--add-txn requires --amount and --category")
                day = parse_date(args.date) if args.date else date.today()
                txn_id = add_transaction(
                    conn, day, args.type, parse_amount(args.amount), args.category,
                    args.account, args.description,
                )
                print(f"Recorded transaction #{txn_id}.")
                return 0
            if args.add_recurring:
                if not args.amount or not args.next_due or not args.description:
                    parser.error("--add-recurring requires --amount, --next-due, and --description")
                recurring_id = add_recurring(
                    conn, args.description, parse_amount(args.amount), args.frequency,
                    parse_date(args.next_due, "--next-due"),
                    args.category or "Uncategorized", args.account,
                )
                print(f"Added recurring cost #{recurring_id}.")
                return 0
            if args.stop_recurring is not None:
                if stop_recurring(conn, args.stop_recurring):
                    print(f"Deactivated recurring cost #{args.stop_recurring}.")
                    return 0
                print(f"error: recurring cost #{args.stop_recurring} not found", file=sys.stderr)
                return 2
            if args.accounts:
                print(list_accounts(conn))
                return 0
            if args.report:
                start = parse_date(args.start, "--from") if args.start else date.today().replace(day=1)
                end = parse_date(args.end, "--to") if args.end else date.today()
                if start > end:
                    raise ValueError("--from must be on or before --to")
                report = build_report(conn, start, end, include_recurring=not args.no_recurring)
                print(render_report(report, include_recurring=not args.no_recurring))
                return 0
            if args.export_csv:
                print(f"Exported {export_csv(conn, args.export_csv)} transactions to {args.export_csv}.")
                return 0
            if args.import_csv:
                print(f"Imported {import_csv(conn, args.import_csv)} transactions from {args.import_csv}.")
                return 0
            parser.print_help()
            return 0
    except (ValueError, sqlite3.Error, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("\ninterrupted", file=sys.stderr)
        raise SystemExit(130)
