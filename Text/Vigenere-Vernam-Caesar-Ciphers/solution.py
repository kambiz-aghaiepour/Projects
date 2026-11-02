#!/usr/bin/env python3
"""Caesar, Vigenère, and Vernam (one-time-pad) encryption and decryption.

A small self-testing cipher toolkit:

* Caesar rotates each letter by a fixed shift, preserving case and punctuation.
* Vigenère repeats a keyword of letters over the alphabetic characters.
* Vernam XORs UTF-8 bytes with a key that must be at least as long as the
  message (a true one-time pad), using a hex or file-supplied key.

``--demo`` runs known-answer tests and example round-trips without any input.
"""

from __future__ import annotations

import argparse
import base64
import secrets
import sys
from pathlib import Path


class CipherError(Exception):
    """Raised for invalid keys or ciphertext."""


# -- Caesar --------------------------------------------------------------
def caesar(text: str, shift: int) -> str:
    """Rotate ASCII letters in *text* by *shift* places, preserving case."""
    shift %= 26
    result = []
    for char in text:
        if char.isascii() and char.isalpha():
            base = ord("A") if char.isupper() else ord("a")
            result.append(chr((ord(char) - base + shift) % 26 + base))
        else:
            result.append(char)
    return "".join(result)


def caesar_encrypt(text: str, shift: int) -> str:
    return caesar(text, shift)


def caesar_decrypt(text: str, shift: int) -> str:
    return caesar(text, -shift)


# -- Vigenère ------------------------------------------------------------
def validate_vigenere_key(key: str) -> list[int]:
    if not key:
        raise CipherError("the Vigenère key must not be empty")
    if not key.isascii() or not key.isalpha():
        raise CipherError("the Vigenère key must contain ASCII letters only")
    return [ord(char.upper()) - ord("A") for char in key]


def vigenere(text: str, key: str, decrypt: bool = False) -> str:
    """Apply a repeating Vigenère key to the letters of *text*."""
    shifts = validate_vigenere_key(key)
    result = []
    index = 0
    for char in text:
        if char.isascii() and char.isalpha():
            base = ord("A") if char.isupper() else ord("a")
            shift = shifts[index % len(shifts)]
            if decrypt:
                shift = -shift
            result.append(chr((ord(char) - base + shift) % 26 + base))
            index += 1
        else:
            result.append(char)
    return "".join(result)


def vigenere_encrypt(text: str, key: str) -> str:
    return vigenere(text, key, decrypt=False)


def vigenere_decrypt(text: str, key: str) -> str:
    return vigenere(text, key, decrypt=True)


# -- Vernam / one-time pad ----------------------------------------------
def vernam(data: bytes, key: bytes) -> bytes:
    """XOR *data* with *key*, which must be at least as long as the data."""
    if not key:
        raise CipherError("the Vernam key must not be empty")
    if len(key) < len(data):
        raise CipherError(
            f"the Vernam key is too short: {len(key)} bytes for {len(data)} bytes of data"
        )
    return bytes(byte ^ key[index] for index, byte in enumerate(data))


def encode_bytes(data: bytes, fmt: str) -> str:
    return data.hex() if fmt == "hex" else base64.b64encode(data).decode("ascii")


def decode_bytes(text: str, fmt: str) -> bytes:
    compact = "".join(text.split())
    try:
        return bytes.fromhex(compact) if fmt == "hex" else base64.b64decode(compact, validate=True)
    except (ValueError, TypeError) as exc:
        raise CipherError(f"ciphertext is not valid {fmt}: {exc}") from exc


def key_from_hex(text: str) -> bytes:
    try:
        key = bytes.fromhex("".join(text.split()))
    except ValueError as exc:
        raise CipherError(f"key is not valid hex: {exc}") from exc
    if not key:
        raise CipherError("the Vernam key must not be empty")
    return key


