# Sorting

*Category: `Classic-Algorithms` — project directory: `Classic-Algorithms/Sorting/`.*

## Problem

Implement two types of sorting algorithms: merge sort and bubble sort.

## Features

- Merge sort and bubble sort written from scratch — no `sorted()` and no
  `list.sort()` anywhere in the module.
- Exact comparison counts for every run, via an injectable counting comparator.
- Stable output for both algorithms.
- Bubble sort exits early on already-sorted input.
- Handles integers, floats, duplicates, negative values, and empty input.
- Verifies each result for sortedness and for element preservation.
- Seeded benchmark mode for comparing the two algorithms on larger inputs.

## Requirements

Python 3.10+ (standard library only).

## Usage

```bash
python3 solution.py --demo
python3 solution.py 5 3 9 1
python3 solution.py -a merge 4,2,7,1
python3 solution.py --benchmark 5000 --seed 42
```

Options:

- `values` – numbers to sort, separated by spaces and/or commas.
- `-a, --algorithm {merge,bubble,both}` – algorithm to run (default `both`).
- `--demo` – scripted demonstration on fixed data plus a seeded benchmark.
- `--benchmark N` – benchmark both algorithms on `N` random integers.
- `--seed N` – random seed for the benchmark (default `20240101`).

With no values and no flags, the program prompts for a line of numbers.

## Example Output

```
$ python3 solution.py --demo
Sorting - demo
Input: 38, 27, 43, 3, 9, 82, 10, -5, 27, 0

Bubble sort: -5, 0, 3, 9, 10, 27, 27, 38, 43, 82
  comparisons: 45
Merge sort: -5, 0, 3, 9, 10, 27, 27, 38, 43, 82
  comparisons: 24
  outputs agree: yes
  verification (bubble): ok
  verification (merge): ok

Benchmark on 600 seeded integers (seed=20240101):
  bubble   0.019s       178,959 comparisons  sorted=True
  merge    0.001s         4,783 comparisons  sorted=True
```

## Implementation Notes

Merge sort is a stable top-down implementation: the input is split in half,
each half is sorted recursively, and the two sorted halves are merged. It runs
in O(n log n) time and uses O(n) auxiliary memory. Bubble sort repeatedly swaps
adjacent out-of-order elements, stopping after a pass with no swaps; it is
O(n²) worst case, O(n) best case, and sorts in place.

Both functions copy their input and return a new list, so the caller's data is
never mutated. Comparisons go through a `less` callable; the demo passes a
small counting wrapper to obtain exact comparison totals. This also makes the
algorithms usable with custom orderings (for example, sorting tuples by a key).
