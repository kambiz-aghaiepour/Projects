#!/usr/bin/env python3
"""SQL Query Analyzer: inspect SQLite query plans and suggest useful indexes.

Runs a read-only SQL statement against a SQLite database, reports the
``EXPLAIN QUERY PLAN`` tree, wall-clock timing, row count, and heuristics for
full table scans, temporary B-trees, and columns that would benefit from an
index.  Suggested ``CREATE INDEX`` statements are printed verbatim so they can
be reviewed and applied by hand.
"""

from __future__ import annotations

import argparse
import json
import random
import re
import sqlite3
import sys
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

READ_ONLY_START = re.compile(r"^\s*(?:SELECT|WITH|EXPLAIN)\b", re.IGNORECASE)
WRITE_KEYWORDS = re.compile(
    r"\b(INSERT|UPDATE|DELETE|REPLACE|DROP|ALTER|CREATE|TRUNCATE|ATTACH|DETACH|"
    r"VACUUM|REINDEX|PRAGMA)\b", re.IGNORECASE)
SQL_LITERALS = re.compile(r"'(?:[^']|'')*'|\"[^\"]*\"|--[^\n]*|/\*.*?\*/", re.DOTALL)
TABLE_RE = re.compile(
    r"\b(?:FROM|JOIN)\s+([A-Za-z_][\w$]*)(?:\s+(?:AS\s+)?([A-Za-z_][\w$]*))?",
    re.IGNORECASE,
)
ALIAS_STOP = {
    "WHERE", "GROUP", "ORDER", "LIMIT", "HAVING", "ON", "LEFT", "RIGHT",
    "INNER", "OUTER", "CROSS", "JOIN", "UNION", "USING", "NATURAL",
    "EXCEPT", "INTERSECT", "WINDOW", "OFFSET",
}
JOIN_EQ_RE = re.compile(r"\bON\s+([A-Za-z_][\w.]*)\s*=\s*([A-Za-z_][\w.]*)", re.I)
WHERE_CLAUSE_RE = re.compile(
    r"\bWHERE\b(.*?)(?:\bGROUP\s+BY\b|\bORDER\s+BY\b|\bLIMIT\b|\bHAVING\b|$)",
    re.I | re.S,
)
PREDICATE_RE = re.compile(r"([A-Za-z_][\w.]*)\s*(>=|<=|=|>|<|\bLIKE\b|\bIN\b)", re.I)
SCAN_RE = re.compile(r"\bSCAN\s+(?:TABLE\s+)?([A-Za-z_][\w$]*)", re.I)
SORT_RE = re.compile(r"\bUSE\s+TEMP\s+B-TREE\s+FOR\s+(ORDER BY|GROUP BY)", re.I)
SAFE_IDENT = re.compile(r"^[A-Za-z_]\w*$")


@dataclass
class Finding:
    """A single observation about a query plan."""

    severity: str
    message: str


@dataclass
class Report:
    """Analysis result for one SQL statement."""

    sql: str
    plan: list[str] = field(default_factory=list)
    elapsed_ms: float = 0.0
    rows: int = 0
    findings: list[Finding] = field(default_factory=list)
    suggestions: list[str] = field(default_factory=list)


def split_statements(script: str) -> list[str]:
    """Split a SQL script into complete statements using SQLite's parser."""
    statements: list[str] = []
    buffer = ""
    for line in script.splitlines(keepends=True):
        buffer += line
        if sqlite3.complete_statement(buffer):
            statement = buffer.strip()
            if statement:
                statements.append(statement)
            buffer = ""
    if buffer.strip():
        statements.append(buffer.strip())
    return statements


def table_aliases(sql: str) -> tuple[list[str], dict[str, str]]:
    """Return tables referenced in FROM/JOIN clauses and an alias map."""
    tables: list[str] = []
    aliases: dict[str, str] = {}
    for match in TABLE_RE.finditer(sql):
        table = match.group(1)
        alias = match.group(2)
        if table.upper() in ALIAS_STOP:
            continue
        if table not in tables:
            tables.append(table)
        aliases[table] = table
        if alias and alias.upper() not in ALIAS_STOP:
            aliases[alias] = table
    return tables, aliases


def resolve(ref: str, aliases: dict[str, str], tables: list[str]) -> str | None:
    """Resolve a possibly qualified column reference to a table name."""
    if "." in ref:
        prefix = ref.split(".", 1)[0]
        return aliases.get(prefix, prefix if prefix in tables else None)
    if len(tables) == 1:
        return tables[0]
    return None


