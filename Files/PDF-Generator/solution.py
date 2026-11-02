#!/usr/bin/env python3
"""Generate a small, valid PDF from a plain-text or simple HTML file.

The writer is pure standard library: it lays out headings, paragraphs, lists,
bold/italic runs and explicit page breaks, then emits PDF objects, a content
stream per page, a cross-reference table and a trailer.  Text uses the
standard Helvetica family with WinAnsi encoding; font metrics are
approximated (no font is embedded).

``--validate`` checks an existing PDF's header, xref offsets and page count.
"""

from __future__ import annotations

import argparse
import re
import sys
import tempfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

PAGE_SIZES = {
    "a4": (595.28, 841.89),
    "letter": (612.0, 792.0),
}


class PdfError(Exception):
    """Raised for unreadable input or an invalid PDF."""


# --------------------------------------------------------------------------
# Document model
# --------------------------------------------------------------------------


@dataclass
class Run:
    """A stretch of text sharing one style."""

    text: str
    bold: bool = False
    italic: bool = False


@dataclass
class Block:
    """A layout block: heading, paragraph, bullet, rule or page break."""

    kind: str
    runs: list[Run] = field(default_factory=list)
    level: int = 0


def merge_runs(runs: list[Run]) -> list[Run]:
    cleaned: list[Run] = []
    for run in runs:
        if not run.text:
            continue
        if cleaned and (cleaned[-1].bold, cleaned[-1].italic) == (run.bold, run.italic):
            cleaned[-1].text += run.text
        else:
            cleaned.append(Run(run.text, run.bold, run.italic))
    return cleaned


def text_to_blocks(text: str) -> list[Block]:
    """Split plain text on blank lines; hard-wrapped lines are rejoined."""
    blocks: list[Block] = []
    for chunk in re.split(r"\n\s*\n", text.replace("\r\n", "\n")):
        lines = [line.strip() for line in chunk.splitlines() if line.strip()]
        if lines:
            blocks.append(Block("paragraph", [Run(" ".join(lines))]))
    return blocks


class HtmlToBlocks(HTMLParser):
    """Collect a small subset of HTML into layout blocks."""

    HEADINGS = {"h1": 1, "h2": 2, "h3": 3}
    BLOCK_TAGS = {"p", "div", "li", "blockquote"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.blocks: list[Block] = []
        self.runs: list[Run] = []
        self.current = "paragraph"
        self.level = 0
        self.bold = 0
        self.italic = 0
        self.skip = 0

    def flush(self) -> None:
        runs = merge_runs(self.runs)
        self.runs = []
        while runs and not runs[-1].text.strip():
            runs.pop()
        while runs and not runs[0].text.strip():
            runs[0].text = runs[0].text.lstrip()
        if runs:
            self.blocks.append(Block(self.current, runs, self.level))

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attrs_dict = dict(attrs)
        if tag in {"script", "style", "head"}:
            self.skip += 1
        elif tag in self.HEADINGS:
            self.flush()
            self.current, self.level = "heading", self.HEADINGS[tag]
        elif tag in self.BLOCK_TAGS:
            classes = (attrs_dict.get("class") or "").split()
            if tag == "div" and ("page-break" in classes or "pagebreak" in classes):
                self.flush()
                self.blocks.append(Block("pagebreak"))
                return
            self.flush()
            self.current = "bullet" if tag == "li" else "paragraph"
            self.level = 0
        elif tag == "br":
            self.runs.append(Run("\n", bool(self.bold), bool(self.italic)))
        elif tag == "hr":
            self.flush()
            self.blocks.append(Block("rule"))
        elif tag in {"b", "strong"}:
            self.bold += 1
        elif tag in {"i", "em"}:
            self.italic += 1

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "head"}:
            self.skip = max(0, self.skip - 1)
        elif tag in self.HEADINGS or tag in self.BLOCK_TAGS:
            self.flush()
            self.current, self.level = "paragraph", 0
        elif tag in {"b", "strong"}:
            self.bold = max(0, self.bold - 1)
        elif tag in {"i", "em"}:
            self.italic = max(0, self.italic - 1)

    def handle_data(self, data: str) -> None:
        if self.skip:
            return
        text = re.sub(r"\s+", " ", data)
        if text:
            self.runs.append(Run(text, bool(self.bold), bool(self.italic)))

    def close(self) -> None:
        super().close()
        self.flush()


