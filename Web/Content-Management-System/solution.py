#!/usr/bin/env python3
"""Content Management System: a small SQLite-backed publishing site.

Public visitors get a post index, individual post/page views and search.  A
single administrator signs in with a password (``CMS_ADMIN_PASSWORD`` or a
generated one printed at startup) and can create, edit, publish, unpublish and
delete posts and pages through HTML forms.  Bodies are written in a small,
safely escaped Markdown subset.

``--demo`` starts an ephemeral server on 127.0.0.1 and drives the real login
and CRUD flow over HTTP.
"""

from __future__ import annotations

import argparse
import hashlib
import hmac
import html
import http.cookiejar
import json
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
from dataclasses import dataclass
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from markdown_subset import render_markdown, slugify, strip_markdown

MAX_BODY = 200_000
SESSION_TTL = 8 * 3600
KINDS = ("post", "page")
STATUSES = ("draft", "published")

CSS = """
:root { color-scheme: light; }
* { box-sizing: border-box; }
body { margin:0; background:#f7f4ee; color:#211d1a; font-family: Georgia, 'Times New Roman', serif; line-height:1.6; }
a { color:#8a3b12; }
header.site { border-bottom:1px solid #ded5c6; background:#fffdf8; }
header.site .inner { max-width:980px; margin:0 auto; padding:18px 24px; display:flex; align-items:center; gap:26px; flex-wrap:wrap; }
.brand { font-size:1.35rem; font-weight:700; letter-spacing:-.02em; text-decoration:none; color:#211d1a; }
nav { display:flex; gap:18px; flex-wrap:wrap; font-family:system-ui,sans-serif; font-size:.9rem; }
nav a { text-decoration:none; color:#5c5147; }
nav a:hover { color:#8a3b12; }
nav .spacer { flex:1; }
main { max-width:980px; margin:0 auto; padding:44px 24px 80px; }
h1 { font-size:2.5rem; line-height:1.15; margin:0 0 .4em; letter-spacing:-.03em; }
h2 { font-size:1.55rem; margin-top:2rem; }
h3 { font-size:1.2rem; }
.lead { color:#655a4e; font-size:1.1rem; }
.meta { font-family:system-ui,sans-serif; font-size:.82rem; color:#857767; text-transform:uppercase; letter-spacing:.07em; }
article.post { border-bottom:1px solid #e2d9ca; padding:26px 0; }
article.post:last-child { border-bottom:0; }
article.post h2 { margin:0 0 6px; }
article.post h2 a { color:#211d1a; text-decoration:none; }
article.post h2 a:hover { color:#8a3b12; }
.excerpt { color:#4d443c; }
pre { background:#221d18; color:#f4eee4; padding:16px 18px; border-radius:8px; overflow-x:auto; font-size:.88rem; }
code { font-family: ui-monospace, 'SFMono-Regular', Consolas, monospace; background:#eee7db; padding:1px 5px; border-radius:4px; font-size:.9em; }
pre code { background:transparent; padding:0; color:inherit; }
blockquote { margin:1.4em 0; padding:4px 0 4px 20px; border-left:4px solid #d2a679; color:#5d5044; font-style:italic; }
hr { border:0; border-top:1px solid #ded5c6; margin:2.2em 0; }
input[type=text], input[type=password], input[type=search], select, textarea {
  width:100%; padding:10px 12px; border:1px solid #cfc3b1; border-radius:6px; background:#fffdf8;
  font:inherit; color:inherit; }
textarea { min-height:320px; font-family: ui-monospace, Consolas, monospace; font-size:.92rem; line-height:1.55; }
label { display:block; font-family:system-ui,sans-serif; font-size:.8rem; letter-spacing:.06em;
  text-transform:uppercase; color:#6c5f51; margin:16px 0 6px; }
button, .button { display:inline-block; cursor:pointer; border:0; border-radius:6px; padding:10px 18px;
  font:600 .9rem system-ui,sans-serif; background:#8a3b12; color:#fff8ef; text-decoration:none; }
button.secondary { background:#e9e0d2; color:#3b3129; }
button.danger { background:#9b2d2d; }
button:hover { filter:brightness(1.08); }
.row { display:flex; gap:20px; flex-wrap:wrap; }
.row > * { flex:1; min-width:220px; }
.actions { display:flex; gap:10px; align-items:center; flex-wrap:wrap; margin-top:22px; }
.notice { padding:12px 16px; border-radius:6px; background:#e8f2e2; border:1px solid #b9d3aa;
  font-family:system-ui,sans-serif; font-size:.9rem; margin:0 0 24px; }
.notice.error { background:#f7e4e2; border-color:#dfb4ae; }
table { width:100%; border-collapse:collapse; font-family:system-ui,sans-serif; font-size:.9rem; background:#fffdf8; }
th, td { text-align:left; padding:11px 12px; border-bottom:1px solid #e4dbcc; vertical-align:middle; }
th { font-size:.75rem; letter-spacing:.07em; text-transform:uppercase; color:#7a6b5b; background:#f0e9dd; }
.badge { display:inline-block; padding:2px 9px; border-radius:999px; font-size:.72rem; font-weight:700;
  letter-spacing:.05em; text-transform:uppercase; }
.badge.published { background:#dcefd2; color:#2f5b25; }
.badge.draft { background:#f3e6c8; color:#7a5713; }
.badge.page { background:#dfe8f5; color:#2c4a73; }
.admin-shell { background:#fffdf8; border:1px solid #e2d9ca; border-radius:10px; padding:26px; }
.login { max-width:420px; margin:60px auto; background:#fffdf8; border:1px solid #e2d9ca;
  border-radius:10px; padding:30px; }
footer { border-top:1px solid #ded5c6; padding:22px 24px; text-align:center; color:#8c7d6c;
  font-family:system-ui,sans-serif; font-size:.82rem; }
.empty { background:#fffdf8; border:1px dashed #cfc3b1; padding:36px; border-radius:10px; color:#6c5f51; }
"""


