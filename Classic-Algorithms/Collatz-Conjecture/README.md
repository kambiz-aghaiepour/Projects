# Collatz Conjecture

*Category: `Classic-Algorithms` — project directory: `Classic-Algorithms/Collatz-Conjecture/`.*

## Problem

Start with a number `n > 1`. Find the number of steps it takes to reach one
using the following process: if `n` is even, divide it by 2; if `n` is odd,
multiply it by 3 and add 1.

## Features

- Counts the steps for any starting value and reports the highest value reached.
- Prints the complete trajectory from the start down to 1.
- Finds the starting value with the longest chain below an arbitrary bound.
- Memoises every value it visits, so a full scan over a range is close to one
  unit of work per new starting value.
- Works as a one-shot CLI command or as an interactive prompt.

## Requirements

Python 3.10+ (standard library only).

## Usage

```bash
python3 solution.py --demo
python3 solution.py 27
python3 solution.py 27 --sequence
python3 solution.py --demo --limit 1000000
```

Options:

- `number` – optional positional starting value; when omitted the program
  prompts for one.
- `-l, --limit N` – upper bound used by `--demo` when searching for the longest
  chain (default `100000`, capped at `5000000`).
- `-s, --sequence` – print the full trajectory for the requested number.
- `--demo` – scripted, non-interactive demonstration.
- `--max-limit` – print the supported demo bound and exit.

## Example Output

```
$ python3 solution.py --demo
Collatz Conjecture - demo
Rule: n even -> n/2, n odd -> 3n + 1; stop when the value reaches 1.

Steps for the first ten starting values:
   1 ->  0 steps
   2 ->  1 steps
   3 ->  7 steps
   4 ->  2 steps
   5 ->  5 steps
   6 ->  8 steps
   7 -> 16 steps
   8 ->  3 steps
   9 -> 19 steps
  10 ->  6 steps

Sample trajectories:
  6: 6 -> 3 -> 10 -> 5 -> 16 -> 8 -> 4 -> 2 -> 1
     8 steps, peak 16
  27: 27 -> 82 -> 41 -> 124 -> 62 -> 31 -> 94 -> 47 -> 142 -> 71 -> ... (96 omitted) ... -> 5 -> 16 -> 8 -> 4 -> 2 -> 1
     111 steps, peak 9,232

Longest chain for 1 <= n <= 100,000:
  start 77,031: 350 steps, peak 21,933,016
  cache entries: 217,212
```

## Implementation Notes

The solver walks a trajectory iteratively until it hits a value already in the
cache (the base case is `1 -> 0` steps), then back-fills step counts and peaks
for every value on the path in reverse. Step counting is therefore amortised
almost O(1) per starting value, and `longest_under` only does new work for
values whose trajectory has not been seen.

The cache holds one entry per distinct value visited, which can exceed the
search bound because trajectories climb above their starting value (for
`n <= 100,000` it holds about 217k entries). No recursion is used, so large
starting values cannot exhaust the Python stack. The demo bound is capped at
5,000,000 to keep run time and memory reasonable.
