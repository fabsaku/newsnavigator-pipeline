"""Bevakningsspåren: träffar, krav på andel rubriker, och att de inte påverkar annat än urvalet."""
import pipeline
import sajt
import spar
import vikt


def test_spar_traffar_ratt():
    assert spar.av_rubriker(["Ceasefire talks resume in Doha"]) == ["samarbete"]
    assert spar.av_rubriker(["Amnesty reports torture in prisons"]) == ["rattigheter"]
    assert spar.av_rubriker(["EU tightens rules on emissions"]) == ["miljo"]
    assert spar.av_rubriker(["Saab tests new Gripen radar"]) == ["teknik"]


def test_kriget_i_sig_ar_inget_spar():
    assert spar.av_rubriker(["Russian strikes hit Kharkiv as war enters new phase"]) == []


def test_religion_kraver_bade_tro_och_vald():
    assert spar.av_rubriker(["Pope visits a church in Lisbon"]) == []
    assert spar.av_rubriker(["Gunmen attack a church in Nigeria"]) == ["religion"]
    assert spar.av_rubriker(["Gunmen attack a mosque in Pakistan"]) == ["religion"]
    assert spar.av_rubriker(["Rise in antisemitism reported across Europe"]) == ["religion"]


def test_i_stora_handelser_kravs_var_femte_rubrik():
    rubriker = ["Climate talks open"] + [f"Democrats win race {i}" for i in range(9)]
    assert spar.av_rubriker(rubriker) == []
    assert spar.av_rubriker(rubriker[:1] + ["Climate deal near"] + rubriker[1:9]) == ["miljo"]


def test_delspar_for_teknik():
    ev = {"kallor": [{"rubrik": "New iPhone goes on sale"}]}
    assert spar.delspar(ev)[0] == "hem"
    assert spar.delspar({"kallor": [{"rubrik": "Budget passes"}]}) is None


def _kluster(titel, score=1.0, sektion=None):
    return {"items": [{"title": titel, "source_id": "a", "region": "europa"}], "score": score, "section_topics": sektion or [],
            "vikt": {"spar": spar.av_rubriker([titel])}}


def test_spar_ger_vikt():
    med = vikt.vikt({"items": [{"title": "Climate deal signed", "source_id": "a", "region": "europa"}]}, {"europa": 10})
    utan = vikt.vikt({"items": [{"title": "Budget deal signed", "source_id": "a", "region": "europa"}]}, {"europa": 10})
    assert round(med[0] - utan[0], 1) == spar.VIKT
    assert med[1]["spar"] == ["miljo"]


def test_platser_hålls_at_sparen():
    vanliga = [_kluster(f"Budget vote {i}", score=100 - i) for i in range(10)]
    miljo = [_kluster(f"Climate report {i}", score=1 - i / 10) for i in range(3)]
    valda = pipeline.choose(vanliga + miljo, 5, reserved={})
    assert sum(1 for c in valda if "miljo" in c["vikt"]["spar"]) == pipeline.SPAR_PLATSER
    assert len(valda) == 5


def test_sparsidan_visar_tomma_spar_och_ar_lika_i_bada_utgavorna():
    ev = {"id": "abc", "reserv_rubrik": "Climate deal", "kallor": [{"rubrik": "Climate deal", "region": "europa", "namn": "X", "url": "https://x"}],
          "antal_kallor": 1, "utkast": {"rubrik_sv": "Klimatavtal", "rubrik_en": "Climate deal"}}
    for lang, tomt in (("sv", "Inga notiser"), ("en", "No stories")):
        sida = sajt.spar_page(sajt.Urls(flat=False, lang=lang), [ev], [], "", True)
        assert 'id="miljo"' in sida and tomt in sida and "/n/abc/" in sida
