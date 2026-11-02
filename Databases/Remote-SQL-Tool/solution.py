#!/usr/bin/env python3
"""Remote SQL Tool: run SQL against local SQLite files or remote databases.

Connections are described by named profiles stored in a JSON file.  SQLite is
always available through the standard library; PostgreSQL and MySQL work when
their optional drivers (``psycopg``/``psycopg2`` and ``PyMySQL``) are
installed.  Queries are read-only by default and bound by a wall-clock timeout.
"""

from __future__ import annotations

import argparse
import csv
import getpass
import importlib.util
import io
import json
import os
import re
import sqlite3
import sys
import tempfile
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

DRIVERS = ("sqlite", "postgresql", "mysql")
DEFAULT_PORTS = {"postgresql": 5432, "mysql": 3306}
READ_ONLY_FIRST = re.compile(r"^\s*(?:SELECT|WITH|EXPLAIN)\b", re.IGNORECASE)
WRITE_KEYWORDS = re.compile(
    r"\b(INSERT|UPDATE|DELETE|REPLACE|DROP|ALTER|CREATE|TRUNCATE|ATTACH|DETACH|"
    r"VACUUM|REINDEX|PRAGMA|GRANT|REVOKE|MERGE|CALL|EXEC|EXECUTE)\b",
    re.IGNORECASE,
)
STRING_OR_COMMENT = re.compile(
    r"'(?:[^']|'')*'|\"(?:[^\"]|\"\")*\"|--[^\n]*|/\*.*?\*/",
    re.DOTALL,
)


class QueryError(RuntimeError):
    """A user-facing connection or query failure."""


@dataclass
class Profile:
    """A saved connection profile; secrets are referenced by env var name."""

    name: str
    driver: str
    database: str = ""
    host: str = ""
    port: int = 0
    user: str = ""
    password_env: str = ""

    def validate(self) -> None:
        if self.driver not in DRIVERS:
            raise QueryError(f"unsupported driver '{self.driver}' (choose from {', '.join(DRIVERS)})")
        if self.driver == "sqlite":
            if not self.database:
                raise QueryError("sqlite profiles need --database PATH")
        elif not self.database:
            raise QueryError(f"{self.driver} profiles need --database NAME")
        if self.driver != "sqlite" and not self.host:
            raise QueryError(f"{self.driver} profiles need --host")
        if self.port < 0:
            raise QueryError("port must be positive")
        if not self.port and self.driver in DEFAULT_PORTS:
            self.port = DEFAULT_PORTS[self.driver]


def default_profiles_path() -> Path:
    """Location of the profile store, overridable with REMOTE_SQL_PROFILES."""
    override = os.environ.get("REMOTE_SQL_PROFILES")
    if override:
        return Path(override).expanduser()
    return Path.home() / ".remote_sql_profiles.json"


def load_profiles(path: Path) -> dict[str, Profile]:
    """Load profiles, tolerating a missing file but not corrupt JSON."""
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise QueryError(f"cannot read profiles file {path}: {exc}") from exc
    raw = payload.get("profiles", {}) if isinstance(payload, dict) else {}
    profiles: dict[str, Profile] = {}
    for name, values in raw.items():
        if not isinstance(values, dict):
            continue
        values = {key: value for key, value in values.items()
                  if key in Profile.__dataclass_fields__ and key != "name"}
        profiles[name] = Profile(name=name, **values)
    return profiles


def save_profiles(path: Path, profiles: dict[str, Profile]) -> None:
    """Persist profiles atomically with owner-only permissions where possible."""
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"profiles": {name: asdict(profile) for name, profile in profiles.items()}}
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)
    try:
        path.chmod(0o600)
    except OSError:
        pass


def driver_available(driver: str) -> tuple[bool, str]:
    """Return availability and a human-readable hint for optional drivers."""
    if driver == "sqlite":
        return True, "built in"
    if driver == "postgresql":
        for module in ("psycopg", "psycopg2"):
            if importlib.util.find_spec(module):
                return True, module
        return False, "install with: pip install 'psycopg[binary]'"
    if driver == "mysql":
        if importlib.util.find_spec("pymysql"):
            return True, "pymysql"
        return False, "install with: pip install PyMySQL"
    return False, "unknown driver"