def html_to_blocks(text: str) -> list[Block]:
    parser = HtmlToBlocks()
    parser.feed(text)
    parser.close()
    return parser.blocks


# --------------------------------------------------------------------------
# Text measurement and line breaking
# --------------------------------------------------------------------------

NARROW = set("iljftrI.,:;'!|()[]")
WIDE = set("mwMW@%&")


def char_width(char: str, size: float, bold: bool = False) -> float:
    """Approximate Helvetica advance width in points."""
    if char == " ":
        units = 278
    elif char in NARROW:
        units = 278
    elif char in WIDE:
        units = 833
    elif char.isupper():
        units = 667
    elif char.isdigit():
        units = 556
    elif char in "“”‘’":
        units = 333
    else:
        units = 556
    if bold:
        units *= 1.04
    return units * size / 1000.0


def text_width(text: str, size: float, bold: bool = False) -> float:
    return sum(char_width(ch, size, bold) for ch in text)


def wrap_runs(
    runs: list[Run],
    width: float,
    size: float,
    first_indent: float = 0.0,
    rest_indent: float = 0.0,
) -> list[list[Run]]:
    """Greedy word wrap; long words are split at character boundaries."""
    tokens: list[tuple[str, bool, bool]] = []
    for run in runs:
        for match in re.finditer(r"\n|\S+|\s+", run.text):
            tokens.append((match.group(), run.bold, run.italic))

    lines: list[list[Run]] = []
    line: list[Run] = []
    used = first_indent
    indent = first_indent
    pending_space = False

    def push() -> None:
        nonlocal line, used, indent, pending_space
        if line:
            lines.append(line)
        line, used, indent, pending_space = [], rest_indent, rest_indent, False

    for token, bold, italic in tokens:
        if token == "\n":
            push()
            continue
        if token.isspace():
            pending_space = True
            continue
        space_w = char_width(" ", size) if line else 0.0
        token_w = text_width(token, size, bold)
        if line and used + space_w + token_w > width:
            push()
            space_w, token_w = 0.0, text_width(token, size, bold)

        if token_w > width - used and not line:
            piece = ""
            for ch in token:
                if piece and used + text_width(piece + ch, size, bold) > width:
                    lines.append([Run(piece, bold, italic)])
                    used = rest_indent
                    piece = ch
                else:
                    piece += ch
            if piece:
                line = [Run(piece, bold, italic)]
                used += text_width(piece, size, bold)
            continue

        if pending_space and line:
            if line[-1].bold == bold and line[-1].italic == italic:
                line[-1].text += " "
            else:
                line.append(Run(" ", bold, italic))
            used += space_w
        pending_space = False
        if line and line[-1].bold == bold and line[-1].italic == italic:
            line[-1].text += token
        else:
            line.append(Run(token, bold, italic))
        used += token_w
    push()
    return lines


# --------------------------------------------------------------------------
# PDF writing
# --------------------------------------------------------------------------

FONT_NAMES = {
    (False, False): "F1",
    (True, False): "F2",
    (False, True): "F3",
    (True, True): "F4",
}


def pdf_string(text: str) -> str:
    """Encode text as a PDF literal string in WinAnsi, escaping specials."""
    data = text.encode("cp1252", "replace")
    out: list[str] = []
    for byte in data:
        if byte in (0x28, 0x29, 0x5C):
            out.append("\\" + chr(byte))
        elif 32 <= byte <= 126:
            out.append(chr(byte))
        else:
            out.append(f"\\{byte:03o}")
    return "(" + "".join(out) + ")"


