# Remote SQL Tool

> Category: `Databases` · Project: `Remote-SQL-Tool`

## Problem

A utility that can execute queries on remote servers from your local computer
across the Internet. It should take in a remote host, user name and password,
run the query and return the results.

## Features

- Named connection profiles stored in a JSON file, with `--add-profile`,
  `--list-profiles`, and `--remove-profile`.
- SQLite works out of the box (standard library); PostgreSQL and MySQL are
  supported when their optional drivers are installed, with a clear install
  hint when they are not.
- Result formats: aligned table, JSON, or clean CSV.
- Read-only guard by default: only `SELECT`, `WITH`, and `EXPLAIN` statements
  pass, and data-changing keywords are rejected. `--allow-write` permits a
  single modifying statement.
- Wall-clock query timeout for SQLite (progress handler), PostgreSQL
  (`statement_timeout`), and MySQL (`MAX_EXECUTION_TIME` + socket timeouts).
- Row limit with explicit truncation reporting, and a small interactive REPL
  when no query arguments are supplied.
- Passwords are never stored in the profile file: profiles name an environment
  variable (`--password-env`, e.g. `PGPASSWORD`), with an interactive prompt as
  a fallback.

## Requirements

Python 3.10+ for SQLite. Optional drivers:

```bash
pip install 'psycopg[binary]'   # PostgreSQL
pip install PyMySQL             # MySQL
```

## Usage

```bash
python3 solution.py --demo

python3 solution.py --profiles ~/.remote_sql_profiles.json \
    --add-profile shop --driver postgresql --host db.example.com \
    --port 5432 --database sales --user analyst --password-env PG_PASSWORD

python3 solution.py --profile shop --sql "SELECT * FROM orders LIMIT 10"
python3 solution.py --profile shop --file report.sql --format csv
python3 solution.py --profile shop --sql "UPDATE ..." --allow-write
```

- `--profiles` — path to the profile store (default
  `~/.remote_sql_profiles.json`, override with `REMOTE_SQL_PROFILES`).
- `--driver` — `sqlite`, `postgresql`, or `mysql`.
- `--database` — SQLite file path or remote database name.
- `--host`, `--port`, `--user`, `--password-env` — remote connection details.
- `--profile` — saved profile to use for a query.
- `--sql` / `--file` — statement to run (one statement at a time).
- `--format` — `table` (default), `json`, or `csv`.
- `--timeout` — seconds before the query is cancelled (default 10).
- `--max-rows` — rows fetched before truncation (default 100).
- `--allow-write` — disable the read-only guard for this invocation.
- `--demo` — run against a temporary SQLite database; no network or credentials.

## Example Output

```
Remote SQL Tool — demo
Saved 2 profiles to a temp file

Profiles:
  demo       sqlite     demo.db  [ready]
  warehouse  postgresql db.example.test  [driver missing: install with: pip install 'psycopg[binary]']

--- table format ---
+-----------------+--------+---------+
| name            | orders | revenue |
+-----------------+--------+---------+
| Edsger Dijkstra | 1      | 310.25  |
| Grace Hopper    | 1      | 240.0   |
| Ada Lovelace    | 2      | 210.49  |
+-----------------+--------+---------+
3 row(s) in 0.1 ms

--- csv format ---
name,orders,revenue
Edsger Dijkstra,1,310.25
Grace Hopper,1,240.0
Ada Lovelace,2,210.49

--- read-only guard ---
blocked as expected: read-only mode blocked a data-changing keyword; use --allow-write to override

--- timeout guard ---
stopped as expected: query timed out after 0.05s
```

## Implementation Notes

Profiles are a flat JSON document keyed by profile name; the file is written
atomically and chmod `0600` on POSIX. SQLite connections use a progress handler
that interrupts the statement once a monotonic deadline passes. PostgreSQL
sets `statement_timeout` per session; MySQL sets `MAX_EXECUTION_TIME` and
connection/read/write timeouts.

The read-only guard strips string literals and comments before looking for
keywords, then rejects multiple statements. This is a safety convenience, not a
security boundary: a determined user with `--allow-write` has the database
privileges of the configured account. Use a read-only database role for real
remote access.

Optional drivers are imported lazily, so the tool and its demo remain fully
functional offline and on a bare Python installation.
