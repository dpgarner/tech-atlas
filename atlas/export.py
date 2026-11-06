"""Export the store into a self-contained JSON the browser UI can load."""
from __future__ import annotations

import json
import os
import time


def export_graph(con, out_path: str, top_edges: int = 6000, samples_per_tech: int = 8):
    nodes = []
    for row in con.execute(
        "SELECT key,name,kind,description,website,domain_count,bookmark_count "
        "FROM technologies ORDER BY bookmark_count DESC, domain_count DESC"
    ):
        samples = [r[0] for r in con.execute(
            "SELECT b.url_canonical FROM bookmark_tech bt "
            "JOIN bookmarks b ON b.id = bt.bookmark_id "
            "WHERE bt.tech_key = ? ORDER BY b.add_date DESC LIMIT ?",
            (row["key"], samples_per_tech),
        )]
        nodes.append({
            "id": row["key"],
            "name": row["name"],
            "kind": row["kind"],
            "count": row["bookmark_count"],
            "domains": row["domain_count"],
            "description": row["description"] or "",
            "website": row["website"] or "",
            "samples": samples,
        })

    edges = [{
        "source": r["a"], "target": r["b"], "kind": r["kind"],
        "weight": round(r["weight"], 2),
    } for r in con.execute(
        "SELECT a,b,kind,weight FROM tech_relations ORDER BY weight DESC LIMIT ?",
        (top_edges,),
    )]

    kinds = {}
    for n in nodes:
        kinds[n["kind"]] = kinds.get(n["kind"], 0) + 1

    payload = {
        "generated": int(time.time()),
        "stats": {
            "bookmarks": con.execute("SELECT COUNT(*) FROM bookmarks").fetchone()[0],
            "domains": con.execute("SELECT COUNT(*) FROM domains").fetchone()[0],
            "technologies": len(nodes),
            "relations": con.execute("SELECT COUNT(*) FROM tech_relations").fetchone()[0],
        },
        "kinds": kinds,
        "nodes": nodes,
        "edges": edges,
    }

    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, separators=(",", ":"))
    # Also emit a JS wrapper so the UI can be opened directly via file:// without
    # fetch/CORS restrictions (double-click friendly).
    js_path = os.path.splitext(out_path)[0] + ".js"
    with open(js_path, "w", encoding="utf-8") as fh:
        fh.write("window.ATLAS_DATA = ")
        json.dump(payload, fh, ensure_ascii=False, separators=(",", ":"))
        fh.write(";\n")
    return {"out": out_path, "nodes": len(nodes), "edges": len(edges),
            "bytes": os.path.getsize(out_path)}