def read_password(profile: Profile) -> str | None:
    """Read a password from the configured environment variable or prompt."""
    if not profile.password_env:
        return None
    value = os.environ.get(profile.password_env)
    if value is not None:
        return value
    if sys.stdin.isatty():
        return getpass.getpass(f"Password for {profile.user}@{profile.host}: ")
    raise QueryError(f"environment variable {profile.password_env} is not set")


def connect(profile: Profile, timeout: float) -> tuple[Any, str]:
    """Open a DB-API connection and return it with its driver name."""
    profile.validate()
    if profile.driver == "sqlite":
        path = Path(profile.database).expanduser()
        if not path.exists():
            raise QueryError(f"SQLite database not found: {path}")
        connection = sqlite3.connect(str(path), timeout=timeout)
        deadline = time.monotonic() + timeout

        def cancel_if_slow() -> int:
            return 1 if time.monotonic() > deadline else 0

        connection.set_progress_handler(cancel_if_slow, 1000)
        return connection, "sqlite"

    available, detail = driver_available(profile.driver)
    if not available:
        raise QueryError(f"{profile.driver} driver not installed ({detail})")
    password = read_password(profile)
    if profile.driver == "postgresql":
        if importlib.util.find_spec("psycopg"):
            import psycopg  # type: ignore

            connection = psycopg.connect(
                host=profile.host, port=profile.port, user=profile.user,
                password=password, dbname=profile.database,
                connect_timeout=max(1, int(timeout)),
            )
            connection.execute(f"SET statement_timeout = {int(timeout * 1000)}")
            return connection, "psycopg"
        import psycopg2  # type: ignore

        connection = psycopg2.connect(
            host=profile.host, port=profile.port, user=profile.user,
            password=password, dbname=profile.database,
            connect_timeout=max(1, int(timeout)),
            options=f"-c statement_timeout={int(timeout * 1000)}",
        )
        return connection, "psycopg2"

    import pymysql  # type: ignore

    connection = pymysql.connect(
        host=profile.host, port=profile.port, user=profile.user,
        password=password or "", database=profile.database,
        connect_timeout=max(1, int(timeout)), read_timeout=max(1, int(timeout)),
        write_timeout=max(1, int(timeout)),
    )
    with connection.cursor() as cursor:
        cursor.execute(f"SET SESSION MAX_EXECUTION_TIME={int(timeout * 1000)}")
    return connection, "pymysql"


def clean_sql(sql: str) -> str:
    """Strip string literals and comments so keyword checks are meaningful."""
    return STRING_OR_COMMENT.sub(" ", sql).strip()


def ensure_read_only(sql: str) -> None:
    """Reject statements that could change data or schema."""
    cleaned = clean_sql(sql)
    if WRITE_KEYWORDS.search(cleaned):
        raise QueryError("read-only mode blocked a data-changing keyword; use --allow-write to override")
    if not READ_ONLY_FIRST.match(cleaned):
        raise QueryError("read-only mode accepts SELECT, WITH, and EXPLAIN statements only")
    without_trailing = cleaned.rstrip().rstrip(";")
    if ";" in without_trailing:
        raise QueryError("submit one statement at a time")


def ensure_single_statement(sql: str) -> None:
    """Allow at most one statement, ignoring a single trailing semicolon."""
    if ";" in clean_sql(sql).rstrip().rstrip(";"):
        raise QueryError("submit one statement at a time")


