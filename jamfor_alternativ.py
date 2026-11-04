#!/usr/bin/env python3
"""Jämför två körningar av pipelinen på samma flöden: A (ingress från alla källor, som idag) och B (bara rubrik för källor som stänger ute
Claude i robots.txt, NN_BARA_RUBRIK). Visar bara det som berörs: händelser där minst en av de utvalda källorna finns med.

  python jamfor_alternativ.py A.json B.json id1,id2,...   (flode.json från varje körning; källornas id i feeds.yaml)
"""
import json
import sys
from pathlib import Path

import autopilot

ROOT = Path(__file__).parent


def _matt(events):
    n = len(events)
    ord_ = [len(((e.get("utkast") or {}).get("sammanfattning_sv") or "").split()) for e in events]
    prob = [len((e.get("kallkontroll") or {}).get("problem") or []) for e in events]
    return {"antal": n,
            "osakra": sum(bool((e.get("utkast") or {}).get("osaker")) for e in events),
            "kallkontroll_ok": sum(bool((e.get("kallkontroll") or {}).get("ok")) for e in events),
            "klarar_grindarna": sum(not autopilot.grindar(e) for e in events),
            "medelord": round(sum(ord_) / n, 1) if n else 0,
            "medel_anmarkningar": round(sum(prob) / n, 2) if n else 0,
            "med_berattelser": sum(bool((e.get("narrativ") or {}).get("ok")) for e in events),
            "med_betydelse": sum(bool((e.get("betydelse") or {}).get("ok") and ((e["betydelse"].get("sv")) or e["betydelse"].get("en"))) for e in events)}


def jamfor(a, b, namn):
    """a och b: listor med händelser (flode.json), namn: namnen på de utvalda källorna så som de står i händelsernas `kallor`."""
    ia, ib = {e["id"]: e for e in a}, {e["id"]: e for e in b}
    bada = [i for i in ia if i in ib]
    berorda = [i for i in bada if any(k["namn"] in namn for k in ia[i].get("kallor") or [])]
    oberorda = [i for i in bada if i not in berorda]
    grind = lambda e: not autopilot.grindar(e)
    return {"totalt": {"A": len(a), "B": len(b), "bada": len(bada)},
            "bara_i": {"A": sorted(set(ia) - set(ib)), "B": sorted(set(ib) - set(ia))},
            "berorda": {"antal": len(berorda), "A": _matt([ia[i] for i in berorda]), "B": _matt([ib[i] for i in berorda])},
            "oberorda": {"antal": len(oberorda), "A": _matt([ia[i] for i in oberorda]), "B": _matt([ib[i] for i in oberorda])},
            "forsamrade": [i for i in berorda if grind(ia[i]) and not grind(ib[i])],
            "forbattrade": [i for i in berorda if grind(ib[i]) and not grind(ia[i])]}


def text(r):
    t, be, ob = r["totalt"], r["berorda"], r["oberorda"]
    rad = [f"Händelser i båda körningarna: {t['bada']} (A {t['A']}, B {t['B']}). Berörda av de utvalda källorna: {be['antal']} av {t['bada']}.", ""]
    namn = (("osäkra utkast", "osakra"), ("källkontroll godkänd", "kallkontroll_ok"), ("klarar grindarna (kan gå automatiskt)", "klarar_grindarna"),
            ("med berättelser", "med_berattelser"), ("med Analys-rad", "med_betydelse"))
    rad.append(f"Berörda händelser ({be['antal']}):          A     B")
    for etikett, nyckel in namn:
        rad.append(f"  {etikett:<40}{be['A'][nyckel]:>4}  {be['B'][nyckel]:>4}")
    rad.append(f"  {'sammanfattningens längd (ord)':<40}{be['A']['medelord']:>4}  {be['B']['medelord']:>4}")
    rad.append(f"  {'anmärkningar per händelse i källkontrollen':<40}{be['A']['medel_anmarkningar']:>4}  {be['B']['medel_anmarkningar']:>4}")
    rad.append(f"Oberörda händelser ({ob['antal']}), kontroll av jämförelsens brus: osäkra A {ob['A']['osakra']} B {ob['B']['osakra']}, "
               f"klarar grindarna A {ob['A']['klarar_grindarna']} B {ob['B']['klarar_grindarna']}")
    rad.append(f"Försämrade med B (klarade grindarna i A, inte i B): {len(r['forsamrade'])}  Förbättrade: {len(r['forbattrade'])}")
    return "\n".join(rad)


def main(argv):
    import yaml
    a, b, ids = (json.loads(Path(argv[0]).read_text(encoding="utf-8"))["handelser"], json.loads(Path(argv[1]).read_text(encoding="utf-8"))["handelser"],
                 set(argv[2].split(",")))
    namn = {s["namn"] for s in yaml.safe_load((ROOT / "feeds.yaml").read_text(encoding="utf-8"))["sources"] if s["id"] in ids}
    r = jamfor(a, b, namn)
    print(text(r))
    for i in r["forsamrade"][:10]:
        e = next(x for x in b if x["id"] == i)
        print(f"  försämrad: {(e.get('utkast') or {}).get('rubrik_sv')} ({', '.join(autopilot.grindar(e)[:2])})")


if __name__ == "__main__":
    main(sys.argv[1:])
