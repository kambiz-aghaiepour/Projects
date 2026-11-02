# Vigenère / Vernam / Caesar Ciphers

*Category: Text · Project directory: `Text/Vigenere-Vernam-Caesar-Ciphers/`*

## Problem

Functions for encrypting and decrypting data messages. Then send them to a friend.

## Features

- Caesar cipher with arbitrary (including negative and wrapping) shifts.
- Vigenère cipher with a repeating alphabetic keyword.
- Vernam / one-time-pad XOR cipher over UTF-8 bytes.
- Case and punctuation are preserved by Caesar and Vigenère; only letters rotate.
- Hex or base64 ciphertext for Vernam, with keys supplied via `--key-hex` or `--key-file`.
- `--random-key` generates a cryptographically random pad and `--key-out` saves it.
- Strict key checks: Vigenère rejects non-letters, Vernam rejects keys shorter than the message.
- `--self-test` known-answer tests; `--demo` prints tests and example round-trips.

## Requirements

Python 3.10+ (standard library only: `secrets`, `base64`).

## Usage

```bash
python3 solution.py --demo
python3 solution.py --self-test

python3 solution.py caesar encrypt "Hello, World!" --shift 3
python3 solution.py caesar decrypt "Khoor, Zruog!" --shift 3

python3 solution.py vigenere encrypt "ATTACKATDAWN" --key LEMON
python3 solution.py vigenere decrypt "LXFOPVEFRNHR" --key LEMON

python3 solution.py vernam encrypt "Attack at dawn!" \
    --key-hex 0102030405060708090a0b0c0d0e0f
python3 solution.py vernam decrypt 40767765666d27697d2a6f6d7a602e \
    --key-hex 0102030405060708090a0b0c0d0e0f

python3 solution.py vernam encrypt "secret" --random-key --key-out secret.key
python3 solution.py vernam decrypt CIPHERTEXT --key-file secret.key --format base64
```

If `text` is omitted, it is read from stdin. Running with no arguments on a terminal prompts for the cipher, mode, text, and key.

| Option | Meaning |
| --- | --- |
| `cipher` | `caesar`, `vigenere`, or `vernam`. |
| `mode` | `encrypt` or `decrypt`. |
| `--shift N` | Caesar rotation (default 3; wraps modulo 26). |
| `--key TEXT` | Vigenère keyword; ASCII letters only. |
| `--key-hex HEX` | Vernam key bytes in hex (whitespace ignored). |
| `--key-file PATH` | File containing the Vernam key as hex. |
| `--random-key` | Generate a random key as long as the plaintext (encryption only). |
| `--key-out PATH` | Write the key to a file as hex. |
| `--format hex` or `--format base64` | Vernam ciphertext encoding (default hex). |
| `--self-test`, `--demo` | Run tests or the scripted demonstration. |

## Example Output

```text
Vigenère / Vernam / Caesar Ciphers demo
==========================================
  [PASS] Caesar known vector
  [PASS] Caesar round-trip
  [PASS] Caesar shift wraps
  [PASS] Vigenère known vector
  [PASS] Vigenère case/punctuation
  [PASS] Vigenère round-trip
  [PASS] Vernam round-trip
  [PASS] Vernam XOR is self-inverse
  [PASS] Vernam rejects short keys
  [PASS] Vigenère rejects non-letters

--- Caesar (shift 3) ---
plain:       The quick brown fox jumps over the lazy dog.
cipher:      Wkh txlfn eurzq ira mxpsv ryhu wkh odcb grj.
round-trip:  The quick brown fox jumps over the lazy dog.

--- Vigenère (key: LEMON) ---
plain:       Attack at dawn!
cipher:      Lxfopv ef rnhr!
round-trip:  Attack at dawn!

--- Vernam one-time pad ---
plain:       Attack at dawn!
key (hex):   0102030405060708090a0b0c0d0e0f
cipher:      40767765666d27697d2a6f6d7a602e
round-trip:  Attack at dawn!
base64 form: QHZ3ZWZtJ2l9Km9temAu
```

## Implementation Notes

- Caesar uses `(ord(ch) - base + shift) % 26`, so any integer shift works and decryption is the same function with `-shift`.
- Vigenère indexes the key only on alphabetic characters, preserving case, spaces, and punctuation. A non-letter key is rejected rather than silently filtered.
- Vernam computes `cipher[i] = plain[i] XOR key[i]`. A key shorter than the data raises `CipherError`; this is the one-time-pad requirement, not a repeated-key stream cipher. The same function decrypts.
- Vernam input is encoded as UTF-8, so it works for Unicode text but is byte-oriented; decryption that does not produce valid UTF-8 is reported as an error.
- `--random-key` uses `secrets.token_bytes`; with `--key-out PATH` the hex key is written to that file and never echoed to stdout. Never reuse a one-time pad for two messages.
- Caesar and Vigenère are classical ciphers and are not secure for real secrets; the demo is educational. Vernam is only information-theoretically secure with a truly random key used once and kept secret.
