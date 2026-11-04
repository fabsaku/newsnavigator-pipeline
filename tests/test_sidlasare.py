"""Läsaren för källor utan flöde: en sidas rubriklista blir ett flöde. Bara rubrik och länk, robots.txt först, datum är när länken först sågs."""
import time
from pathlib import Path

import pytest

import pipeline
import sidlasare

SIDA = Path(__file__).parent / "sida-nyheter.html"
BAS = "https://www.exempel.se/nyheter/"
MONSTER = r"^/(nyheter|pressrum)/\d{4}/"


@pytest.fixture(autouse=True)
def tillstand(tmp_path, monkeypatch):
    monkeypatch.setattr(sidlasare, "STATE", tmp_path / "sidor.json")
    monkeypatch.setattr(sidlasare, "_state", None)
    sidlasare._sedda.clear()
    sidlasare.nollstall_robots()
    return tmp_path


def kalla(**kw):
    return {"id": "fi", "namn": "Exempelmyndigheten", "url": f"file:{SIDA.relative_to(Path(__file__).parent.parent)}", "hamtning": "sida",
            "lankar": MONSTER, "bas": BAS, "sprak": "sv", "typ": "primar", "land": "SE", "region": "sverige", **kw}


# ---------- Tolkningen av sidan ----------

def test_rubriker_och_lankar_ur_en_sida():
    lank = sidlasare.lankar(SIDA.read_text(encoding="utf-8"), BAS, MONSTER)
    assert lank == [
        ("Riksbanken håller styrräntan oförändrad på 1,75 procent", "https://www.exempel.se/nyheter/2026/11/riksbanken-haller-styrrantan/"),
        ("Ny tillsynsrapport visar brister hos bankerna", "https://www.exempel.se/nyheter/2026/11/ny-tillsynsrapport/"),
        ("Gammalt beslut om kapitalkrav för försäkringsbolag", "https://www.exempel.se/nyheter/2026/10/gammalt-beslut/"),
        ("Pressmeddelande om tillstånd för nytt betalinstitut", "https://www.exempel.se/pressrum/2026/11/pressmeddelande-om-tillstand/"),
        ("Voxtral 3", "https://www.exempel.se/nyheter/2026/11/kort-med-rubrikelement/"),
        ("Bolag Mistral öppnar ett tyskt nav i München för industriell AI 6 oktober 2026", "https://www.exempel.se/nyheter/2026/11/kort-utan-rubrikelement-men-med-lang-text-och-datum/"),
        ("Nyhet vars sökväg inte slutar med snedstreck alls", "https://www.exempel.se/nyheter/2026/11/sist-i-listan-utan-snedstreck-i-monstret")]


def test_navigering_korta_texter_bildlankar_andra_sajter_och_skript_utesluts():
    titlar = " ".join(t for t, _ in sidlasare.lankar(SIDA.read_text(encoding="utf-8"), BAS, MONSTER))
    for fel in ("Om oss", "Alla nyheter", "Till toppen", "Kort", "reklam", "Skript", "pressavdelningen"):
        assert fel not in titlar


def test_samma_lank_tas_en_gang_med_den_langsta_rubriken():
    lank = sidlasare.lankar(SIDA.read_text(encoding="utf-8"), BAS, MONSTER)
    assert sum(1 for _, u in lank if u.endswith("riksbanken-haller-styrrantan/")) == 1
    assert lank[0][0].endswith("oförändrad på 1,75 procent")


def test_max_antal_begransar():
    assert len(sidlasare.lankar(SIDA.read_text(encoding="utf-8"), BAS, MONSTER, max_antal=2)) == 2


def test_utan_monster_tas_inget_med():
    assert sidlasare.lankar(SIDA.read_text(encoding="utf-8"), BAS, None) == []


# ---------- Datum: när länken först sågs ----------