def execute(profile: Profile, sql: str, *, allow_write: bool = False,
            timeout: float = 10.0, max_rows: int = 100) -> tuple[list[str], list[tuple], bool, float]:
    """Execute *sql* and return columns, rows, truncation flag, and duration."""
    if not allow_write:
        ensure_read_only(sql)
    else:
        ensure_single_statement(sql)
    if max_rows < 1:
        raise QueryError("--max-rows must be at least 1")

    connection, driver = connect(profile, timeout)
    started = time.perf_counter()
    try:
        cursor = connection.cursor()
        cursor.execute(sql)
        if cursor.description is None:
            connection.commit()
            return [], [], False, (time.perf_counter() - started) * 1000
        columns = [str(item[0]) for item in cursor.description]
        rows = cursor.fetchmany(max_rows + 1)
        truncated = len(rows) > max_rows
        rows = rows[:max_rows]
        connection.commit()
        return columns, [tuple(row) for row in rows], truncated, (time.perf_counter() - started) * 1000
    except Exception as exc:  # drivers raise different exception hierarchies
        message = str(exc).strip() or exc.__class__.__name__
        if "interrupted" in message.lower() or "timeout" in message.lower() or "canceling" in message.lower():
            raise QueryError(f"query timed out after {timeout:g}s") from exc
        raise QueryError(f"query failed: {message}") from exc
    finally:
        try:
            connection.close()
        except Exception:
            pass


def cell(value: Any, width: int = 36) -> str:
    """Render a value for a fixed-width table cell."""
    if value is None:
        text = "NULL"
    elif isinstance(value, bytes):
        text = f"<{len(value)} bytes>"
    else:
        text = str(value).replace("\n", " ")
    return text if len(text) <= width else text[: width - 1] + "…"


def format_table(columns: list[str], rows: list[tuple], truncated: bool, elapsed_ms: float) -> str:
    """Render rows as an aligned text table."""
    if not columns:
        return f"Statement executed in {elapsed_ms:.1f} ms (no result set)."
    text_rows = [[cell(value) for value in row] for row in rows]
    widths = [len(column) for column in columns]
    for row in text_rows:
        widths = [max(width, len(value)) for width, value in zip(widths, row)]
    line = "+" + "+".join("-" * (width + 2) for width in widths) + "+"
    output = [line, "| " + " | ".join(column.ljust(width) for column, width in zip(columns, widths)) + " |", line]
    for row in text_rows:
        output.append("| " + " | ".join(value.ljust(width) for value, width in zip(row, widths)) + " |")
    if not text_rows:
        output.append("| " + " | ".join("(no rows)".ljust(width) for width in widths) + " |")
    output.append(line)
    suffix = f"{len(rows)} row(s)"
    if truncated:
        suffix += " (truncated; raise --max-rows for more)"
    output.append(f"{suffix} in {elapsed_ms:.1f} ms")
    return "\n".join(output)


def format_json(columns: list[str], rows: list[tuple], truncated: bool, elapsed_ms: float) -> str:
    """Render rows as a JSON object with metadata."""
    payload = {
        "columns": columns,
        "rows": [dict(zip(columns, row)) for row in rows],
        "row_count": len(rows),
        "truncated": truncated,
        "elapsed_ms": round(elapsed_ms, 3),
    }
    return json.dumps(payload, indent=2, default=str)


def format_csv(columns: list[str], rows: list[tuple]) -> str:
    """Render rows as CSV without any decorative output."""
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(columns)
    writer.writerows(rows)
    return buffer.getvalue().rstrip("\n")


def format_result(kind: str, columns: list[str], rows: list[tuple],
                  truncated: bool, elapsed_ms: float) -> str:
    if kind == "json":
        return format_json(columns, rows, truncated, elapsed_ms)
    if kind == "csv":
        return format_csv(columns, rows)
    return format_table(columns, rows, truncated, elapsed_ms)


def profile_from_args(args: argparse.Namespace) -> Profile:
    return Profile(
        name=args.add_profile,
        driver=args.driver,
        database=args.database or "",
        host=args.host or "",
        port=int(args.port or 0),
        user=args.user or "",
        password_env=args.password_env or "",
    )