@dataclass
class PdfOptions:
    """Page geometry and typography settings."""

    page_size: str = "a4"
    margin: float = 56.7
    font_size: float = 11.0
    line_spacing: float = 1.35
    title: str = ""


class Layout:
    """Flowing page layout that emits PDF content operators."""

    def __init__(self, options: PdfOptions) -> None:
        self.options = options
        self.width, self.height = PAGE_SIZES[options.page_size]
        self.pages: list[list[str]] = [[]]
        self.y = self.height - options.margin
        self.body_leading = options.font_size * options.line_spacing

    @property
    def content_width(self) -> float:
        return self.width - 2 * self.options.margin

    def new_page(self) -> None:
        self.pages.append([])
        self.y = self.height - self.options.margin

    def ensure(self, space: float) -> None:
        if self.y - space < self.options.margin:
            self.new_page()

    def draw_line(
        self,
        segments: list[Run],
        size: float,
        x_offset: float = 0.0,
        color: str = "0 0 0",
    ) -> None:
        ops = self.pages[-1]
        x = self.options.margin + x_offset
        for segment in segments:
            if not segment.text:
                continue
            font = FONT_NAMES[(segment.bold, segment.italic)]
            ops.append(
                f"{color} rg BT /{font} {size:g} Tf "
                f"1 0 0 1 {x:.2f} {self.y:.2f} Tm {pdf_string(segment.text)} Tj ET"
            )
            x += text_width(segment.text, size, segment.bold)

    def heading(self, block: Block) -> None:
        size = {1: 20.0, 2: 15.5, 3: 13.0}.get(block.level, 12.0)
        before = {1: 8.0, 2: 14.0, 3: 10.0}.get(block.level, 10.0)
        self.y -= before
        leading = size * 1.25
        lines = wrap_runs(block.runs, self.content_width, size)
        self.ensure(leading * min(2, len(lines)) + 4)
        for line in lines:
            self.ensure(leading)
            self.y -= leading * 0.8
            self.draw_line(line, size, color="0.09 0.18 0.31")
            self.y -= leading * 0.2
        if block.level == 1:
            self.y -= 3
            ops = self.pages[-1]
            ops.append(
                f"0.75 0.78 0.82 RG 0.8 w {self.options.margin:.2f} {self.y:.2f} m "
                f"{self.width - self.options.margin:.2f} {self.y:.2f} l S"
            )
        self.y -= 6

    def paragraph(self, block: Block) -> None:
        lines = wrap_runs(block.runs, self.content_width, self.options.font_size)
        self.ensure(self.body_leading * min(2, len(lines)))
        for line in lines:
            self.ensure(self.body_leading)
            self.y -= self.body_leading * 0.8
            self.draw_line(line, self.options.font_size)
            self.y -= self.body_leading * 0.2
        self.y -= self.options.font_size * 0.55

    def bullet(self, block: Block) -> None:
        indent = 16.0
        lines = wrap_runs(
            block.runs,
            self.content_width - indent,
            self.options.font_size,
            first_indent=0,
            rest_indent=indent,
        )
        self.ensure(self.body_leading * min(2, len(lines)))
        for number, line in enumerate(lines):
            self.ensure(self.body_leading)
            self.y -= self.body_leading * 0.8
            if number == 0:
                self.draw_line([Run("•", bold=False)], self.options.font_size, x_offset=3)
            self.draw_line(line, self.options.font_size, x_offset=indent)
            self.y -= self.body_leading * 0.2
        self.y -= self.options.font_size * 0.3

    def rule(self) -> None:
        self.ensure(12)
        self.y -= 6
        ops = self.pages[-1]
        ops.append(
            f"0.75 0.75 0.75 RG 0.5 w {self.options.margin:.2f} {self.y:.2f} m "
            f"{self.width - self.options.margin:.2f} {self.y:.2f} l S"
        )
        self.y -= 8

    def render(self, blocks: list[Block]) -> list[list[str]]:
        for block in blocks:
            if block.kind == "pagebreak":
                self.new_page()
            elif block.kind == "heading":
                self.heading(block)
            elif block.kind == "bullet":
                self.bullet(block)
            elif block.kind == "rule":
                self.rule()
            else:
                self.paragraph(block)
        if len(self.pages) > 1 and not self.pages[-1]:
            self.pages.pop()
        if not self.pages:
            self.pages = [[]]
        return self.pages

    def add_page_numbers(self) -> None:
        total = len(self.pages)
        size = 9.0
        for number, ops in enumerate(self.pages, 1):
            label = f"Page {number} of {total}"
            x = (self.width - text_width(label, size)) / 2
            ops.append(
                f"0.42 0.42 0.42 rg BT /F1 {size:g} Tf "
                f"1 0 0 1 {x:.2f} {self.options.margin * 0.45:.2f} Tm "
                f"{pdf_string(label)} Tj ET"
            )


