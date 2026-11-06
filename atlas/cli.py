"""Command-line interface for tech-atlas."""
from __future__ import annotations

import argparse
import json
import os
import sys

from . import db, export, pipeline
from .enrich import enrich
from .ingest import parse_any, to_epoch
from .resolve import Resolver
from .urls import canonicalize, identity

DEFAULT_DB = "atlas.db"


def _opener(path):
    return db.connect(path)


def cmd_ingest(args):
    con = _opener(args.db)
    total = 0
    for source in args.sources:
        rows = parse_any(source)
        res = pipeline.ingest_rows(con, rows, canonicalize, identity, to_epoch)
        total += res["ingested"]
        print(f"  ingested {res['ingested']:>9,}  <- {source}")
    print(f"total in store: {pipeline.stats(con)['bookmarks']:,}")
    con.close()


def cmd_build(args):
    con = _opener(args.db)
    resolver = Resolver()
    print("domains  :", pipeline.build_domains(con))
    print("resolve  :", pipeline.resolve_technologies(con, resolver))
    print("relations:", pipeline.build_relations(con, resolver))
    print("stats    :", json.dumps(pipeline.stats(con)))
    con.close()


def cmd_enrich(args):
    con = _opener(args.db)
    print("enrich   :", enrich(con, limit=args.limit, cache_path=args.cache))
    con.close()


def cmd_export(args):
    con = _opener(args.db)
    print("export   :", export.export_graph(con, args.out, top_edges=args.top_edges))
    con.close()


def cmd_stats(args):
    con = _opener(args.db)
    st = pipeline.stats(con)
    print(json.dumps(st, indent=2))
    print("\nTop technologies:")
    for row in con.execute(
        "SELECT name, kind, bookmark_count, domain_count FROM technologies "
        "ORDER BY bookmark_count DESC LIMIT 25"
    ):
        print(f"  {row['name']:<22} {row['kind']:<10} "
              f"{row['bookmark_count']:>6} bm / {row['domain_count']:>4} dom")
    print("\nStrongest relations:")
    for row in con.execute(
        "SELECT a,b,kind,weight FROM tech_relations ORDER BY weight DESC LIMIT 10"
    ):
        print(f"  {row['a']:<18} --{row['kind']:<12}--> {row['b']:<18} w={row['weight']}")
    con.close()


def cmd_demo(args):
    if os.path.exists(args.db):
        db.reset(args.db)
    con = _opener(args.db)
    sample = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                          "sample_data", "bookmarks_sample.html")
    res = pipeline.ingest_rows(con, parse_any(sample), canonicalize, identity, to_epoch)
    print("ingest   :", res)
    resolver = Resolver()
    print("domains  :", pipeline.build_domains(con))
    print("resolve  :", pipeline.resolve_technologies(con, resolver))
    print("relations:", pipeline.build_relations(con, resolver))
    out = args.out or os.path.join("ui", "data", "graph.json")
    print("export   :", export.export_graph(con, out))
    print("stats    :", json.dumps(pipeline.stats(con)))
    con.close()


def main(argv=None):
    p = argparse.ArgumentParser(prog="tech-atlas",
                                description="Build a technology atlas from bookmarks.")
    p.add_argument("--db", default=DEFAULT_DB, help="SQLite store path")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("ingest", help="load bookmark exports")
    s.add_argument("sources", nargs="+")
    s.set_defaults(func=cmd_ingest)

    s = sub.add_parser("build", help="derive domains, technologies, relations")
    s.set_defaults(func=cmd_build)

    s = sub.add_parser("enrich", help="optional Wikidata enrichment")
    s.add_argument("--limit", type=int, default=200)
    s.add_argument("--cache", default="cache/wikidata.json")
    s.set_defaults(func=cmd_enrich)

    s = sub.add_parser("export", help="write ui/data/graph.json")
    s.add_argument("--out", default=os.path.join("ui", "data", "graph.json"))
    s.add_argument("--top-edges", type=int, default=6000)
    s.set_defaults(func=cmd_export)

    s = sub.add_parser("stats", help="print store summary")
    s.set_defaults(func=cmd_stats)

    s = sub.add_parser("demo", help="run end-to-end on bundled sample data")
    s.add_argument("--out", default=None)
    s.set_defaults(func=cmd_demo)

    args = p.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    sys.exit(main())
