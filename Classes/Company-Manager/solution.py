#!/usr/bin/env python3
"""Company payroll manager built around an abstract Employee hierarchy.

Each employee type computes pay differently:

* ``HourlyEmployee``  - hourly rate with 1.5x overtime after 80 hours in a
  biweekly period (two 40-hour weeks).
* ``SalariedEmployee``- fixed annual salary paid biweekly (26 periods).
* ``Manager``         - salary + a bonus percentage + a per-report stipend.
* ``Executive``       - salary + a performance award percentage.

``Company`` owns the roster and exposes hire / fire / raise operations plus a
payroll report.  The CLI wraps the same API for interactive use.
"""

from __future__ import annotations

import argparse
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, ROUND_HALF_UP

PERIODS_PER_YEAR = Decimal("26")
STANDARD_WORK_YEAR = Decimal("2080")

MoneyLike = Decimal | int | float | str


class CompanyError(Exception):
    """Raised for invalid roster or payroll operations."""


def q(value: Decimal) -> Decimal:
    """Round money to cents."""
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def money(value: Decimal) -> str:
    return f"${value:,.2f}"


def as_decimal(value: Decimal | int | float | str, field: str) -> Decimal:
    try:
        result = Decimal(str(value))
    except Exception:
        raise ValueError(f"{field} must be a number") from None
    if result < 0:
        raise ValueError(f"{field} must not be negative")
    return result


class Employee(ABC):
    """Abstract base class for everyone on the payroll."""

    role = "Employee"

    def __init__(self, employee_id: str, name: str, title: str, hired: date) -> None:
        if not employee_id.strip():
            raise ValueError("employee id must not be empty")
        if not name.strip():
            raise ValueError("name must not be empty")
        if not isinstance(hired, date):
            raise ValueError("hire date must be a date")
        self.employee_id = employee_id.strip().upper()
        self.name = name.strip()
        self.title = title.strip() or self.role
        self.hired = hired
        self.active = True
        self.terminated_on: date | None = None
        self.raises: list[tuple[date, Decimal]] = []

    def __str__(self) -> str:
        status = "active" if self.active else f"left {self.terminated_on}"
        return f"{self.employee_id} {self.name} ({self.title}, {self.role}, {status})"

    @property
    @abstractmethod
    def annual_base(self) -> Decimal:
        """Contractual annual base pay, excluding bonuses."""

    @abstractmethod
    def calculate_pay(self, hours_worked: float = 0.0) -> Decimal:
        """Gross pay for one biweekly pay period."""

    @abstractmethod
    def regular_period_pay(self) -> Decimal:
        """Pay for a normal period without overtime or bonuses."""

    @abstractmethod
    def _apply_raise(self, percent: Decimal) -> None:
        """Mutate the underlying rate or salary by ``percent``."""

    @abstractmethod
    def pay_note(self, hours_worked: float = 0.0) -> str:
        """Human-readable explanation of how this period's pay was derived."""

    def give_raise(self, percent: Decimal, effective: date | None = None) -> None:
        """Apply a percentage raise and record it."""
        percent = as_decimal(percent, "raise percent")
        if percent <= 0 or percent > 100:
            raise ValueError("raise percent must be between 0 and 100")
        self._apply_raise(percent)
        self.raises.append((effective or date.today(), percent))

    def severance(self, weeks: int = 2) -> Decimal:
        """Severance pay: regular pay for the given number of weeks."""
        if weeks < 0:
            raise ValueError("severance weeks must not be negative")
        return q(self.regular_period_pay() * Decimal(weeks) / Decimal("2"))

    def annual_cost_estimate(self) -> Decimal:
        """Projected yearly cost including normal bonuses."""
        return q(self.calculate_pay(self.standard_period_hours()) * PERIODS_PER_YEAR)

    def standard_period_hours(self) -> float:
        return 0.0

    def check_hours(self, hours_worked: float) -> float:
        hours = float(hours_worked)
        if hours < 0 or hours > 168:
            raise ValueError("hours worked must be between 0 and 168")
        return hours


