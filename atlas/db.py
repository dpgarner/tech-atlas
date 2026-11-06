"""SQLite schema and connection helpers.

The store is deliberately plain SQLite: it ingests a million rows fine when we
stream and index, it is a single portable file, and it is trivially inspectable.
Switch to DuckDB/Postgres only if you outgrow single-machine analytics.
"""
from __future__ import annotations

import os
import sqlite3

SCHEMA = """
PRAGMA journal_mode = WAL;

CREATE TABLE IF NOT EXISTS bookmarks (
    id            INTEGER PRIMARY KEY,
    url           TEXT,
    url_canonical TEXT,
    host          TEXT,
    registrable   TEXT,
    brand         TEXT,
    method        TEXT,           -- repo | domain | aggregator
    site          TEXT,           -- aggregation key (repo-level for code hosts)
    title         TEXT,
    folder        TEXT,
    tags          TEXT,
    add_date      INTEGER
);
CREATE INDEX IF NOT EXISTS ix_bm_site        ON bookmarks(site);
CREATE INDEX IF NOT EXISTS ix_bm_registrable ON bookmarks(registrable);
CREATE INDEX IF NOT EXISTS ix_bm_brand       ON bookmarks(brand);
CREATE INDEX IF NOT EXISTS ix_bm_folder      ON bookmarks(folder);

CREATE TABLE IF NOT EXISTS domains (
    site           TEXT PRIMARY KEY,
    registrable    TEXT,
    host_sample    TEXT,
    brand          TEXT,
    method         TEXT,
    bookmark_count INTEGER,
    title_sample   TEXT
);

CREATE TABLE IF NOT EXISTS technologies (
    key            TEXT PRIMARY KEY,   -- canonical slug, e.g. 'react'
    name           TEXT,               -- display name, e.g. 'React'
    kind           TEXT,               -- category bucket, e.g. 'frontend'
    website        TEXT,
    description    TEXT,
    aliases        TEXT,               -- comma-joined raw brands folded in
    domain_count   INTEGER DEFAULT 0,
    bookmark_count INTEGER DEFAULT 0,
    wikidata       TEXT
);

CREATE TABLE IF NOT EXISTS tech_domains (
    tech_key   TEXT,
    site       TEXT,
    registrable TEXT,
    method     TEXT,
    bookmarks  INTEGER
);
CREATE INDEX IF NOT EXISTS ix_td_tech ON tech_domains(tech_key);

CREATE TABLE IF NOT EXISTS bookmark_tech (
    bookmark_id INTEGER,
    tech_key    TEXT
);
CREATE INDEX IF NOT EXISTS ix_bt_tech ON bookmark_tech(tech_key);
CREATE INDEX IF NOT EXISTS ix_bt_bm   ON bookmark_tech(bookmark_id);

CREATE TABLE IF NOT EXISTS tech_relations (
    a        TEXT,
    b        TEXT,
    kind     TEXT,     -- co_occurs | alternative
    weight   REAL,
    evidence TEXT,
    primary KEY (a, b, kind)
);
CREATE INDEX IF NOT EXISTS ix_rel_a ON tech_relations(a);

CREATE TABLE IF NOT EXISTS meta (
    k TEXT PRIMARY KEY,
    v TEXT
);
"""


def connect(path: str) -> sqlite3.Connection:
    con = sqlite3.connect(path)
    con.row_factory = sqlite3.Row
    con.executescript(SCHEMA)
    _migrate(con)
    return con


def _migrate(con: sqlite3.Connection) -> None:
    """Light-touch migrations so older stores keep working."""
    cols = {r[1] for r in con.execute("PRAGMA table_info(bookmarks)")}
    if cols and "site" not in cols:
        con.execute("ALTER TABLE bookmarks ADD COLUMN site TEXT")
    dcols = {r[1] for r in con.execute("PRAGMA table_info(domains)")}
    if dcols and "site" not in dcols:
        con.execute("DROP TABLE domains")
        con.execute(
            "CREATE TABLE domains (site TEXT PRIMARY KEY, registrable TEXT, "
            "host_sample TEXT, brand TEXT, method TEXT, bookmark_count INTEGER, "
            "title_sample TEXT)"
        )
    con.commit()


def reset(path: str) -> None:
    for suffix in ("", "-wal", "-shm"):
        p = path + suffix
        if os.path.exists(p):
            os.remove(p)
