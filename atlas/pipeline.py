"""The build pipeline: bookmarks in, technology graph out."""
from __future__ import annotations

from . import relations as rel


def ingest_rows(con, rows, canonicalize, identity, to_epoch):
    """Stream raw bookmark dicts into the store with normalised keys."""
    batch = []
    seen = set()
    n = 0
    for row in rows:
        canon = canonicalize(row.get("url"))
        if not canon or canon in seen:
            continue
        seen.add(canon)
        host, registrable, brand, method = identity(canon)
        batch.append((
            row.get("url", ""), canon, host, registrable, brand, method,
            (row.get("title") or "")[:512], (row.get("folder") or "")[:512],
            (row.get("tags") or "")[:512], to_epoch(row.get("add_date")),
        ))
        n += 1
        if len(batch) >= 5000:
            con.executemany(
                "INSERT INTO bookmarks(url,url_canonical,host,registrable,brand,method,title,folder,tags,add_date)"
                " VALUES(?,?,?,?,?,?,?,?,?,?)", batch)
            batch = []
    if batch:
        con.executemany(
            "INSERT INTO bookmarks(url,url_canonical,host,registrable,brand,method,title,folder,tags,add_date)"
            " VALUES(?,?,?,?,?,?,?,?,?,?)", batch)
    con.commit()
    return {"ingested": n}


def build_domains(con):
    con.execute("DELETE FROM domains")
    con.execute(
        "INSERT INTO domains(registrable, host_sample, brand, method, bookmark_count, title_sample) "
        "SELECT registrable, MIN(host), MIN(brand), MIN(method), COUNT(*), MIN(title) "
        "FROM bookmarks WHERE registrable IS NOT NULL AND registrable <> '' "
        "GROUP BY registrable"
    )
    con.commit()
    return {"domains": con.execute("SELECT COUNT(*) c FROM domains").fetchone()["c"]}


def resolve_technologies(con, resolver):
    con.execute("DELETE FROM technologies")
    con.execute("DELETE FROM tech_domains")
    con.execute("DELETE FROM bookmark_tech")
    con.commit()

    techs = {}
    dom_rows = list(con.execute(
        "SELECT registrable, brand, method, bookmark_count FROM domains"))
    for row in dom_rows:
        key = resolver.key(row["brand"])
        t = techs.setdefault(key, {"brands": set(), "domains": set(), "bookmarks": 0})
        t["brands"].add(row["brand"])
        t["domains"].add((row["registrable"], row["method"] or "", row["bookmark_count"]))
        t["bookmarks"] += row["bookmark_count"]

    for key, t in techs.items():
        con.execute(
            "INSERT OR REPLACE INTO technologies(key,name,kind,aliases,domain_count,bookmark_count)"
            " VALUES(?,?,?,?,?,?)",
            (key, resolver.name(key), resolver.kind(key),
             ",".join(sorted(t["brands"])), len(t["domains"]), t["bookmarks"]),
        )
        con.executemany(
            "INSERT INTO tech_domains(tech_key,registrable,method,bookmarks) VALUES(?,?,?,?)",
            [(key, reg, method, cnt) for (reg, method, cnt) in t["domains"]],
        )

    batch = []
    for row in con.execute("SELECT id, brand FROM bookmarks"):
        batch.append((row["id"], resolver.key(row["brand"])))
        if len(batch) >= 5000:
            con.executemany("INSERT INTO bookmark_tech VALUES(?,?)", batch)
            batch = []
    if batch:
        con.executemany("INSERT INTO bookmark_tech VALUES(?,?)", batch)
    con.commit()
    return {"technologies": len(techs)}


def build_relations(con, resolver):
    rel.build_contexts(con)
    rel.build_cooccurrence(con)
    con.commit()
    extra = rel.build_alternatives(con, resolver)
    con.commit()
    n = con.execute("SELECT COUNT(*) c FROM tech_relations").fetchone()["c"]
    return {"relations": n, **extra}


def stats(con):
    q = lambda sql: con.execute(sql).fetchone()[0]
    return {
        "bookmarks": q("SELECT COUNT(*) FROM bookmarks"),
        "domains": q("SELECT COUNT(*) FROM domains"),
        "technologies": q("SELECT COUNT(*) FROM technologies"),
        "relations": q("SELECT COUNT(*) FROM tech_relations"),
        "bookmarks_with_tech": q("SELECT COUNT(DISTINCT bookmark_id) FROM bookmark_tech"),
    }
