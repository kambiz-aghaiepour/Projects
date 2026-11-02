#!/usr/bin/env python3
"""Estimate one-sided or two-sided limits of f(x) numerically.

Expressions are parsed with :mod:`ast` and evaluated only through a small
whitelist of arithmetic operations and math functions, so no untrusted code
runs.  The limit is estimated by sampling values closer and closer to the
target point and extrapolating the trend; infinite limits and non-existent
(jumping or oscillating) limits are reported as such.

Examples:
    python3 solution.py "sin(x)/x" --at 0
    python3 solution.py "(x**2 - 1)/(x - 1)" --at 1 --dir right
    python3 solution.py "1/x" --at 0 --samples
    python3 solution.py "(1 + 1/x)**x" --at inf
    python3 solution.py --demo
"""

from __future__ import annotations

import argparse
import ast
import math
import operator
import re
import sys
from collections.abc import Callable
from dataclasses import dataclass

BINOPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Pow: operator.pow,
    ast.Mod: operator.mod,
}

FUNCTIONS = {
    "sin": math.sin, "cos": math.cos, "tan": math.tan,
    "asin": math.asin, "acos": math.acos, "atan": math.atan,
    "sinh": math.sinh, "cosh": math.cosh, "tanh": math.tanh,
    "exp": math.exp, "log": math.log, "ln": math.log, "log10": math.log10,
    "log2": math.log2, "sqrt": math.sqrt, "cbrt": lambda v: math.copysign(abs(v) ** (1 / 3), v),
    "abs": abs, "floor": math.floor, "ceil": math.ceil,
}
CONSTANTS = {"pi": math.pi, "e": math.e, "tau": math.tau}


@dataclass
class SideLimit:
    """Result of approaching the point from one side."""

    kind: str                  # finite, inf, -inf, dne, undefined
    value: float | None = None
    note: str = ""


@dataclass
class LimitResult:
    """Combined limit and the two one-sided estimates."""

    expression: str
    point_text: str
    left: SideLimit | None
    right: SideLimit | None
    at_infinity: SideLimit | None
    kind: str
    value: float | None
    note: str = ""


def validate_node(node: ast.AST) -> None:
    """Reject anything outside the numeric expression whitelist."""

    if isinstance(node, ast.Expression):
        validate_node(node.body)
    elif isinstance(node, ast.Constant):
        if isinstance(node.value, bool) or not isinstance(node.value, (int, float)):
            raise ValueError("only numeric constants are allowed")
    elif isinstance(node, ast.Name):
        if node.id != "x" and node.id not in CONSTANTS:
            raise ValueError(f"unknown name {node.id!r}; only x and constants are allowed")
    elif isinstance(node, ast.BinOp):
        if type(node.op) not in BINOPS:
            raise ValueError(f"operator {type(node.op).__name__} is not allowed")
        validate_node(node.left)
        validate_node(node.right)
    elif isinstance(node, ast.UnaryOp):
        if not isinstance(node.op, (ast.UAdd, ast.USub)):
            raise ValueError("only unary + and - are allowed")
        validate_node(node.operand)
    elif isinstance(node, ast.Call):
        if not isinstance(node.func, ast.Name) or node.func.id not in FUNCTIONS:
            raise ValueError("only basic math functions are allowed")
        if len(node.args) != 1 or node.keywords:
            raise ValueError(f"{node.func.id}() takes exactly one argument")
        validate_node(node.args[0])
    else:
        raise ValueError(f"unsupported syntax: {type(node).__name__}")


def compile_expression(text: str) -> Callable[[float], float]:
    """Parse and validate ``text``; return a callable ``f(x)``."""

    cleaned = text.strip()
    if not cleaned:
        raise ValueError("expression is empty")
    cleaned = cleaned.replace("^", "**").replace("−", "-").replace("×", "*").replace("÷", "/")
    cleaned = re.sub(r"^\s*(?:f\s*\(\s*x\s*\)|y)\s*=\s*", "", cleaned, flags=re.IGNORECASE).strip()
    try:
        tree = ast.parse(cleaned, mode="eval")
    except SyntaxError as exc:
        raise ValueError(f"could not parse expression: {exc.msg}") from exc
    validate_node(tree)

    def evaluate(x: float) -> float:
        return _eval(tree.body, x)

    return evaluate


def _eval(node: ast.AST, x: float) -> float:
    """Evaluate a validated AST at ``x``."""

    if isinstance(node, ast.Constant):
        return float(node.value)
    if isinstance(node, ast.Name):
        return x if node.id == "x" else CONSTANTS[node.id]
    if isinstance(node, ast.BinOp):
        left, right = _eval(node.left, x), _eval(node.right, x)
        result = BINOPS[type(node.op)](left, right)
        if isinstance(result, complex):
            raise ValueError("expression produced a complex value")
        return float(result)
    if isinstance(node, ast.UnaryOp):
        value = _eval(node.operand, x)
        return -value if isinstance(node.op, ast.USub) else value
    if isinstance(node, ast.Call):
        function = FUNCTIONS[node.func.id]  # type: ignore[union-attr]
        return float(function(_eval(node.args[0], x)))
    raise ValueError("unsupported expression")


