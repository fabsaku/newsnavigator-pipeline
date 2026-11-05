"""Fas 3: autopiloten. Grindarna som ren funktion, vetofönstret, taket, tyst läge, ångra och märkningen."""
import json
import time

import pytest

import autopilot
import granskning_github
import instagram
import newsletter
import sajt


def kalla(namn, region="europa", typ="media", stat=False, rubrik="Train crash in Spain kills dozens"):
    return {"namn": namn, "rubrik": rubrik, "url": f"https://example.org/{namn}", "betalvagg": False, "typ": typ,
            "land": "XX", "region": region, "agare": "privat", "statskontrollerad": stat}


def handelse(**andringar):
    ev = {
        "id": "abc1234567", "amnen": ["varlden"], "amnen_sektion": ["varlden"], "poang": 9.0, "antal_kallor": 3,
        "reserv_rubrik": "Train crash in Spain",
        "utkast": {"rubrik_sv": "Tågolycka i Spanien", "sammanfattning_sv": "Minst 60 döda enligt myndigheterna.",
                   "rubrik_en": "Train crash in Spain", "sammanfattning_en": "At least 60 dead, authorities say.",
                   "osaker": False},
        "kallkontroll": {"ok": True, "antal": 5, "problem": []},
        "perspektiv": {"regioner": ["europa", "usa"], "per_region": {"europa": [], "usa": []}, "blind_flack": None, "usa_blind": None},
        "kallor": [kalla("BBC"), kalla("France 24"), kalla("NPR", "usa")],
    }
    ev.update(andringar)
    return ev


# ---------- Grindarna ----------

def test_bra_notis_klarar_grindarna():
    assert autopilot.grindar(handelse()) == []


def test_kallkontroll_med_anmarkning_stoppar():
    ev = handelse(kallkontroll={"ok": False, "antal": 5, "problem": ["x"]})
    assert any("källkontroll" in s for s in autopilot.grindar(ev))
    assert autopilot.grindar(handelse(kallkontroll=None))


def test_osakert_utkast_stoppar():
    ev = handelse(utkast={**handelse()["utkast"], "osaker": True})
    assert any("osäker" in s for s in autopilot.grindar(ev))


def test_minst_tre_oberoende_kallor_och_tva_regioner():
    assert autopilot.grindar(handelse(kallor=[kalla("BBC"), kalla("NPR", "usa")]))
    # Kuraterade listor och statskontrollerade medier räknas inte
    kuraterat = handelse(kallor=[kalla("BBC"), kalla("NPR", "usa"), kalla("Techmeme", "usa", typ="kuraterat")])
    assert autopilot.grindar(kuraterat)
    stat = handelse(kallor=[kalla("BBC"), kalla("NPR", "usa"), kalla("RT", "europa", stat=True)])
    assert autopilot.grindar(stat)
    en_region = handelse(kallor=[kalla("BBC"), kalla("France 24"), kalla("DW")],
                         perspektiv={"regioner": ["europa"], "blind_flack": None, "usa_blind": None})
    assert any("region" in s for s in autopilot.grindar(en_region))


def test_svensk_nyhet_kraver_tva_svenska_kallor():
    ev = handelse(amnen_sektion=["sverige"], kallor=[kalla("SVT", "sverige"), kalla("BBC"), kalla("NPR", "usa")])
    assert any("svenska" in s for s in autopilot.grindar(ev))
    ok = handelse(amnen_sektion=["sverige"], kallor=[kalla("SVT", "sverige"), kalla("Ekot", "sverige"), kalla("NRK", "norden")])
    assert autopilot.grindar(ok) == []


def test_hopslagna_kluster_stoppar():
    manga = handelse(kallor=[kalla(f"k{n}", ["europa", "usa"][n % 2]) for n in range(21)])
    assert any("hopslagna" in s for s in autopilot.grindar(manga))
    sektioner = handelse(amnen_sektion=["ai", "marknader", "sverige", "rymd"])
    assert any("hopslagna" in s for s in autopilot.grindar(sektioner))


