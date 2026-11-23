"""Kostnadsskydd för AI-steget: räkna tokens per anrop, spara per dygn, och stoppa nya utkast över taket."""
import json
from types import SimpleNamespace

import kostnad


class FalskKlient:
    def __init__(self):
        self.messages = SimpleNamespace(create=self.create)
        self.anrop = 0

    def create(self, **kw):
        self.anrop += 1
        return SimpleNamespace(usage=SimpleNamespace(input_tokens=1000, output_tokens=200,
                                                     cache_read_input_tokens=0, cache_creation_input_tokens=0), content=[])


def test_klienten_raknar_tokens_utan_att_andra_svaret():
    r = kostnad.Rakning("claude-haiku-5-5")
    k = kostnad.RaknandeKlient(FalskKlient(), r)
    msg = k.messages.create(model="x", max_tokens=1, messages=[])
    assert msg.usage.input_tokens == 1000
    k.messages.create(model="x", max_tokens=1, messages=[])
    assert (r.anrop, r.tokens_in, r.tokens_ut) == (2, 2000, 400)


def test_pris_haiku_5_5_ar_010_in_och_050_ut_per_miljon():
    r = kostnad.Rakning("claude-haiku-5-5")
    r.lagg_till(SimpleNamespace(input_tokens=1_000_000, output_tokens=1_000_000))
    assert abs(r.usd() - 0.60) < 1e-9


def test_okand_modell_prissatts_forsiktigt_och_markeras():
    r = kostnad.Rakning("claude-sonnet-5-5")
    r.lagg_till(SimpleNamespace(input_tokens=1_000_000, output_tokens=0))
    assert abs(r.usd() - 2.0) < 1e-9
    r = kostnad.Rakning("helt-ny-modell")
    r.lagg_till(SimpleNamespace(input_tokens=1_000_000, output_tokens=0))
    assert r.okand_modell and r.usd() >= 2.0


def test_spara_summerar_per_dygn_och_dagens_kostnad_lases_tillbaka(tmp_path):
    sokvag = tmp_path / "kostnad.json"
    for _ in range(2):
        r = kostnad.Rakning("claude-haiku-5-5")
        r.lagg_till(SimpleNamespace(input_tokens=100_000, output_tokens=10_000))
        kostnad.spara(r, sokvag, idag="2026-11-18")
    d = json.loads(sokvag.read_text(encoding="utf-8"))
    assert d["dagar"]["2026-11-18"]["korningar"] == 2 and d["dagar"]["2026-11-18"]["anrop"] == 2
    assert abs(kostnad.dagens_usd(sokvag, idag="2026-11-18") - 2 * (0.01 + 0.005)) < 1e-9
    assert kostnad.dagens_usd(sokvag, idag="2026-11-19") == 0


def test_gamla_dygn_rensas(tmp_path):
    sokvag = tmp_path / "kostnad.json"
    sokvag.write_text(json.dumps({"dagar": {f"2026-01-{d:02d}": {"usd": 1} for d in range(1, 29)}}), encoding="utf-8")
    kostnad.spara(kostnad.Rakning("claude-haiku-5-5"), sokvag, idag="2026-11-18", behall=10)
    assert len(json.loads(sokvag.read_text(encoding="utf-8"))["dagar"]) <= 10


def test_budgeten_stoppar_nya_utkast_over_korningens_tak_och_over_dagstaket():
    b = kostnad.Budget(max_nya=2, dagstak_usd=0.50, redan_idag_usd=0.0)
    assert [b.far_nytt() for _ in range(3)] == [True, True, False]
    b = kostnad.Budget(max_nya=10, dagstak_usd=0.50, redan_idag_usd=0.50)
    assert b.far_nytt() is False, "dagstaket är nått: inga nya utkast"
    b = kostnad.Budget(max_nya=10, dagstak_usd=0, redan_idag_usd=99)
    assert b.far_nytt() is True, "0 betyder ingen gräns"


def test_pipelinen_anvander_raknaren_och_budgeten():
    import inspect
    import pipeline
    main = inspect.getsource(pipeline.main)
    assert "kostnad.RaknandeKlient" in main and "kostnad.spara" in main
    assert "far_nytt" in inspect.getsource(pipeline.main)


