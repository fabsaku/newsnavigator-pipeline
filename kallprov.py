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


def main(urls):
    if not urls:
        sys.exit("Ange minst en adress.")
    for url in urls:
        prova(url)


if __name__ == "__main__":
    main(sys.argv[1:])