# -- self-tests and demo -------------------------------------------------
def run_self_tests() -> list[tuple[str, bool]]:
    """Return ``(name, passed)`` results for known-answer and round-trip tests."""
    results: list[tuple[str, bool]] = []

    def check(name: str, condition: bool) -> None:
        results.append((name, bool(condition)))

    check("Caesar known vector", caesar_encrypt("Hello, World!", 3) == "Khoor, Zruog!")
    check("Caesar round-trip", caesar_decrypt(caesar_encrypt("Attack at dawn!", 7), 7) == "Attack at dawn!")
    check("Caesar shift wraps", caesar_encrypt("abc", 29) == caesar_encrypt("abc", 3) == "def")
    check("Vigenère known vector", vigenere_encrypt("ATTACKATDAWN", "LEMON") == "LXFOPVEFRNHR")
    check(
        "Vigenère case/punctuation",
        vigenere_encrypt("Attack at dawn!", "LEMON") == "Lxfopv ef rnhr!",
    )
    check(
        "Vigenère round-trip",
        vigenere_decrypt(vigenere_encrypt("Meet me at 10:30, please.", "CIPHER"), "CIPHER")
        == "Meet me at 10:30, please.",
    )
    message = b"Attack at dawn!"
    key = bytes(range(1, len(message) + 1))
    cipher = vernam(message, key)
    check("Vernam round-trip", vernam(cipher, key) == message)
    check("Vernam XOR is self-inverse", cipher != message and vernam(cipher, key) == message)
    try:
        vernam(b"too long", b"short")
        check("Vernam rejects short keys", False)
    except CipherError:
        check("Vernam rejects short keys", True)
    try:
        vigenere_encrypt("text", "bad key")
        check("Vigenère rejects non-letters", False)
    except CipherError:
        check("Vigenère rejects non-letters", True)
    return results


def demo() -> int:
    """Run the self-tests and print example encryptions."""
    print("Vigenère / Vernam / Caesar Ciphers demo\n" + "=" * 42)
    results = run_self_tests()
    for name, passed in results:
        print(f"  [{'PASS' if passed else 'FAIL'}] {name}")
    if not all(passed for _, passed in results):
        print("self-tests failed", file=sys.stderr)
        return 1

    print("\n--- Caesar (shift 3) ---")
    plain = "The quick brown fox jumps over the lazy dog."
    cipher = caesar_encrypt(plain, 3)
    print(f"plain:       {plain}")
    print(f"cipher:      {cipher}")
    print(f"round-trip:  {caesar_decrypt(cipher, 3)}")

    print("\n--- Vigenère (key: LEMON) ---")
    plain = "Attack at dawn!"
    cipher = vigenere_encrypt(plain, "LEMON")
    print(f"plain:       {plain}")
    print(f"cipher:      {cipher}")
    print(f"round-trip:  {vigenere_decrypt(cipher, 'LEMON')}")

    print("\n--- Vernam one-time pad ---")
    message = b"Attack at dawn!"
    key = bytes(range(1, len(message) + 1))
    cipher_bytes = vernam(message, key)
    print(f"plain:       {message.decode()}")
    print(f"key (hex):   {key.hex()}")
    print(f"cipher:      {encode_bytes(cipher_bytes, 'hex')}")
    print(f"round-trip:  {vernam(cipher_bytes, key).decode()}")
    print(f"base64 form: {encode_bytes(cipher_bytes, 'base64')}")

    if caesar_decrypt(caesar_encrypt(plain, 5), 5) != plain:
        return 1
    print("\ndemo assertions passed: all ciphers round-trip correctly")
    return 0


# -- CLI -----------------------------------------------------------------
def read_vernam_key(args: argparse.Namespace, length: int) -> bytes:
    if args.key_hex:
        key = key_from_hex(args.key_hex)
    elif args.key_file:
        try:
            key = key_from_hex(Path(args.key_file).expanduser().read_text(encoding="utf-8"))
        except OSError as exc:
            raise CipherError(f"cannot read key file {args.key_file}: {exc}") from exc
    elif args.random_key:
        if length == 0:
            raise CipherError("cannot generate a key for empty input")
        key = secrets.token_bytes(length)
    else:
        raise CipherError("Vernam needs --key-hex, --key-file, or --random-key")
    if args.key_out:
        try:
            Path(args.key_out).expanduser().write_text(key.hex() + "\n", encoding="utf-8")
        except OSError as exc:
            raise CipherError(f"cannot write key file {args.key_out}: {exc}") from exc
        print(f"key written to {args.key_out}", file=sys.stderr)
    return key


