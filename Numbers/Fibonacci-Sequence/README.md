# Fibonacci Sequence

**Category:** Numbers · **Project:** `Fibonacci-Sequence`

## Problem

Enter a number and have the program generate the Fibonacci sequence to that number or to the Nth number.

## Features

- Two modes: the first N terms, or every term up to a maximum value.
- `--nth N` computes a single term with fast doubling in O(log N) big-integer
  multiplications.
- Arbitrary-size integers — F(1000) and far larger values work.
- Optional `--no-index` for a plain list of numbers.
- Interactive count prompt when run with no arguments.

## Requirements

Python 3.10+ and the standard library only.

## Usage

```bash
python3 solution.py --demo
python3 solution.py 10
python3 solution.py --up-to 1000
python3 solution.py --nth 1000
python3 solution.py 10 --no-index
```

- `N` — number of terms to print, starting at F(0) = 0.
- `--up-to V` — print every term less than or equal to V.
- `--nth N` — print only F(N), computed by fast doubling.
- `--no-index` — omit the `F(i) =` prefix.
- `--demo` — show both modes and F(1000).

## Example Output

```text
First 15 Fibonacci numbers:
F(0) = 0
F(1) = 1
F(2) = 1
F(3) = 2
F(4) = 3
F(5) = 5
F(6) = 8
F(7) = 13
F(8) = 21
F(9) = 34
F(10) = 55
F(11) = 89
F(12) = 144
F(13) = 233
F(14) = 377

Fibonacci numbers less than or equal to 100:
0, 1, 1, 2, 3, 5, 8, 13, 21, 34, 55, 89

F(1000) via fast doubling:
43466557686937456435688527675040625802564660517371780402481729089536555417949051890403879840079255169295922593080322634775209689623239873322471161642996440906533187938298969649928516003704476137795166849228875
```

## Implementation Notes

Sequence generation is iterative, O(N) additions and O(N) memory if the caller
collects the values. `nth_fibonacci` uses the identities

- `F(2k) = F(k) · (2F(k+1) − F(k))`
- `F(2k+1) = F(k)² + F(k+1)²`

recursively, so F(N) costs O(log N) multiplications. Output uses Python's
arbitrary-precision integers throughout; there is no fixed upper bound beyond
available memory and time.
