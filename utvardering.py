#!/usr/bin/env python3
"""B3: utvärderingen av berättelserna. Ett GitHub-ärende med 30 händelser. Du bockar av om berättelserna stämmer med källorna eller
missvisar, och räkningen säger hur ofta de stämmer. Först när minst 30 är bedömda och minst 80 procent stämmer rekommenderas
NN_BERATTELSER=1 (berattelser.py). Inget slås på av sig självt.

  python utvardering.py skapa    väljer 30 händelser med godkända berättelser och skapar eller uppdaterar ärendet
  python utvardering.py rakna    läser ärendet och skriver data/utvardering.json
"""
import json
import math
import os
import re
import sys
import time
import urllib.request
from pathlib import Path

from newsletter import section_of

ROOT = Path(__file__).parent
FLODE = ROOT / "data" / "flode.json"
UT = ROOT / "data" / "utvardering.json"
LABEL = "utvardering"
MARK = "<!-- newsnavigator-utvardering -->"
N = 30
MAX_ANDEL_SEKTION = 0.4
TROSKEL_BEDOMDA, TROSKEL_ANDEL = 30, 0.8
RUTA = re.compile(r"^- \[([ xX])\] .*`(stammer|fel|bstammer|bfel):([0-9a-f]{10})`", re.M)
BLOCK = re.compile(r"^### \d+\. .*?(?=^### \d+\. |\Z)", re.M | re.S)
REGIONER = {"sverige": "Sverige", "norden": "Norden", "europa": "Europa", "usa": "USA", "latinamerika": "Latinamerika", "asien": "Asien",
            "mellanostern": "Mellanöstern", "afrika": "Afrika", "global": "Globalt"}
LUTNING = {"vanster": "vänster", "lutar_vanster": "lutar vänster", "mitten": "mitten", "lutar_hoger": "lutar höger", "hoger": "höger"}


def api(method, path, body=None):
    repo, token = os.environ["GITHUB_REPOSITORY"], os.environ["GITHUB_TOKEN"]
    req = urllib.request.Request(
        f"https://api.github.com/repos/{repo}{path}", method=method,
        data=json.dumps(body).encode() if body is not None else None,
        headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json",
                 "X-GitHub-Api-Version": "2022-11-28", "User-Agent": "newsnavigator"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read() or b"null")


def _har_narrativ(e):
    return bool((e.get("narrativ") or {}).get("ok") and len(e["narrativ"].get("berattelser") or []) >= 2)


def _har_betydelse(e):
    b = e.get("betydelse") or {}
    return bool(b.get("ok") and (b.get("sv") or b.get("en")))


def valj(events, n=N, max_andel_sektion=MAX_ANDEL_SEKTION):
    """Händelser vars berättelser källkontrollen godkänt, högsta poäng först, med tak per sektion (släpper om inget annat finns)."""
    kand = sorted((e for e in events if _har_narrativ(e) or _har_betydelse(e)),
                  key=lambda e: e.get("poang", 0), reverse=True)
    tak = math.ceil(max_andel_sektion * n)
    valda, per = [], {}
    for relaxa in (False, True):
        for e in kand:
            if len(valda) >= n:
                break
            if e in valda:
                continue
            s = section_of(e)
            if not relaxa and per.get(s, 0) >= tak:
                continue
            valda.append(e)
            per[s] = per.get(s, 0) + 1
    return valda


def _kalla(k):
    extra = [REGIONER.get(k["region"], k["region"])]
    if k.get("lutning") in LUTNING:
        extra.append(f"AllSides: {LUTNING[k['lutning']]}")
    if k.get("statskontrollerad"):
        extra.append("statskontrollerad")
    return f"[{k['namn']}]({k['url']}) ({', '.join(extra)})"


def block(i, ev):
    d = ev.get("utkast") or {}
    rader = [f"### {i}. {d.get('rubrik_sv') or ev['reserv_rubrik']}", f"Händelse `{ev['id']}`, {ev.get('antal_kallor', '?')} källor", ""]
    if _har_narrativ(ev):
        for b in ev["narrativ"]["berattelser"]:
            rader.append(f"**{b['namn_sv']}.** {b['lyfter_sv']}  ")
            rader.append(f"Bärs av: {', '.join(_kalla(k) for k in b['kallor'])}")
            rader.append("")
        rader += [f"- [ ] Berättelserna stämmer med källorna `stammer:{ev['id']}`", f"- [ ] Berättelserna missvisar `fel:{ev['id']}`", ""]
    if _har_betydelse(ev):
        b = ev["betydelse"]
        for lang, namn in (("sv", "Svenska läsaren"), ("en", "Engelska läsaren")):
            if b.get(lang):
                rader.append(f"**Analys, {namn}.** {b[lang]}  ")
        rader.append(f"Bygger på: {', '.join(f'[{k['namn']}]({k['url']})' for k in b.get('grund_kallor') or [])}")
        rader += ["", f"- [ ] Analysen stämmer med fakta och är försiktig (inga råd, inga förutsägelser) `bstammer:{ev['id']}`",
                  f"- [ ] Analysen missvisar, förutsäger eller ger råd `bfel:{ev['id']}`", ""]
    return "\n".join(rader)


