# Minimum Spanning Tree

Part of the **Graph** category — project `Graph/Minimum-Spanning-Tree`.

## Problem

Create a program which takes a connected, undirected graph with weights and
outputs the minimum spanning tree of the graph, i.e. a subgraph that is a tree,
contains all the vertices, and the sum of its weights is the least possible.

## Features

- Kruskal's algorithm with a disjoint-set forest (path halving, union by rank).
- Optional Prim's algorithm with a binary heap (`--prim`).
- `--compare` cross-checks both algorithms and reports whether their totals
  agree.
- `--forest` builds a minimum spanning forest when the input is disconnected.
- Clear error when a connected MST is requested for disconnected input, naming
  the number of components.
- Reports selected edges, total weight and a structural verification line
  (edge count = nodes - 1 for an MST).
- Handles parallel edges and ignores self-loops naturally through union-find.
- Reads weighted edges from `--edges`, `--file`, piped stdin, or an interactive
  prompt.

## Requirements

Python 3.10+; standard library only. No third-party packages.

## Usage

```bash
python3 solution.py --demo
python3 solution.py --edges "A B 7" "A D 5" "B D 9" "C E 5"
python3 solution.py --file weighted_edges.txt --prim
python3 solution.py --file clusters.txt --forest
```

Options:

- `--edges EDGE [EDGE ...]` — weighted undirected edges; repeatable.
- `--file PATH` — read weighted edges from a file; repeatable.
- `--prim` — use Prim's algorithm instead of Kruskal's.
- `--forest` — allow disconnected input and produce a minimum spanning forest.
- `--compare` — also run the other algorithm and compare total weights.
- `--demo` — run the scripted demonstration.

## Example Output

```
Minimum Spanning Tree -- demo

Minimum spanning tree (Kruskal)
===============================
undirected, weighted graph: 7 nodes, 11 edges
Edges selected: 6
  A -- D   weight 5
  C -- E   weight 5
  D -- F   weight 6
  A -- B   weight 7
  B -- E   weight 7
  E -- G   weight 9
Total weight: 39
Verification: 6 edges = 7 nodes - 1, all nodes connected, acyclic by construction

Prim comparison
---------------
Prim total: 39 (6 edges)
Kruskal total: 39 (6 edges)
Match: YES

Disconnected input
------------------
Connected-only check: graph is disconnected (3 components); an MST requires a connected graph (use --forest for a spanning forest)

Minimum spanning forest (Kruskal)
=================================
undirected, weighted graph: 7 nodes, 6 edges
Edges selected: 4
  A -- B   weight 1
  B -- C   weight 2
  D -- E   weight 3
  E -- F   weight 4
Total weight: 10
Input components: 3
Verification: 4 edges = 7 nodes - 3 components (expected 4)
```

## Implementation Notes

Kruskal sorts all edges by `(weight, insertion order)` — the tie-breaker keeps
output deterministic — then adds an edge whenever union-find reports that its
endpoints are in different sets. With E edges the sort dominates at
O(E log E); union-find operations are near-constant amortised.

Prim grows one tree from a start node using a min-heap of frontier edges,
O(E log V). For `--forest`, Prim restarts at each unvisited node; both
algorithms produce forests with the same total weight, which `--compare`
verifies. The reported total is the sum of selected edge weights, and the
verification line checks the spanning-tree edge count. A directed graph is
rejected because a minimum spanning tree is defined on undirected graphs.
