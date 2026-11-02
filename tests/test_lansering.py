"""A3: lanseringen. 56 inlägg per konto ur veckan som gått, en genomgång av hela batchen, och ett maraton som postar i lugn takt.

Säkerheten är huvudsaken: inget postas innan batchen är godkänd, varje inlägg sparas direkt (en omstart kan aldrig ge dubbelpost),
och tyst läge stoppar allt.
"""
import json
from pathlib import Path

import pytest
import yaml

import instagram
import lansering
import newsletter

NU = 1_793_600_000.0
DAG = 86400
WORKFLOWS = Path(__file__).parent.parent / ".github" / "workflows"


def kalla(namn, region="europa"):
    return {"namn": namn, "rubrik": f"{namn} headline", "url": f"https://x/{namn}/{region}", "typ": "media", "land": "XX", "region": region,
            "statskontrollerad": False, "betalvagg": False, "agare": "privat"}


GLOBAL = [kalla("BBC"), kalla("NPR", "usa"), kalla("SCMP", "asien")]


def historia(n, rubrik_en=None, poang=10.0, alder_dagar=1.0, amnen=("varlden",), kallor=None, blind=None, **extra):
    """En berättelse som från flödeshistoriken: händelsen och när den senast sågs."""
    kallor = kallor or [{**k, "url": f"https://x/{n}/{k['namn']}"} for k in GLOBAL]
    rubrik_en = rubrik_en or " ".join(f"w{n:03d}{k}x" for k in range(4))
    ev = {"id": f"{n:010d}", "poang": poang, "antal_kallor": len(kallor), "amnen_sektion": list(amnen), "reserv_rubrik": rubrik_en,
          "kallor": kallor, "senast": None,
          "utkast": {"rubrik_sv": f"Berättelse {n}", "sammanfattning_sv": "Text.", "rubrik_en": rubrik_en, "sammanfattning_en": "Text.", "osaker": False},
          "kallkontroll": {"ok": True, "antal": 2, "problem": []},
          "perspektiv": {"regioner": sorted({k["region"] for k in kallor}), "blind_flack": blind, "usa_blind": None, "per_region": {}}}
    ev.update(extra)
    return {"ev": ev, "senast": NU - alder_dagar * DAG}


# ---------- Urval ----------

def test_valj_ger_hogst_antal_och_sorterar_efter_poang():
    stories = [historia(n, poang=100 - n) for n in range(80)]
    valda = lansering.valj(stories, "en", antal=56, nu=NU)
    assert len(valda) == 56
    assert [v["rank"] for v in valda] == list(range(1, 57))
    assert valda[0]["id"] == f"{0:010d}"


def test_nyare_slar_aldre_vid_lika_poang():
    stories = [historia(1, poang=10, alder_dagar=6), historia(2, poang=10, alder_dagar=0.5)]
    assert [v["id"] for v in lansering.valj(stories, "en", antal=2, nu=NU)] == [f"{2:010d}", f"{1:010d}"]


def test_hogst_tre_per_handelsfamilj():
    delar = [historia(n, rubrik_en=f"Train crash near Toledo Spain leaves dozens dead angle{n}", poang=50) for n in range(6)]
    ovriga = [historia(100 + n, poang=5) for n in range(10)]
    valda = lansering.valj(delar + ovriga, "en", antal=10, nu=NU)
    assert sum(1 for v in valda if int(v["id"]) < 100) == 3 and len(valda) == 10


def test_sektionstak_men_fyller_pa_om_det_behovs():
    ekonomi = [historia(n, poang=90 - n, amnen=("marknader",)) for n in range(30)]
    annat = [historia(100 + n, poang=10 - n * 0.1, amnen=("varlden",)) for n in range(10)]
    valda = lansering.valj(ekonomi + annat, "en", antal=20, nu=NU, max_andel_sektion=0.5)
    assert sum(1 for v in valda if v["sektion"] == "marknader") == 10 and sum(1 for v in valda if v["sektion"] == "varlden") == 10
    kort = lansering.valj(ekonomi, "en", antal=20, nu=NU, max_andel_sektion=0.5)
    assert len(kort) == 20          # inget annat finns: taket släpper


