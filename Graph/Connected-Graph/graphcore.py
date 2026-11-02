#!/usr/bin/env python3
"""Dependency-free adjacency-list graph helpers for the Graph projects.

This module is vendored into every Graph project directory so each project
stays self-contained.  It supports directed and undirected multigraphs with
numeric weights, traversal, weak/strong connectivity, edge-list parsing and
simple text/DOT rendering.
"""
from __future__ import annotations

import math
import re
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence

__all__ = [
    "Edge",
    "Graph",
    "build_graph",
    "format_adjacency",
    "format_weight",
    "graph_summary",
    "parse_edge_line",
    "read_edge_lines",
    "to_dot",
]

_NUMBER_RE = re.compile(r"^[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?$")
_ARROW_RE = re.compile(r"\s*(?:-->|->|--|→)\s*")


@dataclass(frozen=True)
class Edge:
    """A single edge record.  ``idx`` distinguishes parallel copies."""

    u: str
    v: str
    weight: float
    idx: int


class Graph:
    """An adjacency-list graph with optional direction and edge weights.

    Parallel edges and self-loops are preserved.  For undirected graphs every
    edge appears in both endpoint lists (a self-loop therefore appears twice),
    which keeps degree and Euler-trail calculations correct.
    """

    def __init__(self, directed: bool = False) -> None:
        self.directed = bool(directed)
        self._adj: dict[str, list[tuple[str, float, int]]] = {}
        self._edges: list[Edge] = []

    # ------------------------------------------------------------------
    # Construction
    # ------------------------------------------------------------------
    def add_node(self, node: str) -> None:
        """Add ``node`` if it is not present yet."""
        self._adj.setdefault(str(node), [])

    def add_edge(self, u: str, v: str, weight: float = 1.0) -> None:
        """Add an edge, creating missing endpoints."""
        try:
            weight = float(weight)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"invalid edge weight {weight!r}") from exc
        if not math.isfinite(weight):
            raise ValueError(f"edge weight must be finite, got {weight!r}")
        u, v = str(u), str(v)
        self.add_node(u)
        self.add_node(v)
        idx = len(self._edges)
        self._edges.append(Edge(u, v, weight, idx))
        self._adj[u].append((v, weight, idx))
        if not self.directed:
            self._adj[v].append((u, weight, idx))

    # ------------------------------------------------------------------
    # Basic accessors
    # ------------------------------------------------------------------
    @property
    def nodes(self) -> list[str]:
        """Nodes in insertion order."""
        return list(self._adj)

    @property
    def edges(self) -> list[Edge]:
        """One record per edge, in insertion order."""
        return list(self._edges)

    @property
    def node_count(self) -> int:
        return len(self._adj)

    @property
    def edge_count(self) -> int:
        return len(self._edges)

    @property
    def weighted(self) -> bool:
        """True when at least one edge weight differs from 1."""
        return any(e.weight != 1.0 for e in self._edges)

    def has_node(self, node: str) -> bool:
        return node in self._adj

    def incident(self, node: str) -> list[tuple[str, float, int]]:
        """Raw adjacency entries: ``(neighbour, weight, edge_id)``.

        Undirected edges appear in both endpoints' lists.  Callers that need
        each logical edge once should use :attr:`edges`.
        """
        return list(self._adj.get(node, ()))

    def neighbors(self, node: str, *, unique: bool = True) -> list[str]:
        """Successor (or undirected neighbour) names in insertion order."""
        seen: set[str] = set()
        result: list[str] = []
        for nxt, _weight, _idx in self._adj.get(node, ()):
            if unique and nxt in seen:
                continue
            seen.add(nxt)
            result.append(nxt)
        return result

    def out_degree(self, node: str) -> int:
        """Number of outgoing half-edges (self-loops count once)."""
        return len(self._adj.get(node, ()))

    def in_degree(self, node: str) -> int:
        """Number of incoming half-edges (self-loops count once)."""
        return sum(1 for edge in self._edges if edge.v == node)

    def degree(self, node: str) -> int:
        """Total degree: undirected half-edges, or in+out when directed."""
        if self.directed:
            return self.out_degree(node) + self.in_degree(node)
        return len(self._adj.get(node, ()))

    def is_isolated(self, node: str) -> bool:
        return self.degree(node) == 0

    # ------------------------------------------------------------------
    # Traversal and connectivity
    # ------------------------------------------------------------------
    def bfs(self, start: str) -> list[str]:
        """Breadth-first visit order from ``start``."""
        if start not in self._adj:
            raise ValueError(f"unknown start node {start!r}")
        seen = {start}
        queue = deque([start])
        order: list[str] = []
        while queue:
            node = queue.popleft()
            order.append(node)
            for nxt in self.neighbors(node):
                if nxt not in seen:
                    seen.add(nxt)
                    queue.append(nxt)
        return order

    def dfs(self, start: str) -> list[str]:
        """Depth-first pre-order from ``start`` (iterative)."""
        if start not in self._adj:
            raise ValueError(f"unknown start node {start!r}")
        seen: set[str] = set()
        stack = [start]
        order: list[str] = []
        while stack:
            node = stack.pop()
            if node in seen:
                continue
            seen.add(node)
            order.append(node)
            for nxt in reversed(self.neighbors(node)):
                if nxt not in seen:
                    stack.append(nxt)
        return order

    def components(self) -> list[list[str]]:
        """Weakly connected components (edge direction ignored)."""
        adjacency: dict[str, list[str]] = {node: [] for node in self._adj}
        for edge in self._edges:
            if edge.u == edge.v:
                adjacency[edge.u].append(edge.u)
            else:
                adjacency[edge.u].append(edge.v)
                adjacency[edge.v].append(edge.u)
        for node, neighbours in adjacency.items():
            adjacency[node] = list(dict.fromkeys(neighbours))

        seen: set[str] = set()
        result: list[list[str]] = []
        for start in self._adj:
            if start in seen:
                continue
            component: list[str] = []
            queue = deque([start])
            seen.add(start)
            while queue:
                node = queue.popleft()
                component.append(node)
                for nxt in adjacency[node]:
                    if nxt not in seen:
                        seen.add(nxt)
                        queue.append(nxt)
            result.append(component)
        return result

    def is_connected(self) -> bool:
        """True when the graph has at most one weak component.

        An empty graph is treated as vacuously connected.
        """
        return len(self.components()) <= 1

    def strong_components(self) -> list[list[str]]:
        """Strongly connected components via iterative Kosaraju.

        Undirected graphs simply return their weak components.
        """
        if not self.directed:
            return self.components()

        successors = {node: self.neighbors(node) for node in self._adj}
        visited: set[str] = set()
        finish_order: list[str] = []
        for start in self._adj:
            if start in visited:
                continue
            visited.add(start)
            stack: list[tuple[str, int]] = [(start, 0)]
            while stack:
                node, index = stack[-1]
                if index < len(successors[node]):
                    nxt = successors[node][index]
                    stack[-1] = (node, index + 1)
                    if nxt not in visited:
                        visited.add(nxt)
                        stack.append((nxt, 0))
                else:
                    finish_order.append(node)
                    stack.pop()

        reverse: dict[str, list[str]] = {node: [] for node in self._adj}
        for edge in self._edges:
            reverse[edge.v].append(edge.u)
        for node in reverse:
            reverse[node] = list(dict.fromkeys(reverse[node]))

        assigned: set[str] = set()
        result: list[list[str]] = []
        for start in reversed(finish_order):
            if start in assigned:
                continue
            component: list[str] = []
            walk_stack = [start]
            assigned.add(start)
            while walk_stack:
                node = walk_stack.pop()
                component.append(node)
                for prev in reverse[node]:
                    if prev not in assigned:
                        assigned.add(prev)
                        walk_stack.append(prev)
            result.append(component)
        return result

    def is_strongly_connected(self) -> bool:
        """True when the whole graph is one strongly connected component."""
        return len(self.strong_components()) <= 1

    def density(self) -> float:
        """Edge density based on unique pairs, ignoring self-loops."""
        count = self.node_count
        if count < 2:
            return 0.0
        pairs: set[tuple[str, str]] = set()
        for edge in self._edges:
            if edge.u == edge.v:
                continue
            pairs.add((edge.u, edge.v) if self.directed else (min(edge.u, edge.v), max(edge.u, edge.v)))
        possible = count * (count - 1) if self.directed else count * (count - 1) / 2
        return len(pairs) / possible

    def has_negative_weight(self) -> bool:
        return any(e.weight < 0 for e in self._edges)


