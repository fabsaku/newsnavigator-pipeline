#!/usr/bin/env python3
"""Lanseringen: 56 inlägg per Instagramkonto ur veckan som gått, en genomgång av hela batchen, och ett maraton i lugn takt.

  python lansering.py valj [--konto sv|en|alla] [--antal 56]   välj ur veckans flöden, bygg korten, skriv förhandsgranskningen
  python lansering.py godkann [--konto ...] [--uteslut 3,17]   godkänn batchen (och ta bort enstaka poster), arkivera dem
  python lansering.py posta [--konto ...] [--antal 1] [--intervall 8] [--torrt] [--budget 330]
                                                               posta i rangordning, ett inlägg var 8:e minut

Säkerheten är huvudsaken. Inget postas innan batchen är godkänd. Varje inlägg sparas i git direkt efter att det postats, så att en
omstart aldrig kan ge ett dubbelinlägg. Tyst läge (data/autopilot.json) stoppar allt. Tre fel i rad stoppar. Instagrams kvot kontrolleras
före varje inlägg. Förhandsgranskningen ligger på sajten under /lansering/ (noindex).
"""
import argparse
import html
import json
import math
import os
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import autopilot
import instagram
import newsletter
import utgava
from pipeline import tokens

ROOT = Path(__file__).parent
DIR = ROOT / "data" / "lansering"
PREVIEW = ROOT / "public" / "lansering"
DAG = 86400
ANTAL = 56
HALVERING = 0.92            # poängen sjunker åtta procent per dygn: nyare går före äldre
MAX_PER_FAMILJ = 3
MAX_ANDEL_SEKTION = 0.4
FEL_I_RAD = 3
KVOT_MARGINAL = 2
FEL_PAUS = 120              # sekunder efter ett misslyckat inlägg


class EjGodkand(Exception):
    """Batchen är inte godkänd, så ingenting får postas."""


# ---------- Veckans berättelser ----------

def _lika(a, b):
    if a["urls"] & b["urls"]:
        return True
    delade = len(a["w"] & b["w"])
    return delade >= 3 and delade / max(1, min(len(a["w"]), len(b["w"]))) >= 0.5


def _samma_artiklar(a, b):
    """Samma händelse under två id (äldre körningar): minst hälften av den mindre berättelsens länkar finns i den andra."""
    delade = len(a["urls"] & b["urls"])
    return delade > 0 and delade / max(1, min(len(a["urls"]), len(b["urls"]))) >= 0.5


def _bas(s):
    ev = s["ev"]
    d = ev.get("utkast") or {}
    return {"urls": {k["url"] for k in ev.get("kallor") or []}, "w": tokens(d.get("rubrik_en") or ev.get("reserv_rubrik") or "")}


def _en_gang(stories):
    """En berättelse som setts flera gånger räknas en gång, med den version som har flest källor (vid lika den senaste)."""
    unika = []
    for s in stories:
        b = {**_bas(s), "s": s}
        for u in unika:
            if u["s"]["ev"]["id"] == s["ev"]["id"] or _samma_artiklar(b, u):
                u["urls"] |= b["urls"]
                u["w"] |= b["w"]
                if (s["ev"].get("antal_kallor", 0), s["senast"]) > (u["s"]["ev"].get("antal_kallor", 0), u["s"]["senast"]):
                    u["s"] = s
                break
        else:
            unika.append(b)
    return [u["s"] for u in unika]


def _familjer(stories):
    """Berättelser om samma händelse (olika vinklar) får samma familjenummer."""
    bas = [_bas(s) for s in stories]
    foralder = list(range(len(stories)))

    def rot(i):
        while foralder[i] != i:
            foralder[i] = foralder[foralder[i]]
            i = foralder[i]
        return i
    for i in range(len(stories)):
        for j in range(i + 1, len(stories)):
            if _lika(bas[i], bas[j]):
                foralder[rot(i)] = rot(j)
    return [rot(i) for i in range(len(stories))]


