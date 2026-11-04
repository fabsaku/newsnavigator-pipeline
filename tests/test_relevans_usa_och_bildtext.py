"""USA: blått och rött bara när det är relevant, och bildtextens enda skillnadsrad bara när källorna verkligen skiljer sig åt."""
import re

import pytest

import instagram
import newsletter
import render
import sajt
import utgava
from test_instagram_en import handelse, kalla


def usa_sidor(bla=("NPR", "CNN"), rod=("Fox", "Daily Wire"), mitten=()):
    def sida(namn, lut):
        return [{"kalla": n, "rubrik": f"{n} headline", "url": f"https://x/{n}", "lutning": lut} for n in namn]
    return {"bla": sida(bla, "lutar_vanster"), "mitten": sida(mitten, "mitten"), "rod": sida(rod, "lutar_hoger")}


def ev_med_usa(rubrik_en="Trump signs spending bill after Senate vote", rubrik_sv="Trump skriver under budgeten efter omröstning", **usa_kw):
    ev = handelse()
    ev["utkast"].update({"rubrik_en": rubrik_en, "rubrik_sv": rubrik_sv, "usa_sv": "Rubrikerna skiljer sig i ordval.", "usa_en": "Headlines differ in wording."})
    ev["reserv_rubrik"] = rubrik_en
    ev["perspektiv"]["usa"] = usa_sidor(**usa_kw)
    return ev


# ---------- USA: blått och rött ----------

def test_visas_nar_handelsen_ar_amerikansk_och_bada_sidor_finns():
    assert utgava.usa_relevant(ev_med_usa())


@pytest.mark.parametrize("rubrik_en,rubrik_sv", [
    ("Train crash in Spain leaves 69 dead", "Tågolycka i Spanien dödar 69"),
    ("Earthquake hits Japan", "Jordbävning i Japan"),
    ("Ukraine and Russia to hold talks in Abu Dhabi", "Ukraina och Ryssland ska hålla samtal"),
])
def test_visas_inte_for_globala_handelser_utan_amerikansk_koppling(rubrik_en, rubrik_sv):
    assert not utgava.usa_relevant(ev_med_usa(rubrik_en=rubrik_en, rubrik_sv=rubrik_sv))


@pytest.mark.parametrize("rubrik_en,rubrik_sv", [
    ("Democrats take control of Congress in US midterms", "Demokraterna tar kontrollen över kongressen i midtermvalet"),
    ("Supreme Court rules on tariffs", "Högsta domstolen avgör om tullarna"),
    ("Republicans split over budget", "Republikanerna splittrade om budgeten"),
    ("Fed holds rates", "Fed behåller räntan"),
    ("White House denies report", "Vita huset dementerar uppgifter"),
])
def test_visas_for_amerikansk_politik_och_ekonomi(rubrik_en, rubrik_sv):
    assert utgava.usa_relevant(ev_med_usa(rubrik_en=rubrik_en, rubrik_sv=rubrik_sv))


def test_kravs_bade_bla_och_rod_och_minst_tre_medier():
    assert not utgava.usa_relevant(ev_med_usa(bla=("NPR", "CNN"), rod=()))                  # bara en sida
    assert not utgava.usa_relevant(ev_med_usa(bla=("NPR",), rod=("Fox",)))                 # bara två medier
    assert not utgava.usa_relevant(ev_med_usa(bla=(), rod=(), mitten=("AP", "Reuters")))   # bara mitten
    assert utgava.usa_relevant(ev_med_usa(bla=("NPR",), rod=("Fox",), mitten=("AP",)))
    ev = ev_med_usa()
    ev["perspektiv"].pop("usa")
    assert not utgava.usa_relevant(ev)


def test_notissidan_visar_blocket_bara_nar_det_ar_relevant():
    rel = sajt.story_page(sajt.Urls(flat=False, lang="sv"), {**ev_med_usa(), "godkand_tid": 1.0}, [], [], "", True)
    irrel = sajt.story_page(sajt.Urls(flat=False, lang="sv"), {**ev_med_usa(rubrik_en="Earthquake hits Japan", rubrik_sv="Jordbävning i Japan"), "godkand_tid": 1.0}, [], [], "", True)
    assert "USA: blått och rött" in rel and "Rubrikerna skiljer sig i ordval." in rel
    assert "USA: blått och rött" not in irrel and "Rubrikerna skiljer sig i ordval." not in irrel


