#!/usr/bin/env python3
"""Kontrollerar varje källa i feeds.yaml och skriver data/kallstatus.md.

Kör där internet är öppet (din dator med öppen nätverksinställning, eller GitHub Actions).
"""
import time
from datetime import datetime, timezone
from pathlib import Path

import feedparser
import yaml

ROOT = Path(__file__).parent


def main():
    sources = yaml.safe_load((ROOT / "feeds.yaml").read_text(encoding="utf-8"))["sources"]
    rows = ["| Källa | Status | Artiklar | Senaste | Kommentar |", "| --- | --- | --- | --- | --- |"]
    ok = 0
    for s in sources:
        f = feedparser.parse(s["url"], agent="NewsnavigatorBot/0.1")
        n = len(f.entries)
        newest = None
        for e in f.entries:
            ts = e.get("published_parsed") or e.get("updated_parsed")
            if ts and (newest is None or ts > newest):
                newest = ts
        status = "OK" if n else "FEL"
        note = "" if n else str(f.get("bozo_exception", f.get("status", "inga artiklar")))[:80]
        if n and newest and time.time() - time.mktime(newest) > 14 * 86400:
            status, note = "GAMMAL", "inget nytt på 14 dagar"
        ok += status == "OK"
        when = time.strftime("%Y-%m-%d", newest) if newest else ""
        rows.append(f"| {s['namn']} | {status} | {n} | {when} | {note} |")
    out = ROOT / "data" / "kallstatus.md"
    out.parent.mkdir(exist_ok=True)
    out.write_text(f"# Källstatus {datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC\n\n{ok}/{len(sources)} OK\n\n" + "\n".join(rows) + "\n", encoding="utf-8")
    print(f"{ok}/{len(sources)} källor OK, se {out}")


if __name__ == "__main__":
    main()
