# Report Generator

> Category: `Databases` · Project: `Report-Generator`

## Problem

Create a utility that generates a report based on some tables in a database.
Generate sales reports based on the order/order details tables or sum up the
day's current database activity.

## Features

- Works with a small, documented sales schema: `customers`, `products`,
  `orders`, and `order_items`.
- Inclusive `--from` / `--to` date filtering; defaults to the full range found
  in the database.
- Revenue KPIs: revenue, order count, units, active customers, average order
  value, and order counts by status.
- Revenue by category with share, top products, top customers, a monthly
  revenue trend with bars, and recent orders.
- Three output formats: aligned plain text, tidy line-item CSV, and a
  standalone styled HTML document.
- `--out` writes any format to a file; `--demo` builds a deterministic
  six-month sample database in a temporary directory.

## Requirements

Python 3.10+ (standard library only).

## Usage

```bash
python3 solution.py --demo
python3 solution.py --db sales.db
python3 solution.py --db sales.db --from 2026-04-01 --to 2026-06-30
python3 solution.py --db sales.db --from 2026-01-01 --to 2026-06-30 --format html --out report.html
python3 solution.py --db sales.db --format csv --out line-items.csv
```

- `--db` — SQLite database containing the sales schema.
- `--from`, `--to` — inclusive ISO dates (`YYYY-MM-DD`).
- `--format` — `text` (default), `csv`, or `html`.
- `--out` — output file; without it the report goes to stdout.
- `--demo` — create sample data and generate text, CSV, and HTML reports in a
  temporary workspace.

### Expected schema

```sql
customers(id, name, email, city, country)
products(id, name, category, unit_price)
orders(id, customer_id, order_date, status)
order_items(order_id, product_id, quantity, unit_price)
```

Revenue counts only orders with status `paid` or `shipped`; status totals still
show every order so cancelled/pending volume is visible. CSV export contains
all line items in the range, with the status column intact.

## Example Output

```
SALES REPORT
2026-01-01 to 2026-06-30
Revenue:          $136,571.74
Orders:           216
Units sold:       1,029
Active customers: 59
Average order:    $632.28
Status counts:    paid=168, shipped=48, cancelled=27, pending=24

REVENUE BY CATEGORY
+-------------+------------+-------+-------+
| Category    |    Revenue | Share | Units |
+-------------+------------+-------+-------+
| Home        | $58,929.88 | 43.1% |   274 |
| Electronics | $45,866.03 | 33.6% |   259 |
| Outdoors    | $22,644.65 | 16.6% |   289 |
| Books       |  $9,131.18 |  6.7% |   207 |
+-------------+------------+-------+-------+

MONTHLY REVENUE
  2026-01    $20,153.59   38 orders  ######################
  2026-02    $11,910.30   29 orders  #############
  2026-03    $29,678.22   36 orders  ################################
  ...
CSV: 650 line items, 57,399 bytes
HTML: 7,862 bytes, standalone document: True
```

## Implementation Notes

All aggregates are computed in SQL with parameterized date bounds, so the tool
scales with the database rather than loading the whole table into Python. The
monthly series is gap-filled in Python so months with no orders still appear in
the chart. Money is formatted only at render time.

The HTML output is a single self-contained document with inline CSS, escaped
text, KPI cards, category bars, and a monthly chart built from divs — no
template engine or external assets. CSV uses Python's `csv` module with Unix
newlines.

Dates are ISO-8601 strings, which sort correctly with SQLite's `BETWEEN`.
`order_date` is treated as a date, not a timestamp; put the time in a separate
column if you need intra-day reporting. The demo data is generated with a fixed
seed and fixed 2026 dates, so its output is reproducible.