def fmt_time(timestamp: float) -> str:
    """Format a Unix timestamp for display."""
    return time.strftime("%Y-%m-%d %H:%M", time.localtime(timestamp))


def page_layout(title: str, body: str, pages: list[sqlite3.Row], admin: bool, notice: str = "") -> str:
    """Wrap content in the shared public chrome."""
    page_links = "".join(
        f'<a href="/page/{html.escape(p["slug"])}">{html.escape(p["title"])}</a>' for p in pages
    )
    admin_link = ('<a href="/admin/logout">Sign out</a>' if admin
                  else '<a href="/admin">Admin</a>')
    notice_html = f'<p class="notice">{html.escape(notice)}</p>' if notice else ""
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(title)}</title><style>{CSS}</style></head>
<body>
<header class="site"><div class="inner">
  <a class="brand" href="/">Fieldnotes</a>
  <nav><a href="/">Home</a>{page_links}
    <form method="get" action="/search" style="margin:0"><input type="search" name="q" placeholder="Search…"
      aria-label="Search" style="width:150px;padding:6px 9px"></form>
    <a href="/admin">{'Dashboard' if admin else 'Admin'}</a>{admin_link if admin else ''}
  </nav>
</div></header>
<main>{notice_html}{body}</main>
<footer>Fieldnotes CMS · a small publishing engine · Python + SQLite</footer>
</body></html>"""


def post_form(item: dict[str, str] | None = None, csrf: str = "", error: str = "") -> str:
    """Shared create/edit form."""
    item = item or {"title": "", "slug": "", "kind": "post", "status": "draft", "body": ""}
    heading = "Edit item" if item.get("id") else "New item"
    error_html = f'<p class="notice error">{html.escape(error)}</p>' if error else ""
    kind_options = "".join(
        f'<option value="{kind}"{" selected" if kind == item["kind"] else ""}>{kind.title()}</option>'
        for kind in KINDS
    )
    return f"""
<h1>{heading}</h1>
<p class="lead">Write in the supported Markdown subset: headings, <strong>bold</strong>,
<em>italic</em>, <code>code</code>, lists, quotes, links and fenced code blocks.</p>
{error_html}
<form method="post" action="{item.get('action', '/admin/new')}">
  <input type="hidden" name="csrf" value="{html.escape(csrf)}">
  <div class="row">
    <div><label for="title">Title</label>
      <input id="title" type="text" name="title" maxlength="200" required value="{html.escape(item['title'])}"></div>
    <div><label for="slug">Slug (optional)</label>
      <input id="slug" type="text" name="slug" maxlength="80" placeholder="generated-from-title" value="{html.escape(item['slug'])}"></div>
    <div><label for="kind">Type</label><select id="kind" name="kind">{kind_options}</select></div>
  </div>
  <label for="body">Body (Markdown)</label>
  <textarea id="body" name="body" required>{html.escape(item['body'])}</textarea>
  <div class="actions">
    <button type="submit" name="action" value="draft">Save draft</button>
    <button type="submit" name="action" value="published">Publish</button>
    <a class="button" style="background:#e9e0d2;color:#3b3129" href="/admin">Cancel</a>
  </div>