INTRO = """Utvärdering av berättelserna (B3 i planen). Läs varje händelse, öppna källorna vid behov och bocka i EN ruta:
**stämmer** om varje berättelse går att spåra till just de källor som anges och inget påstås om vad en källa utelämnar, eller **missvisar** om en berättelse är fel, vinklad eller inte hör ihop. Rör inte rutan om du inte hunnit bedöma.
Händelser med en Analys-rad (vad det betyder för läsaren, princip 4) har två egna rutor för raden: **stämmer** om den följer av fakta och är försiktig (inga råd, inga förutsägelser), **missvisar** annars.
Räkningen körs i Actions, Utvärdering, `lage=rakna`. Berättelserna och Analys-raderna slås på var för sig, först när minst 30 är bedömda och minst 80 procent stämmer.
"""


def kropp(valda, behallna=()):
    delar = list(behallna) + [block(i, e) for i, e in enumerate(valda, len(behallna) + 1)]
    return f"{MARK}\n{INTRO}\n" + "\n".join(delar)


def _bockade(body):
    return {i for ruta, _, i in RUTA.findall(body or "") if ruta in "xX"}


def uppdatera_kropp(gammal, nya, n=N):
    """Bedömda händelser står kvar med sina bockar, resten byts mot dagens bästa."""
    ratade = _bockade(gammal)
    kvar = [b for b in BLOCK.findall(gammal or "") if any(f"`{k}:{i}`" in b for i in ratade for k in ("stammer", "bstammer"))]
    kvar_ids = {i for b in kvar for i in re.findall(r"`b?stammer:([0-9a-f]{10})`", b)}
    nya = [e for e in nya if e["id"] not in kvar_ids][:max(0, n - len(kvar))]
    # numreringen görs om så att den blir löpande
    kvar = [re.sub(r"^### \d+\.", f"### {i}.", b, count=1) for i, b in enumerate(kvar, 1)]
    return kropp(nya, kvar)


def _rakna(body, ja, nej):
    stammer, fel, ids = set(), set(), set()
    for ruta, vilken, i in RUTA.findall(body or ""):
        if vilken not in (ja, nej):
            continue
        ids.add(i)
        if ruta in "xX":
            (stammer if vilken == ja else fel).add(i)
    oklara = stammer & fel
    s, f = stammer - oklara, fel - oklara
    bedomda = len(s) + len(f)
    return {"totalt": len(ids), "bedomda": bedomda, "stammer": len(s), "fel": len(f), "oklara": len(oklara),
            "obedomda": len(ids) - bedomda - len(oklara), "andel_stammer": (len(s) / bedomda) if bedomda else None}


def rakna(body):
    """Berättelserna på översta nivån (som förut) och Analys-raderna under "betydelse"."""
    return {**_rakna(body, "stammer", "fel"), "betydelse": _rakna(body, "bstammer", "bfel")}


def rekommendation(r, vad="Berättelserna", flagga="NN_BERATTELSER", fil="berattelser.py"):
    if r["bedomda"] < TROSKEL_BEDOMDA:
        return f"Inte klart: {r['bedomda']} av {TROSKEL_BEDOMDA} bedömda."
    if r["andel_stammer"] < TROSKEL_ANDEL:
        return (f"{r['stammer']} av {r['bedomda']} stämmer ({round(100 * r['andel_stammer'])} procent), under {round(100 * TROSKEL_ANDEL)}. "
                f"{vad} visas inte. Justera prompten i {fil} och utvärdera igen.")
    return (f"{r['stammer']} av {r['bedomda']} stämmer ({round(100 * r['andel_stammer'])} procent). "
            f"{vad} kan slås på: sätt {flagga}=1 i pipeline.yml.")


def _arende():
    for i in api("GET", f"/issues?labels={LABEL}&state=open&per_page=5") or []:
        if MARK in (i.get("body") or ""):
            return i
    return None


def skapa(events, n=N):
    valda = valj(events, n)
    if not valda:
        print("Inga händelser med godkända berättelser än.")
        return None
    arende = _arende()
    if arende:
        api("PATCH", f"/issues/{arende['number']}", {"body": uppdatera_kropp(arende["body"], valda, n)})
        print(f"Uppdaterade ärende {arende['number']}")
        return arende["number"]
    ny = api("POST", "/issues", {"title": "Utvärdering: berättelserna", "body": kropp(valda), "labels": [LABEL]})
    print(f"Skapade ärende {ny['number']}")
    return ny["number"]


def main(argv=None):
    kommando = (argv or sys.argv[1:] or ["skapa"])[0]
    if kommando == "skapa":
        skapa(json.loads(FLODE.read_text(encoding="utf-8"))["handelser"])
    elif kommando == "rakna":
        arende = _arende()
        if not arende:
            print("Inget utvärderingsärende.")
            return
        r = rakna(arende["body"])
        r["rekommendation"] = rekommendation(r)
        r["betydelse"]["rekommendation"] = rekommendation(r["betydelse"], "Analys-raderna", "NN_BETYDELSE", "betydelse.py")
        r["raknad"] = time.time()
        UT.parent.mkdir(parents=True, exist_ok=True)
        UT.write_text(json.dumps(r, ensure_ascii=False, indent=1), encoding="utf-8")
        print(json.dumps(r, ensure_ascii=False, indent=1))
    else:
        sys.exit("skapa eller rakna")


if __name__ == "__main__":
    main()