def parse_point(text: str) -> float:
    """Parse a target point, including ``inf`` and ``-inf``."""

    cleaned = text.strip().lower()
    if cleaned in {"inf", "+inf", "infinity", "+infinity"}:
        return math.inf
    if cleaned in {"-inf", "-infinity"}:
        return -math.inf
    if cleaned in CONSTANTS:
        return CONSTANTS[cleaned]
    try:
        return float(cleaned)
    except ValueError as exc:
        raise ValueError(f"invalid limit point {text!r}") from exc


def sample_finite(f: Callable[[float], float], point: float, side: int,
                  lowest_power: int = 5) -> tuple[list[tuple[float, float]], int]:
    """Sample ``f(point + side*h)`` for h = 1e-2 ... 1e-<lowest_power>."""

    samples: list[tuple[float, float]] = []
    failures = 0
    for power in range(2, lowest_power + 1):
        h = 10.0 ** -power
        try:
            value = f(point + side * h)
        except (ZeroDivisionError, ValueError, OverflowError):
            failures += 1
            continue
        if math.isfinite(value) or math.isinf(value):
            samples.append((h, float(value)))
    return samples, failures


def sample_infinity(f: Callable[[float], float], sign: int,
                    highest_power: int = 8) -> tuple[list[tuple[float, float]], int]:
    """Sample ``f(sign * 10**k)`` and express the distance as h = 10**-k."""

    samples: list[tuple[float, float]] = []
    failures = 0
    for power in range(1, highest_power + 1):
        h = 10.0 ** -power
        try:
            value = f(sign / h)
        except (ZeroDivisionError, ValueError, OverflowError):
            failures += 1
            continue
        if math.isfinite(value) or math.isinf(value):
            samples.append((h, float(value)))
    return samples, failures


def classify(samples: list[tuple[float, float]], failures: int = 0) -> SideLimit:
    """Classify a sample sequence as finite, infinite, or non-existent."""

    if not samples:
        return SideLimit("undefined", note="no real values near the point")

    finite = [(h, value) for h, value in samples if math.isfinite(value)]
    if len(finite) < 3:
        if finite and abs(finite[-1][1]) > 1e6:
            return SideLimit("inf" if finite[-1][1] > 0 else "-inf",
                             note="values grow without bound")
        if failures >= 2 and finite:
            return SideLimit("inf" if finite[-1][1] > 0 else "-inf",
                             note="values overflow before the point")
        return SideLimit("dne", note="too few finite samples to estimate")

    last = finite[-5:]
    values = [value for _, value in last]
    scale = max(1.0, max(abs(value) for value in values))
    diffs = [values[index + 1] - values[index] for index in range(len(values) - 1)]

    if all(abs(diff) <= 1e-9 * scale for diff in diffs[-2:]):
        return SideLimit("finite", values[-1])

    nondecreasing = all(diff >= 0 for diff in diffs)
    nonincreasing = all(diff <= 0 for diff in diffs)
    if not (nondecreasing or nonincreasing):
        if max(values) - min(values) <= 1e-6 * scale:
            return SideLimit("finite", sum(values[-3:]) / 3)
        return SideLimit("dne", note="values oscillate")

    if len(last) < 3:
        return SideLimit("dne", note="not enough samples")

    (h1, v1), (h2, v2), (h3, v3) = last[-3], last[-2], last[-1]
    d1, d2 = v1 - v2, v2 - v3
    if d2 == 0:
        return SideLimit("finite", v3)
    ratio = d1 / d2
    if ratio <= 0:
        return SideLimit("dne", note="values do not settle")
    try:
        power = math.log(ratio) / math.log(h1 / h2)
    except (ValueError, ZeroDivisionError):
        return SideLimit("dne")

    if power < -0.35:
        return SideLimit("inf" if v3 > 0 else "-inf", note="values grow without bound")
    if abs(power) < 0.08:
        if abs(v3) > 4 and abs(d2) > 1e-9 * scale:
            return SideLimit("inf" if v3 > 0 else "-inf", note="slow logarithmic divergence")
        return SideLimit("finite", v3)
    if power > 15:
        return SideLimit("dne", note="values change too erratically")

    q = (h2 / h3) ** power - 1
    if q <= 0:
        return SideLimit("dne")
    extrapolated = v3 - d2 / q
    if not math.isfinite(extrapolated) or abs(extrapolated - v3) > 10 * scale:
        return SideLimit("dne", note="extrapolation is unstable")

    if len(last) >= 4:
        h4, v4 = last[-4]
        predicted = extrapolated + (d2 / q) * ((h4 / h3) ** power)
        if abs(predicted - v4) > 1e-3 * max(1.0, abs(v4)):
            return SideLimit("dne", note="extrapolation does not fit the sample trend")

    return SideLimit("finite", extrapolated)


