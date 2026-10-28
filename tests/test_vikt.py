"""Vikt: bredd i förhållande till regionernas källor, uthållighet, konsekvens och golvregeln Måste med.

Kör: python -m pytest tests
"""
import vikt

TOT = {"usa": 49, "europa": 25, "asien": 18, "sverige": 14, "latinamerika": 8, "afrika": 7, "mellanostern": 7, "norden": 4, "global": 7}


def item(src, region, title="Rubrik", typ="media", owner="privat"):
    return {"source_id": src, "source_name": src, "source_type": typ, "owner": owner, "region": region, "title": title}


def kluster(*items, timmar=1):
    return {"items": list(items), "timmar": timmar}


def test_fem_amerikanska_vager_mindre_an_tva_afrikanska():
    usa = kluster(*[item(f"us{i}", "usa") for i in range(5)])
    afr = kluster(item("a1", "afrika"), item("a2", "afrika"))
    assert vikt.bredd(afr, TOT)[0] > vikt.bredd(usa, TOT)[0]


def test_kuraterade_listor_raknas_inte_som_bredd():
    c = kluster(item("techmeme", "usa", typ="kuraterat"), item("bbc", "europa"))
    assert vikt.bredd(c, TOT)[1] == {"europa": 1}


def test_uthallighet_hojer_vikten():
    a = kluster(item("bbc", "europa"), item("svt", "sverige"), timmar=1)
    b = kluster(item("bbc", "europa"), item("svt", "sverige"), timmar=12)
    assert vikt.vikt(b, TOT)[0] > vikt.vikt(a, TOT)[0]


def test_lag_konsekvens_slar_bredd():
    bred = kluster(*[item(f"s{r}", r) for r in TOT], timmar=6)
    smal = kluster(item("bbc", "europa"), item("dw", "europa"), item("svt", "sverige"), item("aj", "mellanostern"), timmar=6)
    noje = {"medel": 1.0}
    krig = {"medel": 4.7}
    assert vikt.vikt(smal, TOT, krig)[0] > vikt.vikt(bred, TOT, noje)[0]


def test_maste_med_kraver_konsekvens():
    c = kluster(*[item(f"s{i}{r}", r) for r in ("usa", "europa", "asien", "afrika", "latinamerika") for i in range(2)])
    assert vikt.vikt(c, TOT, {"medel": 4.0})[1]["maste"]
    assert not vikt.vikt(c, TOT, {"medel": 1.3})[1]["maste"]


def test_historiken_kanner_igen_samma_handelse():
    hist = []
    c1 = {"items": [item("bbc", "europa", title="Machado returns to Venezuela after exile"), item("svt", "sverige", title="Machado tillbaka i Venezuela")]}
    vikt.update_history([c1], hist, now=3600 * 10)
    c2 = {"items": [item("bbc", "europa", title="Machado returns to Venezuela from exile"), item("nrk", "norden", title="Machado tilbake")]}
    vikt.update_history([c2], hist, now=3600 * 11)
    assert c2["timmar"] == 2 and len(hist) == 1
    c3 = {"items": [item("bbc", "europa", title="Earthquake hits Japan coast")]}
    vikt.update_history([c3], hist, now=3600 * 12)
    assert c3["timmar"] == 1 and len(hist) == 2
