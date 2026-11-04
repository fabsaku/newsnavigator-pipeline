"""A2: två Instagramkonton. @newsnavigator.se på svenska och @news.navigator på engelska, med varsitt tillstånd och varsina secrets."""
import json
import time
from datetime import datetime, timezone

import re

import pytest

import instagram

# Måndag 2 november 2026, 12.00 svensk tid
TS = datetime(2026, 11, 2, 11, 0, tzinfo=timezone.utc).timestamp()


def kalla(namn, region="europa", land="GB"):
    return {"namn": namn, "rubrik": f"{namn} headline", "url": f"https://x/{namn}", "typ": "media", "land": land, "region": region,
            "statskontrollerad": False, "betalvagg": False, "agare": "privat"}


def handelse(eid="aaaaaaaaaa", kallor=None, **extra):
    kallor = kallor if kallor is not None else [kalla("BBC", "europa", "GB"), kalla("NPR", "usa", "US"), kalla("SCMP", "asien", "HK")]
    ev = {"id": eid, "poang": 10.0, "antal_kallor": len(kallor), "amnen_sektion": ["varlden"], "reserv_rubrik": "Train crash in Spain",
          "godkand_tid": TS, "kallor": kallor,
          "utkast": {"rubrik_sv": "Tågolycka i Spanien", "sammanfattning_sv": "Minst 60 döda.", "oenighet": "Dödstalet varierar.",
                     "perspektiv_sv": "Europeiska källor lyfter räddningsarbetet.", "usa_sv": "x",
                     "rubrik_en": "Train crash in Spain", "sammanfattning_en": "At least 60 dead.", "oenighet_en": "The death toll varies.",
                     "perspektiv_en": "European sources focus on the rescue effort.", "usa_en": "x", "osaker": False},
          "perspektiv": {"regioner": ["asien", "europa", "usa"], "blind_flack": None, "usa_blind": None,
                         "per_region": {r: [{"kalla": k["namn"], "land": k["land"], "rubrik": f"{k['namn']} headline", "url": k["url"],
                                             "statskontrollerad": False}] for r, k in (("europa", kallor[0]), ("usa", kallor[1]), ("asien", kallor[2]))},
                         "usa": {"bla": [{"kalla": "NPR", "rubrik": "NPR headline", "url": "u", "lutning": "lutar_vanster"}],
                                 "mitten": [], "rod": [{"kalla": "Fox", "rubrik": "Fox headline", "url": "u", "lutning": "lutar_hoger"}]}}}
    ev.update(extra)
    return ev


SVENSKA = ["källor", "Saknas i svenska", "Så ser världen", "Sammanfattad med hjälp", "Nästa sida:", "Källorna skiljer sig", "Blå publik", "granskad av redaktionen"]


# ---------- Datum och kort ----------

def test_datum_pa_bada_spraken():
    assert instagram._date(TS) == "Måndag 2 november"
    assert instagram._date(TS, "en") == "Monday 2 November"


def test_omslaget_pa_engelska_har_ingen_svenska():
    html = instagram.slide_cover(handelse(), "Monday 2 November", True, lang="en")
    assert "Train crash in Spain" in html and "At least 60 dead." in html and "Tågolycka" not in html
    assert "3 sources in three regions" in html and "Next page: how the world sees it" in html
    assert "Summarised with the help of AI and reviewed by the editors." in html
    assert "World" in html and "Asia and Oceania" not in html      # sektionen, och korta regionnamn i remsan
    assert not any(s in html for s in SVENSKA)


def test_omslaget_pa_svenska_ar_oforandrat():
    html = instagram.slide_cover(handelse(), "Måndag 2 november", True)
    assert "Tågolycka i Spanien" in html and "3 källor i tre regioner" in html and "Nästa sida: så ser världen på det" in html


def test_saknas_i_svenska_medier_finns_inte_pa_engelska_kort():
    ev = handelse(perspektiv={**handelse()["perspektiv"], "blind_flack": "saknas_i_sverige"})
    assert "Saknas i svenska medier" in instagram.slide_cover(ev, "d", False)
    en = instagram.slide_cover(ev, "d", False, lang="en")
    assert "svenska" not in en and "Swedish" not in en