def _close(a: float, b: float) -> bool:
    return abs(a - b) <= 1e-5 * max(1.0, abs(a), abs(b))


def combine(left: SideLimit, right: SideLimit) -> tuple[str, float | None, str]:
    """Combine one-sided estimates into a two-sided verdict."""

    if left.kind == "undefined" and right.kind == "undefined":
        return "undefined", None, "function is not defined near the point"
    if left.kind == "undefined":
        return right.kind, right.value, "left-hand side is outside the domain"
    if right.kind == "undefined":
        return left.kind, left.value, "right-hand side is outside the domain"

    if left.kind == "finite" and right.kind == "finite":
        if _close(left.value, right.value):
            return "finite", (left.value + right.value) / 2, ""
        return "dne", None, "left and right limits differ (jump)"
    if left.kind == right.kind and left.kind in {"inf", "-inf"}:
        return left.kind, None, ""
    if left.kind in {"inf", "-inf"} and right.kind in {"inf", "-inf"}:
        return "dne", None, "left and right limits are infinite with opposite signs"
    if left.kind == "dne" or right.kind == "dne":
        return "dne", None, "one or both sides do not settle"
    if left.kind in {"inf", "-inf"} or right.kind in {"inf", "-inf"}:
        return "dne", None, "one side is infinite and the other is finite"
    return "dne", None, "left and right behaviour disagree"


def evaluate_limit(expression: str, point_text: str, direction: str = "both") -> LimitResult:
    """Estimate the requested limit."""

    f = compile_expression(expression)
    point = parse_point(point_text)

    if math.isinf(point):
        sign = 1 if point > 0 else -1
        samples, failures = sample_infinity(f, sign)
        side = classify(samples, failures)
        note = side.note
        return LimitResult(expression, point_text, None, None, side, side.kind, side.value, note)

    left = right = None
    if direction in ("both", "left"):
        samples, failures = sample_finite(f, point, -1)
        left = classify(samples, failures)
    if direction in ("both", "right"):
        samples, failures = sample_finite(f, point, +1)
        right = classify(samples, failures)

    if direction == "left":
        assert left is not None
        return LimitResult(expression, point_text, left, None, None,
                           left.kind, left.value, "left-hand limit" if not left.note else left.note)
    if direction == "right":
        assert right is not None
        return LimitResult(expression, point_text, None, right, None,
                           right.kind, right.value, "right-hand limit" if not right.note else right.note)

    assert left is not None and right is not None
    kind, value, note = combine(left, right)
    return LimitResult(expression, point_text, left, right, None, kind, value, note)


def format_side(side: SideLimit) -> str:
    """Render one side's verdict."""

    if side.kind == "finite":
        value = 0.0 if abs(side.value or 0.0) < 1e-12 else (side.value or 0.0)
        return f"{value:.8g}"
    if side.kind == "inf":
        return "infinity"
    if side.kind == "-inf":
        return "-infinity"
    if side.kind == "undefined":
        return "undefined (outside domain)"
    return "does not exist"


def format_limit(kind: str, value: float | None) -> str:
    """Render the combined limit."""

    if kind == "finite":
        value = 0.0 if abs(value or 0.0) < 1e-12 else (value or 0.0)
        return f"{value:.8g}"
    if kind == "inf":
        return "infinity"
    if kind == "-inf":
        return "-infinity"
    if kind == "undefined":
        return "undefined"
    return "does not exist"


def print_samples(f: Callable[[float], float], point: float, direction: str) -> None:
    """Print the raw sampling table for a finite point."""

    print("  h          left f(x)            right f(x)")
    for power in range(2, 6):
        h = 10.0 ** -power
        left_text = right_text = "-"
        if direction in ("both", "left"):
            try:
                left_text = f"{f(point - h):.12g}"
            except (ZeroDivisionError, ValueError, OverflowError):
                left_text = "undefined"
        if direction in ("both", "right"):
            try:
                right_text = f"{f(point + h):.12g}"
            except (ZeroDivisionError, ValueError, OverflowError):
                right_text = "undefined"
        print(f"  {h:.0e}   {left_text:<20} {right_text}")


