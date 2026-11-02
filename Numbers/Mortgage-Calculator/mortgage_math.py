"""Mortgage math: rate conversion, amortization and payoff simulation.

Kept separate from the CLI so the calculations can be tested or reused
directly.  Every value is a :class:`decimal.Decimal`.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP, localcontext

CENT = Decimal("0.01")
PRECISION = 40

COMPOUNDING_CHOICES = ("monthly", "weekly", "daily", "continuously")


@dataclass(frozen=True)
class ScheduleRow:
    """One year of an amortization schedule."""

    year: int
    interest: Decimal
    principal: Decimal
    balance: Decimal


@dataclass(frozen=True)
class LoanResult:
    """Everything a summary needs for one loan."""

    payment: Decimal
    scheduled_months: int
    monthly_rate: Decimal
    months: int
    interest: Decimal
    paid: Decimal
    rows: list[ScheduleRow]


def monthly_rate(annual_percent: Decimal, compounding: str) -> Decimal:
    """Convert a nominal annual rate to an effective monthly rate."""
    with localcontext() as ctx:
        ctx.prec = PRECISION
        annual = annual_percent / Decimal(100)
        if annual == 0:
            return Decimal(0)
        if compounding == "monthly":
            return annual / Decimal(12)
        if compounding == "weekly":
            factor = (Decimal(1) + annual / Decimal(52)).ln() * Decimal(52) / Decimal(12)
            return factor.exp() - 1
        if compounding == "daily":
            factor = (Decimal(1) + annual / Decimal(365)).ln() * Decimal(365) / Decimal(12)
            return factor.exp() - 1
        if compounding == "continuously":
            return (annual / Decimal(12)).exp() - 1
        raise ValueError(f"unknown compounding interval: {compounding}")


def level_payment(principal: Decimal, rate: Decimal, months: int) -> Decimal:
    """Return the monthly payment, rounded to cents."""
    with localcontext() as ctx:
        ctx.prec = PRECISION
        if rate == 0:
            payment = principal / Decimal(months)
        else:
            factor = (Decimal(1) + rate) ** months
            payment = principal * rate * factor / (factor - 1)
    return payment.quantize(CENT, rounding=ROUND_HALF_UP)


def amortize(
    principal: Decimal,
    rate: Decimal,
    payment: Decimal,
    extra: Decimal,
    scheduled_months: int,
) -> tuple[int, Decimal, Decimal, list[ScheduleRow]]:
    """Simulate monthly payments until the balance reaches zero.

    The contractual final payment absorbs any cents-level residual so a loan
    does not report a spurious extra month.  Returns
    ``(months, total_interest, total_paid, yearly_rows)``.
    """
    balance = principal
    total_interest = Decimal(0)
    total_paid = Decimal(0)
    rows: list[ScheduleRow] = []
    year_interest = Decimal(0)
    year_principal = Decimal(0)
    months = 0

    while balance > 0 and months < 12 * 100:
        interest = (balance * rate).quantize(CENT, rounding=ROUND_HALF_UP)
        scheduled = payment + extra
        final_scheduled_month = months + 1 == scheduled_months
        if balance + interest <= scheduled or final_scheduled_month:
            scheduled = balance + interest
        principal_part = scheduled - interest
        balance = (balance - principal_part).quantize(CENT, rounding=ROUND_HALF_UP)
        total_interest += interest
        total_paid += scheduled
        year_interest += interest
        year_principal += principal_part
        months += 1

        if months % 12 == 0 or balance <= 0:
            rows.append(
                ScheduleRow(
                    year=(months + 11) // 12,
                    interest=year_interest,
                    principal=year_principal,
                    balance=max(balance, Decimal(0)),
                )
            )
            year_interest = Decimal(0)
            year_principal = Decimal(0)

    return months, total_interest, total_paid, rows


def summarize(
    principal: Decimal,
    annual_percent: Decimal,
    years: Decimal,
    compounding: str,
    extra: Decimal,
) -> LoanResult:
    """Compute payment and amortization for one loan."""
    months = int((years * 12).to_integral_value(rounding=ROUND_HALF_UP))
    if months < 1:
        raise ValueError("term must be at least one month")
    if months > 12 * 100:
        raise ValueError("term cannot exceed 100 years")
    rate = monthly_rate(annual_percent, compounding)
    payment = level_payment(principal, rate, months)
    actual_months, interest, paid, rows = amortize(
        principal, rate, payment, extra, months
    )
    return LoanResult(
        payment=payment,
        scheduled_months=months,
        monthly_rate=rate,
        months=actual_months,
        interest=interest,
        paid=paid,
        rows=rows,
    )