def test_kortet_finns_bara_nar_det_ar_relevant():
    assert instagram.slide_usa(ev_med_usa(), "sv")
    assert instagram.slide_usa(ev_med_usa(rubrik_en="Earthquake hits Japan", rubrik_sv="Jordbävning i Japan"), "sv") is None
    sidor = instagram.slides(ev_med_usa(rubrik_en="Earthquake hits Japan", rubrik_sv="Jordbävning i Japan"), lang="sv")
    assert all("USA: blått och rött" not in s for s in sidor)


def test_brevet_tar_med_raden_bara_nar_det_ar_relevant():
    rel, irrel = ev_med_usa(), ev_med_usa(rubrik_en="Earthquake hits Japan", rubrik_sv="Jordbävning i Japan")
    assert newsletter.usa_text(rel, "sv") and not newsletter.usa_text(irrel, "sv")


# ---------- Bildtextens skillnadsrad ----------

def med_oenighet(sv, en=None):
    ev = handelse()
    ev["utkast"]["oenighet"] = sv
    ev["utkast"]["oenighet_en"] = en
    return ev


def rad_med(cap, start):
    return next((r for r in cap.splitlines() if r.startswith(start)), None)


def test_ingen_rad_nar_kallorna_ar_eniga():
    for sv, en in (("Källorna är eniga om förloppet och siffrorna.", "The sources agree on the sequence and the figures."),
                   ("Inga skillnader mellan källorna.", "No differences between the sources."), (None, None), ("", "")):
        ev = med_oenighet(sv, en)
        assert "skiljer sig åt" not in instagram.caption(ev, "sv") and "Sources differ" not in instagram.caption(ev, "en")


def test_en_mening_nar_kallorna_skiljer_sig_at():
    ev = med_oenighet("Dödstalet varierar mellan källorna: BBC anger 60 och NPR 64. Reuters anger ett spann. Fler detaljer följer.",
                      "The death toll varies between sources: BBC says 60 and NPR 64. Reuters gives a range. More follows.")
    sv, en = instagram.caption(ev, "sv"), instagram.caption(ev, "en")
    assert "Dödstalet varierar mellan källorna: BBC anger 60 och NPR 64." in sv and "Reuters anger ett spann" not in sv
    assert "The death toll varies between sources: BBC says 60 and NPR 64." in en and "Reuters gives a range" not in en


def test_den_motsagande_inledningen_ger_ingen_dubbel_etikett():
    """Det verkliga fallet: AI-texten börjar med att källorna är eniga och säger sedan var de skiljer sig."""
    text = ("Källorna är eniga om att demokraterna har vunnit senaten, men formuleringarna om representanthuset skiljer sig åt. "
            "Premium Times skriver att demokraterna leder. The Japan Times skriver att omfattningen klarnar.")
    cap = instagram.caption(med_oenighet(text), "sv")
    assert "Källorna skiljer sig åt: Källorna är eniga" not in cap
    assert "Källorna är eniga om att demokraterna har vunnit senaten, men formuleringarna om representanthuset skiljer sig åt." in cap
    assert "Premium Times" not in cap.split("Källor:")[0]


def test_etikett_laggs_till_nar_meningen_inte_namner_kallorna():
    cap = instagram.caption(med_oenighet("Dödstalet varierar: 60 enligt BBC och 64 enligt NPR."), "sv")
    assert "Källorna skiljer sig åt: Dödstalet varierar: 60 enligt BBC och 64 enligt NPR." in cap


def test_for_lang_mening_hoppas_over_hellre_an_klipps():
    lang = "Källorna skiljer sig åt " + " ".join(["och"] * 120) + "."
    cap = instagram.caption(med_oenighet(lang), "sv")
    assert "skiljer sig åt" not in cap and "och och och" not in cap


def test_bildtexten_ar_kort_med_skillnadsraden():
    for lang in ("sv", "en"):
        cap = instagram.caption(med_oenighet("Dödstalet varierar mellan källorna.", "The death toll varies between sources."), lang)
        assert len(cap) < 700
