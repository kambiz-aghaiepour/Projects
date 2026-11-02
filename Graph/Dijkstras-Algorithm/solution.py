#!/usr/bin/env python3
"""Shortest paths with Dijkstra's algorithm and a binary heap.

Reads a weighted graph from an edge list, computes shortest distances from a
source node, reconstructs paths and reports unreachable nodes.  Negative edge
weights are rejected because Dijkstra's algorithm requires non-negative costs.
"""
from __future__ import annotations

import argparse
import heapq
import math
import sys

import graphcore as gl


def dijkstra(
    graph: gl.Graph, source: str
) -> tuple[dict[str, float], dict[str, str]]:
    """Return ``(distances, predecessors)`` for all nodes reachable from source.

    Raises ``ValueError`` for an unknown source or a negative edge weight.
    """
    if not graph.has_node(source):
        raise ValueError(f"source node {source!r} is not in the graph")
    if graph.has_negative_weight():
        bad = next(edge for edge in graph.edges if edge.weight < 0)
        raise ValueError(
            f"negative edge weight {gl.format_weight(bad.weight)} on "
            f"{bad.u}-{bad.v}; Dijkstra requires non-negative weights"
        )

    distances: dict[str, float] = {source: 0.0}
    predecessors: dict[str, str] = {}
    heap: list[tuple[float, str]] = [(0.0, source)]

    while heap:
        distance, node = heapq.heappop(heap)
        if distance > distances.get(node, math.inf):
            continue  # stale heap entry
        for nxt, weight, _idx in graph.incident(node):
            candidate = distance + weight
            if candidate < distances.get(nxt, math.inf):
                distances[nxt] = candidate
                predecessors[nxt] = node
                heapq.heappush(heap, (candidate, nxt))
    return distances, predecessors


def reconstruct_path(
    predecessors: dict[str, str], source: str, target: str
) -> list[str]:
    """Reconstruct the node sequence from source to target, or ``[]``."""
    if target == source:
        return [source]
    if target not in predecessors:
        return []
    path = [target]
    while path[-1] != source:
        path.append(predecessors[path[-1]])
    path.reverse()
    return path


def edge_weight(graph: gl.Graph, u: str, v: str) -> float:
    """Smallest weight among edges directly connecting ``u`` to ``v``."""
    weights = [
        weight for nxt, weight, _idx in graph.incident(u) if nxt == v
    ]
    if not weights:
        raise ValueError(f"no edge {u} -> {v}")
    return min(weights)


def format_table(
    graph: gl.Graph,
    distances: dict[str, float],
    predecessors: dict[str, str],
    source: str,
) -> str:
    """Render shortest distances and paths to every node."""
    reachable = sorted(
        (node for node in graph.nodes if node in distances),
        key=lambda node: (distances[node], node),
    )
    unreachable = sorted(
        node for node in graph.nodes if node not in distances
    )
    lines = [f"Shortest paths from {source}", "-" * (20 + len(source))]
    width = max((len(node) for node in graph.nodes), default=1)
    lines.append(f"  {'Node':<{width}}  {'Distance':>8}  Path")
    for node in reachable:
        path = " -> ".join(reconstruct_path(predecessors, source, node))
        lines.append(
            f"  {node:<{width}}  {gl.format_weight(distances[node]):>8}  {path}"
        )
    for node in unreachable:
        lines.append(f"  {node:<{width}}  {'-':>8}  unreachable")
    if unreachable:
        lines.append("Unreachable: " + ", ".join(unreachable))
    return "\n".join(lines)


