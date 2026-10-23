#!/usr/bin/env python3
"""Granskning i ett GitHub-ärende, så att redaktören kan godkänna från mobilen.

  python granskning_github.py las          läs bockarna i ärendet och uppdatera data/godkanda.json
  python granskning_github.py uppdatera    skriv om ärendet med dagens utkast (behåller bockar)

Kräver GITHUB_TOKEN och GITHUB_REPOSITORY (finns automatiskt i GitHub Actions).
En bock = godkänd. En borttagen bock = godkännandet ångras.
"""
import json
import os
import re
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).parent
FLODE = ROOT / "data" / "flode.json"
GODK = ROOT / "data" / "godkanda.json"
ARKIV = ROOT / "data" / "arkiv.json"
LABEL = "granskning"
MARK = "<!-- newsnavigator-granskning -->"
LINE = re.compile(r"^- \[([ xX])\] .*`([0-9a-f]{10})`", re.M)
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


def read_ticks():
    issue = find_issue()
    if not issue:
        print("Inget granskningsärende än.")
        return
    ticks = {m.group(2): m.group(1).lower() == "x" for m in LINE.finditer(issue["body"] or "")}
    ok = approved()
    added = {i for i, on in ticks.items() if on} - ok
    removed = {i for i, on in ticks.items() if not on} & ok
    ok = (ok | added) - removed
    save_approved(ok)
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
    meta = f"{ev['antal_kallor']} källor, {regs} regioner"
    out = [f"- [{'x' if checked else ' '}] **{title}** · {meta} · `{ev['id']}`"]
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


def update_issue():
    data = json.loads(FLODE.read_text(encoding="utf-8"))
    ok = approved()
    todo = [e for e in data["handelser"] if e["id"] not in ok][:MAX]
    done = [e for e in data["handelser"] if e["id"] in ok]
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")
    body = [MARK,
            "Bocka i de notiser som får publiceras. Sajten och Navigatorn uppdateras inom ett par minuter. "
            "Ta bort en bock för att ångra. Läs källorna innan du godkänner, särskilt notiser märkta OSÄKER.",
            "", f"Uppdaterad {now} UTC · {len(todo)} att granska · {len(done)} godkända i flödet", "",
            "### Att granska", ""]
    body += [_item(e, False) for e in todo] or ["Inget nytt att granska."]
    if done:
        body += ["", "### Godkända", ""] + [_item(e, True) for e in done]
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
