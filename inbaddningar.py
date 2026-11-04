#!/usr/bin/env python3
"""Experiment: ger flerspråkiga inbäddningar bättre kluster än dagens regler? Mäts parvis på de handmärkta rubrikerna i
tests/kluster-rubriker.json: två rubriker om samma händelse ska hamna ihop, två om olika inte. Dagens klustring (pipeline.cluster, regler på
gemensamma ord i den engelska översättningen) jämförs med en inbäddningsmodell på originalrubriken (ingen översättning behövs) och på den
engelska rubriken, med tröskeln svept.

  python inbaddningar.py [modell]     modell är en sentence-transformers-modell (standard paraphrase-multilingual-MiniLM-L12-v2)
Körs i Actions (Källprov, inmatning inbaddningar), eftersom sentence-transformers och torch inte ligger i requirements.txt.
"""
import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).parent
FIXTUR = ROOT / "tests" / "kluster-rubriker.json"
MODELL = "paraphrase-multilingual-MiniLM-L12-v2"
TROSKLER = [round(0.40 + 0.05 * i, 2) for i in range(12)]


def cosinus(a, b):
    na, nb = math.sqrt(sum(x * x for x in a)), math.sqrt(sum(x * x for x in b))
    return sum(x * y for x, y in zip(a, b)) / (na * nb) if na and nb else 0.0


def parvisa_matt(etiketter, forutsagt):
    """Precision, recall och F1 över alla par med båda rubrikerna märkta. forutsagt(i, j) säger om paret förutsägs höra ihop."""
    tp = fp = fn = par = 0
    for i in range(len(etiketter)):
        for j in range(i + 1, len(etiketter)):
            if etiketter[i] is None or etiketter[j] is None:
                continue
            par += 1
            sant, pred = etiketter[i] == etiketter[j], forutsagt(i, j)
            tp += sant and pred
            fp += (not sant) and pred
            fn += sant and not pred
    return {"sant_positiva": tp, "falskt_positiva": fp, "falskt_negativa": fn, "par": par,
            "precision": tp / (tp + fp) if tp + fp else 0.0, "recall": tp / (tp + fn) if tp + fn else 0.0,
            "f1": 2 * tp / (2 * tp + fp + fn) if tp else 0.0}


def svep(etiketter, vek, troskler=TROSKLER):
    return [{"troskel": t, **parvisa_matt(etiketter, lambda i, j, t=t: cosinus(vek[i], vek[j]) >= t)} for t in troskler]


def utvardera(rader, kodare, text_ur, troskler=TROSKLER):
    marktade = [r for r in rader if r.get("handelse")]
    vek = kodare([text_ur(r) for r in marktade])
    return svep([r["handelse"] for r in marktade], vek, troskler)


def dagens_klustring(rader):
    """Samma mått för dagens klustring: förutsagt hör ihop = hamnar i samma kluster i pipeline.cluster (alla rubriker klustras, märkta jämförs)."""
    import re
    import pipeline
    t0 = 1_793_000_000
    items = []
    for n, r in enumerate(rader):
        a = {"source_id": re.sub(r"\W+", "-", r["kalla"].lower()).strip("-"), "source_name": r["kalla"], "source_type": r["typ"], "title": r["rubrik"],
             "description": "", "topics": [], "epoch": t0 - n * 60, "_rad": n}
        if r.get("rubrik_en"):
            a["title_en"] = r["rubrik_en"]
        items.append(a)
    hem = {}
    for k, kl in enumerate(pipeline.cluster(items)):
        for it in kl["items"]:
            hem[it["_rad"]] = k
    return parvisa_matt([r.get("handelse") for r in rader], lambda i, j: hem.get(i) == hem.get(j) and i in hem)


def text(r, modell=MODELL):
    rad = [f"Inbäddningar ({modell}) mot dagens klustring, parvis på handmärkta rubriker ({r['dagens']['par']} par)", ""]
    d = r["dagens"]
    rad.append(f"Dagens klustring: precision {d['precision']:.2f}  recall {d['recall']:.2f}  F1 {d['f1']:.2f}")
    for namn, tabell in r["modeller"].items():
        b = max(tabell, key=lambda x: x["f1"])
        rad.append(f"{namn}: bäst vid tröskel {b['troskel']:.2f}: precision {b['precision']:.2f}  recall {b['recall']:.2f}  F1 {b['f1']:.2f}")
    rad.append("")
    for namn, tabell in r["modeller"].items():
        rad.append(f"Tröskelsvep, {namn}:  " + "  ".join(f"{x['troskel']:.2f}→{x['f1']:.2f}" for x in tabell))
    return "\n".join(rad)


def main(argv):
    from sentence_transformers import SentenceTransformer
    modell = argv[0] if argv else MODELL
    rader = json.loads(FIXTUR.read_text(encoding="utf-8"))["rubriker"]
    m = SentenceTransformer(modell)
    kodare = lambda texter: m.encode(list(texter), normalize_embeddings=True).tolist()
    r = {"dagens": dagens_klustring(rader),
         "modeller": {"originalrubrik": utvardera(rader, kodare, lambda x: x["rubrik"]),
                      "engelsk rubrik": utvardera(rader, kodare, lambda x: x.get("rubrik_en") or x["rubrik"])}}
    print(text(r, modell))


if __name__ == "__main__":
    main(sys.argv[1:])
