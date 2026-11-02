"""A1: två utgåvor. Svenska läsaren och engelska läsaren får inte samma urval.

Svenska utgåvan: svenska nyheter, och globala händelser som berör Sverige och Europa, särskilt de som saknas i svenska medier.
Engelska utgåvan: globala händelser. Svenskt och nordiskt bara när det påverkar läsaren. Aldrig lokalt svenskt.
"""
import json
from pathlib import Path

import pytest

import autopilot
import utgava

FLODE = Path(__file__).parent.parent / "data" / "flode.json"


def kalla(namn, region="europa", typ="media", stat=False):
    return {"namn": namn, "rubrik": "x", "url": f"https://x/{namn}", "betalvagg": False, "typ": typ, "land": "XX",
            "region": region, "agare": "privat", "statskontrollerad": stat}


def handelse(eid="aaaaaaaaaa", kallor=None, rubrik_sv="Tågolycka i Spanien", rubrik_en="Train crash in Spain",
             blind=None, usa_blind=None, amnen=("varlden",), **extra):
    kallor = kallor if kallor is not None else [kalla("a"), kalla("b", "usa"), kalla("c", "asien")]
    regioner = sorted({k["region"] for k in kallor})
    ev = {"id": eid, "poang": 10.0, "antal_kallor": len(kallor), "amnen_sektion": list(amnen), "reserv_rubrik": rubrik_en,
          "kallor": kallor,
          "utkast": {"rubrik_sv": rubrik_sv, "sammanfattning_sv": "Minst 60 döda.", "rubrik_en": rubrik_en,
                     "sammanfattning_en": "At least 60 dead.", "osaker": False},
          "kallkontroll": {"ok": True, "antal": 3, "problem": []},
          "perspektiv": {"regioner": regioner, "per_region": {r: [] for r in regioner}, "blind_flack": blind, "usa_blind": usa_blind}}
    ev.update(extra)
    return ev


GLOBAL = [kalla("BBC"), kalla("NPR", "usa"), kalla("SCMP", "asien")]
SVENSKT = [kalla("SVT", "sverige"), kalla("Ekot", "sverige"), kalla("DN", "sverige")]
NORDISKT = [kalla("SVT", "sverige"), kalla("NRK", "norden"), kalla("Yle", "norden")]


# ---------- Relevans ----------

def test_svensk_nyhet_ar_relevant_for_svensk_men_inte_engelsk_laser():
    r = utgava.relevans(handelse(kallor=SVENSKT, rubrik_sv="Misshandel i Uppsala", rubrik_en="Assault in Uppsala"))
    assert r["sv"] == 3 and r["en"] == 0


def test_svensk_nyhet_som_paverkar_utlandet_nar_den_engelska_utgavan():
    for rubrik in ("Sweden joins NATO exercise as Russia warns", "Ericsson cuts 5,000 jobs, shares fall",
                   "Swedish court rules on Nobel prize payout", "Riksbank follows ECB, krona weakens against dollar"):
        r = utgava.relevans(handelse(kallor=SVENSKT, rubrik_en=rubrik))
        assert r["en"] >= 2, rubrik


def test_global_handelse_ar_relevant_for_bada():
    r = utgava.relevans(handelse(kallor=GLOBAL))
    assert r["sv"] >= 1 and r["en"] >= 2


def test_global_handelse_utan_svensk_kalla_ar_den_som_saknas_i_svenska_medier():
    ev = handelse(kallor=GLOBAL, blind="saknas_i_sverige")
    assert utgava.relevans(ev)["sv"] == 1 and utgava.visa(ev, "sv") and utgava.visa(ev, "en")


def test_en_svensk_kalla_gor_globalt_relevant_for_svensken():
    ev = handelse(kallor=GLOBAL + [kalla("SVT", "sverige")])
    assert utgava.relevans(ev)["sv"] == 2


def test_nordisk_handelse_utan_global_koppling_visas_inte_for_engelsk_laser():
    ev = handelse(kallor=NORDISKT, rubrik_en="Municipal budget approved in Oslo")
    assert utgava.visa(ev, "sv") and not utgava.visa(ev, "en")


def test_tunt_underlag_ar_inte_relevant_for_engelsk_laser():
    ev = handelse(kallor=[kalla("BBC"), kalla("NPR", "usa")])
    assert not utgava.visa(ev, "en")


def test_amerikansk_koppling_ger_hogre_relevans():
    med = utgava.relevans(handelse(kallor=GLOBAL, rubrik_en="Fed holds rates as Trump criticises tariffs"))["en"]
    utan = utgava.relevans(handelse(kallor=[kalla("BBC"), kalla("DW"), kalla("SCMP", "asien")], rubrik_en="Flooding in Bangladesh"))["en"]
    assert med == 3 and utan == 2


def test_kuraterade_och_statliga_kallor_raknas_inte_som_oberoende():
    ev = handelse(kallor=[kalla("SVT", "sverige"), kalla("Techmeme", "usa", typ="kuraterat"), kalla("RT", "europa", stat=True)],
                  rubrik_en="Local fire in Gothenburg")
    assert utgava.relevans(ev)["en"] == 0


