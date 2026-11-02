#!/usr/bin/env python3
"""Work out change and the notes/coins needed to make it.

Amounts are parsed as decimals and converted to integer cents, so the coin
breakdown never suffers from floating-point drift.  By default the breakdown
uses quarters, dimes, nickels and pennies, as the classic exercise asks; pass
``--bills`` to include $20/$10/$5/$1 notes first.
"""

from __future__ import annotations

import argparse
import sys
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

COINS = (
    ("quarter", 25),
    ("dime", 10),
    ("nickel", 5),
    ("penny", 1),
)
BILLS = (
    ("$20 bill", 2000),
    ("$10 bill", 1000),
    ("$5 bill", 500),
    ("$1 bill", 100),
)
NAMES = {
    "quarter": ("quarter", "quarters"),
    "dime": ("dime", "dimes"),
    "nickel": ("nickel", "nickels"),
    "penny": ("penny", "pennies"),
}


def parse_money(raw: str, label: str) -> Decimal:
    """Parse a money amount into a Decimal with at most two decimals."""
    try:
        value = Decimal(raw.strip().replace(",", "").replace("$", ""))
    except (AttributeError, InvalidOperation) as exc:
        raise ValueError(f"{label} must be a dollar amount: {raw!r}") from exc
    if not value.is_finite() or value < 0:
        raise ValueError(f"{label} must be a non-negative amount")
    return value


def to_cents(amount: Decimal) -> int:
    """Convert a dollar Decimal to integer cents, rounding half up."""
    return int((amount * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def make_change(cost: Decimal, paid: Decimal, include_bills: bool = False) -> list[tuple[str, int, int]]:
    """Return ``(name, unit_cents, count)`` rows for the change.

    Raises:
        ValueError: when the payment does not cover the cost.
    """
    change = to_cents(paid) - to_cents(cost)
    if change < 0:
        raise ValueError(
            f"insufficient payment: short by ${abs(change) / 100:.2f}"
        )

    denominations = (BILLS + COINS) if include_bills else COINS
    rows = []
    remaining = change
    for name, unit in denominations:
        count, remaining = divmod(remaining, unit)
        if count:
            rows.append((name, unit, count))
    return rows


def format_money(cents: int) -> str:
    """Format integer cents as a dollar string."""
    return f"${Decimal(cents) / 100:,.2f}"


def print_change(cost: Decimal, paid: Decimal, include_bills: bool) -> None:
    """Print the change summary and denomination breakdown."""
    change_cents = to_cents(paid) - to_cents(cost)
    if change_cents < 0:
        raise ValueError(f"insufficient payment: short by {format_money(-change_cents)}")

    print(f"Cost:   {format_money(to_cents(cost))}")
    print(f"Paid:   {format_money(to_cents(paid))}")
    print(f"Change: {format_money(change_cents)}")
    rows = make_change(cost, paid, include_bills)
    if not rows:
        print("Exact change - no coins or bills needed.")
        return
    for name, unit, count in rows:
        singular, plural = NAMES.get(name, (name, name))
        label = singular if count == 1 else plural
        print(
            f"  {count:>3} x {label:<10} ({format_money(unit)} each) "
            f"= {format_money(unit * count)}"
        )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Calculate change and the coins/bills that make it.",
        epilog="Run with no arguments to be prompted for cost and payment.",
    )
    parser.add_argument("--cost", help="purchase cost, e.g. 12.34")
    parser.add_argument("--paid", help="amount handed over, e.g. 20.00")
    parser.add_argument(
        "--bills",
        action="store_true",
        help="include $20/$10/$5/$1 notes in the breakdown",
    )
    parser.add_argument("--demo", action="store_true", help="run scripted examples")
    return parser


def ask(prompt: str) -> str:
    """Prompt, converting EOF into a clean cancellation."""
    try:
        return input(prompt)
    except (EOFError, KeyboardInterrupt) as exc:
        raise ValueError("cancelled") from exc


def run_demo() -> int:
    """Show coin-only and bill-inclusive breakdowns."""
    print("Change return demo")
    print("=" * 17)

    print("\nCoins only ($12.34 cost, $20.00 paid):")
    print_change(Decimal("12.34"), Decimal("20.00"), include_bills=False)

    print("\nWith bills ($12.34 cost, $20.00 paid):")
    print_change(Decimal("12.34"), Decimal("20.00"), include_bills=True)

    print("\nOdd amount ($4.99 cost, $5.00 paid):")
    print_change(Decimal("4.99"), Decimal("5.00"), include_bills=False)

    print("\nInsufficient payment ($10.00 cost, $5.00 paid):")
    try:
        print_change(Decimal("10.00"), Decimal("5.00"), include_bills=False)
    except ValueError as exc:
        print(f"  Error: {exc}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.demo:
        return run_demo()

    try:
        cost = parse_money(args.cost if args.cost is not None else ask("Cost: $"), "cost")
        paid = parse_money(args.paid if args.paid is not None else ask("Paid: $"), "paid")
        print_change(cost, paid, args.bills)
    except (ValueError, ArithmeticError) as exc:
        message = str(exc)
        print("Cancelled." if message == "cancelled" else f"Error: {message}", file=sys.stderr)
        return 0 if message == "cancelled" else 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