def build_pdf(blocks: list[Block], options: PdfOptions) -> bytes:
    """Lay out blocks and serialise a complete PDF document."""
    layout = Layout(options)
    pages = layout.render(blocks)
    layout.add_page_numbers()

    width, height = PAGE_SIZES[options.page_size]
    first_page_id = 8
    page_ids = [first_page_id + 2 * i for i in range(len(pages))]
    content_ids = [pid + 1 for pid in page_ids]

    objects: list[bytes] = [b""] * (first_page_id + 2 * len(pages) - 1)

    def put(obj_id: int, payload: bytes) -> None:
        objects[obj_id - 1] = payload

    put(1, b"<< /Type /Catalog /Pages 2 0 R >>")
    kids = " ".join(f"{pid} 0 R" for pid in page_ids)
    put(
        2,
        f"<< /Type /Pages /Kids [{kids}] /Count {len(pages)} >>".encode("ascii"),
    )
    fonts = [
        ("F1", "Helvetica"),
        ("F2", "Helvetica-Bold"),
        ("F3", "Helvetica-Oblique"),
        ("F4", "Helvetica-BoldOblique"),
    ]
    for index, (name, base) in enumerate(fonts, start=3):
        put(
            index,
            (
                f"<< /Type /Font /Subtype /Type1 /BaseFont /{base} "
                "/Encoding /WinAnsiEncoding >>"
            ).encode("ascii"),
        )
    created = datetime.now(timezone.utc).strftime("D:%Y%m%d%H%M%S")
    info = f"<< /Title {pdf_string(options.title or 'Generated Document')} "
    info += f"/Producer (Python stdlib PDF Generator) /CreationDate ({created}) >>"
    put(7, info.encode("cp1252"))

    resources = (
        "<< /Font << /F1 3 0 R /F2 4 0 R /F3 5 0 R /F4 6 0 R >> "
        "/ProcSet [/PDF /Text] >>"
    )
    for page_id, content_id, ops in zip(page_ids, content_ids, pages):
        stream = "\n".join(ops).encode("cp1252", "replace")
        put(
            page_id,
            (
                f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {width:g} {height:g}] "
                f"/Resources {resources} /Contents {content_id} 0 R >>"
            ).encode("ascii"),
        )
        put(
            content_id,
            f"<< /Length {len(stream)} >>\nstream\n".encode("ascii")
            + stream
            + b"\nendstream",
        )

    out = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = [0]
    for obj_id, payload in enumerate(objects, 1):
        offsets.append(len(out))
        out += f"{obj_id} 0 obj\n".encode("ascii") + payload + b"\nendobj\n"
    xref_at = len(out)
    out += f"xref\n0 {len(objects) + 1}\n".encode("ascii")
    out += b"0000000000 65535 f \n"
    for offset in offsets[1:]:
        out += f"{offset:010d} 00000 n \n".encode("ascii")
    out += (
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R /Info 7 0 R >>\n"
        f"startxref\n{xref_at}\n%%EOF\n"
    ).encode("ascii")
    return bytes(out)


# --------------------------------------------------------------------------
# Validation
# --------------------------------------------------------------------------


