#!/usr/bin/env python3
"""A deliberately small, safe Markdown subset renderer.

Supports ATX headings (``#`` … ``####``), paragraphs, fenced code blocks,
unordered/ordered lists, block quotes, horizontal rules and the inline forms
``**bold**``, ``*italic*``, ```code``` and ``[label](url)``.  All input is
HTML-escaped first, and link targets are restricted to http(s), mailto, root
relative paths and fragments.
"""

from __future__ import annotations

import html
import re

_HEADING = re.compile(r"^(#{1,4})\s+(.*)$")
_ULIST = re.compile(r"^[-*]\s+(.*)$")
_OLIST = re.compile(r"^\d+\.\s+(.*)$")
_FENCE = re.compile(r"^```(\w*)\s*$")


def _inline(text: str) -> str:
    """Render inline markup on text that is already HTML-escaped."""
    stash: list[str] = []

    def keep_code(match: re.Match[str]) -> str:
        stash.append(f"<code>{match.group(1)}</code>")
        return f"\x00{len(stash) - 1}\x00"

    text = re.sub(r"`([^`]+)`", keep_code, text)

    def keep_link(match: re.Match[str]) -> str:
        label, url = match.group(1), match.group(2)
        if re.match(r"^(https?://|mailto:|/|#)", url):
            return f'<a href="{url}" rel="noopener noreferrer">{label}</a>'
        return label

    text = re.sub(r"\[([^\]]+)\]\(([^)\s]+)\)", keep_link, text)
    text = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(r"(?<!\*)\*([^*\n]+)\*(?!\*)", r"<em>\1</em>", text)
    for index, fragment in enumerate(stash):
        text = text.replace(f"\x00{index}\x00", fragment)
    return text


def render_markdown(source: str) -> str:
    """Convert a Markdown subset string to sanitised HTML."""
    lines = source.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    out: list[str] = []
    paragraph: list[str] = []
    i = 0

    def flush_paragraph() -> None:
        if paragraph:
            out.append(f"<p>{_inline(' '.join(paragraph))}</p>")
            paragraph.clear()

    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        fence = _FENCE.match(stripped)
        if fence:
            flush_paragraph()
            language = fence.group(1)
            i += 1
            code_lines: list[str] = []
            while i < len(lines) and not lines[i].strip().startswith("```"):
                code_lines.append(lines[i])
                i += 1
            i += 1  # closing fence (or end of document)
            class_attr = f' class="language-{html.escape(language)}"' if language else ""
            out.append(f"<pre><code{class_attr}>{html.escape(chr(10).join(code_lines))}</code></pre>")
            continue

        if not stripped:
            flush_paragraph()
            i += 1
            continue

        heading = _HEADING.match(stripped)
        if heading:
            flush_paragraph()
            level = len(heading.group(1))
            out.append(f"<h{level}>{_inline(html.escape(heading.group(2)))}</h{level}>")
            i += 1
            continue

        if re.fullmatch(r"(-{3,}|\*{3,}|_{3,})", stripped):
            flush_paragraph()
            out.append("<hr>")
            i += 1
            continue

        if stripped.startswith(">"):
            flush_paragraph()
            quote: list[str] = []
            while i < len(lines) and lines[i].strip().startswith(">"):
                quote.append(lines[i].strip()[1:].lstrip())
                i += 1
            out.append(f"<blockquote><p>{_inline(html.escape(' '.join(quote)))}</p></blockquote>")
            continue

        if _ULIST.match(stripped):
            flush_paragraph()
            items: list[str] = []
            while i < len(lines):
                match = _ULIST.match(lines[i].strip())
                if not match:
                    break
                items.append(f"<li>{_inline(html.escape(match.group(1)))}</li>")
                i += 1
            out.append("<ul>" + "".join(items) + "</ul>")
            continue

        if _OLIST.match(stripped):
            flush_paragraph()
            items = []
            while i < len(lines):
                match = _OLIST.match(lines[i].strip())
                if not match:
                    break
                items.append(f"<li>{_inline(html.escape(match.group(1)))}</li>")
                i += 1
            out.append("<ol>" + "".join(items) + "</ol>")
            continue

        paragraph.append(html.escape(stripped))
        i += 1

    flush_paragraph()
    return "\n".join(out)


def strip_markdown(source: str, limit: int = 200) -> str:
    """Produce a plain-text excerpt from Markdown source."""
    text = re.sub(r"```.*?```", " ", source, flags=re.DOTALL)
    text = re.sub(r"!\[[^\]]*\]\([^)]*\)", " ", text)
    text = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", text)
    text = re.sub(r"(?m)^\s*[-+*]\s+", "", text)
    text = re.sub(r"[#>*_`~]", "", text)
    text = re.sub(r"\s+([.,;:!?])", r"\1", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:limit].rstrip() + ("…" if len(text) > limit else "")


def slugify(value: str) -> str:
    """Turn a title into a URL slug (ASCII letters, digits and hyphens)."""
    value = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return value[:80] or "untitled"

