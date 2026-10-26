"""Fas 0: källstatus som JSON (ersätter data/kallstatus.md), så att panelen kan läsa den."""
import json
from datetime import datetime, timezone
from pathlib import Path

import yaml

import verify_feeds

FEEDS = Path(__file__).parent / "feeds-test.yaml"


def kallor():
    return yaml.safe_load(FEEDS.read_text(encoding="utf-8"))["sources"]


def epoch(text):
    return datetime.fromisoformat(text).replace(tzinfo=timezone.utc).timestamp()


def test_status_per_kalla():
    status = verify_feeds.kallstatus(kallor(), nu=epoch("2026-10-26T06:00:00"))
    per_id = {k["id"]: k for k in status["kallor"]}
    assert set(per_id) == {s["id"] for s in kallor()}
    assert status["totalt"] == len(per_id)
    assert status["ok"] == sum(1 for k in per_id.values() if k["status"] == "ok")

    a = per_id["test-a"]
    assert (a["status"], a["artiklar"], a["fel"]) == ("ok", 3, None)
    assert a["senaste"].startswith("2026-10-23T")
    assert a["namn"] == "Testkälla A" and a["region"] == "usa"

    # Reservadressen används när huvudadressen inte fungerar
    assert per_id["test-b"]["status"] == "ok"
    assert per_id["test-b"]["url"] == "file:tests/b.xml"

    trasig = per_id["test-trasig"]
    assert trasig["status"] == "fel" and trasig["artiklar"] == 0 and trasig["fel"]
    assert trasig["senaste"] is None

    assert per_id["test-stat"]["statskontrollerad"] is True


def test_tyst_kalla():
    status = verify_feeds.kallstatus(kallor(), nu=epoch("2026-12-01T06:00:00"))
    a = next(k for k in status["kallor"] if k["id"] == "test-a")
    assert a["status"] == "tyst"


def test_skriver_json_och_inte_markdown(tmp_path):
    verify_feeds.main(["--feeds", str(FEEDS), "--out", str(tmp_path)])
    data = json.loads((tmp_path / "kallstatus.json").read_text(encoding="utf-8"))
    assert data["skapad"] and len(data["kallor"]) == len(kallor())
    assert not (tmp_path / "kallstatus.md").exists()
