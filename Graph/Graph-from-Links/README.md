# Graph from Links

Part of the **Graph** category — project `Graph/Graph-from-Links`.

## Problem

Create a program that will create a graph or network from a series of links.

## Features

- Accepts links in several common notations: `A-B`, `A->B`, `A B` and `A,B`.
- Optional numeric weights via a third field (`A B 4.5`) or suffix (`A->B:4.5`).
- Reads links from `--edges`, from one or more `--file`s, from piped stdin, or
  from an interactive prompt when run with no arguments.
- Builds directed or undirected graphs; parallel links and self-loops are kept.
- Adds isolated nodes with `--nodes` so they appear in the report.
- Reports node/link counts, unique and duplicate links, density, connected
  components (weak components for directed graphs), isolated nodes, a degree
  table and an adjacency list.
- Exports Graphviz DOT with `--dot` for visualisation in any DOT viewer.

## Requirements

Python 3.10+; standard library only. No third-party packages.

## Usage

```bash
python3 solution.py --demo
python3 solution.py --edges "ada-bob" "bob-carol" "carol-ada"
python3 solution.py --file links.txt --directed --dot network.dot
python3 solution.py                     # interactive prompt
cat links.txt | python3 solution.py     # read links from a pipe
```

Options:

- `--edges EDGE [EDGE ...]` — one or more links; repeat the flag as needed.
- `--file PATH` — read one link per line (blank lines and `#` comments ignored).
- `--nodes NODE [NODE ...]` — add nodes that have no links.
- `--directed` — build a directed graph (default is undirected).
- `--weighted` — interpret a third field as an edge weight.
- `--dot PATH` — also write the graph in Graphviz DOT format.
- `--demo` — run the scripted demonstration.

## Example Output

```
Graph from Links -- demo

Graph from links
================
Type: undirected, unweighted
Nodes: 9   Links: 8
Unique links: 7   Duplicate links: 1
Density: 0.194
Components: 4 (sizes: 3, 3, 2, 1)
Isolated nodes: iris

Degree (unique neighbours / links)
  ada     2 / 3
  bob     2 / 2
  carol   2 / 3
  ...
  iris    0 / 0

Adjacency list
--------------
  ada -- bob, carol x2
  bob -- ada, carol
  carol -- bob, ada x2
  ...
  iris  (isolated)

DOT preview
-----------
graph G {
  "ada";
  "bob";
  ...
```

## Implementation Notes

The reusable `graphcore.py` module stores an adjacency list whose entries are
`(neighbour, weight, edge_id)` tuples. Undirected edges are inserted at both
endpoints, so degrees, Euler trails and multigraph behaviour stay correct;
parallel edges and self-loops are preserved rather than collapsed.

Components are found with BFS over the undirected projection of the graph (so
directed input reports weak components). Density counts unique non-loop pairs
against the number of possible pairs. Parsing accepts whitespace, commas, `--`,
`->` or a single hyphen as separators; node names therefore cannot contain
those separators, spaces or `#`. Building the report is O(V + E).

## Files

- `solution.py` — CLI, report formatting and demonstration.
- `graphcore.py` — shared adjacency-list `Graph` class, parser and renderers.