@pytest.mark.parametrize("text", ["Man misstänkt för mord i Uppsala", "Rapport om självmord bland unga",
                                  "Teenager charged after knife attack", "Children hurt in school bus crash"])
def test_sparrlistan_stoppar(text):
    ev = handelse(utkast={**handelse()["utkast"], "rubrik_sv": text, "rubrik_en": text})
    assert any("spärrord" in s for s in autopilot.grindar(ev))


def test_sparrlistan_laser_aven_kallornas_rubriker():
    ev = handelse(kallor=[kalla("BBC", rubrik="Suspect arrested after train crash"), kalla("France 24"), kalla("NPR", "usa")])
    assert any("spärrord" in s for s in autopilot.grindar(ev))


def test_blinda_flackar_gar_alltid_till_redaktoren():
    ev = handelse(perspektiv={"regioner": ["europa", "usa"], "blind_flack": "saknas_i_sverige", "usa_blind": None})
    assert any("blind" in s for s in autopilot.grindar(ev))
    ev = handelse(perspektiv={"regioner": ["europa", "usa"], "blind_flack": None, "usa_blind": "mest_bla"})
    assert any("blind" in s for s in autopilot.grindar(ev))


# ---------- Inställningar och tak ----------

def test_installningar_standard_ar_avstangd(tmp_path):
    s = autopilot.load_settings(tmp_path / "finns-inte.json")
    assert s["pa"] is False and s["tyst"] is False and s["vetofonster_minuter"] == 45


def test_taket_ar_tva_forsta_veckan_sedan_atta():
    s = {"tak": 2, "tak_efter_forsta_veckan": 8}
    start = 1_000_000.0
    assert autopilot.effektivt_tak(s, {"startad": start}, start + 3 * 86400) == 2
    assert autopilot.effektivt_tak(s, {"startad": start}, start + 8 * 86400) == 8
    assert autopilot.effektivt_tak(s, {}, start) == 2


# ---------- Vetofönstret ----------

def kor(events, approved=(), s=None, status=None, now=1_000_000.0):
    s = {**autopilot.load_settings(None), "pa": True, **(s or {})}
    status = status if status is not None else autopilot.tom_status()
    nya = autopilot.kor(events, set(approved), s, status, now)
    return nya, status


def test_avstangd_autopilot_gor_ingenting():
    nya, status = kor([handelse()], s={"pa": False})
    assert nya == set() and status["ko"] == {}


def test_notis_som_klarar_grindarna_laggs_i_kon_med_klockslag():
    nya, status = kor([handelse()])
    assert nya == set()
    assert status["ko"]["abc1234567"]["klar"] == 1_000_000.0 + 45 * 60
    assert status["ko"]["abc1234567"]["rubrik"] == "Tågolycka i Spanien"


def test_notis_publiceras_nar_fonstret_gatt_ut():
    _, status = kor([handelse()])
    nya, status = kor([handelse()], status=status, now=1_000_000.0 + 46 * 60)
    assert nya == {"abc1234567"}
    assert "abc1234567" not in status["ko"] and "abc1234567" in status["publicerade"]


def test_notis_som_stoppats_kommer_inte_tillbaka():
    _, status = kor([handelse()])
    status["stoppade"]["abc1234567"] = 1_000_000.0
    status["ko"].pop("abc1234567")
    nya, status = kor([handelse()], status=status, now=1_000_000.0 + 60 * 60)
    assert nya == set() and "abc1234567" not in status["ko"]


def test_notis_som_lamnat_flodet_lamnar_kon():
    _, status = kor([handelse()])
    _, status = kor([handelse(id="annan12345")], status=status, now=1_000_000.0 + 60 * 60)
    assert "abc1234567" not in status["ko"]


def test_manuellt_godkand_notis_lamnar_kon():
    _, status = kor([handelse()])
    nya, status = kor([handelse()], approved={"abc1234567"}, status=status, now=1_000_000.0 + 60 * 60)
    assert nya == set() and "abc1234567" not in status["ko"] and "abc1234567" not in status["publicerade"]


