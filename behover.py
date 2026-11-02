#!/usr/bin/env python3
"""Behöver dig: den enda listan över det som väntar på ett beslut, har gått sönder eller löper ut.

Listan byggs av regler (`regler`), inte av hand. Morgonrapporten kl 07.00 är samma lista som mejl, med en rad överst:
"Allt kört." när den är tom. Allvarliga rader (en körning som fallerat två gånger i rad, klockan som stannat,
en token som snart löper ut) mejlas direkt och upprepas efter tolv timmar om felet finns kvar.

  python behover.py                  räknar ut listan och skriver data/behover.json (pipelinen gör det varje timme)
  python behover.py --skicka         dessutom: mejla morgonrapport och varningar via Resend (workflowen rapport.yml)
  python behover.py --skicka --torrt skriv ut mejlet i stället för att skicka det

Secrets: RESEND_API_KEY och RAPPORT_TILL (mottagaren). Avsändare: NN_RAPPORT_FRAN, annars Resends testavsändare, som
bara når kontots egen adress tills en domän är verifierad.
"""
import argparse
import json
import os
import sys
import time
import urllib.parse
import urllib.request
from datetime import date, datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import yaml

import autopilot

ROOT = Path(__file__).parent
TZ = ZoneInfo("Europe/Stockholm")
DAGAR = ["måndag", "tisdag", "onsdag", "torsdag", "fredag", "lördag", "söndag"]
MANADER = ["januari", "februari", "mars", "april", "maj", "juni", "juli", "augusti", "september", "oktober", "november", "december"]
NAMN = {"pipeline": "Pipelinen", "instagram": "Instagram", "granskning": "Granskningen"}

VANTAR_TIMMAR = 2           # en notis som väntar längre än så hamnar på listan
TYST_DAGAR = 3              # en nyhetskälla som varit tyst så länge
TYST_DAGAR_PRIMAR = 14      # primärkällor, forskning och listor publicerar sällan
TOKEN_VARNING_DAGAR = 14
TOKEN_ALLVARLIG_DAGAR = 3
KLOCKA_MINUTER = 150        # pipelinen ska starta varje timme
BREV_MIN = 3
RAPPORT_TIMME = 7
OMVARNA_TIMMAR = 12
MAX_TYSTA = 5
MAX_HOPSLAGNA = 3
STANDARD_FRAN = "Newsnavigator <onboarding@resend.dev>"


def lokal(ts):
    return datetime.fromtimestamp(ts, TZ)


def _tid(ts, now):
    """14.17 samma dag, annars veckodag eller datum."""
    d, n = lokal(ts), lokal(now)
    klock = f"{d:%H.%M}"
    if d.date() == n.date():
        return klock
    if (n.date() - d.date()).days < 7:
        return f"{DAGAR[d.weekday()]} {klock}"
    return f"{d.day} {MANADER[d.month - 1]} {klock}"


def _dag(ts, now):
    """Veckodag för de senaste sex dygnen, annars datum."""
    d, n = lokal(ts), lokal(now)
    if 0 <= (n.date() - d.date()).days < 7:
        return DAGAR[d.weekday()]
    return f"{d.day} {MANADER[d.month - 1]}"


def _iso(text):
    return datetime.fromisoformat(text).timestamp()


def _plural(n, ental, flertal):
    return f"{n} {ental if n == 1 else flertal}"


def rad(kod, text, handling, url=None, allvarlig=False, id=None, detaljer=None):
    ut = {"kod": kod, "id": id or kod, "rad": text, "handling": handling, "url": url, "allvarlig": allvarlig}
    if detaljer:
        ut["detaljer"] = detaljer
    return ut


def arende_url(lage):
    return f"https://github.com/{lage['repo']}/issues?q=is%3Aissue+label%3Agranskning"


# ---------- Reglerna ----------

def _vantar(lage, now):
    godk, ko = lage["godkanda"], lage["status"].get("ko", {})
    stoppade = lage["status"].get("stoppade", {})
    aldst, titlar = {}, {}   # notiser i kön hålls tillbaka av taket med avsikt och är inget beslut åt dig
    for e in lage["flode"]:
        if e["id"] in godk or e["id"] in ko or e["id"] in stoppade:
            continue
        timmar = (e.get("vikt") or {}).get("timmar", 0)
        if e.get("maste") and timmar >= VANTAR_TIMMAR:
            aldst[e["id"]] = timmar
            titlar[e["id"]] = (e.get("utkast") or {}).get("rubrik_sv") or e.get("reserv_rubrik") or e["id"]
    if not aldst:
        return []
    n = len(aldst)
    aldsta = sorted(aldst, key=lambda i: aldst[i], reverse=True)[:3]
    return [rad("vantar", f"{_plural(n, 'notis väntar', 'notiser väntar')} på dig, äldst {round(max(aldst.values()))} h",
                "Till inkorgen", url=arende_url(lage), detaljer=[f"{titlar[i]} ({round(aldst[i])} h)" for i in aldsta])]


