"""Human-readable reporting for a completed thumbnail batch."""

from __future__ import annotations

import os

from pipeline import Summary


def format_bytes(value: float) -> str:
    """Human-readable byte count."""
    amount = float(value)
    for unit in ("B", "KiB", "MiB", "GiB"):
        if abs(amount) < 1024.0 or unit == "GiB":
            return f"{amount:.0f} {unit}" if unit == "B" else f"{amount:.2f} {unit}"
        amount /= 1024.0
    return f"{amount:.2f} GiB"


def print_report(summary: Summary, *, samples: int = 3) -> None:
    """Print the batch summary, failure list and a few manifest samples."""
    settings = summary.settings
    rate = summary.renamed / summary.elapsed if summary.elapsed > 0 else 0.0
    quality_note = (
        f" q{settings['quality']}" if settings["format"] in ("JPEG", "WEBP") else ""
    )
    print()
    print("Bulk thumbnail report")
    print(f"  source images : {summary.discovered}")
    print(f"  output dir    : {summary.output_dir}")
    print(
        f"  settings      : max {settings['width']}x{settings['height']}, "
        f"{settings['format']}{quality_note}, {settings['workers']} workers"
    )
    print(f"  elapsed       : {summary.elapsed:.2f}s ({rate:.1f} images/s)")
    print(f"  succeeded     : {summary.renamed}")
    print(f"  failed        : {summary.failed}")
    for failure in summary.failures[:5]:
        detail = failure.error.replace(str(failure.source.parent) + os.sep, "")
        print(f"    - {failure.source.name} [{failure.stage}] {detail}")
    if len(summary.failures) > 5:
        print(f"    ... {len(summary.failures) - 5} more in the manifest")
    print(
        f"  bytes         : {format_bytes(summary.input_bytes)} in -> "
        f"{format_bytes(summary.output_bytes)} out"
    )
    print(f"  manifest      : {summary.manifest_path}")
    for entry in summary.entries[:samples]:
        source_size = f"{entry['source_dimensions'][0]}x{entry['source_dimensions'][1]}"
        thumb_size = f"{entry['thumbnail_dimensions'][0]}x{entry['thumbnail_dimensions'][1]}"
        captured = f"  captured {entry['captured'][:10]}" if entry["captured"] else ""
        print(
            f"    {entry['thumbnail']}  <-  {entry['source']}  "
            f"({source_size} -> {thumb_size}){captured}"
        )
