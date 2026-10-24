#!/usr/bin/env python3
"""Bygger den publika sajten i public/. Bara granskade notiser kommer med.

  python publish.py                       bygg public/ ur arkivet av godkända notiser
  python publish.py --forhandsvisning DIR bygg en platt förhandsvisning av dagens utkast (märkt, ej publik)

Sidorna byggs av sajt.py. Sätt NN_LANSERAD=1 när sajten ska synas i sökmotorer; innan dess
får alla sidor noindex och robots.txt säger nej.
"""
import argparse
import json
import os
import shutil
import time
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
    stats = sajt.build(out, events, flat=True, banner="Förhandsvisning: ogranskade utkast · Preview: unreviewed drafts",
                       noindex=True, over_sprak=data.get("over_sprak", False))
    png = ROOT / "site" / "newsgator.png"
    if png.exists():
        shutil.copy(png, out / "newsgator.png")
    print(f"Förhandsvisning: {stats['notiser']} notiser -> {out}")


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

    nav = ROOT / "site" / "navigatorn-sv.html"
    has_issue = nav.exists() and "UTKAST" not in nav.read_text(encoding="utf-8")

    PUBLIC.mkdir(exist_ok=True)
    stats = sajt.build(PUBLIC, events, flat=False, noindex=not launched, has_issue=has_issue,
                       over_sprak=_flode().get("over_sprak", False))

    png = ROOT / "site" / "newsgator.png"
    if png.exists():
        shutil.copy(png, PUBLIC / "newsgator.png")

    if has_issue:
        (PUBLIC / "navigatorn").mkdir(exist_ok=True)
        shutil.copy(nav, PUBLIC / "navigatorn" / "index.html")
        en = ROOT / "site" / "navigatorn-en.html"
        if en.exists():
            shutil.copy(en, PUBLIC / "navigatorn" / "en.html")

    (PUBLIC / "robots.txt").write_text(
        "User-agent: *\n" + (f"Allow: /\nSitemap: {sajt.SITE_URL}/sitemap.xml\n" if launched else "Disallow: /\n"), encoding="utf-8")
    sitemap = PUBLIC / "sitemap.xml"
    if launched:
        urls = ["/", "/om/", "/kallor/", "/navigatorn/"] + [f"/{k}/" for k, *_ in sajt.SECTIONS] + [f"/n/{e['id']}/" for e in events]
        sitemap.write_text('<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
                           + "".join(f"<url><loc>{sajt.SITE_URL}{u}</loc></url>" for u in urls) + "</urlset>", encoding="utf-8")
    elif sitemap.exists():
        sitemap.unlink()
    print(f"Publik sajt: {stats['notiser']} granskade notiser ({stats['forstasida']} på förstasidan) -> {PUBLIC}")


if __name__ == "__main__":
    main()
