#!/usr/bin/env python3
"""Redaktionens granskning: lista utkast och godkänn dem för publicering.

  python granska.py lista            visa ogranskade utkast
  python granska.py godkann ID ...   godkänn ett eller flera ID
  python granska.py publicera        bygg site/publicerat.html med bara godkända notiser
"""
import json
import sys
from pathlib import Path

from newsletter import archive
from render import render

ROOT = Path(__file__).parent
FLODE = ROOT / "data" / "flode.json"
GODK = ROOT / "data" / "godkanda.json"


def load():
    return json.loads(FLODE.read_text(encoding="utf-8"))


def approved():
    return set(json.loads(GODK.read_text())) if GODK.exists() else set()


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "lista"
    data, ok = load(), approved()
    if cmd == "lista":
        for ev in data["handelser"]:
            if ev["id"] in ok:
                continue
            d = ev.get("utkast") or {}
            print(f"\n[{ev['id']}] {d.get('rubrik_sv') or ev['reserv_rubrik']}")
            if d.get("sammanfattning_sv"):
                print(f"  {d['sammanfattning_sv']}")
            if d.get("osaker"):
                print(f"  OSÄKER: {d.get('kommentar')}")
            for s in ev["kallor"]:
                print(f"  - {s['namn']}: {s['url']}")
    elif cmd == "godkann":
        ok.update(sys.argv[2:])
        GODK.write_text(json.dumps(sorted(ok), indent=2))
        archive(data["handelser"], ok)
        print(f"Godkända: {len(ok)}")
    elif cmd == "publicera":
        for ev in data["handelser"]:
            ev["granskad"] = ev["id"] in ok
        render(data, ROOT / "site" / "publicerat.html", include_unreviewed=False)
        print(f"Publicerat: {sum(1 for e in data['handelser'] if e['granskad'])} notiser")
    else:
        print(__doc__)


if __name__ == "__main__":
    main()
