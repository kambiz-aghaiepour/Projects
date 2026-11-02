#!/usr/bin/env python3
"""Validate credit card numbers with the Luhn checksum and issuer rules.

The program strips spaces and dashes, checks the number's length and issuer
prefix (Visa, Mastercard, American Express, Discover, JCB, Diners Club,
Maestro), and verifies the Luhn check digit.  ``--generate`` builds valid
sample numbers for testing.

Examples:
    python3 solution.py 4111 1111 1111 1111
    python3 solution.py 378282246310005 --verbose
    python3 solution.py --generate visa --seed 7
    python3 solution.py --demo
"""

from __future__ import annotations

import argparse
import random
import re
import sys
from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True)
class Issuer:
    """Card network definition: prefix pattern, valid lengths, digit grouping."""

    name: str
    pattern: re.Pattern[str]
    lengths: tuple[int, ...]
    groups: tuple[int, ...]


@dataclass(frozen=True)
class Result:
    """Outcome of validating one card number."""

    digits: str
    valid: bool
    issuer: str | None
    luhn_ok: bool
    reason: str
    formatted: str


ISSUERS: tuple[Issuer, ...] = (
    Issuer("Visa", re.compile(r"^4"), (13, 16, 19), (4, 4, 4, 4)),
    Issuer(
        "Mastercard",
        re.compile(r"^(?:5[1-5]|2(?:2[2-9]\d|[3-6]\d{2}|7[01]\d|720))"),
        (16,),
        (4, 4, 4, 4),
    ),
    Issuer("American Express", re.compile(r"^3[47]"), (15,), (4, 6, 5)),
    Issuer(
        "Discover",
        re.compile(r"^(?:6011|65|64[4-9]|622(?:12[6-9]|1[3-9]\d|[2-8]\d{2}|9[01]\d|92[0-5]))"),
        (16, 19),
        (4, 4, 4, 4),
    ),
    Issuer("JCB", re.compile(r"^35(?:2[89]|[3-8]\d)"), (16, 17, 18, 19), (4, 4, 4, 4)),
    Issuer("Diners Club", re.compile(r"^(?:30[0-5]|36|38)"), (14, 16), (4, 6, 4)),
    Issuer(
        "Maestro",
        re.compile(r"^(?:5018|5020|5038|5893|6304|6759|676[1-3])"),
        (12, 13, 14, 15, 16, 17, 18, 19),
        (4, 4, 4, 4),
    ),
)

# Prefixes used by --generate: (issuer, leading digits, total length).
GENERATORS: dict[str, tuple[str, str, int]] = {
    "visa": ("Visa", "4", 16),
    "mastercard": ("Mastercard", "51", 16),
    "amex": ("American Express", "34", 15),
    "discover": ("Discover", "6011", 16),
    "jcb": ("JCB", "3528", 16),
    "diners": ("Diners Club", "300", 14),
    "maestro": ("Maestro", "5018", 16),
}


def normalise_number(text: str) -> str:
    """Remove spaces/dashes and reject anything that is not 12-19 digits."""

    digits = re.sub(r"[\s\-]", "", text)
    if not digits:
        raise ValueError("card number is empty")
    if not digits.isdigit():
        raise ValueError("card number must contain digits only")
    if not 12 <= len(digits) <= 19:
        raise ValueError(f"card number has {len(digits)} digits; expected 12-19")
    return digits


def luhn_total(digits: str) -> int:
    """Return the Luhn sum (doubling every second digit from the right)."""

    total = 0
    for index, char in enumerate(reversed(digits)):
        value = int(char)
        if index % 2 == 1:
            value *= 2
            if value > 9:
                value -= 9
        total += value
    return total


def luhn_ok(digits: str) -> bool:
    """True when the number passes the Luhn mod-10 checksum."""

    return luhn_total(digits) % 10 == 0


def luhn_check_digit(partial: str) -> int:
    """Compute the check digit that must be appended to ``partial``."""

    total = 0
    for index, char in enumerate(reversed(partial)):
        value = int(char)
        if index % 2 == 0:  # with the check digit appended these become odd positions
            value *= 2
            if value > 9:
                value -= 9
        total += value
    return (10 - total % 10) % 10


def group_digits(digits: str, groups: Iterable[int]) -> str:
    """Format digits using the issuer's conventional grouping."""

    chunks: list[str] = []
    position = 0
    for size in groups:
        if position >= len(digits):
            break
        chunks.append(digits[position:position + size])
        position += size
    if position < len(digits):
        chunks.append(digits[position:])
    return " ".join(chunks)


def detect_issuer(digits: str) -> Issuer | None:
    """Return the first issuer whose prefix matches, regardless of length."""

    for issuer in ISSUERS:
        if issuer.pattern.match(digits):
            return issuer
    return None


def validate(text: str) -> Result:
    """Run length, issuer and Luhn checks and explain the verdict."""

    digits = normalise_number(text)
    issuer = detect_issuer(digits)
    checksum_ok = luhn_ok(digits)

    if issuer is None:
        reason = ("unknown issuer prefix"
                  + ("; Luhn checksum passes but the network cannot be identified"
                     if checksum_ok else "; Luhn checksum also fails"))
        return Result(digits, False, None, checksum_ok, reason, group_digits(digits, (4, 4, 4, 4)))

    formatted = group_digits(digits, issuer.groups)
    if len(digits) not in issuer.lengths:
        allowed = ", ".join(str(length) for length in issuer.lengths)
        return Result(digits, False, issuer.name, checksum_ok,
                      f"invalid length for {issuer.name} (expected {allowed} digits)", formatted)
    if not checksum_ok:
        expected = luhn_check_digit(digits[:-1])
        return Result(digits, False, issuer.name, False,
                      f"Luhn checksum failed (last digit should be {expected} for this prefix)",
                      formatted)
    return Result(digits, True, issuer.name, True, "valid number", formatted)