class HourlyEmployee(Employee):
    """Paid by the hour, with overtime after 40 hours in a week."""

    role = "Hourly"

    def __init__(
        self,
        employee_id: str,
        name: str,
        title: str,
        hired: date,
        hourly_rate: MoneyLike,
        overtime_multiplier: MoneyLike = Decimal("1.5"),
    ) -> None:
        super().__init__(employee_id, name, title, hired)
        self.hourly_rate = as_decimal(hourly_rate, "hourly rate")
        self.overtime_multiplier = as_decimal(overtime_multiplier, "overtime multiplier")
        if self.hourly_rate <= 0:
            raise ValueError("hourly rate must be positive")
        if self.overtime_multiplier < 1:
            raise ValueError("overtime multiplier must be at least 1")

    @property
    def annual_base(self) -> Decimal:
        return q(self.hourly_rate * STANDARD_WORK_YEAR)

    def calculate_pay(self, hours_worked: float = 0.0) -> Decimal:
        hours = self.check_hours(hours_worked)
        regular = min(hours, 80.0)
        overtime = max(0.0, hours - 80.0)
        pay = self.hourly_rate * Decimal(str(regular))
        pay += self.hourly_rate * self.overtime_multiplier * Decimal(str(overtime))
        return q(pay)

    def regular_period_pay(self) -> Decimal:
        return q(self.hourly_rate * Decimal("80"))

    def _apply_raise(self, percent: Decimal) -> None:
        self.hourly_rate = q(self.hourly_rate * (Decimal("1") + percent / Decimal("100")))

    def pay_note(self, hours_worked: float = 0.0) -> str:
        hours = self.check_hours(hours_worked)
        overtime = max(0.0, hours - 80.0)
        note = f"{hours:g} h at {money(self.hourly_rate)}/h"
        if overtime:
            note += f" (+{overtime:g} h OT at {self.overtime_multiplier}x)"
        return note

    def standard_period_hours(self) -> float:
        return 80.0


class SalariedEmployee(Employee):
    """Paid a fixed annual salary in 26 equal biweekly periods."""

    role = "Salaried"

    def __init__(
        self,
        employee_id: str,
        name: str,
        title: str,
        hired: date,
        annual_salary: MoneyLike,
    ) -> None:
        super().__init__(employee_id, name, title, hired)
        self.annual_salary = as_decimal(annual_salary, "annual salary")
        if self.annual_salary <= 0:
            raise ValueError("annual salary must be positive")

    @property
    def annual_base(self) -> Decimal:
        return q(self.annual_salary)

    def period_salary(self) -> Decimal:
        return q(self.annual_salary / PERIODS_PER_YEAR)

    def calculate_pay(self, hours_worked: float = 0.0) -> Decimal:
        self.check_hours(hours_worked)
        return self.period_salary()

    def regular_period_pay(self) -> Decimal:
        return self.period_salary()

    def _apply_raise(self, percent: Decimal) -> None:
        self.annual_salary = q(
            self.annual_salary * (Decimal("1") + percent / Decimal("100"))
        )

    def pay_note(self, hours_worked: float = 0.0) -> str:
        return "Biweekly salary (annual / 26)"


class Manager(SalariedEmployee):
    """Salaried manager with a bonus percentage and per-report stipend."""

    role = "Manager"

    def __init__(
        self,
        employee_id: str,
        name: str,
        title: str,
        hired: date,
        annual_salary: MoneyLike,
        team_size: int = 0,
        bonus_rate: MoneyLike = Decimal("0.10"),
        report_stipend: MoneyLike = Decimal("50"),
    ) -> None:
        super().__init__(employee_id, name, title, hired, annual_salary)
        if team_size < 0:
            raise ValueError("team size must not be negative")
        self.team_size = int(team_size)
        self.bonus_rate = as_decimal(bonus_rate, "bonus rate")
        self.report_stipend = as_decimal(report_stipend, "report stipend")
        if self.bonus_rate > 1:
            raise ValueError("bonus rate must be between 0 and 1")

    def bonus(self) -> Decimal:
        return q(self.period_salary() * self.bonus_rate)

    def calculate_pay(self, hours_worked: float = 0.0) -> Decimal:
        self.check_hours(hours_worked)
        return q(
            self.period_salary()
            + self.bonus()
            + self.report_stipend * Decimal(self.team_size)
        )

    def pay_note(self, hours_worked: float = 0.0) -> str:
        return (
            f"Salary {money(self.period_salary())} + {self.bonus_rate:.0%} bonus "
            f"+ {self.team_size} reports x {money(self.report_stipend)}"
        )