def index_columns(conn: sqlite3.Connection, table: str) -> list[tuple[str, list[str]]]:
    """Return ``(index_name, columns)`` for every index on *table*."""
    if not SAFE_IDENT.match(table):
        return []
    result: list[tuple[str, list[str]]] = []
    try:
        indexes = conn.execute(f'PRAGMA index_list("{table}")').fetchall()
    except sqlite3.Error:
        return []
    for row in indexes:
        name = row[1]
        if not SAFE_IDENT.match(name):
            continue
        cols = [info[2] for info in conn.execute(f'PRAGMA index_info("{name}")')]
        result.append((name, cols))
    return result


def rowid_alias_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    """Columns that are already the rowid (a single INTEGER PRIMARY KEY)."""
    if not SAFE_IDENT.match(table):
        return set()
    try:
        info = conn.execute(f'PRAGMA table_info("{table}")').fetchall()
    except sqlite3.Error:
        return set()
    primary = [row for row in info if row[5]]
    if len(primary) == 1 and str(primary[0][2]).upper() == "INTEGER":
        return {str(primary[0][1]).lower()}
    return set()


def analyze(conn: sqlite3.Connection, sql: str, params: Iterable[object] = (),
            repeats: int = 1) -> Report:
    """Run *sql*, capturing its plan, timing, row count and heuristics."""
    statement = sql.strip().rstrip(";")
    if not READ_ONLY_START.match(statement):
        raise ValueError("only SELECT, WITH and EXPLAIN statements can be analyzed")
    if WRITE_KEYWORDS.search(SQL_LITERALS.sub(" ", statement)):
        raise ValueError("read-only analyzer: data-changing statements are not supported")

    report = Report(sql=statement)
    try:
        plan_rows = conn.execute("EXPLAIN QUERY PLAN " + statement, tuple(params)).fetchall()
    except sqlite3.Error as exc:
        raise ValueError(f"SQL error: {exc}") from exc
    report.plan = [str(row[-1]) for row in plan_rows]

    best = float("inf")
    rows: list[tuple] = []
    for _ in range(max(1, repeats)):
        started = time.perf_counter()
        rows = conn.execute(statement, tuple(params)).fetchall()
        best = min(best, (time.perf_counter() - started) * 1000.0)
    report.elapsed_ms = best
    report.rows = len(rows)

    tables, aliases = table_aliases(statement)
    existing = {table: index_columns(conn, table) for table in tables}
    rowid_columns = {table: rowid_alias_columns(conn, table) for table in tables}
    candidates: set[tuple[str, str]] = set()
    equality_predicates: dict[str, list[str]] = {}

    full_scans: set[str] = set()
    for detail in report.plan:
        match = SCAN_RE.search(detail)
        if match and "USING" not in detail.upper():
            name = match.group(1)
            scanned = aliases.get(name, name if name in tables else None)
            if scanned:
                full_scans.add(scanned)

    for table in sorted(full_scans):
        report.findings.append(
            Finding("HIGH", f"full table scan on '{table}' (no index used)")
        )

    def is_covered(table: str, columns: list[str]) -> bool:
        """True when an existing index starts with exactly *columns*."""
        wanted = [column.lower() for column in columns]
        return any([col.lower() for col in cols][:len(wanted)] == wanted
                   for _, cols in existing.get(table, []))

    def add_candidate(table: str | None, column: str, equality: bool = True) -> None:
        if not table or not SAFE_IDENT.match(column):
            return
        if column.lower() in rowid_columns.get(table, set()):
            return
        if equality:
            bucket = equality_predicates.setdefault(table, [])
            if column.lower() not in [item.lower() for item in bucket]:
                bucket.append(column)
        if not any(cols and cols[0].lower() == column.lower()
                   for _, cols in existing.get(table, [])):
            candidates.add((table, column))

    for left, right in JOIN_EQ_RE.findall(statement):
        for ref in (left, right):
            table = resolve(ref, aliases, tables)
            add_candidate(table, ref.split(".")[-1])

    where_match = WHERE_CLAUSE_RE.search(statement)
    if where_match:
        for ref, operator in PREDICATE_RE.findall(where_match.group(1)):
            if ref.lower() in {"and", "or", "not"}:
                continue
            table = resolve(ref, aliases, tables)
            add_candidate(table, ref.split(".")[-1], equality=(operator == "="))

    order_columns: list[tuple[str, str]] = []
    for detail in report.plan:
        sort_match = SORT_RE.search(detail)
        if sort_match and sort_match.group(1).upper() == "ORDER BY":
            report.findings.append(
                Finding("MEDIUM", "temporary B-tree used to satisfy ORDER BY")
            )
            order_match = re.search(r"\bORDER\s+BY\b(.*?)(?:\bLIMIT\b|$)", statement, re.I | re.S)
            if order_match:
                for term in order_match.group(1).split(","):
                    if "(" in term:
                        continue
                    ref = term.strip().split()[0] if term.strip() else ""
                    if not ref or ref.lower() in {"asc", "desc", "nulls", "collate"}:
                        continue
                    table = resolve(ref, aliases, tables)
                    if table and table in full_scans and SAFE_IDENT.match(ref.split(".")[-1]):
                        order_columns.append((table, ref.split(".")[-1]))
            break
        if sort_match and sort_match.group(1).upper() == "GROUP BY":
            report.findings.append(
                Finding("LOW", "temporary B-tree used for GROUP BY aggregation")
            )

    if not report.findings:
        report.findings.append(Finding("INFO", "no obvious plan problems detected"))

    composites: list[tuple[str, list[str]]] = []
    for table, order_column in order_columns:
        equality_columns = [column for column in equality_predicates.get(table, [])
                            if column.lower() != order_column.lower()]
        if equality_columns and not is_covered(table, equality_columns[:2] + [order_column]):
            composites.append((table, equality_columns[:2] + [order_column]))
            for column in equality_columns:
                candidates.discard((table, column))
            candidates.discard((table, order_column))
        elif not is_covered(table, [order_column]):
            candidates.add((table, order_column))

    for table, columns in composites:
        index_name = ("idx_" + table + "_" + "_".join(columns)).lower()
        report.suggestions.append(
            f"CREATE INDEX IF NOT EXISTS {index_name} ON {table}({', '.join(columns)});"
        )
    for (table, column) in sorted(candidates):
        index_name = f"idx_{table}_{column}".lower()
        report.suggestions.append(
            f"CREATE INDEX IF NOT EXISTS {index_name} ON {table}({column});"
        )
    return report


