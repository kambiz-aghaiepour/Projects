#!/usr/bin/env python3
"""A tiny turtle interpreter on a 20 x 20 floor, rendered to PNG and SVG.

Commands (case-insensitive, one or more per line):

=============  =====================================================
FD n           move forward n squares, drawing when the pen is down
BK n           move backward n squares
LT deg / RT deg turn left / right (degrees)
PU / PD        lift / drop the pen
COLOR name     named colour, ``#rrggbb`` or ``rgb(r,g,b)``
WIDTH n        pen width in pixels (at the 900 px reference size)
HOME           return to (10, 10) facing north without drawing
REPEAT n [ ]   repeat the commands inside the brackets n times
=============  =====================================================

``;`` starts a comment.  Command files are read with ``--file``; the demo
writes one, executes it, and produces both renderings.
"""

from __future__ import annotations

import argparse
import math
import re
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Sequence

try:
    from PIL import Image, ImageDraw, ImageFont
except ImportError:  # pragma: no cover
    Image = None  # type: ignore[assignment]

GRID = 20
START = (GRID / 2, GRID / 2)
REFERENCE_SIZE = 900
COLORS = {
    "black": "#1f2933", "white": "#ffffff", "red": "#d64545", "green": "#2f855a",
    "blue": "#2b6cb0", "orange": "#dd6b20", "purple": "#6b46c1", "teal": "#0f766e",
    "gray": "#718096", "grey": "#718096", "brown": "#8b5e3c", "pink": "#d53f8c",
    "yellow": "#d69e2e",
}
TOKEN_RE = re.compile(r"\[|\]|[^\s\[\]]+")
NUMBER_RE = re.compile(r"^[+-]?(?:\d+(?:\.\d*)?|\.\d+)$")
HEX_RE = re.compile(r"^#?([0-9a-fA-F]{6}|[0-9a-fA-F]{3})$")
RGB_RE = re.compile(r"^rgb\(\s*(\d{1,3})\s*,\s*(\d{1,3})\s*,\s*(\d{1,3})\s*\)$", re.IGNORECASE)
FONT_CANDIDATES = (
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    "/System/Library/Fonts/Helvetica.ttc",
    "C:/Windows/Fonts/arial.ttf",
)


class CommandError(ValueError):
    """Raised for malformed turtle programs."""


def require_pillow() -> None:
    if Image is None:
        raise SystemExit("Pillow is required: pip install -r requirements.txt")


def load_font(size: int) -> "ImageFont.ImageFont":
    for candidate in FONT_CANDIDATES:
        if Path(candidate).exists():
            try:
                from PIL import ImageFont as FontModule
                return FontModule.truetype(candidate, size)
            except OSError:
                continue
    from PIL import ImageFont as FontModule
    try:
        return FontModule.load_default(size=size)
    except TypeError:
        return FontModule.load_default()


# --------------------------------------------------------------------------
# Parsing
# --------------------------------------------------------------------------
@dataclass
class Command:
    """One parsed instruction; ``block`` holds REPEAT bodies."""

    name: str
    args: list[str] = field(default_factory=list)
    block: list["Command"] | None = None
    line: int = 0


def tokenize(source: str) -> list[tuple[str, int]]:
    """Split a program into (token, line-number) pairs, dropping comments."""
    tokens: list[tuple[str, int]] = []
    for number, raw_line in enumerate(source.splitlines(), start=1):
        line = raw_line.split(";", 1)[0]
        for token in TOKEN_RE.findall(line):
            tokens.append((token, number))
    return tokens


