#!/usr/bin/env python3
"""Sort CSV records by one or more typed fields (numeric, date or text).

Records are read with the :mod:`csv` module, column types are inferred from
the data (or forced per key), and rows are sorted with a stable multi-key
comparison so equal records keep their original order.  ``--in-place``
rewrites the input file after saving a backup.

Excel ``.xlsx`` files are intentionally out of scope for a standard-library
program: convert them to CSV first (see README).
"""

from __future__ import annotations

import argparse
import csv
import io
import shutil
import sys
import tempfile
from dataclasses import dataclass
from datetime import datetime
from functools import cmp_to_key
from pathlib import Path
from typing import Any

DATE_FORMATS = (
    "%Y-%m-%d",
    "%Y/%m/%d",
    "%Y-%m-%dT%H:%M:%S",
    "%d-%b-%Y",
    "%d %b %Y",
    "%b %d, %Y",
)


class SortError(Exception):
    """Raised for unreadable files, bad keys or invalid options."""


# --------------------------------------------------------------------------
# Value parsing and type inference
# --------------------------------------------------------------------------


def parse_date(raw: str) -> datetime | None:
    """Parse a handful of unambiguous date formats, or return None."""
    text = raw.strip()
    if not text:
        return None
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    return None


def looks_numeric(raw: str) -> bool:
    try:
        float(raw.replace(",", ""))
    except ValueError:
        return False
    return True


def infer_type(values: list[str]) -> str:
    """Infer a column type from its non-empty values.

    A column is numeric when every non-empty value parses as a number, date
    when every value parses as a date, and text otherwise.  All-empty columns
    are text.
    """
    present = [v.strip() for v in values if v.strip()]
    if not present:
        return "text"
    if all(looks_numeric(v) for v in present):
        return "numeric"
    if all(parse_date(v) is not None for v in present):
        return "date"
    return "text"


def convert(raw: str, kind: str) -> Any:
    """Convert a raw cell into a comparable value; None means missing."""
    text = raw.strip()
    if not text:
        return None
    if kind == "numeric":
        try:
            return float(text.replace(",", ""))
        except ValueError:
            return None
    if kind == "date":
        return parse_date(text)
    return text.casefold()


def compare_values(left: Any, right: Any) -> int:
    """Compare two non-None converted values, with text as a fallback."""
    if isinstance(left, str) and isinstance(right, str):
        return (left > right) - (left < right)
    try:
        return (left > right) - (left < right)
    except TypeError:
        ltext, rtext = str(left).casefold(), str(right).casefold()
        return (ltext > rtext) - (ltext < rtext)


# --------------------------------------------------------------------------
# Table loading / writing
# --------------------------------------------------------------------------


@dataclass
class Table:
    """A parsed CSV table with optional header row and inferred types."""

    header: list[str]
    rows: list[list[str]]
    delimiter: str = ","
    has_header: bool = True

    def column_index(self, name: str) -> int:
        folded = [h.casefold() for h in self.header]
        if name.casefold() in folded:
            return folded.index(name.casefold())
        if name.isdigit() and 0 <= int(name) < len(self.header):
            return int(name)
        raise SortError(
            f"unknown column {name!r}; available: {', '.join(self.header)}"
        )

    def types(self) -> dict[str, str]:
        return {
            name: infer_type([row[i] for row in self.rows])
            for i, name in enumerate(self.header)
        }


def detect_delimiter(sample: str) -> str:
    try:
        return csv.Sniffer().sniff(sample, delimiters=",;\t|").delimiter
    except csv.Error:
        return ","


def read_table(path: Path, delimiter: str | None, encoding: str) -> Table:
    if path.suffix.lower() == ".xlsx":
        raise SortError(
            "xlsx is not supported by the standard library; convert it first, "
            "e.g. libreoffice --headless --convert-to csv file.xlsx"
        )
    try:
        encoding_for_read = "utf-8-sig" if encoding.lower() in {"utf-8", "utf8"} else encoding
        text = path.read_text(encoding=encoding_for_read)
    except FileNotFoundError as exc:
        raise SortError(f"file not found: {path}") from exc
    except UnicodeDecodeError as exc:
        raise SortError(f"cannot decode {path} as {encoding}: {exc}") from exc
    if not text.strip():
        raise SortError(f"file is empty: {path}")
    delim = delimiter or detect_delimiter(text[:4096])
    reader = csv.reader(io.StringIO(text), delimiter=delim)
    rows = [row for row in reader]
    if not rows:
        raise SortError(f"file has no records: {path}")
    header = rows[0]
    body = rows[1:]
    for number, row in enumerate(body, start=2):
        if len(row) != len(header):
            raise SortError(
                f"row {number} has {len(row)} fields but the header has {len(header)}"
            )
    return Table(header=header, rows=body, delimiter=delim, has_header=True)


