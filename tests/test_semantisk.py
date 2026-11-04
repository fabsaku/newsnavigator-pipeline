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
    assert semantisk.TAU == 0.60 and semantisk.MIN_DELADE == 2 and semantisk.MODELL == "paraphrase-multilingual-MiniLM-L12-v2"


def test_pipelinen_kor_hybridens_andra_varv_efter_andra_varvet_och_kan_stangas_av():
    import inspect
    main = inspect.getsource(pipeline.main)
    assert "semantisk.sla_ihop(clusters)" in main and main.index("merge_clusters(cluster(items))") < main.index("semantisk.sla_ihop")
    assert 'NN_SEMANTISK' in main


def test_workflowen_installerar_modellen_utan_att_stoppa_vid_fel_och_cachar_den():
    from pathlib import Path
    import yaml
    text = (Path(__file__).parent.parent / ".github" / "workflows" / "pipeline.yml").read_text(encoding="utf-8")
    y = yaml.safe_load(text)
    steg = y["jobs"]["run"]["steps"]
    install = next(s for s in steg if "sentence-transformers" in str(s.get("run", "")))
    assert install.get("continue-on-error") is True and "whl/cpu" in install["run"]
    assert any(s.get("uses", "").startswith("actions/cache") and "huggingface" in s["with"]["path"] for s in steg)
    assert steg.index(install) < next(i for i, s in enumerate(steg) if "pipeline.py" in str(s.get("run", "")))


# ---------- Svensk bevakning hos närliggande händelser ----------

def sv(kalla, rubrik, epoch, region="sverige"):
    return art(kalla, rubrik, epoch, region=region)


def test_handelse_utan_svensk_kalla_markeras_nar_en_narliggande_har_en():
    x = [art("A", "Democrats win control of Congress in midterms", 300, region="usa"), art("B", "Democrats win control of Congress, midterm vote", 290, region="europa"),
         art("C", "Midterms: Democrats win control of Congress", 280, region="asien")]
    y = [sv("Ekot", "Democrats take control of Congress in midterm elections", 270), art("D", "Democrats take control of Congress midterm elections", 260, region="usa")]
    z = [art("E", "Storm Amy floods Gothenburg harbour", 250, region="europa"), art("F", "Gothenburg harbour floods in Storm Amy", 240, region="usa")]
    kl = kluster(x, y, z)
    tabell = {i["title"]: 0 for i in x + y}
    tabell.update({i["title"]: 90 for i in z})
    ut = semantisk.sla_ihop(kl, kodare_fran(tabell), tau=0.9, min_delade=2, pair_rate=1.1)       # pair_rate över 1: inget slås ihop
    markerade = {frozenset(i["source_name"] for i in k["items"]): k.get("svensk_bevakning", False) for k in ut}
    assert markerade[frozenset({"A", "B", "C"})] is True
    assert markerade[frozenset({"Ekot", "D"})] is False                       # har redan en svensk källa
    assert markerade[frozenset({"E", "F"})] is False


def test_en_enstaka_traff_racker_inte_for_att_markera():
    x = [art("A", "Democrats win control of Congress in midterms", 300, region="usa"), art("B", "Storm Amy floods Gothenburg harbour", 290, region="europa"),
         art("C", "Markets rally on rate cut hopes", 280, region="asien")]
    y = [sv("Ekot", "Democrats take control of Congress in midterm elections", 270)]
    tabell = {x[0]["title"]: 0, x[1]["title"]: 90, x[2]["title"]: 180, y[0]["title"]: 0}
    ut = semantisk.sla_ihop(kluster(x, y), kodare_fran(tabell), tau=0.9, min_delade=2, pair_rate=1.1)
    assert not any(k.get("svensk_bevakning") for k in ut)


def test_blind_flack_tas_bort_for_markerade_handelser():
    c = {"items": [art(f"K{n}", f"Democrats win Congress {n}", 300 - n, region=r, country="US", state_controlled=False, usa_lean=None, paywall=False,
                       owner="", url=f"https://x/{n}") for n, r in enumerate(["usa", "europa", "asien"])], "svensk_bevakning": True}
    for it in c["items"]:
        it["source_type"] = "media"
    ut = pipeline.perspective(c)
    assert ut["blind_flack"] is None and ut["grannar_svenska"] is True
    c["svensk_bevakning"] = False
    assert pipeline.perspective(c)["blind_flack"] == "saknas_i_sverige"
