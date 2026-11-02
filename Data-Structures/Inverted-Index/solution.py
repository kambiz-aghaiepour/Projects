#!/usr/bin/env python3
"""Inverted index full-text search over a directory of plain-text files.

Builds an in-memory inverted index (term -> document -> token positions),
answers single-term, multi-term AND, and quoted phrase queries, and offers
both a one-shot CLI and an interactive search prompt.

Usage:
    python3 solution.py --demo
    python3 solution.py sample_docs -q '"full text search"'
    python3 solution.py sample_docs            # interactive prompt
"""

from __future__ import annotations

import argparse
import re
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path

TOKEN_RE = re.compile(r"[A-Za-z0-9]+(?:['\u2019][A-Za-z]+)*")
QUERY_RE = re.compile(r'"([^"]*)"|(\S+)')
SNIPPET_RADIUS = 55
SAMPLE_DIR = Path(__file__).resolve().parent / "sample_docs"


class QueryError(ValueError):
    """Raised when a query string cannot be parsed."""


@dataclass(frozen=True)
class Clause:
    """One required part of a query: a single term or a quoted phrase."""

    label: str
    words: tuple[str, ...]
    phrase: bool


@dataclass(frozen=True)
class Hit:
    """A ranked search result."""

    doc_id: str
    score: int
    frequencies: dict[str, int]
    snippet: str


def tokenize(text: str) -> list[str]:
    """Split text into lowercase alphanumeric tokens (apostrophes kept)."""
    return [match.group(0).lower() for match in TOKEN_RE.finditer(text)]


def parse_query(query: str) -> list[Clause]:
    """Parse a query into clauses, all of which must match (AND semantics).

    ``inverted index`` yields two term clauses; ``"inverted index"`` yields
    one phrase clause. Quoted and unquoted parts can be mixed.
    """
    clauses: list[Clause] = []
    if query.count('"') % 2:
        raise QueryError("unterminated quoted phrase")
    for match in QUERY_RE.finditer(query):
        phrase, word = match.groups()
        if phrase is not None:
            words = tuple(tokenize(phrase))
            if not words:
                raise QueryError("quoted phrase contains no searchable words")
            clauses.append(Clause(f'"{" ".join(words)}"', words, True))
        else:
            for token in tokenize(word):
                clauses.append(Clause(token, (token,), False))
    if not clauses:
        raise QueryError("query is empty")
    return clauses


def make_snippet(text: str, words: tuple[str, ...], radius: int = SNIPPET_RADIUS) -> str:
    """Return a one-line context window around the first occurrence of words."""
    flat = re.sub(r"\s+", " ", text).strip()
    if not flat:
        return ""
    pattern = r"\b" + r"\W+".join(re.escape(word) for word in words) + r"\b"
    match = re.search(pattern, flat, re.IGNORECASE)
    start = max(0, (match.start() if match else 0) - radius)
    end = min(len(flat), (match.end() if match else radius * 2) + radius)
    prefix = "..." if start > 0 else ""
    suffix = "..." if end < len(flat) else ""
    return f"{prefix}{flat[start:end]}{suffix}"