</form>"""


class Store:
    """Thread-safe SQLite persistence for posts and sessions."""

    def __init__(self, db_path: Path) -> None:
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.lock = threading.RLock()
        with self.lock:
            self.conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS posts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    kind TEXT NOT NULL CHECK (kind IN ('post', 'page')),
                    title TEXT NOT NULL,
                    slug TEXT NOT NULL UNIQUE,
                    body TEXT NOT NULL,
                    status TEXT NOT NULL CHECK (status IN ('draft', 'published')),
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL
                );
                CREATE INDEX IF NOT EXISTS posts_status ON posts(status, kind);
                CREATE TABLE IF NOT EXISTS sessions (
                    token TEXT PRIMARY KEY,
                    csrf TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    expires_at REAL NOT NULL
                );
                """
            )
            self.conn.commit()

    def unique_slug(self, base: str, exclude_id: int | None = None) -> str:
        """Return a slug derived from ``base`` that is not already taken."""
        root = slugify(base)
        candidate, counter = root, 2
        while True:
            row = self.conn.execute("SELECT id FROM posts WHERE slug = ?", (candidate,)).fetchone()
            if row is None or row["id"] == exclude_id:
                return candidate
            candidate = f"{root}-{counter}"
            counter += 1

    def create(self, kind: str, title: str, slug: str, body: str, status: str) -> int:
        now = time.time()
        with self.lock:
            final_slug = self.unique_slug(slug or title)
            cursor = self.conn.execute(
                "INSERT INTO posts(kind, title, slug, body, status, created_at, updated_at) VALUES (?,?,?,?,?,?,?)",
                (kind, title, final_slug, body, status, now, now),
            )
            self.conn.commit()
            return int(cursor.lastrowid or 0)

    def update(self, post_id: int, kind: str, title: str, slug: str, body: str, status: str) -> None:
        with self.lock:
            final_slug = self.unique_slug(slug or title, exclude_id=post_id)
            self.conn.execute(
                "UPDATE posts SET kind=?, title=?, slug=?, body=?, status=?, updated_at=? WHERE id=?",
                (kind, title, final_slug, body, status, time.time(), post_id),
            )
            self.conn.commit()

    def get(self, post_id: int) -> sqlite3.Row | None:
        with self.lock:
            return self.conn.execute("SELECT * FROM posts WHERE id=?", (post_id,)).fetchone()

    def get_by_slug(self, slug: str, published_only: bool = False) -> sqlite3.Row | None:
        query = "SELECT * FROM posts WHERE slug=?"
        params: list[object] = [slug]
        if published_only:
            query += " AND status='published'"
        with self.lock:
            return self.conn.execute(query, params).fetchone()

    def all_items(self) -> list[sqlite3.Row]:
        with self.lock:
            return self.conn.execute("SELECT * FROM posts ORDER BY updated_at DESC").fetchall()

    def published(self, kind: str, limit: int = 50) -> list[sqlite3.Row]:
        with self.lock:
            return self.conn.execute(
                "SELECT * FROM posts WHERE status='published' AND kind=? ORDER BY created_at DESC LIMIT ?",
                (kind, limit),
            ).fetchall()

    def published_pages(self) -> list[sqlite3.Row]:
        with self.lock:
            return self.conn.execute(
                "SELECT * FROM posts WHERE status='published' AND kind='page' ORDER BY title"
            ).fetchall()

    def search(self, term: str) -> list[sqlite3.Row]:
        like = f"%{term}%"
        with self.lock:
            return self.conn.execute(
                "SELECT * FROM posts WHERE status='published' AND (title LIKE ? OR body LIKE ?) "
                "ORDER BY updated_at DESC LIMIT 50",
                (like, like),
            ).fetchall()

    def delete(self, post_id: int) -> None:
        with self.lock:
            self.conn.execute("DELETE FROM posts WHERE id=?", (post_id,))
            self.conn.commit()

    def counts(self) -> dict[str, int]:
        with self.lock:
            rows = self.conn.execute(
                "SELECT status, COUNT(*) AS n FROM posts GROUP BY status"
            ).fetchall()
        result = {row["status"]: row["n"] for row in rows}
        return {"published": result.get("published", 0), "draft": result.get("draft", 0),
                "total": sum(result.values())}

    def new_session(self) -> tuple[str, str]:
        token, csrf = secrets.token_urlsafe(24), secrets.token_urlsafe(24)
        now = time.time()
        with self.lock:
            self.conn.execute("DELETE FROM sessions WHERE expires_at < ?", (now,))
            self.conn.execute("INSERT INTO sessions VALUES (?,?,?,?)", (token, csrf, now, now + SESSION_TTL))
            self.conn.commit()
        return token, csrf

    def session(self, token: str) -> sqlite3.Row | None:
        with self.lock:
            row = self.conn.execute("SELECT * FROM sessions WHERE token=?", (token,)).fetchone()
            if row is None:
                return None
            if row["expires_at"] < time.time():
                self.conn.execute("DELETE FROM sessions WHERE token=?", (token,))
                self.conn.commit()
                return None
            return row

    def drop_session(self, token: str) -> None:
        with self.lock:
            self.conn.execute("DELETE FROM sessions WHERE token=?", (token,))
            self.conn.commit()

    def close(self) -> None:
        self.conn.close()