class Executive(SalariedEmployee):
    """Salaried executive with a performance award each period."""

    role = "Executive"

    def __init__(
        self,
        employee_id: str,
        name: str,
        title: str,
        hired: date,
        annual_salary: MoneyLike,
        performance_rate: MoneyLike = Decimal("0.25"),
    ) -> None:
        super().__init__(employee_id, name, title, hired, annual_salary)
        self.performance_rate = as_decimal(performance_rate, "performance rate")
        if self.performance_rate > 2:
            raise ValueError("performance rate must be between 0 and 2")

    def performance_award(self) -> Decimal:
        return q(self.period_salary() * self.performance_rate)

    def calculate_pay(self, hours_worked: float = 0.0) -> Decimal:
        self.check_hours(hours_worked)
        return q(self.period_salary() + self.performance_award())

    def pay_note(self, hours_worked: float = 0.0) -> str:
        return (
            f"Salary {money(self.period_salary())} + "
            f"{self.performance_rate:.0%} performance award"
        )


@dataclass(frozen=True)
class PayLine:
    """One row of a payroll run."""

    employee_id: str
    name: str
    role: str
    gross: Decimal
    detail: str


@dataclass(frozen=True)
class Termination:
    """Record of an employee leaving the company."""

    employee_id: str
    name: str
    on: date
    severance: Decimal


