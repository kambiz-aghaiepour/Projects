#!/usr/bin/env python3
"""Fixed-rate mortgage calculator with selectable compounding.

Computes the level monthly payment, simulates the amortization schedule to
report the true payoff time, and supports extra monthly principal payments.
The math lives in :mod:`mortgage_math`; all values use `Decimal`.
"""

from __future__ import annotations

import argparse
import sys
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from mortgage_math import (
    CENT,
    COMPOUNDING_CHOICES,
    LoanResult,
    summarize,
)


def money(value: Decimal) -> str:
    """Format a Decimal as a money amount."""
    return f"{value.quantize(CENT, rounding=ROUND_HALF_UP):,.2f}"


def parse_decimal(raw: str, label: str, *, minimum: str = "0") -> Decimal:
    """Parse a Decimal >= minimum."""
    try:
        value = Decimal(raw.strip().replace(",", "").replace("$", ""))
    except (AttributeError, InvalidOperation) as exc:
        raise ValueError(f"{label} must be a number: {raw!r}") from exc
    if not value.is_finite() or value < Decimal(minimum):
        raise ValueError(f"{label} must be at least {minimum}")
    return value


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Calculate mortgage payments and payoff time.",
        epilog="Run with no arguments for an interactive walkthrough.",
    )
    parser.add_argument("--principal", help="loan amount, e.g. 300000")
    parser.add_argument("--rate", help="nominal annual interest rate in percent")
    parser.add_argument("--years", help="term in years (default: 30)")
    parser.add_argument(
        "--compounding",
        choices=COMPOUNDING_CHOICES,
        default="monthly",
        help="compounding interval (default: monthly)",
    )
    parser.add_argument("--extra", default="0", help="extra principal paid each month")
    parser.add_argument(
        "--schedule", action="store_true", help="print a year-by-year summary"
    )
    parser.add_argument("--demo", action="store_true", help="run scripted examples")
    return parser


def ask(prompt: str) -> str:
    """Read a line, raising ValueError on EOF."""
    try:
        return input(prompt)
    except (EOFError, KeyboardInterrupt) as exc:
        raise ValueError("cancelled") from exc


def print_result(
    label: str,
    principal: Decimal,
    annual_percent: Decimal,
    years: Decimal,
    compounding: str,
    extra: Decimal,
    schedule: bool,
) -> LoanResult:
    """Print a formatted summary and return the computed values."""
    result = summarize(principal, annual_percent, years, compounding, extra)
    years_paid, remainder = divmod(result.months, 12)
    print(f"\n{label}")
    print(f"  Principal:          ${money(principal)}")
    print(f"  Annual rate:        {annual_percent}% ({compounding} compounding)")
    print(f"  Scheduled term:     {years} years ({result.scheduled_months} months)")
    print(f"  Monthly payment:    ${money(result.payment)}")
    if extra:
        print(f"  Extra principal:    ${money(extra)}/month")
    print(f"  Payoff time:        {years_paid} yr {remainder} mo ({result.months} payments)")
    print(f"  Total interest:     ${money(result.interest)}")
    print(f"  Total paid:         ${money(result.paid)}")

    if schedule and result.rows:
        print("  Year   Interest      Principal      Balance")
        for row in result.rows:
            print(
                f"  {row.year:>4}   ${money(row.interest):>11}  "
                f"${money(row.principal):>11}  ${money(row.balance):>12}"
            )
    return result


def run_demo() -> int:
    """Compare a baseline loan, compounding options and extra payments."""
    print("Mortgage calculator demo")
    print("=" * 24)

    baseline = print_result(
        "Baseline: $300,000 at 6.5% for 30 years",
        Decimal("300000"),
        Decimal("6.5"),
        Decimal("30"),
        "monthly",
        Decimal("0"),
        schedule=False,
    )

    print("\nCompounding comparison: $250,000 at 5.25% over 15 years")
    print("  Interval        Monthly payment   Total interest")
    for option in COMPOUNDING_CHOICES:
        result = summarize(
            Decimal("250000"), Decimal("5.25"), Decimal("15"), option, Decimal("0")
        )
        print(
            f"  {option:<14}  ${money(result.payment):>13}   "
            f"${money(result.interest):>12}"
        )

    print("\nExtra payment: $300,000 at 6.5% for 30 years with $200 extra/month")
    extra_result = print_result(
        "With $200 extra principal each month",
        Decimal("300000"),
        Decimal("6.5"),
        Decimal("30"),
        "monthly",
        Decimal("200"),
        schedule=False,
    )
    print(f"  Interest saved:     ${money(baseline.interest - extra_result.interest)}")
    print(f"  Months saved:       {baseline.months - extra_result.months}")

    print("\nYear-by-year schedule sample: $120,000 at 5% for 10 years")
    print_result(
        "Schedule sample",
        Decimal("120000"),
        Decimal("5"),
        Decimal("10"),
        "monthly",
        Decimal("0"),
        schedule=True,
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.demo:
        return run_demo()

    try:
        principal = parse_decimal(
            args.principal if args.principal is not None else ask("Loan principal: "),
            "principal",
            minimum="0.01",
        )
        rate = parse_decimal(
            args.rate if args.rate is not None else ask("Annual interest rate (%): "),
            "rate",
        )
        if args.years is not None:
            raw_years = args.years
        elif args.principal is not None and args.rate is not None:
            raw_years = "30"
        else:
            raw_years = ask("Term in years [30]: ") or "30"
        years = parse_decimal(raw_years, "term", minimum="0.01")
        extra = parse_decimal(args.extra, "extra payment")
        print_result(
            "Mortgage summary",
            principal,
            rate,
            years,
            args.compounding,
            extra,
            args.schedule,
        )
    except (ValueError, ArithmeticError) as exc:
        message = str(exc)
        print(
            "Cancelled." if message == "cancelled" else f"Error: {message}",
            file=sys.stderr,
        )
        return 0 if message == "cancelled" else 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