@dataclass(frozen=True)
class Admin:
    """Currently authenticated administrator."""

    token: str
    csrf: str


class App:
    """Application state: storage, password hash and login throttling."""

    def __init__(self, db_path: Path, password: str | None = None, verbose: bool = False) -> None:
        self.store = Store(db_path)
        self.verbose = verbose
        self.generated_password = ""
        if password is None:
            password = os.environ.get("CMS_ADMIN_PASSWORD", "")
        if not password:
            password = secrets.token_urlsafe(9)
            self.generated_password = password
        self.salt = os.urandom(16)
        self.password_hash = self._hash(password)
        self.failed_logins: dict[str, list[float]] = {}
        self._lock = threading.Lock()

    def _hash(self, password: str) -> bytes:
        return hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), self.salt, 120_000)

    def check_password(self, password: str) -> bool:
        return hmac.compare_digest(self._hash(password), self.password_hash)

    def throttled(self, client: str) -> bool:
        now = time.monotonic()
        with self._lock:
            attempts = [t for t in self.failed_logins.get(client, []) if now - t < 300]
            self.failed_logins[client] = attempts
            return len(attempts) >= 5

    def record_failure(self, client: str) -> None:
        with self._lock:
            self.failed_logins.setdefault(client, []).append(time.monotonic())

    def clear_failures(self, client: str) -> None:
        with self._lock:
            self.failed_logins.pop(client, None)


