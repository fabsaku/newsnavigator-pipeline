#!/usr/bin/env python3
"""Newsnavigator pipeline v0.1

Hämtar RSS-flöden, grupperar artiklar om samma händelse, taggar ämnen,
rangordnar, skriver AI-utkast (om API-nyckel finns) och bygger
data/flode.json samt en förhandsvisning i site/index.html.

Kör:  python pipeline.py                 (alla källor i feeds.yaml)
      python pipeline.py --feeds tests/feeds-test.yaml --max-age-hours 0
"""
import argparse
import hashlib
import html
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import feedparser
import yaml

from prompts import SYSTEM_PROMPT, user_prompt

ROOT = Path(__file__).parent
STOPWORDS = set("""
och i att det som en på är av för med till den har de inte om ett han hon men var
the a an of to in and for on is are with by as at from that this it its be was were
new says said after over into vs how why what will can more
""".split())

KEYWORDS = {
    "ai": ["ai", "artificiell", "llm", "språkmodell", "openai", "anthropic", "deepmind", "chatgpt", "machine learning", "maskininlärning"],
    "robotik": ["robot", "humanoid", "automation", "drönare", "drone"],
    "marknader": ["ränta", "inflation", "börs", "aktie", "stocks", "rate", "inflation", "ecb", "riksbank", "fed", "kronan", "dollar"],
    "halvledare": ["chip", "halvledare", "semiconductor", "nvidia", "tsmc", "asml"],
    "energi": ["elpris", "elnät", "energy", "kärnkraft", "nuclear", "fusion", "vindkraft", "solkraft"],
    "geopolitik": ["sanktion", "sanction", "nato", "tull", "tariff", "export", "krig", "war"],
    "rymd": ["rymd", "space", "satellit", "satellite", "nasa", "esa", "rocket", "raket"],
}


def load_sources(path):
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)["sources"]


def clean(text, limit=320):
    text = re.sub(r"<[^>]+>", " ", text or "")
    text = html.unescape(re.sub(r"\s+", " ", text)).strip()
    return text if len(text) <= limit else text[:limit].rsplit(" ", 1)[0] + " …"


AGENT = "NewsnavigatorBot/0.2 (+https://newsnavigator.se/bot)"


def fetch_one(s):
    """Prövar källans url och sedan dess reservadresser. Returnerar (feed, använd url, fel)."""
    err = "inga adresser"
    for url in [s["url"], *s.get("alternativ", [])]:
        target = str((ROOT / url[5:]).resolve()) if url.startswith("file:") else url
        try:
            feed = feedparser.parse(target, agent=AGENT)
        except Exception as e:  # nätverk eller parsning
            err = str(e)
            continue
        if feed.entries:
            return feed, url, None
        err = str(feed.get("bozo_exception", "inga artiklar"))
    return None, None, err


def fetch(sources, max_age_hours):
    items, report = [], []
    now = time.time()
    for s in sources:
        feed, used, err = fetch_one(s)
        if feed is None:
            report.append({"id": s["id"], "ok": False, "fel": err})
            continue
        n = 0
        for e in feed.entries:
            ts = e.get("published_parsed") or e.get("updated_parsed")
            epoch = time.mktime(ts) if ts else None
            if max_age_hours and epoch and now - epoch > max_age_hours * 3600:
                continue
            link = e.get("link", "")
            items.append({
                "id": hashlib.sha1(link.encode()).hexdigest()[:12],
                "source_id": s["id"],
                "source_name": s["namn"],
                "source_type": s["typ"],
                "paywall": s.get("betalvagg", False),
                "lang": s["sprak"],
                "country": s.get("land", ""),
                "region": s.get("region", "global"),
                "owner": s.get("agare", ""),
                "state_controlled": s.get("statskontrollerad", False),
                "topics": list(s.get("amnen", [])),
                "title": clean(e.get("title", ""), 200),
                # Betalväggskällor: bara rubrik och länk används
                "description": "" if s.get("betalvagg") else clean(e.get("summary", "")),
                "url": link,
                "published": datetime.fromtimestamp(epoch, timezone.utc).isoformat() if epoch else None,
                "epoch": epoch,
            })
            n += 1
        report.append({"id": s["id"], "ok": True, "artiklar": n, "url": used})
    return items, report


def tokens(text):
    words = re.findall(r"[a-zåäöéü0-9]+", text.lower())
    return {w for w in words if len(w) > 2 and w not in STOPWORDS}


def cluster(items, threshold=0.4, min_shared=3, research_threshold=0.65):
    """Grupperar artiklar om samma händelse.

    Likhet = andel gemensamma ord av den kortaste rubriken (overlap-koefficient),
    med krav på minst `min_shared` gemensamma ord, så att korta rubriker inte slås ihop av en slump.
    En källa kan bara förekomma en gång per händelse.
    """
    clusters = []
    for it in sorted(items, key=lambda x: x["epoch"] or 0, reverse=True):
        tk = tokens(it["title"])
        best, best_sim = None, 0.0
        for c in clusters:
            shared = len(tk & c["tokens"])
            if shared < min_shared:
                continue
            sim = shared / (min(len(tk), len(c["title_tokens"])) or 1)
            # Forskningsrubriker är fulla av fackord som "model" och "agents": kräv högre likhet
            research = it["source_type"] == "forskning" or any(i["source_type"] == "forskning" for i in c["items"])
            if research and sim < research_threshold:
                continue
            if sim > best_sim:
                best, best_sim = c, sim
        if best and best_sim >= threshold and it["source_id"] not in {i["source_id"] for i in best["items"]}:
            best["items"].append(it)
            best["tokens"] |= tk
        else:
            clusters.append({"items": [it], "tokens": set(tk), "title_tokens": set(tk)})
    return clusters