def test_taket_per_dygn():
    amnen = ["Harbour strike in Rotterdam", "Volcano erupts on Iceland", "Bank merger in Tokyo", "Drought hits Kenya"]
    evs = [handelse(id=f"id{i}00000000"[:10], reserv_rubrik=t, utkast={**handelse()["utkast"], "rubrik_en": t},
                    kallor=[{**k, "url": f"https://k/{i}/{j}"} for j, k in enumerate(handelse()["kallor"])])
           for i, t in enumerate(amnen)]
    _, status = kor(evs)
    nya, status = kor(evs, status=status, now=1_000_000.0 + 60 * 60)
    assert len(nya) == 2 and len(status["ko"]) == 2
    nya2, status = kor(evs, status=status, now=1_000_000.0 + 2 * 60 * 60)
    assert nya2 == set()
    nya3, status = kor(evs, status=status, now=1_000_000.0 + 25 * 60 * 60)
    assert len(nya3) == 2


def test_tyst_lage_publicerar_inget_men_samlar():
    _, status = kor([handelse()])
    nya, status = kor([handelse()], s={"tyst": True}, status=status, now=1_000_000.0 + 60 * 60)
    assert nya == set() and "abc1234567" in status["ko"]


# ---------- Granskningsärendet som vetofönster ----------

def test_bock_i_kon_ar_inte_godkannande_och_urbockad_stoppar():
    status = autopilot.tom_status()
    status["ko"] = {"aaaaaaaaaa": {"klar": 1.0}, "bbbbbbbbbb": {"klar": 1.0}}
    ticks = {"aaaaaaaaaa": True, "bbbbbbbbbb": False, "cccccccccc": True, "dddddddddd": False}
    ok, added, removed = granskning_github.tillampa_bockar(ticks, {"dddddddddd"}, status)
    assert ok == {"cccccccccc"}
    assert added == {"cccccccccc"} and removed == {"dddddddddd"}
    assert "aaaaaaaaaa" in status["ko"] and "bbbbbbbbbb" not in status["ko"]
    assert "bbbbbbbbbb" in status["stoppade"] and "dddddddddd" in status["stoppade"]


def test_arendet_visar_kon_med_klockslag():
    status = autopilot.tom_status()
    status["ko"]["abc1234567"] = {"klar": 1_000_000.0, "rubrik": "Tågolycka i Spanien", "tillagd": 999_000.0}
    rad = granskning_github._ko_rad(handelse(), status["ko"]["abc1234567"])
    assert rad.startswith("- [x] ") and "`abc1234567`" in rad and "bockar ur" in rad


# ---------- Ångra ----------

def test_angra_tar_bort_ur_godkanda_och_arkiv(tmp_path, monkeypatch):
    godk, arkiv, status_fil = tmp_path / "godkanda.json", tmp_path / "arkiv.json", tmp_path / "status.json"
    godk.write_text(json.dumps(["abc1234567", "x"]))
    arkiv.write_text(json.dumps({"abc1234567": {"id": "abc1234567"}, "x": {"id": "x"}}))
    monkeypatch.setattr(autopilot, "GODK", godk)
    monkeypatch.setattr(autopilot, "ARKIV", arkiv)
    monkeypatch.setattr(autopilot, "STATUS", status_fil)
    import instagram
    monkeypatch.setattr(instagram, "STATE_DIR", tmp_path / "ig")
    monkeypatch.setattr(instagram, "LEGACY_STATE", tmp_path / "gammal.json")
    autopilot.angra("abc1234567", now=5.0)
    assert json.loads(godk.read_text()) == ["x"]
    assert list(json.loads(arkiv.read_text())) == ["x"]
    assert json.loads(status_fil.read_text())["stoppade"]["abc1234567"] == 5.0


# ---------- Märkningen ----------

def test_arkivet_marker_automatiska(tmp_path, monkeypatch):
    monkeypatch.setattr(newsletter, "ARKIV", tmp_path / "arkiv.json")
    arkiv = newsletter.archive([handelse(), handelse(id="manuell123")], {"abc1234567", "manuell123"}, automatic={"abc1234567"})
    assert arkiv["abc1234567"]["automatisk"] is True and arkiv["manuell123"]["automatisk"] is False


AUTO_SV = "Publicerad utan manuell granskning"