def _korningar(lage, now):
    hist = sorted(lage["drift"].get("historik", []), key=lambda k: k.get("start") or "", reverse=True)
    ut = []
    for wf in dict.fromkeys(k["workflow"] for k in hist):
        serie = [k for k in hist if k["workflow"] == wf and k["status"] != "avbruten"]
        fel = []
        for k in serie:
            if k["status"] != "fel":
                break
            fel.append(k)
        if len(fel) >= 2:
            ut.append(rad("korning", f"{NAMN.get(wf, wf)} har stannat sedan {_tid(_iso(fel[-1]['start']), now)}",
                          "Öppna loggen, kör igen", url=fel[0].get("url"), allvarlig=True, id=f"korning:{wf}"))
    pipe = [_iso(k["start"]) for k in hist if k["workflow"] == "pipeline" and k.get("start")]
    if pipe and now - max(pipe) > KLOCKA_MINUTER * 60:
        ut.append(rad("klocka", f"Klockan har stannat: senaste körningen startade {_tid(max(pipe), now)}",
                      "Kontrollera klockan (Cloudflare Worker) och kör pipelinen", allvarlig=True))
    return ut


def _hopslagna(lage, now):
    skuggade = lage["godkanda"] | set(lage["status"].get("stoppade", {}))
    traffar = [e for e in lage["flode"] if e["id"] not in skuggade
               and any("hopslagna" in s for s in autopilot.grindar(e))]
    traffar.sort(key=lambda e: e.get("poang", 0), reverse=True)
    return [rad("hopslagen", f"Troligen hopslagna händelser: {(e.get('utkast') or {}).get('rubrik_sv') or e.get('reserv_rubrik')}",
                "Dela upp eller avvisa", url=arende_url(lage), id=f"hopslagen:{e['id']}") for e in traffar[:MAX_HOPSLAGNA]]


def _tysta(lage, now):
    tyst = []
    for k in lage["kallstatus"].get("kallor", []):
        if not k.get("senaste"):
            continue
        typ = lage["kallor_typ"].get(k["id"], "media")
        grans = (TYST_DAGAR if typ == "media" else TYST_DAGAR_PRIMAR) * 86400
        ts = _iso(k["senaste"])
        if now - ts > grans:
            tyst.append((ts, k))
    tyst.sort(key=lambda x: x[0])
    ut = [rad("tyst", f"{k['namn']} tyst sedan {_dag(ts, now)}", "Kontrollera flödet, pausa", id=f"tyst:{k['id']}")
          for ts, k in tyst[:MAX_TYSTA]]
    if len(tyst) > MAX_TYSTA:
        kvar = len(tyst) - MAX_TYSTA
        ut.append(rad("tyst", f"och {kvar} {'källa till är tyst' if kvar == 1 else 'källor till är tysta'}", "Kontrollera källstatus", id="tyst:fler"))
    return ut


def _instagram(lage, now):
    ut = []
    for lang, handtag in (("sv", "@newsnavigator.se"), ("en", "@news.navigator")):
        s = (lage["instagram_status"] or {}).get(lang) or {}
        suffix = "_EN" if lang == "en" else ""
        if s.get("token_utgar"):
            utgar = date.fromisoformat(s["token_utgar"])
            dagar = (utgar - lokal(now).date()).days
            if dagar <= TOKEN_VARNING_DAGAR:
                dag = f"{utgar.day} {MANADER[utgar.month - 1]}"
                ut.append(rad("token", f"Instagram-token för {handtag} {'gick ut' if dagar < 0 else 'går ut'} {dag}", "Förnya",
                              allvarlig=dagar <= TOKEN_ALLVARLIG_DAGAR, id=f"token:{lang}"))
        if s.get("secrets") is False and s.get("vantar", 0) > 0:
            ut.append(rad("instagram", f"{handtag} postar inget: secrets saknas, {s['vantar']} kort väntar",
                          f"Lägg in IG_USER_ID{suffix} och IG_ACCESS_TOKEN{suffix} i repots secrets", id=f"instagram:{lang}"))
        elif s.get("secrets") and s.get("fel"):
            ut.append(rad("instagram", f"{handtag} misslyckades: {s['fel']}", "Öppna loggen och kontrollera token", id=f"instagram:{lang}"))
    return ut


