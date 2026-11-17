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