def validate_pdf(path: Path) -> dict[str, Any]:
    """Check header, xref offsets and page count of a classic PDF."""
    try:
        data = path.read_bytes()
    except FileNotFoundError as exc:
        raise PdfError(f"PDF not found: {path}") from exc
    if not data.startswith(b"%PDF-1."):
        raise PdfError("missing %PDF- header")
    if b"%%EOF" not in data[-1024:]:
        raise PdfError("missing %%EOF marker")
    marker = data.rfind(b"startxref")
    if marker == -1:
        raise PdfError("missing startxref")
    match = re.search(rb"startxref\s+(\d+)", data[marker:])
    if not match:
        raise PdfError("unreadable startxref offset")
    xref_at = int(match.group(1))
    if not data[xref_at:].startswith(b"xref"):
        raise PdfError("startxref does not point at an xref table")
    header = re.match(rb"xref\s+0\s+(\d+)\s+", data[xref_at:])
    if not header:
        raise PdfError("unsupported xref table format")
    count = int(header.group(1))
    entry_start = xref_at + header.end()
    for obj_id in range(1, count):
        entry = data[entry_start + 20 * obj_id: entry_start + 20 * obj_id + 20]
        try:
            offset = int(entry[:10])
        except ValueError as exc:
            raise PdfError(f"malformed xref entry {obj_id}") from exc
        needle = f"{obj_id} 0 obj".encode("ascii")
        if not data[offset:].startswith(needle):
            raise PdfError(f"xref entry {obj_id} points to the wrong object")
    pages = len(re.findall(rb"/Type\s*/Page[^s]", data))
    if pages == 0:
        raise PdfError("no page objects found")
    return {
        "pages": pages,
        "bytes": len(data),
        "version": data[:8].decode("ascii"),
        "objects": count - 1,
    }


# --------------------------------------------------------------------------
# Demo
# --------------------------------------------------------------------------

DEMO_TEXT = """PDF Generator Demo
==================

This paragraph comes from a plain-text file.  The generator wraps it to the
page width, honours the configured margins, and writes a cross-reference
table so the result is a structurally valid PDF.

A second paragraph starts after a blank line.  Text is measured with an
approximation of the Helvetica metrics, which keeps line breaks close to
what a real viewer will render.
"""

DEMO_HTML = """<!doctype html>
<html><head><title>HTML sample</title></head>
<body>
  <h1>HTML Report</h1>
  <p>This document was produced from <b>simple HTML</b> with
  <i>italic</i> and <b><i>bold italic</i></b> runs.</p>
  <h2>Highlights</h2>
  <ul>
    <li>Headings and paragraphs</li>
    <li>Lists, rules and explicit page breaks</li>
  </ul>
  <hr>
  <p>A line break follows.<br>This is on the next line.</p>
  <div class="page-break"></div>
  <h2>Second Page</h2>
  <p>The page break above forced this content onto a new page, and every
  page carries a page number in the footer.</p>
</body></html>
"""


