#!/usr/bin/env python3
"""Bygger den publika sajten i public/. Bara granskade notiser kommer med.

  python publish.py                       bygg public/ ur arkivet av godkända notiser: /sv/, /en/ och en valsida i roten
  python publish.py --forhandsvisning DIR bygg en platt förhandsvisning av dagens utkast (märkt, ej publik)

Sidorna byggs av sajt.py. Sätt NN_LANSERAD=1 när sajten ska synas i sökmotorer; innan dess
får alla sidor noindex och robots.txt säger nej.
"""
import argparse
import json
import os
import shutil
import time
from datetime import datetime, timezone
from pathlib import Path

import sajt
from newsletter import load_archive

ROOT = Path(__file__).parent
PUBLIC = ROOT / "public"
FLODE = ROOT / "data" / "flode.json"


def _flode():
    return json.loads(FLODE.read_text(encoding="utf-8")) if FLODE.exists() else {"handelser": [], "over_sprak": False}


def preview(out):
    data = _flode()
    skapad = time.time()
    events = []
    for e in data["handelser"]:
        if (e.get("utkast") or {}).get("rubrik_sv"):
            events.append({**e, "granskad": True, "godkand_tid": skapad})
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    stats = sajt.build(out, events, flat=True, konsol=data["handelser"], banner="Förhandsvisning: ogranskade utkast · Preview: unreviewed drafts",
                       noindex=True, over_sprak=data.get("over_sprak", False))
    png = ROOT / "site" / "newsgator.png"
    if png.exists():
        shutil.copy(png, out / "newsgator.png")
    print(f"Förhandsvisning: {stats['notiser']} notiser -> {out}")


def skriv_status(public, data, notiser):
    """status.json: när sajten byggdes, när flödet skapades och hur många händelser. Går att övervaka utifrån."""
    (Path(public) / "status.json").write_text(json.dumps(
        {"byggd": datetime.now(timezone.utc).isoformat(), "flode_skapat": data.get("skapad"),
         "handelser": len(data.get("handelser", [])), "notiser": notiser}, ensure_ascii=False), encoding="utf-8")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--forhandsvisning", metavar="DIR", help="bygg platt förhandsvisning av dagens utkast")
    args = ap.parse_args()
    if args.forhandsvisning:
        preview(args.forhandsvisning)
        return

    launched = bool(os.environ.get("NN_LANSERAD"))
    events = sorted(load_archive().values(),
                    key=lambda e: (e.get("godkand_tid", 0) // 3600, e.get("poang", 0)), reverse=True)
    for e in events:
        e["granskad"] = True

    issues = {}
    for lang in sajt.utgava.UTGAVOR:
        nav = ROOT / "site" / f"navigatorn-{lang}.html"
        issues[lang] = nav.exists() and "UTKAST" not in nav.read_text(encoding="utf-8")

    PUBLIC.mkdir(exist_ok=True)
    flode = _flode()
    stats = sajt.build_editions(PUBLIC, events, noindex=not launched, issues=issues, over_sprak=flode.get("over_sprak", False),
                               konsol=flode.get("handelser", []))

    png = ROOT / "site" / "newsgator.png"
    if png.exists():
        shutil.copy(png, PUBLIC / "newsgator.png")

    for lang, ok in issues.items():
        if ok:
            (PUBLIC / lang / "navigatorn").mkdir(parents=True, exist_ok=True)
            shutil.copy(ROOT / "site" / f"navigatorn-{lang}.html", PUBLIC / lang / "navigatorn" / "index.html")

    (PUBLIC / "robots.txt").write_text(
        "User-agent: *\n" + (f"Allow: /\nSitemap: {sajt.SITE_URL}/sitemap.xml\n" if launched else "Disallow: /\n"), encoding="utf-8")
    sitemap = PUBLIC / "sitemap.xml"
    if launched:
        sitemap.write_text(sajt.sitemap_xml(stats["per_utgava"]), encoding="utf-8")
    elif sitemap.exists():
        sitemap.unlink()
    skriv_status(PUBLIC, flode, len(events))
    print(f"Publik sajt: {len(events)} granskade notiser, {len(stats['per_utgava']['sv'])} i /sv/ och {len(stats['per_utgava']['en'])} i /en/ -> {PUBLIC}")


if __name__ == "__main__":
    main()