def test_utgavans_regler_galler():
    svenskt = historia(1, kallor=[kalla("SVT", "sverige"), kalla("Ekot", "sverige"), kalla("DN", "sverige")], rubrik_en="Assault in Uppsala")
    blind = historia(2, blind="saknas_i_sverige")
    osaker = historia(3)
    osaker["ev"]["utkast"]["osaker"] = True
    stories = [svenskt, blind, osaker, historia(4)]
    en = {v["id"] for v in lansering.valj(stories, "en", nu=NU)}
    sv = {v["id"] for v in lansering.valj(stories, "sv", nu=NU)}
    assert en == {f"{2:010d}", f"{4:010d}"}                      # inget lokalt svenskt, och blind fläck är inget hinder
    assert sv == {f"{1:010d}", f"{2:010d}", f"{4:010d}"}         # svenskt med, osäkert aldrig
    markerad = next(v for v in lansering.valj(stories, "sv", nu=NU) if v["id"] == f"{2:010d}")
    assert markerad["genomgang"] is True and not any(v["genomgang"] for v in lansering.valj(stories, "en", nu=NU))


def test_engelska_kontot_kraver_engelsk_text():
    s = historia(1)
    del s["ev"]["utkast"]["sammanfattning_en"]
    assert lansering.valj([s], "en", nu=NU) == [] and len(lansering.valj([s], "sv", nu=NU)) == 1


def test_samma_berattelse_flera_ganger_raknas_en_gang():
    a, b = historia(1, poang=10), historia(1, poang=12)
    assert len(lansering.valj([a, b], "en", nu=NU)) == 1


# ---------- Lanseringsfilen och godkännandet ----------

@pytest.fixture
def rot(tmp_path, monkeypatch):
    monkeypatch.setattr(lansering, "DIR", tmp_path / "lansering")
    monkeypatch.setattr(lansering, "PREVIEW", tmp_path / "public" / "lansering")
    monkeypatch.setattr(newsletter, "ARKIV", tmp_path / "arkiv.json")
    monkeypatch.setattr(instagram, "OUT", tmp_path / "public" / "ig")
    monkeypatch.setattr(instagram, "STATE_DIR", tmp_path / "instagram")
    monkeypatch.setattr(instagram, "LEGACY_STATE", tmp_path / "gammal.json")
    import autopilot
    monkeypatch.setattr(autopilot, "INSTALLNINGAR", tmp_path / "autopilot.json")
    for k in ("IG_USER_ID", "IG_ACCESS_TOKEN", "IG_USER_ID_EN", "IG_ACCESS_TOKEN_EN"):
        monkeypatch.delenv(k, raising=False)
    return tmp_path


def fyll(lang, antal=5, godkand=False):
    stories = [historia(n, poang=100 - n) for n in range(antal)]
    valda = lansering.valj(stories, lang, antal=antal, nu=NU)
    lansering.skriv(lang, valda, stories, nu=NU)
    return stories, valda


def test_skriv_ger_en_ogodkand_lista_med_handelserna(rot):
    stories, valda = fyll("en")
    data = lansering.las("en")
    assert data["godkand"] is False and len(data["valda"]) == 5 and data["konto"] == "@news.navigator"
    assert data["valda"][0]["rank"] == 1 and data["valda"][0]["rubrik"].startswith("w0000")
    assert (rot / "lansering" / "en.json").exists()


def test_godkann_arkiverar_med_ursprungligt_datum_och_markerar_inte_som_automatiskt(rot):
    stories, valda = fyll("en")
    lansering.godkann("en", nu=NU + 100)
    data = lansering.las("en")
    assert data["godkand"] is True and data["godkand_tid"] == NU + 100
    arkiv = newsletter.load_archive()
    assert set(arkiv) == {v["id"] for v in valda}
    post = arkiv[valda[0]["id"]]
    assert post["godkand_tid"] == NU - DAG and post["automatisk"] is False and post["granskad"] is True


def test_godkann_kan_utesluta_enskilda_poster(rot):
    stories, valda = fyll("en")
    lansering.godkann("en", uteslut=[2, valda[3]["id"]], nu=NU)
    data = lansering.las("en")
    assert [v["id"] for v in data["valda"]] == [valda[0]["id"], valda[2]["id"], valda[4]["id"]]
    assert [v["rank"] for v in data["valda"]] == [1, 2, 3]
    assert set(newsletter.load_archive()) == {v["id"] for v in data["valda"]}


def test_nytt_urval_nollstaller_godkannandet(rot):
    fyll("en")
    lansering.godkann("en", nu=NU)
    fyll("en")
    assert lansering.las("en")["godkand"] is False


def test_skyddade_kort_rensas_inte_av_bygget(rot, monkeypatch):
    stories, valda = fyll("en")
    kort = rot / "public" / "ig" / "en" / valda[0]["id"]
    kort.mkdir(parents=True)
    (kort / "1.jpg").write_bytes(b"x")
    assert lansering.skyddade("en") == {v["id"] for v in valda}
    monkeypatch.setattr(instagram, "load_archive", lambda: {})
    instagram.bygg(["en"])
    assert kort.exists()


