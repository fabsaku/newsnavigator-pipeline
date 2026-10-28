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