def run_cipher(args: argparse.Namespace) -> int:
    if not args.cipher or not args.mode:
        raise CipherError("choose a cipher and a mode (encrypt/decrypt)")
    if args.cipher == "caesar":
        text = args.text if args.text is not None else sys.stdin.read()
        result = caesar_encrypt(text, args.shift) if args.mode == "encrypt" else caesar_decrypt(text, args.shift)
        print(result)
        return 0

    if args.cipher == "vigenere":
        if not args.key:
            raise CipherError("Vigenère needs --key")
        text = args.text if args.text is not None else sys.stdin.read()
        result = vigenere_encrypt(text, args.key) if args.mode == "encrypt" else vigenere_decrypt(text, args.key)
        print(result)
        return 0

    # Vernam
    if args.mode == "encrypt":
        text = args.text if args.text is not None else sys.stdin.read()
        plain = text.encode("utf-8")
        key = read_vernam_key(args, len(plain))
        print(encode_bytes(vernam(plain, key), args.format))
        return 0
    if args.random_key:
        raise CipherError("--random-key cannot be used for decryption")
    cipher_text = args.text if args.text is not None else sys.stdin.read()
    cipher = decode_bytes(cipher_text, args.format)
    key = read_vernam_key(args, len(cipher))
    plain = vernam(cipher, key)
    try:
        print(plain.decode("utf-8"))
    except UnicodeDecodeError as exc:
        raise CipherError(f"decrypted bytes are not valid UTF-8: {exc}") from exc
    return 0


def interactive() -> int:
    """Prompt for cipher, mode, text, and key when run on a terminal."""
    print("Choose a cipher: 1) Caesar  2) Vigenère  3) Vernam")
    choice = input("cipher [1]: ").strip() or "1"
    mode = input("mode [encrypt/decrypt] (encrypt): ").strip().lower() or "encrypt"
    if mode not in {"encrypt", "decrypt"}:
        print("mode must be encrypt or decrypt", file=sys.stderr)
        return 2
    text = input("text: ")
    try:
        if choice in {"1", "caesar"}:
            shift = int(input("shift [3]: ").strip() or "3")
            print(caesar_encrypt(text, shift) if mode == "encrypt" else caesar_decrypt(text, shift))
        elif choice in {"2", "vigenere", "vigenère"}:
            key = input("key: ")
            print(vigenere_encrypt(text, key) if mode == "encrypt" else vigenere_decrypt(text, key))
        elif choice in {"3", "vernam"}:
            key_text = input("key (hex): ")
            key = key_from_hex(key_text)
            if mode == "encrypt":
                print(encode_bytes(vernam(text.encode(), key), "hex"))
            else:
                print(vernam(decode_bytes(text, "hex"), key).decode())
        else:
            print("unknown cipher", file=sys.stderr)
            return 2
    except (CipherError, UnicodeDecodeError, EOFError, KeyboardInterrupt) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Encrypt or decrypt text with Caesar, Vigenère, or Vernam ciphers.",
        epilog="Examples: solution.py caesar encrypt 'Hello' --shift 3 | "
               "solution.py vigenere decrypt LXFOPVEFRNHR --key LEMON",
    )
    parser.add_argument("cipher", nargs="?", choices=["caesar", "vigenere", "vernam"])
    parser.add_argument("mode", nargs="?", choices=["encrypt", "decrypt"])
    parser.add_argument("text", nargs="?", help="text to process; omit to read stdin")
    parser.add_argument("--shift", type=int, default=3, help="Caesar shift (default: 3)")
    parser.add_argument("--key", help="Vigenère keyword (letters only)")
    parser.add_argument("--key-hex", help="Vernam key as hexadecimal bytes")
    parser.add_argument("--key-file", help="file containing a Vernam key in hex")
    parser.add_argument("--random-key", action="store_true",
                        help="generate a random Vernam key as long as the plaintext")
    parser.add_argument("--key-out", metavar="PATH", help="write the Vernam key (hex) to a file")
    parser.add_argument("--format", choices=["hex", "base64"], default="hex",
                        help="Vernam ciphertext encoding (default: hex)")
    parser.add_argument("--self-test", action="store_true", help="run known-answer tests")
    parser.add_argument("--demo", action="store_true", help="run a scripted demonstration")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.demo:
        return demo()
    if args.self_test:
        results = run_self_tests()
        for name, passed in results:
            print(f"[{'PASS' if passed else 'FAIL'}] {name}")
        return 0 if all(passed for _, passed in results) else 1
    if not args.cipher:
        if not sys.stdin.isatty():
            parser.print_usage(sys.stderr)
            print("error: choose a cipher (or use --demo)", file=sys.stderr)
            return 2
        return interactive()
    try:
        return run_cipher(args)
    except CipherError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
