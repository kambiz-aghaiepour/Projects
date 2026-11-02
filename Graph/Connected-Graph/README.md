# Connected Graph

Part of the **Graph** category — project `Graph/Connected-Graph`.

## Problem

Create a program which takes a graph as an input and outputs whether every node
is connected or not.

## Features

- Undirected graphs: connected-component decomposition with sizes and isolated
  nodes, plus a clear connected / not-connected verdict.
- Directed graphs: reports both **weak** components (direction ignored) and
  **strongly connected components** (Kosaraju).
- `--strong` makes strong connectivity the pass/fail requirement for directed
  graphs.
- Adds isolated nodes with `--nodes` so they are included in the analysis.
- Reads edges from `--edges`, `--file`, piped stdin, or an interactive prompt.

## Requirements

Python 3.10+; standard library only. No third-party packages.

## Usage

```bash
python3 solution.py --demo
python3 solution.py --edges "A B" "B C" "C D"
python3 solution.py --edges "A->B" "B->C" "C->A" --directed
python3 solution.py --file edges.txt --directed --strong
python3 solution.py --nodes A B C        # three isolated nodes
```

Options:

- `--edges EDGE [EDGE ...]` — edge specifications; repeatable.
- `--file PATH` — read one edge per line; repeatable.
- `--nodes NODE [NODE ...]` — add isolated nodes.
- `--directed` — treat the graph as directed.
- `--strong` — for directed graphs, decide the verdict using strong
  connectivity instead of weak connectivity.
- `--demo` — run the scripted demonstration.

## Example Output

```
Connected Graph -- demo

Undirected: connected
---------------------
Graph connectivity
==================
undirected graph: 5 nodes, 5 edges
Components: 1 (sizes: 5)
  Component 1 (5): A, B, C, D, E
Isolated nodes: none
Verdict: CONNECTED -- every node is reachable from every other

Undirected: disconnected
------------------------
Graph connectivity
==================
undirected graph: 8 nodes, 4 edges
Components: 4 (sizes: 3, 2, 2, 1)
  Component 1 (3): A, B, C
  Component 2 (2): D, E
  Component 3 (2): F, G
  Component 4 (1): H  [isolated]
Isolated nodes: H
Verdict: NOT CONNECTED -- 4 separate components

Directed: weak but not strong
-----------------------------
Graph connectivity
==================
directed graph: 4 nodes, 4 edges
Weak components: 1
  Component 1 (4): A, B, C, D
Weakly connected: YES

Strongly connected components: 2
  SCC 1 (3): A, B, C
  SCC 2 (1): D
Strongly connected: NO

Verdict (weak connectivity): CONNECTED
```

## Implementation Notes

Undirected components are found by breadth-first search from every unvisited
node. For directed graphs the same BFS runs over an undirected projection
(each edge usable both ways) to obtain weak components, while Kosaraju's
algorithm — an iterative finishing-order DFS followed by a DFS on the reversed
graph — produces strongly connected components.

Both passes are O(V + E) time and space. A single node is connected; the CLI
rejects empty input. `--strong` without `--directed` is reported as a usage
error because strong connectivity has no distinct meaning for undirected
graphs.
