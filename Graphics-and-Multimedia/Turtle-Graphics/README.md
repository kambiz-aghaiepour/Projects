# Turtle Graphics

**Category:** Graphics-and-Multimedia · **Project:** Turtle-Graphics

## Problem

> Create a floor of 20 x 20 squares. Using various commands you tell a turtle
> to draw a line on the floor. You can move forward, left or right, lift or
> drop pen etc. Optional: read commands from a file.

## Features

- A command interpreter on a **20 × 20 grid**: `FD`, `BK`, `LT`, `RT`, `PU`,
  `PD`, `COLOR`, `WIDTH`, `HOME` and `REPEAT n [ … ]`, with nested repeats.
- Colours as names (`teal`, `orange`, …), `#rrggbb` / `#rgb`, or
  `rgb(r,g,b)`; pen widths from hairline to 60 px.
- Reads commands from a file (`;` starts a comment) or from `--commands`.
- Renders the floor to **PNG** (Pillow) and **SVG** (standalone vector file),
  both with optional grid, coordinate labels, the turtle arrow and a stats
  header.
- Turtle position is continuous in grid units but clamped to the floor; the
  number of edge hits is reported instead of crashing.
- Clear parse/execution errors with line numbers, e.g. unknown colour or a
  missing `]`.
- Deterministic `--demo` writes its command file, reads it back, executes it
  and renders both formats.

## Requirements

Python 3.10+ and Pillow:

```bash
pip install -r requirements.txt
```

SVG output has no dependencies; Pillow is only needed for PNG.

## Usage

```bash
# Scripted demo: writes pattern.turtle, then turtle.png and turtle.svg
python3 solution.py --demo

# Run a command file and choose output paths
python3 solution.py pattern.turtle --png out/pattern.png --svg out/pattern.svg

# Inline commands, larger canvas, no grid
python3 solution.py --commands "HOME; REPEAT 36 [FD 2 RT 10]" \
    --size 1200 --no-grid --png spiral.png

# SVG only
python3 solution.py pattern.turtle --no-png --svg pattern.svg
```

| Option | Meaning |
| --- | --- |
| `FILE` / `--commands` | Command source (file, or inline text) |
| `--png PATH` | PNG output (default `turtle.png`) |
| `--svg PATH` | SVG output (default `turtle.svg`) |
| `--size N` | Image size in pixels, 200–4000 (default `900`) |
| `--no-grid` | Hide the floor grid and labels |
| `--no-png` / `--no-svg` | Skip one format |
| `--demo` | Draw the built-in pattern |

### Command reference

| Command | Effect |
| --- | --- |
| `FD n` / `BK n` | Move forward/backward `n` grid units (draws if pen is down) |
| `LT deg` / `RT deg` | Turn left/right by degrees (heading starts north) |
| `PU` / `PD` | Lift / drop the pen |
| `COLOR c` | Set stroke colour |
| `WIDTH n` | Set stroke width in pixels at 900 px reference size |
| `HOME` | Return to `(10, 10)` facing north without drawing |
| `REPEAT n [ … ]` | Repeat the bracketed commands `n` times (nestable, max 10000) |

## Example Output

```text
Turtle Graphics demo
  commands : pattern.turtle (33 lines, read back from disk)
  executed : 191 commands, 69 segments, 4 colours
  bounds   : x 1.0..18.2, y 2.0..19.2 (floor 20x20)
  turtle   : (19.0, 19.2) heading 90°
  clipped  : 0 moves hit the floor edge
  PNG      : turtle.png (22.4 KiB)
  SVG      : turtle.svg (13.1 KiB)
  checks   : 3/3 passed
Demo complete: open turtle.png or turtle.svg.
```

## Implementation Notes

- **Parsing** is a small recursive-descent parser over a tokenizer that keeps
  line numbers. `REPEAT` consumes a numeric count and a `[ … ]` block; nested
  repeats are represented as a command tree. The parser rejects stray brackets
  and missing arguments before anything is drawn.
- **Execution** keeps turtle state (`x`, `y`, heading, pen, colour, width) and
  appends immutable `Segment` records. Heading is degrees clockwise from north:
  `dx = sin(θ)`, `dy = -cos(θ)` in screen coordinates. Every move is clamped to
  `[0, 20]` and a clipped-move counter is incremented.
- **Rendering** uses one shared mapping from floor units to pixels, so PNG and
  SVG are geometrically identical. Lines are stroked with round caps (circles
  at segment ends in PNG, `stroke-linecap="round"` in SVG) to hide joints.
- Execution cost is `O(commands × repeat counts)`; rendering is linear in the
  number of segments. The demo draws 69 segments in milliseconds.
- Limitations: no arcs/circles, no text or flood fill, and no undo. The floor is
  fixed at 20 × 20 by the problem statement, and `HOME` never draws.
