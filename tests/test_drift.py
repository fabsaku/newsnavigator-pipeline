"""Fas 0: data/drift.json skrivs i slutet av varje körning, av alla tre workflows."""
import json
from pathlib import Path

import pytest
import yaml

import drift

WORKFLOWS = Path(__file__).parent.parent / ".github" / "workflows"
MILJO = {"GITHUB_RUN_ID": "123", "GITHUB_SERVER_URL": "https://github.com",
         "GITHUB_REPOSITORY": "fabsaku/newsnavigator-pipeline"}


def registrera(fil, workflow="pipeline", status="success", start=1000.0, slut=1090.0, miljo=MILJO, **kw):
    return drift.registrera(workflow, status, start=start, slut=slut, fil=fil, miljo=miljo, **kw)


def test_forsta_korningen_skapar_filen(tmp_path):
    fil = tmp_path / "drift.json"
    registrera(fil)
    data = json.loads(fil.read_text(encoding="utf-8"))
    senaste = data["senaste"]["pipeline"]
    assert senaste["status"] == "ok"
    assert senaste["sekunder"] == 90
    assert senaste["start"].startswith("1970-01-01T00:16:40")
    assert senaste["url"] == "https://github.com/fabsaku/newsnavigator-pipeline/actions/runs/123"
    assert data["historik"] == [senaste]
    assert data["uppdaterad"]


@pytest.mark.parametrize("github, svensk", [("success", "ok"), ("failure", "fel"), ("cancelled", "avbruten")])
def test_status_fran_github(tmp_path, github, svensk):
    assert registrera(tmp_path / "drift.json", status=github)["status"] == svensk


def test_andra_workflows_behalls(tmp_path):
    fil = tmp_path / "drift.json"
    registrera(fil, "pipeline")
    registrera(fil, "instagram", "failure", start=2000.0, slut=2010.0)
    data = json.loads(fil.read_text(encoding="utf-8"))
    assert data["senaste"]["pipeline"]["status"] == "ok"
    assert data["senaste"]["instagram"]["status"] == "fel"
    assert [k["workflow"] for k in data["historik"]] == ["instagram", "pipeline"]


def test_historiken_haller_de_tjugo_senaste(tmp_path):
    fil = tmp_path / "drift.json"
    for n in range(25):
        registrera(fil, start=1000.0 + n, slut=1010.0 + n, miljo={**MILJO, "GITHUB_RUN_ID": str(n)})
    historik = json.loads(fil.read_text(encoding="utf-8"))["historik"]
    assert len(historik) == 20
    assert historik[0]["sekunder"] == 10 and historik[0]["start"] > historik[-1]["start"]


def test_samma_korning_star_en_gang(tmp_path):
    """Felar ett steg efter commiten skrivs körningen igen, nu som fel; historiken ska bara ha den senaste."""
    fil = tmp_path / "drift.json"
    registrera(fil, "pipeline", "success")
    registrera(fil, "pipeline", "failure")
    historik = json.loads(fil.read_text(encoding="utf-8"))["historik"]
    assert [k["status"] for k in historik] == ["fel"]


def test_pipelinen_sammanfattar_flodet(tmp_path):
    flode = tmp_path / "flode.json"
    flode.write_text(json.dumps({"handelser": [{}, {}, {}],
                                 "kallrapport": [{"ok": True}, {"ok": True}, {"ok": False}]}), encoding="utf-8")
    senaste = registrera(tmp_path / "drift.json", flode=flode)
    assert (senaste["handelser"], senaste["kallor_ok"], senaste["kallor_totalt"]) == (3, 2, 3)


def test_kommandoraden(tmp_path, monkeypatch):
    for k, v in {**MILJO, "NN_START": "1000"}.items():
        monkeypatch.setenv(k, v)
    fil = tmp_path / "drift.json"
    drift.main(["granskning", "success", "--fil", str(fil)])
    senaste = json.loads(fil.read_text(encoding="utf-8"))["senaste"]["granskning"]
    assert senaste["status"] == "ok" and senaste["start"].startswith("1970-01-01T00:16:40")


@pytest.mark.parametrize("fil, namn", [("pipeline.yml", "pipeline"), ("granskning.yml", "granskning"),
                                       ("instagram.yml", "instagram")])
def test_varje_workflow_skriver_drift(fil, namn):
    """Lyckad körning: drift.json följer med i workflowens vanliga commit.
    Misslyckad eller avbruten körning: ett eget steg skriver och pushar drift.json ändå."""
    steg = yaml.safe_load((WORKFLOWS / fil).read_text(encoding="utf-8"))["jobs"]
    steg = next(iter(steg.values()))["steps"]
    korningar = [n for n, s in enumerate(steg) if f"drift.py {namn}" in s.get("run", "")]
    commit = next(n for n, s in enumerate(steg) if "git commit" in s.get("run", "") and "drift.py" not in s.get("run", ""))

    lyckad = [n for n in korningar if "failure()" not in str(steg[n].get("if", ""))]
    assert lyckad and lyckad[0] < commit, "drift.py ska köras före den vanliga commiten"
    git_add = next(r for r in steg[commit]["run"].splitlines() if "git add" in r)
    assert " data " in f"{git_add} " or "data/drift.json" in git_add

    misslyckad = [steg[n] for n in korningar if "failure()" in str(steg[n].get("if", ""))]
    assert misslyckad, "ett steg med if: failure() || cancelled() ska skriva drift.json när körningen fallerar"
    assert "cancelled()" in misslyckad[0]["if"]
    assert "data/drift.json" in misslyckad[0]["run"] and "git push" in misslyckad[0]["run"]

    assert any("NN_START" in s.get("run", "") for s in steg[:2]), "starttiden sparas först i jobbet"


@pytest.mark.parametrize("fil", ["pipeline.yml", "granskning.yml", "instagram.yml", "angra.yml"])
def test_senaste_korningen_vinner_vid_konflikt(fil):
    """Två körningar nära varandra (GitHubs reservschema och klockan) gav konflikter i data/ och public/
    29 och 30 oktober. Allt som sparas byggs om av varje körning, och ärendet är sanningen för bockarna,
    så den senaste körningen får vinna."""
    text = (WORKFLOWS / fil).read_text(encoding="utf-8")
    pulls = [rad for rad in text.splitlines() if "git pull --rebase" in rad]
    assert pulls and all("-X theirs" in rad for rad in pulls), pulls
    if "failure()" in text:
        assert "git rebase --abort" in text