def test_forsta_korningen_markerar_det_som_star_pa_sidan_som_gammalt():
    feed, _, fel = sidlasare.som_flode(kalla(), nu=1_000_000.0)
    assert fel is None and len(feed.entries) == 7
    assert all(time.mktime(e["published_parsed"]) < 1_000_000.0 - 86400 for e in feed.entries)


def test_ny_lank_far_tiden_den_sags_och_gamla_behaller_sin():
    s = kalla()
    sidlasare.som_flode(s, nu=1_000_000.0)
    del sidlasare._state["fi"]["lankar"]["https://www.exempel.se/nyheter/2026/11/ny-tillsynsrapport/"]       # som om länken dök upp efteråt
    feed, _, _ = sidlasare.som_flode(s, nu=1_003_600.0)
    ny = next(e for e in feed.entries if e["link"].endswith("ny-tillsynsrapport/"))
    gammal = next(e for e in feed.entries if e["link"].endswith("gammalt-beslut/"))
    assert abs(time.mktime(ny["published_parsed"]) - 1_003_600.0) < 86400            # sedd nu
    assert time.mktime(gammal["published_parsed"]) < 1_000_000.0 - 86400            # stod där från början


def test_tillstandet_sparas_och_rensas_pa_gamla_lankar():
    s = kalla()
    sidlasare.som_flode(s, nu=1_000_000.0)
    sidlasare._state["fi"]["lankar"]["https://gammal.se/borta"] = 1_000_000.0 - 40 * 86400
    sidlasare.spara(nu=1_000_000.0)
    sidlasare._state = None
    sidlasare.som_flode(s, nu=1_000_100.0)
    assert "https://gammal.se/borta" not in sidlasare._state["fi"]["lankar"]


# ---------- Respekt för utgivaren ----------

class Hamtningar:
    def __init__(self, robots, html=None):
        self.robots, self.html, self.anrop = robots, html, []

    def robots_txt(self, url):
        self.anrop.append("robots")
        return self.robots

    def sida(self, url):
        self.anrop.append("sida")
        return self.html


def http_kalla():
    return kalla(url="https://www.exempel.se/nyheter/")


def test_robots_som_blockerar_boten_ger_ingen_hamtning(monkeypatch):
    h = Hamtningar(("User-agent: *\nDisallow: /nyheter/\n", None), SIDA.read_text(encoding="utf-8"))
    monkeypatch.setattr(sidlasare, "_robots", h.robots_txt)
    monkeypatch.setattr(sidlasare, "_sida", h.sida)
    feed, used, fel = sidlasare.som_flode(http_kalla(), nu=1.0)
    assert feed is None and "robots.txt" in fel and h.anrop == ["robots"]


def test_robots_som_inte_gar_att_lasa_ger_ingen_hamtning(monkeypatch):
    h = Hamtningar((None, "HTTP 500"), SIDA.read_text(encoding="utf-8"))
    monkeypatch.setattr(sidlasare, "_robots", h.robots_txt)
    monkeypatch.setattr(sidlasare, "_sida", h.sida)
    feed, _, fel = sidlasare.som_flode(http_kalla(), nu=1.0)
    assert feed is None and "robots.txt" in fel and h.anrop == ["robots"]


def test_tillatet_hamtar_sidan(monkeypatch):
    h = Hamtningar(("User-agent: *\nAllow: /\n", None), SIDA.read_text(encoding="utf-8"))
    monkeypatch.setattr(sidlasare, "_robots", h.robots_txt)
    monkeypatch.setattr(sidlasare, "_sida", h.sida)
    feed, _, fel = sidlasare.som_flode(http_kalla(), nu=1.0)
    assert fel is None and len(feed.entries) == 7 and h.anrop == ["robots", "sida"]


def test_robots_hamtas_en_gang_per_utgivare_och_korning(monkeypatch):
    h = Hamtningar(("User-agent: *\nAllow: /\n", None), SIDA.read_text(encoding="utf-8"))
    monkeypatch.setattr(sidlasare, "_robots", h.robots_txt)
    monkeypatch.setattr(sidlasare, "_sida", h.sida)
    sidlasare.nollstall_robots()
    sidlasare.som_flode(http_kalla(), nu=1.0)
    sidlasare.som_flode({**http_kalla(), "id": "fi2"}, nu=1.0)
    assert h.anrop.count("robots") == 1