def read_headerless(path: Path, delimiter: str | None, encoding: str) -> Table:
    table = read_table(path, delimiter, encoding)
    width = len(table.header)
    table.rows.insert(0, table.header)
    table.header = [f"col{i + 1}" for i in range(width)]
    table.has_header = False
    return table


def write_table(table: Table, path: Path, encoding: str) -> None:
    buffer = io.StringIO()
    writer = csv.writer(buffer, delimiter=table.delimiter, lineterminator="\n")
    if table.has_header:
        writer.writerow(table.header)
    writer.writerows(table.rows)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(buffer.getvalue(), encoding=encoding)


# --------------------------------------------------------------------------
# Sorting
# --------------------------------------------------------------------------


@dataclass
class SortKey:
    index: int
    kind: str
    descending: bool
    name: str


def parse_key_spec(spec: str, table: Table, inferred: dict[str, str]) -> SortKey:
    """Parse ``field[:asc|desc][:text|numeric|date]`` into a SortKey."""
    parts = [p.strip() for p in spec.split(":") if p.strip()]
    if not parts:
        raise SortError("empty sort key")
    field = parts[0]
    index = table.column_index(field)
    descending = False
    kind = inferred.get(table.header[index], "text")
    for token in parts[1:]:
        low = token.casefold()
        if low in {"asc", "ascending"}:
            descending = False
        elif low in {"desc", "descending"}:
            descending = True
        elif low in {"text", "str", "string"}:
            kind = "text"
        elif low in {"numeric", "num", "number", "int", "float"}:
            kind = "numeric"
        elif low in {"date", "datetime"}:
            kind = "date"
        else:
            raise SortError(f"unknown key modifier {token!r} in {spec!r}")
    return SortKey(index=index, kind=kind, descending=descending, name=table.header[index])


def sort_rows(table: Table, keys: list[SortKey]) -> list[list[str]]:
    """Stable multi-key sort; missing values always sort last."""
    decorated: list[tuple[list[str], list[Any]]] = [
        (row, [convert(row[k.index], k.kind) for k in keys]) for row in table.rows
    ]

    def compare(left: tuple[list[str], list[Any]], right: tuple[list[str], list[Any]]) -> int:
        for i, key in enumerate(keys):
            a, b = left[1][i], right[1][i]
            if a is None and b is None:
                continue
            if a is None:
                return 1
            if b is None:
                return -1
            result = compare_values(a, b)
            if result:
                return -result if key.descending else result
        return 0

    decorated.sort(key=cmp_to_key(compare))
    return [row for row, _ in decorated]


def apply_sort(table: Table, specs: list[str]) -> tuple[Table, list[SortKey]]:
    inferred = table.types()
    keys = [parse_key_spec(spec, table, inferred) for spec in specs]
    if not keys:
        raise SortError("at least one --key is required")
    rows = sort_rows(table, keys)
    return Table(table.header, rows, table.delimiter, table.has_header), keys


# --------------------------------------------------------------------------
# Display helpers
# --------------------------------------------------------------------------


def format_table(table: Table, limit: int = 12) -> str:
    rows = ([table.header] if table.has_header else []) + table.rows[:limit]
    if not rows:
        return "(no rows)"
    widths = [max(len(str(row[i])) for row in rows) for i in range(len(table.header))]
    lines = []
    for n, row in enumerate(rows):
        lines.append("  ".join(str(cell).ljust(widths[i]) for i, cell in enumerate(row)))
        if n == 0 and table.has_header:
            lines.append("  ".join("-" * w for w in widths))
    hidden = len(table.rows) - limit
    if hidden > 0:
        lines.append(f"... {hidden} more row(s)")
    return "\n".join(lines)


# --------------------------------------------------------------------------
# Demo
# --------------------------------------------------------------------------

DEMO_CSV = """name,team,age,joined,score
Zoe,Blue,29,2021-05-17,88.5
adam,Red,34,2019-11-02,91.0
Maya,Blue,26,2022-01-30,95.5
Noah,Green,41,2015-07-08,72.0
Ivy,Red,34,2020-03-15,88.5
Liam,Green,23,2023-09-21,100.0
Elena,Blue,38,2018-12-05,84.0
"""


