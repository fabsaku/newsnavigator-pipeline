#!/usr/bin/env python3
"""Prövar nya källor innan de läggs i feeds.yaml: får vår bot läsa flödet enligt robots.txt, och går det att läsa?

  python kallprov.py https://exempel.se/rss.xml [fler adresser]

Körs i GitHub Actions (workflowen kallprov.yml), eftersom sandboxen sällan når flödena. Skriver inget till repot.
Flödet hämtas bara om robots.txt tillåter det.
"""
import re
import sys
import time
import urllib.error
import urllib.request
from urllib.parse import urlsplit

from pipeline import AGENT, fetch_one

from pathlib import Path

ROOT = Path(__file__).parent
BOT = "NewsnavigatorBot"
# Utgivare som stänger ute AI-botar har sagt något om hur de vill att texten används, även när vår bot är tillåten.
AI_BOTAR = ["anthropic-ai", "ClaudeBot", "Claude-Web", "GPTBot", "ChatGPT-User", "Google-Extended", "CCBot",
            "PerplexityBot", "Applebot-Extended", "Bytespider", "meta-externalagent"]


def _grupper(text):
    """robots.txt som lista av (user-agents, regler), regler som (allow, sökväg)."""
    grupper, agenter, regler = [], [], []
    for rad in text.splitlines():
        rad = rad.split("#", 1)[0].strip()
        if ":" not in rad:
            continue
        falt, varde = (d.strip() for d in rad.split(":", 1))
        falt = falt.lower()
        if falt == "user-agent":
            if regler:
                grupper.append((agenter, regler))
                agenter, regler = [], []
            agenter.append(varde.lower())
        elif falt in ("allow", "disallow") and agenter:
            regler.append((falt == "allow", varde))
    if agenter:
        grupper.append((agenter, regler))
    return grupper


def _traffar(monster, sokvag):
    regex = "".join(".*" if c == "*" else re.escape(c) for c in monster.rstrip("$"))
    return re.match(regex + ("$" if monster.endswith("$") else ""), sokvag) is not None


def _beslut(grupper, agent, sokvag):
    """Enligt RFC 9309: den egna gruppen före *, och den längsta matchande regeln avgör (Allow vid lika)."""
    namn = agent.lower()
    regler = [r for ag, rr in grupper if namn in ag for r in rr]
    grupp = agent
    if not any(namn in ag for ag, _ in grupper):
        regler = [r for ag, rr in grupper if "*" in ag for r in rr]
        grupp = "*"
    traffar = [(len(p), allow, p) for allow, p in regler if p and _traffar(p, sokvag)]
    if not traffar:
        return True, None
    _, allow, monster = max(traffar, key=lambda t: (t[0], t[1]))
    return allow, f"User-agent: {grupp} / {'Allow' if allow else 'Disallow'}: {monster}"


def robots_besked(text, url, agent=BOT):
    parts = urlsplit(url)
    sokvag = (parts.path or "/") + (f"?{parts.query}" if parts.query else "")
    grupper = _grupper(text)
    tillaten, regel = _beslut(grupper, agent, sokvag)
    return {"tillaten": tillaten, "regel": regel,
            "ai_blockerade": sorted((a for a in AI_BOTAR if not _beslut(grupper, a, "/")[0]), key=str.lower)}


def hamta_robots(url):
    parts = urlsplit(url)
    req = urllib.request.Request(f"{parts.scheme}://{parts.netloc}/robots.txt", headers={"User-Agent": AGENT})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return r.read().decode("utf-8", errors="replace"), None
    except urllib.error.HTTPError as e:
        if 400 <= e.code < 500:
            return "", None     # ingen robots.txt betyder inga regler
        return None, f"HTTP {e.code}"
    except Exception as e:
        return None, str(e)[:120]


def prova(url):
    print(f"\n== {url}")
    text, fel = hamta_robots(url)
    if text is None:
        print(f"   robots.txt: kunde inte läsas ({fel}). Flödet hämtas inte.")
        return
    besked = robots_besked(text, url)
    print(f"   robots.txt: {'tillåter' if besked['tillaten'] else 'BLOCKERAR'} {BOT}"
          + (f" (regel {besked['regel']})" if besked["regel"] else "")
          + (f"; blockerar AI-botar: {', '.join(besked['ai_blockerade'])}" if besked["ai_blockerade"] else ""))
    if not besked["tillaten"]:
        return
    feed, _, err = fetch_one({"url": url})
    if feed is None:
        print(f"   flöde: FEL ({err})")
        return
    stamps = [e.get("published_parsed") or e.get("updated_parsed") for e in feed.entries]
    stamps = [time.mktime(t) for t in stamps if t]
    per_dygn = ""
    if len(stamps) > 1:
        dagar = max((max(stamps) - min(stamps)) / 86400, 1 / 24)
        per_dygn = f", cirka {len(stamps) / dagar:.0f} per dygn"
    senaste = time.strftime("%Y-%m-%d %H:%M", time.gmtime(max(stamps))) + " UTC" if stamps else "okänt"
    print(f"   flöde: {len(feed.entries)} artiklar{per_dygn}, senaste {senaste}")
    for e in feed.entries[:8]:
        print(f"   - {e.get('title', '')[:110]}")


CLAUDE_BOTAR = ("anthropic-ai", "ClaudeBot", "Claude-Web")