# ----------------------------------------------------------------------
# Parsing
# ----------------------------------------------------------------------
def parse_edge_line(
    line: str,
    *,
    default_weight: float = 1.0,
    allow_weight: bool = True,
) -> tuple[str, str, float] | None:
    """Parse one edge specification.

    Accepted forms (whitespace, comma, ``--`` and ``->`` all separate the two
    endpoints)::

        A B            A,B           A--B          A->B
        A B 4.5        A,B,4.5       A--B:4.5      A->B:4.5

    Blank lines and ``#`` comments return ``None``.  Bad input raises
    :class:`ValueError` with the offending line included.
    """
    text = line.strip()
    if not text or text.startswith("#"):
        return None
    text = re.split(r"\s+#", text, maxsplit=1)[0].strip()
    if not text:
        return None

    text = _ARROW_RE.sub(" ", text)
    if "," in text:
        parts = [part.strip() for part in text.split(",") if part.strip()]
    else:
        parts = text.split()

    # A lone "A-B" (or "A-B:4") needs the hyphen split before field parsing.
    if len(parts) == 1:
        token = parts[0]
        suffix: str | None = None
        head, sep, tail = token.rpartition(":")
        if sep and _NUMBER_RE.match(tail.strip()):
            token, suffix = head.strip(), tail.strip()
        if "-" in token:
            left, _, right = token.partition("-")
            if left.strip() and right.strip():
                parts = [left.strip(), right.strip()]
                if suffix is not None:
                    parts.append(suffix)

    # "A-B 4": a hyphenated endpoint followed by a separate weight field.
    if len(parts) == 2 and "-" in parts[0] and _NUMBER_RE.match(parts[1]):
        left, _, right = parts[0].partition("-")
        if left.strip() and right.strip():
            parts = [left.strip(), right.strip(), parts[1]]

    # A trailing ":weight" on the second field, e.g. "A B:4".
    if len(parts) == 2:
        head, sep, tail = parts[-1].rpartition(":")
        if sep and _NUMBER_RE.match(tail.strip()):
            parts[-1] = head.strip()
            parts.append(tail.strip())

    if len(parts) == 2:
        u, v = parts
        weight = float(default_weight)
    elif len(parts) == 3:
        if not allow_weight:
            raise ValueError(f"unexpected third field in edge {line!r} (use --weighted)")
        u, v, weight_text = parts
        if not _NUMBER_RE.match(weight_text):
            raise ValueError(f"invalid weight {weight_text!r} in edge {line!r}")
        weight = float(weight_text)
    else:
        raise ValueError(f"expected 'U V [weight]', got {line!r}")

    u, v = u.strip(), v.strip()
    if not u or not v:
        raise ValueError(f"empty endpoint in edge {line!r}")
    if not math.isfinite(float(weight)):
        raise ValueError(f"non-finite weight in edge {line!r}")
    return u, v, float(weight)


