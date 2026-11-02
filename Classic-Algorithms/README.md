# Classic Algorithms

Foundational algorithms: sequences, sorting, geometry, and primes.

Each project lives in its own subdirectory with a `README.md` and a runnable `solution.py`.

- [Collatz Conjecture](Collatz-Conjecture/) — Start with a number n > 1. Find the number of steps it takes to reach one using the following process: If n is even, divide it by 2. If n is odd, multiply it by 3 and add 1.
- [Sorting](Sorting/) — Implement two types of sorting algorithms: Merge sort and bubble sort.
- [Closest Pair Problem](Closest-Pair-Problem/) — The closest pair of points problem or closest pair problem is a problem of computational geometry: given n points in metric space, find a pair of points with the smallest distance between them.
- [Sieve of Eratosthenes](Sieve-of-Eratosthenes/) — The sieve of Eratosthenes is one of the most efficient ways to find all of the smaller primes (below 10 million or so).

## Running a project

```bash
cd <Project-Directory>
python3 solution.py --demo
```

Every program supports `--help`; most run interactively with no arguments. Image-based projects list Pillow in `requirements.txt`.
