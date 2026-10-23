#!/usr/bin/env python3
"""Kontrollerar varje källa i feeds.yaml (med reservadresser) och skriver data/kallstatus.md.

Kör där internet är öppet (GitHub Actions eller din dator).
"""
import time
from datetime import datetime, timezone
from pathlib import Path

import yaml

from pipeline import fetch_one

ROOT = Path(__file__).parent


def main():
    sources = yaml.safe_load((ROOT / "feeds.yaml").read_text(encoding="utf-8"))["sources"]
    rows = ["| Källa | Region | Status | Artiklar | Senaste | Adress som fungerade / fel |",
            "| --- | --- | --- | --- | --- | --- |"]
    ok = 0
    for s in sources:
        f, used, err = fetch_one(s)
        n = len(f.entries) if f else 0
        newest = None
        for e in (f.entries if f else []):
            ts = e.get("published_parsed") or e.get("updated_parsed")
            if ts and (newest is None or ts > newest):
                newest = ts
        status = "OK" if n else "FEL"
        note = (used if used != s["url"] else "") if n else (err or "")[:80]
        if n and newest and time.time() - time.mktime(newest) > 14 * 86400:
            status, note = "TYST", "inget nytt på 14 dagar"
        ok += status == "OK"
        when = time.strftime("%Y-%m-%d", newest) if newest else ""
        name = s["namn"] + (" (statskontrollerat)" if s.get("statskontrollerad") else "")
        rows.append(f"| {name} | {s.get('region', '')} | {status} | {n} | {when} | {note} |")
    out = ROOT / "data" / "kallstatus.md"
    out.parent.mkdir(exist_ok=True)
    out.write_text(f"# Källstatus {datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC\n\n{ok}/{len(sources)} OK\n\n"
                   + "\n".join(rows) + "\n", encoding="utf-8")
    print(f"{ok}/{len(sources)} källor OK, se {out}")


if __name__ == "__main__":
    main()
