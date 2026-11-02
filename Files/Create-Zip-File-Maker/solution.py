#!/usr/bin/env python3
"""Create zip archives from files in different directories, then list or extract them.

Sources may be files or directories; directory trees keep their layout, and
``--exclude`` globs drop unwanted files.  Compression can be ``store`` (no
compression) or one of the compressed methods supported by :mod:`zipfile`.

Note: Python's standard library can *read* legacy ZipCrypto archives but it
cannot *write* encrypted archives; use a tool such as 7-Zip for that.
"""

from __future__ import annotations

import argparse
import fnmatch
import os
import sys
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path

COMPRESSIONS = {
    "store": zipfile.ZIP_STORED,
    "deflate": zipfile.ZIP_DEFLATED,
    "bzip2": zipfile.ZIP_BZIP2,
    "lzma": zipfile.ZIP_LZMA,
}


class ZipError(Exception):
    """Raised for missing sources, unsafe paths or corrupt archives."""


@dataclass
class Entry:
    """One archive member with its on-disk source path."""

    source: Path
    arcname: str


def matches_exclude(arcname: str, patterns: list[str]) -> bool:
    """True when any glob matches the full arcname or the basename."""
    base = arcname.rsplit("/", 1)[-1]
    return any(
        fnmatch.fnmatchcase(arcname, pat) or fnmatch.fnmatchcase(base, pat)
        for pat in patterns
    )


def collect_entries(
    sources: list[Path],
    excludes: list[str],
    arcname: str | None,
    no_top_dir: bool,
) -> list[Entry]:
    """Expand sources into archive members, preserving directory structure."""
    if arcname and (len(sources) != 1 or sources[0].is_dir()):
        raise ZipError("--arcname is only valid with a single file source")
    entries: list[Entry] = []
    seen: set[str] = set()

    def add(path: Path, name: str) -> None:
        name = name.strip("/")
        if not name or name.endswith("/"):
            return
        if matches_exclude(name, excludes):
            print(f"  excluded {name}")
            return
        if name in seen:
            raise ZipError(f"duplicate archive name: {name}")
        seen.add(name)
        entries.append(Entry(path, name))

    for src in sources:
        if not src.exists():
            raise ZipError(f"source does not exist: {src}")
        if src.is_dir():
            base = src if no_top_dir else src.parent
            for path in sorted(src.rglob("*")):
                if path.is_dir():
                    continue
                add(path, path.relative_to(base).as_posix())
        else:
            add(src, arcname or src.name)

    if not entries:
        raise ZipError("no files matched the given sources and exclusions")
    return entries


def create_archive(
    entries: list[Entry],
    output: Path,
    compression: str,
    level: int | None,
) -> zipfile.ZipFile:
    """Write the archive atomically (temp file + replace) and return it opened."""
    if compression not in COMPRESSIONS:
        raise ZipError(f"unknown compression {compression!r}")
    if level is not None and not 0 <= level <= 9:
        raise ZipError("--level must be between 0 and 9")
    output.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=output.name + ".", dir=output.parent)
    os.close(fd)
    tmp = Path(tmp_name)
    try:
        with zipfile.ZipFile(
            tmp,
            "w",
            compression=COMPRESSIONS[compression],
            compresslevel=level if compression != "store" else None,
            strict_timestamps=False,
        ) as archive:
            for entry in entries:
                archive.write(entry.source, arcname=entry.arcname)
        os.replace(tmp, output)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise
    return zipfile.ZipFile(output)


def describe(archive: zipfile.ZipFile) -> list[str]:
    """Return one summary line per member, plus a total line."""
    lines = [f"{'Name':<40} {'Size':>10} {'Packed':>10} {'Ratio':>7}  Method"]
    total_raw = total_packed = 0
    for info in archive.infolist():
        if info.is_dir():
            continue
        total_raw += info.file_size
        total_packed += info.compress_size
        ratio = f"{info.compress_size / info.file_size:.0%}" if info.file_size else "-"
        method = {
            zipfile.ZIP_STORED: "store",
            zipfile.ZIP_DEFLATED: "deflate",
            zipfile.ZIP_BZIP2: "bzip2",
            zipfile.ZIP_LZMA: "lzma",
        }.get(info.compress_type, str(info.compress_type))
        encrypted = " (encrypted)" if info.flag_bits & 0x1 else ""
        lines.append(
            f"{info.filename:<40} {info.file_size:>10} {info.compress_size:>10} "
            f"{ratio:>7}  {method}{encrypted}"
        )
    if total_raw:
        pct = 100 * (1 - total_packed / total_raw)
        lines.append(
            f"{'TOTAL':<40} {total_raw:>10} {total_packed:>10} "
            f"{total_packed / total_raw:>6.0%}  saved {pct:.1f}%"
        )
    return lines


def safe_extract(archive: zipfile.ZipFile, dest: Path) -> list[Path]:
    """Extract members, refusing absolute paths and ``..`` escapes."""
    dest.mkdir(parents=True, exist_ok=True)
    root = dest.resolve()
    written: list[Path] = []
    for info in archive.infolist():
        target = (dest / info.filename).resolve()
        if not target.is_relative_to(root):
            raise ZipError(f"unsafe member path: {info.filename!r}")
        archive.extract(info, dest)
        if not info.is_dir():
            written.append(target)
    return written


def open_archive(path: Path) -> zipfile.ZipFile:
    if not path.exists():
        raise ZipError(f"archive not found: {path}")
    try:
        return zipfile.ZipFile(path)
    except zipfile.BadZipFile as exc:
        raise ZipError(f"not a valid zip archive: {path}") from exc