def valj(stories, lang, antal=ANTAL, nu=None, max_per_familj=MAX_PER_FAMILJ, max_andel_sektion=MAX_ANDEL_SEKTION):
    """De `antal` bästa berättelserna för kontots utgåva: bara sådana som klarar utgåvans grindar, nyare före äldre, högst tre per
    händelsefamilj och inte för mycket av en och samma sektion (släpper om inget annat finns)."""
    nu = time.time() if nu is None else nu
    kandidater = [s for s in _en_gang(stories)
                  if utgava.visa(s["ev"], lang) and instagram.kan_byggas(s["ev"], lang) and not utgava.grindar(s["ev"], lang, batch=True)]
    fam = dict(zip(map(id, kandidater), _familjer(kandidater)))

    def poang(s):
        return s["ev"].get("poang", 0) * HALVERING ** max(0.0, (nu - s["senast"]) / DAG)
    ordnade = sorted(kandidater, key=poang, reverse=True)
    tak = math.ceil(max_andel_sektion * antal)
    valda, per_familj, per_sektion = [], {}, {}
    for relaxa in (False, True):
        for s in ordnade:
            if len(valda) >= antal:
                break
            if s in valda or per_familj.get(fam[id(s)], 0) >= max_per_familj:
                continue
            sek = newsletter.section_of(s["ev"])
            if not relaxa and per_sektion.get(sek, 0) >= tak:
                continue
            valda.append(s)
            per_familj[fam[id(s)]] = per_familj.get(fam[id(s)], 0) + 1
            per_sektion[sek] = per_sektion.get(sek, 0) + 1
    valda.sort(key=poang, reverse=True)
    return [{"rank": n, "id": s["ev"]["id"], "rubrik": instagram._rubrik(s["ev"], lang), "sektion": newsletter.section_of(s["ev"]),
             "poang": round(poang(s), 2), "senast": s["senast"], "genomgang": utgava.kraver_genomgang(s["ev"], lang),
             "familj": fam[id(s)]} for n, s in enumerate(valda, 1)]


def samla_vecka(dagar=7, steg=3, rot=ROOT):
    """Veckans berättelser ur flödeshistoriken i git (kräver full historik) och arkivet."""
    def git(*args):
        return subprocess.run(["git", *args], cwd=rot, capture_output=True, text=True).stdout
    revs = [r.split() for r in git("log", "--format=%h %at", f"--since={dagar} days ago", "--", "data/flode.json").strip().splitlines()][::steg]
    stories = []
    for h, at in revs:
        try:
            handelser = json.loads(git("show", f"{h}:data/flode.json"))["handelser"]
        except ValueError:
            continue
        stories += [{"ev": e, "senast": float(at)} for e in handelser]
    for e in newsletter.load_archive().values():
        stories.append({"ev": e, "senast": e.get("godkand_tid") or time.time()})
    return _en_gang(stories)


# ---------- Lanseringsfilen, förhandsgranskning och godkännande ----------

def _fil(lang):
    return DIR / f"{lang}.json"


