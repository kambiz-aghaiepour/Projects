#!/usr/bin/env python3
"""Report connectivity of an undirected or directed graph.

Undirected graphs are split into connected components.  Directed graphs are
analysed both as weakly connected components (direction ignored) and as
strongly connected components (Kosaraju), with ``--strong`` selecting which
notion decides the pass/fail verdict.
"""
from __future__ import annotations

import argparse
import sys

import graphcore as gl


def sorted_components(graph: gl.Graph, components: list[list[str]]) -> list[list[str]]:
    """Largest components first, ties broken by first-seen node."""
    position = {node: index for index, node in enumerate(graph.nodes)}
    ordered = sorted(components, key=lambda comp: (-len(comp), position[comp[0]]))
    return [sorted(component) for component in ordered]


def component_lines(
    graph: gl.Graph, components: list[list[str]], label: str = "Component"
) -> list[str]:
    """Render numbered component membership lines."""
    lines: list[str] = []
    for index, component in enumerate(components, 1):
        if len(component) == 1 and graph.degree(component[0]) == 0:
            suffix = "  [isolated]"
        else:
            suffix = ""
        lines.append(
            f"  {label} {index} ({len(component)}): {', '.join(component)}{suffix}"
        )
    return lines


def undirected_report(graph: gl.Graph) -> str:
    components = sorted_components(graph, graph.components())
    lines = ["Graph connectivity", "=" * 18, gl.graph_summary(graph)]
    sizes = ", ".join(str(len(component)) for component in components)
    lines.append(f"Components: {len(components)} (sizes: {sizes})")
    lines.extend(component_lines(graph, components))
    isolated = [node for node in graph.nodes if graph.degree(node) == 0]
    lines.append("Isolated nodes: " + (", ".join(isolated) if isolated else "none"))
    if len(components) == 1:
        lines.append("Verdict: CONNECTED -- every node is reachable from every other")
    else:
        lines.append(f"Verdict: NOT CONNECTED -- {len(components)} separate components")
    return "\n".join(lines)


def directed_report(graph: gl.Graph, require_strong: bool) -> str:
    weak = sorted_components(graph, graph.components())
    strong = sorted_components(graph, graph.strong_components())
    lines = ["Graph connectivity", "=" * 18, gl.graph_summary(graph)]
    lines.append(f"Weak components: {len(weak)}")
    lines.extend(component_lines(graph, weak))
    lines.append(f"Weakly connected: {'YES' if len(weak) == 1 else 'NO'}")
    lines.append("")
    lines.append(f"Strongly connected components: {len(strong)}")
    lines.extend(component_lines(graph, strong, label="SCC"))
    strongly = len(strong) == 1
    lines.append(f"Strongly connected: {'YES' if strongly else 'NO'}")
    lines.append("")
    if require_strong:
        verdict = "CONNECTED" if strongly else "NOT CONNECTED"
        lines.append(f"Verdict (--strong): {verdict}")
    else:
        verdict = "CONNECTED" if len(weak) == 1 else "NOT CONNECTED"
        lines.append(f"Verdict (weak connectivity): {verdict}")
    return "\n".join(lines)


def report(graph: gl.Graph, require_strong: bool) -> str:
    if graph.directed:
        return directed_report(graph, require_strong)
    return undirected_report(graph)


def show(title: str, graph: gl.Graph, require_strong: bool = False) -> None:
    print(title)
    print("-" * len(title))
    print(report(graph, require_strong))
    print()


def disconnected_demo_graph() -> gl.Graph:
    """A graph with a real component, a small component and an isolated node."""
    graph = gl.build_graph(["A-B", "B-C", "D-E", "F-G"], weighted=False)
    graph.add_node("H")
    return graph


def demo() -> None:
    """Run scripted connected, disconnected, weak and strong examples."""
    print("Connected Graph -- demo")
    print()

    show(
        "Undirected: connected",
        gl.build_graph(["A-B", "B-C", "C-D", "D-A", "D-E"], weighted=False),
    )
    show(
        "Undirected: disconnected",
        disconnected_demo_graph(),
    )
    show(
        "Directed: weak but not strong",
        gl.build_graph(
            ["A->B", "B->C", "C->A", "C->D"], directed=True, weighted=False
        ),
    )
    show(
        "Directed: strongly connected",
        gl.build_graph(
            ["A->B", "B->C", "C->A", "C->D", "D->A"],
            directed=True,
            weighted=False,
        ),
    )


def make_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Check whether every node in a graph is connected."
    )
    parser.add_argument(
        "--edges",
        nargs="+",
        action="append",
        metavar="EDGE",
        help="edge specification(s), e.g. 'A B' (repeatable)",
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
        "--nodes",
        nargs="+",
        default=[],
        metavar="NODE",
        help="add isolated nodes (useful for testing disconnected graphs)",
    )
    parser.add_argument(
        "--directed", action="store_true", help="treat the graph as directed"
    )
    parser.add_argument(
        "--strong",
        action="store_true",
        help="for directed graphs, require strong connectivity for the verdict",
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
    if args.strong and not args.directed:
        print("error: --strong is only meaningful together with --directed", file=sys.stderr)
        return 2

    try:
        lines: list[str] = []
        for group in args.edges or []:
            lines.extend(group)
        lines.extend(gl.read_edge_lines(args.files))
        if not lines and not args.nodes and sys.stdin.isatty():
            lines = prompt_edges()
        elif not lines and not args.nodes:
            lines = [line for line in sys.stdin.read().splitlines() if line.strip()]

        graph = gl.build_graph(lines, directed=args.directed)
        for node in args.nodes:
            graph.add_node(node)
        if graph.node_count == 0:
            print("error: no nodes or edges provided (use --edges, --file, --nodes, or --demo)", file=sys.stderr)
            return 2
        print(report(graph, args.strong))
    except (ValueError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