# --------------------------------------------------------------------------
# Demo
# --------------------------------------------------------------------------

DEMO_TREE = {
    "notes/readme.txt": (
        "Project notes\n=============\n\nKeep this file.\n" * 20
    ),
    "notes/draft.txt": "Draft copy that will be excluded.\n" * 20,
    "src/app.py": (
        "def main():\n    print('hello from src/app.py')\n\n" * 12
    ),
    "src/data/values.csv": "id,value\n" + "".join(
        f"{index},{index * 10}\n" for index in range(20)
    ),
    "src/debug.log": "noise\n" * 50,
}


def run_demo() -> int:
    """Create archives with excludes, verify integrity, list and extract."""
    with tempfile.TemporaryDirectory(prefix="zipmaker-") as tmp:
        work = Path(tmp)
        for relative, content in DEMO_TREE.items():
            path = work / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")

        archive_path = work / "dist" / "bundle.zip"
        entries = collect_entries(
            [work / "notes", work / "src"],
            excludes=["*.log", "draft.txt"],
            arcname=None,
            no_top_dir=False,
        )
        print(f"Collected {len(entries)} files for the archive:")
        for entry in entries:
            print(f"  {entry.arcname:<24} <- {entry.source.relative_to(work)}")

        with create_archive(entries, archive_path, "deflate", 9) as archive:
            print(f"\nArchive: {archive_path.name} ({archive_path.stat().st_size} bytes)")
            print("\n".join(describe(archive)))
            bad = archive.testzip()
            assert bad is None, f"CRC failure in {bad}"
            assert archive.read("src/app.py") == DEMO_TREE["src/app.py"].encode()
            assert "src/debug.log" not in archive.namelist()
            assert "notes/draft.txt" not in archive.namelist()

        with open_archive(archive_path) as archive:
            out_dir = work / "extracted"
            written = safe_extract(archive, out_dir)
            print(f"\nExtracted {len(written)} files to {out_dir.name}/")
            assert (out_dir / "src" / "data" / "values.csv").read_text() == DEMO_TREE[
                "src/data/values.csv"
            ]

        stored_path = work / "dist" / "stored.zip"
        with create_archive(entries, stored_path, "store", None) as stored:
            assert stored.testzip() is None
            stored_size = stored_path.stat().st_size
        print(
            f"Deflate archive {archive_path.stat().st_size} bytes vs "
            f"stored archive {stored_size} bytes"
        )
        assert archive_path.stat().st_size < stored_size
        print("Compression reduced the archive size.")

        try:
            bad = collect_entries([work / "src"], ["*"], None, True)
            raise AssertionError(f"expected ZipError, got {len(bad)} entries")
        except ZipError:
            print("Exclude-everything guard raised ZipError as expected.")
        print("\nDemo complete: zip creation, listing, test and extraction work.")
    return 0


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Zip files from different directories; list or extract archives.",
        epilog="Encrypted archives can be read but not written by the standard library.",
    )
    parser.add_argument("sources", nargs="*", type=Path, help="files/directories to add")
    parser.add_argument("-o", "--output", type=Path, default=Path("archive.zip"),
                        help="archive to create (default: archive.zip)")
    parser.add_argument("--compression", choices=sorted(COMPRESSIONS), default="deflate",
                        help="compression method (default: deflate)")
    parser.add_argument("--level", type=int, default=6,
                        help="compression level 0-9 (default 6; ignored for store)")
    parser.add_argument("--exclude", action="append", default=[], metavar="GLOB",
                        help="exclude matching archive paths or basenames; repeatable")
    parser.add_argument("--arcname", help="archive name for a single file source")
    parser.add_argument("--no-top-dir", action="store_true",
                        help="directory contents go at the archive root")
    parser.add_argument("--list", type=Path, metavar="ARCHIVE", help="list an archive")
    parser.add_argument("--test", type=Path, metavar="ARCHIVE", help="verify archive CRCs")
    parser.add_argument("--extract", type=Path, metavar="ARCHIVE", help="extract an archive")
    parser.add_argument("-d", "--dest", type=Path, default=Path("."),
                        help="extraction destination (default: current directory)")
    parser.add_argument("--demo", action="store_true", help="run the offline demo")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.demo:
        return run_demo()

    try:
        if args.list:
            with open_archive(args.list) as archive:
                print("\n".join(describe(archive)))
            return 0

        if args.test:
            with open_archive(args.test) as archive:
                bad = archive.testzip()
                if bad is not None:
                    print(f"FAILED: CRC error in {bad}", file=sys.stderr)
                    return 1
                print(f"OK: {len(archive.infolist())} entries, all CRCs valid")
            return 0

        if args.extract:
            with open_archive(args.extract) as archive:
                written = safe_extract(archive, args.dest)
            print(f"Extracted {len(written)} files to {args.dest}")
            return 0

        if not args.sources:
            build_parser().print_help()
            return 0

        entries = collect_entries(args.sources, args.exclude, args.arcname, args.no_top_dir)
        with create_archive(entries, args.output, args.compression, args.level) as archive:
            print(f"Created {args.output} with {len(entries)} files ({args.compression}):")
            for entry in entries:
                print(f"  {entry.arcname}")
            print(f"Archive size: {args.output.stat().st_size} bytes")
        return 0
    except (ZipError, OSError, zipfile.BadZipFile) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
