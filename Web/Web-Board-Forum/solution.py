#!/usr/bin/env python3
"""Web Board: a small threaded discussion forum.

Boards contain threads, threads contain posts.  Visitors pick a display name
for each post; the browser's HttpOnly session cookie owns the posts it creates,
so authors may edit or delete their own writing while a moderator (key from
``FORUM_MODERATOR_KEY`` or generated at startup) can lock, pin, edit and delete
anything.  Everything is stored in SQLite; lists are paginated.

``--demo`` starts an ephemeral server and drives boards, threads, quoting,
editing, ownership checks, pagination and moderation over real HTTP.
"""

from __future__ import annotations

import argparse
import hashlib
import hmac
import html
import http.cookiejar
import json
import math
import os
import re
import secrets
import sqlite3
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from forum_store import ForumStore

PER_PAGE = 10
MAX_TITLE = 140
MAX_AUTHOR = 40
MAX_BODY = 8_000

CSS = """
:root { color-scheme: dark; }
* { box-sizing: border-box; }
body { margin:0; background:#10151c; color:#e7e2d6; font-family: system-ui, -apple-system, 'Segoe UI', sans-serif; line-height:1.55; }
a { color:#e9b872; text-decoration:none; }
a:hover { text-decoration:underline; }
header { border-bottom:1px solid #26303c; background:#151c25; }
header .inner { max-width:1000px; margin:0 auto; padding:16px 22px; display:flex; align-items:center; gap:22px; flex-wrap:wrap; }
.brand { font-family: ui-monospace, 'SFMono-Regular', Consolas, monospace; font-weight:700; letter-spacing:-.02em;
  font-size:1.2rem; color:#f0e7d6; }
nav { display:flex; gap:16px; margin-left:auto; font-size:.9rem; align-items:center; }
main { max-width:1000px; margin:0 auto; padding:34px 22px 70px; }
h1 { font-size:2rem; letter-spacing:-.02em; margin:0 0 8px; }
h2 { font-size:1.3rem; margin:0; }
.lead { color:#9aa6b4; margin:0 0 24px; }
.crumbs { font-size:.85rem; color:#8b98a7; margin-bottom:14px; }
.board-grid { display:grid; grid-template-columns:repeat(auto-fill,minmax(280px,1fr)); gap:18px; }
.board-card { background:#171f29; border:1px solid #26303c; border-radius:10px; padding:20px; }
.board-card h2 { margin-bottom:4px; }
.board-card p { color:#9aa6b4; min-height:44px; }
.stats { font-size:.8rem; color:#7f8c9b; border-top:1px solid #26303c; padding-top:12px; margin-top:10px; }
.stats span { margin-right:6px; white-space:nowrap; }
.stats span:not(:last-child)::after { content:' ·'; color:#4d5a69; }
table { width:100%; border-collapse:collapse; }
th, td { text-align:left; padding:11px 10px; border-bottom:1px solid #202a35; vertical-align:top; }
th { font-size:.72rem; text-transform:uppercase; letter-spacing:.08em; color:#7f8c9b; }
.thread-title { font-weight:600; }
.badge { display:inline-block; padding:1px 8px; border-radius:99px; font-size:.68rem; font-weight:700;
  letter-spacing:.06em; text-transform:uppercase; vertical-align:middle; }
.badge.locked { background:#3a2a2a; color:#f0a8a8; }
.badge.pinned { background:#3a3420; color:#f0d38a; }
.badge.mod { background:#1f3340; color:#9ad4e8; }
.muted { color:#7f8c9b; font-size:.82rem; }
.form-box { background:#171f29; border:1px solid #26303c; border-radius:10px; padding:20px; margin-top:26px; }
label { display:block; font-size:.75rem; text-transform:uppercase; letter-spacing:.07em; color:#8b98a7; margin:14px 0 6px; }
input[type=text], textarea { width:100%; padding:10px 12px; border-radius:7px; border:1px solid #354150;
  background:#0d1319; color:#e7e2d6; font:inherit; }
textarea { min-height:130px; resize:vertical; }
button { cursor:pointer; border:0; border-radius:6px; padding:9px 17px; font:600 .88rem system-ui,sans-serif;
  background:#e9b872; color:#241a0c; }
button.secondary { background:#2a3542; color:#dfe6ee; }
button.danger { background:#a63d3d; color:#fff2f0; }
button:hover { filter:brightness(1.07); }
.actions { display:flex; gap:9px; flex-wrap:wrap; align-items:center; margin-top:16px; }
.inline { display:inline; margin:0; }
.post { display:grid; grid-template-columns:52px 1fr; gap:16px; padding:20px 0; border-bottom:1px solid #202a35; }
.avatar { width:44px; height:44px; border-radius:8px; background:#243140; color:#e9b872; display:flex;
  align-items:center; justify-content:center; font-weight:700; font-size:1.1rem; }
.post-head { display:flex; gap:12px; align-items:baseline; flex-wrap:wrap; }
.author { font-weight:700; color:#f0e7d6; }
.post-body { overflow-wrap:anywhere; margin-top:8px; color:#d6d1c4; }
.post-body blockquote { margin:9px 0; padding:8px 14px; border-left:3px solid #4d6072;
  background:#111923; color:#aeb9c6; font-style:italic; border-radius:0 6px 6px 0; }
.post.deleted .post-body { color:#6f7a87; font-style:italic; }
.post-actions { display:flex; gap:14px; margin-top:8px; font-size:.8rem; }
.notice { padding:12px 15px; border-radius:7px; background:#1d2b23; border:1px solid #35553f;
  margin:0 0 20px; font-size:.9rem; }
.notice.error { background:#33201f; border-color:#6d3a36; }
.notice.locked { background:#2e2a1c; border-color:#5e512c; }
.pager { display:flex; gap:8px; margin:22px 0; font-size:.9rem; align-items:center; }
.pager a, .pager span { padding:5px 11px; border:1px solid #2b3644; border-radius:6px; }
.pager .current { background:#e9b872; color:#241a0c; border-color:#e9b872; font-weight:700; }
.empty { border:1px dashed #354150; border-radius:10px; padding:30px; color:#8b98a7; margin-top:20px; }
.mod-table { background:#171f29; border:1px solid #26303c; border-radius:10px; overflow:hidden; }
footer { border-top:1px solid #26303c; text-align:center; padding:20px; color:#66727f; font-size:.8rem; }
"""