def run_demo() -> int:
    """Create PDFs from text and HTML, then validate structure and pages."""
    with tempfile.TemporaryDirectory(prefix="pdfgen-") as tmp:
        work = Path(tmp)
        text_path = work / "sample.txt"
        html_path = work / "sample.html"
        text_path.write_text(DEMO_TEXT, encoding="utf-8")
        html_path.write_text(DEMO_HTML, encoding="utf-8")

        text_pdf = work / "from_text.pdf"
        blocks = text_to_blocks(DEMO_TEXT)
        options = PdfOptions(page_size="a4", margin=56.7, title="Text Sample")
        text_pdf.write_bytes(build_pdf(blocks, options))
        info = validate_pdf(text_pdf)
        print(f"Text PDF : {text_pdf.name}  {info['bytes']} bytes  "
              f"{info['pages']} page(s)  {info['objects']} objects")
        assert info["pages"] >= 1

        html_pdf = work / "from_html.pdf"
        html_blocks = html_to_blocks(DEMO_HTML)
        kinds = [b.kind for b in html_blocks]
        print(f"HTML blocks parsed: {len(html_blocks)} -> {kinds}")
        assert "heading" in kinds and "bullet" in kinds and "pagebreak" in kinds
        html_pdf.write_bytes(
            build_pdf(html_blocks, PdfOptions(page_size="a4", margin=51.0, title="HTML Sample"))
        )
        html_info = validate_pdf(html_pdf)
        print(f"HTML PDF : {html_pdf.name}  {html_info['bytes']} bytes  "
              f"{html_info['pages']} page(s)  {html_info['objects']} objects")
        assert html_info["pages"] >= 2, "explicit page break did not produce a second page"

        header = text_pdf.read_bytes()[:8]
        print(f"Header   : {header!r}")
        assert header == b"%PDF-1.4"

        letter_pdf = work / "letter.pdf"
        letter_pdf.write_bytes(build_pdf(blocks, PdfOptions(page_size="letter")))
        assert validate_pdf(letter_pdf)["pages"] >= 1
        print("Letter-size variant validated.")

        try:
            validate_pdf(text_path)
            raise AssertionError("expected PdfError for a text file")
        except PdfError:
            print("Validator rejected a non-PDF file as expected.")
        print("\nDemo complete: PDF generation and validation work.")
    return 0


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Convert a text or simple HTML file into a paginated PDF.",
        epilog="Run --demo to generate and validate sample PDFs offline.",
    )
    parser.add_argument("input", nargs="?", type=Path, help="input .txt/.html file")
    parser.add_argument("-o", "--output", type=Path, help="output PDF (default: input.pdf)")
    parser.add_argument("--format", choices=["auto", "text", "html"], default="auto",
                        help="input format (default: by extension)")
    parser.add_argument("--page-size", choices=sorted(PAGE_SIZES), default="a4")
    parser.add_argument("--margin", type=float, default=56.7,
                        help="page margin in points (default 56.7 = 2 cm)")
    parser.add_argument("--font-size", type=float, default=11.0, help="body font size")
    parser.add_argument("--line-spacing", type=float, default=1.35, help="line height factor")
    parser.add_argument("--title", help="PDF metadata title")
    parser.add_argument("--validate", type=Path, metavar="PDF",
                        help="validate an existing PDF and print its page count")
    parser.add_argument("--demo", action="store_true", help="run the offline demo")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.demo:
        return run_demo()

    if args.validate:
        try:
            info = validate_pdf(args.validate)
        except PdfError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2
        print(f"Valid PDF: {info['version']}, {info['pages']} pages, "
              f"{info['objects']} objects, {info['bytes']} bytes")
        return 0

    if args.input is None:
        build_parser().print_help()
        return 0

    fmt = args.format
    if fmt == "auto":
        fmt = "html" if args.input.suffix.lower() in {".html", ".htm"} else "text"
    try:
        source = args.input.read_text(encoding="utf-8")
    except FileNotFoundError:
        print(f"error: input not found: {args.input}", file=sys.stderr)
        return 2
    except UnicodeDecodeError as exc:
        print(f"error: input is not UTF-8 text: {exc}", file=sys.stderr)
        return 2
    if not source.strip():
        print("error: input is empty", file=sys.stderr)
        return 2

    blocks = html_to_blocks(source) if fmt == "html" else text_to_blocks(source)
    if not blocks:
        print("error: no renderable content found", file=sys.stderr)
        return 2

    options = PdfOptions(
        page_size=args.page_size,
        margin=max(8.0, args.margin),
        font_size=max(4.0, args.font_size),
        line_spacing=max(1.0, args.line_spacing),
        title=args.title or args.input.stem.replace("_", " ").title(),
    )
    try:
        pdf = build_pdf(blocks, options)
    except (ValueError, OverflowError) as exc:
        print(f"error: could not lay out document: {exc}", file=sys.stderr)
        return 2
    output = args.output or args.input.with_suffix(".pdf")
    output.write_bytes(pdf)
    info = validate_pdf(output)
    print(f"Wrote {output} ({info['pages']} pages, {info['bytes']} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