def test_blaa_roda_publiken_pa_engelska():
    ev = handelse(perspektiv={**handelse()["perspektiv"], "usa_blind": "mest_bla"})
    assert "Mostly in outlets with a blue audience" in instagram.slide_cover(ev, "d", False, lang="en")


def test_automatisk_markning_pa_engelska():
    html = instagram.slide_cover(handelse(automatisk=True), "d", False, lang="en")
    assert "Published without manual review; corrections are visible." in html


def test_varldskortet_pa_engelska():
    html = instagram.slide_world(handelse(), lang="en")
    assert "How the world sees it" in html and "Headlines from three regions" in html
    assert "US and Canada" in html and "Asia and Oceania" in html and "Europe" in html and "United Kingdom" not in html
    assert not any(s in html for s in SVENSKA)


def test_usa_kortet_pa_engelska():
    ev = handelse()
    ev["utkast"].update({"rubrik_en": "Trump signs spending bill", "rubrik_sv": "Trump skriver under budgeten"})
    ev["perspektiv"]["usa"]["mitten"] = [{"kalla": "AP", "rubrik": "AP headline", "url": "u", "lutning": "mitten"}]    # minst tre medier
    html = instagram.slide_usa(ev, lang="en")
    assert "US: blue and red" in html and "Blue audience" in html and "Red audience" in html and "lean left" in html
    assert "not our own judgement" in html and "Blå publik" not in html


def test_oenighetskortet_pa_engelska_och_saknas_utan_engelsk_text():
    html = instagram.slide_differ(handelse(), lang="en")
    assert "Sources differ" in html and "The death toll varies." in html and "Dödstalet" not in html
    ev = handelse()
    del ev["utkast"]["oenighet_en"]
    assert instagram.slide_differ(ev, lang="en") is None and instagram.slide_differ(ev) is not None


def test_dataKortet_pa_engelska_har_punkt_som_decimaltecken():
    ev = handelse(data=[{"namn_sv": "Styrränta", "namn_en": "Policy rate", "datum": "2026-10-29", "senaste": 3.75, "ar_sedan": 4.25,
                         "decimaler": 2, "enhet": "%", "kalla": "ECB", "spark": [4.0, 3.9, 3.75]}])
    en, sv = instagram.slide_data(ev, lang="en"), instagram.slide_data(ev)
    assert "The data behind the story" in en and "Policy rate" in en and "3.75 %" in en and "A year earlier 4.25 %" in en
    assert "3,75 %" in sv and "Ett år tidigare 4,25 %" in sv


def test_karusellen_pa_engelska():
    sidor = instagram.slides(handelse(), lang="en")
    assert 2 <= len(sidor) <= 3 and all('lang="en"' in s for s in sidor)
    assert all("1 / " not in s or "newsnavigator.se" in s for s in sidor)


# ---------- Caption ----------

def test_caption_pa_engelska_ar_kort_och_sakligt():
    cap = instagram.caption(handelse(), lang="en")
    assert cap.splitlines()[0] == "Train crash in Spain"
    assert "At least 60 dead." in cap and "Sources differ: The death toll varies." in cap
    assert "Sources: BBC, NPR, SCMP" in cap and "/en/n/aaaaaaaaaa/" in cap
    assert "In English:" not in cap and "Källor" not in cap and len(cap) <= 2200


def test_caption_pa_svenska_ar_kort_och_sakligt():
    cap = instagram.caption(handelse())
    assert "Källor: BBC, NPR, SCMP" in cap and "/sv/n/aaaaaaaaaa/" in cap and "In English" not in cap


def test_bildtexten_har_inga_slogans_eller_hashtaggar():
    """Text-tv: kort, tätt och att lita på. Inget trams."""
    for lang in ("sv", "en"):
        cap = instagram.caption(handelse(), lang=lang)
        assert "#" not in cap and "Vi levererar" not in cap and "We deliver" not in cap
        assert "How the world sees it" not in cap and "Så ser världen" not in cap      # perspektiven står på korten och sidan
        assert len([r for r in cap.splitlines() if r.strip()]) <= 6


