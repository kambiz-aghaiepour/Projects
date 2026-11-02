#!/usr/bin/env python3
"""Complex-number algebra with one function per operation.

Implements a small immutable ``Complex`` type and separate ``add``,
``multiply``, ``negate`` and ``inverse`` functions.  Subtraction and division
are built from those primitives, as the original exercise suggests.

Examples:
    python3 solution.py --a "3+4i" --b "1-2i" --op multiply
    python3 solution.py --a "1+i" --op inverse
    python3 solution.py --a "2+3i" --op pow --exponent 3
    python3 solution.py --demo
"""

from __future__ import annotations

import argparse
import math
import sys
from dataclasses import dataclass


@dataclass(frozen=True)
class Complex:
    """An immutable complex number ``re + im*i``."""

    re: float = 0.0
    im: float = 0.0

    def __str__(self) -> str:
        return format_complex(self)


def _fmt(value: float) -> str:
    """Format a component without trailing zeros or negative zero."""

    if abs(value) < 1e-12:
        value = 0.0
    return f"{value:.10g}"


def format_complex(z: Complex) -> str:
    """Render ``z`` as ``a + bi``, ``bi`` or ``a``."""

    if z.im == 0:
        return _fmt(z.re)
    magnitude = "i" if abs(z.im) == 1 else f"{_fmt(abs(z.im))}i"
    if z.re == 0:
        return ("-" if z.im < 0 else "") + magnitude
    sign = "+" if z.im > 0 else "-"
    return f"{_fmt(z.re)} {sign} {magnitude}"


def add(a: Complex, b: Complex) -> Complex:
    """Return ``a + b``."""

    return Complex(a.re + b.re, a.im + b.im)


def negate(z: Complex) -> Complex:
    """Return ``-z``."""

    return Complex(-z.re, -z.im)


def subtract(a: Complex, b: Complex) -> Complex:
    """Return ``a - b`` as ``a + (-b)``."""

    return add(a, negate(b))


def multiply(a: Complex, b: Complex) -> Complex:
    """Return ``a * b`` using (ac - bd) + (ad + bc)i."""

    return Complex(a.re * b.re - a.im * b.im, a.re * b.im + a.im * b.re)


def inverse(z: Complex) -> Complex:
    """Return ``1 / z``; raises ZeroDivisionError for zero."""

    denominator = z.re * z.re + z.im * z.im
    if denominator == 0:
        raise ZeroDivisionError("cannot invert zero")
    return Complex(z.re / denominator, -z.im / denominator)


def divide(a: Complex, b: Complex) -> Complex:
    """Return ``a / b`` as ``a * inverse(b)``."""

    return multiply(a, inverse(b))


def conjugate(z: Complex) -> Complex:
    """Return the complex conjugate."""

    return Complex(z.re, -z.im)


def magnitude(z: Complex) -> float:
    """Return ``|z|``."""

    return math.hypot(z.re, z.im)


def argument(z: Complex) -> float:
    """Return the argument of ``z`` in radians."""

    return math.atan2(z.im, z.re)


def power(z: Complex, exponent: int) -> Complex:
    """Raise ``z`` to an integer power by repeated squaring."""

    if exponent < 0:
        return inverse(power(z, -exponent))
    result = Complex(1.0, 0.0)
    base = z
    remaining = exponent
    while remaining:
        if remaining & 1:
            result = multiply(result, base)
        remaining >>= 1
        if remaining:
            base = multiply(base, base)
    return result


def parse_complex(text: str) -> Complex:
    """Parse ``3+4i``, ``3-4i``, ``-2i``, ``i``, ``5`` or ``1.5e2+3j``."""

    cleaned = text.strip().lower().replace(" ", "").replace("−", "-")
    if not cleaned:
        raise ValueError("empty complex number")
    if cleaned in {"i", "j", "+i", "+j"}:
        return Complex(0.0, 1.0)
    if cleaned in {"-i", "-j"}:
        return Complex(0.0, -1.0)
    if not cleaned.endswith(("i", "j")):
        try:
            return Complex(float(cleaned), 0.0)
        except ValueError as exc:
            raise ValueError(f"invalid complex number {text!r}") from exc

    body = cleaned[:-1]
    split = _split_real_imaginary(body)
    if split > 0:
        real_text, imag_text = body[:split], body[split:]
    else:
        real_text, imag_text = "0", body

    if imag_text in ("", "+"):
        imag = 1.0
    elif imag_text == "-":
        imag = -1.0
    else:
        try:
            imag = float(imag_text)
        except ValueError as exc:
            raise ValueError(f"invalid imaginary part in {text!r}") from exc
    try:
        real = float(real_text)
    except ValueError as exc:
        raise ValueError(f"invalid real part in {text!r}") from exc
    return Complex(real, imag)


