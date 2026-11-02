# Credit Card Validator

**Category:** Numbers · **Project:** `Credit-Card-Validator`

## Problem

> Takes in a credit card number from a common credit card vendor (Visa, MasterCard, American Express, Discoverer) and validates it to make sure that it is a valid number (look into how credit cards use a checksum).

## Features

- Strips spaces and dashes, then checks length, issuer prefix and the Luhn mod-10 checksum.
- Issuer detection for **Visa, Mastercard, American Express, Discover, JCB, Diners Club and Maestro**,
  including Mastercard's 2221–2720 range and Discover's 622126–622925 range.
- Explains *why* a number fails: wrong length for the network, bad checksum (and the expected
  check digit), or an unrecognised prefix.
- Formats numbers with the network's conventional grouping (4-6-5 for Amex, 4-6-4 for Diners, etc.).
- `--verbose` prints the full Luhn table: each digit, whether it was doubled, and its contribution.
- `--generate ISSUER --seed N` creates deterministic, checksum-valid sample numbers for testing.
- `--list-issuers` documents supported prefixes and lengths.

## Requirements

Python 3.10 or newer. Standard library only — no packages to install.

## Usage

```bash
python3 solution.py --demo
python3 solution.py 4111111111111111
python3 solution.py "3782 822463 10005" --verbose
python3 solution.py --generate amex --seed 7
python3 solution.py --list-issuers
```

- `NUMBER` — card number to validate; spaces and dashes are ignored.
- `--verbose` — show the Luhn doubling table and checksum total.
- `--generate ISSUER` — produce a valid sample for `visa`, `mastercard`, `amex`, `discover`,
  `jcb`, `diners` or `maestro`; combine with `--seed` and `--length`.
- `--list-issuers` — print prefix patterns and accepted lengths.
- `--demo` — validate known test numbers and generated samples.
- Exit status is 0 for a valid number and 1 for a failed validation; malformed input exits 2.

## Example Output

```text
Credit Card Validator demo
==========================================================
4111 1111 1111 1111
  status: VALID
  issuer: Visa
  Luhn:   pass
  detail: valid number

5500 0055 5555 5559
  status: VALID
  issuer: Mastercard
  Luhn:   pass
  detail: valid number

3782 822463 10005
  status: VALID
  issuer: American Express
  Luhn:   pass
  detail: valid number

6011 1111 1111 1117
  status: VALID
  issuer: Discover
  Luhn:   pass
  detail: valid number

3530 1113 3330 0000
  status: VALID
  issuer: JCB
  Luhn:   pass
  detail: valid number

3056 930902 5904
  status: VALID
  issuer: Diners Club
  Luhn:   pass
  detail: valid number

----------------------------------------------------------
Invalid checksum:
4111 1111 1111 1112
  status: INVALID
  issuer: Visa
  Luhn:   fail
  detail: Luhn checksum failed (last digit should be 1 for this prefix)
...
----------------------------------------------------------
Generated samples (seed 2024):
  visa        4729 4364 8375 6894           VALID (Visa)
  mastercard  5172 9436 4837 5683           VALID (Mastercard)
  amex        3472 943648 37568             VALID (American Express)
  discover    6011 7294 3648 3752           VALID (Discover)
  jcb         3528 7294 3648 3755           VALID (JCB)
  diners      3007 294364 8371              VALID (Diners Club)
  maestro     5018 7294 3648 3757           VALID (Maestro)
```

## Implementation Notes

Luhn's algorithm: starting from the rightmost digit and moving left, double every
second digit, subtract 9 from products above 9, then sum all digits. A number is
well-formed when the sum is divisible by 10. The check digit for a partial number
is `(10 - sum % 10) % 10`.

A passing checksum only proves the digits are internally consistent; it does not
prove the card exists, is active, or has funds. Real validation requires an issuer
authorisation. Issuer prefix tables change over time, so unknown-but-Luhn-valid
numbers are reported as having an unrecognised issuer rather than being accepted.