def fmt_time(timestamp: float | None) -> str:
    """Format a Unix timestamp, or a dash when missing."""
    return time.strftime("%Y-%m-%d %H:%M", time.localtime(timestamp)) if timestamp else "—"


def plural(count: int, singular: str, plural_form: str | None = None) -> str:
    """Return ``count`` with a correctly pluralised noun."""
    word = singular if count == 1 else (plural_form or singular + "s")
    return f"{count} {word}"


def format_body(body: str) -> str:
    """Escape a post body, rendering leading ``>`` lines as a quote block."""
    parts: list[str] = []
    quote: list[str] = []

    def flush_quote() -> None:
        if quote:
            parts.append("<blockquote>" + "<br>".join(quote) + "</blockquote>")
            quote.clear()

    for line in body.splitlines():
        stripped = line.lstrip()
        if stripped.startswith(">"):
            quote.append(html.escape(stripped[1:].lstrip()))
        else:
            flush_quote()
            parts.append(html.escape(line))
    flush_quote()
    return "<br>".join(parts)


def quote_source(post: sqlite3.Row) -> str:
    """Build the prefilled quote block for a reply."""
    lines = (post["body"] or "").splitlines() or [""]
    quoted = "\n".join("> " + line for line in lines[:8])
    if len(lines) > 8:
        quoted += "\n> …"
    return f"> {post['author']} wrote:\n{quoted}\n\n"


def page_numbers(page: int, pages: int) -> list[int | None]:
    """Compact pagination: first, last and a window around the current page."""
    if pages <= 7:
        return list(range(1, pages + 1))
    wanted = {1, pages, page - 1, page, page + 1}
    wanted = {p for p in wanted if 1 <= p <= pages}
    result: list[int | None] = []
    previous = 0
    for number in sorted(wanted):
        if number - previous > 1:
            result.append(None)
        result.append(number)
        previous = number
    return result


def pager(base: str, page: int, pages: int) -> str:
    """Render pagination links for ``base`` (which already contains `?` or not)."""
    if pages <= 1:
        return ""
    separator = "&" if "?" in base else "?"
    parts = [f'<div class="pager"><span>{page} / {pages}</span>']
    for number in page_numbers(page, pages):
        if number is None:
            parts.append("<span>…</span>")
        elif number == page:
            parts.append(f'<span class="current">{number}</span>')
        else:
            parts.append(f'<a href="{html.escape(base)}{separator}page={number}">{number}</a>')
    parts.append("</div>")
    return "".join(parts)


def layout(title: str, body: str, is_mod: bool = False) -> str:
    """Shared page chrome."""
    mod_link = ('<a href="/mod">Moderation</a>' if is_mod else "")
    badge = '<span class="badge mod">moderator</span>' if is_mod else ""
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(title)}</title><style>{CSS}</style></head>
<body>
<header><div class="inner"><a class="brand" href="/">the web board</a>
<nav><a href="/">Boards</a>{mod_link}<span class="muted">{badge}</span></nav></div></header>
<main>{body}</main>
<footer>the web board · SQLite · no accounts, just names and good faith</footer>
</body></html>"""


def boards_page(boards: list[sqlite3.Row]) -> str:
    cards = "".join(
        f"""<div class="board-card">
  <h2><a href="/b/{html.escape(b['slug'])}">{html.escape(b['name'])}</a></h2>
  <p>{html.escape(b['description'])}</p>
  <div class="stats"><span>{plural(b['thread_count'], 'thread')}</span>
    <span>{plural(b['post_count'], 'post')}</span><span>last: {fmt_time(b['last_at'])}</span></div>
</div>""" for b in boards
    )
    return layout("The Web Board", f"""<h1>The Web Board</h1>
