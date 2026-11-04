"""Jämförelsen av alternativ A (ingress från alla källor) och B (bara rubrik för källor som stänger ute Claude)."""
import pytest

import jamfor_alternativ
import pipeline
from test_sidlasare import SIDA, kalla as sidkalla


def test_env_gor_utvalda_kallor_till_bara_rubrik(monkeypatch):
    """NN_BARA_RUBRIK används för jämförelsen: de angivna källornas ingress skickas inte till modellen."""
    s = {**sidkalla(), "hamtning": None, "url": "file:tests/a.xml", "id": "test-a", "namn": "A", "sprak": "en", "typ": "media"}
    monkeypatch.delenv("NN_BARA_RUBRIK", raising=False)
    items, _ = pipeline.fetch([s], 0)
    assert any(i["description"] for i in items)
    monkeypatch.setenv("NN_BARA_RUBRIK", "annan,test-a")
    items, _ = pipeline.fetch([s], 0)
    assert items and all(i["description"] == "" for i in items)


def ev(eid, kallor, osaker=False, ok=True, sv="Ett par meningar om vad som hänt.", problem=(), narrativ=None, betydelse=None, regioner=("europa", "usa")):
    ks = [{"namn": n.upper(), "typ": "media", "region": r, "statskontrollerad": False, "rubrik": "h", "url": f"https://x/{n}"} for n, r in zip(kallor, regioner * 5)]
    return {"id": eid, "kallor": ks, "antal_kallor": len(ks), "amnen_sektion": ["varlden"],
            "utkast": {"rubrik_sv": "Rubrik", "sammanfattning_sv": sv, "rubrik_en": "Headline", "sammanfattning_en": "Text.", "osaker": osaker},
            "kallkontroll": {"ok": ok, "antal": 3, "problem": list(problem)},
            "perspektiv": {"regioner": list(regioner), "per_region": {}, "blind_flack": None, "usa_blind": None},
            "narrativ": narrativ, "betydelse": betydelse}


def test_jamforelsen_raknar_bara_handelser_som_berors():
    a = [ev("1", ["svt", "bbc", "npr"]), ev("2", ["bbc", "npr", "afp"])]
    b = [ev("1", ["svt", "bbc", "npr"], osaker=True, ok=False, problem=["saknar stöd: x"]), ev("2", ["bbc", "npr", "afp"])]
    r = jamfor_alternativ.jamfor(a, b, {"SVT"})
    assert r["totalt"] == {"A": 2, "B": 2, "bada": 2}
    assert r["berorda"]["antal"] == 1
    assert r["berorda"]["A"]["osakra"] == 0 and r["berorda"]["B"]["osakra"] == 1
    assert r["berorda"]["A"]["kallkontroll_ok"] == 1 and r["berorda"]["B"]["kallkontroll_ok"] == 0
    assert r["berorda"]["A"]["klarar_grindarna"] == 1 and r["berorda"]["B"]["klarar_grindarna"] == 0
    assert r["oberorda"]["A"]["osakra"] == 0 and r["oberorda"]["B"]["osakra"] == 0


def test_jamforelsen_ser_vilka_handelser_som_forsamras_och_forbattras():
    a = [ev("1", ["svt", "bbc", "npr"]), ev("2", ["dr", "bbc", "npr"], osaker=True)]
    b = [ev("1", ["svt", "bbc", "npr"], osaker=True), ev("2", ["dr", "bbc", "npr"])]
    r = jamfor_alternativ.jamfor(a, b, {"SVT", "DR"})
    assert r["forsamrade"] == ["1"] and r["forbattrade"] == ["2"]


def test_handelser_som_bara_finns_i_en_korning_redovisas_men_jamfors_inte():
    a = [ev("1", ["svt", "bbc", "npr"]), ev("9", ["svt", "bbc", "npr"])]
    b = [ev("1", ["svt", "bbc", "npr"]), ev("8", ["svt", "bbc", "npr"])]
    r = jamfor_alternativ.jamfor(a, b, {"SVT"})
    assert r["totalt"]["bada"] == 1 and r["bara_i"] == {"A": ["9"], "B": ["8"]}


def test_summeringens_langd_och_oenighet_och_berattelser_och_betydelse():
    nar = {"ok": True, "berattelser": [{}, {}]}
    bet = {"ok": True, "sv": "x", "en": None}
    a = [{**ev("1", ["svt", "bbc", "npr"], sv="ett två tre fyra fem"), "narrativ": nar, "betydelse": bet}]
    b = [{**ev("1", ["svt", "bbc", "npr"], sv="ett två"), "narrativ": None, "betydelse": None}]
    r = jamfor_alternativ.jamfor(a, b, {"SVT"})
    assert r["berorda"]["A"]["medelord"] == 5 and r["berorda"]["B"]["medelord"] == 2
    assert r["berorda"]["A"]["med_berattelser"] == 1 and r["berorda"]["B"]["med_berattelser"] == 0
    assert r["berorda"]["A"]["med_betydelse"] == 1 and r["berorda"]["B"]["med_betydelse"] == 0


def test_utskriften_ar_kort_och_sager_slutsatsen():
    a = [ev(str(i), ["svt", "bbc", "npr"]) for i in range(10)]
    b = [ev(str(i), ["svt", "bbc", "npr"], osaker=(i < 4), ok=(i >= 4)) for i in range(10)]
    ut = jamfor_alternativ.text(jamfor_alternativ.jamfor(a, b, {"SVT"}))
    assert "10 av 10" in ut and "klarar grindarna" in ut.lower() and len(ut.splitlines()) < 30


def test_workflowen_kor_a_och_b_och_skriver_inget_till_repot():
    from pathlib import Path
    import yaml
    text = (Path(__file__).parent.parent / ".github" / "workflows" / "kallprov.yml").read_text(encoding="utf-8")
    y = yaml.safe_load(text)
    assert y["permissions"] == {"contents": "read"} and "schedule" not in y[True]
    assert "git push" not in text and "git commit" not in text
    assert "jamfor" in y[True]["workflow_dispatch"]["inputs"] and set(y["jobs"]) == {"prova", "jamfor"}
    assert "--out /tmp/A" in text and "--out /tmp/B" in text and "NN_BARA_RUBRIK" in text and "ANTHROPIC_API_KEY" in text
    assert y["jobs"]["prova"]["if"] != y["jobs"]["jamfor"]["if"]
