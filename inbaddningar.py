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


def _artiklar(rader):
    import re
    t0 = 1_793_000_000
    items = []
    for n, r in enumerate(rader):
        a = {"source_id": re.sub(r"\W+", "-", r["kalla"].lower()).strip("-"), "source_name": r["kalla"], "source_type": r["typ"], "title": r["rubrik"],
             "description": "", "topics": [], "epoch": t0 - n * 60, "_rad": n}
        if r.get("rubrik_en"):
            a["title_en"] = r["rubrik_en"]
        items.append(a)
    return items


def _dagens_hem(rader):
    """{radnummer: klusternummer} för dagens klustring (regler och andra varvet, pipeline.cluster och merge_clusters) på alla rubriker."""
    import pipeline
    items = _artiklar(rader)
    hem = {}
    for k, kl in enumerate(pipeline.merge_clusters(pipeline.cluster(items))):           # som i pipelinen: första och andra varvet
        for it in kl["items"]:
            hem[it["_rad"]] = k
    return hem


def dagens_klustring(rader):
    """Samma mått för dagens klustring: förutsagt hör ihop = hamnar i samma kluster i pipeline.cluster (alla rubriker klustras, märkta jämförs)."""
    hem = _dagens_hem(rader)
    return parvisa_matt([r.get("handelse") for r in rader], lambda i, j: hem.get(i) == hem.get(j) and i in hem)


def hybridens_kluster(rader, vek_per_text, tau, min_delade, pair_rate):
    """Produktionsvägen: regler, andra varvet och semantisk.sla_ihop. vek_per_text: {rubrik (engelska om den finns): vektor}."""
    import pipeline
    import semantisk
    kl = pipeline.merge_clusters(pipeline.cluster(_artiklar(rader)))
    ut = semantisk.sla_ihop(kl, lambda texter: [vek_per_text[t] for t in texter], tau=tau, min_delade=min_delade, pair_rate=pair_rate)
    hem = {it["_rad"]: k for k, c in enumerate(ut) for it in c["items"]}
    return {"tau": tau, "min_delade": min_delade, "pair_rate": pair_rate,
            **parvisa_matt([r.get("handelse") for r in rader], lambda i, j: i in hem and hem.get(i) == hem.get(j))}


def parametersvep(rader, vek_per_text, taus=(0.5, 0.55, 0.6, 0.65), delade=(1, 2), rater=(0.25,)):
    return [hybridens_kluster(rader, vek_per_text, t, d, r) for t in taus for d in delade for r in rater]


def handelsepar(handelser, kodare, tau=0.6, min_delade=2, topp=25):
    """Diagnos på riktiga händelser (data/flode.json): för varje par av händelser, hur många rubrikpar mellan dem föreslår inbäddningen och orden (cosinus
    minst tau, minst min_delade gemensamma ord, olika källor), och hur stor andel det är av alla rubrikpar. Visar vad som skulle slås ihop och varför inte."""
    import pipeline
    rader = [(e["id"], k["namn"], k["rubrik"], pipeline.tokens(k["rubrik"])) for e in handelser for k in e["kallor"] if k.get("rubrik")]
    vek = kodare([r[2] for r in rader])
    antal = {}
    for i in range(len(rader)):
        for j in range(i + 1, len(rader)):
            if rader[i][0] == rader[j][0] or rader[i][1] == rader[j][1] or len(rader[i][3] & rader[j][3]) < min_delade:
                continue
            if cosinus(vek[i], vek[j]) >= tau:
                nyckel = tuple(sorted((rader[i][0], rader[j][0])))
                antal[nyckel] = antal.get(nyckel, 0) + 1
    storlek = {}
    for r in rader:
        storlek[r[0]] = storlek.get(r[0], 0) + 1
    titel = {e["id"]: (e.get("utkast") or {}).get("rubrik_en") or e["reserv_rubrik"] for e in handelser}
    ut = [{"a": a, "b": b, "traffar": n, "andel": n / (storlek[a] * storlek[b]), "storlek": (storlek[a], storlek[b]), "titel": (titel[a], titel[b])}
          for (a, b), n in antal.items()]
    return sorted(ut, key=lambda x: -x["traffar"])[:topp]


def sammanhang_efter_renhet(rader, vek_per_text, min_storlek=3):
    """Sammanhang (semantisk._satt_sammanhang) för produktionsklustren med minst min_storlek rubriker som alla är handmärkta: rena (alla samma händelse)
    och blandade (flera händelser). Underlag för tröskeln SAMMANHANG_MIN i autopilot.py."""
    import pipeline
    import semantisk
    kl = pipeline.merge_clusters(pipeline.cluster(_artiklar(rader)))
    kl = semantisk.sla_ihop(kl, lambda texter: [vek_per_text[t] for t in texter])
    rena, blandade = [], []
    for c in kl:
        etiketter = [rader[it["_rad"]].get("handelse") for it in c["items"]]
        if len(c["items"]) < min_storlek or any(e is None for e in etiketter) or "sammanhang" not in c:
            continue
        (rena if len(set(etiketter)) == 1 else blandade).append(c["sammanhang"])
    return {"rena": rena, "blandade": blandade}


def sammanhangstroskel(rena, blandade, troskler=(0.4, 0.45, 0.5, 0.55, 0.6, 0.65, 0.7)):
    """För varje tröskel: hur många blandade kluster som skulle stoppas (sammanhang under tröskeln) och hur många rena som stoppas av misstag."""
    return [{"troskel": t, "blandade_stoppade": sum(x < t for x in blandade), "blandade": len(blandade),
             "rena_stoppade": sum(x < t for x in rena), "rena": len(rena)} for t in troskler]