<p class="lead">A quiet place for you and your buddies to post, administer and share thoughts.</p>
<div class="board-grid">{cards}</div>""")


def board_page(board: sqlite3.Row, threads: list[sqlite3.Row], page: int, pages: int,
               error: str = "", values: dict[str, str] | None = None) -> str:
    values = values or {}
    if threads:
        rows = "".join(f"""<tr>
  <td><a class="thread-title" href="/t/{t['id']}">{html.escape(t['title'])}</a>
    {'<span class="badge pinned">pinned</span>' if t['pinned'] else ''}
    {'<span class="badge locked">locked</span>' if t['locked'] else ''}
    <div class="muted">by {html.escape(t['first_author'] or t['author'])}</div></td>
  <td>{plural(max(0, t['post_count'] - 1), 'reply', 'replies')}</td>
  <td class="muted">{fmt_time(t['updated_at'])}</td>
</tr>""" for t in threads)
        listing = f"""<table><thead><tr><th>Thread</th><th>Replies</th><th>Last activity</th></tr></thead>
<tbody>{rows}</tbody></table>"""
    else:
        listing = '<div class="empty">No threads yet. Start the first conversation below.</div>'
    error_html = f'<p class="notice error">{html.escape(error)}</p>' if error else ""
    return layout(board["name"], f"""<p class="crumbs"><a href="/">Boards</a> / {html.escape(board['name'])}</p>
<h1>{html.escape(board['name'])}</h1><p class="lead">{html.escape(board['description'])}</p>
{pager(f'/b/{board["slug"]}', page, pages)}
{error_html}{listing}
{pager(f'/b/{board["slug"]}', page, pages)}
<div class="form-box">
<h2>Start a new thread</h2>
<form method="post" action="/b/{html.escape(board['slug'])}/new">
  <label for="title">Title</label>
  <input id="title" type="text" name="title" maxlength="{MAX_TITLE}" required value="{html.escape(values.get('title', ''))}">
  <label for="author">Your name</label>
  <input id="author" type="text" name="author" maxlength="{MAX_AUTHOR}" required value="{html.escape(values.get('author', ''))}">
  <label for="body">First post</label>
  <textarea id="body" name="body" maxlength="{MAX_BODY}" required>{html.escape(values.get('body', ''))}</textarea>
  <div class="actions"><button type="submit">Post thread</button></div>
</form></div>""")


def thread_page(thread: sqlite3.Row, posts: list[sqlite3.Row], page: int, pages: int,
                editable: set[int], quote_text: str, quote_id: int | None) -> str:
    rendered = []
    for post in posts:
        if post["deleted"]:
            rendered.append(f"""<article class="post deleted" id="p{post['id']}">
  <div class="avatar">×</div><div><div class="post-head"><span class="author">{html.escape(post['author'])}</span>
  <span class="muted">{fmt_time(post['created_at'])}</span></div>
  <div class="post-body">This post was deleted.</div></div></article>""")
            continue
        can_edit = post["id"] in editable
        controls = [f'<a href="?quote={post["id"]}#reply">Quote</a>']
        if can_edit:
            controls.append(f'<a href="/t/{thread["id"]}/edit/{post["id"]}">Edit</a>')
            controls.append(f"""<form class="inline" method="post" action="/t/{thread['id']}/delete/{post['id']}"
              onsubmit="return confirm('Delete this post?')"><button class="danger"
              style="padding:2px 9px;font-size:.75rem">Delete</button></form>""")
        edited = f' <span class="muted">· edited {fmt_time(post["edited_at"])}</span>' if post["edited_at"] else ""
        rendered.append(f"""<article class="post" id="p{post['id']}">
  <div class="avatar">{html.escape((post['author'] or '?')[0].upper())}</div>
  <div><div class="post-head"><span class="author">{html.escape(post['author'])}</span>
    <span class="muted">{fmt_time(post['created_at'])}</span>{edited}</div>
    {f'<div class="muted"><a href="#p{post["quote_id"]}">replying to post #{post["quote_id"]}</a></div>' if post['quote_id'] else ''}
    <div class="post-body">{format_body(post['body'])}</div>
    <div class="post-actions">{''.join(controls)}</div></div></article>""")
    if thread["locked"]:
        reply = '<p class="notice locked">This thread is locked. New replies are disabled.</p>'
    else:
        reply = f"""<div class="form-box" id="reply"><h2>Reply</h2>
<form method="post" action="/t/{thread['id']}/reply">
  <input type="hidden" name="quote_id" value="{quote_id or ''}">
  <label for="author">Your name</label>
  <input id="author" type="text" name="author" maxlength="{MAX_AUTHOR}" required>
  <label for="body">Message</label>
  <textarea id="body" name="body" maxlength="{MAX_BODY}" required>{html.escape(quote_text)}</textarea>
  <div class="actions"><button type="submit">Post reply</button></div>
</form></div>"""
    badges = ('<span class="badge pinned">pinned</span>' if thread["pinned"] else "") + \
             ('<span class="badge locked">locked</span>' if thread["locked"] else "")
    return layout(thread["title"], f"""<p class="crumbs"><a href="/">Boards</a> /
