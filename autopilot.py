#!/usr/bin/env python3
"""Autopiloten: vad som får publiceras utan redaktören.

Grindarna (`grindar`) avgör om en notis får gå automatiskt. Den som klarar dem läggs i en kö med ett
klockslag, vetofönstret: står den kvar när tiden gått ut godkänns den av sig själv, högst `tak` per dygn.
Tills panelen finns är granskningsärendet vetofönstret: kön visas där med klockslag, och en urbockad
notis stoppas. Allt som publicerats automatiskt märks så och går att ångra.

  python autopilot.py angra <id>     tar bort en notis ur godkända och arkivet, och spärrar den

Inställningar i data/autopilot.json (skrivs av dig eller panelen):
  pa, tyst, tak, tak_efter_forsta_veckan, vetofonster_minuter
Status i data/autopilot_status.json (skrivs av pipelinen): ko, publicerade, stoppade, startad.
"""
import json
import os
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).parent
INSTALLNINGAR = ROOT / "data" / "autopilot.json"
STATUS = ROOT / "data" / "autopilot_status.json"
GODK = ROOT / "data" / "godkanda.json"
ARKIV = ROOT / "data" / "arkiv.json"

STANDARD = {"pa": False, "tyst": False, "tak": 2, "tak_efter_forsta_veckan": 8, "vetofonster_minuter": 45,
            "navigatorn": False}   # sant när brevet skickas: då kräver Behöver dig minst tre notiser
FORSTA_VECKAN = 7 * 86400
MAX_KALLOR, MAX_SEKTIONER = 20, 3

# Ord som alltid skickar notisen till redaktören: brottmål med namngivna personer, självmord, sexualbrott, barn.
# Hela ord; * betyder ordstam.
SPARRORD = """
misstänkt* åtalad* åtalas anhållen anhölls anhålls häktad* häktas häkte* gripen gripits grips greps dömd* döms
åklagare* tingsrätt* polisanmäl*
mord* mördad* mördare knivskuren
självmord* suicid*
våldtäkt* våldtagen våldtog sexualbrott* sexuellt övergrepp* pedofil* barnporr*
barn barnet barnen barns barnens flicka flickan pojke pojken
suicide* rape* raped sexual pedophil* paedophil* molest*
child children child's kids boy girl teenager* toddler* infant*
charged indicted arrested arrest suspect suspected convicted sentenced murder* killer stabbed
""".split()
_SPARR = re.compile(r"\b(?:" + "|".join(re.escape(w.rstrip("*")) + (r"\w*" if w.endswith("*") else "") for w in SPARRORD) + r")\b", re.I)

# Sektionerna delas med brevet och sajten; importeras sent för att undvika importcirklar.


def _sektioner(ev):
    from newsletter import SECTIONS
    amnen = set(ev.get("amnen_sektion") or [])
    return {k for k, _, _, tags in SECTIONS if amnen & tags}


def _svensk_inrikes(oberoende, sektioner):
    """Svensk inrikesnyhet: bara nordiska källor, minst två svenska, och inte nöje eller utrikes. Den kan inte nå flera regioner
    och har sällan tre källor, så två svenska källor räcker. Övriga grindar, som spärrorden, gäller som vanligt."""
    return ({s.get("region") for s in oberoende} <= {"sverige", "norden"} and not sektioner & {"noje", "varlden"}
            and sum(1 for s in oberoende if s.get("region") == "sverige") >= 2)


def grindar(ev):
    """Skälen till att en notis inte får publiceras automatiskt. Tom lista betyder att den klarar grindarna."""
    skal = []
    d = ev.get("utkast") or {}
    k = ev.get("kallkontroll")
    if not d.get("rubrik_sv") or not d.get("sammanfattning_sv"):
        skal.append("inget utkast")
    elif d.get("osaker"):
        skal.append("utkastet är märkt osäkert")
    if not k:
        skal.append("ingen källkontroll")
    elif not k.get("ok"):
        skal.append(f"källkontrollen har {len(k.get('problem') or [])} anmärkningar")

    kallor = ev.get("kallor") or []
    oberoende = [s for s in kallor if s.get("typ") != "kuraterat" and not s.get("statskontrollerad")]
    sektioner = _sektioner(ev)
    inrikes = _svensk_inrikes(oberoende, sektioner)
    if len(oberoende) < 3 and not inrikes:
        skal.append(f"färre än tre oberoende källor ({len(oberoende)})")
    if len({s.get("region") for s in oberoende}) < 2 and not inrikes:
        skal.append("bara en region")
    if "sverige" in sektioner and sum(1 for s in oberoende if s.get("region") == "sverige") < 2:
        skal.append("färre än två svenska källor")
    if len(kallor) > MAX_KALLOR or len(sektioner) > MAX_SEKTIONER:
        skal.append("troligen hopslagna händelser")

    texter = [d.get("rubrik_sv"), d.get("sammanfattning_sv"), d.get("rubrik_en"), d.get("sammanfattning_en")]
    texter += [s.get("rubrik") for s in kallor]
    traffar = sorted({m.group(0).lower() for t in texter if t for m in _SPARR.finditer(t)})
    if traffar:
        skal.append("spärrord: " + ", ".join(traffar[:5]))

    p = ev.get("perspektiv") or {}
    # "Bara i svenska medier" är normalläget för inrikes, inte ett påstående att kontrollera.
    if (p.get("blind_flack") and not (inrikes and p["blind_flack"] == "bara_i_sverige")) or p.get("usa_blind"):
        skal.append("blind fläck")
    return skal


