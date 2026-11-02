# Dijkstra's Algorithm

Part of the **Graph** category — project `Graph/Dijkstras-Algorithm`.

## Problem

Create a program that finds the shortest path through a graph using its edges.

## Features

- Dijkstra's algorithm with a binary heap (`heapq`) and lazy deletion of stale
  heap entries.
- Reconstructs the actual path, not only the distance.
- Reports a full distance/path table from a source, or one detailed hop-by-hop
  route with `--target`.
- Handles unreachable nodes explicitly.
- Rejects negative edge weights with a clear error, since Dijkstra's algorithm
  is only valid for non-negative costs.
- Undirected by default; `--directed` honours one-way edges.
- Reads weighted edges from `--edges`, `--file`, piped stdin, or an interactive
  prompt; the source defaults to the first node.

## Requirements

Python 3.10+; standard library only. No third-party packages.

## Usage

```bash
python3 solution.py --demo
python3 solution.py --edges "A B 4" "A C 2" "B C 1" --source A
python3 solution.py --edges "A->B 1" "B->C 2" --directed --source A --target C
python3 solution.py --file weighted_edges.txt --source S
```

Options:

- `--edges EDGE [EDGE ...]` — weighted edges such as `A B 4` or `A->B:4`.
- `--file PATH` — read weighted edges from a file; repeatable.
- `--source NODE` — start node (default: first node in the input).
- `--target NODE` — print a detailed route instead of the full table.
- `--directed` — treat edges as directed (default is undirected).
- `--demo` — run the scripted demonstration.

## Example Output

```
Dijkstra's Algorithm -- demo

Undirected weighted graph
-------------------------
  A -- B(4), C(2)
  B -- A(4), C(1), D(5)
  ...
  G  (isolated)

Shortest paths from A
---------------------
  Node  Distance  Path
  A         0  A
  C         2  A -> C
  B         3  A -> C -> B
  D         8  A -> C -> B -> D
  E        10  A -> C -> B -> D -> E
  F        13  A -> C -> B -> D -> E -> F
  G         -  unreachable
Unreachable: G

Shortest path A -> F: 13
  A -> C   (2)
  C -> B   (1)
  B -> D   (5)
  D -> E   (2)
  E -> F   (3)
  Total: 13 over 5 edges
```

## Implementation Notes

The heap stores `(distance, node)` pairs. When a node is popped, entries whose
distance is greater than the best known distance are skipped; each relaxation
pushes a new entry, so the heap may contain duplicates but remains bounded by
O(E). Time complexity is O((V + E) log V) and space is O(V + E).

Predecessors are recorded on every successful relaxation and walked backwards
to reconstruct a path. Distances use Python floats; weights are formatted
without a trailing `.0`. The program checks every edge for negativity before
running and exits with status 2 on invalid input. An unreachable target is a
normal result (exit 0) and prints `No path from ...`.
