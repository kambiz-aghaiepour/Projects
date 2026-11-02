#!/usr/bin/env python3
"""SQLite storage layer for the Web Board forum.

Boards, threads, posts and browser sessions live here.  Post ownership is tied
to an opaque session id so that an author can edit or delete their own posts
without a full account system; moderators bypass the ownership check.
"""

from __future__ import annotations

import secrets
import sqlite3
import threading
import time
from pathlib import Path

DEFAULT_BOARDS = [
    ("general", "General Discussion", "Introductions, ideas and anything else."),
    ("projects", "Projects", "Show what you are building and ask for feedback."),
    ("off-topic", "Off Topic", "Small talk, links and harmless distractions."),
]

SESSION_TTL = 30 * 24 * 3600


class ForumStore:
    """Thread-safe forum persistence."""

    def __init__(self, db_path: Path) -> None:
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.lock = threading.RLock()
        with self.lock:
            self.conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS boards (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    slug TEXT NOT NULL UNIQUE,
                    name TEXT NOT NULL,
                    description TEXT NOT NULL DEFAULT '',
                    created_at REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS threads (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    board_id INTEGER NOT NULL REFERENCES boards(id),
                    title TEXT NOT NULL,
                    author TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL,
                    locked INTEGER NOT NULL DEFAULT 0,
                    pinned INTEGER NOT NULL DEFAULT 0,
                    deleted INTEGER NOT NULL DEFAULT 0
                );
                CREATE TABLE IF NOT EXISTS posts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    thread_id INTEGER NOT NULL REFERENCES threads(id),
                    author TEXT NOT NULL,
                    body TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    edited_at REAL,
                    quote_id INTEGER,
                    deleted INTEGER NOT NULL DEFAULT 0
                );
                CREATE TABLE IF NOT EXISTS sessions (
                    sid TEXT PRIMARY KEY,
                    is_mod INTEGER NOT NULL DEFAULT 0,
                    created_at REAL NOT NULL,
                    expires_at REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS owners (
                    sid TEXT NOT NULL,
                    post_id INTEGER NOT NULL,
                    PRIMARY KEY (sid, post_id)
                );
                CREATE INDEX IF NOT EXISTS threads_board ON threads(board_id, deleted, pinned, updated_at);
                CREATE INDEX IF NOT EXISTS posts_thread ON posts(thread_id, id);
                """
            )
            now = time.time()
            for slug, name, description in DEFAULT_BOARDS:
                self.conn.execute(
                    "INSERT OR IGNORE INTO boards(slug, name, description, created_at) VALUES (?,?,?,?)",
                    (slug, name, description, now),
                )
            self.conn.commit()

    # ---------- boards & threads ----------

    def boards(self) -> list[sqlite3.Row]:
        with self.lock:
            return self.conn.execute(
                """SELECT b.*,
                     (SELECT COUNT(*) FROM threads t WHERE t.board_id=b.id AND t.deleted=0) AS thread_count,
                     (SELECT COUNT(*) FROM posts p JOIN threads t2 ON p.thread_id=t2.id
                        WHERE t2.board_id=b.id AND t2.deleted=0 AND p.deleted=0) AS post_count,
                     (SELECT MAX(t3.updated_at) FROM threads t3 WHERE t3.board_id=b.id AND t3.deleted=0) AS last_at
                   FROM boards b ORDER BY b.id"""
            ).fetchall()

    def board(self, slug: str) -> sqlite3.Row | None:
        with self.lock:
            return self.conn.execute("SELECT * FROM boards WHERE slug=?", (slug,)).fetchone()

    def board_threads(self, board_id: int, page: int, per_page: int) -> tuple[list[sqlite3.Row], int]:
        offset = (page - 1) * per_page
        with self.lock:
            total = int(self.conn.execute(
                "SELECT COUNT(*) FROM threads WHERE board_id=? AND deleted=0", (board_id,)
            ).fetchone()[0])
            rows = self.conn.execute(
                """SELECT t.*,
                     (SELECT COUNT(*) FROM posts p WHERE p.thread_id=t.id AND p.deleted=0) AS post_count,
                     (SELECT p.author FROM posts p WHERE p.thread_id=t.id ORDER BY p.id LIMIT 1) AS first_author
                   FROM threads t WHERE t.board_id=? AND t.deleted=0
                   ORDER BY t.pinned DESC, t.updated_at DESC LIMIT ? OFFSET ?""",
                (board_id, per_page, offset),
            ).fetchall()
        return rows, total

    def thread(self, thread_id: int) -> sqlite3.Row | None:
        with self.lock:
            return self.conn.execute(
                """SELECT t.*, b.slug AS board_slug, b.name AS board_name
                   FROM threads t JOIN boards b ON b.id=t.board_id
                   WHERE t.id=? AND t.deleted=0""",
                (thread_id,),
            ).fetchone()

    def all_threads(self) -> list[sqlite3.Row]:
        """Every live thread, newest activity first (moderator dashboard)."""
        with self.lock:
            return self.conn.execute(
                """SELECT t.*, b.slug AS board_slug, b.name AS board_name,
                     (SELECT COUNT(*) FROM posts p WHERE p.thread_id=t.id AND p.deleted=0) AS post_count
                   FROM threads t JOIN boards b ON b.id=t.board_id
                   WHERE t.deleted=0 ORDER BY t.updated_at DESC"""
            ).fetchall()

    def create_thread(self, board_id: int, title: str, author: str, body: str, sid: str) -> int:
        now = time.time()
        with self.lock:
            cursor = self.conn.execute(
                "INSERT INTO threads(board_id, title, author, created_at, updated_at) VALUES (?,?,?,?,?)",
                (board_id, title, author, now, now),
            )
            thread_id = int(cursor.lastrowid or 0)
            post = self.conn.execute(
                "INSERT INTO posts(thread_id, author, body, created_at) VALUES (?,?,?,?)",
                (thread_id, author, body, now),
            )
            self.conn.execute("INSERT OR IGNORE INTO owners(sid, post_id) VALUES (?,?)",
                              (sid, int(post.lastrowid or 0)))
            self.conn.commit()
            return thread_id

    def add_post(self, thread_id: int, author: str, body: str, sid: str, quote_id: int | None) -> int:
        now = time.time()
        with self.lock:
            cursor = self.conn.execute(
                "INSERT INTO posts(thread_id, author, body, created_at, quote_id) VALUES (?,?,?,?,?)",
                (thread_id, author, body, now, quote_id),
            )
            post_id = int(cursor.lastrowid or 0)
            self.conn.execute("INSERT OR IGNORE INTO owners(sid, post_id) VALUES (?,?)", (sid, post_id))
            self.conn.execute("UPDATE threads SET updated_at=? WHERE id=?", (now, thread_id))
            self.conn.commit()
            return post_id

    def posts(self, thread_id: int, page: int, per_page: int) -> tuple[list[sqlite3.Row], int]:
        offset = (page - 1) * per_page
        with self.lock:
            total = int(self.conn.execute(
                "SELECT COUNT(*) FROM posts WHERE thread_id=?", (thread_id,)
            ).fetchone()[0])
            rows = self.conn.execute(
                "SELECT * FROM posts WHERE thread_id=? ORDER BY id LIMIT ? OFFSET ?",
                (thread_id, per_page, offset),
            ).fetchall()
        return rows, total

    def post(self, post_id: int) -> sqlite3.Row | None:
        with self.lock:
            return self.conn.execute("SELECT * FROM posts WHERE id=?", (post_id,)).fetchone()

    def post_count(self, thread_id: int) -> int:
        with self.lock:
            return int(self.conn.execute(
                "SELECT COUNT(*) FROM posts WHERE thread_id=?", (thread_id,)
            ).fetchone()[0])

    def update_post(self, post_id: int, body: str) -> None:
        with self.lock:
            self.conn.execute("UPDATE posts SET body=?, edited_at=? WHERE id=?", (body, time.time(), post_id))
            self.conn.commit()

    def delete_post(self, post_id: int) -> None:
        with self.lock:
            self.conn.execute("UPDATE posts SET deleted=1, body='' WHERE id=?", (post_id,))
            self.conn.commit()

    def delete_thread(self, thread_id: int) -> None:
        with self.lock:
            self.conn.execute("UPDATE threads SET deleted=1 WHERE id=?", (thread_id,))
            self.conn.commit()

    def set_flag(self, thread_id: int, flag: str, value: bool) -> None:
        if flag not in ("locked", "pinned"):
            raise ValueError(f"unknown thread flag: {flag}")
        with self.lock:
            self.conn.execute(f"UPDATE threads SET {flag}=? WHERE id=?", (1 if value else 0, thread_id))
            self.conn.commit()

    # ---------- ownership & sessions ----------

    def is_owner(self, sid: str, post_id: int) -> bool:
        with self.lock:
            return self.conn.execute(
                "SELECT 1 FROM owners WHERE sid=? AND post_id=?", (sid, post_id)
            ).fetchone() is not None

    def new_session(self) -> str:
        sid = secrets.token_urlsafe(24)
        now = time.time()
        with self.lock:
            self.conn.execute("DELETE FROM sessions WHERE expires_at < ?", (now,))
            self.conn.execute("INSERT INTO sessions VALUES (?,0,?,?)", (sid, now, now + SESSION_TTL))
            self.conn.commit()
        return sid

    def session(self, sid: str) -> sqlite3.Row | None:
        if not sid or len(sid) > 64:
            return None
        with self.lock:
            row = self.conn.execute("SELECT * FROM sessions WHERE sid=?", (sid,)).fetchone()
            if row is None:
                return None
            if row["expires_at"] < time.time():
                self.conn.execute("DELETE FROM sessions WHERE sid=?", (sid,))
                self.conn.commit()
                return None
            return row

    def set_mod(self, sid: str, is_mod: bool) -> None:
        with self.lock:
            self.conn.execute("UPDATE sessions SET is_mod=? WHERE sid=?", (1 if is_mod else 0, sid))
            self.conn.commit()

    def counts(self) -> dict[str, int]:
        with self.lock:
            boards = int(self.conn.execute("SELECT COUNT(*) FROM boards").fetchone()[0])
            threads = int(self.conn.execute("SELECT COUNT(*) FROM threads WHERE deleted=0").fetchone()[0])
            posts = int(self.conn.execute(
                "SELECT COUNT(*) FROM posts p JOIN threads t ON t.id=p.thread_id "
                "WHERE p.deleted=0 AND t.deleted=0").fetchone()[0])
        return {"boards": boards, "threads": threads, "posts": posts}

    def close(self) -> None:
        self.conn.close()
