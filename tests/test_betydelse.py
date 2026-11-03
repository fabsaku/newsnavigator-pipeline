"""B2: Analys-raden, vad en händelse betyder för just den här läsaren. Märkt Analys, efter fakta, spårbar till källorna, utan råd och förutsägelser,
kontrollerad av en andra läsning. Sparas som `betydelse` men visas först efter utvärderingen (NN_BETYDELSE=1)."""
import json
from types import SimpleNamespace

import pytest

import betydelse
import sajt
from pipeline import reply_text
from test_berattelser import UTKAST, kluster, item
from test_lansering import NU, historia

SVAR = {"betydelse_sv": "Beslutet om tullar rör svenska exportföretag, eftersom Sverige säljer varor till både USA och Kina.",
        "betydelse_en": "The tariff decision matters for American farmers, since the report says US exports to China fall.",
        "grund": [1, 3]}
KONTROLL_OK = {"problem": [], "ok": True}


class Falsk:
    def __init__(self, svar=SVAR, kontroll=KONTROLL_OK):
        self.anrop, self.svar, self.kontroll = [], svar, kontroll
        self.messages = SimpleNamespace(create=self._create)

    def _create(self, **kw):
        self.anrop.append(kw)
        d = self.kontroll if kw["system"] == betydelse.KONTROLL else self.svar
        return SimpleNamespace(content=[SimpleNamespace(type="text", text=json.dumps(d))], stop_reason="end_turn")


def bygg(c=None, client=None, cache=None, utkast=UTKAST):
    return betydelse.bygg(c or kluster(), utkast, client or Falsk(), "m", reply_text, cache if cache is not None else {})


def test_kravs_ai_utkast_och_minst_tre_kallor():
    assert betydelse.bygg(kluster(), UTKAST, None, "m", reply_text, {}) is None
    assert bygg(utkast={"osaker": True}) is None
    assert bygg(c={"id": "x", "items": kluster()["items"][:2]}) is None


def test_resultatet_har_bada_lasarna_grund_och_kontroll():
    r = bygg()
    assert r["sv"].startswith("Beslutet om tullar") and r["en"].startswith("The tariff decision")
    assert r["grund"] == [1, 3] and r["kontroll"]["ok"] is True and r["ok"] is True
    assert [k["namn"] for k in r["grund_kallor"]] == ["NPR", "SCMP"]


def test_ingen_koppling_till_lasaren_ger_null_per_sprak():
    r = bygg(client=Falsk({"betydelse_sv": None, "betydelse_en": "The decision matters for exporters, since the report says so.", "grund": [1]}))
    assert r["sv"] is None and r["en"]
    assert bygg(client=Falsk({"betydelse_sv": None, "betydelse_en": None, "grund": []})) is None


@pytest.mark.parametrize("text", [
    "Du bör se över dina sparande eftersom räntan stiger.",                       # råd
    "Kronan kommer att försvagas eftersom tullarna införs.",                      # förutsägelse
    "Det här är en katastrof för svenska bönder, eftersom exporten faller.",      # värdeord
    "Beslutet rör Sverige — eftersom exporten faller.",                           # tankstreck
    "Beslutet rör Sverige.  " * 20,                                               # för lång
])
def test_rad_med_rad_forutsagelse_vardeord_tankstreck_eller_langd_underkanns(text):
    assert bygg(client=Falsk({**SVAR, "betydelse_sv": text, "betydelse_en": None})) is None


@pytest.mark.parametrize("text", ["You should sell your dollars since tariffs rise.", "The dollar will weaken since tariffs rise.",
                                  "This is a disaster for farmers, since exports fall."])
def test_engelska_raden_granskas_pa_samma_satt(text):
    assert bygg(client=Falsk({**SVAR, "betydelse_en": text, "betydelse_sv": None})) is None


def test_ogiltigt_kallnummer_eller_tom_grund_underkanns():
    assert bygg(client=Falsk({**SVAR, "grund": [99]})) is None
    assert bygg(client=Falsk({**SVAR, "grund": []})) is None


