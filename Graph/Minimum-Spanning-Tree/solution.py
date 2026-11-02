#!/usr/bin/env python3
"""Minimum spanning tree via Kruskal's algorithm with union-find.

Kruskal sorts edges by weight and adds them when they join two different
components.  Prim's algorithm is available with ``--prim`` for comparison, and
``--forest`` builds a minimum spanning forest for disconnected input.
"""
from __future__ import annotations

import argparse
import heapq
import sys

import graphcore as gl


class UnionFind:
    """Disjoint-set forest with path halving and union by rank."""

    def __init__(self, nodes: list[str]) -> None:
        self.parent = {node: node for node in nodes}
        self.rank = {node: 0 for node in nodes}
        self.count = len(self.parent)

    def find(self, node: str) -> str:
        while self.parent[node] != node:
            self.parent[node] = self.parent[self.parent[node]]
            node = self.parent[node]
        return node

    def union(self, a: str, b: str) -> bool:
        """Join two sets; return False when they were already connected."""
        root_a, root_b = self.find(a), self.find(b)
        if root_a == root_b:
            return False
        if self.rank[root_a] < self.rank[root_b]:
            root_a, root_b = root_b, root_a
        self.parent[root_b] = root_a
        if self.rank[root_a] == self.rank[root_b]:
            self.rank[root_a] += 1
        self.count -= 1
        return True


def _check_undirected(graph: gl.Graph) -> None:
    if graph.directed:
        raise ValueError("minimum spanning trees require an undirected graph")


def kruskal(graph: gl.Graph, forest: bool = False) -> tuple[list[gl.Edge], float]:
    """Return the MST (or MSF) edges and total weight."""
    _check_undirected(graph)
    union_find = UnionFind(graph.nodes)
    chosen: list[gl.Edge] = []
    total = 0.0
    for edge in sorted(graph.edges, key=lambda e: (e.weight, e.idx)):
        if union_find.union(edge.u, edge.v):
            chosen.append(edge)
            total += edge.weight
    if not forest and union_find.count > 1:
        raise ValueError(
            f"graph is disconnected ({union_find.count} components); an MST "
            "requires a connected graph (use --forest for a spanning forest)"
        )
    return chosen, total


def prim_component(
    graph: gl.Graph, start: str
) -> tuple[list[gl.Edge], float, set[str]]:
    """Prim's algorithm on the component containing ``start``."""
    visited = {start}
    heap: list[tuple[float, str, str]] = []
    for nxt, weight, _idx in graph.incident(start):
        heapq.heappush(heap, (weight, nxt, start))
    chosen: list[gl.Edge] = []
    total = 0.0
    while heap:
        weight, node, parent = heapq.heappop(heap)
        if node in visited:
            continue
        visited.add(node)
        chosen.append(gl.Edge(parent, node, weight, -1))
        total += weight
        for nxt, next_weight, _idx in graph.incident(node):
            if nxt not in visited:
                heapq.heappush(heap, (next_weight, nxt, node))
    return chosen, total, visited


def prim(
    graph: gl.Graph, forest: bool = False
) -> tuple[list[gl.Edge], float]:
    """Return the MST (or MSF) using Prim's algorithm."""
    _check_undirected(graph)
    if graph.node_count == 0:
        return [], 0.0
    remaining = set(graph.nodes)
    chosen: list[gl.Edge] = []
    total = 0.0
    for start in graph.nodes:
        if start not in remaining:
            continue
        edges, subtotal, reached = prim_component(graph, start)
        chosen.extend(edges)
        total += subtotal
        remaining -= reached
        if not forest and remaining:
            raise ValueError(
                "graph is disconnected; an MST requires a connected graph "
                "(use --forest for a spanning forest)"
            )
    return chosen, total


def format_result(
    graph: gl.Graph,
    edges: list[gl.Edge],
    total: float,
    algorithm: str,
    forest: bool,
) -> str:
    """Render an MST or MSF result."""
    title = "Minimum spanning forest" if forest else "Minimum spanning tree"
    lines = [f"{title} ({algorithm})", "=" * len(f"{title} ({algorithm})")]
    lines.append(gl.graph_summary(graph))
    lines.append(f"Edges selected: {len(edges)}")
    for edge in edges:
        lines.append(
            f"  {edge.u} -- {edge.v}   weight {gl.format_weight(edge.weight)}"
        )
    lines.append(f"Total weight: {gl.format_weight(total)}")
    if forest:
        components = len(graph.components())
        expected = graph.node_count - components
        lines.append(f"Input components: {components}")
        lines.append(
            f"Verification: {len(edges)} edges = {graph.node_count} nodes "
            f"- {components} components (expected {expected})"
        )
    else:
        lines.append(
            f"Verification: {len(edges)} edges = {graph.node_count} nodes - 1, "
            "all nodes connected, acyclic by construction"
        )
    return "\n".join(lines)