class Parser:
    """Recursive-descent parser for the turtle command language."""

    def __init__(self, tokens: Sequence[tuple[str, int]]) -> None:
        self.tokens = list(tokens)
        self.position = 0

    def _peek(self) -> tuple[str, int] | None:
        return self.tokens[self.position] if self.position < len(self.tokens) else None

    def _next(self) -> tuple[str, int]:
        if self.position >= len(self.tokens):
            raise CommandError("unexpected end of program")
        token = self.tokens[self.position]
        self.position += 1
        return token

    def parse(self) -> list[Command]:
        commands = self._parse_sequence(stop_at_bracket=False)
        if self.position != len(self.tokens):
            token, line = self.tokens[self.position]
            raise CommandError(f"line {line}: unexpected {token!r}")
        return commands

    def _parse_sequence(self, stop_at_bracket: bool) -> list[Command]:
        commands: list[Command] = []
        while True:
            peeked = self._peek()
            if peeked is None:
                if stop_at_bracket:
                    raise CommandError("missing closing ']'")
                return commands
            token, line = peeked
            if token == "]":
                if not stop_at_bracket:
                    raise CommandError(f"line {line}: unexpected ']'")
                self.position += 1
                return commands
            if token == "[":
                raise CommandError(f"line {line}: '[' only valid after REPEAT")
            self.position += 1
            name = token.upper()
            if name == "REPEAT":
                count = self._number(f"line {line}: REPEAT needs a count")
                if self._peek() is None or self._peek()[0] != "[":
                    raise CommandError(f"line {line}: REPEAT needs a '[' block")
                self.position += 1
                body = self._parse_sequence(stop_at_bracket=True)
                if not 0 <= int(count) <= 10_000:
                    raise CommandError(f"line {line}: REPEAT count out of range (0-10000)")
                commands.append(Command(name, [count], body, line))
                continue
            arity = 0 if name in {"PU", "PENUP", "PD", "PENDOWN", "HOME"} else 1
            args: list[str] = []
            for _ in range(arity):
                if self._peek() is None or self._peek()[0] in {"]", "["}:
                    raise CommandError(f"line {line}: {name} needs an argument")
                args.append(self._next()[0])
            commands.append(Command(name, args, None, line))
        return commands

    def _number(self, message: str) -> str:
        token = self._next()[0]
        if not NUMBER_RE.match(token):
            raise CommandError(f"{message} (got {token!r})")
        return token


def parse(source: str) -> list[Command]:
    """Parse turtle source into a command tree."""
    return Parser(tokenize(source)).parse()


def parse_color(raw: str) -> str:
    """Normalise a colour name / hex / ``rgb()`` value to ``#rrggbb``."""
    lowered = raw.lower()
    if lowered in COLORS:
        return COLORS[lowered]
    match = HEX_RE.match(raw)
    if match:
        digits = match.group(1)
        if len(digits) == 3:
            digits = "".join(ch * 2 for ch in digits)
        return "#" + digits.lower()
    match = RGB_RE.match(raw)
    if match:
        channels = [int(value) for value in match.groups()]
        if any(channel > 255 for channel in channels):
            raise CommandError(f"colour channel out of range: {raw}")
        return "#" + "".join(f"{channel:02x}" for channel in channels)
    raise CommandError(f"unknown colour {raw!r} (use a name, #rrggbb or rgb(r,g,b))")


# --------------------------------------------------------------------------
# Execution
# --------------------------------------------------------------------------
@dataclass(frozen=True)
class Segment:
    """A straight pen stroke in floor coordinates."""

    x1: float
    y1: float
    x2: float
    y2: float
    color: str
    width: float


@dataclass
class Drawing:
    """The finished drawing plus final turtle state."""

    segments: list[Segment]
    start: tuple[float, float] = START
    final: tuple[float, float] = START
    heading: float = 0.0
    clipped: int = 0
    commands: int = 0
    colors: set[str] = field(default_factory=set)

    @property
    def bounds(self) -> tuple[float, float, float, float]:
        if not self.segments:
            return (self.final[0], self.final[1], self.final[0], self.final[1])
        xs = [value for seg in self.segments for value in (seg.x1, seg.x2)]
        ys = [value for seg in self.segments for value in (seg.y1, seg.y2)]
        return min(xs), min(ys), max(xs), max(ys)


class Turtle:
    """Mutable turtle state and command execution."""

    def __init__(self) -> None:
        self.x, self.y = START
        self.heading = 0.0  # degrees clockwise from north
        self.pen_down = True
        self.color = COLORS["black"]
        self.width = 3.0
        self.segments: list[Segment] = []
        self.colors: set[str] = set()
        self.clipped = 0
        self.executed = 0

    def _move(self, distance: float) -> None:
        radians = math.radians(self.heading)
        target_x = self.x + math.sin(radians) * distance
        target_y = self.y - math.cos(radians) * distance
        clamped_x = min(GRID, max(0.0, target_x))
        clamped_y = min(GRID, max(0.0, target_y))
        if (clamped_x, clamped_y) != (target_x, target_y):
            self.clipped += 1
        if self.pen_down:
            self.segments.append(Segment(self.x, self.y, clamped_x, clamped_y, self.color, self.width))
            self.colors.add(self.color)
        self.x, self.y = clamped_x, clamped_y

    def run(self, commands: Sequence[Command]) -> None:
        for command in commands:
            name = command.name
            self.executed += 1
            try:
                if name in {"FD", "FORWARD"}:
                    self._move(float(command.args[0]))
                elif name in {"BK", "BACK", "BACKWARD"}:
                    self._move(-float(command.args[0]))
                elif name in {"LT", "LEFT"}:
                    self.heading = (self.heading - float(command.args[0])) % 360
                elif name in {"RT", "RIGHT"}:
                    self.heading = (self.heading + float(command.args[0])) % 360
                elif name in {"PU", "PENUP"}:
                    self.pen_down = False
                elif name in {"PD", "PENDOWN"}:
                    self.pen_down = True
                elif name in {"COLOR", "COLOUR"}:
                    self.color = parse_color(command.args[0])
                elif name == "WIDTH":
                    value = float(command.args[0])
                    if value <= 0:
                        raise CommandError("WIDTH must be positive")
                    self.width = min(60.0, value)
                elif name == "HOME":
                    self.x, self.y = START
                    self.heading = 0.0
                elif name == "REPEAT":
                    count = int(float(command.args[0]))
                    for _ in range(max(0, count)):
                        self.run(command.block or [])
                else:
                    raise CommandError(f"unknown command {name!r}")
            except (CommandError, ValueError) as exc:
                message = str(exc)
                prefix = f"line {command.line}: "
                if not message.startswith("line "):
                    message = prefix + message
                raise CommandError(message) from exc


