"""Fas 1: samma händelse en gång, och samma id när den får nya källor."""
import re

import vikt
from pipeline import cluster, merge_clusters


def art(kalla, rubrik, t):
    return {"id": f"{kalla}-{t}", "source_id": re.sub(r"\W+", "-", kalla.lower()), "source_name": kalla, "source_type": "media",
            "title": rubrik, "description": "", "topics": ["varlden"], "epoch": t, "region": "europa"}


TAG = [
    art("France 24", "Spain: At least 64 dead in high-speed train crash", 100),
    art("BBC", "Watch: At the scene of Spain's deadly train crash", 99),
    art("CNBC", "At least 68 people dead in high-speed Spain train crash", 98),
    art("Dawn", "At least 64 people killed in Spain as two high-speed trains collide", 97),
    art("The Hindu", "At least 68 dead after two trains collide in Spain's Toledo", 96),
    art("Rappler", "At least 64 people killed in Spain as 2 high-speed trains collide", 95),
    art("France 24 b", "Spain: Dozens killed after high-speed train collision", 94),
    art("SR", "Live report on the train accident in Spain", 93),
    art("DR", "Train collision in Spain occurs nine months after another crash", 92),
]
ANDRA = [
    art("Guardian", "Teenager shot dead after knife attack near Israeli embassy in Belgrade", 90),
    art("AP", "Policeman kills knife attacker outside Israeli embassy in Serbia", 89),
    art("Politico", "Israel election: Arab parties projected to win record seats", 88),
    art("Haaretz", "Israel's Arab parties win record number of seats in election", 87),
]


def test_tagolyckan_blir_en_handelse():
    kl = merge_clusters(cluster(TAG + ANDRA))
    med_tag = [c for c in kl if any("train" in i["title"].lower() for i in c["items"])]
    assert len(med_tag) == 1


def test_olika_handelser_i_samma_land_halls_isar():
    kl = merge_clusters(cluster(TAG + ANDRA))
    for c in kl:
        rubriker = " ".join(i["title"].lower() for i in c["items"])
        assert not ("embassy" in rubriker and "election" in rubriker)


def test_samma_handelse_behaller_id_med_ny_kalla():
    hist = []
    forst = {"items": TAG[:4]}
    vikt.update_history([forst], hist, now=3600 * 5)
    forst["_hist"]["id"] = "abc123"
    sen = {"items": TAG[:4] + [art("NPR", "Dozens are dead in a high-speed train crash in Spain", 101)]}
    vikt.update_history([sen], hist, now=3600 * 6)
    assert sen["_hist"]["id"] == "abc123"


def test_tva_handelser_far_aldrig_samma_id():
    """Historiken gav ett kluster id X medan ett annat klusters artikelhash också var X (flödet 28 oktober 21.34)."""
    import pipeline
    a = {"items": [art("A", "x", 1), art("B", "x", 2)], "_hist": {"id": "deadbeef00"}}
    b = {"items": [art("C", "y", 3)]}
    used = set()
    pipeline.assign_id(a, used)
    b_hash = pipeline.assign_id({"items": b["items"]}, set())
    a["_hist"]["id"] = b_hash          # historiken pekar på samma id som b:s hash
    used = set()
    pipeline.assign_id(a, used)
    pipeline.assign_id(b, used)
    assert a["id"] == b_hash and b["id"] != b_hash and len(used) == 2
    assert a["_hist"]["id"] == a["id"]


# ---------- Publicerad händelse känns igen och uppdateras ----------

def kalla(namn, url):
    return {"namn": namn, "rubrik": "Lagarde to step down", "url": url, "betalvagg": False, "typ": "media",
            "land": "XX", "region": "europa", "agare": "privat", "statskontrollerad": False}