<a href="/b/{html.escape(thread['board_slug'])}">{html.escape(thread['board_name'])}</a> / thread</p>
<h1>{html.escape(thread['title'])} {badges}</h1>
<p class="lead">Started by {html.escape(thread['author'])} · {fmt_time(thread['created_at'])}</p>
{pager(f'/t/{thread["id"]}', page, pages)}
{''.join(rendered)}
{pager(f'/t/{thread["id"]}', page, pages)}
{reply}""")



class App:
    """Application state."""

    def __init__(self, db_path: Path, mod_key: str | None = None, verbose: bool = False) -> None:
        self.store = ForumStore(db_path)
        self.verbose = verbose
        self.generated_key = ""
        if mod_key is None:
            mod_key = os.environ.get("FORUM_MODERATOR_KEY", "")
        if not mod_key:
            mod_key = secrets.token_urlsafe(9)
            self.generated_key = mod_key
        self.mod_key_hash = hashlib.sha256(mod_key.encode("utf-8")).digest()

    def check_key(self, candidate: str) -> bool:
        return hmac.compare_digest(hashlib.sha256(candidate.encode("utf-8")).digest(), self.mod_key_hash)


class Handler(BaseHTTPRequestHandler):
    """Forum routes."""

    server_version = "WebBoard/1.0"

    @property
    def app(self) -> App:
        return self.server.app  # type: ignore[attr-defined]

    def log_message(self, format: str, *args: object) -> None:  # noqa: A002
        if self.app.verbose:
            super().log_message(format, *args)

    # ---------- plumbing ----------

    def _send(self, status: int, body: bytes, content_type: str, headers: dict[str, str] | None = None) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "same-origin")
        new_sid = getattr(self, "_new_sid", "")
        if new_sid:
            self.send_header("Set-Cookie", f"forum_sid={new_sid}; Path=/; HttpOnly; SameSite=Lax; Max-Age=2592000")
        for key, value in (headers or {}).items():
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(body)

    def _html(self, status: int, markup: str, headers: dict[str, str] | None = None) -> None:
        self._send(status, markup.encode("utf-8"), "text/html; charset=utf-8", headers)

    def _redirect(self, location: str) -> None:
        self._send(303, b"", "text/plain; charset=utf-8", {"Location": location})

    def _session(self) -> sqlite3.Row:
        """Return the current session, creating one (and its cookie) if needed."""
        raw = self.headers.get("Cookie", "")
        sid = ""
        if raw:
            try:
                morsel = SimpleCookie(raw).get("forum_sid")
                sid = morsel.value if morsel else ""
            except Exception:
                sid = ""
        row = self.app.store.session(sid) if sid else None
        if row is None:
            sid = self.app.store.new_session()
            self._new_sid = sid
            row = self.app.store.session(sid)
        assert row is not None
        return row

    def _form(self) -> dict[str, str]:
        try:
            length = int(self.headers.get("Content-Length", "0") or 0)
        except ValueError:
            length = 0
        if length <= 0 or length > MAX_BODY + 20_000:
            return {}
        raw = self.rfile.read(length).decode("utf-8", "replace")
        return {k: v[0] for k, v in urllib.parse.parse_qs(raw, keep_blank_values=True).items()}

    def _can_modify(self, post: sqlite3.Row, session: sqlite3.Row) -> bool:
        return bool(session["is_mod"]) or self.app.store.is_owner(session["sid"], post["id"])

    def _error(self, status: int, message: str, session: sqlite3.Row) -> None:
        body = (f"<h1>{status}</h1><p class='lead'>{html.escape(message)}</p>"
                "<p><a href='/'>Back to the boards</a></p>")
        self._html(status, layout(str(status), body, bool(session["is_mod"])))

    def _not_found(self, session: sqlite3.Row) -> None:
        self._error(404, "That board, thread or post does not exist.", session)

    @staticmethod
    def _int(value: str) -> int | None:
        return int(value) if value.isdigit() else None

    # ---------- GET ----------

    def do_GET(self) -> None:  # noqa: N802
        parsed = urllib.parse.urlparse(self.path)
        segments = [part for part in parsed.path.split("/") if part]
        query = urllib.parse.parse_qs(parsed.query)
        session = self._session()
        try:
            if not segments:
                self._html(200, boards_page(self.app.store.boards()))
            elif segments == ["health"]:
                self._send(200, json.dumps(self.app.store.counts()).encode(), "application/json")
            elif segments == ["mod"]:
                self._mod_dashboard(session)
            elif segments == ["mod", "login"]:
                self._mod_login_page(session)
            elif segments[0] == "b" and len(segments) == 2:
                self._board(segments[1], query, session)
            elif segments[0] == "t" and len(segments) in (2, 4):
                thread_id = self._int(segments[1]) if len(segments) >= 2 else None
                if thread_id is None:
                    self._not_found(session)
                elif len(segments) == 2:
                    self._thread(thread_id, query, session)
                elif segments[2] == "edit":
                    post_id = self._int(segments[3])
                    self._edit_form(thread_id, post_id, session)
                else:
                    self._not_found(session)
            else:
                self._not_found(session)
        except BrokenPipeError:
            pass

    def _board(self, slug: str, query: dict[str, list[str]], session: sqlite3.Row) -> None:
        board = self.app.store.board(slug)
        if board is None:
            self._not_found(session)
            return
        try:
            page = max(1, int((query.get("page") or ["1"])[0]))
        except ValueError:
            page = 1
        threads, total = self.app.store.board_threads(board["id"], page, PER_PAGE)
        pages = max(1, math.ceil(total / PER_PAGE))
        if page > pages:
            page = pages
            threads, total = self.app.store.board_threads(board["id"], page, PER_PAGE)
        self._html(200, board_page(board, threads, page, pages))

    def _thread(self, thread_id: int, query: dict[str, list[str]], session: sqlite3.Row) -> None:
        thread = self.app.store.thread(thread_id)
        if thread is None:
            self._not_found(session)
            return
        try:
            page = max(1, int((query.get("page") or ["1"])[0]))
        except ValueError:
            page = 1
        total = self.app.store.post_count(thread_id)
        pages = max(1, math.ceil(total / PER_PAGE))
        page = min(page, pages)
        posts, _total = self.app.store.posts(thread_id, page, PER_PAGE)
        editable = {p["id"] for p in posts
                    if session["is_mod"] or self.app.store.is_owner(session["sid"], p["id"])}
        quote_text, quote_id = "", None
        raw_quote = (query.get("quote") or [""])[0]
        if raw_quote.isdigit():
            source = self.app.store.post(int(raw_quote))
            if source is not None and source["thread_id"] == thread_id and not source["deleted"]:
                quote_text, quote_id = quote_source(source), int(raw_quote)
        markup = thread_page(thread, posts, page, pages, editable, quote_text, quote_id)
        self._html(200, markup)

    def _edit_form(self, thread_id: int, post_id: int | None, session: sqlite3.Row) -> None:
        thread = self.app.store.thread(thread_id)
        post = self.app.store.post(post_id) if post_id is not None else None
        if thread is None or post is None or post["thread_id"] != thread_id or post["deleted"]:
            self._not_found(session)
            return
        if not self._can_modify(post, session):
            self._error(403, "You can only edit posts made in this browser session.", session)
            return
        body = f"""<p class="crumbs"><a href="/t/{thread_id}">{html.escape(thread['title'])}</a> / edit</p>
