# SQL Query Analyzer

> Category: `Databases` · Project: `SQL-Query-Analyzer`

## Problem

A utility application which a user can enter a query and have it run against a
local database and look for ways to make it more efficient.

## Features

- Runs read-only SQLite queries and prints the exact `EXPLAIN QUERY PLAN` tree.
- Measures wall-clock execution time (best of three runs in the demo) and the
  number of rows returned.
- Flags full table scans, temporary B-trees for `ORDER BY`, and temporary
  B-trees for `GROUP BY`.
- Inspects `WHERE` and `JOIN ... ON` predicates and the query's existing
  indexes, then emits ready-to-review `CREATE INDEX` statements.
- Suggests composite `(filter, sort)` indexes when a query filters on one
  column and orders by another.
- Never modifies your database: the CLI opens it with SQLite `mode=ro` and
  rejects anything that is not `SELECT`, `WITH`, or `EXPLAIN`.
- Text or JSON output; accepts a single statement or a multi-statement script.

## Requirements

Python 3.10+ (standard library only).

## Usage

```bash
python3 solution.py --demo
python3 solution.py --db shop.db --sql "SELECT * FROM orders WHERE customer_id = 7"
python3 solution.py --db shop.db --file report.sql
python3 solution.py --db shop.db --sql "SELECT ..." --json
```

- `--db` — SQLite database file to inspect (opened read-only).
- `--sql` — SQL statement or script to analyze.
- `--file` — read the SQL from a file.
- `--json` — machine-readable report.
- `--demo` — build a temporary sample database and compare query plans before
  and after applying the suggested indexes.

## Example Output

```
SQL Query Analyzer — demo
Sample database: 400 customers, 4,000 orders, 12,000 order items

[Filter + sort (composite index)]
SQL: SELECT id, order_date, status FROM orders WHERE status = 'paid' ORDER BY order_date DESC LIMIT 5
Query plan:
  SCAN orders
  USE TEMP B-TREE FOR ORDER BY
Timing: 0.17 ms | Rows returned: 5
Findings:
  [HIGH  ] full table scan on 'orders' (no index used)
  [MEDIUM] temporary B-tree used to satisfy ORDER BY
Suggested indexes:
  CREATE INDEX IF NOT EXISTS idx_orders_status_order_date ON orders(status, order_date);

Applied 4 suggested index(es). Re-running...

[Filter + sort (composite index)] 0.17 ms -> 0.01 ms (20.5x)
  Plan: SEARCH orders USING COVERING INDEX idx_orders_status_order_date (status=?)
  Findings: no obvious plan problems detected
```

## Implementation Notes

The analyzer executes `EXPLAIN QUERY PLAN <query>`, then parses the detail
strings: `SCAN <table>` without a `USING ... INDEX` clause is a full scan, and
`USE TEMP B-TREE FOR ...` reveals sort/group work. Table aliases are resolved
from the `FROM`/`JOIN` clauses so plan lines that name an alias are attributed
to the right table.

Candidate index columns come from equality/range predicates in `WHERE` and
from both sides of `JOIN ... ON` equalities. Columns already covered by the
leading position of an existing index and single-column `INTEGER PRIMARY KEY`
(rowid alias) columns are skipped. For a `WHERE status = ? ORDER BY date`
shape, a composite `(status, date)` index is suggested so one index serves both
the filter and the ordering.

Heuristics are intentionally conservative: SQLite may still prefer a scan for
small tables or low-selectivity columns, and write/DDL statements are rejected
rather than analyzed. The suggested DDL is printed, never applied automatically.