def interactive(path: Path) -> int:
    """Small REPL: pick a profile, run read-only queries, :q to quit."""
    try:
        profiles = load_profiles(path)
    except QueryError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    if not profiles:
        print("No profiles yet. Add one with --add-profile NAME --driver sqlite --database FILE")
        return 1
    print("Profiles: " + ", ".join(sorted(profiles)))
    name = input("Profile: ").strip()
    if name not in profiles:
        print(f"error: unknown profile '{name}'", file=sys.stderr)
        return 2
    while True:
        try:
            sql = input("sql> ").strip()
        except EOFError:
            print()
            return 0
        if sql.lower() in {":q", "quit", "exit"}:
            return 0
        if not sql:
            continue
        try:
            columns, rows, truncated, elapsed = execute(profiles[name], sql)
            print(format_result("table", columns, rows, truncated, elapsed))
        except QueryError as exc:
            print(f"error: {exc}", file=sys.stderr)


def seed_demo_db(path: Path) -> None:
    """Create a small deterministic sales database for the demo."""
    with sqlite3.connect(path) as connection:
        connection.executescript(
            """
            CREATE TABLE customers (id INTEGER PRIMARY KEY, name TEXT, city TEXT);
            CREATE TABLE orders (id INTEGER PRIMARY KEY, customer_id INTEGER,
                                 order_date TEXT, total REAL, status TEXT);
            """
        )
        connection.executemany(
            "INSERT INTO customers VALUES (?, ?, ?)",
            [(1, "Ada Lovelace", "London"), (2, "Grace Hopper", "New York"),
             (3, "Alan Turing", "Manchester"), (4, "Edsger Dijkstra", "Rotterdam"),
             (5, "Barbara Liskov", "Boston")],
        )
        connection.executemany(
            "INSERT INTO orders VALUES (?, ?, ?, ?, ?)",
            [
                (1, 1, "2026-01-05", 120.50, "paid"),
                (2, 1, "2026-02-11", 89.99, "paid"),
                (3, 2, "2026-02-14", 240.00, "paid"),
                (4, 3, "2026-03-02", 15.75, "refunded"),
                (5, 4, "2026-03-18", 310.25, "paid"),
                (6, 5, "2026-04-01", 75.00, "pending"),
            ],
        )