def execute(commands: Sequence[Command]) -> Drawing:
    """Execute a parsed program and return the resulting drawing."""
    turtle = Turtle()
    turtle.run(commands)
    return Drawing(
        segments=turtle.segments,
        final=(turtle.x, turtle.y),
        heading=turtle.heading,
        clipped=turtle.clipped,
        commands=turtle.executed,
        colors=turtle.colors,
    )


def load_program(path: Path) -> list[Command]:
    """Read and parse a command file."""
    try:
        source = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise CommandError(f"cannot read {path}: {exc}") from exc
    return parse(source)


# --------------------------------------------------------------------------
# Rendering
# --------------------------------------------------------------------------
def _scale(size: int) -> tuple[float, float]:
    margin = size * 0.07
    return margin, (size - 2 * margin) / GRID


def _turtle_arrow(final: tuple[float, float], heading: float, size: int) -> list[tuple[float, float]]:
    margin, cell = _scale(size)
    x = margin + final[0] * cell
    y = margin + final[1] * cell
    length = cell * 0.55
    width = cell * 0.32
    radians = math.radians(heading)
    dx, dy = math.sin(radians), -math.cos(radians)
    px, py = -dy, dx
    tip = (x + dx * length, y + dy * length)
    left = (x - dx * length * 0.6 + px * width, y - dy * length * 0.6 + py * width)
    right = (x - dx * length * 0.6 - px * width, y - dy * length * 0.6 - py * width)
    return [tip, left, right]


