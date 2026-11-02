# Company Manager

**Category:** Classes · **Project:** `Classes/Company-Manager`

## Problem

Create a hierarchy of classes: abstract class Employee and subclasses
HourlyEmployee, SalariedEmployee, Manager and Executive. Every one's pay is
calculated differently. Create a Company class that allows you to hire, fire
and raise employees.

## Features

- Abstract `Employee` with shared identity, hire date, raise history and
  severance calculation.
- Four concrete payroll rules:
  - `HourlyEmployee`: hourly rate, 1.5× overtime after 80 hours per biweekly
    period (two 40-hour weeks).
  - `SalariedEmployee`: annual salary paid in 26 equal biweekly periods.
  - `Manager`: salary + configurable bonus percentage + per-direct-report
    stipend.
  - `Executive`: salary + performance award percentage.
- `Company` supports hire, fire (with severance and termination record), raise,
  payroll runs with per-employee hours, headcount by role and projected annual
  cost.
- Roster, payroll, and termination reports; validation for duplicate ids,
  unknown employees, invalid raises and firing twice.

## Requirements

Python 3.10+ (standard library only).

## Usage

```bash
python3 solution.py --demo
python3 solution.py
python3 solution.py --company "Acme Corp"
```

- `--demo` runs a scripted hire → payroll → raise → fire → payroll sequence and
  exits 0.
- `--company NAME` names the company used in interactive mode.
- With no arguments the interactive menu lets you view the roster, hire each
  employee type, give raises, fire employees and run payroll (prompting for
  hours for hourly staff).

## Example Output

```
== Northwind Robotics - Company Manager Demo ==
Active employees: 5

ID      NAME             ROLE       TITLE                       BASE/YR HIRED
-----------------------------------------------------------------------------
E-001   Alice Chen       Hourly     Assembly Technician      $50,960.00 2024-03-11
E-002   Ben Ortiz        Salaried   Software Engineer        $96,000.00 2023-08-01
E-003   Carla Ruiz       Manager    Engineering Manager     $132,000.00 2022-01-17
E-004   Dev Patel        Executive  VP Operations           $210,000.00 2021-05-03
E-005   Emma Novak       Hourly     QC Inspector             $58,240.00 2025-02-24

-- Payroll run (biweekly) --
ID      NAME             ROLE             GROSS  DETAIL
-------------------------------------------------------------------------------------
E-001   Alice Chen       Hourly       $2,327.50  90 h at $24.50/h (+10 h OT at 1.5x)
E-002   Ben Ortiz        Salaried     $3,692.31  Biweekly salary (annual / 26)
E-003   Carla Ruiz       Manager      $5,784.61  Salary $5,076.92 + 10% bonus + 4 reports x $50.00
E-004   Dev Patel        Executive   $10,096.15  Salary $8,076.92 + 25% performance award
E-005   Emma Novak       Hourly       $2,128.00  76 h at $28.00/h
-------------------------------------------------------------------------------------
TOTAL                                           $24,028.57

Projected annual payroll cost: $618,099.82

-- Termination --
  E-005 Emma Novak left 2026-06-30; severance $2,240.00
  Active employees now: 4
```

## Implementation Notes

`Employee` is an ABC declaring `annual_base`, `calculate_pay`,
`regular_period_pay`, `_apply_raise` and `pay_note`. The base class implements
the common template: raises validate the percentage, delegate to the
subclass's `_apply_raise` and append to raise history; severance is two weeks
of regular period pay.

Pay is computed per biweekly period with `Decimal` and quantised to cents.
Hourly overtime is applied to hours above 80 in the period, which is equivalent
to two 40-hour weeks. Salaried pay is `annual / 26`; managers add a bonus on
period salary plus a flat stipend per report; executives add a performance
award. `annual_cost_estimate` projects 26 periods including normal bonuses.

`Company` stores all records in a dict keyed by employee id, retains terminated
employees for history, and filters to active staff for payroll and headcount.
Payroll is O(n) in headcount; every operation validates its inputs and raises
a domain error with a readable message.