def las(lang):
    try:
        return json.loads(_fil(lang).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _spara(lang, data):
    DIR.mkdir(parents=True, exist_ok=True)
    _fil(lang).write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


def status(lang):
    try:
        return json.loads((DIR / f"status-{lang}.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"postade": {}, "fel": []}


def _spara_status(lang, st):
    DIR.mkdir(parents=True, exist_ok=True)
    (DIR / f"status-{lang}.json").write_text(json.dumps(st, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


def skyddade(lang):
    """Notiser vars kort inte får rensas bort av det vanliga bygget."""
    data = las(lang)
    return {p["id"] for p in data["valda"]} if data else set()


def skriv(lang, valda, stories, nu=None, intervall=8):
    """Skriver lanseringsfilen (ogodkänd) och förhandsgranskningen."""
    nu = time.time() if nu is None else nu
    per_id = {s["ev"]["id"]: s for s in stories}
    poster = []
    for v in valda:
        ev = {**per_id[v["id"]]["ev"], "godkand_tid": v["senast"]}
        poster.append({**v, "ev": ev})
    data = {"konto": instagram.HANDTAG[lang], "lang": lang, "skapad": nu, "godkand": False, "intervall": intervall, "valda": poster}
    _spara(lang, data)
    _forhandsgranskning(lang, data)
    return data


CSS = """
:root{--bg:#000;--ink:#fff;--text:#d6d6d6;--mute:#8c8c8c;--rule:#2e2e2e;--serif:'Source Serif 4',Georgia,serif;--sans:'Source Sans 3','Helvetica Neue',Arial,sans-serif}
body{margin:0;background:var(--bg);color:var(--text);font:400 17px/1.5 var(--sans)}main{max-width:1100px;margin:0 auto;padding:32px 16px 80px}
h1{font:600 34px/1.2 var(--serif);color:var(--ink);margin:0 0 8px}p.lede{color:var(--mute);margin:0 0 28px;max-width:70ch}
.post{display:grid;grid-template-columns:270px 1fr;gap:24px;border-top:1px solid var(--rule);padding:24px 0}
.post img{width:270px;height:auto;display:block;background:#111}.post h2{font:600 22px/1.25 var(--serif);color:var(--ink);margin:0 0 6px}
.meta{color:var(--mute);font-size:14px;margin:0 0 8px}.flag{color:var(--ink);font-weight:700}details{margin-top:10px;color:var(--mute);font-size:14px}
pre{white-space:pre-wrap;font:inherit;margin:8px 0 0}@media(max-width:700px){.post{grid-template-columns:1fr}.post img{width:100%}}
"""


def _forhandsgranskning(lang, data):
    PREVIEW.mkdir(parents=True, exist_ok=True)
    sv = lang == "sv"
    delar = [f'<!doctype html><html lang="{lang}"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
             f'<meta name="robots" content="noindex, nofollow"><title>Lansering {html.escape(data["konto"])}</title>'
             f'<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Source+Serif+4:wght@600&family=Source+Sans+3:wght@400;700&display=swap">'
             f"<style>{CSS}</style></head><body><main><h1>Lansering {html.escape(data['konto'])}</h1>"
             f'<p class="lede">{len(data["valda"])} inlägg i den ordning de postas. Bläddra igenom allt en gång. Det du inte vill ha tar du bort '
             f'med "godkann" och "uteslut" i workflowen Lansering. Inget postas innan du godkänt.</p>']
    for p in data["valda"]:
        ev = p["ev"]
        d = ev.get("utkast") or {}
        marke = (' <span class="flag">Kräver din genomgång</span>' + (": Saknas i svenska medier" if (ev.get("perspektiv") or {}).get("blind_flack") == "saknas_i_sverige" else "")) \
            if p["genomgang"] else ""
        dag = time.strftime("%Y-%m-%d", time.gmtime(p["senast"]))
        delar.append(
            f'<article class="post"><a href="../ig/{lang}/{p["id"]}/1.jpg"><img src="../ig/{lang}/{p["id"]}/1.jpg" alt="" loading="lazy"></a><div>'
            f'<p class="meta">#{p["rank"]} · {html.escape(p["sektion"])} · {ev.get("antal_kallor", 0)} källor · {dag}{marke}</p>'
            f'<h2>{html.escape(p["rubrik"])}</h2><p>{html.escape(d.get(f"sammanfattning_{lang}") or "")}</p>'
            f'<details><summary>Caption</summary><pre>{html.escape(instagram.caption(ev, lang))}</pre></details></div></article>')
    delar.append("</main></body></html>")
    (PREVIEW / f"{lang}.html").write_text("".join(delar), encoding="utf-8")


def bygg_kort(lang):
    """Kort och captions för alla valda som saknar kort."""
    data = las(lang)
    for p in data["valda"]:
        dest = instagram.OUT / lang / p["id"]
        if (dest / "1.jpg").exists():
            continue
        instagram.render(p["ev"], dest, lang=lang)
        print(f"Kort: {lang} #{p['rank']} {p['rubrik'][:60]}")


def godkann(lang, uteslut=(), nu=None):
    """Godkänner batchen: tar bort uteslutna poster (rangordning eller id), arkiverar resten som granskade med sitt ursprungliga datum."""
    nu = time.time() if nu is None else nu
    data = las(lang)
    if not data:
        raise EjGodkand(f"ingen lansering vald för {lang}")
    ute = {str(u) for u in uteslut}
    kvar = [p for p in data["valda"] if str(p["rank"]) not in ute and p["id"] not in ute]
    for n, p in enumerate(kvar, 1):
        p["rank"] = n
    arkiv = newsletter.load_archive()
    for p in kvar:
        ev = {**p["ev"], "granskad": True, "godkand_tid": min(p["senast"], nu), "automatisk": False, "relevans": utgava.relevans(p["ev"])}
        arkiv[ev["id"]] = ev
    newsletter.ARKIV.parent.mkdir(parents=True, exist_ok=True)
    newsletter.ARKIV.write_text(json.dumps(arkiv, ensure_ascii=False, indent=1), encoding="utf-8")
    data.update(valda=kvar, godkand=True, godkand_tid=nu)
    _spara(lang, data)
    _forhandsgranskning(lang, data)
    return data


# ---------- Maraton ----------

def _git(*args):
    return subprocess.run(["git", *args], capture_output=True, text=True)


def git_spara(lang):
    """Sparar status i git direkt efter varje inlägg (bara i Actions, där LANSERING_GIT är satt)."""
    if not os.environ.get("LANSERING_GIT"):
        return
    _git("add", "data/lansering")
    _git("commit", "-m", f"Lansering {lang}: status {time.strftime('%Y-%m-%dT%H:%M', time.gmtime())}")
    for _ in range(4):
        if _git("pull", "--rebase", "-X", "theirs", "origin", "main").returncode == 0 and _git("push").returncode == 0:
            return
        time.sleep(3)
    print("Lansering: kunde inte pusha statusen", file=sys.stderr)


def tyst_nu():
    """Tyst läge lokalt eller i senaste versionen på main (nödstoppet kan slås på medan maratonet pågår)."""
    try:
        _git("fetch", "-q", "origin", "main")
        fjarr = json.loads(_git("show", "origin/main:data/autopilot.json").stdout or "{}")
        if fjarr.get("tyst"):
            return True
    except Exception:
        pass
    return bool(autopilot.load_settings().get("tyst"))


def kvot_nu(user, token):
    """Hur många inlägg kontot får publicera till, enligt Instagram själva. Okänt (None) om frågan misslyckas."""
    try:
        d = instagram._api(f"{user}/content_publishing_limit", {"fields": "quota_usage,config", "access_token": token}, method="GET")
        post = d["data"][0]
        return post.get("config", {}).get("quota_total", 100) - post.get("quota_usage", 0)
    except Exception:
        return None


def bild_finns_nu(url):
    try:
        req = urllib.request.Request(url, method="HEAD", headers={"User-Agent": "newsnavigator-lansering/1.0"})
        with urllib.request.urlopen(req, timeout=15) as r:
            return r.status == 200
    except Exception:
        return False


def _bilder(lang, eid):
    return sorted(f.name for f in (instagram.OUT / lang / eid).glob("*.jpg")) or ["1.jpg"]


def publicera_nu(lang, post, user, token):
    return instagram.publish_one(lang, post["id"], {"bilder": _bilder(lang, post["id"])}, user, token)


def maraton(lang, antal=1, intervall=8, torrt=False, budget_minuter=None, publicera=publicera_nu, sov=time.sleep, sparat=git_spara,
            tyst=tyst_nu, kvot=kvot_nu, bild_finns=bild_finns_nu, nu=time.time):
    """Postar upp till `antal` inlägg ur den godkända listan, i rangordning, med `intervall` minuter emellan.
    Returnerar {"postade", "kvar", "stopp", ...}. `stopp` är skälet till att körningen slutade i förtid, eller "klart"."""
    data = las(lang)
    if not data or not data.get("godkand"):
        raise EjGodkand(f"lanseringen för {lang} är inte godkänd")
    st = status(lang)
    kvar_lista = [p for p in data["valda"] if p["id"] not in st["postade"]]
    if torrt:
        return {"postade": 0, "kvar": len(kvar_lista), "stopp": None, "skulle_posta": [p["id"] for p in kvar_lista[:antal]]}
    user_var, token_var = instagram.KONTON[lang]
    user, token = os.environ.get(user_var), os.environ.get(token_var)
    ut = {"postade": 0, "kvar": len(kvar_lista), "stopp": None}
    if not (user and token):
        return {**ut, "stopp": "secrets saknas"}
    start, fel_i_rad = nu(), 0

    def klar(stopp):
        ut["stopp"] = stopp
        ut["kvar"] = len([p for p in data["valda"] if p["id"] not in st["postade"]])
        return ut
    for post in kvar_lista:
        if ut["postade"] >= antal:
            break
        if tyst():
            return klar("tyst läge")
        k = kvot(user, token)
        if k is not None and k <= KVOT_MARGINAL:
            return klar("kvoten nästan slut")
        url = f"{instagram.IMAGE_BASE}/ig/{lang}/{post['id']}/1.jpg"
        for forsok in range(3):
            if bild_finns(url):
                break
            sov(30)
        else:
            return klar("korten finns inte på sajten")
        try:
            ig_id = publicera(lang, post, user, token)
        except Exception as e:
            st["fel"].append({"id": post["id"], "ts": nu(), "fel": str(e)[:200]})
            _spara_status(lang, st)
            sparat(lang)
            fel_i_rad += 1
            if fel_i_rad >= FEL_I_RAD:
                return klar("tre fel i rad")
            sov(FEL_PAUS)
            continue
        fel_i_rad = 0
        st["postade"][post["id"]] = {"ts": nu(), "ig_id": ig_id, "rank": post["rank"]}
        _spara_status(lang, st)
        sparat(lang)
        ut["postade"] += 1
        print(f"Lansering {data['konto']}: postade #{post['rank']} {post['rubrik'][:60]} ({ig_id})")
        kvar_efter = [p for p in data["valda"] if p["id"] not in st["postade"] and p is not post]
        if ut["postade"] < antal and kvar_efter:
            if budget_minuter is not None and (nu() - start) + intervall * 60 > budget_minuter * 60:
                return klar("tidsbudgeten")
            sov(intervall * 60)
    return klar("klart" if not [p for p in data["valda"] if p["id"] not in st["postade"]] else ut["stopp"])


# ---------- Kommandorad ----------

def _konton(val):
    return list(instagram.UTGAVOR) if val == "alla" else [val]


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("kommando", choices=["valj", "godkann", "posta"])
    ap.add_argument("--konto", choices=["sv", "en", "alla"], default="alla")
    ap.add_argument("--antal", type=int, default=None)
    ap.add_argument("--intervall", type=int, default=8)
    ap.add_argument("--uteslut", default="")
    ap.add_argument("--torrt", action="store_true")
    ap.add_argument("--budget", type=int, default=None, help="minuter som körningen får pågå innan den lämnar över")
    a = ap.parse_args(argv)
    if a.kommando == "valj":
        stories = samla_vecka()
        print(f"Veckans berättelser: {len(stories)}")
        for lang in _konton(a.konto):
            valda = valj(stories, lang, antal=a.antal or ANTAL)
            skriv(lang, valda, stories, intervall=a.intervall)
            bygg_kort(lang)
            sek = {}
            for v in valda:
                sek[v["sektion"]] = sek.get(v["sektion"], 0) + 1
            print(f"{instagram.HANDTAG[lang]}: {len(valda)} valda, {sum(1 for v in valda if v['genomgang'])} kräver din genomgång, sektioner {sek}")
    elif a.kommando == "godkann":
        ute = [u.strip() for u in a.uteslut.split(",") if u.strip()]
        for lang in _konton(a.konto):
            d = godkann(lang, uteslut=ute)
            print(f"{d['konto']}: batchen godkänd, {len(d['valda'])} inlägg")
    else:
        for lang in _konton(a.konto):
            ut = maraton(lang, antal=a.antal or 1, intervall=a.intervall, torrt=a.torrt, budget_minuter=a.budget)
            print(f"{instagram.HANDTAG[lang]}: {json.dumps(ut, ensure_ascii=False)}")
            if ut.get("stopp") == "tidsbudgeten" and os.environ.get("GITHUB_OUTPUT"):
                with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as f:
                    f.write(f"fortsatt=true\nkonto={lang}\nrest={max(0, (a.antal or 1) - ut['postade'])}\n")


if __name__ == "__main__":
    main()
