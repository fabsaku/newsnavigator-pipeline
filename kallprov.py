#!/usr/bin/env python3
"""Prövar nya källor innan de läggs i feeds.yaml: får vår bot läsa flödet enligt robots.txt, och går det att läsa?

  python kallprov.py https://exempel.se/rss.xml [fler adresser]

Körs i GitHub Actions (workflowen kallprov.yml), eftersom sandboxen sällan når flödena. Skriver inget till repot.
Flödet hämtas bara om robots.txt tillåter det.
"""
import sys
import time
import urllib.error
import urllib.request
from urllib.parse import urlsplit
from urllib.robotparser import RobotFileParser

from pipeline import AGENT, fetch_one

BOT = "NewsnavigatorBot"
# Utgivare som stänger ute AI-botar har sagt något om hur de vill att texten används, även när vår bot är tillåten.
AI_BOTAR = ["anthropic-ai", "ClaudeBot", "Claude-Web", "GPTBot", "ChatGPT-User", "Google-Extended", "CCBot",
            "PerplexityBot", "Applebot-Extended", "Bytespider", "meta-externalagent"]


def robots_besked(text, url, agent=BOT):
    rp = RobotFileParser()
    rp.parse(text.splitlines())
    root = f"{urlsplit(url).scheme}://{urlsplit(url).netloc}/"
    return {"tillaten": rp.can_fetch(agent, url),
            "ai_blockerade": sorted((a for a in AI_BOTAR if not rp.can_fetch(a, root)), key=str.lower)}


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