def test_kontrollen_som_hittar_fel_ger_ok_falskt():
    fel = {"problem": [{"text": "exporten faller", "skal": "saknar stöd"}], "ok": False}
    r = bygg(client=Falsk(kontroll=fel))
    assert r["ok"] is False and r["kontroll"]["problem"]


def test_kontrollen_far_raden_och_kallmaterialet():
    ai = Falsk()
    bygg(client=ai)
    k = next(a for a in ai.anrop if a["system"] == betydelse.KONTROLL)["messages"][0]["content"]
    assert "Beslutet om tullar" in k and "[1] NPR" in k and UTKAST["rubrik_sv"] in k


def test_prompten_forbjuder_rad_forutsagelser_och_nya_fakta():
    s = betydelse.SYSTEM
    for ord_ in ("aldrig råd", "förutsägelse", "tankstreck", "null", "Analys"):
        assert ord_ in s or ord_.capitalize() in s


def test_cache_och_fel():
    cache, ai = {}, Falsk()
    forsta = bygg(client=ai, cache=cache)
    n = len(ai.anrop)
    assert bygg(client=ai, cache=cache) == forsta and len(ai.anrop) == n

    class Trasig(Falsk):
        def _create(self, **kw):
            raise RuntimeError("nät")
    assert bygg(client=Trasig()) is None


# ---------- Visning ----------

def notis(**kw):
    ev = historia(1)["ev"]
    ev["godkand_tid"] = NU - 3600
    ev["granskad"] = True
    ev["perspektiv"]["per_region"] = {r: [{"rubrik": k["rubrik"], "url": k["url"], "kalla": k["namn"], "land": k["land"], "statskontrollerad": False} for k in ev["kallor"] if k["region"] == r] for r in {k["region"] for k in ev["kallor"]}}
    ev["betydelse"] = bygg()
    ev.update(kw)
    return ev


def test_visas_inte_utan_flaggan(monkeypatch):
    monkeypatch.delenv("NN_BETYDELSE", raising=False)
    assert "exportföretag" not in sajt.story_page(sajt.Urls(flat=True), notis(), [], [], "", True)


def test_svenska_traedet_visar_svenska_raden_markerad_analys(monkeypatch):
    monkeypatch.setenv("NN_BETYDELSE", "1")
    sida = sajt.story_page(sajt.Urls(flat=False, lang="sv"), notis(), [], [], "", True)
    assert "Beslutet om tullar rör svenska exportföretag" in sida and "Analys" in sida and "American farmers" not in sida
    assert "med hjälp av AI" in sida


def test_engelska_traedet_visar_engelska_raden_markerad_analysis(monkeypatch):
    monkeypatch.setenv("NN_BETYDELSE", "1")
    sida = sajt.story_page(sajt.Urls(flat=False, lang="en"), notis(), [], [], "", True)
    assert "The tariff decision matters for American farmers" in sida and "Analysis" in sida and "exportföretag" not in sida


def test_raden_efter_fakta_inte_i_rubrik_eller_sammanfattning(monkeypatch):
    monkeypatch.setenv("NN_BETYDELSE", "1")
    sida = sajt.story_page(sajt.Urls(flat=False, lang="sv"), notis(), [], [], "", True)
    assert sida.index("Beslutet om tullar rör") > sida.index("<h3 class=\"section-h\">Källor")
    assert sida.index("<h2>") < sida.index("Beslutet om tullar rör")


def test_visas_inte_om_kontrollen_underkant_eller_raden_saknas(monkeypatch):
    monkeypatch.setenv("NN_BETYDELSE", "1")
    ev = notis()
    ev["betydelse"]["ok"] = False
    assert "exportföretag" not in sajt.story_page(sajt.Urls(flat=False, lang="sv"), ev, [], [], "", True)
    ev = notis(betydelse={"sv": None, "en": "x y", "grund": [1], "kontroll": KONTROLL_OK, "ok": True, "grund_kallor": []})
    assert "Analys" not in sajt.story_page(sajt.Urls(flat=False, lang="sv"), ev, [], [], "", True)
