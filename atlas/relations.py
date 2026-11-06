"""Relation extraction: how technologies connect inside a bookmark corpus.

Two signals, both cheap and both meaningful:

* ``co_occurs``  - two technologies share a folder/tag context. This is the
  single most useful relation: people folder their bookmarks by topic, so
  "these two live in the same mental bucket" falls out for free.
* ``alternative`` - the title/folder literally says "A vs B" or "alternative
  to A", i.e. a comparison the user already made.
"""
from __future__ import annotations

import re

# Context fan-out guard: a folder/tag containing hundreds of technologies tells
# us nothing (it is a catch-all), so we prune it before counting pairs.
MAX_CONTEXT_TECHS = 150
MIN_PAIR_WEIGHT = 2

VS_RE = re.compile(
    r"([a-z0-9][a-z0-9\.\+#_-]{1,30})\s+(?:vs\.?|versus)\s+([a-z0-9][a-z0-9\.\+#_-]{1,30})",
    re.IGNORECASE,
)
ALT_RE = re.compile(
    r"alternative(?:s)?\s+to\s+([a-z0-9][a-z0-9\.\+#_-]{1,30})",
    re.IGNORECASE,
)


def build_contexts(con):
    """Materialise (bookmark_id, context) from folder paths and tags."""
    con.execute("DROP TABLE IF EXISTS ctx")
    con.execute("CREATE TEMP TABLE ctx (bookmark_id INTEGER, context TEXT)")
    batch = []
    cur = con.execute("SELECT id, folder, tags FROM bookmarks")
    for row in cur:
        bid = row["id"]
        for part in (row["folder"] or "").split(" / "):
            part = part.strip().lower()
            if part:
                batch.append((bid, "f:" + part))
        for tag in re.split(r"[,;]", row["tags"] or ""):
            tag = tag.strip().lower()
            if tag:
                batch.append((bid, "t:" + tag))
        if len(batch) >= 5000:
            con.executemany("INSERT INTO ctx VALUES (?,?)", batch)
            batch = []
    if batch:
        con.executemany("INSERT INTO ctx VALUES (?,?)", batch)
    con.execute("CREATE INDEX IF NOT EXISTS ix_ctx_context ON ctx(context)")


def build_cooccurrence(con):
    con.execute("DROP TABLE IF EXISTS ctx_tech")
    con.execute(
        "CREATE TEMP TABLE ctx_tech AS "
        "SELECT DISTINCT c.context AS context, bt.tech_key AS tech_key "
        "FROM ctx c JOIN bookmark_tech bt ON bt.bookmark_id = c.bookmark_id"
    )
    con.execute("CREATE INDEX IF NOT EXISTS ix_ct_context ON ctx_tech(context)")
    # Prune catch-all contexts.
    con.execute(
        "DELETE FROM ctx_tech WHERE context IN ("
        "  SELECT context FROM ctx_tech GROUP BY context HAVING COUNT(*) > ?"
        ")",
        (MAX_CONTEXT_TECHS,),
    )
    con.execute("DELETE FROM tech_relations WHERE kind='co_occurs'")
    con.execute(
        "INSERT OR REPLACE INTO tech_relations(a, b, kind, weight, evidence) "
        "SELECT a.tech_key, b.tech_key, 'co_occurs', COUNT(*), '' "
        "FROM ctx_tech a JOIN ctx_tech b "
        "  ON a.context = b.context AND a.tech_key < b.tech_key "
        "GROUP BY a.tech_key, b.tech_key "
        "HAVING COUNT(*) >= ?",
        (MIN_PAIR_WEIGHT,),
    )


def build_alternatives(con, resolver):
    """Detect explicit 'A vs B' / 'alternative to A' comparison evidence."""
    known = {r["key"] for r in con.execute("SELECT key FROM technologies")}
    pairs = {}      # (a,b) -> first evidence string
    alt_singles = {}  # tech -> count of "alternative to X"

    cur = con.execute("SELECT DISTINCT title, folder FROM bookmarks")
    for row in cur:
        text = f'{row["title"] or ""} {row["folder"] or ""}'
        low = text.lower()
        for m in VS_RE.finditer(low):
            a = resolver.key(m.group(1))
            b = resolver.key(m.group(2))
            if a in known and b in known and a != b:
                key = tuple(sorted((a, b)))
                pairs.setdefault(key, text.strip()[:180])
        for m in ALT_RE.finditer(low):
            a = resolver.key(m.group(1))
            if a in known:
                alt_singles[a] = alt_singles.get(a, 0) + 1

    con.execute("DELETE FROM tech_relations WHERE kind='alternative'")
    rows = [(a, b, "alternative", 1.0, ev) for (a, b), ev in pairs.items()]
    con.executemany(
        "INSERT OR REPLACE INTO tech_relations(a,b,kind,weight,evidence) VALUES (?,?,?,?,?)",
        rows,
    )
    return {"alternative_pairs": len(rows)}
