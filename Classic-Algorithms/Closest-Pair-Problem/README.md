# Closest Pair Problem

*Category: `Classic-Algorithms` — project directory: `Classic-Algorithms/Closest-Pair-Problem/`.*

## Problem

The closest pair of points problem (or closest pair problem) is a problem of
computational geometry: given `n` points in metric space, find a pair of points
with the smallest distance between them.

## Features

- O(n log n) divide-and-conquer solution for points in the Euclidean plane.
- Linear-time strip check using y-sorted merge, avoiding an extra sort at each
  recursion level.
- Independent O(n²) brute-force implementation included for cross-checking.
- Handles duplicate points (distance 0), collinear points, and vertical lines.
- Accepts points on the command line, generates seeded random clouds, or reads
  them interactively.
- Demo cross-checks both algorithms on fixed and random data and reports a
  speed-up measurement.

## Requirements

Python 3.10+ (standard library only).

## Usage

```bash
python3 solution.py --demo
python3 solution.py --points "0,0 3,4 10,10"
python3 solution.py --random 5000 --seed 7
python3 solution.py --points "0,0 3,4 10,10" --brute-force
```

Options:

- `-p, --points LIST` – points as `x,y` tokens separated by spaces or
  semicolons.
- `--random N` – generate `N` random points in `[0, 1000)²` instead.
- `--seed N` – random seed for `--random` and the demo (default `12345`).
- `--brute-force` – use the O(n²) reference algorithm instead of divide and
  conquer (useful for small inputs or verification).
- `--demo` – scripted, non-interactive demonstration with a brute-force
  cross-check.

## Example Output

```
$ python3 solution.py --demo
Closest Pair - demo (O(n log n) divide and conquer)
Points: (2, 3) (12, 30) (40, 50) (5, 1) (12, 10) (3, 4) (28, 19)
  divide and conquer: (2, 3) <-> (3, 4) distance 1.414214 (13 checks)
  brute force:        (2, 3) <-> (3, 4) distance 1.414214 (21 checks)
  results agree: yes

Random cloud: 400 points, seed=12345
  divide and conquer: (952.164, 96.4074) <-> (949.831, 97.1794) distance 2.457405 (2,695 checks) in 0.0010s
  brute force:        (952.164, 96.4074) <-> (949.831, 97.1794) distance 2.457405 (79,800 checks) in 0.0084s
  results agree: yes
  speed-up at this size: 8.8x

Scaling check: 20,000 points in 0.072s (closest distance 0.2512)
```

## Implementation Notes

Points are sorted by x once. The recursive step splits the sorted list at the
midpoint, solves each half, and returns the points sorted by y. The two
y-sorted halves are merged in linear time, so each level of recursion costs
O(n) and the total is O(n log n).

After the recursive calls, only points within the current best distance `d` of
the dividing line are examined, in y order. For each point, the inner loop
stops once the y gap reaches `d`, which limits the number of distance
evaluations per point to a small constant. Squared distances are used in the
inner loops to avoid square roots.

The demo's brute-force cross-check is O(n²), which is why it is only run on the
fixed set and on a 400-point cloud; the 20,000-point scaling check uses the
divide-and-conquer path alone.
