#!/usr/bin/env python3
"""Driftstatus: varje workflow skriver hur körningen gick till data/drift.json, som panelen och morgonrapporten läser.

  python drift.py pipeline success      (andra argumentet är ${{ job.status }}: success, failure eller cancelled)

Starttiden läses ur NN_START (sekunder sedan 1970), som workflowen sätter i sitt första steg.
Länken till loggen byggs av GITHUB_SERVER_URL, GITHUB_REPOSITORY och GITHUB_RUN_ID.
"""
import argparse
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).parent
DRIFT = ROOT / "data" / "drift.json"
FLODE = ROOT / "data" / "flode.json"
HISTORIK = 20
STATUS = {"success": "ok", "failure": "fel", "cancelled": "avbruten"}


def _iso(epoch):
    return datetime.fromtimestamp(epoch, timezone.utc).isoformat() if epoch is not None else None


def _flode(path):
    """Pipelinens sammanfattning: antal händelser och hur många källor som gick att läsa."""
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    report = data.get("kallrapport") or []
    return {"handelser": len(data.get("handelser") or []),
            "kallor_ok": sum(1 for r in report if r.get("ok")), "kallor_totalt": len(report)}


def registrera(workflow, status, *, start=None, slut=None, fil=DRIFT, miljo=None, flode=None):
    """Lägger till en körning i drift.json och returnerar den."""
    miljo = os.environ if miljo is None else miljo
    slut = time.time() if slut is None else slut
    run_id = miljo.get("GITHUB_RUN_ID")
    korning = {
        "workflow": workflow,
        "status": STATUS.get(status, "fel"),
        "start": _iso(start),
        "slut": _iso(slut),
        "sekunder": round(slut - start) if start is not None else None,
        "korning": run_id,
        "url": (f"{miljo.get('GITHUB_SERVER_URL', 'https://github.com')}/{miljo['GITHUB_REPOSITORY']}/actions/runs/{run_id}"
                if run_id and miljo.get("GITHUB_REPOSITORY") else None),
    }
    if flode is not None:
        korning.update(_flode(flode))

    fil = Path(fil)
    try:
        data = json.loads(fil.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        data = {}
    data["uppdaterad"] = korning["slut"]
    data["senaste"] = {**data.get("senaste", {}), workflow: korning}
    tidigare = [k for k in data.get("historik", [])
                if not (run_id and k.get("korning") == run_id and k.get("workflow") == workflow)]
    data["historik"] = [korning, *tidigare][:HISTORIK]
    fil.parent.mkdir(parents=True, exist_ok=True)
    fil.write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return korning


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("workflow", choices=["pipeline", "granskning", "instagram"])
    ap.add_argument("status", help="job.status från GitHub Actions: success, failure eller cancelled")
    ap.add_argument("--fil", default=str(DRIFT))
    args = ap.parse_args(argv)
    start = os.environ.get("NN_START")
    korning = registrera(args.workflow, args.status, start=float(start) if start else None, fil=args.fil,
                         flode=FLODE if args.workflow == "pipeline" else None)
    print(f"Drift: {korning['workflow']} {korning['status']}, {korning['sekunder']} s")


if __name__ == "__main__":
    main()