def render_png(drawing: Drawing, destination: Path, size: int = REFERENCE_SIZE, grid: bool = True) -> None:
    """Render the drawing to a PNG file with Pillow."""
    require_pillow()
    margin, cell = _scale(size)
    image = Image.new("RGB", (size, size), "#fbf8f1")
    draw = ImageDraw.Draw(image)

    if grid:
        for index in range(GRID + 1):
            coordinate = margin + index * cell
            major = index % 5 == 0
            color = "#c9c2b2" if major else "#e3ddd0"
            width = 2 if major else 1
            draw.line((margin, coordinate, size - margin, coordinate), fill=color, width=width)
            draw.line((coordinate, margin, coordinate, size - margin), fill=color, width=width)
        label_font = load_font(max(10, size // 60))
        for index in range(0, GRID + 1, 5):
            coordinate = margin + index * cell
            draw.text((coordinate, size - margin + 6), str(index), font=label_font, fill="#8b8272", anchor="ma")
            draw.text((margin - 10, coordinate), str(index), font=label_font, fill="#8b8272", anchor="rm")

    width_scale = size / REFERENCE_SIZE
    for segment in drawing.segments:
        start = (margin + segment.x1 * cell, margin + segment.y1 * cell)
        end = (margin + segment.x2 * cell, margin + segment.y2 * cell)
        stroke = max(1, round(segment.width * width_scale))
        draw.line((start, end), fill=segment.color, width=stroke)
        radius = stroke / 2
        for point in (start, end):
            draw.ellipse((point[0] - radius, point[1] - radius, point[0] + radius, point[1] + radius), fill=segment.color)

    arrow = _turtle_arrow(drawing.final, drawing.heading, size)
    draw.polygon(arrow, fill="#111827", outline="#fbf8f1")
    draw.ellipse(
        (arrow[0][0] - 3, arrow[0][1] - 3, arrow[0][0] + 3, arrow[0][1] + 3),
        fill="#fbf8f1",
    )

    title_font = load_font(max(16, size // 32))
    small_font = load_font(max(11, size // 55))
    draw.text((margin, margin * 0.45), "Turtle Graphics", font=title_font, fill="#2b2b2b", anchor="lm")
    stats = (
        f"{len(drawing.segments)} segments · {drawing.commands} commands · "
        f"{len(drawing.colors)} colours · floor {GRID}x{GRID}"
    )
    draw.text((size - margin, margin * 0.45), stats, font=small_font, fill="#7a7264", anchor="rm")
    destination.parent.mkdir(parents=True, exist_ok=True)
    image.save(destination)


def render_svg(drawing: Drawing, destination: Path, size: int = REFERENCE_SIZE, grid: bool = True) -> None:
    """Render the drawing to a standalone SVG file."""
    margin, cell = _scale(size)
    width_scale = size / REFERENCE_SIZE
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{size}" height="{size}" viewBox="0 0 {size} {size}">',
        f'<rect width="{size}" height="{size}" fill="#fbf8f1"/>',
    ]
    if grid:
        for index in range(GRID + 1):
            coordinate = margin + index * cell
            major = index % 5 == 0
            stroke = "#c9c2b2" if major else "#e3ddd0"
            stroke_width = 2 if major else 1
            parts.append(
                f'<line x1="{margin:.2f}" y1="{coordinate:.2f}" x2="{size - margin:.2f}" y2="{coordinate:.2f}" '
                f'stroke="{stroke}" stroke-width="{stroke_width}"/>'
            )
            parts.append(
                f'<line x1="{coordinate:.2f}" y1="{margin:.2f}" x2="{coordinate:.2f}" y2="{size - margin:.2f}" '
                f'stroke="{stroke}" stroke-width="{stroke_width}"/>'
            )
        for index in range(0, GRID + 1, 5):
            coordinate = margin + index * cell
            parts.append(
                f'<text x="{coordinate:.2f}" y="{size - margin + 20:.2f}" fill="#8b8272" font-size="{max(10, size // 60)}" '
                f'text-anchor="middle" font-family="sans-serif">{index}</text>'
            )
            parts.append(
                f'<text x="{margin - 10:.2f}" y="{coordinate + 4:.2f}" fill="#8b8272" font-size="{max(10, size // 60)}" '
                f'text-anchor="end" font-family="sans-serif">{index}</text>'
            )
    for segment in drawing.segments:
        x1, y1 = margin + segment.x1 * cell, margin + segment.y1 * cell
        x2, y2 = margin + segment.x2 * cell, margin + segment.y2 * cell
        parts.append(
            f'<line x1="{x1:.2f}" y1="{y1:.2f}" x2="{x2:.2f}" y2="{y2:.2f}" '
            f'stroke="{segment.color}" stroke-width="{max(1, segment.width * width_scale):.1f}" stroke-linecap="round"/>'
        )
    arrow = _turtle_arrow(drawing.final, drawing.heading, size)
    points = " ".join(f"{x:.2f},{y:.2f}" for x, y in arrow)
    parts.append(f'<polygon points="{points}" fill="#111827" stroke="#fbf8f1" stroke-width="1.5"/>')
    parts.append(
        f'<text x="{margin:.2f}" y="{margin * 0.45:.2f}" fill="#2b2b2b" font-size="{max(16, size // 32)}" '
        f'font-family="sans-serif" font-weight="bold" dominant-baseline="middle">Turtle Graphics</text>'
    )
    stats = f"{len(drawing.segments)} segments · {drawing.commands} commands · {len(drawing.colors)} colours · floor {GRID}x{GRID}"
    parts.append(
        f'<text x="{size - margin:.2f}" y="{margin * 0.45:.2f}" fill="#7a7264" font-size="{max(11, size // 55)}" '
        f'font-family="sans-serif" text-anchor="end" dominant-baseline="middle">{stats}</text>'
    )
    parts.append("</svg>")
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text("\n".join(parts) + "\n", encoding="utf-8")


DEMO_SOURCE = """\
; Turtle Graphics demo — rosette, square frame and star on a 20x20 floor
HOME
COLOR teal
WIDTH 4
REPEAT 48 [FD 0.8 RT 15]

HOME
PU
BK 8
LT 90
FD 8
RT 90
PD
COLOR #e4572e
WIDTH 3
REPEAT 4 [FD 16 RT 90]

HOME
PD
COLOR rgb(107,70,193)
WIDTH 2.5
REPEAT 5 [FD 7.5 RT 144]

HOME
PU
BK 9.2
LT 90
FD 9
RT 180
PD
COLOR gray
WIDTH 1.5
REPEAT 12 [FD 0.7 PU FD 0.8 PD]
"""


def run_demo() -> int:
    """Write a command file, execute it and render PNG + SVG."""
    require_pillow()
    workdir = Path(tempfile.mkdtemp(prefix="turtle-demo-"))
    source_path = workdir / "pattern.turtle"
    source_path.write_text(DEMO_SOURCE, encoding="utf-8")
    print("Turtle Graphics demo")
    print(f"  workspace: {workdir}")
    print(f"  commands : {source_path.name} ({len(DEMO_SOURCE.splitlines())} lines, read back from disk)")

    try:
        program = load_program(source_path)
        drawing = execute(program)
    except CommandError as exc:
        print(f"  ERROR: {exc}", file=sys.stderr)
        return 1

    png_path = workdir / "turtle.png"
    svg_path = workdir / "turtle.svg"
    render_png(drawing, png_path, size=900)
    render_svg(drawing, svg_path, size=900)
    x1, y1, x2, y2 = drawing.bounds
    print(f"  executed : {drawing.commands} commands, {len(drawing.segments)} segments, {len(drawing.colors)} colours")
    print(f"  bounds   : x {x1:.1f}..{x2:.1f}, y {y1:.1f}..{y2:.1f} (floor {GRID}x{GRID})")
    print(f"  turtle   : ({drawing.final[0]:.1f}, {drawing.final[1]:.1f}) heading {drawing.heading:.0f}°")
    print(f"  clipped  : {drawing.clipped} moves hit the floor edge")
    print(f"  PNG      : {png_path.name} ({png_path.stat().st_size / 1024:.1f} KiB)")
    print(f"  SVG      : {svg_path.name} ({svg_path.stat().st_size / 1024:.1f} KiB)")
    checks = [len(drawing.segments) > 20, png_path.stat().st_size > 5000, svg_path.stat().st_size > 1000]
    print(f"  checks   : {sum(checks)}/{len(checks)} passed")
    print("Demo complete: open turtle.png or turtle.svg.")
    return 0 if all(checks) else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Interpret turtle commands on a 20x20 floor and render PNG/SVG.",
        epilog="Commands: FD BK LT RT PU PD COLOR WIDTH HOME REPEAT n [ ... ]; ';' comments",
    )
    parser.add_argument("file", nargs="?", metavar="FILE", help="command file to execute")
    parser.add_argument("--commands", metavar="TEXT", help="commands as a single string (instead of a file)")
    parser.add_argument("--png", metavar="PATH", default="turtle.png", help="PNG output (default: turtle.png)")
    parser.add_argument("--svg", metavar="PATH", default="turtle.svg", help="SVG output (default: turtle.svg)")
    parser.add_argument("--size", type=int, default=900, help="image size in pixels (default: 900)")
    parser.add_argument("--no-grid", action="store_true", help="hide the floor grid")
    parser.add_argument("--no-png", action="store_true", help="skip PNG output")
    parser.add_argument("--no-svg", action="store_true", help="skip SVG output")
    parser.add_argument("--demo", action="store_true", help="draw a deterministic demo pattern and exit")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.demo:
        require_pillow()
        return run_demo()

    if args.size < 200 or args.size > 4000:
        parser.error("--size must be between 200 and 4000")
    if args.no_png and args.no_svg:
        parser.error("both outputs are disabled")

    source = args.commands
    if args.file:
        try:
            program = load_program(Path(args.file).expanduser())
        except CommandError as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 2
    elif source:
        try:
            # Inline snippets frequently use ';' between commands; files keep
            # ';' as the comment marker.
            program = parse(source.replace(";", "\n"))
        except CommandError as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 2
    else:
        if not sys.stdin.isatty():
            parser.error("no command file given (try --demo)")
        try:
            raw = input("Command file: ").strip().strip("'\"")
        except (EOFError, KeyboardInterrupt):
            print("\nCancelled.", file=sys.stderr)
            return 130
        if not raw:
            parser.error("no command file given")
        try:
            program = load_program(Path(raw).expanduser())
        except CommandError as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 2

    try:
        drawing = execute(program)
    except CommandError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2

    if not args.no_png:
        require_pillow()
    try:
        if not args.no_png:
            render_png(drawing, Path(args.png), args.size, not args.no_grid)
            print(f"Wrote {args.png} ({len(drawing.segments)} segments)")
        if not args.no_svg:
            render_svg(drawing, Path(args.svg), args.size, not args.no_grid)
            print(f"Wrote {args.svg}")
    except OSError as exc:
        print(f"Error writing output: {exc}", file=sys.stderr)
        return 2
    if drawing.clipped:
        print(f"warning: {drawing.clipped} move(s) hit the floor edge and were clipped", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