def run_demo() -> int:
    """Exercise inference, multi-key sort, date sort and in-place backup."""
    with tempfile.TemporaryDirectory(prefix="sortcsv-") as tmp:
        work = Path(tmp)
        source = work / "people.csv"
        source.write_text(DEMO_CSV, encoding="utf-8")

        table = read_table(source, None, "utf-8")
        inferred = table.types()
        print("Loaded people.csv")
        print("Inferred types: " + ", ".join(f"{k}={v}" for k, v in inferred.items()))
        assert inferred["age"] == "numeric" and inferred["joined"] == "date"
        assert inferred["name"] == "text"

        print("\nOriginal records:")
        print(format_table(table))

        sorted_table, keys = apply_sort(table, ["age:desc", "name:asc"])
        print("\nSorted by age desc, name asc:")
        print(format_table(sorted_table))
        ages = [int(row[2]) for row in sorted_table.rows]
        assert ages == sorted(ages, reverse=True), "age ordering is wrong"
        same_age = [r[0] for r in sorted_table.rows if r[2] == "34"]
        assert same_age == ["adam", "Ivy"], f"tie-break failed: {same_age}"

        by_date, _ = apply_sort(table, ["joined:date:desc"])
        dates = [row[3] for row in by_date.rows]
        assert dates[0] == "2023-09-21" and dates[-1] == "2015-07-08"
        print(f"\nNewest join date first: {dates[0]} (oldest {dates[-1]})")

        # Stable sort check: sorting only by team keeps original order in ties.
        by_team, _ = apply_sort(table, ["team:asc"])
        blue = [r[0] for r in by_team.rows if r[1] == "Blue"]
        assert blue == ["Zoe", "Maya", "Elena"], f"stability failed: {blue}"
        print(f"Stable tie order for Blue: {blue}")

        backup = work / "people.csv.bak"
        shutil.copy2(source, backup)
        write_table(sorted_table, source, "utf-8")
        assert backup.read_text(encoding="utf-8") == DEMO_CSV
        reloaded = read_table(source, None, "utf-8")
        assert reloaded.rows == sorted_table.rows
        print(f"\nIn-place write verified; backup preserved at {backup.name}")

        # Text sort is case-insensitive.
        names, _ = apply_sort(table, ["name:asc"])
        assert [r[0] for r in names.rows][:3] == ["adam", "Elena", "Ivy"]
        print("Case-insensitive name ordering verified.")
        print("\nDemo complete: CSV sort utility works.")
    return 0


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Sort CSV records by typed, multi-column keys.",
        epilog=(
            "Key syntax: FIELD[:asc|desc][:text|numeric|date]. "
            "Repeat --key for secondary sorts. Run --demo for an example."
        ),
    )
    parser.add_argument("input", nargs="?", type=Path, help="CSV file to read")
    parser.add_argument("-k", "--key", action="append", default=[], metavar="FIELD[:desc][:TYPE]",
                        help="sort key; repeat for secondary keys")
    parser.add_argument("-o", "--output", type=Path, help="write the sorted CSV here")
    parser.add_argument("--in-place", action="store_true",
                        help="overwrite the input file (writes a .bak backup)")
    parser.add_argument("--backup-suffix", default=".bak", help="backup suffix for --in-place")
    parser.add_argument("--delimiter", help="field delimiter (default: auto-detect)")
    parser.add_argument("--encoding", default="utf-8", help="input/output encoding")
    parser.add_argument("--no-header", action="store_true", help="treat the first row as data")
    parser.add_argument("--columns", help="comma-separated columns to keep, in order")
    parser.add_argument("--list-columns", action="store_true", help="show columns and inferred types")
    parser.add_argument("--demo", action="store_true", help="run the offline demo")
    return parser


def project_columns(table: Table, spec: str) -> Table:
    keep = [table.column_index(name.strip()) for name in spec.split(",") if name.strip()]
    return Table(
        header=[table.header[i] for i in keep],
        rows=[[row[i] for i in keep] for row in table.rows],
        delimiter=table.delimiter,
        has_header=table.has_header,
    )


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.demo:
        return run_demo()
    if args.input is None:
        build_parser().print_help()
        return 0
    if args.in_place and args.output:
        print("error: choose --in-place or --output, not both", file=sys.stderr)
        return 2
    if not args.key and not args.list_columns:
        print("error: provide at least one --key (or --list-columns)", file=sys.stderr)
        return 2

    try:
        table = (
            read_headerless(args.input, args.delimiter, args.encoding)
            if args.no_header
            else read_table(args.input, args.delimiter, args.encoding)
        )
        if args.list_columns:
            for name, kind in table.types().items():
                print(f"{name:<20} {kind}")
            if not args.key:
                return 0

        sorted_table, keys = apply_sort(table, args.key)

        if args.columns:
            sorted_table = project_columns(sorted_table, args.columns)

        if args.in_place:
            backup = args.input.with_name(args.input.name + args.backup_suffix)
            shutil.copy2(args.input, backup)
            write_table(sorted_table, args.input, args.encoding)
            print(f"Sorted {len(sorted_table.rows)} rows in place (backup: {backup.name})")
        elif args.output:
            write_table(sorted_table, args.output, args.encoding)
            print(f"Sorted {len(sorted_table.rows)} rows -> {args.output}")
        else:
            print(format_table(sorted_table, limit=len(sorted_table.rows) or 1))
        summary = ", ".join(
            f"{k.name} {'desc' if k.descending else 'asc'} ({k.kind})" for k in keys
        )
        print(f"Keys: {summary}")
        return 0
    except SortError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except OSError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