def test_sajten_marker_automatiska():
    auto = {**handelse(), "granskad": True, "godkand_tid": 1_000_000.0, "automatisk": True}
    manuell = {**auto, "automatisk": False}
    u = sajt.Urls(flat=True)
    assert AUTO_SV in sajt.story_page(u, auto, [], [], "", True)
    assert AUTO_SV not in sajt.story_page(u, manuell, [], [], "", True)
    assert "granskad av redaktionen" in sajt.story_page(u, manuell, [], [], "", True)


def test_navigatorn_marker_automatiska():
    auto = {**handelse(), "granskad": True, "godkand_tid": 1_000_000.0, "automatisk": True}
    html = newsletter._story(auto, "sv", True)
    assert AUTO_SV in html
    assert AUTO_SV not in newsletter._story({**auto, "automatisk": False}, "sv", True)


def test_instagram_marker_automatiska():
    auto = {**handelse(), "granskad": True, "godkand_tid": 1_000_000.0, "automatisk": True}
    assert AUTO_SV in instagram.caption(auto)
    assert AUTO_SV in instagram.slide_cover(auto, "28 oktober", False)
    assert AUTO_SV not in instagram.caption({**auto, "automatisk": False})


def test_angra_tar_bort_inlagget_pa_kontot_dar_det_postades(tmp_path, monkeypatch):
    import instagram
    monkeypatch.setattr(autopilot, "GODK", tmp_path / "godkanda.json")
    monkeypatch.setattr(autopilot, "ARKIV", tmp_path / "arkiv.json")
    monkeypatch.setattr(autopilot, "STATUS", tmp_path / "status.json")
    monkeypatch.setattr(instagram, "STATE_DIR", tmp_path / "ig")
    monkeypatch.setattr(instagram, "LEGACY_STATE", tmp_path / "gammal.json")
    instagram.save_state({"abc1234567": {"ig_id": "SVPOST", "postad": 1}}, "sv")
    instagram.save_state({"abc1234567": {"ig_id": "ENPOST", "postad": 1}}, "en")
    monkeypatch.setenv("IG_ACCESS_TOKEN", "SVTOKEN")
    monkeypatch.setenv("IG_ACCESS_TOKEN_EN", "ENTOKEN")
    anrop = []
    monkeypatch.setattr(instagram, "_api", lambda path, params, method="POST": anrop.append((path, params["access_token"], method)) or {"success": True})
    autopilot.angra("abc1234567", now=5.0)
    assert sorted(anrop) == [("ENPOST", "ENTOKEN", "DELETE"), ("SVPOST", "SVTOKEN", "DELETE")]


# ---------- Stora berättelser: sammanhangsmåttet är bara information ----------

def test_sammanhangsmattet_luckrar_inte_upp_hopslagningsgrinden():
    """Kalibrering 5 november: rena kluster låg mellan 0,47 och 0,88 och det enda blandade på 0,63, så måttet skiljer inte hopslagningar från stora berättelser."""
    stor = handelse(kallor=[kalla(f"K{i}", "usa" if i % 2 else "europa") for i in range(24)], sammanhang=0.9)
    assert any("hopslagna" in s for s in autopilot.grindar(stor))


def _svensk(*regioner, amnen=("sverige",), rubrik="Riksdagen röstar om budgeten"):
    return {"amnen_sektion": list(amnen), "kallkontroll": {"ok": True},
            "utkast": {"rubrik_sv": rubrik, "sammanfattning_sv": "Text."},
            "kallor": [{"region": r, "rubrik": rubrik, "typ": "media"} for r in regioner]}


def test_tva_svenska_kallor_racker_for_inrikes():
    assert autopilot.grindar(_svensk("sverige", "sverige")) == []


def test_en_svensk_kalla_racker_inte():
    assert any("färre än tre" in s for s in autopilot.grindar(_svensk("sverige", "norden")))


def test_utlandsnyhet_i_svenska_medier_omfattas_inte_om_annan_region_finns():
    skal = autopilot.grindar(_svensk("sverige", "sverige", "usa", amnen=("usa",)))
    assert skal == []
    assert any("färre än tre" in s for s in autopilot.grindar(_svensk("sverige", "usa", amnen=("usa",))))