def genomgang(kallor, hamta=hamta_robots):
    """Genomgång av en hel källista mot utgivarnas robots.txt, utan att hämta några flöden. En rad per källa:
    robots (tillaten, blockerar, oklart), ai_blockerade, claude_blockerad, atgard (något vi bör göra) och beslut (något du bör avgöra).
    robots.txt hämtas en gång per utgivare."""
    cache, rader = {}, []
    for k in kallor:
        url = k["url"]
        host = urlsplit(url).netloc
        if host not in cache:
            cache[host] = hamta(url)
        text, fel = cache[host]
        rad = {"id": k["id"], "namn": k.get("namn", k["id"]), "typ": k.get("typ"), "region": k.get("region"),
               "betalvagg": bool(k.get("betalvagg")), "bara_rubrik": bool(k.get("bara_rubrik")), "url": url,
               "robots": "oklart", "regel": None, "fel": fel, "ai_blockerade": [], "claude_blockerad": False, "atgard": None, "beslut": None}
        if text is not None:
            besked = robots_besked(text, url)
            rad.update(robots="tillaten" if besked["tillaten"] else "blockerar", regel=besked["regel"], fel=None)
            if besked["tillaten"]:          # blockerar utgivaren alla botar säger det inget särskilt om AI
                rad["ai_blockerade"] = besked["ai_blockerade"]
                rad["claude_blockerad"] = any(b in besked["ai_blockerade"] for b in CLAUDE_BOTAR)
        if rad["robots"] == "blockerar":
            rad["atgard"] = "ta bort, utgivaren tillåter inte oss"
        elif rad["ai_blockerade"] and rad["betalvagg"]:
            rad["beslut"] = "betalvägg och blockerar Claude" if rad["claude_blockerad"] else "betalvägg och blockerar andra AI-botar"
        elif rad["ai_blockerade"] and not rad["bara_rubrik"]:
            rad["atgard"] = "satt bara_rubrik"
        rader.append(rad)
    return rader


def sammanfatta(rader):
    return {"totalt": len(rader), "tillaten": sum(r["robots"] == "tillaten" for r in rader), "blockerar": sum(r["robots"] == "blockerar" for r in rader),
            "oklart": sum(r["robots"] == "oklart" for r in rader), "ai_blockerar": sum(bool(r["ai_blockerade"]) for r in rader),
            "claude_blockerar": sum(r["claude_blockerad"] for r in rader), "beslut": sum(bool(r["beslut"]) for r in rader),
            "atgarder": sum(bool(r["atgard"]) for r in rader)}


def skriv_genomgang(rader):
    s = sammanfatta(rader)
    print(f"{s['totalt']} källor: robots.txt tillåter oss {s['tillaten']}, blockerar oss {s['blockerar']}, oklart {s['oklart']}. "
          f"Blockerar AI-botar {s['ai_blockerar']} (varav Claude {s['claude_blockerar']}). Åtgärder {s['atgarder']}, beslut {s['beslut']}.")
    for rubrik, urval in (("BLOCKERAR OSS", lambda r: r["robots"] == "blockerar"), ("OKLART", lambda r: r["robots"] == "oklart"),
                          ("BESLUT: betalvägg och AI-blockering", lambda r: bool(r["beslut"])),
                          ("AI-BLOCKERAR, BARA RUBRIK SAKNAS", lambda r: r["atgard"] == "satt bara_rubrik"),
                          ("AI-BLOCKERAR, REDAN BARA RUBRIK", lambda r: bool(r["ai_blockerade"]) and r["bara_rubrik"] and not r["betalvagg"])):
        valda = [r for r in rader if urval(r)]
        if valda:
            print(f"\n## {rubrik} ({len(valda)})")
            for r in valda:
                print(f"{r['id']} | {r['namn']} | {r['typ']} | {r['region']} | betalvägg {'ja' if r['betalvagg'] else 'nej'} | "
                      f"{', '.join(r['ai_blockerade']) or '-'}" + (f" | {r['regel']}" if r["robots"] == "blockerar" else "")
                      + (f" | {r['fel']}" if r["robots"] == "oklart" else ""))


def prova_sida(url, monster=None):
    """Prövar en källa utan flöde: tillåter robots.txt det, och vilka rubriker och länkar skulle läsaren (sidlasare.py) hitta?"""
    import sidlasare
    print(f"\n== {url}  (mönster: {monster or 'inget än'})")
    ok, orsak = sidlasare._tillaten(url)
    if not ok:
        print(f"   robots.txt: {orsak}. Sidan hämtas inte.")
        return
    print(f"   robots.txt: tillåter {BOT}")
    try:
        html = sidlasare._sida(url)
    except Exception as e:
        print(f"   sida: FEL ({str(e)[:120]})")
        return
    print("   sökvägar med rubrikliknande länkar: " + ", ".join(f"{k} ({n})" for k, n in list(sidlasare.oversikt(html, url).items())[:12]))
    funna = sidlasare.lankar(html, url, monster)
    print(f"   {len(funna)} rubriker med mönstret")
    for titel, lank in funna[:15]:
        print(f"   - {titel[:90]}\n     {lank}")


def main(argv):
    if argv and argv[0] == "--alla":
        import yaml
        skriv_genomgang(genomgang(yaml.safe_load(open(ROOT / "feeds.yaml", encoding="utf-8"))["sources"]))
        return
    if argv and argv[0] == "--sida":
        if len(argv) < 2:
            sys.exit("Ange adress och helst mönster: --sida ADRESS MÖNSTER")
        prova_sida(argv[1], argv[2] if len(argv) > 2 else None)
        return
    if not argv:
        sys.exit("Ange minst en adress.")
    for url in argv:
        prova(url)


if __name__ == "__main__":
    main(sys.argv[1:])
