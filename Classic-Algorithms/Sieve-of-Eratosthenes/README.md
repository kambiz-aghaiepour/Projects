# Sieve of Eratosthenes

*Category: `Classic-Algorithms` — project directory: `Classic-Algorithms/Sieve-of-Eratosthenes/`.*

## Problem

The sieve of Eratosthenes is one of the most efficient ways to find all of the
smaller primes (below 10 million or so).

## Features

- Generates every prime up to a chosen bound, up to 10,000,000.
- Fast bytearray implementation: slice assignment marks whole multiples at
  once in C rather than looping per composite.
- `--count` mode reports the prime count and largest prime without building a
  list.
- `--twin` mode lists twin prime pairs below the bound.
- Demo verifies known values of π(n) and times sieves of 100k, 1M, and 10M.
- Interactive fallback when no limit is supplied.

## Requirements

Python 3.10+ (standard library only).

## Usage

```bash
python3 solution.py --demo
python3 solution.py --limit 1000000
python3 solution.py --limit 10000000 --count
python3 solution.py --limit 1000 --twin
```

Options:

- `-l, --limit N` – inclusive upper bound (prompted for when omitted; maximum
  `10000000`).
- `--count` – print only the count and the largest prime.
- `--twin` – also report twin prime pairs up to the limit.
- `--demo` – scripted demonstration with prime counts and timings.

With no options, the program prompts for an upper bound.

## Example Output

```
$ python3 solution.py --demo
Sieve of Eratosthenes - demo
Supported limit: up to 10,000,000

Primes up to 50:
  2, 3, 5, 7, 11, 13, 17, 19, 23, 29, 31, 37, 41, 43, 47

Prime counting and timing:
       limit    primes      time    memory
     100,000     9,592    0.000s     0.1MB
   1,000,000    78,498    0.004s     1.0MB
  10,000,000   664,579    0.036s     9.5MB
  largest prime below 10,000,000: 9,999,991

Known checks: pi(100)=25, pi(1,000)=168, pi(1,000,000)=78,498
  pi(100) = 25
  pi(10,000) = 1,229
  prime 9973? True; prime 9999? False

Twin primes below 1,000: 35; last five: (809,811) (821,823) (827,829) (857,859) (881,883)
Demo sieve time (all three sizes): 0.040s
```

## Implementation Notes

The sieve stores one byte per candidate. All entries start as `1`; indices 0
and 1 are cleared, then for each prime `p` up to `sqrt(limit)` the slice
`flags[p*p::p]` is replaced with zero bytes. Assigning a slice of the right
length keeps the marking loop inside CPython's C code, which is why 10 million
takes only a few hundredths of a second here.

Memory use is one byte per number, so the 10M case needs about 9.5 MiB. The
limit is capped at 10,000,000 both to honour the problem's stated scale and to
avoid unbounded allocation. Counting uses `sum(flags)` rather than building a
list, and extracting primes uses `enumerate` over the bytearray.