def test_svenskt_noje_omfattas_inte():
    assert "bara en region" in autopilot.grindar(_svensk("sverige", "sverige", amnen=("noje",)))


def test_sparrord_galler_aven_inrikes():
    assert any("spärrord" in s for s in autopilot.grindar(_svensk("sverige", "sverige", rubrik="Man häktad i Malmö")))


def test_svenska_medier_om_utlandet_ar_inte_inrikes():
    assert "bara en region" in autopilot.grindar(_svensk("sverige", "sverige", amnen=("usa",), rubrik="Trump talar i Ohio"))


def test_namngivet_brottmal_gar_till_redaktoren():
    assert any("spärrord" in s for s in autopilot.grindar(_svensk("sverige", "sverige", rubrik="Marius Borg Høiby hålls kvar i häkte")))


def test_bara_i_sverige_stoppar_inte_inrikes():
    ev = {**_svensk("sverige", "sverige"), "perspektiv": {"blind_flack": "bara_i_sverige"}}
    assert autopilot.grindar(ev) == []


def test_saknas_i_sverige_stoppar_fortfarande():
    ev = {**_svensk("usa", "europa", "asien", amnen=("usa",)), "perspektiv": {"blind_flack": "saknas_i_sverige"}}
    assert "blind fläck" in autopilot.grindar(ev)


def _i_ko(eid, rubrik, poang, *regioner, amnen=("usa",)):
    ev = {**_svensk(*regioner, amnen=amnen, rubrik=rubrik), "id": eid, "poang": poang, "reserv_rubrik": rubrik, "antal_kallor": len(regioner)}
    ev["utkast"]["rubrik_en"] = rubrik
    for i, k in enumerate(ev["kallor"]):
        k["url"] = f"https://k/{eid}/{i}"
    return ev


def _kor(events, tak=8):
    status = {**autopilot.tom_status(), "startad": 1.0, "ko": {e["id"]: {"klar": 0, "rubrik": "x"} for e in events}}
    settings = {**autopilot.STANDARD, "pa": True, "tak": tak, "tak_efter_forsta_veckan": tak}
    return autopilot.kor(events, set(), settings, status, now=1000.0), status


def test_samma_handelse_publiceras_inte_tva_ganger_samma_dygn(tmp_path, monkeypatch):
    monkeypatch.setattr(autopilot, "ARKIV", tmp_path / "arkiv.json")
    a = _i_ko("a", "Democrats win control of Congress in midterm elections", 40, "usa", "europa", "asien")
    b = _i_ko("b", "Democrats win control of Congress in the midterm vote", 30, "usa", "europa", "afrika")
    nya, status = _kor([a, b])
    assert nya == {"a"} and "b" in status["ko"]


def test_svensk_inrikes_gar_fore_hog_poang_under_taket(tmp_path, monkeypatch):
    monkeypatch.setattr(autopilot, "ARKIV", tmp_path / "arkiv.json")
    stor = _i_ko("a", "Summit opens in Nairobi with leaders", 40, "usa", "europa", "asien")
    svensk = _i_ko("b", "Riksdagen röstar om budgeten", 10, "sverige", "sverige", amnen=("sverige",))
    nya, _ = _kor([stor, svensk], tak=1)
    assert nya == {"b"}


def test_det_som_maste_med_gar_forst_och_rakans_inte_mot_taket(tmp_path, monkeypatch):
    monkeypatch.setattr(autopilot, "ARKIV", tmp_path / "arkiv.json")
    maste = {**_i_ko("a", "Summit opens in Nairobi with leaders", 30, "usa", "europa", "asien"), "maste": True}
    svensk = _i_ko("b", "Riksdagen röstar om budgeten", 10, "sverige", "sverige", amnen=("sverige",))
    vanlig = _i_ko("c", "Harbour strike halts Rotterdam traffic", 20, "usa", "europa", "asien")
    nya, _ = _kor([vanlig, svensk, maste], tak=1)
    assert nya == {"a", "b"}