def format_route(
    graph: gl.Graph,
    distances: dict[str, float],
    predecessors: dict[str, str],
    source: str,
    target: str,
) -> str:
    """Render one route hop by hop, including edge weights."""
    if target not in graph.nodes:
        raise ValueError(f"target node {target!r} is not in the graph")
    if target not in distances:
        return f"No path from {source} to {target}"
    path = reconstruct_path(predecessors, source, target)
    if not path:
        return f"No path from {source} to {target}"
    lines = [
        f"Shortest path {source} -> {target}: "
        f"{gl.format_weight(distances[target])}"
    ]
    for u, v in zip(path, path[1:]):
        lines.append(f"  {u} -> {v}   ({gl.format_weight(edge_weight(graph, u, v))})")
    hops = max(0, len(path) - 1)
    lines.append(
        f"  Total: {gl.format_weight(distances[target])} over {hops} edge"
        + ("" if hops == 1 else "s")
    )
    return "\n".join(lines)


DEMO_EDGES = [
    "A-B 4",
    "A-C 2",
    "B-C 1",
    "B-D 5",
    "C-D 8",
    "C-E 10",
    "D-E 2",
    "D-F 6",
    "E-F 3",
]


def demo() -> None:
    """Run a scripted undirected and directed demonstration."""
    print("Dijkstra's Algorithm -- demo")
    print()

    graph = gl.build_graph(DEMO_EDGES, weighted=True)
    graph.add_node("G")  # isolated: unreachable from A
    print("Undirected weighted graph")
    print("-------------------------")
    print(gl.format_adjacency(graph))
    print()
    distances, predecessors = dijkstra(graph, "A")
    print(format_table(graph, distances, predecessors, "A"))
    print()
    print(format_route(graph, distances, predecessors, "A", "F"))
    print()

    directed = gl.build_graph(
        ["A->B 1", "B->C 2", "A->C 5", "C->D 1", "D->B 1"],
        directed=True,
        weighted=True,
    )
    print("Directed graph (one-way edges)")
    print("------------------------------")
    print(gl.format_adjacency(directed))
    print()
    d_dist, d_prev = dijkstra(directed, "A")
    print(format_table(directed, d_dist, d_prev, "A"))
    print()
    d_from_d, prev_from_d = dijkstra(directed, "D")
    print(format_route(directed, d_from_d, prev_from_d, "D", "A"))


def make_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Find shortest paths with Dijkstra's algorithm (binary heap, "
            "non-negative weights only)."
        )
    )
    parser.add_argument(
        "--edges",
        nargs="+",
        action="append",
        metavar="EDGE",
        help="weighted edge(s), e.g. 'A B 4' or 'A->B:4' (repeatable)",
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
        "--source", metavar="NODE", help="source node (default: first node)"
    )
    parser.add_argument(
        "--target",
        metavar="NODE",
        help="print a detailed route to this node instead of the full table",
    )
    parser.add_argument(
        "--directed", action="store_true", help="treat edges as directed (default: undirected)"
    )
    parser.add_argument("--demo", action="store_true", help="run a scripted demonstration")
    return parser


def prompt_edges() -> list[str]:
    """Read weighted edges interactively until a blank line."""
    print("Enter weighted edges, one per line ('A B 4' or 'A->B:4'); blank line to finish.")
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
        interactive = False
        if not lines and sys.stdin.isatty():
            lines = prompt_edges()
            interactive = True
        elif not lines:
            lines = [line for line in sys.stdin.read().splitlines() if line.strip()]

        graph = gl.build_graph(lines, directed=args.directed, weighted=True)
        if graph.node_count == 0:
            print("error: no edges provided (use --edges, --file, or --demo)", file=sys.stderr)
            return 2

        source = args.source
        if source is None:
            default_source = graph.nodes[0]
            if interactive and sys.stdin.isatty():
                entered = input(f"Source node [{default_source}]: ").strip()
                source = entered or default_source
            else:
                source = default_source

        distances, predecessors = dijkstra(graph, source)
        if args.target:
            print(f"Graph: {gl.graph_summary(graph)}")
            print(format_route(graph, distances, predecessors, source, args.target))
        else:
            print(gl.graph_summary(graph))
            print(format_table(graph, distances, predecessors, source))
    except (ValueError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