# ---------- Grindar per utgåva ----------

def test_blind_flack_saknas_i_sverige_hindrar_inte_engelska_utgavan():
    ev = handelse(kallor=GLOBAL, blind="saknas_i_sverige")
    assert "blind fläck" in autopilot.grindar(ev)
    assert utgava.grindar(ev, "en") == []
    assert utgava.grindar(ev, "sv") == ["blind fläck"]


def test_blind_flack_i_sv_ar_batchgranskning_inte_hinder():
    ev = handelse(kallor=GLOBAL, blind="saknas_i_sverige")
    assert utgava.grindar(ev, "sv", batch=True) == []
    assert utgava.kraver_genomgang(ev, "sv") is True and utgava.kraver_genomgang(ev, "en") is False


def test_usa_blind_gar_alltid_till_redaktoren_i_bada():
    ev = handelse(kallor=GLOBAL, usa_blind="mest_bla")
    assert utgava.grindar(ev, "en") == ["blind fläck"] and utgava.grindar(ev, "sv", batch=True) == ["blind fläck"]


def test_svenska_kallkravet_galler_bara_svenska_utgavan():
    ev = handelse(kallor=GLOBAL + [kalla("SVT", "sverige")], amnen=("sverige",))
    assert any("svenska" in s for s in utgava.grindar(ev, "sv"))
    assert not any("svenska" in s for s in utgava.grindar(ev, "en"))


def test_ovriga_grindar_gar_igenom_oforandrade():
    ev = handelse(kallor=GLOBAL, kallkontroll={"ok": False, "antal": 3, "problem": ["x"]})
    assert any("källkontroll" in s for s in utgava.grindar(ev, "en"))
    assert any("källkontroll" in s for s in utgava.grindar(ev, "sv", batch=True))


# ---------- Urval ----------

def test_urval_sorterar_efter_poang_och_respekterar_utgavan():
    evs = [handelse("a000000001", kallor=GLOBAL, poang=5), handelse("b000000001", kallor=SVENSKT, rubrik_en="Assault in Uppsala", poang=9),
           handelse("c000000001", kallor=GLOBAL, poang=8)]
    assert [e["id"] for e in utgava.urval(evs, "en")] == ["c000000001", "a000000001"]
    assert [e["id"] for e in utgava.urval(evs, "sv")] == ["b000000001", "c000000001", "a000000001"] or \
        [e["id"] for e in utgava.urval(evs, "sv")] == ["b000000001", "c000000001", "a000000001"]


def test_urval_filtrerar_bort_dem_som_inte_klarar_grindarna():
    evs = [handelse("a000000001", kallor=GLOBAL), handelse("b000000001", kallor=GLOBAL, blind="saknas_i_sverige"),
           handelse("c000000001", kallor=[kalla("BBC"), kalla("NPR", "usa")])]
    assert [e["id"] for e in utgava.urval(evs, "en")] == ["a000000001", "b000000001"]
    assert [e["id"] for e in utgava.urval(evs, "sv")] == ["a000000001"]
    assert [e["id"] for e in utgava.urval(evs, "sv", batch=True)] == ["a000000001", "b000000001"]


def test_urval_utan_grindar_ger_alla_relevanta():
    evs = [handelse("a000000001", kallor=GLOBAL, kallkontroll=None), handelse("b000000001", kallor=NORDISKT, rubrik_en="Budget in Oslo")]
    assert len(utgava.urval(evs, "sv", grindar_=False)) == 2 and len(utgava.urval(evs, "en", grindar_=False)) == 1


def test_okand_utgava_ger_fel():
    with pytest.raises(ValueError):
        utgava.visa(handelse(), "de")


# ---------- Mot dagens riktiga flöde ----------

@pytest.mark.skipif(not FLODE.exists(), reason="data/flode.json saknas")
def test_riktigt_flode_engelska_utgavan_har_aldrig_rent_svenskt():
    handelser = json.loads(FLODE.read_text(encoding="utf-8"))["handelser"]
    valda = utgava.urval(handelser, "en", grindar_=False)
    assert valda, "den engelska utgåvan ska ha något att visa"
    for e in valda:
        oberoende = [k for k in e["kallor"] if k["typ"] != "kuraterat" and not k["statskontrollerad"]]
        assert any(k["region"] not in ("sverige", "norden") for k in oberoende) or utgava.relevans(e)["en"] >= 2


@pytest.mark.skipif(not FLODE.exists(), reason="data/flode.json saknas")
def test_riktigt_flode_allt_som_klarar_autopilotens_grindar_syns_i_svenska_utgavan():
    handelser = json.loads(FLODE.read_text(encoding="utf-8"))["handelser"]
    for e in handelser:
        if not autopilot.grindar(e):
            assert utgava.visa(e, "sv"), e["utkast"]["rubrik_sv"]
