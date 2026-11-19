"""24/7: sajten är öppen för sökmotorer, GitHubs reservschema täcker alla timmar, tidsgränsen har marginal och sajten publicerar en statusfil."""
import json
from pathlib import Path

import yaml

import publish

ROOT = Path(__file__).parent.parent
PIPE = yaml.safe_load((ROOT / ".github" / "workflows" / "pipeline.yml").read_text(encoding="utf-8"))


def test_reservschemat_startar_varje_timme_dygnet_runt():
    crons = [s["cron"] for s in PIPE[True]["schedule"]]
    assert crons == ["17 * * * *"]


def test_tidsgransen_har_marginal_mot_en_normal_korning():
    assert PIPE["jobs"]["run"]["timeout-minutes"] >= 25, "en normal körning tar 6 till 12 minuter"


def test_sajten_byggs_oppen_for_sokmotorer():
    env = PIPE["jobs"]["run"].get("env", {}) or {}
    assert str(env.get("NN_LANSERAD")) == "1"


def test_statusfilen_visar_nar_sajten_byggdes_och_hur_manga_handelser(tmp_path, monkeypatch):
    monkeypatch.setattr(publish, "PUBLIC", tmp_path)
    publish.skriv_status(tmp_path, {"skapad": "2026-11-19T10:00:00+00:00", "handelser": [1, 2, 3]}, 7)
    d = json.loads((tmp_path / "status.json").read_text(encoding="utf-8"))
    assert d["flode_skapat"] == "2026-11-19T10:00:00+00:00" and d["handelser"] == 3 and d["notiser"] == 7 and d["byggd"]
