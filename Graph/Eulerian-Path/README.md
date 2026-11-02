# Eulerian Path

Part of the **Graph** category — project `Graph/Eulerian-Path`.

## Problem

Create a program which will take as an input a graph and output either a
Eulerian path or a Eulerian cycle, or state that it is not possible. A Eulerian
path starts at one node and traverses every edge of a graph through every node
and finishes at another node. A Eulerian cycle is a Eulerian path that starts
and finishes at the same node.

## Features

- Works with undirected and directed graphs (`--directed`).
- Reports **Eulerian cycle**, **Eulerian path**, or **not possible** with the
  exact reason (odd degrees, degree imbalance, or disconnected edges).
- Uses Hierholzer's algorithm to construct the trail, not just decide existence.
- Supports parallel edges and self-loops through edge-ID bookkeeping.
- Re-verifies the produced trail, confirming every edge is used exactly once.
- `--start NODE` forces a valid starting vertex for a cycle or either endpoint
  of a path.
- Reads edges from `--edges`, `--file`, piped stdin, or an interactive prompt.

## Requirements

Python 3.10+; standard library only. No third-party packages.

## Usage

```bash
python3 solution.py --demo
python3 solution.py --edges "A B" "B C" "C D" "D A"
python3 solution.py --edges "A->B" "B->C" "C->D" --directed
python3 solution.py --file edges.txt --start A
```

Options:

- `--edges EDGE [EDGE ...]` — edge specifications; repeatable.
- `--file PATH` — read one edge per line (blank lines and `#` comments ignored).
- `--directed` — treat edges as directed (default is undirected).
- `--start NODE` — require the trail to begin at this valid endpoint.
- `--demo` — run the scripted demonstration.

## Example Output

```
Eulerian Path -- demo

Undirected square (cycle)
-------------------------
undirected graph: 4 nodes, 4 edges
Eulerian trail: EULERIAN CYCLE
Start/end: A
Edges traversed: 4 of 4
Trail: A -> B -> C -> D -> A
Verified: every edge used exactly once

Undirected line (path)
----------------------
undirected graph: 5 nodes, 4 edges
Eulerian trail: EULERIAN PATH
Start: A   End: E
Edges traversed: 4 of 4
Trail: A -> B -> C -> D -> E
Verified: every edge used exactly once

Undirected star (not possible)
------------------------------
undirected graph: 4 nodes, 3 edges
Eulerian trail: NOT POSSIBLE
Reason: 4 vertices have odd degree; an Eulerian trail needs 0 (cycle) or 2 (path): S, A, B, C

Directed cycle
--------------
directed graph: 3 nodes, 3 edges
Eulerian trail: EULERIAN CYCLE
Start/end: A
Edges traversed: 3 of 3
Trail: A -> B -> C -> A
Verified: every edge used exactly once
```

## Implementation Notes

For an undirected graph, all vertices with non-zero degree must lie in one
component and the number of odd-degree vertices must be 0 (cycle) or 2 (path);
otherwise no trail exists. For a directed graph the weak connectivity condition
is the same, while `out-degree - in-degree` must be zero everywhere for a cycle
or `+1` at the start and `-1` at the end for a path. Isolated vertices are
ignored.

Hierholzer's algorithm is implemented iteratively with a pointer per vertex and
a `used` flag per edge ID, giving O(V + E) time and O(V + E) space. Because
edges are identified individually, parallel edges and self-loops work. The
resulting vertex sequence is checked against the edge multiset before printing;
`--start` is rejected when it is not a legal endpoint.
