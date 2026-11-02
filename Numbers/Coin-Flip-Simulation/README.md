# Coin Flip Simulation

**Category:** Numbers · **Project:** `Coin-Flip-Simulation`

## Problem

> Write some code that simulates flipping a single coin however many times the user decides. The code should record the outcomes and count the number of tails and heads.

## Features

- Simulates any number of independent flips (default 100).
- Records every outcome in order for later inspection.
- Reports head/tail counts, percentages, and the longest streak of each side.
- `--seed` makes runs reproducible; `--p-heads` simulates a biased coin.
- `--sequence` prints the outcome sequence, truncated safely at 120 flips.
- Validates flip count and probability with clear error messages.
- `--demo` shows a seeded 1,000-flip run, a visible 20-flip sequence and a biased coin.

## Requirements

Python 3.10 or newer. Standard library only — no packages to install.

## Usage

```bash
python3 solution.py --demo
python3 solution.py --flips 1000 --seed 42
python3 solution.py --flips 20 --sequence
python3 solution.py --flips 500 --p-heads 0.75 --seed 1
```

- `-n/--flips N` — number of flips (default 100).
- `--seed N` — seed the RNG for a repeatable result.
- `--p-heads P` — probability of heads in `[0, 1]` (default 0.5).
- `--sequence` — print the recorded outcomes (first 120 shown).
- `--demo` — run the scripted demonstrations.

## Example Output

```text
Coin Flip Simulation demo
====================================================
1,000 flips with seed 42:
Flips:        1,000
P(heads):     0.50
Heads:        480 (48.0%)
Tails:        520 (52.0%)
Longest run:  heads 7, tails 13

20 flips with seed 7 (outcome sequence):
  H H T H T H H T H H H H H T H H T T T H
  heads=13 tails=7 (longest streak H5/T3)

Biased coin, p(heads)=0.75, 400 flips, seed 1:
Flips:        400
P(heads):     0.75
Heads:        299 (74.8%)
Tails:        101 (25.2%)
Longest run:  heads 18, tails 4
```

## Implementation Notes

Outcomes are simulated with `random.Random.random() < p_heads`, one draw per
flip, and stored as `"H"`/`"T"`. Counts and streaks are updated during the same
pass, so the simulation is O(n) time and O(n) memory (memory is needed to show the
sequence). Independent draws mean the long-run proportion converges to `p_heads`,
but short runs can deviate substantially — that is expected randomness, not a bug.

`random` is a Mersenne Twister PRNG and is not suitable for cryptographic use;
this is a statistics demonstration.
