#!/usr/bin/env python3
"""Granskning i ett GitHub-ärende, så att redaktören kan godkänna från mobilen.

  python granskning_github.py las          läs bockarna i ärendet och uppdatera data/godkanda.json
  python granskning_github.py uppdatera    skriv om ärendet med dagens utkast (behåller bockar)

Kräver GITHUB_TOKEN och GITHUB_REPOSITORY (finns automatiskt i GitHub Actions).
En bock = godkänd. En borttagen bock = godkännandet ångras.
Autopilotens kö visas förbockad med klockslag: bocken är inget godkännande, men en urbockad notis stoppas.
"""
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

import autopilot

ROOT = Path(__file__).parent
FLODE = ROOT / "data" / "flode.json"
GODK = ROOT / "data" / "godkanda.json"
ARKIV = ROOT / "data" / "arkiv.json"
BOCKAR = ROOT / "data" / "bockar.json"   # vad redaktören sett i ärendet: rubrik och källor per id, så att id:t kan hållas
BOCKAR_DAGAR = 7
LABEL = "granskning"
MARK = "<!-- newsnavigator-granskning -->"
LINE = re.compile(r"^- \[([ xX])\] .*`([0-9a-f]{10})`", re.M)
ITEM = re.compile(r"^- \[([ xX])\] (.*?)`([0-9a-f]{10})`\n((?:  .*\n?)*)", re.M)
TITLE = re.compile(r"\*\*(.+?)\*\*")
LINK = re.compile(r"\]\((https?://[^)\s]+)\)")
MAX = 40


def api(method, path, body=None):
    repo, token = os.environ["GITHUB_REPOSITORY"], os.environ["GITHUB_TOKEN"]
    req = urllib.request.Request(
        f"https://api.github.com/repos/{repo}{path}", method=method,
        data=json.dumps(body).encode() if body is not None else None,
        headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json",
                 "X-GitHub-Api-Version": "2022-11-28", "User-Agent": "newsnavigator"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read() or b"null")


def find_issue():
    issues = api("GET", f"/issues?labels={LABEL}&state=open&per_page=5") or []
    return next((i for i in issues if MARK in (i.get("body") or "")), None)


def approved():
    return set(json.loads(GODK.read_text())) if GODK.exists() else set()


def save_approved(ok):
    GODK.write_text(json.dumps(sorted(ok), indent=2))


def parse_items(body):
    """Ärendets rader: per id bocken, rubriken och källornas adresser."""
    out = {}
    for m in ITEM.finditer(body or ""):
        head, rest = m.group(2), m.group(4)
        title = TITLE.search(head)
        urls = []
        for rad in rest.splitlines():
            if rad.strip().startswith("Källor:"):
                urls = LINK.findall(rad)
        out[m.group(3)] = {"bock": m.group(1).lower() == "x", "rubrik": title.group(1).strip() if title else "", "urls": urls}
    return out


