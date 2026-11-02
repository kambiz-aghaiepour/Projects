#!/usr/bin/env python3
"""Fizz Buzz with a configurable range and custom rules.

The classic exercise prints 1..100, replacing multiples of 3 with "Fizz",
multiples of 5 with "Buzz", and multiples of both with "FizzBuzz".  This
version keeps that default but lets you change the range and define any
number of divisor/label rules (for example 7:Pop or 2:Even).
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence

DEFAULT_START = 1
DEFAULT_END = 100


@dataclass(frozen=True)
class Rule:
    """A divisor and the word printed for its multiples."""

    divisor: int
    label: str


DEFAULT_RULES: tuple[Rule, ...] = (Rule(3, "Fizz"), Rule(5, "Buzz"))


def parse_rule(raw: str) -> Rule:
    """Parse a ``DIVISOR:LABEL`` command-line rule.

    Raises:
        argparse.ArgumentTypeError: if the divisor is not a positive integer
            or the label is empty.
    """
    divisor_text, sep, label = raw.partition(":")
    if not sep:
        raise argparse.ArgumentTypeError(
            f"invalid rule {raw!r}; expected DIVISOR:LABEL (e.g. 7:Pop)"
        )
    try:
        divisor = int(divisor_text)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            f"invalid divisor in rule {raw!r}; expected an integer"
        ) from exc
    if divisor <= 0:
        raise argparse.ArgumentTypeError("rule divisors must be positive integers")
    label = label.strip()
    if not label:
        raise argparse.ArgumentTypeError(f"rule {raw!r} has an empty label")
    return Rule(divisor, label)


def build_rules(raw_rules: Sequence[str] | None) -> list[Rule]:
    """Return the rules to use, rejecting duplicate divisors."""
    rules = [parse_rule(raw) for raw in raw_rules] if raw_rules else list(DEFAULT_RULES)
    seen: set[int] = set()
    for rule in rules:
        if rule.divisor in seen:
            raise ValueError(f"duplicate rule for divisor {rule.divisor}")
        seen.add(rule.divisor)
    return rules


def fizz_buzz_value(number: int, rules: Iterable[Rule]) -> str:
    """Return the Fizz Buzz word(s) for ``number``, or the number as text."""
    label = "".join(rule.label for rule in rules if number % rule.divisor == 0)
    return label or str(number)


def generate(start: int, end: int, rules: Sequence[Rule]) -> list[str]:
    """Generate one output line per integer in the inclusive range."""
    return [fizz_buzz_value(number, rules) for number in range(start, end + 1)]


def run(start: int, end: int, rules: Sequence[Rule], separator: str) -> str:
    """Render the sequence as a single string."""
    return separator.join(generate(start, end, rules))


def demo() -> int:
    """Show the standard sequence and a custom three-rule sequence."""
    print("Standard rules (Fizz=3, Buzz=5), 1 to 20:")
    print(" ".join(generate(1, 20, DEFAULT_RULES)))

    custom = [Rule(3, "Fizz"), Rule(5, "Buzz"), Rule(7, "Pop")]
    print("\nCustom rules (3:Fizz, 5:Buzz, 7:Pop), 1 to 21:")
    print(" ".join(generate(1, 21, custom)))

    print("\nRule spot checks:")
    for number in (15, 21, 35):
        print(f"  {number:>3} -> {fizz_buzz_value(number, custom)}")
    return 0


def interactive_range() -> tuple[int, int]:
    """Prompt for a range, using the classic defaults on empty input."""
    start_text = input(f"Start [{DEFAULT_START}]: ").strip()
    end_text = input(f"End [{DEFAULT_END}]: ").strip()
    try:
        start = int(start_text) if start_text else DEFAULT_START
        end = int(end_text) if end_text else DEFAULT_END
    except ValueError:
        print("Please enter whole numbers.", file=sys.stderr)
        return DEFAULT_START, DEFAULT_END
    return start, end


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Print Fizz Buzz for a range, with optional custom rules.",
        epilog=(
            "Examples:\n"
            "  python3 solution.py --start 1 --end 15\n"
            "  python3 solution.py --rule 3:Fizz --rule 5:Buzz --rule 7:Pop\n"
            "  python3 solution.py --start 90 --end 100 --separator ', '"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--start", type=int, default=None, help="first number (default 1)")
    parser.add_argument("--end", type=int, default=None, help="last number (default 100)")
    parser.add_argument(
        "--rule",
        action="append",
        metavar="DIVISOR:LABEL",
        help="replace the default rules with custom ones; may be repeated",
    )
    parser.add_argument(
        "--separator",
        default="\n",
        help="text between outputs (default: newline)",
    )
    parser.add_argument("--output", metavar="FILE", help="write output to FILE instead of stdout")
    parser.add_argument("--demo", action="store_true", help="run a scripted demonstration")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.demo:
        return demo()

    try:
        rules = build_rules(args.rule)
    except (ValueError, argparse.ArgumentTypeError) as exc:
        parser.error(str(exc))

    start = args.start
    end = args.end
    if start is None or end is None:
        if start is None and end is None and sys.stdin.isatty():
            start, end = interactive_range()
        else:
            start = DEFAULT_START if start is None else start
            end = DEFAULT_END if end is None else end

    if start > end:
        parser.error("--start must be less than or equal to --end")

    output = run(start, end, rules, args.separator)
    if args.output:
        try:
            Path(args.output).write_text(output + "\n", encoding="utf-8")
        except OSError as exc:
            print(f"error: cannot write {args.output}: {exc}", file=sys.stderr)
            return 1
        count = end - start + 1
        print(f"Wrote {count} line(s) to {args.output}")
    else:
        print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