def print_result(result: LimitResult, show_samples: bool = False) -> None:
    """Print a compact result and, optionally, the sampling table."""

    label = result.expression
    if re.match(r"^\s*(?:f\s*\(\s*x\s*\)|y)\s*=", label, re.IGNORECASE):
        print(label)
    else:
        print(f"f(x) = {label}")
    print(f"limit as x -> {result.point_text}:")
    if result.left is not None:
        print(f"  left-hand:  {format_side(result.left)}")
    if result.right is not None:
        print(f"  right-hand: {format_side(result.right)}")
    if result.at_infinity is not None:
        print(f"  behaviour:  {format_side(result.at_infinity)}")
    print(f"  limit:      {format_limit(result.kind, result.value)}")
    if result.note:
        print(f"  note:       {result.note}")
    if show_samples and result.at_infinity is None:
        f = compile_expression(result.expression)
        point = parse_point(result.point_text)
        print_samples(f, point, "both" if result.left and result.right else
                      ("left" if result.left else "right"))


def run_demo() -> int:
    """Evaluate a collection of standard limits."""

    print("Limit Calculator demo")
    print("=" * 62)
    cases = [
        ("(x**2 - 1)/(x - 1)", "1", "both"),
        ("sin(x)/x", "0", "both"),
        ("1/x", "0", "both"),
        ("1/x**2", "0", "both"),
        ("(1 + 1/x)**x", "inf", "both"),
        ("(x**2 + 3*x)/(2*x**2 - x)", "inf", "both"),
        ("sqrt(x)", "0", "both"),
        ("abs(x)/x", "0", "both"),
        ("sin(x)", "inf", "both"),
    ]
    for expression, point, direction in cases:
        result = evaluate_limit(expression, point, direction)
        print(f"  {expression:<28} at {point:<4} -> {format_limit(result.kind, result.value)}")

    print("\nDetails for 1/x as x -> 0:")
    detail = evaluate_limit("1/x", "0", "both")
    print(f"  left-hand  = {format_side(detail.left)}")
    print(f"  right-hand = {format_side(detail.right)}")
    print(f"  conclusion = {format_limit(detail.kind, detail.value)} ({detail.note})")

    print("\nDetails for sqrt(x) as x -> 0:")
    root = evaluate_limit("sqrt(x)", "0", "both")
    print(f"  right-hand = {format_side(root.right)}")
    print(f"  conclusion = {format_limit(root.kind, root.value)} ({root.note})")

    print("\nLimit at infinity for (1 + 1/x)**x:")
    e_limit = evaluate_limit("(1 + 1/x)**x", "inf")
    print(f"  estimate = {format_limit(e_limit.kind, e_limit.value)} "
          f"(e = {math.e:.10g})")

    print("\nOne-sided example, (x**2 - 1)/(x - 1) as x -> 1 from the right:")
    print(f"  limit = {format_limit(*_kind_value(evaluate_limit('(x**2 - 1)/(x - 1)', '1', 'right')))}")
    return 0


def _kind_value(result: LimitResult) -> tuple[str, float | None]:
    return result.kind, result.value


def _normalise_argv(argv: list[str] | None) -> list[str]:
    """Allow ``--at -inf`` / ``--at -2`` by binding negative values to the option."""

    tokens = list(sys.argv[1:] if argv is None else argv)
    index = 0
    while index < len(tokens) - 1:
        token, following = tokens[index], tokens[index + 1]
        if token == "--at" and re.fullmatch(r"-(?:inf(?:inity)?|\d+(?:\.\d+)?)", following,
                                            re.IGNORECASE):
            tokens[index:index + 2] = [f"--at={following}"]
            continue
        index += 1
    return tokens


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Estimate limits of f(x) numerically, including infinite limits.",
        epilog="Use ** or ^ for powers. Example: solution.py 'sin(x)/x' --at 0",
    )
    parser.add_argument("expression", nargs="?", help="function of x, e.g. 'sin(x)/x'")
    parser.add_argument("-e", "--expr", dest="expression_option", metavar="EXPR",
                        help="function of x (use this when it starts with '-')")
    parser.add_argument("--at", default="0", metavar="POINT",
                        help="limit point: number, inf or -inf (default: 0)")
    parser.add_argument("--dir", choices=("both", "left", "right"), default="both",
                        help="which side(s) to approach from (default: both)")
    parser.add_argument("--samples", action="store_true",
                        help="show the numeric sampling table")
    parser.add_argument("--demo", action="store_true", help="run a scripted demonstration")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(_normalise_argv(argv))

    if args.demo:
        return run_demo()

    expression = args.expression or args.expression_option
    if not expression:
        try:
            expression = input("f(x) = ")
            point = input("limit as x -> [0]: ").strip() or "0"
        except (EOFError, KeyboardInterrupt):
            print("\nCancelled.")
            return 0
        args.at = point

    try:
        result = evaluate_limit(expression, args.at, args.dir)
    except (ValueError, ZeroDivisionError, OverflowError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print_result(result, show_samples=args.samples)
    return 0


if __name__ == "__main__":
    sys.exit(main())
