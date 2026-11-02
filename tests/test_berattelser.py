"""B1: berättelserna. Två till fyra namngivna berättelser per händelse med minst fyra källor, bara tillskrivet, bara vad källorna
lyfter fram, och med en egen källkontroll. Sparas på händelsen (`narrativ`) men visas först efter utvärderingen (B3)."""
import json
from types import SimpleNamespace

import pytest

import berattelser
import kallkontroll
import sajt
from pipeline import reply_text
from test_lansering import NU, historia


def item(n, namn, region, titel, lean=None, stat=False, typ="media", land="XX"):
    return {"source_id": f"s{n}", "source_name": namn, "country": land, "region": region, "state_controlled": stat, "usa_lean": lean,
            "source_type": typ, "title": titel, "description": f"Ingress {n}", "published": None, "url": f"https://x/{n}", "paywall": False, "owner": "privat"}


def kluster(extra=()):
    return {"id": "abc123", "items": [
        item(1, "NPR", "usa", "Tariffs hit US farmers", lean="lutar_vanster"),
        item(2, "Fox News", "usa", "Tariffs punish China", lean="hoger"),
        item(3, "SCMP", "asien", "Tariffs cloud trade outlook"),
        item(4, "BBC", "europa", "Tariffs raise EU worries"),
        *extra]}


UTKAST = {"rubrik_sv": "Nya tullar införs", "sammanfattning_sv": "Text.", "rubrik_en": "New tariffs imposed", "sammanfattning_en": "Text.", "osaker": False}

BERATTELSER = {"berattelser": [
    {"namn_sv": "Kostnaden för bönder", "namn_en": "The cost to farmers", "lyfter_sv": "NPR lyfter fram konsekvenserna för amerikanska bönder.",
     "lyfter_en": "NPR highlights the consequences for American farmers.", "kallor": [1]},
    {"namn_sv": "Trycket på Kina", "namn_en": "Pressure on China", "lyfter_sv": "Fox News lyfter fram trycket på Kina.",
     "lyfter_en": "Fox News highlights the pressure on China.", "kallor": [2]},
    {"namn_sv": "Oro för handeln", "namn_en": "Worry for trade", "lyfter_sv": "SCMP och BBC lyfter fram oron för handeln.",
     "lyfter_en": "SCMP and BBC highlight the worry for trade.", "kallor": [3, 4]}]}
KONTROLL_OK = {"pastaenden": [{"text": "x", "stod": [1], "problem": None}], "ok": True, "sammanfattning": None}


class Falsk:
    """Falsk AI: svarar med berättelser till berättelsesteget och med kontrollen till källkontrollen."""

    def __init__(self, berattelser_svar=BERATTELSER, kontroll=KONTROLL_OK):
        self.anrop = []
        self.berattelser_svar, self.kontroll = berattelser_svar, kontroll
        self.messages = SimpleNamespace(create=self._create)

    def _create(self, **kw):
        self.anrop.append(kw)
        svar = self.kontroll if kw["system"] == kallkontroll.SYSTEM else self.berattelser_svar
        return SimpleNamespace(content=[SimpleNamespace(type="text", text=json.dumps(svar))], stop_reason="end_turn")


def bygg(c=None, client=None, cache=None, utkast=UTKAST):
    return berattelser.bygg(c or kluster(), utkast, client or Falsk(), "m", reply_text, cache if cache is not None else {})


# ---------- Vem som får berättelser ----------

def test_kravs_minst_fyra_oberoende_kallor_i_minst_tva_regioner():
    assert berattelser.kvalificerad(kluster())
    assert not berattelser.kvalificerad({"items": kluster()["items"][:3]})
    bara_en_region = {"items": [item(n, f"K{n}", "usa", "t") for n in range(5)]}
    assert not berattelser.kvalificerad(bara_en_region)
    kurerat = {"items": kluster()["items"][:3] + [item(9, "Techmeme", "usa", "t", typ="kuraterat")]}
    assert not berattelser.kvalificerad(kurerat)


def test_ingen_ai_inga_berattelser():
    assert berattelser.bygg(kluster(), UTKAST, None, "m", reply_text, {}) is None
    assert bygg(c={"id": "x", "items": kluster()["items"][:2]}) is None


def test_inget_utkast_inga_berattelser():
    assert bygg(utkast={"osaker": True}) is None


# ---------- Resultatet ----------

def test_berattelserna_far_kallornas_region_och_allsides_sida_av_koden_inte_av_ai():
    n = bygg()
    assert [b["namn_sv"] for b in n["berattelser"]] == ["Kostnaden för bönder", "Trycket på Kina", "Oro för handeln"]
    forsta, andra, tredje = n["berattelser"]
    assert forsta["kallor"] == [{"namn": "NPR", "region": "usa", "lutning": "lutar_vanster", "statskontrollerad": False, "url": "https://x/1"}]
    assert forsta["regioner"] == ["usa"] and forsta["usa_sidor"] == ["bla"]
    assert andra["usa_sidor"] == ["rod"]
    assert tredje["regioner"] == ["asien", "europa"] and tredje["usa_sidor"] == []
    assert n["kontroll"]["ok"] is True and n["ok"] is True


def test_statskontrollerad_kalla_markeras():
    c = kluster([item(5, "CGTN", "asien", "Tariffs unfair", stat=True)])
    svar = {"berattelser": [*BERATTELSER["berattelser"][:2], {**BERATTELSER["berattelser"][2], "kallor": [3, 5]}]}
    n = bygg(c=c, client=Falsk(svar))
    assert any(k["statskontrollerad"] for k in n["berattelser"][2]["kallor"])