# ---------- Förhandsgranskningen ----------

def test_forhandsgranskning_visar_alla_med_markering(rot):
    stories = [historia(n, poang=100 - n, blind="saknas_i_sverige" if n == 1 else None) for n in range(3)]
    valda = lansering.valj(stories, "sv", antal=3, nu=NU)
    lansering.skriv("sv", valda, stories, nu=NU)
    html = (rot / "public" / "lansering" / "sv.html").read_text(encoding="utf-8")
    assert 'name="robots" content="noindex' in html and html.count('class="post"') == 3
    assert "Berättelse 0" in html and "../ig/sv/0000000000/1.jpg" in html and "@newsnavigator.se" in html
    assert html.count("Kräver din genomgång") == 1 and "Saknas i svenska medier" in html


# ---------- Maraton ----------

class Maraton:
    """Allt maratonet rör utifrån, utbytt mot rena funktioner."""
    def __init__(self, tyst=False, kvot=100, fel_pa=(), bild_finns=True):
        self.postat, self.sov, self.sparat, self.tyst, self.kvot_kvar = [], [], [], tyst, kvot
        self.fel_pa, self.bild = set(fel_pa), bild_finns
        self.klocka = NU

    def kw(self):
        def publicera(lang, post, user, token):
            if post["id"] in self.fel_pa:
                raise RuntimeError("Instagram nekade")
            self.postat.append((lang, post["id"], user, token))
            return f"ig_{post['id']}"
        return dict(publicera=publicera, sov=lambda s: self.sov.append(s) or setattr(self, "klocka", self.klocka + s),
                    sparat=lambda lang: self.sparat.append(lang), tyst=lambda: self.tyst, kvot=lambda user, token: self.kvot_kvar,
                    bild_finns=lambda url: self.bild, nu=lambda: self.klocka)


def godkand_lista(rot, antal=5, lang="en", monkeypatch=None):
    fyll(lang, antal)
    lansering.godkann(lang, nu=NU)


def secrets(monkeypatch, lang="en"):
    u, t = instagram.KONTON[lang]
    monkeypatch.setenv(u, "ID")
    monkeypatch.setenv(t, "TOKEN")


def test_maraton_vagrar_ogodkand_batch(rot, monkeypatch):
    fyll("en")
    secrets(monkeypatch)
    with pytest.raises(lansering.EjGodkand):
        lansering.maraton("en", antal=2, **Maraton().kw())


def test_maraton_postar_i_rangordning_med_paus_mellan_inlagg(rot, monkeypatch):
    godkand_lista(rot)
    secrets(monkeypatch)
    m = Maraton()
    ut = lansering.maraton("en", antal=3, intervall=8, **m.kw())
    ids = [f"{n:010d}" for n in range(3)]
    assert [p[1] for p in m.postat] == ids and all(p[2:] == ("ID", "TOKEN") for p in m.postat)
    assert m.sov == [480, 480]                                      # pausar mellan inläggen, inte efter det sista
    assert ut["postade"] == 3 and ut["kvar"] == 2 and ut["stopp"] is None
    assert lansering.status("en")["postade"][ids[0]]["ig_id"] == f"ig_{ids[0]}"
    assert len(m.sparat) == 3                                       # sparas efter varje inlägg


def test_maraton_fortsatter_dar_det_slutade_och_postar_aldrig_samma_igen(rot, monkeypatch):
    godkand_lista(rot)
    secrets(monkeypatch)
    lansering.maraton("en", antal=2, **Maraton().kw())
    m = Maraton()
    ut = lansering.maraton("en", antal=10, **m.kw())
    assert [p[1] for p in m.postat] == [f"{n:010d}" for n in (2, 3, 4)] and ut["kvar"] == 0 and ut["stopp"] == "klart"


def test_tyst_lage_ar_nodstopp(rot, monkeypatch):
    godkand_lista(rot)
    secrets(monkeypatch)
    m = Maraton(tyst=True)
    ut = lansering.maraton("en", antal=3, **m.kw())
    assert m.postat == [] and ut["stopp"] == "tyst läge" and ut["kvar"] == 5


def test_maraton_stannar_nar_tyst_laget_slas_pa_mitt_i(rot, monkeypatch):
    godkand_lista(rot)
    secrets(monkeypatch)
    m = Maraton()
    kw = m.kw()
    ursprunglig = kw["publicera"]
    kw["publicera"] = lambda *a: (ursprunglig(*a), setattr(m, "tyst", True))[0]
    ut = lansering.maraton("en", antal=5, **kw)
    assert len(m.postat) == 1 and ut["stopp"] == "tyst läge"