def test_bildtexten_sager_hur_notisen_granskats():
    assert "granskad av redaktionen" in instagram.caption(handelse())
    assert "reviewed by the editors" in instagram.caption(handelse(), lang="en")


# ---------- Vad varje konto får ----------

def test_kan_byggas_kraver_engelsk_text_for_engelska_kontot():
    ev = handelse()
    assert instagram.kan_byggas(ev, "sv") and instagram.kan_byggas(ev, "en")
    del ev["utkast"]["sammanfattning_en"]
    assert instagram.kan_byggas(ev, "sv") and not instagram.kan_byggas(ev, "en")


# ---------- Tillstånd, bygge och postning per konto ----------

@pytest.fixture
def rot(tmp_path, monkeypatch):
    monkeypatch.setattr(instagram, "OUT", tmp_path / "ig")
    monkeypatch.setattr(instagram, "STATE_DIR", tmp_path / "instagram")
    monkeypatch.setattr(instagram, "LEGACY_STATE", tmp_path / "instagram.json")
    import autopilot
    monkeypatch.setattr(autopilot, "INSTALLNINGAR", tmp_path / "finns-inte.json")
    for k in ("IG_USER_ID", "IG_ACCESS_TOKEN", "IG_USER_ID_EN", "IG_ACCESS_TOKEN_EN"):
        monkeypatch.delenv(k, raising=False)
    return tmp_path


def test_tillstand_ligger_per_konto(rot):
    assert instagram.state_path("sv") == rot / "instagram" / "sv.json" and instagram.state_path("en") == rot / "instagram" / "en.json"
    assert instagram.status_path("en") == rot / "instagram" / "status-en.json"
    instagram.save_state({"a": {"rubrik": "A"}}, "en")
    assert instagram.load_state("en") == {"a": {"rubrik": "A"}} and instagram.load_state("sv") == {}


def test_gamla_tillstandet_blir_svenska_kontots(rot):
    (rot / "instagram.json").write_text(json.dumps({"x": {"rubrik": "Gammal", "postad": 5}}), encoding="utf-8")
    assert instagram.load_state("sv") == {"x": {"rubrik": "Gammal", "postad": 5}} and instagram.load_state("en") == {}


def test_bygg_ger_varje_konto_sitt_urval(rot, monkeypatch):
    svenskt = handelse("s000000001", kallor=[kalla("SVT", "sverige", "SE"), kalla("Ekot", "sverige", "SE"), kalla("DN", "sverige", "SE")])
    svenskt["utkast"].update(rubrik_en="Assault in Uppsala", sammanfattning_en="One arrested.")
    global_ = handelse("g000000001")
    monkeypatch.setattr(instagram, "load_archive", lambda: {"s000000001": svenskt, "g000000001": global_})
    byggda = []

    def fake_render(ev, out_dir, banner="", lang="sv"):
        byggda.append((lang, ev["id"], str(out_dir)))
        return ["1.jpg", "2.jpg"]
    monkeypatch.setattr(instagram, "render", fake_render)
    instagram.bygg()
    assert sorted((l, i) for l, i, _ in byggda) == [("en", "g000000001"), ("sv", "g000000001"), ("sv", "s000000001")]
    assert all(f"/ig/{l}/{i}" in d for l, i, d in byggda)
    assert set(instagram.load_state("en")) == {"g000000001"} and set(instagram.load_state("sv")) == {"g000000001", "s000000001"}
    assert instagram.load_state("en")["g000000001"]["rubrik"] == "Train crash in Spain"
    assert instagram.load_state("sv")["g000000001"]["rubrik"] == "Tågolycka i Spanien"