def test_effort_laggs_pa_som_standard_och_kan_stangas_av(monkeypatch):
    sett = {}
    inre = FalskKlient()
    orig = inre.messages.create
    inre.messages.create = lambda **kw: (sett.update(kw), orig(**kw))[1]
    k = kostnad.RaknandeKlient(inre, kostnad.Rakning("claude-haiku-5-5"))
    monkeypatch.delenv("NN_AI_EFFORT", raising=False)
    k.messages.create(model="x", max_tokens=1, messages=[])
    assert sett["extra_body"] == {"output_config": {"effort": "low"}}
    sett.clear()
    monkeypatch.setenv("NN_AI_EFFORT", "")
    k.messages.create(model="x", max_tokens=1, messages=[])
    assert "extra_body" not in sett


def test_over_dagstaket_stoppar_ocksa_de_ovriga_ai_stegen():
    assert kostnad.Budget(4, 0.15, 0.15).over() is True
    assert kostnad.Budget(4, 0.15, 0.10).over() is False
    assert kostnad.Budget(4, 0, 99).over() is False, "0 betyder ingen gräns"


def test_pipelinens_valfria_ai_steg_respekterar_dagstaket():
    import inspect
    import pipeline
    main = inspect.getsource(pipeline.main)
    assert "ai_ok" in main
    for steg in ("translate_titles(items, client", "top = clusters[:KONSEKVENS_TOPP]", "kandidater = [(c, d)", "kand = [(c, d)"):
        i = main.index(steg)
        assert "ai_ok" in main[max(0, i - 160): i + 60], steg


def test_utkast_ateranvands_nar_kallorna_nastan_ar_desamma():
    import pipeline
    nu = 1_000_000.0
    hit = {"kallor": ["a", "b", "c", "d", "e"], "skapad": nu - 3600}
    assert pipeline.kan_ateranvanda(hit, ["a", "b", "c", "d", "e", "f"], nu), "en ny källa av sex: samma händelse"
    assert not pipeline.kan_ateranvanda(hit, ["a", "x", "y", "z"], nu), "mest nya källor: nytt utkast"
    assert not pipeline.kan_ateranvanda({**hit, "skapad": nu - 90000}, ["a", "b", "c", "d", "e"], nu), "äldre än ett dygn: nytt utkast"
    assert not pipeline.kan_ateranvanda({"skapad": nu}, ["a"], nu), "äldre cacheposter utan källista: nytt utkast"
    assert not pipeline.kan_ateranvanda(hit, [], nu)


def test_ai_fel_registreras_och_larmas(tmp_path):
    import behover
    class Fel(Exception):
        status_code = 401
    class Dod:
        def __init__(self):
            self.messages = SimpleNamespace(create=self.create)
        def create(self, **kw):
            raise Fel("invalid x-api-key")
    r = kostnad.Rakning("claude-haiku-5-5")
    k = kostnad.RaknandeKlient(Dod(), r)
    try:
        k.messages.create(model="x", max_tokens=1, messages=[])
    except Fel:
        pass
    assert r.fel and "401" in r.fel
    sokvag = tmp_path / "kostnad.json"
    kostnad.spara(r, sokvag, idag="2026-11-23", nu="2026-11-23T01:00:00+00:00")
    d = json.loads(sokvag.read_text(encoding="utf-8"))
    assert d["senaste_fel"]["fel"].startswith("401")
    nu = 1_795_000_000.0
    d["senaste_fel"]["tid"] = behover_iso(nu - 1800)
    rad = behover._ai({"kostnad": d}, nu)
    assert rad and rad[0]["allvarlig"] and "401" in rad[0]["rad"] and "ANTHROPIC_API_KEY" in rad[0]["handling"]
    # ett lyckat varv utan fel tar bort larmet
    ok = kostnad.Rakning("claude-haiku-5-5")
    ok.lagg_till(SimpleNamespace(input_tokens=1, output_tokens=1))
    kostnad.spara(ok, sokvag, idag="2026-11-23")
    assert json.loads(sokvag.read_text(encoding="utf-8")).get("senaste_fel") is None
    assert behover._ai({"kostnad": {}}, nu) == []


def behover_iso(ts):
    from datetime import datetime, timezone
    return datetime.fromtimestamp(ts, timezone.utc).isoformat()
