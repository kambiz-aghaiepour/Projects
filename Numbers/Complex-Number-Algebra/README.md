# Complex Number Algebra

**Category:** Numbers · **Project:** `Complex-Number-Algebra`

## Problem

> Show addition, multiplication, negation, and inversion of complex numbers in separate functions. (Subtraction and division operations can be made with pairs of these operations.) Print the results for each operation tested.

## Features

- Immutable `Complex` dataclass with real and imaginary float components.
- Separate primitives: `add`, `multiply`, `negate`, `inverse`.
- Derived operations: `subtract(a, b) = add(a, negate(b))` and
  `divide(a, b) = multiply(a, inverse(b))`.
- Extras: `conjugate`, `magnitude`, `argument`, and integer `power` by repeated squaring.
- Parser accepts `3+4i`, `3-4i`, `-2i`, `i`, `5`, `1.5e2+3j`, and whitespace.
- CLI dispatch for `add`, `subtract`, `multiply`, `divide`, `negate`, `inverse`,
  `conjugate` and `pow`.
- Demo prints every operation, algebraic identities, and parser examples.

## Requirements

Python 3.10 or newer. Standard library only — no packages to install.

## Usage

```bash
python3 solution.py --demo
python3 solution.py --a "3+4i" --b "1-2i" --op add
python3 solution.py --a "3+4i" --op inverse
python3 solution.py --a "2+3i" --op pow --exponent 4
python3 solution.py --a "1-2i" --b "3+i" --op divide
```

- `--a COMPLEX` — first operand (prompted if omitted).
- `--b COMPLEX` — second operand, required for binary operations.
- `--op {add,subtract,multiply,divide,negate,inverse,conjugate,pow}` — operation (default `add`).
- `--exponent N` — integer exponent for `pow` (default 2; negatives use the inverse).
- `--demo` — print the full operation table.

## Example Output

```text
Complex Number Algebra demo
======================================================
z1 = 3 + 4i
z2 = 1 - 2i

add(z1, z2)       = 4 + 2i
multiply(z1, z2)  = 11 - 2i
negate(z1)        = -3 - 4i
inverse(z1)       = 0.12 - 0.16i
subtract(z1, z2)  = 2 + 6i
divide(z1, z2)    = -1 + 2i
conjugate(z1)     = 3 - 4i
|z1|              = 5.000000
arg(z1)           = 0.927295 rad
z1^3              = -117 + 44i

Identities:
  z1 + (-z1)      = 0
  z1 * inverse(z1)= 1
  divide(z1, z1)  = 1

Parsing:
  '3+4i'       -> 3 + 4i
  '1-2i'       -> 1 - 2i
  '-2i'        -> -2i
  'i'          -> i
  '5'          -> 5
  '1.5e2+3j'   -> 150 + 3i

Check: (3+4i)(1-2i) expanded = 11 - 2i, program says 11 - 2i.
```

## Implementation Notes

With `z = a + bi`:

- `add(z₁, z₂) = (a₁+a₂) + (b₁+b₂)i`
- `multiply(z₁, z₂) = (a₁a₂ − b₁b₂) + (a₁b₂ + b₁a₂)i`
- `negate(z) = −a − bi`
- `inverse(z) = (a − bi) / (a² + b²)`, undefined at zero

Division multiplies by the inverse, so it raises a clear `ZeroDivisionError`
for a zero denominator. Integer powers use exponentiation by squaring and
negative powers invert the positive power. Components are IEEE-754 floats, so
results can show tiny rounding artefacts; the formatter trims values below
`1e-12` to zero and prints at most ten significant digits.
