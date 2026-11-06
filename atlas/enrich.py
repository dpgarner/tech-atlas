"""Optional enrichment via Wikidata (free, no key, cacheable).

Only the *head* of the distribution needs enrichment: your top few hundred
technologies carry most of the value. The long tail stays as passive signals
(name + count + relations), which is enough to find and compare it.
"""
from __future__ import annotations

import json
import os
import time
import urllib.parse
import urllib.request

API = "https://www.wikidata.org/w/api.php"
UA = "tech-atlas/0.1 (bookmark technology atlas; contact: local)"


def _get(params: dict, timeout: int = 15):
    url = API + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _search(label: str):
    try:
        data = _get({
            "action": "wbsearchentities", "search": label, "language": "en",
            "uselang": "en", "format": "json", "limit": 1, "type": "item",
        })
    except Exception:
        return None
    hits = data.get("search") or []
    if not hits:
        return None
    return hits[0].get("id")


def _entity(qid: str):
    try:
        data = _get({
            "action": "wbgetentities", "ids": qid, "format": "json",
            "props": "descriptions|claims", "languages": "en",
        })
    except Exception:
        return None
    ent = (data.get("entities") or {}).get(qid)
    if not ent:
        return None
    desc = ((ent.get("descriptions") or {}).get("en") or {}).get("value", "")
    website = ""
    claims = ent.get("claims") or {}
    for snak in (claims.get("P856") or []):  # official website
        try:
            website = snak["mainsnak"]["datavalue"]["value"]
            break
        except (KeyError, TypeError):
            continue
    return {"qid": qid, "description": desc, "website": website}


class Enricher:
    def __init__(self, cache_path: str):
        self.cache_path = cache_path
        self.cache = {}
        if os.path.exists(cache_path):
            try:
                with open(cache_path, "r", encoding="utf-8") as fh:
                    self.cache = json.load(fh)
            except (ValueError, OSError):
                self.cache = {}

    def lookup(self, name: str) -> dict:
        key = name.strip().lower()
        if key in self.cache:
            return self.cache[key]
        qid = _search(name)
        result = {"qid": "", "description": "", "website": ""}
        if qid:
            ent = _entity(qid) or {}
            result = ent
        self.cache[key] = result
        return result

    def save(self):
        os.makedirs(os.path.dirname(self.cache_path), exist_ok=True)
        with open(self.cache_path, "w", encoding="utf-8") as fh:
            json.dump(self.cache, fh, ensure_ascii=False, indent=1)


def enrich(con, limit: int = 200, cache_path: str = "cache/wikidata.json", sleep: float = 0.2):
    enr = Enricher(cache_path)
    rows = list(con.execute(
        "SELECT key, name FROM technologies ORDER BY bookmark_count DESC LIMIT ?",
        (limit,),
    ))
    updated = 0
    for row in rows:
        info = enr.lookup(row["name"])
        if info.get("description") or info.get("website"):
            con.execute(
                "UPDATE technologies SET description=?, website=?, wikidata=? WHERE key=?",
                (info.get("description", ""), info.get("website", ""), info.get("qid", ""), row["key"]),
            )
            updated += 1
        time.sleep(sleep)
    con.commit()
    enr.save()
    return {"enriched": updated, "considered": len(rows)}