class InvertedIndex:
    """In-memory inverted index with positional postings."""

    def __init__(self) -> None:
        self._postings: dict[str, dict[str, list[int]]] = defaultdict(dict)
        self._tokens: dict[str, list[str]] = {}
        self._texts: dict[str, str] = {}

    def __len__(self) -> int:
        return len(self._tokens)

    @property
    def vocabulary_size(self) -> int:
        return len(self._postings)

    @property
    def token_count(self) -> int:
        return sum(len(tokens) for tokens in self._tokens.values())

    def document_ids(self) -> list[str]:
        return sorted(self._tokens)

    def add_document(self, doc_id: str, text: str) -> None:
        """Tokenize one document and record every term position."""
        if doc_id in self._tokens:
            raise ValueError(f"duplicate document id: {doc_id}")
        tokens = tokenize(text)
        self._tokens[doc_id] = tokens
        self._texts[doc_id] = text
        for position, token in enumerate(tokens):
            self._postings[token].setdefault(doc_id, []).append(position)

    def _clause_occurrences(self, clause: Clause) -> dict[str, int]:
        """Return {doc_id: occurrence_count} for one clause."""
        if not clause.phrase:
            return {
                doc_id: len(positions)
                for doc_id, positions in self._postings.get(clause.words[0], {}).items()
            }
        counts: dict[str, int] = {}
        first, rest = clause.words[0], clause.words[1:]
        candidates = set(self._postings.get(first, {}))
        for word in rest:
            candidates &= set(self._postings.get(word, {}))
        for doc_id in candidates:
            tokens = self._tokens[doc_id]
            total = 0
            for position in self._postings[first][doc_id]:
                if tuple(tokens[position:position + len(clause.words)]) == clause.words:
                    total += 1
            if total:
                counts[doc_id] = total
        return counts

    def search(self, query: str) -> list[Hit]:
        """Search for a query, returning every matching document ranked."""
        clauses = parse_query(query)
        per_clause = [self._clause_occurrences(clause) for clause in clauses]
        matching = set(per_clause[0])
        for occurrences in per_clause[1:]:
            matching &= set(occurrences)
        hits: list[Hit] = []
        for doc_id in matching:
            frequencies = {
                clause.label: occurrences[doc_id]
                for clause, occurrences in zip(clauses, per_clause)
            }
            hits.append(
                Hit(
                    doc_id=doc_id,
                    score=sum(frequencies.values()),
                    frequencies=frequencies,
                    snippet=make_snippet(self._texts[doc_id], clauses[0].words),
                )
            )
        hits.sort(key=lambda hit: (-hit.score, hit.doc_id))
        return hits

    def summary(self) -> str:
        """Human-readable index statistics."""
        docs = len(self._tokens)
        tokens = self.token_count
        average = tokens / docs if docs else 0.0
        occurrences = Counter(
            {
                term: sum(len(positions) for positions in postings.values())
                for term, postings in self._postings.items()
            }
        )
        top = ", ".join(
            f"{term} ({count})" for term, count in occurrences.most_common(5)
        )
        return (
            f"Documents: {docs}\n"
            f"Vocabulary: {self.vocabulary_size} terms\n"
            f"Tokens: {tokens}\n"
            f"Average document length: {average:.1f} tokens\n"
            f"Most frequent terms: {top}"
        )


def build_index(target: Path, extension: str = ".txt") -> InvertedIndex:
    """Index a single file or every matching file under a directory."""
    if not target.exists():
        raise FileNotFoundError(f"path does not exist: {target}")
    index = InvertedIndex()
    if target.is_file():
        index.add_document(target.name, target.read_text(encoding="utf-8", errors="replace"))
        return index
    if not target.is_dir():
        raise ValueError(f"not a file or directory: {target}")
    files = sorted(
        path for path in target.rglob(f"*{extension}") if path.is_file()
    )
    if not files:
        raise ValueError(f"no {extension} files found under {target}")
    for path in files:
        doc_id = path.relative_to(target).as_posix()
        index.add_document(doc_id, path.read_text(encoding="utf-8", errors="replace"))
    return index


def print_hits(hits: list[Hit], query: str, limit: int, snippets: bool = True) -> None:
    """Print a ranked result list."""
    if not hits:
        print(f"No documents matched: {query}")
        return
    shown = hits[:limit]
    print(f"{len(hits)} result(s) for {query}, showing {len(shown)}:")
    for rank, hit in enumerate(shown, start=1):
        detail = ", ".join(
            f"{term} x{count}" for term, count in sorted(hit.frequencies.items())
        )
        print(f"  {rank}. {hit.doc_id}  (score {hit.score}: {detail})")
        if snippets and hit.snippet:
            print(f"     {hit.snippet}")


