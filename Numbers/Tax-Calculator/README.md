# Tax Calculator

**Category:** Numbers · **Project:** `Tax-Calculator`

## Problem

> Asks the user to enter a cost and either a country or state tax. It then returns the tax plus the total cost with tax.

## Features

- Built-in base rates for all 50 US states plus DC and 58 countries (VAT/GST/sales tax).
- Flexible region names: full names, two-letter codes, case changes and underscores
  (`california`, `CA`, `US-CA`, `uk`, `germany`). Ambiguous codes such as `DE`
  (Delaware or Germany) produce a clear error asking for the full name.
- `--rate` overrides the table for local/city rates.
- `--inclusive` treats the entered amount as tax-included and extracts net and tax.
- Exact decimal money arithmetic with `Decimal` and half-up rounding to cents.
- `--list` shows every jurisdiction and rate, optionally filtered by `--kind`.
- Interactive prompts when `--amount` or `--region` is omitted.

## Requirements

Python 3.10 or newer. Standard library only — no packages to install.

## Usage

```bash
python3 solution.py --demo
python3 solution.py --amount 100 --region california
python3 solution.py --amount 250 --region UK
python3 solution.py --amount 99.99 --region germany --inclusive
python3 solution.py --amount 80 --region "new york" --rate 8.875
python3 solution.py --list --kind country
```

- `-a/--amount COST` — net cost; accepts `$`, `€`, `£`, commas and underscores.
- `-r/--region REGION` — US state or country name/code.
- `--rate PERCENT` — override the jurisdiction's rate (e.g. `8.875`).
- `--inclusive` — split a tax-inclusive amount into net + tax instead of adding tax.
- `--list [--kind state|country]` — print supported jurisdictions and rates.
- `--demo` — run five representative calculations.

## Example Output

```text
Tax Calculator demo
====================================================
Region:    California (state)
Rate:      7.25%
Net:       100.00
Tax:       7.25
Total:     107.25

Region:    Texas (state)
Rate:      6.25%
Net:       249.99
Tax:       15.62
Total:     265.61

Region:    United Kingdom (country)
Rate:      20%
Net:       250.00
Tax:       50.00
Total:     300.00

Region:    Germany (country)
Rate:      19%
Net:       84.03
Tax:       15.96
Total:     99.99
(amount treated as tax-inclusive)

Region:    New York (state)
Rate:      8.875%
Net:       80.00
Tax:       7.10
Total:     87.10

109 jurisdictions available (51 state-level, 58 countries).
```

## Implementation Notes

Money is handled with `decimal.Decimal` rather than binary floats, and every
result is quantised to cents with `ROUND_HALF_UP`. For inclusive amounts the net
is computed as `gross / (1 + rate)` and the tax as the remainder, so net + tax
always equals the entered gross (to the cent).

The table holds **base** rates: US state-level sales taxes exclude county and city
add-ons, and some countries apply reduced rates to specific goods. Rates and rules
change; use `--rate` for the exact figure you need. This is an educational
calculator, not tax advice.
