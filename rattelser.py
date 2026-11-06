"""Rättelser (princip 8): allt som rättats eller tagits bort efter publicering, öppet i data/rattelser.json.

En borttagen notis loggas av sig själv. En rättelse läggs in för hand i filen:
  {"id": "...", "tid": 1793900000, "typ": "rattad", "rubrik_sv": "...", "rubrik_en": "...", "vad_sv": "...", "vad_en": "..."}
"""
import json
import time
from pathlib import Path

FIL = Path(__file__).parent / "data" / "rattelser.json"


def load(path=None):
    try:
        return json.loads(Path(path or FIL).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []


def borttagen(ev, path=None, nu=None):
    """Loggar att en publicerad notis togs bort. Rubriken står kvar så att det syns vad som försvann."""
    path = Path(path or FIL)
    d = ev.get("utkast") or {}
    poster = load(path)
    poster.append({"id": ev["id"], "tid": nu or time.time(), "typ": "borttagen",
                   "rubrik_sv": d.get("rubrik_sv") or ev.get("reserv_rubrik") or "",
                   "rubrik_en": d.get("rubrik_en") or ev.get("reserv_rubrik") or ""})
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(poster, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


def borttagna_id(path=None):
    return {p["id"] for p in load(path) if p.get("typ") == "borttagen"}


def for_notis(eid, path=None):
    return [p for p in load(path) if p["id"] == eid and p.get("typ") == "rattad"]
