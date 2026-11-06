"""URL canonicalization and domain identity helpers.

Everything downstream depends on turning a raw bookmark URL into a small,
stable set of keys: a canonical URL, a host, a registrable domain, and a
"brand" (the likely technology identity behind the link).
"""
from __future__ import annotations

import re
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode

# Query params that never change what a page is about.
TRACKING_PARAMS = {
    "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
    "utm_id", "utm_name", "utm_reader", "gclid", "fbclid", "dclid", "msclkid",
    "mc_cid", "mc_eid", "igshid", "yclid", "ref", "ref_src", "ref_url",
    "source", "spm", "_ga", "_gl", "si", "s_kwcid",
}

# Two-label public suffixes we care about (subset; enough for real bookmark data).
MULTI_TLDS = {
    "co.uk", "org.uk", "ac.uk", "gov.uk", "me.uk", "ltd.uk", "plc.uk",
    "co.jp", "or.jp", "ne.jp", "ac.jp", "co.kr", "or.kr", "com.au",
    "net.au", "org.au", "edu.au", "co.nz", "net.nz", "org.nz", "com.br",
    "com.cn", "com.tw", "com.hk", "co.in", "net.in", "org.in", "com.mx",
    "co.za", "com.sg", "com.tr", "com.ar", "github.io",
}

# Hosts that are "hosting platforms": the technology is in the path, not the host.
REPO_HOSTS = {"github.com", "gitlab.com", "bitbucket.org", "codeberg.org", "sr.ht"}

# Hosts that are pure aggregators / not a technology themselves.
AGGREGATOR_HOSTS = {
    "news.ycombinator.com", "reddit.com", "twitter.com", "x.com", "medium.com",
    "youtube.com", "youtu.be", "linkedin.com", "facebook.com", "pinterest.com",
    "stackoverflow.com", "stackexchange.com", "quora.com", "substack.com",
    "wikipedia.org", "docs.google.com", "notion.so", "producthunt.com",
}


def canonicalize(url: str):
    """Return a canonical URL string, or None if it is not a usable http(s) link."""
    if not url:
        return None
    raw = url.strip()
    if not raw:
        return None
    try:
        parts = urlsplit(raw)
    except (ValueError, TypeError):
        return None
    scheme = (parts.scheme or "").lower()
    if scheme not in ("http", "https"):
        return None
    host = (parts.hostname or "").lower().strip(".")
    if not host or "." not in host and host != "localhost":
        return None
    if host.startswith("www."):
        host = host[4:]
    try:
        port = parts.port
    except ValueError:
        port = None
    netloc = host
    if port and not ((scheme == "http" and port == 80) or (scheme == "https" and port == 443)):
        netloc = f"{host}:{port}"
    path = parts.path or "/"
    path = re.sub(r"/{2,}", "/", path)
    if len(path) > 1 and path.endswith("/"):
        path = path[:-1]
    kept = [
        (k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True)
        if k.lower() not in TRACKING_PARAMS
    ]
    kept.sort()
    query = urlencode(kept)
    return urlunsplit((scheme, netloc, path, query, ""))  # fragment intentionally dropped


def registrable_domain(host: str) -> str:
    host = (host or "").lower().strip(".")
    labels = [l for l in host.split(".") if l]
    if len(labels) <= 2:
        return ".".join(labels)
    last2 = ".".join(labels[-2:])
    if last2 in MULTI_TLDS and len(labels) >= 3:
        return ".".join(labels[-3:])
    return last2


def root_label(registrable: str) -> str:
    """The first label of a registrable domain, e.g. react.dev -> 'react'."""
    return registrable.split(".")[0] if registrable else ""


def identity(canonical: str):
    """Derive (host, registrable, brand, method, site) for a canonical URL.

    site is the aggregation key for "who owns this link":
      - github.com/acme/widget      -> site 'github.com/acme/widget', brand 'widget'
      - docs.docker.com             -> site 'docker.com', brand 'docker'
      - news.ycombinator.com        -> site 'ycombinator.com', method 'aggregator'
    """
    parts = urlsplit(canonical)
    host = (parts.hostname or "").lower()
    registrable = registrable_domain(host)
    segs = [s for s in parts.path.split("/") if s]

    if registrable in REPO_HOSTS and len(segs) >= 2:
        owner = segs[0].lower()
        repo = _clean_repo_name(segs[1])
        return host, registrable, repo, "repo", f"{registrable}/{owner}/{repo}"

    brand = root_label(registrable)
    method = "aggregator" if registrable in AGGREGATOR_HOSTS else "domain"
    return host, registrable, brand, method, registrable


def _clean_repo_name(seg: str) -> str:
    seg = seg.lower()
    seg = re.sub(r"\.(git|html?|php|js|py)$", "", seg)
    seg = seg.replace("_", "-").strip("-.")
    return seg


def strip_known_prefixes(brand: str) -> str:
    """docs.foo.com and foo.com should converge on 'foo'."""
    for p in ("docs", "doc", "developer", "developers", "dev", "api", "learn",
              "www", "blog", "news", "get", "try", "about", "support", "help"):
        if brand == p:
            return brand
    return brand