def save_items(items, now=None):
    """Sparar vad redaktören sett, i sju dagar, så att pipelinen kan ge en ändrad händelse samma id igen."""
    now = time.time() if now is None else now
    try:
        data = json.loads(BOCKAR.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        data = {}
    for i, post in items.items():
        data[i] = {"rubrik": post["rubrik"], "urls": post["urls"], "sedd": now}
    data = {i: p for i, p in data.items() if now - p.get("sedd", 0) < BOCKAR_DAGAR * 86400}
    BOCKAR.parent.mkdir(parents=True, exist_ok=True)
    BOCKAR.write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


def tillampa_bockar(ticks, ok, status):
    """Bockarna i ärendet mot godkända och autopilotens status. Returnerar (godkända, nya, ångrade).
    En notis i autopilotens kö: bock = väntar kvar, urbockad = stoppad. En ångrad notis spärras för autopiloten."""
    ko = status.setdefault("ko", {})
    stoppade = status.setdefault("stoppade", {})
    now = time.time()
    for i, on in ticks.items():
        if i in ko and not on:
            ko.pop(i)
            stoppade[i] = now
    added = {i for i, on in ticks.items() if on and i not in ko} - ok
    removed = {i for i, on in ticks.items() if not on} & ok
    for i in removed:
        stoppade[i] = now
    return (ok | added) - removed, added, removed


def read_ticks():
    issue = find_issue()
    if not issue:
        print("Inget granskningsärende än.")
        return
    ticks = {m.group(2): m.group(1).lower() == "x" for m in LINE.finditer(issue["body"] or "")}
    save_items(parse_items(issue["body"]))
    status = autopilot.load_status()
    ok, added, removed = tillampa_bockar(ticks, approved(), status)
    save_approved(ok)
    autopilot.save_status(status)
    # Arkivera nya godkännanden direkt, och ta bort ångrade ur arkivet
    from newsletter import archive, load_archive
    if FLODE.exists():
        archive(json.loads(FLODE.read_text(encoding="utf-8"))["handelser"], ok)
    if removed:
        arkiv = load_archive()
        for i in removed:
            arkiv.pop(i, None)
        ARKIV.write_text(json.dumps(arkiv, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"Granskning: {len(added)} nya godkända, {len(removed)} ångrade, {len(ok)} totalt")


def _clean(s):
    return (s or "").replace("\n", " ").replace("|", "/").strip()


def _item(ev, checked):
    d = ev.get("utkast") or {}
    p = ev.get("perspektiv") or {}
    title = _clean(d.get("rubrik_sv") or ev["reserv_rubrik"])
    regs = len(p.get("regioner", []))
    meta = f"{ev['antal_kallor']} källor, {regs} regioner, vikt {ev.get('poang', 0)}"
    v = ev.get("vikt") or {}
    kons = v.get("konsekvens")
    if kons:
        meta += f" (konsekvens {kons['medel']}, {v.get('timmar', 1)} h i flödet)"
    k = ev.get("kallkontroll")
    flag = ("❗ Måste med · " if ev.get("maste") else "") + ("" if not k or k["ok"] else "⚠️ ")
    out = [f"- [{'x' if checked else ' '}] {flag}**{title}** · {meta} · `{ev['id']}`"]
    if k and not k["ok"]:
        out.append(f"  **KÄLLKONTROLL, {len(k['problem'])} anmärkningar:** " + " · ".join(_clean(x) for x in k["problem"][:4]))
    elif k:
        out.append(f"  Källkontroll: alla {k['antal']} påståenden spårade till källorna.")
    if d.get("osaker"):
        out.append(f"  **OSÄKER:** {_clean(d.get('kommentar'))}")
    if d.get("sammanfattning_sv"):
        out.append(f"  {_clean(d['sammanfattning_sv'])}")
    if d.get("perspektiv_sv") and regs >= 2:
        out.append(f"  *Så ser världen på det:* {_clean(d['perspektiv_sv'])}")
    if d.get("usa_sv") and p.get("usa"):
        out.append(f"  *USA, blått och rött:* {_clean(d['usa_sv'])}")
    if d.get("oenighet"):
        out.append(f"  *Källorna skiljer sig åt:* {_clean(d['oenighet'])}")
    srcs = ", ".join(f"[{_clean(s['namn'])}]({s['url']})" for s in ev["kallor"][:6])
    more = f" och {len(ev['kallor']) - 6} till" if len(ev["kallor"]) > 6 else ""
    out.append(f"  Källor: {srcs}{more}")
    return "\n".join(out)


def _ko_rad(ev, post):
    from zoneinfo import ZoneInfo
    klar = datetime.fromtimestamp(post["klar"], ZoneInfo("Europe/Stockholm")).strftime("%H.%M")
    return f"- [x] ⏱ publiceras {klar} om du inte bockar ur · {_item(ev, False)[6:]}"


def update_issue():
    data = json.loads(FLODE.read_text(encoding="utf-8"))
    ok = approved()
    status = autopilot.load_status()
    ko = {i: p for i, p in status["ko"].items() if i not in ok}
    todo = [e for e in data["handelser"] if e["id"] not in ok and e["id"] not in ko][:MAX]
    vantar = [e for e in data["handelser"] if e["id"] in ko]
    done = [e for e in data["handelser"] if e["id"] in ok]
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")
    body = [MARK,
            "Bocka i de notiser som får publiceras. Sajten och Navigatorn uppdateras inom ett par minuter. "
            "Ta bort en bock för att ångra. Läs källorna innan du godkänner, särskilt notiser märkta OSÄKER.",
            "", f"Uppdaterad {now} UTC · {len(todo)} att granska · {len(vantar)} publiceras automatiskt · {len(done)} godkända i flödet", ""]
    if vantar:
        body += ["### Publiceras automatiskt", "Klarar grindarna. Bocka ur för att stoppa; bocken är inget godkännande.", ""]
        body += [_ko_rad(e, ko[e["id"]]) for e in vantar] + [""]
    body += ["### Att granska", ""]
    body += [_item(e, False) for e in todo] or ["Inget nytt att granska."]
    if done:
        auto = autopilot.automatiska(status)
        body += ["", "### Godkända", ""] + [_item(e, True) + ("\n  Publicerad automatiskt." if e["id"] in auto else "") for e in done]
    text = "\n".join(body)[:65000]
    issue = find_issue()
    if issue:
        api("PATCH", f"/issues/{issue['number']}", {"body": text})
        print(f"Granskningsärende #{issue['number']} uppdaterat")
    else:
        try:
            api("POST", "/labels", {"name": LABEL, "color": "111111", "description": "Newsnavigators granskning"})
        except urllib.error.HTTPError:
            pass  # etiketten finns redan
        new = api("POST", "/issues", {"title": "Granskning: dagens utkast", "body": text, "labels": [LABEL]})
        print(f"Granskningsärende #{new['number']} skapat")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "las":
        read_ticks()
    elif cmd == "uppdatera":
        update_issue()
    else:
        print(__doc__)
