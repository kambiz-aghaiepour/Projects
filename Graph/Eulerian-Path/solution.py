#!/usr/bin/env python3
"""Find an Eulerian path or cycle using Hierholzer's algorithm.

The program checks connectivity and vertex degrees, reports whether a trail is
impossible, and otherwise prints the vertex sequence that traverses every edge
exactly once.  Both undirected and directed graphs are supported.
"""
from __future__ import annotations

import argparse
import sys
from collections import Counter
from dataclasses import dataclass

import graphcore as gl


@dataclass
class TrailResult:
    """Outcome of the Eulerian analysis."""

    kind: str  # "cycle", "path" or "none"
    start: str | None = None
    end: str | None = None
    trail: list[str] | None = None
    reason: str = ""


def hierholzer(graph: gl.Graph, start: str) -> list[str]:
    """Return a vertex trail consuming every edge exactly once."""
    adjacency = {node: graph.incident(node) for node in graph.nodes}
    pointer = {node: 0 for node in graph.nodes}
    used = [False] * graph.edge_count
    stack = [start]
    circuit: list[str] = []

    while stack:
        node = stack[-1]
        entries = adjacency[node]
        while pointer[node] < len(entries) and used[entries[pointer[node]][2]]:
            pointer[node] += 1
        if pointer[node] < len(entries):
            nxt, _weight, edge_id = entries[pointer[node]]
            used[edge_id] = True
            stack.append(nxt)
        else:
            circuit.append(stack.pop())
    circuit.reverse()
    return circuit


def verify_trail(graph: gl.Graph, trail: list[str]) -> bool:
    """Confirm that ``trail`` uses every edge exactly once."""
    if len(trail) != graph.edge_count + 1:
        return False
    if graph.directed:
        remaining = Counter((edge.u, edge.v) for edge in graph.edges)
        steps = zip(trail, trail[1:])
    else:
        remaining = Counter(
            (min(edge.u, edge.v), max(edge.u, edge.v)) for edge in graph.edges
        )
        steps = (
            (min(u, v), max(u, v)) for u, v in zip(trail, trail[1:])
        )
    for step in steps:
        if remaining[step] <= 0:
            return False
        remaining[step] -= 1
    return not any(remaining.values())


def _edge_components(graph: gl.Graph) -> list[list[str]]:
    """Weak components that contain at least one edge."""
    return [
        component
        for component in graph.components()
        if any(graph.degree(node) > 0 for node in component)
    ]


def _undirected_conditions(graph: gl.Graph) -> TrailResult:
    odd = [node for node in graph.nodes if graph.degree(node) % 2 == 1]
    if len(odd) not in (0, 2):
        listed = ", ".join(odd[:8]) + (" ..." if len(odd) > 8 else "")
        return TrailResult(
            "none",
            reason=(
                f"{len(odd)} vertices have odd degree; an Eulerian trail needs "
                f"0 (cycle) or 2 (path): {listed}"
            ),
        )
    start = odd[0] if odd else next(
        node for node in graph.nodes if graph.degree(node) > 0
    )
    end = odd[1] if len(odd) == 2 else start
    return TrailResult("path" if odd else "cycle", start=start, end=end)


def _directed_conditions(graph: gl.Graph) -> TrailResult:
    balance = {
        node: graph.out_degree(node) - graph.in_degree(node)
        for node in graph.nodes
    }
    nonzero = {node: diff for node, diff in balance.items() if diff != 0}
    if not nonzero:
        start = next(node for node in graph.nodes if graph.degree(node) > 0)
        return TrailResult("cycle", start=start, end=start)

    values = sorted(nonzero.values())
    if len(nonzero) == 2 and values == [-1, 1]:
        start = next(node for node, diff in nonzero.items() if diff == 1)
        end = next(node for node, diff in nonzero.items() if diff == -1)
        return TrailResult("path", start=start, end=end)

    shown = ", ".join(f"{node}:{diff:+d}" for node, diff in list(nonzero.items())[:6])
    return TrailResult(
        "none",
        reason=(
            "out-degree minus in-degree must be all zero (cycle) or one +1/-1 "
            f"pair (path); got {shown}"
        ),
    )