<h1>Edit post</h1><p class="lead">Posting as {html.escape(post['author'])} · {fmt_time(post['created_at'])}</p>
<div class="form-box"><form method="post" action="/t/{thread_id}/edit/{post_id}">
  <label for="body">Message</label>
  <textarea id="body" name="body" maxlength="{MAX_BODY}" required>{html.escape(post['body'])}</textarea>
  <div class="actions"><button type="submit">Save changes</button>
    <a class="muted" href="/t/{thread_id}">Cancel</a></div>
</form></div>"""
        self._html(200, layout(f"Edit post · {thread['title']}", body, bool(session["is_mod"])))

    def _mod_login_page(self, session: sqlite3.Row, error: str = "", status: int = 200) -> None:
        if session["is_mod"] and not error:
            self._redirect("/mod")
            return
        error_html = f'<p class="notice error">{html.escape(error)}</p>' if error else ""
        body = f"""<div class="form-box" style="max-width:430px;margin:50px auto">
<h1 style="font-size:1.6rem">Moderator sign in</h1>
<p class="lead" style="font-size:.92rem">Enter the forum moderator key.</p>{error_html}
<form method="post" action="/mod/login">
  <label for="key">Moderator key</label>
  <input id="key" type="password" name="key" required autofocus>
  <div class="actions"><button type="submit">Sign in</button></div>
</form></div>"""
        self._html(status, layout("Moderator sign in", body, False))

    def _mod_dashboard(self, session: sqlite3.Row) -> None:
        if not session["is_mod"]:
            self._redirect("/mod/login")
            return
        threads = self.app.store.all_threads()
        rows = "".join(f"""<tr><td><a href="/t/{t['id']}">{html.escape(t['title'])}</a>
  <div class="muted">{html.escape(t['board_name'])} · {t['post_count']} posts</div></td>
  <td>{'<span class="badge pinned">pinned</span>' if t['pinned'] else ''}
      {'<span class="badge locked">locked</span>' if t['locked'] else ''}</td>
  <td><div class="actions" style="margin:0">
    <form class="inline" method="post" action="/t/{t['id']}/lock"><button class="secondary"
      style="padding:3px 9px;font-size:.75rem">{'Unlock' if t['locked'] else 'Lock'}</button></form>
    <form class="inline" method="post" action="/t/{t['id']}/pin"><button class="secondary"
      style="padding:3px 9px;font-size:.75rem">{'Unpin' if t['pinned'] else 'Pin'}</button></form>
    <form class="inline" method="post" action="/t/{t['id']}/delete"
      onsubmit="return confirm('Delete this whole thread?')"><button class="danger"
      style="padding:3px 9px;font-size:.75rem">Delete</button></form>
  </div></td></tr>""" for t in threads)
        body = f"""<p class="crumbs"><a href="/">Boards</a> / moderation</p>