def generate(issuer_key: str, seed: int | None = None, length: int | None = None) -> str:
    """Generate a Luhn-valid sample number for a supported issuer."""

    key = issuer_key.casefold().replace(" ", "")
    if key not in GENERATORS:
        raise ValueError(f"unknown issuer {issuer_key!r}; choose from {', '.join(GENERATORS)}")
    issuer_name, prefix, default_length = GENERATORS[key]
    if length is not None and length < len(prefix) + 2:
        raise ValueError("requested length is too short for this prefix")
    total_length = length or default_length
    issuer = next(item for item in ISSUERS if item.name == issuer_name)
    if total_length not in issuer.lengths:
        allowed = ", ".join(str(value) for value in issuer.lengths)
        raise ValueError(f"{issuer.name} supports lengths {allowed}, not {total_length}")
    rng = random.Random(seed)
    body = prefix + "".join(str(rng.randrange(10)) for _ in range(total_length - len(prefix) - 1))
    return body + str(luhn_check_digit(body))


def print_luhn_table(digits: str) -> None:
    """Explain the Luhn calculation digit by digit."""

    print("  position  digit  doubled  contribution")
    total = 0
    length = len(digits)
    for index, char in enumerate(digits):
        value = int(char)
        from_right = length - index - 1
        doubled = from_right % 2 == 1
        contribution = value * 2 - 9 if doubled and value > 4 else value * (2 if doubled else 1)
        total += contribution
        print(f"  {index + 1:>8}  {value:>5}  {'yes' if doubled else 'no ':>7}  {contribution:>12}")
    print(f"  Luhn sum = {total}; sum % 10 = {total % 10}")


def print_result(result: Result) -> None:
    """Print one validation verdict."""

    status = "VALID" if result.valid else "INVALID"
    print(f"{result.formatted}")
    print(f"  status: {status}")
    print(f"  issuer: {result.issuer or 'unknown'}")
    print(f"  Luhn:   {'pass' if result.luhn_ok else 'fail'}")
    print(f"  detail: {result.reason}")


def run_demo() -> int:
    """Validate known-good cards, a bad checksum and generated numbers."""

    print("Credit Card Validator demo")
    print("=" * 58)
    samples = [
        "4111 1111 1111 1111",
        "5500 0055 5555 5559",
        "3782 822463 10005",
        "6011 1111 1111 1117",
        "3530 1113 3330 0000",
        "3056 930902 5904",
    ]
    for sample in samples:
        print_result(validate(sample))
        print()

    print("-" * 58)
    print("Invalid checksum:")
    print_result(validate("4111 1111 1111 1112"))
    print()
    print_luhn_table(normalise_number("4111 1111 1111 1112"))
    print()

    print("-" * 58)
    print("Generated samples (seed 2024):")
    for key in GENERATORS:
        number = generate(key, seed=2024)
        result = validate(number)
        print(f"  {key:<11} {result.formatted:<29} "
              f"{'VALID' if result.valid else 'INVALID'} ({result.issuer})")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Validate credit card numbers using the Luhn checksum.",
        epilog="Examples: 4111111111111111 | 378282246310005 | --generate amex",
    )
    parser.add_argument("number", nargs="?", help="card number (spaces and dashes allowed)")
    parser.add_argument("--verbose", action="store_true",
                        help="print the Luhn calculation table")
    parser.add_argument("--generate", metavar="ISSUER",
                        help=f"generate a valid sample for: {', '.join(GENERATORS)}")
    parser.add_argument("--length", type=int, help="length for --generate (issuer permitting)")
    parser.add_argument("--seed", type=int, help="random seed for --generate")
    parser.add_argument("--list-issuers", action="store_true", help="show supported issuers")
    parser.add_argument("--demo", action="store_true", help="run a scripted demonstration")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.demo:
        return run_demo()

    if args.list_issuers:
        for issuer in ISSUERS:
            lengths = ", ".join(str(length) for length in issuer.lengths)
            print(f"{issuer.name:<18} lengths: {lengths:<18} prefix: {issuer.pattern.pattern}")
        return 0

    if args.generate:
        try:
            number = generate(args.generate, seed=args.seed, length=args.length)
        except ValueError as exc:
            parser.error(str(exc))
        result = validate(number)
        print(result.formatted)
        print(f"issuer: {result.issuer}; valid: {result.valid}")
        return 0

    if args.number:
        try:
            result = validate(args.number)
        except ValueError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2
        print_result(result)
        if args.verbose:
            print()
            print_luhn_table(result.digits)
        return 0 if result.valid else 1

    print("Enter card numbers to validate (blank line to quit).")
    while True:
        try:
            line = input("card> ")
        except (EOFError, KeyboardInterrupt):
            print()
            return 0
        if not line.strip():
            return 0
        try:
            print_result(validate(line))
        except ValueError as exc:
            print(f"error: {exc}")


if __name__ == "__main__":
    sys.exit(main())