class Company:
    """Roster and payroll operations for one company."""

    def __init__(self, name: str) -> None:
        if not name.strip():
            raise ValueError("company name must not be empty")
        self.name = name.strip()
        self._employees: dict[str, Employee] = {}
        self.terminations: list[Termination] = []

    def __len__(self) -> int:
        return len(self.employees)

    @property
    def employees(self) -> tuple[Employee, ...]:
        """Active employees in hire order."""
        return tuple(e for e in self._employees.values() if e.active)

    @property
    def everyone(self) -> tuple[Employee, ...]:
        """Active and former employees."""
        return tuple(self._employees.values())

    def get(self, employee_id: str) -> Employee:
        key = employee_id.strip().upper()
        try:
            return self._employees[key]
        except KeyError:
            raise CompanyError(f"unknown employee: {key}") from None

    def hire(self, employee: Employee) -> Employee:
        if employee.employee_id in self._employees:
            raise CompanyError(f"employee id {employee.employee_id} already exists")
        if not employee.active:
            raise CompanyError("cannot hire an inactive employee record")
        self._employees[employee.employee_id] = employee
        return employee

    def fire(self, employee_id: str, on: date | None = None, weeks: int = 2) -> Termination:
        """Terminate an employee and record severance."""
        employee = self.get(employee_id)
        if not employee.active:
            raise CompanyError(f"{employee.employee_id} is not active")
        effective = on or date.today()
        if effective < employee.hired:
            raise CompanyError("termination date cannot precede hire date")
        employee.active = False
        employee.terminated_on = effective
        termination = Termination(
            employee.employee_id, employee.name, effective, employee.severance(weeks)
        )
        self.terminations.append(termination)
        return termination

    def give_raise(
        self, employee_id: str, percent: Decimal, effective: date | None = None
    ) -> Employee:
        employee = self.get(employee_id)
        if not employee.active:
            raise CompanyError(f"{employee.employee_id} is not active")
        employee.give_raise(percent, effective)
        return employee

    def payroll(self, hours: dict[str, float] | None = None) -> list[PayLine]:
        """Compute one biweekly payroll run for all active employees."""
        hours = hours or {}
        normalized = {key.upper(): value for key, value in hours.items()}
        unknown = set(normalized) - {e.employee_id for e in self.employees}
        if unknown:
            raise CompanyError(f"hours given for unknown employee(s): {', '.join(sorted(unknown))}")
        lines: list[PayLine] = []
        for employee in self.employees:
            worked = normalized.get(employee.employee_id, 0.0)
            lines.append(
                PayLine(
                    employee.employee_id,
                    employee.name,
                    employee.role,
                    employee.calculate_pay(worked),
                    employee.pay_note(worked),
                )
            )
        return lines

    def total_payroll(self, hours: dict[str, float] | None = None) -> Decimal:
        return q(sum((line.gross for line in self.payroll(hours)), Decimal("0")))

    def headcount_by_role(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for employee in self.employees:
            counts[employee.role] = counts.get(employee.role, 0) + 1
        return counts

    def annual_cost_estimate(self) -> Decimal:
        return q(sum((e.annual_cost_estimate() for e in self.employees), Decimal("0")))

    def roster_report(self) -> str:
        header = f"{'ID':<7} {'NAME':<16} {'ROLE':<10} {'TITLE':<22} {'BASE/YR':>12} HIRED"
        lines = [header, "-" * len(header)]
        for employee in self.employees:
            lines.append(
                f"{employee.employee_id:<7} {employee.name:<16} {employee.role:<10} "
                f"{employee.title:<22} {money(employee.annual_base):>12} {employee.hired}"
            )
        if not self.employees:
            lines.append("(no active employees)")
        return "\n".join(lines)

    def payroll_report(self, hours: dict[str, float] | None = None) -> str:
        lines = self.payroll(hours)
        header = f"{'ID':<7} {'NAME':<16} {'ROLE':<10} {'GROSS':>11}  DETAIL"
        out = [header, "-" * (len(header) + 30)]
        for line in lines:
            out.append(
                f"{line.employee_id:<7} {line.name:<16} {line.role:<10} "
                f"{money(line.gross):>11}  {line.detail}"
            )
        out.append("-" * (len(header) + 30))
        out.append(f"{'TOTAL':<46} {money(sum((l.gross for l in lines), Decimal('0'))):>11}")
        return "\n".join(out)

    def termination_report(self) -> str:
        if not self.terminations:
            return "(no terminations)"
        return "\n".join(
            f"{t.employee_id:<7} {t.name:<16} left {t.on}  severance {money(t.severance)}"
            for t in self.terminations
        )


def build_sample_company() -> Company:
    """Create the deterministic demo roster."""
    company = Company("Northwind Robotics")
    company.hire(
        HourlyEmployee(
            "E-001", "Alice Chen", "Assembly Technician", date(2024, 3, 11), "24.50"
        )
    )
    company.hire(
        SalariedEmployee(
            "E-002", "Ben Ortiz", "Software Engineer", date(2023, 8, 1), "96000"
        )
    )
    company.hire(
        Manager(
            "E-003", "Carla Ruiz", "Engineering Manager", date(2022, 1, 17),
            "132000", team_size=4, bonus_rate="0.10", report_stipend="50",
        )
    )
    company.hire(
        Executive(
            "E-004", "Dev Patel", "VP Operations", date(2021, 5, 3),
            "210000", performance_rate="0.25",
        )
    )
    company.hire(
        HourlyEmployee("E-005", "Emma Novak", "QC Inspector", date(2025, 2, 24), "28.00")
    )
    return company


def run_demo() -> int:
    """Hire, pay, raise, fire and report using only the public API."""
    company = build_sample_company()
    print(f"== {company.name} - Company Manager Demo ==")
    print(f"Active employees: {len(company)}\n")
    print(company.roster_report())

    hours = {"E-001": 90.0, "E-002": 80.0, "E-003": 80.0, "E-004": 80.0, "E-005": 76.0}
    print("\n-- Payroll run (biweekly) --")
    print(company.payroll_report(hours))
    print(f"\nProjected annual payroll cost: {money(company.annual_cost_estimate())}")

    print("\n-- Raises --")
    for employee_id, percent in (("E-001", "5"), ("E-003", "8")):
        employee = company.give_raise(employee_id, Decimal(percent), date(2026, 7, 1))
        print(f"  {employee.employee_id} {employee.name}: +{percent}% "
              f"-> {money(employee.annual_base)} base/year")

    print("\n-- Termination --")
    termination = company.fire("E-005", date(2026, 6, 30), weeks=2)
    print(f"  {termination.employee_id} {termination.name} left {termination.on}; "
          f"severance {money(termination.severance)}")
    print(f"  Active employees now: {len(company)}")

    print("\n-- Next payroll run (E-001 at 96 h, E-005 removed) --")
    hours_next = {"E-001": 96.0, "E-002": 80.0, "E-003": 80.0, "E-004": 80.0}
    print(company.payroll_report(hours_next))

    counts = company.headcount_by_role()
    print("\n-- Headcount --")
    print("  " + ", ".join(f"{role}: {count}" for role, count in sorted(counts.items())))
    print("\n-- Termination history --")
    print(company.termination_report())

    print("\n-- Validation --")
    for label, action in (
        ("unknown employee", lambda: company.get("E-999")),
        ("duplicate id", lambda: company.hire(
            HourlyEmployee("E-001", "Copy Cat", "Temp", date(2026, 1, 1), "20"))),
        ("invalid raise", lambda: company.give_raise("E-002", Decimal("0"))),
        ("fire twice", lambda: company.fire("E-005")),
    ):
        try:
            action()
            print(f"  {label:<16} -> unexpectedly succeeded")
        except (CompanyError, ValueError) as exc:
            print(f"  {label:<16} -> {exc}")
    return 0


def prompt_date(message: str, default: date) -> date:
    raw = input(f"{message} [{default.isoformat()}]: ").strip()
    return date.fromisoformat(raw) if raw else default


def interactive(company_name: str) -> int:
    """Menu-driven company administration console."""
    company = Company(company_name)
    menu = (
        "\n1) Roster          2) Hire hourly     3) Hire salaried\n"
        "4) Hire manager    5) Hire executive  6) Give raise\n"
        "7) Fire            8) Run payroll     9) Quit"
    )
    while True:
        print(menu)
        try:
            choice = input("Choice: ").strip()
        except EOFError:
            print()
            return 0
        try:
            if choice == "1":
                print(company.roster_report())
            elif choice in {"2", "3", "4", "5"}:
                employee_id = input("Employee id: ").strip()
                name = input("Name: ").strip()
                title = input("Title: ").strip()
                hired = prompt_date("Hire date", date.today())
                if choice == "2":
                    employee = HourlyEmployee(
                        employee_id, name, title, hired,
                        Decimal(input("Hourly rate: ").strip()),
                    )
                elif choice == "3":
                    employee = SalariedEmployee(
                        employee_id, name, title, hired,
                        Decimal(input("Annual salary: ").strip()),
                    )
                elif choice == "4":
                    employee = Manager(
                        employee_id, name, title, hired,
                        Decimal(input("Annual salary: ").strip()),
                        team_size=int(input("Direct reports [0]: ").strip() or "0"),
                    )
                else:
                    employee = Executive(
                        employee_id, name, title, hired,
                        Decimal(input("Annual salary: ").strip()),
                    )
                company.hire(employee)
                print(f"Hired {employee.employee_id} {employee.name} as {employee.role}.")
            elif choice == "6":
                percent = Decimal(input("Raise percent: ").strip())
                employee = company.give_raise(input("Employee id: ").strip(), percent)
                print(f"{employee.name} now earns {money(employee.annual_base)}/year.")
            elif choice == "7":
                termination = company.fire(
                    input("Employee id: ").strip(),
                    prompt_date("Termination date", date.today()),
                )
                print(f"Terminated {termination.name}; severance {money(termination.severance)}.")
            elif choice == "8":
                hours: dict[str, float] = {}
                for employee in company.employees:
                    if isinstance(employee, HourlyEmployee):
                        raw = input(f"Hours for {employee.name} [80]: ").strip() or "80"
                        hours[employee.employee_id] = float(raw)
                print(company.payroll_report(hours))
            elif choice == "9":
                print("Goodbye.")
                return 0
            else:
                print("Please choose 1-9.")
        except (CompanyError, ValueError, KeyError) as exc:
            print(f"Error: {exc}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Manage a company roster and run payroll across employee types.",
        epilog="Run without arguments for the interactive company console.",
    )
    parser.add_argument("--demo", action="store_true", help="run the scripted demo")
    parser.add_argument(
        "--company", default="Northwind Robotics", help="company name for interactive mode"
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.demo:
        return run_demo()
    try:
        return interactive(args.company)
    except KeyboardInterrupt:
        print("\nInterrupted.")
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