def bast_med_precision(tabell, min_precision=0.98):
    """Raden med högst recall bland dem som håller precisionen, eller None. Falska sammanslagningar är värre än missade, så det är den punkten som räknas."""
    ok = [r for r in tabell if r["precision"] >= min_precision]
    return max(ok, key=lambda r: r["recall"]) if ok else None


def hybrid(rader, vek, troskler=TROSKLER, min_delade=2):
    """Dagens regler OR (cosinus >= tröskel och minst `min_delade` gemensamma ord i rubrikerna): inbäddningen får bara föreslå par som reglerna
    missar, och ordkravet håller tillbaka falska sammanslagningar. vek har en vektor per rad i `rader`."""
    import pipeline
    hem = _dagens_hem(rader)
    ord_ = [pipeline.tokens(r.get("rubrik_en") or r["rubrik"]) for r in rader]
    etiketter = [r.get("handelse") for r in rader]
    return [{"troskel": t, **parvisa_matt(etiketter, lambda i, j, t=t: (i in hem and hem.get(i) == hem.get(j))
                                          or (cosinus(vek[i], vek[j]) >= t and len(ord_[i] & ord_[j]) >= min_delade))} for t in troskler]


def text(r, modell=MODELL):
    rad = [f"Inbäddningar ({modell}) mot dagens klustring, parvis på handmärkta rubriker ({r['dagens']['par']} par)", ""]
    d = r["dagens"]
    rad.append(f"Dagens klustring: precision {d['precision']:.2f}  recall {d['recall']:.2f}  F1 {d['f1']:.2f}")
    for namn, tabell in r["modeller"].items():
        b = max(tabell, key=lambda x: x["f1"])
        rad.append(f"{namn}: bäst F1 vid tröskel {b['troskel']:.2f}: precision {b['precision']:.2f}  recall {b['recall']:.2f}  F1 {b['f1']:.2f}")
        h = bast_med_precision(tabell)
        rad.append("   " + (f"bäst recall med precision minst 0,98 vid tröskel {h['troskel']:.2f}: precision {h['precision']:.2f}  recall {h['recall']:.2f}  F1 {h['f1']:.2f}"
                            if h else "ingen tröskel håller precision 0,98"))
    rad.append("")
    for namn, tabell in r["modeller"].items():
        rad.append(f"Tröskelsvep, {namn}:  " + "  ".join(f"{x['troskel']:.2f}→{x['f1']:.2f}" for x in tabell))
    if r.get("kluster"):
        rad += ["", "Produktionsvägen (regler, andra varvet, hybridens andra varv), per tau, minst gemensamma ord, andel par:"]
        for x in r["kluster"]:
            rad.append(f"  tau {x['tau']:.2f}  ord {x['min_delade']}  andel {x['pair_rate']:.2f}:  precision {x['precision']:.3f}  recall {x['recall']:.3f}  F1 {x['f1']:.3f}")
    return "\n".join(rad)


def main(argv):
    from sentence_transformers import SentenceTransformer
    if argv and argv[0] == "--handelser":
        m = SentenceTransformer(MODELL)
        kodare = lambda texter: m.encode(list(texter), normalize_embeddings=True).tolist()
        handelser = json.loads((ROOT / "data" / "flode.json").read_text(encoding="utf-8"))["handelser"]
        for p in handelsepar(handelser, kodare, tau=0.55, min_delade=1):
            print(f"{p['traffar']:>3} träffar, andel {p['andel']:.2f}, storlekar {p['storlek']}: {p['titel'][0][:55]} | {p['titel'][1][:55]}")
        rader = json.loads(FIXTUR.read_text(encoding="utf-8"))["rubriker"]
        vek = dict(zip([x.get("rubrik_en") or x["rubrik"] for x in rader], kodare([x.get("rubrik_en") or x["rubrik"] for x in rader])))
        r = sammanhang_efter_renhet(rader, vek, min_storlek=3)
        print(f"\nSammanhang i handmärkta kluster med minst 3 rubriker: {len(r['rena'])} rena, {len(r['blandade'])} blandade")
        for namn in ("rena", "blandade"):
            v = sorted(r[namn])
            if v:
                print(f"  {namn}: min {v[0]:.2f}  median {v[len(v) // 2]:.2f}  max {v[-1]:.2f}")
        for x in sammanhangstroskel(r["rena"], r["blandade"]):
            print(f"  tröskel {x['troskel']:.2f}: stoppar {x['blandade_stoppade']} av {x['blandade']} blandade och {x['rena_stoppade']} av {x['rena']} rena")
        return
    modell = argv[0] if argv else MODELL
    rader = json.loads(FIXTUR.read_text(encoding="utf-8"))["rubriker"]
    m = SentenceTransformer(modell)
    kodare = lambda texter: m.encode(list(texter), normalize_embeddings=True).tolist()
    vek_o, vek_e = kodare([x["rubrik"] for x in rader]), kodare([x.get("rubrik_en") or x["rubrik"] for x in rader])
    vek_per_text = dict(zip([x.get("rubrik_en") or x["rubrik"] for x in rader], vek_e))
    r = {"kluster": parametersvep(rader, vek_per_text, taus=(0.5, 0.55, 0.6, 0.65, 0.7), delade=(1, 2), rater=(0.25, 0.5)),
         "dagens": dagens_klustring(rader),
         "modeller": {"originalrubrik": svep([x.get("handelse") for x in rader], vek_o),
                      "engelsk rubrik": svep([x.get("handelse") for x in rader], vek_e),
                      "hybrid, minst 2 gemensamma ord (engelsk rubrik)": hybrid(rader, vek_e, min_delade=2),
                      "hybrid, minst 1 gemensamt ord (engelsk rubrik)": hybrid(rader, vek_e, min_delade=1)}}
    print(text(r, modell))


if __name__ == "__main__":
    main(sys.argv[1:])
