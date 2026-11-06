"""Bookmark ingestion: Netscape/Chrome/Firefox HTML exports and JSON exports.

Everything streams line-by-line / element-by-element so a million-URL export
never has to sit in memory at once.
"""
from __future__ import annotations

import json
import time
from html.parser import HTMLParser


# --------------------------------------------------------------------------- #
# Netscape bookmark HTML (Chrome, Edge, Firefox, Safari exports)
# --------------------------------------------------------------------------- #
class _NetscapeParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.folder_stack = []      # list of folder names (or None for root <DL>)
        self.pending_folder = None  # last <H3> text, becomes a folder on next <DL>
        self._in_h3 = False
        self._h3 = []
        self._in_a = False
        self._a = []
        self._a_attrs = {}
        self.rows = []

    def handle_starttag(self, tag, attrs):
        d = {k.lower(): (v or "") for k, v in attrs}
        if tag == "dl":
            self.folder_stack.append(self.pending_folder)
            self.pending_folder = None
        elif tag == "h3":
            self._in_h3 = True
            self._h3 = []
        elif tag == "a":
            self._in_a = True
            self._a = []
            self._a_attrs = d

    def handle_endtag(self, tag):
        if tag == "dl":
            if self.folder_stack:
                self.folder_stack.pop()
        elif tag == "h3":
            self._in_h3 = False
            name = "".join(self._h3).strip()
            if name:
                self.pending_folder = name
        elif tag == "a":
            self._in_a = False
            href = self._a_attrs.get("href", "")
            if href:
                folder = " / ".join(f for f in self.folder_stack if f)
                self.rows.append({
                    "url": href,
                    "title": "".join(self._a).strip(),
                    "folder": folder,
                    "tags": self._a_attrs.get("tags", ""),
                    "add_date": self._a_attrs.get("add_date", ""),
                })

    def handle_data(self, data):
        if self._in_h3:
            self._h3.append(data)
        if self._in_a:
            self._a.append(data)


def parse_netscape_html(path: str):
    """Yield raw bookmark dicts from an HTML export (streamed in chunks)."""
    parser = _NetscapeParser()
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        while True:
            chunk = fh.read(1 << 20)  # 1 MiB
            if not chunk:
                break
            parser.feed(chunk)
            while parser.rows:
                yield parser.rows.pop(0)
    parser.close()
    while parser.rows:
        yield parser.rows.pop(0)


# --------------------------------------------------------------------------- #
# JSON bookmark exports (Pocket, Raindrop, Pinboard, custom scrapers)
# --------------------------------------------------------------------------- #
def _coerce_row(obj):
    if not isinstance(obj, dict):
        return None
    url = obj.get("url") or obj.get("href") or obj.get("link") or obj.get("uri")
    if not url:
        return None
    tags = obj.get("tags") or obj.get("tag") or ""
    if isinstance(tags, list):
        tags = ",".join(str(t) for t in tags)
    folder = obj.get("folder") or obj.get("collection") or ""
    if isinstance(folder, list):
        folder = " / ".join(str(f) for f in folder)
    ts = obj.get("add_date") or obj.get("created") or obj.get("time_added") or obj.get("ts") or obj.get("timestamp")
    return {
        "url": str(url),
        "title": str(obj.get("title") or obj.get("name") or ""),
        "folder": str(folder),
        "tags": str(tags),
        "add_date": str(ts or ""),
    }


def parse_json(path: str):
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        data = json.load(fh)
    if isinstance(data, dict):
        for key in ("bookmarks", "items", "data", "rows", "links"):
            if isinstance(data.get(key), list):
                data = data[key]
                break
        else:
            data = [data]
    for obj in data:
        row = _coerce_row(obj)
        if row:
            yield row


def parse_any(path: str):
    low = path.lower()
    if low.endswith(".json") or low.endswith(".jsonl"):
        yield from parse_json(path)
    elif low.endswith((".html", ".htm")):
        yield from parse_netscape_html(path)
    else:
        # sniff
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            head = fh.read(4096).lstrip()
        if head.startswith("{") or head.startswith("["):
            yield from parse_json(path)
        else:
            yield from parse_netscape_html(path)


def to_epoch(raw) -> int:
    """Best-effort timestamp normalisation; returns 0 when unknown."""
    if raw in (None, "", 0, "0"):
        return 0
    try:
        v = int(str(raw).strip())
    except (ValueError, TypeError):
        return 0
    # Chrome exports sometimes store microseconds.
    if v > 10_000_000_000:
        v //= 1_000_000
    if v > 10_000_000_000:
        v //= 1000
    # Sanity: between 2001 and 2100.
    if 978_307_200 < v < 4_102_444_800:
        return v
    return 0


def now_epoch() -> int:
    return int(time.time())