def _brev(lage, now):
    if not lage["installningar"].get("navigatorn"):
        return []
    n = sum(1 for p in lage["arkiv"].values() if now - p.get("godkand_tid", 0) < 86400)
    if n < BREV_MIN:
        return [rad("brev", f"Navigatorn har bara {n} notiser i dag, minst {BREV_MIN} krävs", "Godkänn fler i ärendet",
                    url=arende_url(lage))]
    return []


def _tyst_lage(lage, now):
    if lage["installningar"].get("tyst"):
        return [rad("tyst_lage", "Tyst läge är på: inget publiceras automatiskt och Instagram postar inte",
                    "Slå av i data/autopilot.json", id="tyst_lage")]
    return []


def _rattelser(lage, now):
    return [rad("rattelse", f"Rättelse: {r['rubrik']}", "Öppna notisen", url=r.get("url"), id=f"rattelse:{r.get('url') or r['rubrik']}")
            for r in lage["rattelser"]]


def regler(lage, now):
    """Listan över det som behöver redaktören. Allvarliga rader först, annars i reglernas ordning."""
    rader = []
    for regel in (_vantar, _korningar, _hopslagna, _tysta, _instagram, _brev, _tyst_lage, _rattelser):
        rader += regel(lage, now)
    return sorted(rader, key=lambda r: not r["allvarlig"])


# ---------- Rapport och varning ----------

def _rader_text(rader):
    ut = []
    for n, r in enumerate(rader, 1):
        ut.append(f"{n}. {r['rad']}")
        ut += [f"   - {d}" for d in r.get("detaljer", [])]
        ut.append(f"   Gör: {r['handling']}")
        if r.get("url"):
            ut.append(f"   {r['url']}")
    return ut


def rapport(rader, lage, now):
    """(ämne, text) för morgonrapporten."""
    pub = [eid for eid, t in lage["status"].get("publicerade", {}).items() if now - t < 86400]
    ko = len(lage["status"].get("ko", {}))
    pub_text = ("Inga notiser publicerades automatiskt senaste dygnet" if not pub
                else f"{_plural(len(pub), 'notis publicerades', 'notiser publicerades')} automatiskt senaste dygnet")
    ko_text = "ingen väntar i kön" if ko == 0 else f"{ko} väntar i kön"
    if rader:
        amne = f"Newsnavigator: {_plural(len(rader), 'sak', 'saker')} behöver dig"
        text = [f"{_plural(len(rader), 'sak', 'saker')} behöver dig.", ""] + _rader_text(rader)
    else:
        amne = "Newsnavigator: allt kört"
        text = [f"Allt kört. Inget behöver dig. {pub_text}, {ko_text}."]
    if pub and rader:
        text += ["", f"{pub_text}, {ko_text}."]
    if pub:
        site = os.environ.get("NN_SITE_URL", "https://newsnavigator.se").rstrip("/")
        text += ["", "Publicerat automatiskt:"]
        for eid in pub:
            titel = (lage["arkiv"].get(eid, {}).get("utkast") or {}).get("rubrik_sv") or eid
            text.append(f"- {titel} {site}/sv/n/{eid}/")
    kallor = lage["kallstatus"].get("kallor", [])
    if kallor:
        text += ["", f"Källor: {sum(1 for k in kallor if k.get('status') == 'ok')} av {len(kallor)} går att läsa."]
    text += ["", "Det här mejlet kommer varje morgon kl 07.00. Är listan tom behöver du inte öppna något."]
    return amne, "\n".join(text) + "\n"


def varning(rader):
    amne = "Newsnavigator: något har gått sönder"
    text = ["Det här behöver dig nu:", ""] + _rader_text(rader) + [
        "", "Varningen kommer direkt när en körning fallerat två gånger i rad eller klockan stannat, "
            "och upprepas efter tolv timmar om felet finns kvar."]
    return amne, "\n".join(text) + "\n"


def beslut(state, rader, now):
    """Vad som ska mejlas nu: morgonrapporten en gång per dag efter 07.00, varningar en gång och igen efter tolv timmar."""
    l = lokal(now)
    allvarliga = [r for r in rader if r["allvarlig"]]
    varnade = state.get("varnade", {})
    varna = [r for r in allvarliga if now - varnade.get(r["id"], 0) >= OMVARNA_TIMMAR * 3600]
    return {"rapport": l.hour >= RAPPORT_TIMME and state.get("rapport_datum") != l.date().isoformat(),
            "varna": varna, "allvarliga": [r["id"] for r in allvarliga], "idag": l.date().isoformat()}


def markera(state, besked, now):
    """Ny status efter ett varv: sänd rapport och varningar noteras, varningar för fel som försvunnit rensas."""
    ny = dict(state)
    if besked["rapport"]:
        ny["rapport_datum"] = besked["idag"]
    varnade = {i: t for i, t in state.get("varnade", {}).items() if i in besked["allvarliga"]}
    for r in besked["varna"]:
        varnade[r["id"]] = now
    ny["varnade"] = varnade
    return ny