DEMO_EDGES = [
    "A-B 7",
    "A-D 5",
    "B-C 8",
    "B-D 9",
    "B-E 7",
    "C-E 5",
    "D-E 15",
    "D-F 6",
    "E-F 8",
    "E-G 9",
    "F-G 11",
]


def demo() -> None:
    """Run connected Kruskal/Prim and disconnected forest examples."""
    print("Minimum Spanning Tree -- demo")
    print()

    graph = gl.build_graph(DEMO_EDGES, weighted=True)
    kruskal_edges, kruskal_total = kruskal(graph)
    print(format_result(graph, kruskal_edges, kruskal_total, "Kruskal", forest=False))
    print()

    prim_edges, prim_total = prim(graph)
    print("Prim comparison")
    print("---------------")
    print(f"Prim total: {gl.format_weight(prim_total)} ({len(prim_edges)} edges)")
    print(f"Kruskal total: {gl.format_weight(kruskal_total)} ({len(kruskal_edges)} edges)")
    print(f"Match: {'YES' if prim_total == kruskal_total else 'NO'}")
    print()

    disconnected = gl.build_graph(
        ["A-B 1", "B-C 2", "C-A 4", "D-E 3", "E-F 4", "F-D 5"], weighted=True
    )
    disconnected.add_node("G")
    print("Disconnected input")
    print("------------------")
    try:
        kruskal(disconnected)
    except ValueError as exc:
        print(f"Connected-only check: {exc}")
    print()
    forest_edges, forest_total = kruskal(disconnected, forest=True)
    print(
        format_result(
            disconnected, forest_edges, forest_total, "Kruskal", forest=True
        )
    )


def make_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Compute a minimum spanning tree with Kruskal's algorithm "
            "(union-find), optionally with Prim's algorithm."
        )
    )
    parser.add_argument(
        "--edges",
        nargs="+",
        action="append",
        metavar="EDGE",
        help="weighted edge(s), e.g. 'A B 4' (repeatable)",
    )
    parser.add_argument(
        "--file",
        action="append",
        default=[],
        dest="files",
        metavar="PATH",
        help="read weighted edges from a text file (repeatable)",
    )
    parser.add_argument(
        "--prim", action="store_true", help="use Prim's algorithm instead of Kruskal's"
    )
    parser.add_argument(
        "--forest",
        action="store_true",
        help="allow disconnected input and build a minimum spanning forest",
    )
    parser.add_argument(
        "--compare",
        action="store_true",
        help="run both algorithms and report whether their totals agree",
    )
    parser.add_argument("--demo", action="store_true", help="run a scripted demonstration")
    return parser


def prompt_edges() -> list[str]:
    """Read weighted edges interactively until a blank line."""
    print("Enter weighted edges, one per line ('A B 4'); blank line to finish.")
    lines: list[str] = []
    while True:
        try:
            line = input("edge> ")
        except EOFError:
            break
        if not line.strip():
            break
        lines.append(line)
    return lines


def main(argv: list[str] | None = None) -> int:
    parser = make_parser()
    args = parser.parse_args(argv)
    if args.demo:
        demo()
        return 0

    try:
        lines: list[str] = []
        for group in args.edges or []:
            lines.extend(group)
        lines.extend(gl.read_edge_lines(args.files))
        if not lines and sys.stdin.isatty():
            lines = prompt_edges()
        elif not lines:
            lines = [line for line in sys.stdin.read().splitlines() if line.strip()]

        graph = gl.build_graph(lines, weighted=True)
        if graph.node_count == 0:
            print("error: no edges provided (use --edges, --file, or --demo)", file=sys.stderr)
            return 2

        algorithm = prim if args.prim else kruskal
        edges, total = algorithm(graph, forest=args.forest)
        print(format_result(graph, edges, total, "Prim" if args.prim else "Kruskal", args.forest))
        if args.compare:
            other = kruskal if args.prim else prim
            other_edges, other_total = other(graph, forest=args.forest)
            print()
            print(
                f"Cross-check: {len(other_edges)} edges, total "
                f"{gl.format_weight(other_total)}; "
                f"match = {'YES' if other_total == total else 'NO'}"
            )
    except (ValueError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