def test_tre_fel_i_rad_stoppar(rot, monkeypatch):
    godkand_lista(rot, antal=6)
    secrets(monkeypatch)
    m = Maraton(fel_pa={f"{n:010d}" for n in range(0, 3)})
    ut = lansering.maraton("en", antal=6, **m.kw())
    assert m.postat == [] and ut["stopp"] == "tre fel i rad" and ut["postade"] == 0
    assert lansering.status("en")["fel"][-1]["id"] == f"{2:010d}"


def test_ett_fel_hoppas_over_och_forsoks_igen_senare(rot, monkeypatch):
    godkand_lista(rot)
    secrets(monkeypatch)
    m = Maraton(fel_pa={f"{1:010d}"})
    ut = lansering.maraton("en", antal=5, **m.kw())
    assert [p[1] for p in m.postat] == [f"{n:010d}" for n in (0, 2, 3, 4)] and ut["kvar"] == 1
    m2 = Maraton()
    lansering.maraton("en", antal=5, **m2.kw())
    assert [p[1] for p in m2.postat] == [f"{1:010d}"]


def test_kvoten_stoppar_innan_instagram_gor_det(rot, monkeypatch):
    godkand_lista(rot)
    secrets(monkeypatch)
    m = Maraton(kvot=2)
    ut = lansering.maraton("en", antal=5, **m.kw())
    assert m.postat == [] and ut["stopp"] == "kvoten nästan slut"


def test_saknade_secrets_postar_inget(rot):
    godkand_lista(rot)
    m = Maraton()
    ut = lansering.maraton("en", antal=3, **m.kw())
    assert m.postat == [] and ut["stopp"] == "secrets saknas"


def test_bilder_som_inte_finns_an_vantas_in_och_ger_till_slut_stopp(rot, monkeypatch):
    godkand_lista(rot)
    secrets(monkeypatch)
    m = Maraton(bild_finns=False)
    ut = lansering.maraton("en", antal=2, **m.kw())
    assert m.postat == [] and ut["stopp"] == "korten finns inte på sajten"


def test_torrt_lage_postar_inget_och_sparar_inget(rot, monkeypatch):
    godkand_lista(rot)
    secrets(monkeypatch)
    m = Maraton()
    ut = lansering.maraton("en", antal=3, torrt=True, **m.kw())
    assert m.postat == [] and m.sov == [] and ut["skulle_posta"] == [f"{n:010d}" for n in range(3)]
    assert lansering.status("en") == {"postade": {}, "fel": []}


def test_tidsbudget_delar_upp_maratonet_i_omgangar(rot, monkeypatch):
    godkand_lista(rot, antal=10)
    secrets(monkeypatch)
    m = Maraton()
    ut = lansering.maraton("en", antal=10, intervall=8, budget_minuter=30, **m.kw())
    assert len(m.postat) == 4 and ut["stopp"] == "tidsbudgeten" and ut["kvar"] == 6      # 0, 8, 16, 24 minuter


def test_kontona_har_varsin_lista_och_status(rot, monkeypatch):
    godkand_lista(rot, lang="en")
    godkand_lista(rot, lang="sv")
    secrets(monkeypatch, "sv")
    secrets(monkeypatch, "en")
    m = Maraton()
    lansering.maraton("sv", antal=1, **m.kw())
    assert [p[0] for p in m.postat] == ["sv"] and lansering.status("en")["postade"] == {} and len(lansering.status("sv")["postade"]) == 1


# ---------- Workflowen ----------

def test_lansering_workflow():
    text = (WORKFLOWS / "lansering.yml").read_text(encoding="utf-8")
    y = yaml.safe_load(text)
    inputs = y[True]["workflow_dispatch"]["inputs"]
    assert set(inputs) >= {"lage", "konto", "antal", "intervall", "torrt", "uteslut"}
    assert "schedule" not in y[True], "lanseringen startas bara av dig"
    assert y["concurrency"]["group"].startswith("lansering") and y["concurrency"]["cancel-in-progress"] is False
    assert y["permissions"]["actions"] == "write" and y["permissions"]["contents"] == "write"
    for namn in ("IG_USER_ID", "IG_ACCESS_TOKEN", "IG_USER_ID_EN", "IG_ACCESS_TOKEN_EN"):
        assert f"{namn}: ${{{{ secrets.{namn} }}}}" in text
    assert "fetch-depth: 0" in text and "python lansering.py" in text and "refs/heads/sajt" in text
    assert "workflow_dispatch" in text and "-X theirs" in text
    assert "timeout-minutes: 360" in text or "timeout-minutes: 350" in text