def skicka(amne, text, till, fran, key):
    req = urllib.request.Request(
        "https://api.resend.com/emails", method="POST",
        data=json.dumps({"from": fran, "to": [till], "subject": amne, "text": text}, ensure_ascii=False).encode("utf-8"),
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json", "User-Agent": "newsnavigator-rapport/1.0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())


# ---------- Läget ur repot ----------

def _las(path, standard):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return standard


def hamta_rattelser(miljo):
    """Öppna ärenden märkta rättelse. Utan GITHUB_TOKEN eller vid fel: inga."""
    token, repo = miljo.get("GITHUB_TOKEN"), miljo.get("GITHUB_REPOSITORY")
    if not (token and repo):
        return []
    url = f"https://api.github.com/repos/{repo}/issues?labels={urllib.parse.quote('rättelse')}&state=open&per_page=10"
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json",
                                               "User-Agent": "newsnavigator-rapport/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            data = json.loads(r.read())
    except Exception as e:
        print(f"Rättelser kunde inte hämtas: {e}", file=sys.stderr)
        return []
    return [{"rubrik": i["title"].removeprefix("Rättelse:").strip(), "url": i["html_url"]} for i in data if "pull_request" not in i]


def laddar_lage(root, repo, rattelser):
    d = Path(root) / "data"
    feeds = _las(Path(root) / "feeds.yaml", None)
    if feeds is None:
        try:
            feeds = yaml.safe_load((Path(root) / "feeds.yaml").read_text(encoding="utf-8"))
        except (OSError, yaml.YAMLError):
            feeds = {}
    return {"repo": repo,
            "flode": _las(d / "flode.json", {}).get("handelser", []),
            "godkanda": set(_las(d / "godkanda.json", [])),
            "status": autopilot.load_status(d / "autopilot_status.json"),
            "installningar": autopilot.load_settings(d / "autopilot.json"),
            "drift": _las(d / "drift.json", {}),
            "kallstatus": _las(d / "kallstatus.json", {"kallor": []}),
            "kallor_typ": {s["id"]: s.get("typ", "media") for s in (feeds or {}).get("sources", [])},
            "arkiv": _las(d / "arkiv.json", {}),
            "instagram": {lang: _las(d / "instagram" / f"{lang}.json", {}) for lang in ("sv", "en")},
            "instagram_status": {lang: _las(d / "instagram" / f"status-{lang}.json", {}) for lang in ("sv", "en")},
            "rattelser": rattelser}


def main(argv=None, root=ROOT, now=None, miljo=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--skicka", action="store_true", help="mejla morgonrapport och varningar")
    ap.add_argument("--torrt", action="store_true", help="skriv ut mejlen i stället för att skicka dem")
    args = ap.parse_args(argv)
    miljo = os.environ if miljo is None else miljo
    now = time.time() if now is None else now
    root = Path(root)

    lage = laddar_lage(root, miljo.get("GITHUB_REPOSITORY", "fabsaku/newsnavigator-pipeline"), hamta_rattelser(miljo))
    rader = regler(lage, now)
    amne, text = rapport(rader, lage, now)
    (root / "data").mkdir(exist_ok=True)
    (root / "data" / "behover.json").write_text(json.dumps(
        {"skapad": datetime.fromtimestamp(now, timezone.utc).isoformat(), "rader": rader, "rapport": {"amne": amne, "text": text}},
        ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"Behöver dig: {len(rader)} rader")
    for r in rader:
        print(f"  {r['rad']} ({r['handling']})")
    if not args.skicka:
        return rader

    state_path = root / "data" / "rapport.json"
    state = _las(state_path, {})
    besked = beslut(state, rader, now)
    post = []
    if besked["rapport"]:
        post.append((amne, text))
    if besked["varna"]:
        post.append(varning(besked["varna"]))
    if args.torrt:
        for a, t in post:
            print(f"\n--- {a}\n{t}")
        return rader
    key, till = miljo.get("RESEND_API_KEY"), miljo.get("RAPPORT_TILL")
    if post and not (key and till):
        print("RESEND_API_KEY eller RAPPORT_TILL saknas, mejlet skickas inte")
        besked = {**besked, "rapport": False, "varna": []}
    elif post:
        for a, t in post:
            skicka(a, t, till=till, fran=miljo.get("NN_RAPPORT_FRAN") or STANDARD_FRAN, key=key)
            print(f"Skickade: {a}")
    ny = markera(state, besked, now)
    if ny != state:
        state_path.write_text(json.dumps(ny, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return rader


if __name__ == "__main__":
    main()
