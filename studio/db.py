"""Mémoire (SQLite) : articles vus, sujets déjà traités, posts générés. Une connexion par usage (multi-thread sûr)."""
from __future__ import annotations

import json
import sqlite3
import time
from contextlib import contextmanager

from .config import DATA

SCHEMA = """
PRAGMA journal_mode=WAL;
CREATE TABLE IF NOT EXISTS articles (
    media TEXT, id TEXT, source TEXT, title TEXT, summary TEXT, link TEXT,
    published REAL, fetched REAL, weight REAL, trusted INTEGER, PRIMARY KEY (media, id)
);
CREATE INDEX IF NOT EXISTS idx_art ON articles(media, published);
CREATE TABLE IF NOT EXISTS covered (media TEXT, article_id TEXT, created REAL, PRIMARY KEY (media, article_id));
CREATE TABLE IF NOT EXISTS posts (
    id INTEGER PRIMARY KEY AUTOINCREMENT, media TEXT, created REAL, headline TEXT, importance INTEGER,
    sensitive INTEGER, n_sources INTEGER, data TEXT,
    posted_x INTEGER DEFAULT 0, posted_social INTEGER DEFAULT 0, hidden INTEGER DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_posts ON posts(media, created);
CREATE TABLE IF NOT EXISTS kv (key TEXT PRIMARY KEY, value TEXT);
"""


@contextmanager
def connect():
    DATA.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(str(DATA / "studio.db"), timeout=30)
    con.row_factory = sqlite3.Row
    try:
        yield con
        con.commit()
    finally:
        con.close()


def init() -> None:
    with connect() as con:
        con.executescript(SCHEMA)
        cols = {r[1] for r in con.execute("PRAGMA table_info(articles)").fetchall()}
        for col, typ in (("dated", "INTEGER DEFAULT 0"), ("image", "TEXT DEFAULT ''")):
            if col not in cols:
                con.execute(f"ALTER TABLE articles ADD COLUMN {col} {typ}")


def add_articles(media: str, articles: list[dict]) -> int:
    with connect() as con:
        before = con.total_changes
        con.executemany(
            "INSERT OR IGNORE INTO articles (media,id,source,title,summary,link,published,fetched,weight,trusted,dated,image) "
            "VALUES (:media,:id,:source,:title,:summary,:link,:published,:fetched,:weight,:trusted,:dated,:image)",
            [{**a, "media": media} for a in articles],
        )
        return con.total_changes - before


def recent_articles(media: str, hours: float) -> list[dict]:
    with connect() as con:
        rows = con.execute("SELECT * FROM articles WHERE media=? AND published>=? ORDER BY published DESC",
                           (media, time.time() - hours * 3600)).fetchall()
        return [dict(r) for r in rows]


def mark_covered(media: str, ids) -> None:
    now = time.time()
    with connect() as con:
        con.executemany("INSERT OR IGNORE INTO covered VALUES (?,?,?)", [(media, i, now) for i in ids])


def covered_ids(media: str, hours: float = 72) -> set[str]:
    with connect() as con:
        rows = con.execute("SELECT article_id FROM covered WHERE media=? AND created>=?",
                           (media, time.time() - hours * 3600)).fetchall()
        return {r[0] for r in rows}


def add_post(media: str, headline: str, importance: int, sensitive: bool, n_sources: int, data: dict) -> int:
    with connect() as con:
        cur = con.execute(
            "INSERT INTO posts (media,created,headline,importance,sensitive,n_sources,data) VALUES (?,?,?,?,?,?,?)",
            (media, time.time(), headline, importance, int(sensitive), n_sources, json.dumps(data, ensure_ascii=False)))
        return cur.lastrowid


def _post(r) -> dict:
    d = dict(r)
    d["data"] = json.loads(d["data"] or "{}")
    return d


def posts(media: str | None = None, since: float = 0) -> list[dict]:
    q, args = "SELECT * FROM posts WHERE created>=?", [since]
    if media:
        q += " AND media=?"
        args.append(media)
    with connect() as con:
        return [_post(r) for r in con.execute(q + " ORDER BY created DESC", args).fetchall()]


def get_post(pid: int) -> dict | None:
    with connect() as con:
        r = con.execute("SELECT * FROM posts WHERE id=?", (pid,)).fetchone()
        return _post(r) if r else None


def set_status(pid: int, **fields) -> None:
    allowed = {k: int(bool(v)) for k, v in fields.items() if k in ("posted_x", "posted_social", "hidden")}
    if not allowed:
        return
    with connect() as con:
        con.execute(f"UPDATE posts SET {','.join(f'{k}=?' for k in allowed)} WHERE id=?", (*allowed.values(), pid))


def update_data(pid: int, data: dict) -> None:
    with connect() as con:
        con.execute("UPDATE posts SET data=? WHERE id=?", (json.dumps(data, ensure_ascii=False), pid))


def delete_post(pid: int) -> dict | None:
    p = get_post(pid)
    with connect() as con:
        con.execute("DELETE FROM posts WHERE id=?", (pid,))
    return p


def count_today(media: str, midnight: float) -> int:
    with connect() as con:
        return con.execute("SELECT COUNT(*) FROM posts WHERE media=? AND created>=?", (media, midnight)).fetchone()[0]


def kv_get(key: str, default=None):
    with connect() as con:
        r = con.execute("SELECT value FROM kv WHERE key=?", (key,)).fetchone()
        return r[0] if r else default


def kv_set(key: str, value) -> None:
    with connect() as con:
        con.execute("INSERT OR REPLACE INTO kv VALUES (?,?)", (key, str(value)))


def prune(keep_days: float) -> list[dict]:
    """Supprime les vieux articles et posts ; renvoie les posts supprimés (pour effacer leurs fichiers)."""
    old_ts = time.time() - keep_days * 86400
    with connect() as con:
        old = [_post(r) for r in con.execute("SELECT * FROM posts WHERE created<?", (old_ts,)).fetchall()]
        con.execute("DELETE FROM posts WHERE created<?", (old_ts,))
        con.execute("DELETE FROM articles WHERE fetched<?", (time.time() - 8 * 86400,))   # 8 jours : utile aux enquêtes
        con.execute("DELETE FROM covered WHERE created<?", (time.time() - 5 * 86400,))
    return old
