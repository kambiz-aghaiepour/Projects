#!/usr/bin/env python3
"""Build a graph (network) from a series of links and inspect its structure.

Links may be written as ``A-B``, ``A->B``, ``A B`` or ``A,B`` with an optional
weight as a third field.  The program prints node/link counts, density,
components, a degree table and an adjacency list, and can export Graphviz DOT.
"""
from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path

import graphcore as gl

DEMO_LINKS = [
    "ada -- bob",
    "bob -- carol",
    "carol -- ada",
    "ada -- carol",  # duplicate link
    "dave,erin",
    "erin -> frank",
    "frank -- dave",
    "gina -- hugo",
]
DEMO_NODES = ["iris"]  # an isolated node


def make_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Create a graph from a list of links and print a structural report.",
        epilog=(
            "Link formats: 'A B', 'A,B', 'A-B', 'A->B', optionally followed by "
            "a weight (third field or ':weight')."
        ),
    )
    parser.add_argument(
        "--edges",
        nargs="+",
        action="append",
        metavar="EDGE",
        help="one or more link specifications (repeatable)",
    )
    parser.add_argument(
        "--file",
        action="append",
        default=[],
        dest="files",
        metavar="PATH",
        help="read links from a text file (one per line; repeatable)",
    )
    parser.add_argument(
        "--nodes",
        nargs="+",
        default=[],
        metavar="NODE",
        help="add isolated nodes that have no links",
    )
    parser.add_argument(
        "--directed", action="store_true", help="build a directed graph (default: undirected)"
    )
    parser.add_argument(
        "--weighted",
        action="store_true",
        help="interpret a third field as an edge weight",
    )
    parser.add_argument(
        "--dot", metavar="PATH", help="also write the graph to PATH in Graphviz DOT format"
    )
    parser.add_argument("--demo", action="store_true", help="run a scripted demonstration")
    return parser


def collect_link_lines(args: argparse.Namespace) -> list[str]:
    """Flatten --edges groups and append --file contents."""
    lines: list[str] = []
    for group in args.edges or []:
        lines.extend(group)
    lines.extend(gl.read_edge_lines(args.files))
    return lines


def prompt_links() -> list[str]:
    """Read links interactively, ending on an empty line."""
    print("Paste links, one per line ('A-B', 'A->B', 'A B', 'A,B').")
    print("Finish with an empty line.")
    lines: list[str] = []
    while True:
        try:
            line = input("link> ")
        except EOFError:
            break
        if not line.strip():
            break
        lines.append(line)
    return lines


def build_from_args(args: argparse.Namespace) -> gl.Graph:
    """Build the graph from CLI arguments, a pipe, or an interactive prompt."""
    lines = collect_link_lines(args)
    if not lines and not args.nodes:
        if sys.stdin.isatty():
            lines = prompt_links()
        else:
            lines = [line for line in sys.stdin.read().splitlines() if line.strip()]
    graph = gl.build_graph(
        lines, directed=args.directed, weighted=args.weighted
    )
    for node in args.nodes:
        graph.add_node(node)
    return graph


def link_report(graph: gl.Graph) -> str:
    """Build a human-readable structural report."""
    lines = ["Graph from links", "=" * 16]
    kind = "directed" if graph.directed else "undirected"
    weight_kind = "weighted" if graph.weighted else "unweighted"
    lines.append(f"Type: {kind}, {weight_kind}")
    lines.append(f"Nodes: {graph.node_count}   Links: {graph.edge_count}")

    keys = [
        (edge.u, edge.v)
        if graph.directed
        else (min(edge.u, edge.v), max(edge.u, edge.v))
        for edge in graph.edges
    ]
    counts = Counter(keys)
    duplicates = sum(count - 1 for count in counts.values() if count > 1)
    lines.append(f"Unique links: {len(counts)}   Duplicate links: {duplicates}")
    lines.append(f"Density: {graph.density():.3f}")

    components = sorted(graph.components(), key=lambda c: (-len(c), c[0]))
    sizes = ", ".join(str(len(component)) for component in components)
    lines.append(f"Components: {len(components)} (sizes: {sizes})")
    isolated = [node for node in graph.nodes if graph.degree(node) == 0]
    lines.append("Isolated nodes: " + (", ".join(isolated) if isolated else "none"))
    lines.append("")

    lines.append(
        "Degree (unique out-neighbours / in+out links)"
        if graph.directed
        else "Degree (unique neighbours / links)"
    )
    width = max((len(node) for node in graph.nodes), default=1)
    for node in sorted(graph.nodes, key=lambda n: (-len(graph.neighbors(n)), n)):
        links = (
            graph.out_degree(node) + graph.in_degree(node)
            if graph.directed
            else sum(
                1 for edge in graph.edges if edge.u == node or edge.v == node
            )
        )
        lines.append(
            f"  {node:<{width}}  {len(graph.neighbors(node)):>2} / {links}"
        )
    lines.append("")
    lines.append("Adjacency list")
    lines.append("--------------")
    lines.append(gl.format_adjacency(graph))
    return "\n".join(lines)


def dot_preview(graph: gl.Graph, limit: int = 10) -> str:
    """Return the first few DOT lines for display."""
    dot_lines = gl.to_dot(graph).splitlines()
    shown = dot_lines[:limit]
    if len(dot_lines) > limit:
        shown.append("  ...")
    return "\n".join(shown)


def demo() -> None:
    """Run a non-interactive demonstration."""
    print("Graph from Links -- demo")
    print()
    graph = gl.build_graph(DEMO_LINKS, weighted=False)
    for node in DEMO_NODES:
        graph.add_node(node)
    print(link_report(graph))
    print()
    print("DOT preview")
    print("-----------")
    print(dot_preview(graph))
    print()

    print("Directed example")
    print("----------------")
    directed = gl.build_graph(
        ["A->B", "B->C", "C->A", "A->D", "D->C"], directed=True, weighted=False
    )
    print(f"Nodes: {directed.node_count}   Links: {directed.edge_count}")
    print(gl.format_adjacency(directed))


def main(argv: list[str] | None = None) -> int:
    parser = make_parser()
    args = parser.parse_args(argv)

    if args.demo:
        demo()
        return 0

    try:
        graph = build_from_args(args)
        if graph.node_count == 0:
            print(
                "error: no links provided (use --edges, --file, --nodes, or --demo)",
                file=sys.stderr,
            )
            return 2
        print(link_report(graph))
        if args.dot:
            Path(args.dot).write_text(gl.to_dot(graph) + "\n", encoding="utf-8")
            print(f"\nWrote DOT graph to {args.dot}")
    except (ValueError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
