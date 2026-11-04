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
        ("Pressmeddelande om tillstånd för nytt betalinstitut", "https://www.exempel.se/pressrum/2026/11/pressmeddelande-om-tillstand/")]


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
    assert fel is None and len(feed.entries) == 4
    assert all(time.mktime(e["published_parsed"]) < 1_000_000.0 - 86400 for e in feed.entries)


def test_ny_lank_far_tiden_den_sags_och_gamla_behaller_sin():
    s = kalla()
    sidlasare.som_flode(s, nu=1_000_000.0)
    del sidlasare._state["fi"]["https://www.exempel.se/nyheter/2026/11/ny-tillsynsrapport/"]       # som om länken dök upp efteråt
    feed, _, _ = sidlasare.som_flode(s, nu=1_003_600.0)
    ny = next(e for e in feed.entries if e["link"].endswith("ny-tillsynsrapport/"))
    gammal = next(e for e in feed.entries if e["link"].endswith("gammalt-beslut/"))
    assert abs(time.mktime(ny["published_parsed"]) - 1_003_600.0) < 86400            # sedd nu
    assert time.mktime(gammal["published_parsed"]) < 1_000_000.0 - 86400            # stod där från början


def test_tillstandet_sparas_och_rensas_pa_gamla_lankar():
    s = kalla()
    sidlasare.som_flode(s, nu=1_000_000.0)
    sidlasare._state["fi"]["https://gammal.se/borta"] = 1_000_000.0 - 40 * 86400
    sidlasare.spara(nu=1_000_000.0)
    sidlasare._state = None
    sidlasare.som_flode(s, nu=1_000_100.0)
    assert "https://gammal.se/borta" not in sidlasare._state["fi"]


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
    assert fel is None and len(feed.entries) == 4 and h.anrop == ["robots", "sida"]


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
    assert rapport[0]["ok"] and rapport[0]["artiklar"] == 4
    assert {i["description"] for i in items} == {""} and all(i["url"].startswith("https://") for i in items)
    assert items[0]["source_id"] == "fi" and items[0]["source_type"] == "primar"


def test_gamla_lankar_pa_forsta_korningen_blir_inga_artiklar():
    items, rapport = pipeline.fetch([kalla()], max_age_hours=36)
    assert rapport[0]["ok"] and items == []


# ---------- Provläget och tillståndet i pipelinen ----------

def test_oversikt_visar_vilka_sokvagar_sidan_har_for_att_valja_monster():
    o = sidlasare.oversikt(SIDA.read_text(encoding="utf-8"), BAS)
    assert o["/nyheter/2026"] == 3 and o["/pressrum/2026"] == 1
    assert "/om-oss" not in o                       # för korta rubriker räknas inte


def test_prova_sida_skriver_rubriker_och_robotsbesked(monkeypatch, capsys):
    import kallprov
    h = Hamtningar(("User-agent: *\nAllow: /\n", None), SIDA.read_text(encoding="utf-8"))
    monkeypatch.setattr(sidlasare, "_robots", h.robots_txt)
    monkeypatch.setattr(sidlasare, "_sida", h.sida)
    kallprov.prova_sida("https://www.exempel.se/nyheter/", MONSTER)
    ut = capsys.readouterr().out
    assert "tillåter NewsnavigatorBot" in ut and "4 rubriker" in ut and "Riksbanken håller styrräntan" in ut and "/nyheter/2026" in ut


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
    assert "sidlasare.spara()" in main and main.index("fetch(sources") < main.index("sidlasare.spara()")
