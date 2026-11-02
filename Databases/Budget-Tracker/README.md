# Budget Tracker

> Category: `Databases` · Project: `Budget-Tracker`

## Problem

Write an application that keeps track of a household's budget. The user can
add expenses, income, and recurring costs to find out how much they are saving
or losing over a period of time.

## Features

- Multiple accounts (checking, savings, credit, cash) with opening balances and
  computed current balances.
- Income and expense transactions with date, category, account, amount, and
  description. Amounts are stored as integer cents to avoid floating-point
  drift.
- Recurring cost schedules (weekly, monthly, yearly) with a next-due date and
  activation flag.
- Date-range reports: actual income/expenses, net cash flow, recurring
  commitments projected into the range, projected net, and savings rate.
- Category breakdown, monthly trend, recurring schedule detail, and account
  balances.
- CSV export and validated CSV import (all rows are checked before a single
  write, then the whole file is imported transactionally).
- Menu-driven interactive mode when run with no arguments.
- `--demo` seeds three accounts, three recurring costs, and three months of
  transactions in a temporary database, then does a CSV round-trip.

## Requirements

Python 3.10+ (standard library only).

## Usage

```bash
python3 solution.py --demo

python3 solution.py --db budget.db --add-account Checking --kind checking --opening 2500
python3 solution.py --db budget.db --add-txn --date 2026-01-01 --type income \
    --amount 4200 --category Salary --account Checking --description "January salary"
python3 solution.py --db budget.db --add-txn --date 2026-01-08 --type expense \
    --amount 143.50 --category Groceries --account Checking
python3 solution.py --db budget.db --add-recurring --description Rent --amount 1450 \
    --frequency monthly --next-due 2026-01-01 --category Rent --account Checking

python3 solution.py --db budget.db --report --from 2026-01-01 --to 2026-03-31
python3 solution.py --db budget.db --accounts
python3 solution.py --db budget.db --export-csv transactions.csv
python3 solution.py --db budget.db --import-csv transactions.csv
```

- `--db` — SQLite file (default `budget.db`, created on first use).
- `--add-account NAME` with `--kind` and `--opening` (dollars).
- `--add-txn` with `--date`, `--type income|expense`, `--amount`, `--category`,
  `--account`, `--description`. Missing accounts/categories are created.
- `--add-recurring` with `--description`, `--amount`, `--frequency`,
  `--next-due`, `--category`.
- `--stop-recurring ID` — deactivate a schedule.
- `--report` with `--from` / `--to` (defaults: first of the current month to
  today). `--no-recurring` excludes projections.
- `--export-csv` / `--import-csv` — the CSV columns are
  `date,type,account,category,description,amount`.
- `--demo` — scripted sample budget.

## Example Output

```
BUDGET REPORT  2026-01-01 to 2026-03-31
Income (actual):              $13,200.00
Expenses (actual):            $1,655.00
Net cash flow:                $11,545.00
Recurring commitments:        $4,665.00  (9 charge(s) in range)
Projected net after recurring: $6,880.00
Savings rate:                 52.1% of income

SPENDING BY CATEGORY
+---------+---------------+------------+-------+
| Type    | Category      |     Amount | Share |
+---------+---------------+------------+-------+
| Expense | Groceries     |    $840.00 | 50.8% |
| Expense | Utilities     |    $373.00 | 22.5% |
| Expense | Dining        |    $277.00 | 16.7% |
| Expense | Transport     |    $135.00 |  8.2% |
| Expense | Entertainment |     $30.00 |  1.8% |
| Income  | Salary        | $12,600.00 | 95.5% |
| Income  | Freelance     |    $600.00 |  4.5% |
+---------+---------------+------------+-------+

MONTHLY TREND
+---------+-----------+----------+-----------+
| Month   |    Income | Expenses |       Net |
+---------+-----------+----------+-----------+
| 2026-01 | $4,200.00 |  $494.50 | $3,705.50 |
| 2026-02 | $4,800.00 |  $570.50 | $4,229.50 |
| 2026-03 | $4,200.00 |  $590.00 | $3,610.00 |
+---------+-----------+----------+-----------+

RECURRING COST PROJECTION
+----------------+-----------+-----------+-----------+---------+-----------+
| Description    | Category  | Frequency |    Amount | Charges |     Total |
+----------------+-----------+-----------+-----------+---------+-----------+
| Rent           | Rent      | monthly   | $1,450.00 |       3 | $4,350.00 |
| Internet       | Utilities | monthly   |    $60.00 |       3 |   $180.00 |
| Gym membership | Health    | monthly   |    $45.00 |       3 |   $135.00 |
+----------------+-----------+-----------+-----------+---------+-----------+

Exported 21 transactions to CSV (1,303 bytes)
Imported 21 transactions into a fresh database
Round-trip totals match: True (income $13,200.00, expenses $1,655.00)
```

## Implementation Notes

Transactions and recurring schedules are separate concepts. Recurring rows are
**projections** used to estimate committed costs; they are not silently turned
into transactions, so account balances reflect money that actually moved. A
recurring schedule is expanded from its `next_due` date by weeks, months (with
end-of-month clamping), or years, and only occurrences inside the report range
are counted. If you also record the actual payment as a transaction, use
`--no-recurring` for that period (or deactivate the schedule) to avoid counting
it twice.

Savings rate is `(income - expenses - projected recurring) / income`. Account
balances are `opening + income - expenses` through the report end date. CSV
import validates shape, dates, types, and amounts for every row before writing,
then inserts in one transaction; importing the same file twice will duplicate
transactions. Amounts accept `$`, thousands separators, and up to two decimals.
