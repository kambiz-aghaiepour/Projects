#!/usr/bin/env python3
"""Report Generator: sales reports from an orders/order-items database.

Reads a SQLite sales schema (customers, products, orders, order_items) and
produces a report for a date range in plain text, CSV, or a standalone HTML
document.  The report includes revenue KPIs, category and product rankings,
top customers, a monthly trend, and recent orders.
"""

from __future__ import annotations

import argparse
import calendar
import csv
import html
import io
import random
import sqlite3
import sys
import tempfile
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Iterable, Sequence

RECOGNIZED_STATUSES = ("paid", "shipped")

SCHEMA = """
CREATE TABLE customers (
    id INTEGER PRIMARY KEY, name TEXT NOT NULL, email TEXT, city TEXT, country TEXT
);
CREATE TABLE products (
    id INTEGER PRIMARY KEY, name TEXT NOT NULL, category TEXT NOT NULL, unit_price REAL NOT NULL
);
CREATE TABLE orders (
    id INTEGER PRIMARY KEY, customer_id INTEGER NOT NULL,
    order_date TEXT NOT NULL, status TEXT NOT NULL
);
CREATE TABLE order_items (
    order_id INTEGER NOT NULL, product_id INTEGER NOT NULL,
    quantity INTEGER NOT NULL, unit_price REAL NOT NULL,
    PRIMARY KEY (order_id, product_id)
);
"""

REQUIRED_TABLES = {"customers", "products", "orders", "order_items"}


@dataclass
class Report:
    """All data needed to render a sales report."""

    start: date
    end: date
    orders: int
    revenue: float
    units: int
    customers: int
    avg_order: float
    status_counts: list[tuple[str, int]]
    categories: list[tuple[str, float, int]]
    products: list[tuple[str, str, float, int]]
    top_customers: list[tuple[str, str, float, int]]
    monthly: list[tuple[str, float, int]]
    recent: list[tuple[int, str, str, str, float]]