def _split_real_imaginary(body: str) -> int:
    """Find the +/- separating real and imaginary parts, ignoring exponents."""

    for index in range(len(body) - 1, 0, -1):
        if body[index] in "+-" and body[index - 1] not in "eE":
            return index
    return -1


def apply_operation(name: str, a: Complex, b: Complex | None,
                    exponent: int) -> Complex:
    """Dispatch a named operation, validating required operands."""

    if name == "add":
        return add(a, _require(b, name))
    if name == "subtract":
        return subtract(a, _require(b, name))
    if name == "multiply":
        return multiply(a, _require(b, name))
    if name == "divide":
        return divide(a, _require(b, name))
    if name == "negate":
        return negate(a)
    if name == "inverse":
        return inverse(a)
    if name == "conjugate":
        return conjugate(a)
    if name == "pow":
        return power(a, exponent)
    raise ValueError(f"unknown operation {name!r}")


def _require(value: Complex | None, operation: str) -> Complex:
    if value is None:
        raise ValueError(f"operation {operation!r} needs a second operand (--b)")
    return value


def run_demo() -> int:
    """Print results for every operation plus algebraic identities."""

    z1 = Complex(3.0, 4.0)
    z2 = Complex(1.0, -2.0)
    print("Complex Number Algebra demo")
    print("=" * 54)
    print(f"z1 = {z1}")
    print(f"z2 = {z2}\n")

    print(f"add(z1, z2)       = {add(z1, z2)}")
    print(f"multiply(z1, z2)  = {multiply(z1, z2)}")
    print(f"negate(z1)        = {negate(z1)}")
    print(f"inverse(z1)       = {inverse(z1)}")
    print(f"subtract(z1, z2)  = {subtract(z1, z2)}")
    print(f"divide(z1, z2)    = {divide(z1, z2)}")
    print(f"conjugate(z1)     = {conjugate(z1)}")
    print(f"|z1|              = {magnitude(z1):.6f}")
    print(f"arg(z1)           = {argument(z1):.6f} rad")
    print(f"z1^3              = {power(z1, 3)}")

    print("\nIdentities:")
    print(f"  z1 + (-z1)      = {add(z1, negate(z1))}")
    print(f"  z1 * inverse(z1)= {multiply(z1, inverse(z1))}")
    print(f"  divide(z1, z1)  = {divide(z1, z1)}")

    print("\nParsing:")
    for text in ("3+4i", "1-2i", "-2i", "i", "5", "1.5e2+3j"):
        print(f"  {text!r:12} -> {parse_complex(text)}")

    print("\nCheck: (3+4i)(1-2i) expanded = 11 - 2i, "
          f"program says {multiply(z1, z2)}.")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Add, multiply, negate and invert complex numbers.",
        epilog="Numbers use i or j notation, e.g. '3+4i' or '-2.5j'.",
    )
    parser.add_argument("--a", metavar="COMPLEX", help="first operand, e.g. 3+4i")
    parser.add_argument("--b", metavar="COMPLEX", help="second operand, e.g. 1-2i")
    parser.add_argument("--op", choices=("add", "subtract", "multiply", "divide",
                                         "negate", "inverse", "conjugate", "pow"),
                        default="add", help="operation to perform (default: add)")
    parser.add_argument("--exponent", type=int, default=2,
                        help="integer exponent for --op pow (default: 2)")
    parser.add_argument("--demo", action="store_true", help="run a scripted demonstration")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.demo:
        return run_demo()

    a_text, b_text = args.a, args.b
    if not a_text:
        try:
            a_text = input("First complex number (e.g. 3+4i): ")
        except (EOFError, KeyboardInterrupt):
            print("\nCancelled.")
            return 0
    try:
        a = parse_complex(a_text)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    if args.op in {"add", "subtract", "multiply", "divide"} and not b_text:
        try:
            b_text = input("Second complex number (e.g. 1-2i): ")
        except (EOFError, KeyboardInterrupt):
            print("\nCancelled.")
            return 0

    try:
        b = parse_complex(b_text) if b_text else None
        result = apply_operation(args.op, a, b, args.exponent)
    except (ValueError, ZeroDivisionError, OverflowError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    expression = f"{args.op}({a}" + (f", {b}" if b is not None else "") + ")"
    print(f"{expression} = {result}")
    if args.op == "pow":
        print(f"exponent: {args.exponent}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
