# Change Return Program

**Category:** Numbers · **Project:** `Change-Return-Program`

## Problem

The user enters a cost and then the amount of money given. The program will figure out the change and the number of quarters, dimes, nickels, pennies needed for the change.

## Features

- Accepts decimal dollar amounts; converts to integer cents to avoid drift.
- Default breakdown is the classic quarter/dime/nickel/penny set.
- `--bills` adds $20, $10, $5 and $1 notes before the coins.
- Reports the change total and the value of every denomination row.
- Rejects negative amounts and payments that do not cover the cost.
- Interactive prompts when cost or payment is omitted.

## Requirements

Python 3.10+ and the standard library only.

## Usage

```bash
python3 solution.py --demo
python3 solution.py --cost 12.34 --paid 20.00
python3 solution.py --cost 12.34 --paid 20.00 --bills
```

- `--cost` — purchase price in dollars.
- `--paid` — amount handed over.
- `--bills` — include banknotes in the breakdown.
- `--demo` — show coin-only, bill-inclusive, exact-change and error cases.

## Example Output

```text
Coins only ($12.34 cost, $20.00 paid):
Cost:   $12.34
Paid:   $20.00
Change: $7.66
   30 x quarters   ($0.25 each) = $7.50
    1 x dime       ($0.10 each) = $0.10
    1 x nickel     ($0.05 each) = $0.05
    1 x penny      ($0.01 each) = $0.01

With bills ($12.34 cost, $20.00 paid):
Cost:   $12.34
Paid:   $20.00
Change: $7.66
    1 x $5 bill    ($5.00 each) = $5.00
    2 x $1 bill    ($1.00 each) = $2.00
    2 x quarters   ($0.25 each) = $0.50
    1 x dime       ($0.10 each) = $0.10
    1 x nickel     ($0.05 each) = $0.05
    1 x penny      ($0.01 each) = $0.01
```

## Implementation Notes

Cost and payment are parsed as `Decimal`, multiplied by 100 and rounded
half-up to integer cents. A greedy pass over descending denominations yields
the count for each. Greedy is optimal for US coin and note denominations
because each value is at least twice the next smaller one.

The coins-only default is intentional: the classic exercise asks only for
quarters, dimes, nickels and pennies, so a $7.66 change becomes 30 quarters
rather than a $5 note. Use `--bills` for a cashier-style breakdown. Exact
change prints a dedicated message rather than an empty table.
