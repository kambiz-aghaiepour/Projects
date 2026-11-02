# Mortgage Calculator

**Category:** Numbers · **Project:** `Mortgage-Calculator`

## Problem

Calculate the monthly payments of a fixed term mortgage over given Nth terms at a given interest rate. Also figure out how long it will take the user to pay back the loan. For added complexity, add an option for users to select the compounding interval (Monthly, Weekly, Daily, Continually).

## Features

- Level monthly payment from principal, nominal annual rate and term.
- Compounding selectable as monthly, weekly, daily or continuous.
- Amortization simulation reports the true payoff time and total interest.
- Optional extra monthly principal, with months and interest saved.
- `--schedule` prints a year-by-year interest/principal/balance table.
- Exact `Decimal` math with cent-level rounding at each payment.

## Requirements

Python 3.10+ and the standard library only.

## Usage

```bash
python3 solution.py --demo
python3 solution.py --principal 300000 --rate 6.5 --years 30
python3 solution.py --principal 250000 --rate 5.25 --years 15 --compounding weekly
python3 solution.py --principal 300000 --rate 6.5 --years 30 --extra 200 --schedule
```

- `--principal` — loan amount.
- `--rate` — nominal annual interest rate in percent.
- `--years` — term in years (default 30).
- `--compounding` — `monthly`, `weekly`, `daily` or `continuously`.
- `--extra` — additional principal paid every month.
- `--schedule` — print the annual amortization summary.
- `--demo` — run the comparison scenarios.

## Example Output

```text
Baseline: $300,000 at 6.5% for 30 years
  Principal:          $300,000.00
  Annual rate:        6.5% (monthly compounding)
  Scheduled term:     30 years (360 months)
  Monthly payment:    $1,896.20
  Payoff time:        30 yr 0 mo (360 payments)
  Total interest:     $382,636.71
  Total paid:         $682,636.71

Compounding comparison: $250,000 at 5.25% over 15 years
  Interval        Monthly payment   Total interest
  monthly         $     2,009.69   $  111,745.41
  weekly          $     2,010.86   $  111,953.95
  daily           $     2,011.16   $  112,007.81
  continuously    $     2,011.21   $  112,016.89

With $200 extra principal each month
  Payoff time:        23 yr 1 mo (277 payments)
  Total interest:     $279,186.52
  Interest saved:     $103,450.19
  Months saved:       83
```

## Implementation Notes

The reusable math lives in `mortgage_math.py`. The nominal annual rate is
converted to an effective monthly rate. Monthly compounding uses `r/12`;
weekly and daily use `(1 + r/m)^(m/12) − 1`; continuous uses `exp(r/12) − 1`. The payment comes from
the standard annuity formula

`M = P · i · (1+i)^n / ((1+i)^n − 1)`

with `i` the monthly rate and `n` the number of months. The simulation applies
interest to the outstanding balance each month, rounds to cents, and lets the
contractual final payment absorb the residual, so a 30-year loan reports 360
payments rather than a spurious 361st.

The calculator assumes a fixed rate for the entire term, no fees, insurance or
taxes, and that extra principal is paid every month until payoff. A 100-year
simulation guard prevents infinite loops on pathological inputs.
