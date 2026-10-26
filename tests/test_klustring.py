"""Fas 0: ett kluster ska handla om en händelse.

Kör: python -m pytest tests
"""
import json
import re
from collections import defaultdict
from pathlib import Path

from newsletter import SECTIONS
from pipeline import cluster, tag

FIXTUR = Path(__file__).parent / "kluster-rubriker.json"
MAX_SEKTIONER = 3


def artikel(kalla, rubrik, epoch, typ="media", rubrik_en=None, **extra):
    a = {"source_id": re.sub(r"\W+", "-", kalla.lower()).strip("-"), "source_name": kalla, "source_type": typ,
         "title": rubrik, "description": "", "topics": [], "epoch": epoch}
    if rubrik_en:
        a["title_en"] = rubrik_en
    a.update(extra)
    return a


def sektioner(c):
    amnen = set(tag(c)[1])
    return {k for k, _, _, taggar in SECTIONS if amnen & taggar}


def riktiga_rubriker():
    rader = json.loads(FIXTUR.read_text(encoding="utf-8"))["rubriker"]
    t0 = 1_793_000_000
    return [artikel(r["kalla"], r["rubrik"], t0 - n * 60, typ=r["typ"], rubrik_en=r.get("rubrik_en"),
                    handelse=r["handelse"]) for n, r in enumerate(rader)]


def test_ingen_sammanslagning_via_en_tredje_artikel():
    # A och B handlar om samma sak, B och C delar ord, men A och C har inget gemensamt.
    a = artikel("Källa A", "Storm Amy floods Gothenburg harbour", 300)
    b = artikel("Källa B", "Storm Amy floods Gothenburg, ferries cancelled to Denmark", 200)
    c = artikel("Källa C", "Ferries cancelled to Denmark after union strike", 100)
    kluster = cluster([a, b, c])
    hemvist = {i["source_name"]: n for n, k in enumerate(kluster) for i in k["items"]}
    assert hemvist["Källa A"] == hemvist["Källa B"]
    assert hemvist["Källa C"] != hemvist["Källa A"]


def test_en_kalla_per_handelse():
    a = artikel("Källa A", "Storm Amy floods Gothenburg harbour", 300)
    a2 = artikel("Källa A", "Storm Amy floods Gothenburg harbour again", 200, id="andra")
    for k in cluster([a, a2]):
        ids = [i["source_id"] for i in k["items"]]
        assert len(ids) == len(set(ids))


def test_hogst_tre_sektioner_per_kluster():
    # Samma ord i alla rubriker, men var och en drar åt sin sektion.
    rubriker = [
        "Ericsson and Nokia in merger talks over AI",           # Tech och AI
        "Ericsson and Nokia merger talks lift stocks",          # Marknader
        "Ericsson and Nokia merger talks worry Swedish unions",  # Sverige och Norden
        "Ericsson and Nokia merger talks include satellite unit",  # Vetenskap
        "Ericsson and Nokia merger talks raise Nato concerns",  # Världen
    ]
    artiklar = [artikel(f"Källa {n}", r, 1000 - n) for n, r in enumerate(rubriker)]
    kluster = cluster(artiklar)
    assert sum(len(k["items"]) for k in kluster) == len(artiklar)
    for k in kluster:
        if len(k["items"]) > 1:
            assert len(sektioner(k)) <= MAX_SEKTIONER, [i["title"] for i in k["items"]]


def test_riktigt_flode_ger_inga_kluster_med_olika_handelser():
    """Acceptanskriteriet: flödet 2026-10-25 ska inte ge kluster med rubriker om olika händelser."""
    blandade = []
    for k in cluster(riktiga_rubriker()):
        handelser = defaultdict(list)
        for i in k["items"]:
            if i["handelse"]:
                handelser[i["handelse"]].append(f'{i["source_name"]}: {i.get("title_en") or i["title"]}')
        if len(handelser) > 1:
            blandade.append(dict(handelser))
    assert not blandade, json.dumps(blandade, ensure_ascii=False, indent=1)


def test_riktigt_flode_haller_ihop_tydliga_handelser():
    """Stramare klustring får inte dela upp händelser där alla rubriker säger samma sak."""
    kluster = cluster(riktiga_rubriker())
    for handelse in ("machado", "ornnastet", "bulgarien", "burnham", "kim-kina"):
        delar = [k for k in kluster if any(i["handelse"] == handelse for i in k["items"])]
        assert len(delar) == 1, (handelse, [[i["title"] for i in k["items"]] for k in delar])