def test_sidan_utan_traffar_ger_fel_inte_tomt():
    feed, _, fel = sidlasare.som_flode(kalla(lankar=r"^/finns-inte/"), nu=1.0)
    assert feed is None and "inga rubriker" in fel


# ---------- I pipelinen ----------

def test_fetch_one_skickar_sidkallor_till_lasaren():
    feed, used, fel = pipeline.fetch_one(kalla())
    assert fel is None and feed.entries[0]["title"] and feed.entries[0]["link"].startswith("https://www.exempel.se/")


def test_fetch_ger_artiklar_med_bara_rubrik_och_lank(monkeypatch):
    items, rapport = pipeline.fetch([kalla()], max_age_hours=0)
    assert rapport[0]["ok"] and rapport[0]["artiklar"] == 7
    assert {i["description"] for i in items} == {""} and all(i["url"].startswith("https://") for i in items)
    assert items[0]["source_id"] == "fi" and items[0]["source_type"] == "primar"


def test_gamla_lankar_pa_forsta_korningen_blir_inga_artiklar():
    items, rapport = pipeline.fetch([kalla()], max_age_hours=36)
    assert rapport[0]["ok"] and items == []


# ---------- Provläget och tillståndet i pipelinen ----------

def test_oversikt_visar_vilka_sokvagar_sidan_har_for_att_valja_monster():
    o = sidlasare.oversikt(SIDA.read_text(encoding="utf-8"), BAS)
    assert o["/nyheter/2026"] == 6 and o["/pressrum/2026"] == 1
    assert "/om-oss" not in o                       # för korta rubriker räknas inte


def test_prova_sida_skriver_rubriker_och_robotsbesked(monkeypatch, capsys):
    import kallprov
    h = Hamtningar(("User-agent: *\nAllow: /\n", None), SIDA.read_text(encoding="utf-8"))
    monkeypatch.setattr(sidlasare, "_robots", h.robots_txt)
    monkeypatch.setattr(sidlasare, "_sida", h.sida)
    kallprov.prova_sida("https://www.exempel.se/nyheter/", MONSTER)
    ut = capsys.readouterr().out
    assert "tillåter NewsnavigatorBot" in ut and "7 rubriker" in ut and "Riksbanken håller styrräntan" in ut and "/nyheter/2026" in ut


def test_prova_sida_hamtar_inget_nar_robots_nekar(monkeypatch, capsys):
    import kallprov
    h = Hamtningar(("User-agent: *\nDisallow: /\n", None), SIDA.read_text(encoding="utf-8"))
    monkeypatch.setattr(sidlasare, "_robots", h.robots_txt)
    monkeypatch.setattr(sidlasare, "_sida", h.sida)
    kallprov.prova_sida("https://www.exempel.se/nyheter/", MONSTER)
    assert "sida" not in h.anrop and "tillåter inte" in capsys.readouterr().out


def test_spara_skriver_ingen_fil_utan_tillstand(tillstand):
    sidlasare.spara()
    assert not sidlasare.STATE.exists()


def test_pipelinen_sparar_tillstandet_efter_hamtningen():
    import inspect
    main = inspect.getsource(pipeline.main)
    assert "sidlasare.spara(" in main and main.index("fetch(sources") < main.index("sidlasare.spara(")


def test_rubrikelementet_i_kortet_ar_rubriken_och_ingress_och_datum_far_vara_kvar_i_texten():
    lank = dict((u.rsplit("/", 2)[-2], t) for t, u in sidlasare.lankar(SIDA.read_text(encoding="utf-8"), BAS, MONSTER))
    assert lank["kort-med-rubrikelement"] == "Voxtral 3"
    assert "Bygg agenter" not in lank["kort-med-rubrikelement"] and "augusti" not in lank["kort-med-rubrikelement"]