def render_text(report: Report) -> str:
    """Render an analysis report as human-readable text."""
    lines = [
        "=" * 72,
        "SQL: " + " ".join(report.sql.split()),
        "-" * 72,
        "Query plan:",
    ]
    lines.extend(f"  {detail}" for detail in report.plan) if report.plan else lines.append("  (empty)")
    lines.append(f"Timing: {report.elapsed_ms:.2f} ms | Rows returned: {report.rows}")
    lines.append("Findings:")
    for finding in report.findings:
        lines.append(f"  [{finding.severity:<6}] {finding.message}")
    lines.append("Suggested indexes:")
    if report.suggestions:
        lines.extend(f"  {suggestion}" for suggestion in report.suggestions)
    else:
        lines.append("  (none — existing indexes look adequate)")
    return "\n".join(lines)


def analyze_script(conn: sqlite3.Connection, script: str, as_json: bool) -> int:
    """Analyze every statement in *script*; return a process exit code."""
    statements = split_statements(script)
    if not statements:
        print("error: no SQL statement supplied", file=sys.stderr)
        return 2
    reports: list[Report] = []
    for statement in statements:
        try:
            reports.append(analyze(conn, statement))
        except ValueError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2
    if as_json:
        payload = [
            {
                "sql": report.sql,
                "plan": report.plan,
                "elapsed_ms": round(report.elapsed_ms, 3),
                "rows": report.rows,
                "findings": [finding.__dict__ for finding in report.findings],
                "suggestions": report.suggestions,
            }
            for report in reports
        ]
        print(json.dumps(payload, indent=2))
    else:
        for index, report in enumerate(reports):
            if index:
                print()
            print(render_text(report))
    return 0


SAMPLE_SCHEMA = """
CREATE TABLE customers (id INTEGER PRIMARY KEY, name TEXT NOT NULL, city TEXT);
CREATE TABLE products (id INTEGER PRIMARY KEY, name TEXT NOT NULL, category TEXT, unit_price REAL);
CREATE TABLE orders (id INTEGER PRIMARY KEY, customer_id INTEGER NOT NULL,
                     order_date TEXT NOT NULL, status TEXT NOT NULL);
CREATE TABLE order_items (id INTEGER PRIMARY KEY, order_id INTEGER NOT NULL,
                          product_id INTEGER NOT NULL, quantity INTEGER NOT NULL,
                          unit_price REAL NOT NULL);
"""

SAMPLE_QUERIES = [
    (
        "Point lookup",
        "SELECT product_id, quantity, unit_price FROM order_items WHERE order_id = 3999;",
    ),
    (
        "Filtered join",
        """
SELECT o.id, o.order_date, oi.quantity, oi.unit_price
FROM orders o
JOIN order_items oi ON oi.order_id = o.id
WHERE o.customer_id = 7 AND o.status = 'paid'
""",
    ),
    (
        "Filter + sort (composite index)",
        """
SELECT id, order_date, status FROM orders
WHERE status = 'paid'
ORDER BY order_date DESC
LIMIT 5
""",
    ),
]