def read_edge_lines(paths: Sequence[str]) -> list[str]:
    """Read all lines from edge-list files, raising a clear error on failure."""
    lines: list[str] = []
    for raw_path in paths:
        path = Path(raw_path)
        try:
            lines.extend(path.read_text(encoding="utf-8").splitlines())
        except OSError as exc:
            raise ValueError(f"cannot read edge file {raw_path!r}: {exc}") from exc
    return lines


def build_graph(
    lines: Iterable[str],
    *,
    directed: bool = False,
    weighted: bool = True,
    default_weight: float = 1.0,
) -> Graph:
    """Build a graph from edge specifications."""
    graph = Graph(directed=directed)
    for line in lines:
        spec = parse_edge_line(
            line, default_weight=default_weight, allow_weight=weighted
        )
        if spec is not None:
            graph.add_edge(*spec)
    return graph


# ----------------------------------------------------------------------
# Rendering
# ----------------------------------------------------------------------
def format_weight(weight: float) -> str:
    """Render integral weights without a trailing ``.0``."""
    return str(int(weight)) if float(weight).is_integer() else f"{weight:g}"


def format_adjacency(graph: Graph, *, show_weights: bool | None = None) -> str:
    """Return a readable adjacency list, collapsing parallel edges."""
    if show_weights is None:
        show_weights = graph.weighted
    arrow = " -> " if graph.directed else " -- "
    lines: list[str] = []
    for node in graph.nodes:
        groups: dict[str, list[float]] = {}
        for nxt, weight, _idx in graph.incident(node):
            groups.setdefault(nxt, []).append(weight)
        rendered: list[str] = []
        for nxt, weights in groups.items():
            text = nxt
            if show_weights:
                text += f"({format_weight(min(weights))})"
            if len(weights) > 1:
                text += f" x{len(weights)}"
            rendered.append(text)
        if rendered:
            lines.append(f"  {node}{arrow}{', '.join(rendered)}")
        else:
            lines.append(f"  {node}  (isolated)")
    return "\n".join(lines)


def _dot_escape(text: str) -> str:
    """Escape a node name for a quoted DOT identifier."""
    return text.replace("\\", "\\\\").replace('"', '\\"')


def to_dot(graph: Graph, name: str = "G") -> str:
    """Render the graph in Graphviz DOT format."""
    keyword = "digraph" if graph.directed else "graph"
    arrow = "->" if graph.directed else "--"
    lines = [f"{keyword} {name} {{"]
    for node in graph.nodes:
        lines.append(f'  "{_dot_escape(node)}";')
    for edge in graph.edges:
        attrs = f' [label="{format_weight(edge.weight)}"]' if graph.weighted else ""
        lines.append(
            f'  "{_dot_escape(edge.u)}" {arrow} "{_dot_escape(edge.v)}"{attrs};'
        )
    lines.append("}")
    return "\n".join(lines)


def graph_summary(graph: Graph) -> str:
    """One-line description used by several programs."""
    kind = "directed" if graph.directed else "undirected"
    weighted = ", weighted" if graph.weighted else ""
    return (
        f"{kind}{weighted} graph: {graph.node_count} nodes, "
        f"{graph.edge_count} edges"
    )