def interactive(index: InvertedIndex, source: str, limit: int, snippets: bool) -> int:
    """Run a small read-eval-print loop over the index."""
    print(f"Indexed {len(index)} document(s) from {source}.")
    print('Type a query; terms are ANDed and "quoted phrases" are supported.')
    print("Commands: :help  :docs  :stats  :limit N  :quit")
    while True:
        try:
            raw = input("search> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return 0
        if not raw:
            continue
        if raw.startswith(":"):
            command, _, argument = raw.partition(" ")
            command = command.lower()
            if command in (":quit", ":q", ":exit"):
                return 0
            if command == ":help":
                print("  <terms>        documents containing every term")
                print('  "exact phrase" documents containing the phrase')
                print("  :docs          list indexed documents")
                print("  :stats         index statistics")
                print("  :limit N       change the number of displayed results")
                print("  :quit          leave the program")
            elif command == ":docs":
                for doc_id in index.document_ids():
                    print(f"  {doc_id}")
            elif command == ":stats":
                print(index.summary())
            elif command == ":limit":
                try:
                    new_limit = int(argument)
                    if new_limit < 1:
                        raise ValueError
                except ValueError:
                    print("usage: :limit <positive integer>")
                else:
                    limit = new_limit
                    print(f"Display limit set to {limit}.")
            else:
                print(f"unknown command: {command} (try :help)")
            continue
        try:
            hits = index.search(raw)
        except QueryError as exc:
            print(f"invalid query: {exc}")
            continue
        print_hits(hits, raw, limit, snippets)


def run_demo() -> int:
    """Scripted tour over the bundled sample documents."""
    print("Inverted Index demo")
    print("=" * 62)
    try:
        index = build_index(SAMPLE_DIR)
    except (OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(f"Built an in-memory index over {len(index)} bundled documents:")
    for doc_id in index.document_ids():
        print(f"  {doc_id}")
    print()
    print(index.summary())
    print()
    queries = [
        "index",
        "inverted index",
        '"inverted index"',
        '"full text search"',
        "search engine ranking",
        "quantum",
    ]
    for query in queries:
        hits = index.search(query)
        print("-" * 62)
        print_hits(hits, query, limit=3)
    print("-" * 62)
    print("Demo complete: single-term, AND, phrase, and empty result sets shown.")
    return 0


def main(argv: list[str] | None = None) -> int:
    """Parse arguments and run the requested mode."""
    parser = argparse.ArgumentParser(
        description="Build an in-memory inverted index over text files and search it.",
        epilog=(
            "Examples:\n"
            "  python3 solution.py --demo\n"
            "  python3 solution.py sample_docs -q 'inverted index'\n"
            "  python3 solution.py sample_docs --stats\n"
            "With no path the bundled sample_docs directory is indexed."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "path",
        nargs="?",
        help="file or directory to index (default: bundled sample_docs)",
    )
    parser.add_argument("--demo", action="store_true", help="run the scripted demonstration")
    parser.add_argument("-q", "--query", help="run one query and exit")
    parser.add_argument(
        "-e",
        "--extension",
        default=".txt",
        help="extension to index when given a directory (default: .txt)",
    )
    parser.add_argument(
        "-n", "--limit", type=int, default=10, help="results to display (default: 10)"
    )
    parser.add_argument("--stats", action="store_true", help="print index statistics and exit")
    parser.add_argument("--no-snippets", action="store_true", help="hide context snippets")
    args = parser.parse_args(argv)

    if args.demo:
        return run_demo()
    if args.limit < 1:
        parser.error("--limit must be at least 1")

    extension = args.extension if args.extension.startswith(".") else f".{args.extension}"
    target = Path(args.path) if args.path else SAMPLE_DIR
    try:
        index = build_index(target, extension)
    except (OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    snippets = not args.no_snippets
    if args.stats:
        print(index.summary())
        return 0
    if args.query is not None:
        try:
            hits = index.search(args.query)
        except QueryError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2
        print_hits(hits, args.query, args.limit, snippets)
        return 0
    return interactive(index, str(target), args.limit, snippets)


if __name__ == "__main__":
    sys.exit(main())