def test_for_fa_eller_for_manga_berattelser_blir_inga():
    for antal in (0, 1, 5):
        svar = {"berattelser": [BERATTELSER["berattelser"][i % 3] for i in range(antal)]}
        assert bygg(client=Falsk(svar)) is None, antal


def test_ogiltigt_kallnummer_underkanns():
    svar = {"berattelser": [{**BERATTELSER["berattelser"][0], "kallor": [99]}, *BERATTELSER["berattelser"][1:]]}
    n = bygg(client=Falsk(svar))
    assert n is None


@pytest.mark.parametrize("text", ["NPR nämner inte kostnaden.", "Fox News utelämnar bönderna.", "NPR ignorerar Kina.", "BBC tiger om priset.",
                                  "Det här är sanningen om tullarna.", "NPR lyfter fram — kostnaden."])
def test_det_en_kalla_utelamnar_och_tankstreck_underkanns(text):
    fel = {**BERATTELSER["berattelser"][0], "lyfter_sv": text}
    svar = {"berattelser": [fel, *BERATTELSER["berattelser"][1:]]}
    assert bygg(client=Falsk(svar)) is None


def test_namn_med_vardeord_eller_for_langt_underkanns():
    lang = {**BERATTELSER["berattelser"][0], "namn_sv": "Ett mycket långt namn som aldrig kan vara ett namn på en berättelse"}
    assert bygg(client=Falsk({"berattelser": [lang, *BERATTELSER["berattelser"][1:]]})) is None


def test_kallkontrollen_som_hittar_fel_ger_ok_falskt_men_sparar_underlaget():
    fel = {"pastaenden": [{"text": "NPR lyfter bönder", "stod": [], "problem": "fel tillskrivning"}], "ok": False, "sammanfattning": "NPR säger inte det"}
    n = bygg(client=Falsk(kontroll=fel))
    assert n["ok"] is False and n["kontroll"]["problem"]


def test_kallkontrollen_far_berattelserna_som_perspektiv_och_kallmaterialet():
    ai = Falsk()
    bygg(client=ai)
    kontroll = next(a for a in ai.anrop if a["system"] == kallkontroll.SYSTEM)["messages"][0]["content"]
    assert "Kostnaden för bönder" in kontroll and "NPR lyfter fram" in kontroll and "[1] NPR" in kontroll


def test_cachen_ger_samma_svar_utan_nya_anrop():
    cache = {}
    ai = Falsk()
    forsta = bygg(client=ai, cache=cache)
    antal = len(ai.anrop)
    andra = bygg(client=ai, cache=cache)
    assert len(ai.anrop) == antal and andra == forsta and cache["berattelser"]


def test_andrade_kallor_ger_nytt_anrop():
    cache = {}
    ai = Falsk()
    bygg(client=ai, cache=cache)
    antal = len(ai.anrop)
    bygg(c=kluster([item(5, "DW", "europa", "Tariffs split EU")]), client=ai, cache=cache)
    assert len(ai.anrop) > antal


def test_misslyckat_anrop_ger_none_inte_krasch():
    class Trasig(Falsk):
        def _create(self, **kw):
            raise RuntimeError("nät")
    assert bygg(client=Trasig()) is None


def test_prompten_foljer_promptregel_11():
    s = berattelser.SYSTEM
    assert "aldrig vad" in s and "utelämnar" in s and "tankstreck" in s.lower() and "AllSides" in s


# ---------- Visning: bakom flaggan ----------

def notis_med_narrativ():
    ev = historia(1)["ev"]
    ev["godkand_tid"] = NU - 3600
    ev["granskad"] = True
    ev["perspektiv"]["per_region"] = {r: [{"rubrik": k["rubrik"], "url": k["url"], "kalla": k["namn"], "land": k["land"], "statskontrollerad": False} for k in ev["kallor"] if k["region"] == r] for r in {k["region"] for k in ev["kallor"]}}
    ev["narrativ"] = bygg()
    return ev


def test_visas_inte_utan_flaggan(monkeypatch):
    monkeypatch.delenv("NN_BERATTELSER", raising=False)
    sida = sajt.story_page(sajt.Urls(flat=True), notis_med_narrativ(), [], [], "", True)
    assert "Kostnaden för bönder" not in sida and "The cost to farmers" not in sida


def test_visas_med_flaggan_och_bara_om_kontrollen_ar_ok(monkeypatch):
    monkeypatch.setenv("NN_BERATTELSER", "1")
    ev = notis_med_narrativ()
    sida = sajt.story_page(sajt.Urls(flat=True), ev, [], [], "", True)
    assert "Kostnaden för bönder" in sida and "NPR lyfter fram konsekvenserna" in sida and "The cost to farmers" in sida
    ev["narrativ"]["ok"] = False
    assert "Kostnaden för bönder" not in sajt.story_page(sajt.Urls(flat=True), ev, [], [], "", True)


def test_engelska_tradet_visar_bara_engelska(monkeypatch):
    monkeypatch.setenv("NN_BERATTELSER", "1")
    sida = sajt.story_page(sajt.Urls(flat=False, lang="en"), notis_med_narrativ(), [], [], "", True)
    assert "The cost to farmers" in sida and "Kostnaden för bönder" not in sida and "NPR highlights" in sida