def test_text_i_intilliggande_element_skiljs_at_med_mellanslag():
    lank = dict(sidlasare.lankar('<a href="/nyheter/2026/a/"><span>Bolag</span>Mistral öppnar ett nav</a>', BAS, MONSTER))
    assert "BolagMistral" not in " ".join(lank) and "Bolag Mistral öppnar ett nav" in " ".join(lank)


def test_monstret_gar_att_skriva_utan_avslutande_snedstreck():
    html = '<a href="/elbilar/en-ganska-lang-rubrik-om-elbilar-i-sverige/">Kort bildtext som är över tjugo tecken</a>'
    assert sidlasare.lankar(html, "https://www.exempel.se/", r"^/[a-z-]+/[a-z0-9-]{25,}$")


@pytest.mark.parametrize("text,rubrik", [
    ("October 7, 2026Coming Soon: 2026 Annual Meetings Curtain Raiser", "Coming Soon: 2026 Annual Meetings Curtain Raiser"),
    ("September 30, 2026 IMF Executive Board Completes the Third Review", "IMF Executive Board Completes the Third Review"),
    ("6 oktober 2026 Riksbanken sänker räntan med en kvarts procentenhet", "Riksbanken sänker räntan med en kvarts procentenhet"),
    ("2026-11-03 FI publicerar ny vägledning om ESG-data och AI", "FI publicerar ny vägledning om ESG-data och AI"),
    ("Nepal Stabilizes Its Economy and Sets Its Sights Higher", "Nepal Stabilizes Its Economy and Sets Its Sights Higher"),
])
def test_datum_forst_i_rubriken_tas_bort(text, rubrik):
    lank = sidlasare.lankar(f'<a href="/nyheter/2026/a/">{text}</a>', BAS, MONSTER)
    assert lank == [(rubrik, "https://www.exempel.se/nyheter/2026/a/")]


# ---------- Källstatus: en nyss tillagd sidkälla är inte tyst ----------

def test_fro_ar_inte_tystnad_kallstatus_raknar_fran_att_vi_borjade_lasa():
    import calendar
    import verify_feeds
    rad = verify_feeds.kallstatus([kalla()], nu=1_000_100.0)["kallor"][0]
    assert rad["status"] == "ok" and rad["artiklar"] == 7 and rad["senaste"] is not None and not rad["senaste"].startswith("1970")


def test_sidkalla_utan_nya_lankar_blir_tyst_forst_efter_tystnadsgransen():
    import verify_feeds
    s = kalla()
    sidlasare.som_flode(s, nu=1_000_000.0)                # börjar läsas
    sent = 1_000_000.0 + (verify_feeds.TYST_DAGAR + 1) * 86400
    assert verify_feeds.kallstatus([s], nu=1_000_000.0 + 3600)["kallor"][0]["status"] == "ok"
    assert verify_feeds.kallstatus([s], nu=sent)["kallor"][0]["status"] == "tyst"


def test_ny_lank_nollstaller_tystnaden():
    import verify_feeds
    s = kalla()
    sidlasare.som_flode(s, nu=1_000_000.0)
    sent = 1_000_000.0 + (verify_feeds.TYST_DAGAR + 5) * 86400
    del sidlasare._state["fi"]["lankar"]["https://www.exempel.se/nyheter/2026/11/ny-tillsynsrapport/"]
    assert verify_feeds.kallstatus([s], nu=sent)["kallor"][0]["status"] == "ok"      # ny länk sedd precis nu


def test_gammalt_tillstandsformat_flyttas_over():
    sidlasare.STATE.write_text('{"fi": {"https://www.exempel.se/nyheter/2026/10/gammalt-beslut/": 0.0}}', encoding="utf-8")
    sidlasare._state = None
    state = sidlasare._las_state()
    assert "lankar" in state["fi"] and state["fi"]["lankar"]["https://www.exempel.se/nyheter/2026/10/gammalt-beslut/"] == 0.0 and state["fi"]["start"] > 0