def eulerian_trail(graph: gl.Graph, start: str | None = None) -> TrailResult:
    """Analyse ``graph`` and return an Eulerian cycle, path, or a reason."""
    if start is not None and not graph.has_node(start):
        raise ValueError(f"unknown start node {start!r}")
    if graph.edge_count == 0:
        chosen = start or (graph.nodes[0] if graph.nodes else None)
        return TrailResult(
            "cycle", start=chosen, end=chosen, trail=[chosen] if chosen else [],
            reason="graph has no edges (trivial cycle)",
        )

    components = _edge_components(graph)
    if len(components) != 1:
        return TrailResult(
            "none",
            reason=(
                f"vertices with edges lie in {len(components)} disconnected "
                "components; an Eulerian trail must stay in one"
            ),
        )

    result = (
        _directed_conditions(graph) if graph.directed else _undirected_conditions(graph)
    )
    if result.kind == "none":
        return result

    if start is not None:
        if result.kind == "path" and start != result.start:
            raise ValueError(
                f"an Eulerian path must start at {result.start!r}, not {start!r}"
            )
        if result.kind == "cycle" and graph.degree(start) == 0:
            raise ValueError(f"start node {start!r} has no edges")
        result.start = start
        if result.kind == "cycle":
            result.end = start

    trail = hierholzer(graph, result.start or "")
    if not verify_trail(graph, trail):
        raise RuntimeError("internal error: constructed trail does not cover every edge")
    result.trail = trail
    return result


def format_result(graph: gl.Graph, result: TrailResult) -> str:
    """Render an analysis result for humans."""
    if result.kind == "none":
        return f"Eulerian trail: NOT POSSIBLE\nReason: {result.reason}"
    label = "Eulerian cycle" if result.kind == "cycle" else "Eulerian path"
    lines = [f"Eulerian trail: {label.upper()}"]
    if result.kind == "path":
        lines.append(f"Start: {result.start}   End: {result.end}")
    else:
        lines.append(f"Start/end: {result.start}")
    lines.append(f"Edges traversed: {graph.edge_count} of {graph.edge_count}")
    lines.append("Trail: " + " -> ".join(result.trail or []))
    lines.append("Verified: every edge used exactly once")
    return "\n".join(lines)


def show(title: str, graph: gl.Graph, start: str | None = None) -> None:
    print(title)
    print("-" * len(title))
    print(gl.graph_summary(graph))
    print(format_result(graph, eulerian_trail(graph, start)))
    print()


def demo() -> None:
    """Run scripted undirected and directed examples."""
    print("Eulerian Path -- demo")
    print()

    show(
        "Undirected square (cycle)",
        gl.build_graph(["A-B", "B-C", "C-D", "D-A"], weighted=False),
    )
    show(
        "Undirected line (path)",
        gl.build_graph(["A-B", "B-C", "C-D", "D-E"], weighted=False),
    )
    show(
        "Undirected star (not possible)",
        gl.build_graph(["S-A", "S-B", "S-C"], weighted=False),
    )
    show(
        "Undirected disconnected (not possible)",
        gl.build_graph(
            ["A-B", "B-C", "C-A", "D-E", "E-F", "F-D"], weighted=False
        ),
    )
    show(
        "Directed cycle",
        gl.build_graph(["A->B", "B->C", "C->A"], directed=True, weighted=False),
    )
    show(
        "Directed path",
        gl.build_graph(
            ["A->B", "B->C", "C->D"], directed=True, weighted=False
        ),
    )
    show(
        "Directed imbalanced (not possible)",
        gl.build_graph(
            ["A->B", "A->C", "B->C"], directed=True, weighted=False
        ),
    )


def make_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Decide whether a graph has an Eulerian path or cycle and print one "
            "using Hierholzer's algorithm."
        )
    )
    parser.add_argument(
        "--edges",
        nargs="+",
        action="append",
        metavar="EDGE",
        help="edge specification(s), e.g. 'A B' or 'A->B' (repeatable)",
    )
    parser.add_argument(
        "--file",
        action="append",
        default=[],
        dest="files",
        metavar="PATH",
        help="read edges from a text file (repeatable)",
    )
    parser.add_argument(
        "--directed", action="store_true", help="treat edges as directed"
    )
    parser.add_argument(
        "--start",
        metavar="NODE",
        help="require the trail to start at NODE (must be a valid endpoint)",
    )
    parser.add_argument("--demo", action="store_true", help="run a scripted demonstration")
    return parser


def prompt_edges() -> list[str]:
    """Read edges interactively until a blank line."""
    print("Enter edges, one per line ('A B', 'A-B', 'A->B'); blank line to finish.")
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

        graph = gl.build_graph(lines, directed=args.directed)
        if graph.edge_count == 0:
            print("error: no edges provided (use --edges, --file, or --demo)", file=sys.stderr)
            return 2
        print(gl.graph_summary(graph))
        print(format_result(graph, eulerian_trail(graph, args.start)))
    except (ValueError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
