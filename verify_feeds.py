#!/usr/bin/env python3
"""Kontrollerar varje källa i feeds.yaml (med reservadresser) och skriver data/kallstatus.json.

Kör där internet är öppet (GitHub Actions eller din dator).
"""
import argparse
import calendar
import json
import time
from datetime import datetime, timezone
from pathlib import Path

import yaml

from pipeline import fetch_one

ROOT = Path(__file__).parent
TYST_DAGAR = 14


def _iso(epoch):
    return datetime.fromtimestamp(epoch, timezone.utc).isoformat() if epoch is not None else None


def kallstatus(sources, nu=None):
    """Status per källa: ok, fel (flödet gick inte att läsa) eller tyst (inget nytt på TYST_DAGAR dagar)."""
    nu = time.time() if nu is None else nu
    rows = []
    for s in sources:
        f, used, err = fetch_one(s)
        entries = f.entries if f else []
        newest = None
        for e in entries:
            ts = e.get("published_parsed") or e.get("updated_parsed")
            if ts:
                newest = max(newest or 0, calendar.timegm(ts))
            if e.get("senast_sedd"):         # sidkällor: när länken sågs (sidlasare.py), annars är en nyss tillagd källa "tyst sedan 1970"
                newest = max(newest or 0, e["senast_sedd"])
        if not entries:
            status = "fel"
        elif newest is not None and nu - newest > TYST_DAGAR * 86400:
            status = "tyst"
        else:
            status = "ok"
        rows.append({
            "id": s["id"],
            "namn": s["namn"],
            "region": s.get("region", ""),
            "statskontrollerad": bool(s.get("statskontrollerad")),
            "status": status,
            "artiklar": len(entries),
            "senaste": _iso(newest),
            "url": used if entries else None,
            "fel": None if entries else (err or "inga artiklar")[:160],
        })
    return {"skapad": _iso(nu), "ok": sum(1 for r in rows if r["status"] == "ok"), "totalt": len(rows), "kallor": rows}


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--feeds", default=str(ROOT / "feeds.yaml"))
    ap.add_argument("--out", default=str(ROOT / "data"))
    args = ap.parse_args(argv)
    sources = yaml.safe_load(Path(args.feeds).read_text(encoding="utf-8"))["sources"]
    status = kallstatus(sources)
    out = Path(args.out) / "kallstatus.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(status, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"{status['ok']}/{status['totalt']} källor OK, se {out}")


if __name__ == "__main__":
    main()