class Handler(BaseHTTPRequestHandler):
    """HTTP routes for the public site and admin console."""

    server_version = "FieldnotesCMS/1.0"

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
        for key, value in (headers or {}).items():
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(body)

    def _html(self, status: int, markup: str, headers: dict[str, str] | None = None) -> None:
        self._send(status, markup.encode("utf-8"), "text/html; charset=utf-8", headers)

    def _redirect(self, location: str, headers: dict[str, str] | None = None) -> None:
        merged = {"Location": location, **(headers or {})}
        self._send(303, b"", "text/plain; charset=utf-8", merged)

    def _public(self, title: str, body: str, notice: str = "") -> str:
        return page_layout(title, body, self.app.store.published_pages(), self._admin() is not None, notice)

    def _session_token(self) -> str:
        raw = self.headers.get("Cookie", "")
        if not raw:
            return ""
        try:
            cookie = SimpleCookie(raw)
        except Exception:
            return ""
        morsel = cookie.get("cms_session")
        return morsel.value if morsel else ""

    def _admin(self) -> Admin | None:
        token = self._session_token()
        if not token:
            return None
        row = self.app.store.session(token)
        if row is None:
            return None
        return Admin(token, row["csrf"])

    def _read_form(self) -> dict[str, str]:
        try:
            length = int(self.headers.get("Content-Length", "0") or 0)
        except ValueError:
            length = 0
        if length <= 0 or length > MAX_BODY + 10_000:
            return {}
        raw = self.rfile.read(length).decode("utf-8", "replace")
        return {k: v[0] for k, v in urllib.parse.parse_qs(raw, keep_blank_values=True).items()}

    def _not_found(self) -> None:
        body = "<h1>Not found</h1><p class='lead'>That page does not exist or is not published.</p>" \
               "<p><a href='/'>Back to the index</a></p>"
        self._html(404, page_layout("Not found", body, self.app.store.published_pages(), self._admin() is not None))

    def _validate(self, form: dict[str, str]) -> tuple[dict[str, str], str]:
        title = form.get("title", "").strip()
        body = form.get("body", "").strip()
        kind = form.get("kind", "post")
        status = form.get("action", form.get("status", "draft"))
        if status not in STATUSES:
            status = "draft"
        if kind not in KINDS:
            return {}, "Unknown item type."
        if not title:
            return {}, "A title is required."
        if len(title) > 200:
            return {}, "The title is too long (200 characters max)."
        if not body:
            return {}, "The body cannot be empty."
        if len(body) > MAX_BODY:
            return {}, "The body is too large."
        return {"title": title, "slug": form.get("slug", "").strip(), "body": body,
                "kind": kind, "status": status}, ""

    # ---------- GET ----------

    def do_GET(self) -> None:  # noqa: N802
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path.rstrip("/") or "/"
        query = urllib.parse.parse_qs(parsed.query)
        try:
            if path == "/":
                self._index(query)
            elif path == "/search":
                self._search(query)
            elif path == "/health":
                self._send(200, json.dumps(self.app.store.counts()).encode(), "application/json")
            elif path.startswith("/post/"):
                self._show(path[len("/post/"):], "post")
            elif path.startswith("/page/"):
                self._show(path[len("/page/"):], "page")
            elif path == "/admin/login":
                if self._admin():
                    self._redirect("/admin")
                else:
                    self._login_page()
            elif path == "/admin/logout":
                token = self._session_token()
                if token:
                    self.app.store.drop_session(token)
                self._redirect("/", {"Set-Cookie": "cms_session=; Path=/; Max-Age=0; HttpOnly; SameSite=Lax"})
            elif path == "/admin":
                self._dashboard(query)
            elif path == "/admin/new":
                self._new_form()
            elif path.startswith("/admin/edit/"):
                self._edit_form(path.rsplit("/", 1)[-1])
            else:
                self._not_found()
        except BrokenPipeError:
            pass

    def _index(self, query: dict[str, list[str]]) -> None:
        posts = self.app.store.published("post")
        notice = {"created": "Item created.", "updated": "Item updated.",
                  "deleted": "Item deleted.", "status": "Status changed."}.get(
            (query.get("ok") or [""])[0], "")
        if posts:
            cards = []
            for post in posts:
                cards.append(f"""<article class="post">
  <p class="meta">{fmt_time(post['created_at'])}</p>
  <h2><a href="/post/{html.escape(post['slug'])}">{html.escape(post['title'])}</a></h2>
  <p class="excerpt">{html.escape(strip_markdown(post['body'], 220))}</p>
</article>""")
            body = ("<h1>Notes from the workbench</h1><p class='lead'>Essays, field notes and small "
                    "experiments, published with a quietly opinionated CMS.</p>" + "".join(cards))
        else:
            body = ("<h1>Notes from the workbench</h1><p class='lead'>A small publishing engine.</p>"
                    "<div class='empty'>No posts yet. Sign in to the admin console and write the first one.</div>")
        self._html(200, self._public("Fieldnotes", body, notice))

    def _search(self, query: dict[str, list[str]]) -> None:
        term = (query.get("q") or [""])[0].strip()[:100]
        if not term:
            self._html(200, self._public("Search", "<h1>Search</h1><p class='lead'>Type a word in the box above.</p>"))
            return
        results = self.app.store.search(term)
        items = "".join(
            f'<li><a href="/{row["kind"]}/{html.escape(row["slug"])}">{html.escape(row["title"])}</a>'
            f' <span class="meta">— {row["kind"]}</span></li>'
            for row in results
        )
        body = (f"<h1>Search</h1><p class='lead'>{len(results)} result(s) for "
                f"“{html.escape(term)}”.</p>" + (f"<ul>{items}</ul>" if items else "<div class='empty'>Nothing found.</div>"))
        self._html(200, self._public("Search", body))

    def _show(self, slug: str, kind: str) -> None:
        row = self.app.store.get_by_slug(urllib.parse.unquote(slug), published_only=True)
        if row is None or row["kind"] != kind:
            self._not_found()
            return
        body = f"""<article>
<p class="meta">{html.escape(row['kind'])} · {fmt_time(row['created_at'])}</p>
<h1>{html.escape(row['title'])}</h1>
<div class="content">{render_markdown(row['body'])}</div>
</article>"""
        self._html(200, self._public(row["title"], body))

    def _login_page(self, error: str = "", status: int = 200) -> None:
        error_html = f'<p class="notice error">{html.escape(error)}</p>' if error else ""
        body = f"""<div class="login">
<h1 style="font-size:1.7rem">Sign in</h1>
<p class="lead" style="font-size:.95rem">Administrator access for Fieldnotes.</p>
{error_html}
<form method="post" action="/admin/login">
  <label for="password">Password</label>
  <input id="password" type="password" name="password" required autofocus>
  <div class="actions"><button type="submit">Sign in</button></div>
</form></div>"""
        self._html(status, page_layout("Sign in", body, self.app.store.published_pages(), False))

    def _require_admin(self) -> Admin | None:
        admin = self._admin()
        if admin is None:
            self._redirect("/admin/login")
        return admin

    def _dashboard(self, query: dict[str, list[str]]) -> None:
        admin = self._require_admin()
        if admin is None:
            return
        rows = self.app.store.all_items()
        notice = {"created": "Item created.", "updated": "Item updated.",
                  "deleted": "Item deleted.", "status": "Status changed."}.get(
            (query.get("ok") or [""])[0], "")
        notice_html = f'<p class="notice">{html.escape(notice)}</p>' if notice else ""
        if rows:
            table_rows = "".join(
                f"""<tr>
<td><a href="/admin/edit/{row['id']}">{html.escape(row['title'])}</a></td>
<td><span class="badge {row['kind']}">{row['kind']}</span></td>
<td><span class="badge {row['status']}">{row['status']}</span></td>
<td>{fmt_time(row['updated_at'])}</td>
<td><div class="actions" style="margin:0">
  <a class="button" style="padding:6px 12px" href="/admin/edit/{row['id']}">Edit</a>
  <form method="post" action="/admin/toggle/{row['id']}" style="margin:0">
    <input type="hidden" name="csrf" value="{html.escape(admin.csrf)}">
    <button class="secondary" style="padding:6px 12px" name="status"
      value="{'draft' if row['status'] == 'published' else 'published'}">
      {'Unpublish' if row['status'] == 'published' else 'Publish'}</button>
  </form>
  <form method="post" action="/admin/delete/{row['id']}" style="margin:0"
        onsubmit="return confirm('Delete this item permanently?')">
    <input type="hidden" name="csrf" value="{html.escape(admin.csrf)}">
    <button class="danger" style="padding:6px 12px">Delete</button>
  </form>
</div></td></tr>"""
                for row in rows
            )
            table = f"""<table><thead><tr><th>Title</th><th>Type</th><th>Status</th><th>Updated</th><th>Actions</th></tr></thead>
<tbody>{table_rows}</tbody></table>"""
        else:
            table = "<div class='empty'>Nothing yet. Create your first post or page.</div>"
        body = f"""<div class="admin-shell">
<h1 style="font-size:1.9rem">Dashboard</h1>
<p class="lead">Everything on the site, drafts included.</p>
{notice_html}
<p><a class="button" href="/admin/new">New post or page</a>
<a class="button secondary" href="/" style="margin-left:8px">View site</a></p>
{table}
</div>"""
        self._html(200, page_layout("Dashboard", body, self.app.store.published_pages(), True))

    def _new_form(self) -> None:
        admin = self._require_admin()
        if admin is None:
            return
        self._html(200, page_layout("New item", post_form(csrf=admin.csrf),
                                    self.app.store.published_pages(), True))

    def _edit_form(self, raw_id: str) -> None:
        admin = self._require_admin()
        if admin is None:
            return
        if not raw_id.isdigit():
            self._not_found()
            return
        row = self.app.store.get(int(raw_id))
        if row is None:
            self._not_found()
            return
        item = {"id": str(row["id"]), "title": row["title"], "slug": row["slug"], "kind": row["kind"],
                "status": row["status"], "body": row["body"], "action": f"/admin/edit/{row['id']}"}
        self._html(200, page_layout(f"Edit {row['title']}", post_form(item, admin.csrf),
                                    self.app.store.published_pages(), True))

    # ---------- POST ----------

    def do_POST(self) -> None:  # noqa: N802
        path = urllib.parse.urlparse(self.path).path.rstrip("/") or "/"
        form = self._read_form()
        try:
            if path == "/admin/login":
                self._login(form)
                return
            if path == "/admin/logout":
                token = self._session_token()
                if token:
                    self.app.store.drop_session(token)
                self._redirect("/", {"Set-Cookie": "cms_session=; Path=/; Max-Age=0; HttpOnly; SameSite=Lax"})
                return
            admin = self._admin()
            if admin is None:
                self._redirect("/admin/login")
                return
            if not hmac.compare_digest(form.get("csrf", ""), admin.csrf):
                self._html(400, page_layout("Bad request", "<h1>Bad request</h1><p class='lead'>"
                                            "The form token was missing or stale. Reload and try again.</p>",
                                            self.app.store.published_pages(), True))
                return
            if path == "/admin/new":
                self._create(form, admin)
            elif path.startswith("/admin/edit/"):
                self._update(form, admin, path.rsplit("/", 1)[-1])
            elif path.startswith("/admin/delete/"):
                self._delete(path.rsplit("/", 1)[-1])
            elif path.startswith("/admin/toggle/"):
                self._toggle(form, path.rsplit("/", 1)[-1])
            else:
                self._not_found()
        except BrokenPipeError:
            pass

    def _login(self, form: dict[str, str]) -> None:
        client = self.client_address[0]
        if self.app.throttled(client):
            self._login_page("Too many attempts. Wait five minutes and try again.", 429)
            return
        password = form.get("password", "")
        if not self.app.check_password(password):
            self.app.record_failure(client)
            time.sleep(0.15)  # soften rapid guesses without locking up the demo
            self._login_page("Invalid password.", 401)
            return
        self.app.clear_failures(client)
        token, _csrf = self.app.store.new_session()
        self._redirect("/admin", {
            "Set-Cookie": f"cms_session={token}; Path=/; HttpOnly; SameSite=Lax; Max-Age={SESSION_TTL}"
        })

    def _create(self, form: dict[str, str], admin: Admin) -> None:
        data, error = self._validate(form)
        if error:
            shown = {"title": form.get("title", ""), "slug": form.get("slug", ""), "body": form.get("body", ""),
                     "kind": form.get("kind", "post"), "status": form.get("action", "draft")}
            self._html(400, page_layout("New item", post_form(shown, admin.csrf, error),
                                        self.app.store.published_pages(), True))
            return
        self.app.store.create(data["kind"], data["title"], data["slug"], data["body"], data["status"])
        self._redirect("/admin?ok=created")

    def _update(self, form: dict[str, str], admin: Admin, raw_id: str) -> None:
        if not raw_id.isdigit() or self.app.store.get(int(raw_id)) is None:
            self._not_found()
            return
        data, error = self._validate(form)
        if error:
            shown = {"id": raw_id, "title": form.get("title", ""), "slug": form.get("slug", ""),
                     "body": form.get("body", ""), "kind": form.get("kind", "post"),
                     "status": form.get("action", "draft"), "action": f"/admin/edit/{raw_id}"}
            self._html(400, page_layout("Edit item", post_form(shown, admin.csrf, error),
                                        self.app.store.published_pages(), True))
            return
        self.app.store.update(int(raw_id), data["kind"], data["title"], data["slug"], data["body"], data["status"])
        self._redirect("/admin?ok=updated")

    def _delete(self, raw_id: str) -> None:
        if raw_id.isdigit() and self.app.store.get(int(raw_id)) is not None:
            self.app.store.delete(int(raw_id))
        self._redirect("/admin?ok=deleted")

    def _toggle(self, form: dict[str, str], raw_id: str) -> None:
        if raw_id.isdigit():
            row = self.app.store.get(int(raw_id))
            if row is not None:
                new_status = form.get("status", "draft")
                if new_status not in STATUSES:
                    new_status = "draft"
                self.app.store.update(int(raw_id), row["kind"], row["title"], row["slug"],
                                      row["body"], new_status)
        self._redirect("/admin?ok=status")