def run_demo() -> int:
    """Exercise profiles, formats, the read-only guard, and query timeouts."""
    print("Remote SQL Tool — demo")
    with tempfile.TemporaryDirectory(prefix="remote-sql-") as tmp:
        db_path = Path(tmp) / "demo.db"
        profiles_path = Path(tmp) / "profiles.json"
        seed_demo_db(db_path)

        profiles = load_profiles(profiles_path)
        profiles["demo"] = Profile(name="demo", driver="sqlite", database=str(db_path))
        profiles["warehouse"] = Profile(
            name="warehouse", driver="postgresql", database="analytics",
            host="db.example.test", port=5432, user="analyst",
            password_env="PGPASSWORD",
        )
        save_profiles(profiles_path, profiles)
        print(f"Saved {len(profiles)} profiles to a temp file\n")

        print("Profiles:")
        for name, profile in sorted(load_profiles(profiles_path).items()):
            status, detail = driver_available(profile.driver)
            target = Path(profile.database).name if profile.driver == "sqlite" else profile.host
            print(f"  {name:10} {profile.driver:10} {target}"
                  f"  [{'ready' if status else 'driver missing: ' + detail}]")

        sql = """
            SELECT c.name, COUNT(o.id) AS orders, ROUND(SUM(o.total), 2) AS revenue
            FROM customers c JOIN orders o ON o.customer_id = c.id
            WHERE o.status = 'paid'
            GROUP BY c.id ORDER BY revenue DESC
        """
        columns, rows, truncated, elapsed = execute(profiles["demo"], sql, max_rows=10)
        print("\n--- table format ---")
        print(format_result("table", columns, rows, truncated, elapsed))
        print("\n--- json format (first 2 rows) ---")
        print(format_result("json", columns, rows[:2], False, elapsed))
        print("\n--- csv format ---")
        print(format_result("csv", columns, rows, False, elapsed))

        print("\n--- read-only guard ---")
        try:
            execute(profiles["demo"], "DELETE FROM orders WHERE id = 1")
        except QueryError as exc:
            print(f"blocked as expected: {exc}")

        print("\n--- timeout guard ---")
        slow = ("WITH RECURSIVE cnt(x) AS (SELECT 1 UNION ALL "
                "SELECT x + 1 FROM cnt WHERE x < 50000000) SELECT COUNT(*) FROM cnt")
        try:
            execute(profiles["demo"], slow, timeout=0.05)
        except QueryError as exc:
            print(f"stopped as expected: {exc}")

        print("\nDemo complete. Real use: python3 solution.py --profile demo --sql 'SELECT ...'")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="solution.py",
        description="Execute SQL against SQLite, PostgreSQL, or MySQL using saved profiles.",
    )
    parser.add_argument("--profiles", type=Path, default=default_profiles_path(),
                        help="profile store JSON (default: ~/.remote_sql_profiles.json)")
    parser.add_argument("--list-profiles", action="store_true", help="list saved profiles")
    parser.add_argument("--add-profile", metavar="NAME", help="create or update a profile")
    parser.add_argument("--remove-profile", metavar="NAME", help="delete a profile")
    parser.add_argument("--driver", choices=DRIVERS, default="sqlite", help="profile driver")
    parser.add_argument("--database", help="SQLite file path or remote database name")
    parser.add_argument("--host", help="remote host")
    parser.add_argument("--port", type=int, help="remote port")
    parser.add_argument("--user", help="remote user name")
    parser.add_argument("--password-env", help="environment variable holding the password")
    parser.add_argument("--profile", help="profile to query with")
    parser.add_argument("--sql", help="SQL statement to execute")
    parser.add_argument("--file", type=Path, help="read SQL from a file")
    parser.add_argument("--format", choices=("table", "json", "csv"), default="table")
    parser.add_argument("--allow-write", action="store_true", help="permit one data-changing statement")
    parser.add_argument("--timeout", type=float, default=10.0, help="query timeout in seconds")
    parser.add_argument("--max-rows", type=int, default=100, help="maximum rows to fetch")
    parser.add_argument("--demo", action="store_true", help="run the scripted demo")
    args = parser.parse_args(argv)

    if args.demo:
        return run_demo()
    try:
        profiles = load_profiles(args.profiles)
    except QueryError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    if args.list_profiles:
        if not profiles:
            print("No profiles saved.")
        for name, profile in sorted(profiles.items()):
            status, detail = driver_available(profile.driver)
            print(f"{name}: {profile.driver} {profile.host or profile.database} "
                  f"[{'ready' if status else detail}]")
        return 0

    if args.add_profile:
        profile = profile_from_args(args)
        try:
            profile.validate()
        except QueryError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2
        profiles[profile.name] = profile
        save_profiles(args.profiles, profiles)
        print(f"Saved profile '{profile.name}' ({profile.driver}).")
        return 0

    if args.remove_profile:
        if args.remove_profile not in profiles:
            print(f"error: profile '{args.remove_profile}' not found", file=sys.stderr)
            return 2
        del profiles[args.remove_profile]
        save_profiles(args.profiles, profiles)
        print(f"Removed profile '{args.remove_profile}'.")
        return 0

    if not args.profile and not args.sql and not args.file:
        return interactive(args.profiles)

    if not args.profile:
        parser.error("--profile is required (or use --list-profiles / --demo)")
    profile = profiles.get(args.profile)
    if not profile:
        print(f"error: profile '{args.profile}' not found in {args.profiles}", file=sys.stderr)
        return 2
    sql = args.sql
    if args.file:
        try:
            sql = args.file.read_text(encoding="utf-8")
        except OSError as exc:
            print(f"error: cannot read {args.file}: {exc}", file=sys.stderr)
            return 2
    if not sql:
        parser.error("provide --sql or --file")
    try:
        columns, rows, truncated, elapsed = execute(
            profile, sql, allow_write=args.allow_write,
            timeout=args.timeout, max_rows=args.max_rows,
        )
    except QueryError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(format_result(args.format, columns, rows, truncated, elapsed))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("\ninterrupted", file=sys.stderr)
        raise SystemExit(130)
