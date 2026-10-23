#!/usr/bin/env python3
"""Bygger den publika sajten i public/. Bara granskade notiser kommer med.

  python publish.py

public/index.html          granskade notiser från de senaste tre dygnen (ur data/arkiv.json)
public/navigatorn/          senaste morgonbrevet, om det har granskade notiser
public/newsgator.png        maskoten för e-post

Sätt NN_LANSERAD=1 när sajten ska synas i sökmotorer. Innan dess får sidorna noindex.
"""
import json
import os
import re
import shutil
import time
from datetime import datetime, timezone
from pathlib import Path

from newsletter import load_archive
from render import render

ROOT = Path(__file__).parent
PUBLIC = ROOT / "public"
DAGAR = 3


def main():
    PUBLIC.mkdir(exist_ok=True)
    since = time.time() - DAGAR * 86400
    events = sorted((e for e in load_archive().values() if e.get("godkand_tid", 0) >= since),
                    key=lambda e: (e.get("godkand_tid", 0) // 3600, e.get("poang", 0)), reverse=True)
    flode = ROOT / "data" / "flode.json"
    base = json.loads(flode.read_text(encoding="utf-8")) if flode.exists() else {"kallrapport": [], "over_sprak": False}
    payload = {"skapad": datetime.now(timezone.utc).isoformat(), "handelser": events,
               "kallrapport": base.get("kallrapport", []), "over_sprak": base.get("over_sprak", False)}
    tmp = PUBLIC / ".ny.html"
    render(payload, tmp, include_unreviewed=False)
    html = tmp.read_text(encoding="utf-8")
    tmp.unlink()
    if not os.environ.get("NN_LANSERAD"):
        html = html.replace('<meta charset="utf-8">', '<meta charset="utf-8"><meta name="robots" content="noindex">', 1)
    html = html.replace("<title>Newsnavigator</title>",
                        '<title>Newsnavigator</title><meta name="description" content="Nyheter från hela världen, '
                        'samlade och granskade. Se hur olika länder och medier berättar om samma händelse.">'
                        '<link rel="icon" href="/newsgator.png">', 1)
    # Skriv bara om innehållet har ändrats (tidsstämpel och källräkning i sidhuvudet räknas inte),
    # så att sajten inte byggs om varje timme i onödan.
    stable = lambda h: re.sub(r'<div class="mono">[^<]*UTC[^<]*(<[^>]+>[^<]*)*?</div>', "", h)
    old = (PUBLIC / "index.html").read_text(encoding="utf-8") if (PUBLIC / "index.html").exists() else ""
    if stable(old) != stable(html):
        (PUBLIC / "index.html").write_text(html, encoding="utf-8")

    png = ROOT / "site" / "newsgator.png"
    if png.exists():
        shutil.copy(png, PUBLIC / "newsgator.png")

    nav = ROOT / "site" / "navigatorn-sv.html"
    if nav.exists() and "UTKAST" not in nav.read_text(encoding="utf-8"):
        (PUBLIC / "navigatorn").mkdir(exist_ok=True)
        shutil.copy(nav, PUBLIC / "navigatorn" / "index.html")
        en = ROOT / "site" / "navigatorn-en.html"
        if en.exists():
            shutil.copy(en, PUBLIC / "navigatorn" / "en.html")

    (PUBLIC / "robots.txt").write_text(
        "User-agent: *\n" + ("Allow: /\n" if os.environ.get("NN_LANSERAD") else "Disallow: /\n"), encoding="utf-8")
    print(f"Publik sajt: {len(events)} granskade notiser -> {PUBLIC}/index.html")


if __name__ == "__main__":
    main()