def notis(eid, urls, rubrik_en="Lagarde to step down as ECB president", **extra):
    ev = {"id": eid, "reserv_rubrik": rubrik_en, "antal_kallor": len(urls), "poang": 10.0,
          "utkast": {"rubrik_sv": "Lagarde avgår", "rubrik_en": rubrik_en, "sammanfattning_sv": "x", "osaker": False},
          "kallkontroll": {"ok": True, "antal": 1, "problem": []},
          "perspektiv": {"regioner": ["europa"], "per_region": {}, "blind_flack": None, "usa_blind": None},
          "kallor": [kalla(f"k{n}", u) for n, u in enumerate(urls)]}
    ev.update(extra)
    return ev


def test_handelse_med_samma_artiklar_far_arkivets_id():
    import pipeline
    arkiv = {"pub0000001": {**notis("pub0000001", [f"https://x/{n}" for n in range(17)]), "godkand_tid": 1.0}}
    ny = notis("nytt000001", [f"https://x/{n}" for n in range(2, 18)])          # 15 av 17 gemensamma
    annan = notis("annan00001", ["https://x/3", "https://y/1", "https://y/2"], rubrik_en="ECB and Fed hold rates")
    pipeline.match_archive([ny, annan], arkiv)
    assert ny["id"] == "pub0000001" and annan["id"] == "annan00001"


def test_samma_kallor_och_rubrik_racker_utan_samma_artiklar():
    import pipeline
    arkiv = {"pub0000001": {**notis("pub0000001", ["https://a/1", "https://b/1", "https://c/1"]), "godkand_tid": 1.0}}
    ny = notis("nytt000001", ["https://a/2", "https://b/2", "https://c/2"],
               rubrik_en="Lagarde steps down early as ECB president")
    ny["kallor"] = [kalla(k["namn"], k["url"]) for k in ny["kallor"]]
    for k, namn in zip(ny["kallor"], ["k0", "k1", "k2"]):
        k["namn"] = namn
    pipeline.match_archive([ny], arkiv)
    assert ny["id"] == "pub0000001"


def test_tva_handelser_kan_inte_ta_samma_arkivpost():
    import pipeline
    urls = [f"https://x/{n}" for n in range(6)]
    arkiv = {"pub0000001": {**notis("pub0000001", urls), "godkand_tid": 1.0}}
    a = notis("a000000001", urls[:5]); b = notis("b000000001", urls[:4])
    pipeline.match_archive([b, a], arkiv)
    assert {a["id"], b["id"]} == {"pub0000001", "b000000001"}


def test_arkivet_uppdateras_med_nya_kallor_men_behaller_texten(tmp_path, monkeypatch):
    import newsletter
    monkeypatch.setattr(newsletter, "ARKIV", tmp_path / "arkiv.json")
    gammal = notis("pub0000001", ["https://x/1", "https://x/2", "https://x/3"])
    arkiv = newsletter.archive([gammal], {"pub0000001"}, automatic={"pub0000001"})
    godkand = arkiv["pub0000001"]["godkand_tid"]
    ny = notis("pub0000001", ["https://x/1", "https://x/2", "https://x/3", "https://x/4"])
    ny["utkast"] = {**ny["utkast"], "rubrik_sv": "Ny rubrik som ingen granskat"}
    arkiv = newsletter.archive([ny], {"pub0000001"}, automatic={"pub0000001"})
    post = arkiv["pub0000001"]
    assert len(post["kallor"]) == 4 and post["antal_kallor"] == 4
    assert post["utkast"]["rubrik_sv"] == "Lagarde avgår"
    assert post["godkand_tid"] == godkand and post["automatisk"] is True
    assert post["uppdaterad_tid"] >= godkand
    # Oförändrade källor ger ingen uppdateringstid
    arkiv = newsletter.archive([ny], {"pub0000001"})
    assert arkiv["pub0000001"]["uppdaterad_tid"] == post["uppdaterad_tid"]


def test_notissidan_visar_uppdaterad():
    import sajt
    ev = {**notis("pub0000001", ["https://x/1"]), "granskad": True, "godkand_tid": 1_793_000_000.0,
          "uppdaterad_tid": 1_793_010_000.0, "automatisk": False}
    html = sajt.story_page(sajt.Urls(flat=True), ev, [], [], "", True)
    assert "Uppdaterad" in html