def test_publicering_hamtar_korten_under_kontots_sprak(rot, monkeypatch):
    anrop = []
    monkeypatch.setattr(instagram, "_api", lambda path, params, method="POST": anrop.append((path, params)) or {"id": "c1", "status_code": "FINISHED"})
    (rot / "ig" / "en" / "abc").mkdir(parents=True)
    (rot / "ig" / "en" / "abc" / "caption.txt").write_text("Cap", encoding="utf-8")
    instagram.publish_one("en", "abc", {"bilder": ["1.jpg", "2.jpg"]}, "ENID", "ENTOKEN")
    bilder = [p["image_url"] for path, p in anrop if "image_url" in p]
    assert bilder == [f"{instagram.IMAGE_BASE}/ig/en/abc/1.jpg", f"{instagram.IMAGE_BASE}/ig/en/abc/2.jpg"]
    assert all(path.startswith("ENID/") or path == "c1" for path, _ in anrop)


def test_posta_anvander_varje_kontos_egna_secrets(rot, monkeypatch):
    nu = time.time()
    instagram.save_state({"a": {"rubrik": "A", "poang": 5, "godkand_tid": nu - 100, "bilder": ["1.jpg"]}}, "sv")
    instagram.save_state({"b": {"rubrik": "B", "poang": 5, "godkand_tid": nu - 100, "bilder": ["1.jpg"]}}, "en")
    monkeypatch.setenv("IG_USER_ID_EN", "ENID")
    monkeypatch.setenv("IG_ACCESS_TOKEN_EN", "ENTOKEN")
    postade = []
    monkeypatch.setattr(instagram, "publish_one", lambda lang, sid, item, user, token: postade.append((lang, sid, user, token)) or "ig1")
    instagram.posta()
    assert postade == [("en", "b", "ENID", "ENTOKEN")]
    assert instagram.load_state("en")["b"]["ig_id"] == "ig1" and "postad" not in instagram.load_state("sv")["a"]
    sv, en = instagram.load_status("sv"), instagram.load_status("en")
    assert sv["secrets"] is False and sv["vantar"] == 1 and en["secrets"] is True and en["vantar"] == 0


def test_posta_ett_konto_for_sig(rot, monkeypatch):
    nu = time.time()
    for lang in ("sv", "en"):
        instagram.save_state({"a": {"rubrik": "A", "poang": 5, "godkand_tid": nu - 100, "bilder": ["1.jpg"]}}, lang)
        monkeypatch.setenv(instagram.KONTON[lang][0], "ID")
        monkeypatch.setenv(instagram.KONTON[lang][1], "TOKEN")
    postade = []
    monkeypatch.setattr(instagram, "publish_one", lambda lang, sid, item, user, token: postade.append(lang) or "ig1")
    instagram.posta(konton=["sv"])
    assert postade == ["sv"]


def test_status_behaller_token_utgar(rot):
    instagram.spara_status("en", token_utgar="2026-12-20")
    instagram.spara_status("en", secrets=True)
    assert instagram.load_status("en") == {"token_utgar": "2026-12-20", "secrets": True}


# ---------- Tonen: en modern global text-tv ----------

UPPMANINGAR = re.compile(r"\b(dela|delar|dela vidare|skicka vidare|tipsa|följ|följ oss|spara|gilla|kommentera|prenumerera|swipe|svep|share|send this|follow|follow us|"
                         r"save this|like|comment|subscribe|tag a friend|link in bio|länk i bion|länken i bion)\b", re.I)


@pytest.mark.parametrize("lang", ["sv", "en"])
def test_inga_uppmaningar_i_kort_eller_bildtext(lang):
    """Positioneringen är en modern global text-tv: rubrik, fakta, källor. Aldrig uppmaningar att dela, följa, spara eller svepa."""
    ev = handelse()
    texter = [instagram.caption(ev, lang=lang)] + [re.sub(r"<[^>]+>", " ", re.sub(r"<style.*?</style>", "", s, flags=re.S)) for s in instagram.slides(ev, lang=lang)]
    for t in texter:
        assert not UPPMANINGAR.search(t), UPPMANINGAR.search(t).group(0)
