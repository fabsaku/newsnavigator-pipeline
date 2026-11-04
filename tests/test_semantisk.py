"""Hybridklustringen: ett andra varv som slår ihop kluster som reglerna delat upp, när en flerspråkig inbäddning och gemensamma ord båda säger
att rubrikerna handlar om samma sak. Reglerna behåller sista ordet om vad som får slås ihop (en källa en gång, högst tre sektioner)."""
import re

import pytest

import pipeline
import semantisk


def art(kalla, rubrik, epoch, typ="media", **extra):
    a = {"source_id": re.sub(r"\W+", "-", kalla.lower()).strip("-"), "source_name": kalla, "source_type": typ, "title": rubrik, "description": "",
         "topics": [], "epoch": epoch}
    a.update(extra)
    return a


def klustra(items):
    return pipeline.merge_clusters(pipeline.cluster(items))


def riktning(vinkel_grader):
    import math
    r = math.radians(vinkel_grader)
    return [math.cos(r), math.sin(r)]


def kodare_fran(tabell):
    """Falsk kodare: rubriken -> vektor ur en tabell (grader i planet; små vinklar är lika)."""
    return lambda texter: [riktning(tabell[t]) for t in texter]


VALET = [("Källa A", "Democrats win control of Congress in midterm elections", 0), ("Källa B", "Democrats take both chambers of Congress, projections show", 5),
         ("Källa C", "Demokraterna tar kontrollen över kongressen i mellanårsvalet", 8)]


def kluster(*grupper):
    return [{"items": list(g), "item_tokens": [pipeline.tokens(i.get("title_en") or i["title"]) for i in g], "sources": {i["source_id"] for i in g}} for g in grupper]


def test_kluster_som_reglerna_delat_slas_ihop_nar_inbaddning_och_ord_samtycker():
    a = art("Källa A", "Democrats win Congress control in midterm election", 300)
    b = art("Källa B", "Democrats win Congress control in midterm vote", 290)
    c = art("Källa C", "Midterm election: Democrats win both chambers of Congress", 280)
    d = art("Källa D", "Democrats win Congress, projections show, in midterm election", 270)
    kl = kluster([a, b], [c, d])
    tabell = {i["title"]: 3 * n for n, i in enumerate([a, b, c, d])}
    ut = semantisk.sla_ihop(kl, kodare_fran(tabell), tau=0.9, min_delade=2, pair_rate=0.25)
    assert len(ut) == 1 and {i["source_name"] for i in ut[0]["items"]} == {"Källa A", "Källa B", "Källa C", "Källa D"}


def test_inbaddning_utan_gemensamma_ord_slar_inte_ihop():
    items = [art("Källa A", "Storm Amy floods Gothenburg harbour", 300), art("Källa B", "Hamnen i Göteborg står under vatten efter stormen", 290)]
    kl = klustra(items)
    tabell = {items[0]["title"]: 0, items[1]["title"]: 2}
    assert len(semantisk.sla_ihop(kl, kodare_fran(tabell), tau=0.9, min_delade=2)) == 2
    assert len(semantisk.sla_ihop(kl, kodare_fran(tabell), tau=0.9, min_delade=0)) == 1      # utan ordkravet slås de ihop


def test_laga_cosinus_slar_inte_ihop_trots_gemensamma_ord():
    items = [art("Källa A", "Ferries cancelled to Denmark after union strike", 300), art("Källa B", "Ferries cancelled to Denmark after storm Amy", 290)]
    kl = klustra(items)
    tabell = {items[0]["title"]: 0, items[1]["title"]: 80}
    assert len(semantisk.sla_ihop(kl, kodare_fran(tabell), tau=0.9, min_delade=2, pair_rate=0.0)) == len(kl)


def test_en_kalla_en_gang_per_handelse_efter_sammanslagning():
    items = [art("Källa A", "Democrats win Congress control in midterm election", 300), art("Källa A", "Democrats win Congress again in election recount", 200, source_id="a2"),
             art("Källa B", "Democrats win Congress control in midterm vote", 290)]
    items[1]["source_id"] = items[0]["source_id"]
    kl = klustra(items)
    tabell = {i["title"]: 0 for i in items}
    for k in semantisk.sla_ihop(kl, kodare_fran(tabell), tau=0.5, min_delade=2):
        ids = [i["source_id"] for i in k["items"]]
        assert len(ids) == len(set(ids))


def test_hogst_tre_sektioner_i_ett_kluster():
    amnen = ["marknader", "tech", "vetenskap", "noje"]
    items = [art(f"Källa {n}", f"Big deal rattles everyone today {n}", 300 - n, topics=[a]) for n, a in enumerate(amnen)]
    for it in items:
        it["title_en"] = "Big deal rattles everyone today"
    kl = [{"items": [it], "item_tokens": [pipeline.tokens(it["title"])], "sources": {it["source_id"]}} for it in items]
    ut = semantisk.sla_ihop(kl, lambda texter: [[1.0, 0.0]] * len(texter), tau=0.5, min_delade=2)
    assert all(len(pipeline.sections(k)) <= pipeline.MAX_SECTIONS for k in ut)


def test_inga_kluster_andras_om_inget_foreslas():
    items = [art("Källa A", "Storm Amy floods harbour", 300), art("Källa B", "Markets rally on rate cut hopes", 290)]
    kl = klustra(items)
    tabell = {items[0]["title"]: 0, items[1]["title"]: 90}
    ut = semantisk.sla_ihop(kl, kodare_fran(tabell), tau=0.9, min_delade=2)
    assert len(ut) == len(kl) == 2


def test_utan_modell_ger_kluster_oforandrade_och_ett_meddelande(capsys):
    items = [art("Källa A", "Democrats win Congress", 300), art("Källa B", "Democrats win Congress control", 290)]
    kl = klustra(items)
    def saknas(texter):
        raise ImportError("sentence_transformers saknas")
    ut = semantisk.sla_ihop(kl, saknas)
    assert ut == kl and "inbäddningar" in capsys.readouterr().out.lower()


def test_title_en_foredras_framfor_original():
    items = [art("Källa A", "Demokraterna vinner kongressen i valet", 300, title_en="Democrats win Congress in the election"),
             art("Källa B", "Democrats win Congress in the election", 290)]
    kl = [{"items": [it], "item_tokens": [pipeline.tokens(it.get("title_en") or it["title"])], "sources": {it["source_id"]}} for it in items]
    sett = []
    semantisk.sla_ihop(kl, lambda t: sett.append(list(t)) or [[1.0, 0.0]] * len(t), tau=0.5, min_delade=2)
    assert sett == [["Democrats win Congress in the election", "Democrats win Congress in the election"]]


def test_parametrarna_har_de_matta_standardvardena():
    assert semantisk.TAU == 0.55 and semantisk.MIN_DELADE == 2 and semantisk.MODELL == "paraphrase-multilingual-MiniLM-L12-v2"