def build_sample_db(path: Path) -> None:
    """Create and populate a reproducible sales database for the demo."""
    rng = random.Random(42)
    cities = ["Austin", "Berlin", "Lisbon", "Nairobi", "Osaka", "Toronto"]
    statuses = ["paid", "paid", "paid", "shipped", "cancelled"]
    with sqlite3.connect(path) as conn:
        conn.executescript(SAMPLE_SCHEMA)
        conn.executemany(
            "INSERT INTO customers(name, city) VALUES (?, ?)",
            [(f"Customer {i:03d}", cities[i % len(cities)]) for i in range(1, 401)],
        )
        conn.executemany(
            "INSERT INTO products(name, category, unit_price) VALUES (?, ?, ?)",
            [
                (f"Product {i:02d}", ["books", "electronics", "home", "outdoors"][i % 4],
                 round(5 + (i * 7.3) % 180, 2))
                for i in range(1, 41)
            ],
        )
        orders = []
        for order_id in range(1, 4001):
            day = rng.randint(0, 179)
            orders.append((order_id, rng.randint(1, 400), f"2026-01-{1 + day % 28:02d}",
                           rng.choice(statuses)))
        conn.executemany("INSERT INTO orders VALUES (?, ?, ?, ?)", orders)
        items = []
        for order_id in range(1, 4001):
            for _ in range(3):
                items.append((order_id, rng.randint(1, 40), rng.randint(1, 3),
                              round(rng.uniform(5, 200), 2)))
        conn.executemany(
            "INSERT INTO order_items(order_id, product_id, quantity, unit_price) VALUES (?, ?, ?, ?)",
            items,
        )


def run_demo() -> int:
    """Build a sample database and compare queries before and after indexing."""
    print("SQL Query Analyzer — demo")
    with tempfile.TemporaryDirectory(prefix="sql-analyzer-") as tmp:
        db_path = Path(tmp) / "sales.db"
        build_sample_db(db_path)
        print("Sample database: 400 customers, 4,000 orders, 12,000 order items\n")
        with sqlite3.connect(db_path) as conn:
            conn.execute("PRAGMA query_only=ON")
            before: list[Report] = []
            suggestions: list[str] = []
            print("--- Before indexes ---")
            for label, query in SAMPLE_QUERIES:
                report = analyze(conn, query, repeats=3)
                before.append(report)
                print(f"\n[{label}]")
                print(render_text(report))
                for suggestion in report.suggestions:
                    if suggestion not in suggestions:
                        suggestions.append(suggestion)

            conn.execute("PRAGMA query_only=OFF")
            created = 0
            for suggestion in suggestions:
                try:
                    conn.execute(suggestion)
                    created += 1
                except sqlite3.Error as exc:
                    print(f"  could not apply: {suggestion} ({exc})")
            conn.commit()
            print(f"\nApplied {created} suggested index(es). Re-running...\n")

            conn.execute("PRAGMA query_only=ON")
            print("--- After indexes ---")
            for (label, query), old in zip(SAMPLE_QUERIES, before):
                new = analyze(conn, query, repeats=3)
                speedup = old.elapsed_ms / new.elapsed_ms if new.elapsed_ms else 0.0
                print(f"\n[{label}] {old.elapsed_ms:.2f} ms -> {new.elapsed_ms:.2f} ms"
                      f" ({speedup:.1f}x)")
                print("  Plan: " + " | ".join(new.plan))
                print("  Findings: " + "; ".join(f.message for f in new.findings))
            print("\nDemo complete. For real use: python3 solution.py --db FILE --sql 'SELECT ...'")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="solution.py",
        description="Analyze SQLite queries: plan, timing, scans, temp B-trees, index hints.",
    )
    parser.add_argument("--db", type=Path, help="path to a SQLite database file")
    parser.add_argument("--sql", help="SQL statement (or script) to analyze")
    parser.add_argument("--file", type=Path, help="read SQL from a file instead of --sql")
    parser.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    parser.add_argument("--demo", action="store_true", help="run the scripted sample analysis")
    args = parser.parse_args(argv)

    if args.demo:
        return run_demo()
    if not args.db:
        parser.error("--db is required unless --demo is used")
    if not args.db.exists():
        print(f"error: database not found: {args.db}", file=sys.stderr)
        return 2
    script = args.sql
    if args.file:
        try:
            script = args.file.read_text(encoding="utf-8")
        except OSError as exc:
            print(f"error: cannot read {args.file}: {exc}", file=sys.stderr)
            return 2
    if not script:
        parser.error("provide --sql or --file (or use --demo)")
    try:
        connection = sqlite3.connect(f"file:{args.db}?mode=ro", uri=True)
    except sqlite3.Error as exc:
        print(f"error: cannot open database: {exc}", file=sys.stderr)
        return 2
    try:
        return analyze_script(connection, script, args.json)
    finally:
        connection.close()


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("\ninterrupted", file=sys.stderr)
        raise SystemExit(130)