def create_sample_db(path: Path) -> None:
    """Create a deterministic sales database with six months of orders."""
    rng = random.Random(7)
    first_names = ["Ada", "Grace", "Alan", "Edsger", "Barbara", "Linus", "Margaret",
                   "Donald", "Frances", "Ken", "Radia", "Tim", "Anita", "Vint",
                   "Katherine", "Dennis", "Jean", "Bjarne", "Sophie", "Guido"]
    last_names = ["Lovelace", "Hopper", "Turing", "Dijkstra", "Liskov", "Torvalds",
                  "Hamilton", "Knuth", "Allen", "Thompson", "Perlman", "Berners-Lee",
                   "Borg", "Cerf", "Johnson", "Ritchie", "Sammet", "Stroustrup",
                   "Wilson", "Rossum"]
    cities = [("London", "UK"), ("New York", "USA"), ("Berlin", "Germany"),
              ("Toronto", "Canada"), ("Sydney", "Australia"), ("Tokyo", "Japan"),
              ("Lisbon", "Portugal"), ("Nairobi", "Kenya")]
    products = [
        ("The Pragmatic Programmer", "Books", 39.95), ("Designing Data-Intensive Applications", "Books", 49.99),
        ("Structure and Interpretation", "Books", 55.00), ("Refactoring", "Books", 42.50),
        ("Mechanical Keyboard", "Electronics", 129.00), ("Noise-Cancelling Headphones", "Electronics", 279.00),
        ("27-inch Monitor", "Electronics", 349.99), ("USB-C Hub", "Electronics", 69.95),
        ("Raspberry Pi Kit", "Electronics", 89.00), ("Desk Lamp", "Home", 34.50),
        ("Ergonomic Chair", "Home", 420.00), ("Standing Desk", "Home", 510.00),
        ("Espresso Grinder", "Home", 185.00), ("Ceramic Mug Set", "Home", 28.00),
        ("Trail Running Shoes", "Outdoors", 145.00), ("Camping Tent", "Outdoors", 230.00),
        ("Insulated Bottle", "Outdoors", 32.00), ("Headlamp", "Outdoors", 24.95),
        ("Yoga Mat", "Outdoors", 45.00), ("Daypack", "Outdoors", 78.00),
    ]
    statuses = ["paid"] * 7 + ["shipped"] * 2 + ["pending", "cancelled"]
    with sqlite3.connect(path) as conn:
        conn.executescript(SCHEMA)
        customers = []
        for index in range(1, 61):
            city, country = cities[index % len(cities)]
            first = first_names[(index - 1) % len(first_names)]
            last = last_names[((index - 1) // len(first_names) + index - 1) % len(last_names)]
            name = f"{first} {last}"
            customers.append((index, name, f"customer{index:02d}@example.com", city, country))
        conn.executemany("INSERT INTO customers VALUES (?, ?, ?, ?, ?)", customers)
        conn.executemany("INSERT INTO products(name, category, unit_price) VALUES (?, ?, ?)", products)
        price_by_product = {index: product[2] for index, product in enumerate(products, start=1)}

        orders = []
        items = []
        order_id = 0
        for month in range(1, 7):
            days_in_month = calendar.monthrange(2026, month)[1]
            for _ in range(rng.randint(38, 55)):
                order_id += 1
                day = rng.randint(1, days_in_month)
                status = rng.choice(statuses)
                orders.append((order_id, rng.randint(1, 60), f"2026-{month:02d}-{day:02d}", status))
                for product_id in rng.sample(range(1, len(products) + 1), rng.randint(1, 4)):
                    quantity = rng.randint(1, 3)
                    discount = rng.choice([1.0, 1.0, 1.0, 0.9, 0.85])
                    items.append((order_id, product_id, quantity,
                                  round(price_by_product[product_id] * discount, 2)))
        conn.executemany("INSERT INTO orders VALUES (?, ?, ?, ?)", orders)
        conn.executemany("INSERT INTO order_items VALUES (?, ?, ?, ?)", items)


def validate_schema(conn: sqlite3.Connection) -> None:
    """Raise a clear error when the expected sales tables are absent."""
    names = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    missing = sorted(REQUIRED_TABLES - names)
    if missing:
        raise ValueError(
            "database is missing required table(s): " + ", ".join(missing)
            + " (expected schema: customers, products, orders, order_items)"
        )


def date_bounds(conn: sqlite3.Connection) -> tuple[date, date]:
    """Return the earliest and latest order dates in the database."""
    row = conn.execute("SELECT MIN(order_date), MAX(order_date) FROM orders").fetchone()
    if not row or not row[0]:
        raise ValueError("the orders table is empty")
    return date.fromisoformat(row[0]), date.fromisoformat(row[1])


def parse_date(value: str, label: str) -> date:
    """Parse an ISO date with a friendly error message."""
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"{label} must be YYYY-MM-DD, got '{value}'") from exc


def month_keys(start: date, end: date) -> list[str]:
    """List YYYY-MM keys covering the inclusive range."""
    keys: list[str] = []
    year, month = start.year, start.month
    while (year, month) <= (end.year, end.month):
        keys.append(f"{year:04d}-{month:02d}")
        month += 1
        if month == 13:
            year, month = year + 1, 1
    return keys


def collect(conn: sqlite3.Connection, start: date, end: date) -> Report:
    """Run the aggregate queries for the inclusive date range."""
    params = (start.isoformat(), end.isoformat())
    marks = ",".join("?" for _ in RECOGNIZED_STATUSES)
    status_filter = f"o.status IN ({marks})"
    filter_params = (*params, *RECOGNIZED_STATUSES)

    summary = conn.execute(
        f"""
        SELECT COUNT(DISTINCT o.id), COALESCE(SUM(oi.quantity * oi.unit_price), 0),
               COALESCE(SUM(oi.quantity), 0), COUNT(DISTINCT o.customer_id)
        FROM orders o JOIN order_items oi ON oi.order_id = o.id
        WHERE o.order_date BETWEEN ? AND ? AND {status_filter}
        """,
        filter_params,
    ).fetchone()
    orders, revenue, units, customers = summary

    status_counts = conn.execute(
        "SELECT status, COUNT(*) FROM orders WHERE order_date BETWEEN ? AND ? "
        "GROUP BY status ORDER BY COUNT(*) DESC", params
    ).fetchall()

    categories = conn.execute(
        f"""
        SELECT p.category, ROUND(SUM(oi.quantity * oi.unit_price), 2), SUM(oi.quantity)
        FROM order_items oi
        JOIN orders o ON o.id = oi.order_id
        JOIN products p ON p.id = oi.product_id
        WHERE o.order_date BETWEEN ? AND ? AND {status_filter}
        GROUP BY p.category ORDER BY SUM(oi.quantity * oi.unit_price) DESC
        """,
        filter_params,
    ).fetchall()

    products = conn.execute(
        f"""
        SELECT p.name, p.category, ROUND(SUM(oi.quantity * oi.unit_price), 2), SUM(oi.quantity)
        FROM order_items oi
        JOIN orders o ON o.id = oi.order_id
        JOIN products p ON p.id = oi.product_id
        WHERE o.order_date BETWEEN ? AND ? AND {status_filter}
        GROUP BY p.id ORDER BY SUM(oi.quantity * oi.unit_price) DESC LIMIT 8
        """,
        filter_params,
    ).fetchall()

    top_customers = conn.execute(
        f"""
        SELECT c.name, c.city, ROUND(SUM(oi.quantity * oi.unit_price), 2), COUNT(DISTINCT o.id)
        FROM order_items oi
        JOIN orders o ON o.id = oi.order_id
        JOIN customers c ON c.id = o.customer_id
        WHERE o.order_date BETWEEN ? AND ? AND {status_filter}
        GROUP BY c.id ORDER BY SUM(oi.quantity * oi.unit_price) DESC LIMIT 8
        """,
        filter_params,
    ).fetchall()

    monthly_rows = conn.execute(
        f"""
        SELECT substr(o.order_date, 1, 7), ROUND(SUM(oi.quantity * oi.unit_price), 2),
               COUNT(DISTINCT o.id)
        FROM orders o JOIN order_items oi ON oi.order_id = o.id
        WHERE o.order_date BETWEEN ? AND ? AND {status_filter}
        GROUP BY substr(o.order_date, 1, 7) ORDER BY 1
        """,
        filter_params,
    ).fetchall()
    monthly_map = {row[0]: (row[1], row[2]) for row in monthly_rows}
    monthly = [(key, *monthly_map.get(key, (0.0, 0))) for key in month_keys(start, end)]

    recent = conn.execute(
        f"""
        SELECT o.id, o.order_date, c.name, o.status,
               ROUND(SUM(oi.quantity * oi.unit_price), 2)
        FROM orders o
        JOIN order_items oi ON oi.order_id = o.id
        JOIN customers c ON c.id = o.customer_id
        WHERE o.order_date BETWEEN ? AND ?
        GROUP BY o.id ORDER BY o.order_date DESC, o.id DESC LIMIT 8
        """,
        params,
    ).fetchall()

    return Report(
        start=start, end=end, orders=int(orders), revenue=float(revenue), units=int(units),
        customers=int(customers), avg_order=(float(revenue) / orders) if orders else 0.0,
        status_counts=[(str(row[0]), int(row[1])) for row in status_counts],
        categories=[(str(row[0]), float(row[1]), int(row[2])) for row in categories],
        products=[(str(row[0]), str(row[1]), float(row[2]), int(row[3])) for row in products],
        top_customers=[(str(row[0]), str(row[1]), float(row[2]), int(row[3])) for row in top_customers],
        monthly=[(str(row[0]), float(row[1]), int(row[2])) for row in monthly],
        recent=[(int(row[0]), str(row[1]), str(row[2]), str(row[3]), float(row[4])) for row in recent],
    )


def money(value: float) -> str:
    return f"${value:,.2f}"


def text_table(headers: Sequence[str], rows: Iterable[Sequence[object]],
               right_align: Iterable[int] = ()) -> str:
    """Build a simple aligned text table."""
    right = set(right_align)
    body = [[str(value) for value in row] for row in rows]
    widths = [len(header) for header in headers]
    for row in body:
        widths = [max(width, len(value)) for width, value in zip(widths, row)]
    line = "+" + "+".join("-" * (width + 2) for width in widths) + "+"

    def format_row(values: Sequence[str]) -> str:
        cells = []
        for index, (value, width) in enumerate(zip(values, widths)):
            cells.append(value.rjust(width) if index in right else value.ljust(width))
        return "| " + " | ".join(cells) + " |"

    output = [line, format_row(list(headers)), line]
    output.extend(format_row(row) for row in body)
    output.append(line)
    return "\n".join(output)


def render_text(report: Report) -> str:
    """Render the report as plain text."""
    lines = [
        "=" * 78,
        "SALES REPORT".center(78),
        f"{report.start.isoformat()} to {report.end.isoformat()}".center(78),
        "=" * 78,
        "",
        f"Revenue:          {money(report.revenue)}",
        f"Orders:           {report.orders:,}",
        f"Units sold:       {report.units:,}",
        f"Active customers: {report.customers:,}",
        f"Average order:    {money(report.avg_order)}",
        "Status counts:    " + ", ".join(f"{name}={count}" for name, count in report.status_counts),
        "",
        "REVENUE BY CATEGORY",
    ]
    total = report.revenue or 1.0
    category_rows = [
        (name, money(revenue), f"{revenue / total * 100:.1f}%", f"{units:,}")
        for name, revenue, units in report.categories
    ]
    lines.append(text_table(["Category", "Revenue", "Share", "Units"], category_rows, (1, 2, 3)))
    lines.append("\nTOP PRODUCTS")
    lines.append(text_table(
        ["Product", "Category", "Revenue", "Units"],
        [(name, category, money(revenue), f"{units:,}")
         for name, category, revenue, units in report.products], (2, 3),
    ))
    lines.append("\nTOP CUSTOMERS")
    lines.append(text_table(
        ["Customer", "City", "Revenue", "Orders"],
        [(name, city, money(revenue), str(orders))
         for name, city, revenue, orders in report.top_customers], (2, 3),
    ))
    lines.append("\nMONTHLY REVENUE")
    peak = max((revenue for _, revenue, _ in report.monthly), default=0.0) or 1.0
    for month, revenue, orders in report.monthly:
        bar = "#" * max(1 if revenue else 0, round(revenue / peak * 32))
        lines.append(f"  {month}  {money(revenue):>12}  {orders:>3} orders  {bar}")
    lines.append("\nRECENT ORDERS")
    lines.append(text_table(
        ["Order", "Date", "Customer", "Status", "Total"],
        [(f"#{order_id}", order_date, customer, status, money(total))
         for order_id, order_date, customer, status, total in report.recent], (0, 4),
    ))
    return "\n".join(lines)


def html_table(headers: Sequence[str], rows: Iterable[Sequence[object]],
               numeric: Iterable[int] = ()) -> str:
    """Build an escaped HTML table."""
    numeric_set = set(numeric)
    head = "".join(f"<th>{html.escape(str(header))}</th>" for header in headers)
    body = []
    for row in rows:
        cells = "".join(
            f'<td class="{"num" if index in numeric_set else ""}">{html.escape(str(value))}</td>'
            for index, value in enumerate(row)
        )
        body.append(f"<tr>{cells}</tr>")
    return f'<table><thead><tr>{head}</tr></thead><tbody>{"".join(body)}</tbody></table>'


def render_html(report: Report) -> str:
    """Render a standalone, styled HTML report."""
    total = report.revenue or 1.0
    peak = max((revenue for _, revenue, _ in report.monthly), default=0.0) or 1.0
    category_bars = "".join(
        f'<div class="bar-row"><span>{html.escape(name)}</span>'
        f'<div class="track"><div class="fill" style="width:{revenue / total * 100:.1f}%"></div></div>'
        f'<span class="num">{money(revenue)}</span></div>'
        for name, revenue, _ in report.categories
    )
    months = "".join(
        f'<div class="month"><div class="month-bar" style="height:{max(2, revenue / peak * 100):.1f}%"></div>'
        f'<div class="month-label">{month[5:]}<br><small>{money(revenue)}</small></div></div>'
        for month, revenue, _ in report.monthly
    )
    statuses = " · ".join(f"{html.escape(name)}: {count}" for name, count in report.status_counts)
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Sales Report {report.start.isoformat()} – {report.end.isoformat()}</title>
<style>
  :root {{ --ink:#1f2937; --muted:#6b7280; --accent:#2563eb; --line:#e5e7eb; }}
  * {{ box-sizing: border-box; }}
  body {{ margin:0; padding:32px; font:15px/1.5 system-ui, -apple-system, Segoe UI, sans-serif;
         color:var(--ink); background:#f9fafb; }}
  main {{ max-width: 980px; margin:0 auto; background:#fff; padding:40px;
          border:1px solid var(--line); border-radius:10px; }}
  h1 {{ font-size:30px; margin:0 0 4px; }} .period {{ color:var(--muted); margin-bottom:28px; }}
  .kpis {{ display:grid; grid-template-columns:repeat(5, 1fr); gap:12px; margin-bottom:32px; }}
  .kpi {{ background:#f3f4f6; padding:14px; border-radius:8px; }}
  .kpi strong {{ display:block; font-size:20px; }} .kpi span {{ color:var(--muted); font-size:12px; text-transform:uppercase; letter-spacing:.05em; }}
  h2 {{ font-size:18px; margin:32px 0 10px; border-bottom:1px solid var(--line); padding-bottom:6px; }}
  table {{ width:100%; border-collapse:collapse; font-size:14px; }}
  th, td {{ text-align:left; padding:8px 10px; border-bottom:1px solid var(--line); }}
  th {{ color:var(--muted); font-weight:600; }} td.num, th.num {{ text-align:right; font-variant-numeric:tabular-nums; }}
  .bar-row {{ display:grid; grid-template-columns:150px 1fr 110px; gap:12px; align-items:center; margin:8px 0; }}
  .track {{ background:#eef2ff; height:14px; border-radius:7px; overflow:hidden; }}
  .fill {{ background:var(--accent); height:100%; }}
  .chart {{ display:flex; align-items:flex-end; gap:14px; height:180px; padding-top:16px; }}
  .month {{ flex:1; display:flex; flex-direction:column; justify-content:flex-end; height:100%; text-align:center; }}
  .month-bar {{ background:linear-gradient(#60a5fa,#2563eb); border-radius:4px 4px 0 0; min-height:2px; }}
  .month-label {{ font-size:12px; color:var(--muted); margin-top:6px; }}
  .status {{ color:var(--muted); font-size:13px; margin-top:6px; }}
  footer {{ color:var(--muted); font-size:12px; margin-top:36px; }}
</style>
</head>
<body><main>
  <h1>Sales Report</h1>
  <div class="period">{report.start.isoformat()} to {report.end.isoformat()}</div>
  <section class="kpis">
    <div class="kpi"><strong>{money(report.revenue)}</strong><span>Revenue</span></div>
    <div class="kpi"><strong>{report.orders:,}</strong><span>Orders</span></div>
    <div class="kpi"><strong>{report.units:,}</strong><span>Units</span></div>
    <div class="kpi"><strong>{report.customers:,}</strong><span>Customers</span></div>
    <div class="kpi"><strong>{money(report.avg_order)}</strong><span>Avg order</span></div>
  </section>
  <div class="status">Orders by status: {statuses}</div>
  <h2>Revenue by category</h2>
  {category_bars}
  <h2>Top products</h2>
  {html_table(["Product", "Category", "Revenue", "Units"],
              [(name, category, money(revenue), units) for name, category, revenue, units in report.products],
              (2, 3))}
  <h2>Top customers</h2>
  {html_table(["Customer", "City", "Revenue", "Orders"],
              [(name, city, money(revenue), orders) for name, city, revenue, orders in report.top_customers],
              (2, 3))}
  <h2>Monthly revenue</h2>
  <div class="chart">{months}</div>
  <h2>Recent orders</h2>
  {html_table(["Order", "Date", "Customer", "Status", "Total"],
              [(f"#{order_id}", order_date, customer, status, money(total))
               for order_id, order_date, customer, status, total in report.recent], (0, 4))}
  <footer>Generated by Report Generator · recognized statuses: {", ".join(RECOGNIZED_STATUSES)}</footer>
</main></body></html>
"""


def render_csv(conn: sqlite3.Connection, start: date, end: date) -> str:
    """Render every line item in the range as CSV."""
    rows = conn.execute(
        """
        SELECT o.id, o.order_date, o.status, c.name, c.city, c.country,
               p.name, p.category, oi.quantity, oi.unit_price,
               ROUND(oi.quantity * oi.unit_price, 2)
        FROM order_items oi
        JOIN orders o ON o.id = oi.order_id
        JOIN customers c ON c.id = o.customer_id
        JOIN products p ON p.id = oi.product_id
        WHERE o.order_date BETWEEN ? AND ?
        ORDER BY o.order_date, o.id, p.name
        """,
        (start.isoformat(), end.isoformat()),
    ).fetchall()
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(["order_id", "order_date", "status", "customer", "city", "country",
                     "product", "category", "quantity", "unit_price", "line_revenue"])
    writer.writerows(rows)
    return buffer.getvalue().rstrip("\n")


def run_demo() -> int:
    """Create sample data, print a text report, and write CSV and HTML copies."""
    print("Report Generator — demo")
    with tempfile.TemporaryDirectory(prefix="report-generator-") as tmp:
        db_path = Path(tmp) / "sales.db"
        create_sample_db(db_path)
        print("Created sample sales database (60 customers, 20 products, 6 months of orders)\n")
        with sqlite3.connect(db_path) as conn:
            validate_schema(conn)
            start, end = date_bounds(conn)
            report = collect(conn, start, end)
            print(render_text(report))

            csv_text = render_csv(conn, start, end)
            html_text = render_html(report)
            (Path(tmp) / "sales.csv").write_text(csv_text + "\n", encoding="utf-8")
            (Path(tmp) / "sales.html").write_text(html_text, encoding="utf-8")
            csv_rows = max(0, len(csv_text.splitlines()) - 1)
            print(f"\nCSV: {csv_rows:,} line items, {len(csv_text):,} bytes")
            print("  " + csv_text.splitlines()[0])
            print("  " + csv_text.splitlines()[1])
            print(f"HTML: {len(html_text):,} bytes, standalone document: "
                  f"{html_text.lstrip().lower().startswith('<!doctype html>')}")

            q2 = collect(conn, date(2026, 4, 1), date(2026, 6, 30))
            print(f"\nQ2 slice: {money(q2.revenue)} revenue across {q2.orders} orders "
                  f"({q2.start} to {q2.end})")
        print("\nDemo complete. Real use: python3 solution.py --db sales.db --from 2026-01-01 --to 2026-06-30")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="solution.py",
        description="Generate a sales report (text, CSV, or HTML) from a SQLite database.",
    )
    parser.add_argument("--db", type=Path, help="SQLite database with the sales schema")
    parser.add_argument("--from", dest="start", metavar="YYYY-MM-DD", help="inclusive start date")
    parser.add_argument("--to", dest="end", metavar="YYYY-MM-DD", help="inclusive end date")
    parser.add_argument("--format", choices=("text", "csv", "html"), default="text")
    parser.add_argument("--out", type=Path, help="write the report to this file instead of stdout")
    parser.add_argument("--demo", action="store_true", help="run the scripted sample report")
    args = parser.parse_args(argv)

    if args.demo:
        return run_demo()
    if not args.db:
        parser.error("--db is required unless --demo is used")
    if not args.db.exists():
        print(f"error: database not found: {args.db}", file=sys.stderr)
        return 2
    try:
        conn = sqlite3.connect(f"file:{args.db}?mode=ro", uri=True)
    except sqlite3.Error as exc:
        print(f"error: cannot open database: {exc}", file=sys.stderr)
        return 2
    try:
        validate_schema(conn)
        default_start, default_end = date_bounds(conn)
        start = parse_date(args.start, "--from") if args.start else default_start
        end = parse_date(args.end, "--to") if args.end else default_end
        if start > end:
            raise ValueError("--from must be on or before --to")
        if args.format == "csv":
            output = render_csv(conn, start, end)
        else:
            report = collect(conn, start, end)
            output = render_text(report) if args.format == "text" else render_html(report)
    except (ValueError, sqlite3.Error) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    finally:
        conn.close()

    if args.out:
        try:
            args.out.write_text(output + ("\n" if not output.endswith("\n") else ""), encoding="utf-8")
        except OSError as exc:
            print(f"error: cannot write {args.out}: {exc}", file=sys.stderr)
            return 2
        print(f"Wrote {args.format} report to {args.out}")
    else:
        print(output)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("\ninterrupted", file=sys.stderr)
        raise SystemExit(130)