class HttpClient:
    """Cookie-aware HTTP client used by the demo."""

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


def _csrf(markup: str) -> str:
    match = re.search(r'name="csrf" value="([^"]+)"', markup)
    return match.group(1) if match else ""


def demo() -> int:
    """Drive the CMS end to end against an ephemeral server."""
    print("Content Management System demo")
    print("==============================")
    checks: list[tuple[str, bool]] = []

    rendered = render_markdown("## Title\n\nA **bold** word, *soft*, `code`, [link](https://example.com).\n\n- one\n- two")
    checks.append(("Markdown renders headings, emphasis, code, links and lists",
                   "<h2>Title</h2>" in rendered and "<strong>bold</strong>" in rendered
                   and "<em>soft</em>" in rendered and "<code>code</code>" in rendered
                   and 'href="https://example.com"' in rendered and "<li>one</li>" in rendered))
    unsafe = render_markdown("<script>alert(1)</script>\n\n[bad](javascript:alert(1))")
    checks.append(("HTML and javascript: URLs are neutralised",
                   "<script>" not in unsafe and "&lt;script&gt;" in unsafe and "javascript:" not in unsafe))
    checks.append(("slugify makes URL-safe slugs", slugify("Hello, World! Again") == "hello-world-again"))

    with tempfile.TemporaryDirectory(prefix="cms-") as tmp:
        app = App(Path(tmp) / "cms.db", password="demo-secret")
        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        server.daemon_threads = True
        server.app = app  # type: ignore[attr-defined]
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base = f"http://127.0.0.1:{server.server_port}"
        client = HttpClient()
        try:
            status, body, _ = client.request(f"{base}/")
            checks.append(("public index is served", status == 200 and "No posts yet" in body))

            status, body, url = client.request(f"{base}/admin")
            checks.append(("dashboard redirects anonymous visitors to login",
                           status == 200 and "/admin/login" in url and "Sign in" in body))

            status, body, _ = client.request(f"{base}/admin/login", {"password": "wrong"})
            checks.append(("wrong password is rejected", status == 401 and "Invalid password" in body))

            status, body, url = client.request(f"{base}/admin/login", {"password": "demo-secret"})
            checks.append(("correct password signs in", status == 200 and url.endswith("/admin") and "Dashboard" in body))
            csrf = _csrf(body)
            if not csrf:  # an empty dashboard has no inline forms, so use the editor form
                status, body, _ = client.request(f"{base}/admin/new")
                csrf = _csrf(body)
            checks.append(("admin session exposes a CSRF token", bool(csrf)))

            source = ("## A small beginning\n\nThis is **Markdown**, rendered by the CMS. "
                      "It supports `inline code`, lists and [links](https://example.com).\n\n"
                      "- posts and pages\n- drafts and publishing\n- a real SQLite database\n\n"
                      "> Start small, then grow.")
            status, body, _ = client.request(f"{base}/admin/new", {
                "csrf": csrf, "title": "Hello, CMS", "slug": "", "kind": "post",
                "body": source, "action": "draft",
            })
            checks.append(("draft post can be created", status == 200 and "draft" in body.lower() and "Hello, CMS" in body))
            post = app.store.get_by_slug("hello-cms")
            checks.append(("slug is generated from the title", post is not None and post["slug"] == "hello-cms"))
            assert post is not None

            status, body, _ = client.request(f"{base}/post/hello-cms")
            checks.append(("draft is hidden from the public", status == 404))

            status, body, _ = client.request(f"{base}/admin/toggle/{post['id']}", {"csrf": csrf, "status": "published"})
            status, body, _ = client.request(f"{base}/post/hello-cms")
            checks.append(("publishing exposes the post", status == 200 and "A small beginning" in body))
            checks.append(("Markdown is rendered on the public page",
                           "<h2>A small beginning</h2>" in body and "<strong>Markdown</strong>" in body
                           and "<blockquote>" in body and 'href="https://example.com"' in body))

            status, body, _ = client.request(f"{base}/search?q=Markdown")
            checks.append(("search finds published content", status == 200 and "Hello, CMS" in body))

            status, body, _ = client.request(f"{base}/admin/new", {
                "csrf": csrf, "title": "About", "slug": "about", "kind": "page",
                "body": "A **page** about this tiny CMS.", "action": "published",
            })
            status, body, _ = client.request(f"{base}/page/about")
            checks.append(("published page is served at its slug", status == 200 and "about this tiny CMS" in body))

            about = app.store.get_by_slug("about")
            assert about is not None and post is not None
            status, body, _ = client.request(f"{base}/admin/edit/{post['id']}", {
                "csrf": csrf, "title": "Hello, CMS (edited)", "slug": "hello-cms", "kind": "post",
                "body": source + "\n\nEdited after publication.", "action": "published",
            })
            status, body, _ = client.request(f"{base}/post/hello-cms")
            checks.append(("editing updates the public post", status == 200 and "Edited after publication" in body))

            status, body, _ = client.request(f"{base}/admin/new", {
                "csrf": csrf, "title": "Hello, CMS", "slug": "", "kind": "post",
                "body": "A second post with the same title.", "action": "draft",
            })
            duplicate = app.store.get_by_slug("hello-cms-2")
            checks.append(("duplicate titles get unique slugs", duplicate is not None))

            status, body, _ = client.request(f"{base}/admin/delete/{about['id']}", {"csrf": csrf})
            status, body, _ = client.request(f"{base}/page/about")
            checks.append(("deleting removes the page", status == 404))

            status, body, _ = client.request(f"{base}/admin/new", {"csrf": "bogus", "title": "Nope",
                                                                   "body": "no", "kind": "post", "action": "draft"})
            checks.append(("stale CSRF token is rejected", status == 400))

            status, body, _ = client.request(f"{base}/admin/logout", {})
            status, body, url = client.request(f"{base}/admin/new")
            checks.append(("logout ends the session", "/admin/login" in url))

            status, body, _ = client.request(f"{base}/health")
            health = json.loads(body)
            checks.append(("health endpoint reports counts", status == 200 and health["total"] == 2))
            print(f"  database     : {health['total']} items "
                  f"({health['published']} published, {health['draft']} draft)")
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
        description="SQLite-backed CMS with Markdown posts, pages, drafts and a session login.",
        epilog="Set CMS_ADMIN_PASSWORD to choose the admin password, or read the generated one at startup.",
    )
    parser.add_argument("--demo", action="store_true", help="run the scripted HTTP walkthrough")
    parser.add_argument("--serve", action="store_true", help="start the web server (default action)")
    parser.add_argument("--port", type=int, default=8000, help="port for --serve (default: 8000)")
    parser.add_argument("--db", type=Path, default=Path("cms.db"), help="SQLite database path")
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
    print(f"Fieldnotes CMS at http://{host}:{port}")
    if app.generated_password:
        print(f"Generated admin password: {app.generated_password}")
        print("Set CMS_ADMIN_PASSWORD to use your own.")
    else:
        print("Admin password taken from CMS_ADMIN_PASSWORD.")
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