# ---------- Utesluten källa ----------

def test_spara_tar_bort_tillstandet_for_kallor_som_inte_langre_finns():
    sidlasare.som_flode(kalla(), nu=1_000_000.0)
    sidlasare.som_flode(kalla(id="nyteknik"), nu=1_000_000.0)
    sidlasare.spara(nu=1_000_000.0, aktiva={"fi"})
    assert set(sidlasare._state) == {"fi"} and set(__import__("json").loads(sidlasare.STATE.read_text())) == {"fi"}


def test_pipelinen_ger_spara_de_aktiva_sidkallorna():
    import inspect
    assert "aktiva=" in inspect.getsource(pipeline.main)


# ---------- Sidor som ritas med JavaScript ----------

def test_rendera_hamtar_sidan_med_webblasare_i_stallet_for_vanlig_hamtning(monkeypatch):
    h = Hamtningar(("User-agent: *\nAllow: /\n", None), "<html></html>")
    rendrad = []
    monkeypatch.setattr(sidlasare, "_robots", h.robots_txt)
    monkeypatch.setattr(sidlasare, "_sida", h.sida)
    monkeypatch.setattr(sidlasare, "_rendera", lambda url: rendrad.append(url) or SIDA.read_text(encoding="utf-8"))
    feed, _, fel = sidlasare.som_flode({**http_kalla(), "rendera": True}, nu=1.0)
    assert fel is None and len(feed.entries) == 7 and rendrad == ["https://www.exempel.se/nyheter/"] and h.anrop == ["robots"]


def test_rendera_kontrollerar_robots_txt_forst(monkeypatch):
    h = Hamtningar(("User-agent: *\nDisallow: /\n", None))
    rendrad = []
    monkeypatch.setattr(sidlasare, "_robots", h.robots_txt)
    monkeypatch.setattr(sidlasare, "_rendera", lambda url: rendrad.append(url) or "")
    feed, _, fel = sidlasare.som_flode({**http_kalla(), "rendera": True}, nu=1.0)
    assert feed is None and "robots.txt" in fel and rendrad == []


def test_utan_rendera_anvands_vanlig_hamtning(monkeypatch):
    h = Hamtningar(("User-agent: *\nAllow: /\n", None), SIDA.read_text(encoding="utf-8"))
    monkeypatch.setattr(sidlasare, "_robots", h.robots_txt)
    monkeypatch.setattr(sidlasare, "_sida", h.sida)
    monkeypatch.setattr(sidlasare, "_rendera", lambda url: pytest.fail("ska inte renderas"))
    feed, _, fel = sidlasare.som_flode(http_kalla(), nu=1.0)
    assert fel is None and h.anrop == ["robots", "sida"]


def test_rendera_utan_webblasare_ger_fel_inte_krasch(monkeypatch):
    h = Hamtningar(("User-agent: *\nAllow: /\n", None))
    monkeypatch.setattr(sidlasare, "_robots", h.robots_txt)
    def saknas(url):
        raise ImportError("playwright saknas")
    monkeypatch.setattr(sidlasare, "_rendera", saknas)
    feed, _, fel = sidlasare.som_flode({**http_kalla(), "rendera": True}, nu=1.0)
    assert feed is None and "playwright" in fel


def test_prova_sida_med_rendera(monkeypatch, capsys):
    import kallprov
    h = Hamtningar(("User-agent: *\nAllow: /\n", None))
    monkeypatch.setattr(sidlasare, "_robots", h.robots_txt)
    monkeypatch.setattr(sidlasare, "_sida", lambda u: pytest.fail("ska renderas"))
    monkeypatch.setattr(sidlasare, "_rendera", lambda u: SIDA.read_text(encoding="utf-8"))
    kallprov.prova_sida("https://www.exempel.se/nyheter/", MONSTER, rendera=True)
    ut = capsys.readouterr().out
    assert "renderar med webbläsare" in ut and "7 rubriker" in ut