<h1>Moderation</h1><p class="lead">{plural(len(threads), 'live thread')}. Lock stops replies; pin floats a thread;
delete removes it from public view.</p>
<form method="post" action="/mod/logout" style="margin-bottom:18px">
  <button class="secondary">Sign out of moderator mode</button></form>
<div class="mod-table"><table><thead><tr><th>Thread</th><th>Flags</th><th>Actions</th></tr></thead>
<tbody>{rows}</tbody></table></div>"""
        self._html(200, layout("Moderation", body, True))

    # ---------- POST ----------

    def do_POST(self) -> None:  # noqa: N802
        segments = [part for part in urllib.parse.urlparse(self.path).path.split("/") if part]
        form = self._form()
        session = self._session()
        try:
            if segments == ["b", ""]:
                self._not_found(session)
            elif len(segments) == 3 and segments[0] == "b" and segments[2] == "new":
                self._new_thread(segments[1], form, session)
            elif len(segments) == 3 and segments[0] == "t" and segments[2] == "reply":
                self._reply(segments[1], form, session)
            elif len(segments) == 4 and segments[0] == "t" and segments[2] == "edit":
                self._save_edit(segments[1], segments[3], form, session)
            elif len(segments) == 4 and segments[0] == "t" and segments[2] == "delete":
                self._delete_post(segments[1], segments[3], session)
            elif len(segments) == 3 and segments[0] == "t" and segments[2] in ("lock", "pin", "delete"):
                self._moderate_thread(segments[1], segments[2], session)
            elif segments == ["mod", "login"]:
                self._mod_login(form, session)
            elif segments == ["mod", "logout"]:
                self.app.store.set_mod(session["sid"], False)
                self._redirect("/mod/login")
            else:
                self._not_found(session)
        except BrokenPipeError:
            pass

    def _new_thread(self, slug: str, form: dict[str, str], session: sqlite3.Row) -> None:
        board = self.app.store.board(slug)
        if board is None:
            self._not_found(session)
            return
        title = form.get("title", "").strip()
        author = form.get("author", "").strip()
        body = form.get("body", "").strip()
        error = ""
        if not 3 <= len(title) <= MAX_TITLE:
            error = "The title must be between 3 and 140 characters."
        elif not 1 <= len(author) <= MAX_AUTHOR:
            error = "Please give a name (40 characters max)."
        elif not 1 <= len(body) <= MAX_BODY:
            error = "The first post cannot be empty."
        if error:
            threads, total = self.app.store.board_threads(board["id"], 1, PER_PAGE)
            pages = max(1, math.ceil(total / PER_PAGE))
            self._html(400, board_page(board, threads, 1, pages, error,
                                       {"title": title, "author": author, "body": body}))
            return
        thread_id = self.app.store.create_thread(board["id"], title, author, body, session["sid"])
        self._redirect(f"/t/{thread_id}")

    def _reply(self, raw_thread: str, form: dict[str, str], session: sqlite3.Row) -> None:
        thread_id = self._int(raw_thread)
        thread = self.app.store.thread(thread_id) if thread_id is not None else None
        if thread is None or thread_id is None:
            self._not_found(session)
            return
        if thread["locked"]:
            self._error(403, "This thread is locked.", session)
            return
        author = form.get("author", "").strip()
        body = form.get("body", "").strip()
        if not 1 <= len(author) <= MAX_AUTHOR or not 1 <= len(body) <= MAX_BODY:
            self._error(400, "A name and a non-empty message are required.", session)
            return
        quote_id = self._int(form.get("quote_id", ""))
        if quote_id is not None:
            quoted = self.app.store.post(quote_id)
            if quoted is None or quoted["thread_id"] != thread_id:
                quote_id = None
        new_post_id = self.app.store.add_post(thread_id, author, body, session["sid"], quote_id)
        total = self.app.store.post_count(thread_id)
        page = max(1, math.ceil(total / PER_PAGE))
        self._redirect(f"/t/{thread_id}?page={page}#p{new_post_id}")

    def _save_edit(self, raw_thread: str, raw_post: str, form: dict[str, str], session: sqlite3.Row) -> None:
        thread_id, post_id = self._int(raw_thread), self._int(raw_post)
        thread = self.app.store.thread(thread_id) if thread_id is not None else None
        post = self.app.store.post(post_id) if post_id is not None else None
        if thread is None or post is None or thread_id is None or post_id is None \
                or post["thread_id"] != thread_id or post["deleted"]:
            self._not_found(session)
            return
        if not self._can_modify(post, session):
            self._error(403, "You can only edit posts made in this browser session.", session)
            return
        body = form.get("body", "").strip()
        if not 1 <= len(body) <= MAX_BODY:
            self._error(400, "The message cannot be empty.", session)
            return
        self.app.store.update_post(post_id, body)
        self._redirect(f"/t/{thread_id}#p{post_id}")

    def _delete_post(self, raw_thread: str, raw_post: str, session: sqlite3.Row) -> None:
        thread_id, post_id = self._int(raw_thread), self._int(raw_post)
        thread = self.app.store.thread(thread_id) if thread_id is not None else None
        post = self.app.store.post(post_id) if post_id is not None else None
        if thread is None or post is None or thread_id is None or post_id is None \
                or post["thread_id"] != thread_id:
            self._not_found(session)
            return
        if not self._can_modify(post, session):
            self._error(403, "You can only delete posts made in this browser session.", session)
            return
        self.app.store.delete_post(post_id)
        self._redirect(f"/t/{thread_id}")

    def _moderate_thread(self, raw_thread: str, action: str, session: sqlite3.Row) -> None:
        if not session["is_mod"]:
            self._error(403, "Moderator access required.", session)
            return
        thread_id = self._int(raw_thread)
        thread = self.app.store.thread(thread_id) if thread_id is not None else None
        if thread is None or thread_id is None:
            self._not_found(session)
            return
        if action == "delete":
            self.app.store.delete_thread(thread_id)
            self._redirect(f"/b/{thread['board_slug']}")
        else:
            flag = "locked" if action == "lock" else "pinned"
            self.app.store.set_flag(thread_id, flag, not bool(thread[flag]))
            self._redirect("/mod")

    def _mod_login(self, form: dict[str, str], session: sqlite3.Row) -> None:
        if not self.app.check_key(form.get("key", "")):
            time.sleep(0.15)
            self._mod_login_page(session, "Invalid moderator key.", 401)
            return
        self.app.store.set_mod(session["sid"], True)
        self._redirect("/mod")


class HttpClient:
    """Cookie-aware HTTP client for the demo."""

    def __init__(self) -> None:
        self.jar = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self.jar))

    def request(self, url: str, data: dict[str, str] | None = None) -> tuple[int, str, str]:
        payload = urllib.parse.urlencode(data).encode() if data is not None else None
        try:
            with self.opener.open(url, data=payload, timeout=10) as response:
                return response.status, response.read().decode("utf-8", "replace"), response.geturl()
        except urllib.error.HTTPError as exc:
            return exc.code, exc.read().decode("utf-8", "replace"), exc.url or url


def demo() -> int:
    """Exercise the forum end to end."""
    print("Web Board (Forum) demo")
    print("======================")
    checks: list[tuple[str, bool]] = []

    checks.append(("post bodies escape HTML",
                   "<script>" not in format_body("<script>alert(1)</script>")
                   and "&lt;script&gt;" in format_body("<script>alert(1)</script>")))
    checks.append(("pagination compacts long ranges", page_numbers(5, 20) == [1, None, 4, 5, 6, None, 20]))

    with tempfile.TemporaryDirectory(prefix="forum-") as tmp:
        app = App(Path(tmp) / "forum.db", mod_key="demo-mod-key")
        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        server.daemon_threads = True
        server.app = app  # type: ignore[attr-defined]
        threading.Thread(target=server.serve_forever, daemon=True).start()
        base = f"http://127.0.0.1:{server.server_port}"
        main = HttpClient()
        other = HttpClient()
        try:
            status, body, _ = main.request(f"{base}/")
            checks.append(("board index lists the seeded boards",
                           status == 200 and "General Discussion" in body and "Projects" in body))

            status, body, _ = main.request(f"{base}/b/general")
            checks.append(("board page shows the new-thread form", status == 200 and "Start a new thread" in body))

            status, body, _ = main.request(f"{base}/b/general/new", {
                "title": "Welcome to the board", "author": "Ada",
                "body": "Hello friends.\n\nWhat are you building this week?",
            })
            checks.append(("thread can be created", status == 200 and "Welcome to the board" in body))
            match = re.search(r"/t/(\d+)", body)
            thread_id = int(match.group(1)) if match else 0
            checks.append(("new thread has a numeric id", thread_id > 0))

            first_post_id = 0
            match = re.search(r'id="p(\d+)"', body)
            if match:
                first_post_id = int(match.group(1))

            status, body, _ = other.request(f"{base}/t/{thread_id}?quote={first_post_id}")
            checks.append(("quote link prefills the reply", status == 200 and "Ada wrote:" in body))

            status, body, _ = other.request(f"{base}/t/{thread_id}/reply", {
                "author": "Grace",
                "body": "> Ada wrote:\n> Hello friends.\n\nA compiler, mostly.",
                "quote_id": str(first_post_id),
            })
            checks.append(("reply is appended with its quote", status == 200
                           and "A compiler, mostly." in body and "Ada wrote:" in body
                           and "replying to post #" in body))
            reply_ids = [int(m) for m in re.findall(r'id="p(\d+)"', body)]
            reply_id = max(reply_ids) if reply_ids else 0

            status, body, _ = main.request(f"{base}/t/{thread_id}/edit/{first_post_id}")
            checks.append(("author can open the edit form", status == 200 and "Edit post" in body))
            status, body, _ = main.request(f"{base}/t/{thread_id}/edit/{first_post_id}", {
                "body": "Hello friends.\n\nEdited: tell me about your week.",
            })
            checks.append(("author can edit their own post", status == 200 and "Edited: tell me about your week." in body))

            status, body, _ = main.request(f"{base}/t/{thread_id}/edit/{reply_id}", {"body": "hijacked"})
            checks.append(("a different session cannot edit the reply", status == 403))

            status, body, _ = other.request(f"{base}/t/{thread_id}/delete/{reply_id}", {})
            checks.append(("author can delete their own post", status == 200 and "This post was deleted." in body))

            created = []
            for index in range(11):
                status, body, _ = main.request(f"{base}/b/general/new", {
                    "title": f"Thread number {index + 2}", "author": "Ada",
                    "body": f"Body for thread {index + 2}.",
                })
                found = re.search(r"/t/(\d+)", body)
                if found:
                    created.append(int(found.group(1)))
            status, body, _ = main.request(f"{base}/b/general?page=2")
            checks.append(("threads paginate ten per page", status == 200 and "2 / 2" in body
                           and body.count('class="thread-title"') == 2))

            status, body, url = main.request(f"{base}/mod")
            checks.append(("moderation requires sign-in", "/mod/login" in url and "Moderator sign in" in body))

            status, body, _ = main.request(f"{base}/mod/login", {"key": "wrong"})
            checks.append(("wrong moderator key is rejected", status == 401 and "Invalid moderator key" in body))

            status, body, _ = main.request(f"{base}/mod/login", {"key": "demo-mod-key"})
            checks.append(("moderator key signs in", status == 200 and "Moderation" in body
                           and "Welcome to the board" in body))

            status, body, _ = main.request(f"{base}/t/{thread_id}/lock", {})
            checks.append(("moderator can lock a thread", status == 200 and "locked" in body.lower()))
            status, body, _ = other.request(f"{base}/t/{thread_id}/reply", {"author": "Grace", "body": "Still here?"})
            checks.append(("locked threads reject new replies", status == 403))
            status, body, _ = main.request(f"{base}/t/{thread_id}")
            checks.append(("locked thread hides the reply form", "New replies are disabled" in body))

            status, body, _ = main.request(f"{base}/t/{thread_id}/pin", {})
            status, body, _ = main.request(f"{base}/b/general")
            checks.append(("pinned thread floats to the top",
                           body.find("Welcome to the board") < body.find("Thread number")))

            victim = created[-1] if created else thread_id
            status, body, _ = main.request(f"{base}/t/{victim}/delete", {})
            status, body, _ = main.request(f"{base}/t/{victim}")
            checks.append(("moderator can delete a thread", status == 404))

            status, body, _ = main.request(f"{base}/mod/logout", {})
            status, body, url = main.request(f"{base}/mod")
            checks.append(("moderator sign-out is effective", "/mod/login" in url))

            status, body, _ = main.request(f"{base}/health")
            counts = json.loads(body)
            checks.append(("health endpoint reports totals", status == 200 and counts["threads"] >= 10))
            print(f"  database     : {counts['boards']} boards, {counts['threads']} threads, {counts['posts']} posts")
        finally:
            server.shutdown()
            server.server_close()
            app.store.close()

    print()
    for label, ok in checks:
        print(f"  [{'PASS' if ok else 'FAIL'}] {label}")
    failed = sum(1 for _, ok in checks if not ok)
    print(f"\n{len(checks) - failed}/{len(checks)} checks passed")
    return 0 if failed == 0 else 1


def main(argv: list[str] | None = None) -> int:
    """Command-line entry point."""
    parser = argparse.ArgumentParser(
        description="A small SQLite-backed web forum with boards, quotes and moderation.",
        epilog="Set FORUM_MODERATOR_KEY to choose the moderator key, or read the generated one at startup.",
    )
    parser.add_argument("--demo", action="store_true", help="run the scripted HTTP walkthrough")
    parser.add_argument("--serve", action="store_true", help="start the web server (default action)")
    parser.add_argument("--port", type=int, default=8000, help="port for --serve (default: 8000)")
    parser.add_argument("--db", type=Path, default=Path("forum.db"), help="SQLite database path")
    parser.add_argument("--verbose", action="store_true", help="log HTTP requests")
    args = parser.parse_args(argv)

    if args.demo:
        return demo()
    if not (0 <= args.port <= 65535):
        parser.error("--port must be between 0 and 65535")

    app = App(args.db, verbose=args.verbose)
    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    server.daemon_threads = True
    server.app = app  # type: ignore[attr-defined]
    host, port = server.server_address[:2]
    print(f"The Web Board at http://{host}:{port}")
    if app.generated_key:
        print(f"Generated moderator key: {app.generated_key}")
        print("Set FORUM_MODERATOR_KEY to use your own.")
    else:
        print("Moderator key taken from FORUM_MODERATOR_KEY.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down.")
    finally:
        server.shutdown()
        server.server_close()
        app.store.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