def tag(c):
    topics = set()
    text = " ".join(i["title"] + " " + i["description"] for i in c["items"]).lower()
    for i in c["items"]:
        topics.update(i["topics"])
    for topic, words in KEYWORDS.items():
        # Hela ord, så att "ai" inte matchar "Arizona" eller "said"
        if any(re.search(rf"\b{re.escape(w.strip())}", text) for w in words):
            topics.add(topic)
    return sorted(topics)


HOME = {"sverige", "norden"}


def perspective(c):
    """Så ser världen på det: rubriker per region, och blinda fläckar."""
    regions = {}
    for i in c["items"]:
        regions.setdefault(i["region"], []).append({
            "kalla": i["source_name"], "land": i["country"], "rubrik": i["title"], "url": i["url"],
            "statskontrollerad": i["state_controlled"]})
    n_sources = len({i["source_id"] for i in c["items"]})
    names = set(regions)
    blind = None
    if n_sources >= 3 and len(names) >= 2 and not (names & HOME):
        blind = "saknas_i_sverige"      # stort i världen, inget i svenska källor
    elif n_sources >= 2 and names <= HOME:
        blind = "bara_i_sverige"        # bara svenska och nordiska källor
    return {"regioner": sorted(names), "per_region": regions, "blind_flack": blind}


def score(c):
    sources = {i["source_id"] for i in c["items"]}
    regions = {i["region"] for i in c["items"]}
    primary = any(i["source_type"] in ("primar", "forskning") for i in c["items"])
    newest = max((i["epoch"] or 0) for i in c["items"])
    age_h = max(0, (time.time() - newest) / 3600) if newest else 48
    return round(len(sources) * 2 + (len(regions) - 1) * 1.0 + (1.5 if primary else 0) + max(0, 3 - age_h / 8), 2)


def summarize(c, client, model):
    if client is None:
        return None
    msg = client.messages.create(
        model=model, max_tokens=600, system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_prompt(c)}],
    )
    text = msg.content[0].text.strip()
    text = text[text.find("{"): text.rfind("}") + 1]
    return json.loads(text)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--feeds", default=str(ROOT / "feeds.yaml"))
    ap.add_argument("--max-age-hours", type=float, default=36)
    ap.add_argument("--limit", type=int, default=40, help="max antal händelser i flödet")
    ap.add_argument("--out", default=str(ROOT / "data"))
    args = ap.parse_args()

    client, model = None, os.environ.get("NN_MODEL", "claude-haiku-5-5")
    if os.environ.get("ANTHROPIC_API_KEY"):
        import anthropic
        client = anthropic.Anthropic()

    items, report = fetch(load_sources(args.feeds), args.max_age_hours)
    clusters = cluster(items)
    events = []
    for c in clusters:
        c["topics"] = tag(c)
        c["score"] = score(c)
    clusters.sort(key=lambda c: c["score"], reverse=True)

    approved_path = ROOT / "data" / "godkanda.json"
    approved = set(json.loads(approved_path.read_text())) if approved_path.exists() else set()

    order = {"primar": 0, "forskning": 1, "media": 2}
    for c in clusters[: args.limit]:
        # Primärkällor först, sedan fria källor, betalväggar och statskontrollerade medier sist
        c["items"].sort(key=lambda i: (i["state_controlled"], order.get(i["source_type"], 3), i["paywall"]))
        lead = c["items"][0]
        event_id = hashlib.sha1(" ".join(sorted(i["id"] for i in c["items"])).encode()).hexdigest()[:10]
        draft = None
        try:
            draft = summarize(c, client, model)
        except Exception as e:
            draft = {"osaker": True, "kommentar": f"AI-utkast misslyckades: {e}"}
        events.append({
            "id": event_id,
            "amnen": c["topics"],
            "poang": c["score"],
            "antal_kallor": len({i["source_id"] for i in c["items"]}),
            "har_primarkalla": any(i["source_type"] in ("primar", "forskning") for i in c["items"]),
            "senast": max((i["published"] or "") for i in c["items"]) or None,
            "utkast": draft,
            "perspektiv": perspective(c),
            "reserv_rubrik": lead["title"],
            "kallor": [{"namn": i["source_name"], "rubrik": i["title"], "url": i["url"],
                        "betalvagg": i["paywall"], "typ": i["source_type"], "land": i["country"],
                        "region": i["region"], "agare": i["owner"],
                        "statskontrollerad": i["state_controlled"]} for i in c["items"]],
            "granskad": event_id in approved,
        })

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    payload = {"skapad": datetime.now(timezone.utc).isoformat(), "modell": model if client else None,
               "handelser": events, "kallrapport": report}
    (out / "flode.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    from render import render
    render(payload, ROOT / "site" / "index.html")

    ok = sum(1 for r in report if r["ok"])
    print(f"Källor: {ok}/{len(report)} ok · artiklar: {len(items)} · händelser: {len(events)} · AI: {'på' if client else 'av'}")
    for r in report:
        if not r["ok"]:
            print(f"  FEL {r['id']}: {r['fel'][:120]}", file=sys.stderr)


if __name__ == "__main__":
    main()
