"""B3: utvärderingen av berättelserna. Ett ärende med 30 händelser du bockar av (stämmer eller missvisar), och en räkning av hur ofta de stämmer."""
import json

import pytest

import utvardering
from test_berattelser import bygg
from test_lansering import NU, historia


def notis(n, amnen=("varlden",), poang=10.0, med_narrativ=True, ok=True):
    ev = historia(n, poang=poang, amnen=amnen)["ev"]
    ev["utkast"]["rubrik_sv"] = f"Händelse {n}"
    if med_narrativ:
        ev["narrativ"] = bygg()
        ev["narrativ"]["ok"] = ok
    return ev


def test_bara_godkanda_berattelser_utvarderas():
    evs = [notis(1), notis(2, med_narrativ=False), notis(3, ok=False)]
    assert [e["id"] for e in utvardering.valj(evs, 30)] == [f"{1:010d}"]


def test_hogst_n_och_hogsta_poang_forst():
    evs = [notis(n, poang=n) for n in range(1, 41)]
    valda = utvardering.valj(evs, 30, max_andel_sektion=1.0)
    assert len(valda) == 30 and valda[0]["id"] == f"{40:010d}"


def test_sektionstak_ger_spridning_men_fyller_pa():
    evs = [notis(n, amnen=("marknader",), poang=100 - n) for n in range(20)] + [notis(100 + n, amnen=("tech",), poang=1) for n in range(20)]
    valda = utvardering.valj(evs, 30, max_andel_sektion=0.5)
    assert sum(1 for v in valda if v["amnen_sektion"] == ["marknader"]) == 15
    assert len(utvardering.valj(evs[:20], 30, max_andel_sektion=0.5)) == 20      # inget annat finns: taket släpper


def test_arendet_har_markering_en_post_per_handelse_och_tva_rutor():
    kropp = utvardering.kropp(utvardering.valj([notis(1), notis(2)], 30))
    assert utvardering.MARK in kropp
    for n in (1, 2):
        assert f"`stammer:{n:010d}`" in kropp and f"`fel:{n:010d}`" in kropp
    assert "Kostnaden för bönder" in kropp and "[NPR](https://x/1)" in kropp


def test_arendet_aterger_inte_kallornas_text():
    kropp = utvardering.kropp(utvardering.valj([notis(1)], 30))
    assert "NPR headline" not in kropp and "Ingress" not in kropp


def test_arendet_har_inga_tankstreck():
    assert "—" not in utvardering.kropp(utvardering.valj([notis(1)], 30)) and "–" not in utvardering.kropp(utvardering.valj([notis(1)], 30))


def test_rakna_stammer_fel_obedomda_och_dubbelbockat():
    ids = [f"{n:010d}" for n in range(1, 6)]
    kropp = utvardering.kropp(utvardering.valj([notis(n) for n in range(1, 6)], 30))
    for tag, rutor in ((ids[0], "stammer"), (ids[1], "stammer"), (ids[2], "fel"), (ids[3], "stammer"), (ids[3], "fel")):
        kropp = kropp.replace(f"- [ ] ", "- [ ] ", 1)
        rad = next(r for r in kropp.splitlines() if f"`{rutor}:{tag}`" in r)
        kropp = kropp.replace(rad, rad.replace("[ ]", "[x]", 1))
    r = utvardering.rakna(kropp)
    assert {k: v for k, v in r.items() if k != "betydelse"} == {"totalt": 5, "bedomda": 3, "stammer": 2, "fel": 1, "oklara": 1, "obedomda": 1, "andel_stammer": 2 / 3}
    assert r["betydelse"]["totalt"] == 0


def test_rakna_utan_bedomda_ger_ingen_andel():
    r = utvardering.rakna(utvardering.kropp(utvardering.valj([notis(1)], 30)))
    assert r["bedomda"] == 0 and r["andel_stammer"] is None


def test_rekommendation_kraver_30_bedomda_och_80_procent():
    assert "NN_BERATTELSER" not in utvardering.rekommendation({"bedomda": 10, "stammer": 10, "andel_stammer": 1.0})
    assert "NN_BERATTELSER" not in utvardering.rekommendation({"bedomda": 30, "stammer": 20, "andel_stammer": 20 / 30})
    assert "NN_BERATTELSER=1" in utvardering.rekommendation({"bedomda": 30, "stammer": 27, "andel_stammer": 0.9})


def test_skapa_uppdaterar_befintligt_arende_annars_skapar(monkeypatch, tmp_path):
    anrop = []
    monkeypatch.setattr(utvardering, "api", lambda m, p, b=None: anrop.append((m, p)) or ([] if m == "GET" else {"number": 7}))
    monkeypatch.setattr(utvardering, "UT", tmp_path / "ut.json")
    utvardering.skapa([notis(1)])
    assert anrop[-1][0] == "POST"
    anrop.clear()
    monkeypatch.setattr(utvardering, "api", lambda m, p, b=None: anrop.append((m, p)) or ([{"number": 7, "body": utvardering.MARK}] if m == "GET" else {}))
    utvardering.skapa([notis(1)])
    assert anrop[-1] == ("PATCH", "/issues/7")


def test_bedomda_handelser_byts_inte_ut_vid_uppdatering():
    gammal = utvardering.kropp(utvardering.valj([notis(1)], 30))
    gammal = gammal.replace("- [ ] Berättelserna stämmer", "- [x] Berättelserna stämmer", 1)
    ny = utvardering.uppdatera_kropp(gammal, utvardering.valj([notis(2)], 30), 30)       # händelse 1 finns inte längre i flödet
    assert f"`stammer:{1:010d}`" in ny and f"`stammer:{2:010d}`" in ny
    assert utvardering.rakna(ny)["stammer"] == 1 and utvardering.rakna(ny)["totalt"] == 2


def test_workflow():
    import yaml
    from pathlib import Path
    y = yaml.safe_load((Path(__file__).parent.parent / ".github" / "workflows" / "utvardering.yml").read_text(encoding="utf-8"))
    assert set(y[True]["workflow_dispatch"]["inputs"]) >= {"lage"} and "schedule" not in y[True]
    assert y["permissions"]["issues"] == "write" and y["permissions"]["contents"] == "write"


def test_analysraden_far_egna_rutor_och_egen_rakning():
    from test_betydelse import bygg as bygg_bet
    ev = notis(1, med_narrativ=False)
    ev["betydelse"] = bygg_bet()
    kropp = utvardering.kropp(utvardering.valj([ev], 30))
    assert "Analys, Svenska läsaren." in kropp and "Analys, Engelska läsaren." in kropp
    assert f"`bstammer:{ev['id']}`" in kropp and f"`bfel:{ev['id']}`" in kropp and f"`stammer:{ev['id']}`" not in kropp
    rad = next(r for r in kropp.splitlines() if f"`bstammer:{ev['id']}`" in r)
    r = utvardering.rakna(kropp.replace(rad, rad.replace("[ ]", "[x]", 1)))
    assert r["betydelse"]["stammer"] == 1 and r["betydelse"]["andel_stammer"] == 1.0 and r["totalt"] == 0


def test_underkand_analys_utvarderas_inte():
    from test_betydelse import bygg as bygg_bet
    ev = notis(1, med_narrativ=False)
    ev["betydelse"] = bygg_bet()
    ev["betydelse"]["ok"] = False
    assert utvardering.valj([ev], 30) == []