def load_settings(path=None):
    path = INSTALLNINGAR if path is None else path
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        data = {}
    return {**STANDARD, **{k: v for k, v in data.items() if k in STANDARD}}


def tom_status():
    return {"ko": {}, "publicerade": {}, "stoppade": {}, "startad": None}


def load_status(path=None):
    path = STATUS if path is None else path
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        data = {}
    return {**tom_status(), **data}


def save_status(status, path=None):
    path = STATUS if path is None else path
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(status, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


def effektivt_tak(settings, status, now):
    """Taket är lågt första veckan efter att autopiloten slogs på, sedan det vanliga."""
    startad = status.get("startad")
    if startad and now - startad >= FORSTA_VECKAN:
        return settings.get("tak_efter_forsta_veckan", settings["tak"])
    return settings["tak"]


def kor(events, approved, settings, status, now=None):
    """Ett varv: lägg notiser som klarar grindarna i kön, och godkänn dem vars fönster gått ut.
    Returnerar de id som godkänts automatiskt i detta varv. `status` ändras på plats."""
    now = time.time() if now is None else now
    if not settings.get("pa"):
        return set()
    status.setdefault("ko", {}); status.setdefault("publicerade", {}); status.setdefault("stoppade", {})
    if not status.get("startad"):
        status["startad"] = now
    i_flodet = {e["id"]: e for e in events}
    fonster = settings["vetofonster_minuter"] * 60

    for eid in list(status["ko"]):
        if eid not in i_flodet or eid in approved or eid in status["stoppade"]:
            status["ko"].pop(eid)
    for ev in events:
        eid = ev["id"]
        if eid in approved or eid in status["ko"] or eid in status["publicerade"] or eid in status["stoppade"]:
            continue
        if grindar(ev):
            continue
        status["ko"][eid] = {"tillagd": now, "klar": now + fonster,
                             "rubrik": (ev.get("utkast") or {}).get("rubrik_sv") or ev["reserv_rubrik"]}

    nya = set()
    if settings.get("tyst"):
        return nya
    senaste_dygnet = sum(1 for t in status["publicerade"].values() if now - t < 86400)
    tak = effektivt_tak(settings, status, now)
    mogna = sorted((eid for eid, post in status["ko"].items() if post["klar"] <= now),
                   key=lambda eid: i_flodet[eid].get("poang", 0), reverse=True)
    for eid in mogna:
        if senaste_dygnet >= tak:
            break
        if grindar(i_flodet[eid]):      # notisen kan ha ändrats medan den väntade
            status["ko"].pop(eid)
            continue
        status["ko"].pop(eid)
        status["publicerade"][eid] = now
        nya.add(eid)
        senaste_dygnet += 1
    return nya


def automatiska(status=None):
    """Id för allt som publicerats automatiskt."""
    return set((status or load_status())["publicerade"])


def angra(eid, now=None):
    """Tar bort en notis ur godkända och arkivet, spärrar den, och tar bort Instagram-inlägget om det går."""
    now = time.time() if now is None else now
    godk = set(json.loads(GODK.read_text(encoding="utf-8"))) if GODK.exists() else set()
    godk.discard(eid)
    GODK.write_text(json.dumps(sorted(godk), indent=2), encoding="utf-8")
    try:
        arkiv = json.loads(ARKIV.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        arkiv = {}
    arkiv.pop(eid, None)
    ARKIV.write_text(json.dumps(arkiv, ensure_ascii=False, indent=1), encoding="utf-8")
    status = load_status()
    status["ko"].pop(eid, None)
    status["stoppade"][eid] = now
    save_status(status)
    import instagram
    for lang, (_, token_var) in instagram.KONTON.items():
        post = instagram.load_state(lang).get(eid) or {}
        if post.get("ig_id") and os.environ.get(token_var):
            try:
                instagram._api(post["ig_id"], {"access_token": os.environ[token_var]}, method="DELETE")
                print(f"Instagram {instagram.HANDTAG[lang]}: tog bort inlägget {post['ig_id']}")
            except Exception as e:  # Instagram tillåter inte alltid borttagning via API:t
                print(f"Instagram {instagram.HANDTAG[lang]}: kunde inte ta bort {post['ig_id']}: {e}", file=sys.stderr)
    print(f"Ångrat: {eid} är borttagen ur godkända och arkivet och spärrad för autopiloten.")


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "angra":
        angra(sys.argv[2])
    else:
        print(__doc__)
