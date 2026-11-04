#!/usr/bin/env python3
"""Hybridklustringen: ett andra varv efter reglerna (pipeline.cluster och merge_clusters) som slår ihop kluster om samma händelse som reglerna delat upp.

Mätt på de handmärkta rubrikerna i tests/kluster-rubriker.json (inbaddningar.py): reglerna ensamma har precision 1,00 och recall 0,71, hybriden
"reglerna ELLER (flerspråkig inbäddning med cosinus minst TAU och minst MIN_DELADE gemensamma ord)" har precision 0,98 och recall 0,87. Delvis hör
det ihop med att "saknas i svenska medier" annars blir fel: ett val som delats i tretton fragment ger tolv felaktiga påståenden.

Två rubriker föreslås höra ihop när modellen och orden båda säger det och de kommer från olika källor. Två kluster slås ihop när minst PAIR_RATE av
rubrikparen mellan dem föreslås (samma mått som merge_clusters), och bara om en källa fortfarande finns en gång per händelse och sektionerna räcker.
Saknas modellen (sentence-transformers) används klustren som de är: pipelinen går alltid vidare.
"""
import sys

TAU = 0.55
MIN_DELADE = 2
PAIR_RATE = 0.25
MODELL = "paraphrase-multilingual-MiniLM-L12-v2"


def modell_kodare(modell=MODELL):
    """Kodare för sentence-transformers: texter -> normaliserade vektorer."""
    from sentence_transformers import SentenceTransformer
    m = SentenceTransformer(modell)
    return lambda texter: m.encode(list(texter), normalize_embeddings=True, show_progress_bar=False)


def _par(vek, tau):
    """Alla index (i, j), i < j, med cosinus minst tau. numpy när det finns, annars ren Python."""
    try:
        import numpy as np
    except ImportError:
        import math
        n = [math.sqrt(sum(x * x for x in v)) or 1.0 for v in vek]
        return [(i, j) for i in range(len(vek)) for j in range(i + 1, len(vek))
                if sum(a * b for a, b in zip(vek[i], vek[j])) / (n[i] * n[j]) >= tau]
    v = np.asarray(vek, dtype=float)
    v = v / (np.linalg.norm(v, axis=1, keepdims=True) + 1e-12)
    sim = v @ v.T
    ii, jj = np.where(np.triu(sim >= tau, 1))
    return list(zip(ii.tolist(), jj.tolist()))


def sla_ihop(clusters, kodare=None, tau=TAU, min_delade=MIN_DELADE, pair_rate=PAIR_RATE):
    import pipeline
    flat = [(it, tk) for c in clusters for it, tk in zip(c["items"], c["item_tokens"])]
    if len(flat) < 2:
        return clusters
    try:
        kodare = kodare or modell_kodare()
        vek = kodare([it.get("title_en") or it["title"] for it, _ in flat])
    except Exception as e:
        print(f"Inbäddningar inte tillgängliga ({type(e).__name__}: {str(e)[:80]}): klustren används som de är.", file=sys.stdout)
        return clusters
    forslag = [(i, j) for i, j in _par(vek, tau)
               if flat[i][0]["source_id"] != flat[j][0]["source_id"] and len(flat[i][1] & flat[j][1]) >= min_delade]
    if not forslag:
        return clusters
    kl = list(clusters)
    antal_ihop = 0
    while True:
        hem = {id(it): n for n, c in enumerate(kl) for it in c["items"]}
        traffar = {}
        for i, j in forslag:
            a, b = hem.get(id(flat[i][0])), hem.get(id(flat[j][0]))
            if a is not None and b is not None and a != b:
                traffar[(min(a, b), max(a, b))] = traffar.get((min(a, b), max(a, b)), 0) + 1
        kandidater = sorted(((h / (len(kl[a]["items"]) * len(kl[b]["items"])), a, b) for (a, b), h in traffar.items()), reverse=True)
        gjort = False
        for rate, a, b in kandidater:
            if rate < pair_rate:
                break
            ca, cb = kl[a], kl[b]
            pool = sorted(ca["items"] + cb["items"], key=lambda x: x["epoch"] or 0, reverse=True)
            keep, seen = [], set()
            for it in pool:
                if it["source_id"] not in seen:
                    seen.add(it["source_id"])
                    keep.append(it)
            if len(pipeline.sections({"items": keep})) > pipeline.MAX_SECTIONS:
                continue
            toks = {id(it): tk for it, tk in zip(ca["items"] + cb["items"], ca["item_tokens"] + cb["item_tokens"])}
            ny = {"items": keep, "item_tokens": [toks[id(it)] for it in keep], "sources": seen}
            kl = [c for n, c in enumerate(kl) if n not in (a, b)] + [ny]
            antal_ihop += 1
            gjort = True
            break
        if not gjort:
            break
    if antal_ihop:
        print(f"Hybridklustringen: {antal_ihop} sammanslagningar, {len(clusters)} kluster blev {len(kl)}.")
    return kl
