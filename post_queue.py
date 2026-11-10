"""Post queue (SQLite) and the background scheduler that publishes posts when they are due."""

from __future__ import annotations

import datetime as dt
import sqlite3
import threading
import time
from pathlib import Path

import linkedin

DB = Path(__file__).parent / "posts.db"
_lock = threading.Lock()


def _conn():
    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row
    return c


def init():
    with _conn() as c:
        c.execute("""CREATE TABLE IF NOT EXISTS posts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT NOT NULL,
            text TEXT NOT NULL,
            source_url TEXT DEFAULT '',
            source_title TEXT DEFAULT '',
            status TEXT NOT NULL DEFAULT 'draft',   -- draft | scheduled | posting | posted | failed
            scheduled_at TEXT,                      -- UTC ISO-8601
            posted_at TEXT,
            post_urn TEXT,
            test_mode INTEGER DEFAULT 0,
            error TEXT)""")


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def _parse_when(s: str) -> str:
    when = dt.datetime.fromisoformat(s.replace("Z", "+00:00"))
    if when.tzinfo is None:
        raise ValueError("Time must include a timezone")
    if when < dt.datetime.now(dt.timezone.utc) - dt.timedelta(minutes=1):
        raise ValueError("That time is in the past")
    return when.astimezone(dt.timezone.utc).isoformat(timespec="seconds")


def list_posts() -> list[dict]:
    with _conn() as c:
        rows = c.execute("""SELECT * FROM posts ORDER BY
            CASE status WHEN 'scheduled' THEN 0 WHEN 'draft' THEN 1 WHEN 'failed' THEN 2 ELSE 3 END,
            COALESCE(scheduled_at, posted_at, created_at) DESC""").fetchall()
    return [dict(r) for r in rows]


def get(pid: int) -> dict | None:
    with _conn() as c:
        r = c.execute("SELECT * FROM posts WHERE id=?", (pid,)).fetchone()
    return dict(r) if r else None


def save(text: str, source_url: str = "", source_title: str = "", scheduled_at: str | None = None,
         pid: int | None = None) -> dict:
    if not text.strip():
        raise ValueError("The post is empty")
    if len(text) > 3000:
        raise ValueError(f"LinkedIn allows 3000 characters; this post has {len(text)}")
    status, when = ("scheduled", _parse_when(scheduled_at)) if scheduled_at else ("draft", None)
    with _lock, _conn() as c:
        if pid:
            cur = get(pid)
            if not cur or cur["status"] in ("posted", "posting"):
                raise ValueError("This post was already published and can't be edited")
            c.execute("UPDATE posts SET text=?, source_url=?, source_title=?, status=?, scheduled_at=?, error=NULL WHERE id=?",
                      (text, source_url, source_title, status, when, pid))
        else:
            pid = c.execute("INSERT INTO posts (created_at, text, source_url, source_title, status, scheduled_at) VALUES (?,?,?,?,?,?)",
                            (_now(), text, source_url, source_title, status, when)).lastrowid
    return get(pid)


def delete(pid: int):
    with _lock, _conn() as c:
        c.execute("DELETE FROM posts WHERE id=? AND status NOT IN ('posted','posting')", (pid,))


def publish_now(pid: int) -> dict:
    with _lock, _conn() as c:
        # claim the row so the scheduler and a click can't both publish it
        n = c.execute("UPDATE posts SET status='posting' WHERE id=? AND status IN ('draft','scheduled','failed')",
                      (pid,)).rowcount
    if not n:
        return get(pid) or {}
    p = get(pid)
    res = linkedin.publish(p["text"], p["source_url"], p["source_title"])
    with _lock, _conn() as c:
        if res["ok"]:
            c.execute("UPDATE posts SET status='posted', posted_at=?, post_urn=?, test_mode=?, error=NULL WHERE id=?",
                      (_now(), res.get("post_urn"), int(res["test_mode"]), pid))
        else:
            c.execute("UPDATE posts SET status='failed', error=? WHERE id=?", (res["error"], pid))
    return get(pid)


def _due() -> list[int]:
    with _conn() as c:
        return [r["id"] for r in c.execute(
            "SELECT id FROM posts WHERE status='scheduled' AND scheduled_at <= ?", (_now(),))]


def _loop(interval: int):
    while True:
        try:
            for pid in _due():
                publish_now(pid)
        except Exception as e:  # keep the scheduler alive
            print("scheduler error:", e)
        time.sleep(interval)


def start_scheduler(interval: int = 30):
    init()
    threading.Thread(target=_loop, args=(interval,), daemon=True, name="post-scheduler").start()
