#!/usr/bin/env python3
"""A safe scientific calculator built on Python's AST.

The expression engine lives in :mod:`calc_engine`; this module provides the
command line interface and interactive REPL.  Supported operations include
basic arithmetic, powers, trigonometry, logarithms, factorial and constants
pi/e/tau, with optional degree-mode trigonometry.
"""

from __future__ import annotations

import argparse
import sys

from calc_engine import (
    CONSTANTS,
    FUNCTIONS,
    CalculatorError,
    evaluate,
    format_result,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Evaluate scientific calculator expressions safely.",
        epilog="Run with no arguments for an interactive calculator.",
    )
    parser.add_argument(
        "-e",
        "--expr",
        action="append",
        metavar="EXPR",
        help="expression to evaluate (repeatable)",
    )
    parser.add_argument(
        "--degrees",
        action="store_true",
        help="use degrees for sin/cos/tan and asin/acos/atan",
    )
    parser.add_argument("--demo", action="store_true", help="run scripted examples")
    return parser


def run_demo() -> int:
    """Evaluate deterministic arithmetic and scientific examples."""
    print("Scientific calculator demo")
    print("=" * 25)

    expressions = [
        "2 + 3 * 4",
        "(1 + 2) ^ 3",
        "sqrt(2)",
        "log(1000, 10)",
        "factorial(5)",
        "pi * 2^2",
        "hypot(3, 4)",
        "round(pi, 4)",
        "2 ** 10",
    ]
    for expression in expressions:
        print(f"  {expression:<20} = {format_result(evaluate(expression))}")

    print("\nDegree mode (trig arguments and inverse-trig results in degrees):")
    for expression in ("sin(30)", "cos(60)", "atan(1)"):
        print(
            f"  {expression:<20} = "
            f"{format_result(evaluate(expression, degrees=True))}"
        )

    print("\nRejected inputs:")
    for bad in ("1 / 0", "__import__('os').getcwd()", "open('x')"):
        try:
            evaluate(bad)
        except CalculatorError as exc:
            print(f"  {bad:<20} -> error: {exc}")
    return 0


def repl(degrees: bool) -> int:
    """Interactive expression loop."""
    print("Scientific calculator. Type 'help' for commands, 'quit' to exit.")
    while True:
        try:
            line = input("calc> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return 0
        if not line:
            continue
        if line.lower() in {"quit", "exit", "q"}:
            return 0
        if line.lower() in {"help", "?"}:
            print("Operators: + - * / // % ** (or ^), parentheses.")
            print("Functions: " + ", ".join(sorted(FUNCTIONS)))
            print("Constants: " + ", ".join(sorted(CONSTANTS)))
            continue
        try:
            print(format_result(evaluate(line, degrees=degrees)))
        except CalculatorError as exc:
            print(f"Error: {exc}")


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.demo:
        return run_demo()
    if args.expr:
        status = 0
        for expression in args.expr:
            try:
                print(format_result(evaluate(expression, degrees=args.degrees)))
            except CalculatorError as exc:
                print(f"Error: {exc}", file=sys.stderr)
                status = 2
        return status
    return repl(args.degrees)


if __name__ == "__main__":
    raise SystemExit(main())
