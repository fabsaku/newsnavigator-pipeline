#!/usr/bin/env python3
"""Hybridklustringen: ett andra varv efter reglerna (pipeline.cluster och merge_clusters) som slår ihop kluster om samma händelse som reglerna delat upp.

Mätt på de handmärkta rubrikerna i tests/kluster-rubriker.json (inbaddningar.py, produktionsvägen): reglerna och andra varvet har precision 0,98
och recall 0,875; med hybridens andra varv (flerspråkig inbäddning med cosinus minst TAU och minst MIN_DELADE gemensamma ord, minst PAIR_RATE av
paren) är precisionen 0,98 och recallen 0,95. På riktiga data delas stora händelser i fragment (USA-valet blev tio kluster med två till fyra
källor), vilket också ger felaktiga "saknas i svenska medier".

Två rubriker föreslås höra ihop när modellen och orden båda säger det och de kommer från olika källor. Två kluster slås ihop när minst PAIR_RATE av
rubrikparen mellan dem föreslås (samma mått som merge_clusters), och bara om en källa fortfarande finns en gång per händelse och sektionerna räcker.
Saknas modellen (sentence-transformers) används klustren som de är: pipelinen går alltid vidare.
"""
import sys

TAU = 0.60                # mätt: precision 0,98 och recall 0,95 på de handmärkta rubrikerna (regler ensamma: 0,98 och 0,875)
MIN_DELADE = 2
PAIR_RATE = 0.25
BEVAKNING_TAU = 0.55       # svensk täckning hos närliggande händelser räknas med lättare mått än sammanslagning: ett uteblivet
BEVAKNING_DELADE = 1       # "saknas i svenska medier" kostar mindre än ett felaktigt
BEVAKNING_MIN = 2
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
    kl = list(clusters)
    antal_ihop = 0
    while forslag and pair_rate <= 1.0:
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
    lattare = [(i, j) for i, j in _par(vek, BEVAKNING_TAU)
               if flat[i][0]["source_id"] != flat[j][0]["source_id"] and len(flat[i][1] & flat[j][1]) >= BEVAKNING_DELADE]
    markerade = _markera_svensk_bevakning(kl, flat, lattare)
    if antal_ihop or markerade:
        print(f"Hybridklustringen: {antal_ihop} sammanslagningar ({len(clusters)} kluster blev {len(kl)}), {markerade} händelser utan svensk källa har svensk täckning hos närliggande händelser.")
    return kl


def _markera_svensk_bevakning(kl, flat, forslag):
    """En händelse utan svensk källa, vars rubriker till stor del liknar rubriker i en annan händelse som har en svensk källa, har svensk täckning:
    "saknas i svenska medier" vore fel (stora händelser delas i delhändelser). Kräver minst BEVAKNING_MIN av dess rubriker."""
    hem = {id(it): n for n, c in enumerate(kl) for it in c["items"]}
    har_svensk = [any(it.get("region") == "sverige" for it in c["items"]) for c in kl]
    traffade = {}
    for i, j in forslag:
        a, b = hem.get(id(flat[i][0])), hem.get(id(flat[j][0]))
        if a is None or b is None or a == b:
            continue
        for x, y, it in ((a, b, flat[i][0]), (b, a, flat[j][0])):
            if not har_svensk[x] and har_svensk[y]:
                traffade.setdefault(x, set()).add(id(it))
    antal = 0
    for x, ids in traffade.items():
        if len(ids) >= BEVAKNING_MIN:
            kl[x]["svensk_bevakning"] = True
            antal += 1
    return antal
