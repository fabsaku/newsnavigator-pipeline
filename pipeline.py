#!/usr/bin/env python3
"""Newsnavigator pipeline v0.4

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
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

import feedparser
import yaml

from prompts import SYSTEM_PROMPT, user_prompt

ROOT = Path(__file__).parent
NEWSLETTER_ADMIN = re.compile(r"confirm|verify|welcome|subscription|subscribed|subscribing|unsubscribe|bekräfta|välkommen", re.I)
CACHE_PATH = ROOT / "data" / "cache.json"
CACHE_DAYS = 3        # utkast och översättningar som inte setts på tre dagar rensas
WORKERS = 8           # samtidiga AI-anrop
STOPWORDS = set("""
och i att det som en på är av för med till den har de inte om ett han hon men var
the a an of to in and for on is are with by as at from that this it its be was were
new says said after over into vs how why what will can more
week images video photos live updates latest news today veckan bilder bild direkt senaste nytt idag
utanför near amid
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


# Vi presenterar oss ärligt som bot. En utgivare som blockerar botar respekterar vi.
AGENT = "Mozilla/5.0 (compatible; NewsnavigatorBot/0.3; +https://newsnavigator.se/bot)"
ACCEPT = "application/rss+xml, application/atom+xml, application/xml;q=0.9, text/xml;q=0.9, */*;q=0.5"
BAD_XML = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")


def _download(url):
    import urllib.request
    req = urllib.request.Request(url, headers={"User-Agent": AGENT, "Accept": ACCEPT})
    with urllib.request.urlopen(req, timeout=25) as r:
        return r.read()


def fetch_one(s):
    """Prövar källans url och sedan dess reservadresser. Returnerar (feed, använd url, fel).

    Laddar ner flödet själv och rensar bort tecken som är ogiltiga i XML innan det tolkas,
    eftersom några utgivare (t.ex. med trasiga kontrolltecken) annars ger noll artiklar.
    """
    err = "inga adresser"
    for url in [s["url"], *s.get("alternativ", [])]:
        try:
            if url.startswith("file:"):
                raw = (ROOT / url[5:]).read_bytes()
            else:
                raw = _download(url)
            text = BAD_XML.sub("", raw.decode("utf-8", errors="replace")).lstrip("﻿ \r\n\t")
            feed = feedparser.parse(text)
        except Exception as e:  # nätverk, http-fel eller parsning
            err = str(e)[:160]
            continue
        if feed.entries:
            return feed, url, None
        if not url.startswith("file:"):
            # Reserv: låt feedparser hämta själv (hanterar komprimering och omdirigeringar annorlunda)
            try:
                native = feedparser.parse(url, agent=AGENT)
                if native.entries:
                    return native, url, None
            except Exception:
                pass
        head = text[:200].lower()
        err = "sidan är html, inte ett flöde" if "<html" in head or "<!doctype html" in head else \
            str(feed.get("bozo_exception", "inga artiklar"))
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
            if s.get("bara_rubrik") and NEWSLETTER_ADMIN.search(e.get("title", "")):
                continue    # bekräftelse- och välkomstmejl är inga nyheter
            if s.get("avsandare") and s["avsandare"] not in (e.get("author", "") + e.get("author_detail", {}).get("email", "")):
                continue    # flera nyhetsbrev i samma flöde: ta bara det från rätt avsändare
            # lanka: fast länk för källor vars flöde inte pekar på en publik sida (t.ex. nyhetsbrev via e-post)
            link = s.get("lanka") or e.get("link", "")
            ident = e.get("id") or e.get("link", "") or e.get("title", "")
            items.append({
                "id": hashlib.sha1((f"{s['id']}|{ident}" if s.get("lanka") else link).encode()).hexdigest()[:12],
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
                # Betalväggskällor och nyhetsbrev: bara rubrik och länk används
                "description": "" if s.get("betalvagg") or s.get("bara_rubrik") else clean(e.get("summary", "")),
                "url": link,
                "published": datetime.fromtimestamp(epoch, timezone.utc).isoformat() if epoch else None,
                "epoch": epoch,
            })
            n += 1
        report.append({"id": s["id"], "ok": True, "artiklar": n, "url": used})
    return items, report


# Översätter vanliga nyhetsord och namn till en gemensam form, så att svenska,
# norska och engelska rubriker om samma händelse kan matchas även utan AI.
ALIASES = {
    # länder, platser, organisationer
    "ukraina": "ukraine", "ukrainas": "ukraine", "ukrainian": "ukraine", "ryssland": "russia", "rysk": "russia",
    "ryska": "russia", "russian": "russia", "kina": "china", "kinas": "china", "chinese": "china",
    "frankrike": "france", "french": "france", "tyskland": "germany", "german": "germany",
    "storbritannien": "britain", "british": "britain", "usas": "usa", "amerikanska": "usa", "american": "usa",
    "israels": "israel", "israeli": "israel", "irans": "iran", "iranian": "iran", "moskva": "moscow",
    "peking": "beijing", "bryssel": "brussels", "köpenhamn": "copenhagen", "västbanken": "west_bank",
    "gazaremsan": "gaza", "svarta": "black", "havet": "sea", "fn": "un", "nations": "un", "eus": "eu",
    "natos": "nato", "rumänien": "romania", "romanian": "romania", "jordanien": "jordan", "taiwans": "taiwan",
    "förenade": "uae", "emiraten": "uae", "zelenskyj": "zelensky", "zelenskyy": "zelensky",
    # händelser
    "skjutning": "shoot", "skjuten": "shoot", "skjutna": "shoot", "skottlossning": "shoot", "shooting": "shoot",
    "shot": "shoot", "död": "kill", "döda": "kill", "dödad": "kill", "dödade": "kill", "dödas": "kill",
    "killed": "kill", "kills": "kill", "dead": "kill", "kyrka": "church", "begravning": "funeral",
    "attacken": "attack", "attackerat": "attack", "attacked": "attack", "fartyg": "ship", "samtal": "talk",
    "förhandlingar": "talk", "talks": "talk", "fredssamtal": "talk", "vapenvila": "ceasefire", "eldupphör": "ceasefire",
    "sanktioner": "sanction", "sanctions": "sanction", "tullar": "tariff", "tariffs": "tariff", "val": "election",
    "valet": "election", "protester": "protest", "protests": "protest", "demonstrationer": "protest",
    "jordbävning": "earthquake", "översvämning": "flood", "översvämningar": "flood", "floods": "flood",
    "tyfon": "typhoon", "tyfonen": "typhoon", "räntan": "rate", "styrräntan": "rate", "ränta": "rate",
    "rates": "rate", "sänker": "cut", "cuts": "cut", "höjer": "raise", "militär": "military", "militära": "military",
    "operation": "operation", "operationen": "operation", "regeringen": "government", "statsminister": "prime_minister",
    "president": "president", "presidenten": "president",
}


def tokens(text):
    words = re.findall(r"[a-zåäöéüø0-9]+", text.lower())
    out = set()
    for w in words:
        if len(w) <= 2 and w not in ("eu", "fn", "un", "us"):
            continue
        if w in STOPWORDS:
            continue
        mapped = ALIASES.get(w, w)
        out.add(mapped)
    if "west" in out and "bank" in out:
        out.add("west_bank")
    return out


def cluster(items, threshold=0.4, min_shared=3, research_threshold=0.65, curated_threshold=0.6):
    """Grupperar artiklar om samma händelse.

    Likhet = andel gemensamma ord av den kortaste rubriken (overlap-koefficient),
    med krav på minst `min_shared` gemensamma ord, så att korta rubriker inte slås ihop av en slump.
    En källa kan bara förekomma en gång per händelse.
    """
    clusters = []
    for it in sorted(items, key=lambda x: x["epoch"] or 0, reverse=True):
        # title_en finns när AI har översatt rubriken, annars används originalet
        tk = tokens(it.get("title_en") or it["title"])
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
            # Kuraterade listor (Techmeme m.fl.) har långa rubriker som delar ord med nästan allt.
            # Jämför bara mot huvudrubriken och kräv tydlig likhet.
            curated = it["source_type"] == "kuraterat" or any(i["source_type"] == "kuraterat" for i in c["items"])
            if curated:
                head = len(tk & c["title_tokens"])
                if head < 4 or head / (min(len(tk), len(c["title_tokens"])) or 1) < curated_threshold:
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
    n_sources = len(independent(c))
    names = {i["region"] for i in c["items"] if i["source_type"] != "kuraterat"}
    blind = None
    if n_sources >= 3 and len(names) >= 2 and not (names & HOME):
        blind = "saknas_i_sverige"      # stort i världen, inget i svenska källor
    elif n_sources >= 2 and names <= HOME:
        blind = "bara_i_sverige"        # bara svenska och nordiska källor
    return {"regioner": sorted(names), "per_region": regions, "blind_flack": blind}


def independent(c):
    """Källor som rapporterar själva. Kuraterade listor och nyhetsbrev räknas inte."""
    return {i["source_id"] for i in c["items"] if i["source_type"] != "kuraterat"}


def score(c):
    sources = independent(c)
    curated = len({i["source_id"] for i in c["items"]}) - len(sources)
    regions = {i["region"] for i in c["items"]}
    primary = any(i["source_type"] in ("primar", "forskning") for i in c["items"])
    newest = max((i["epoch"] or 0) for i in c["items"])
    age_h = max(0, (time.time() - newest) / 3600) if newest else 48
    # Kuraterade källor ger en liten bonus: det är ett tecken på att techvärlden pratar om saken.
    return round(len(sources) * 2 + min(curated, 2) * 0.5 + (len(regions) - 1) * 1.0 + (1.5 if primary else 0) + max(0, 3 - age_h / 8), 2)


def reply_text(msg):
    """Plockar ut svarstexten. Modellen kan skicka resonemangsblock före texten, de hoppas över."""
    text = "".join(getattr(b, "text", "") for b in msg.content if getattr(b, "type", "text") == "text")
    if not text.strip():
        kinds = ",".join(getattr(b, "type", "?") for b in msg.content)
        raise ValueError(f"tomt svar (stop_reason={getattr(msg, 'stop_reason', '?')}, block={kinds})")
    return text


def translate_titles(items, client, model, cache, batch=60):
    """Översätter icke-engelska rubriker till engelska (title_en) så att grupperingen fungerar över språk.

    Rubriker som redan översatts hämtas ur cachen. Returnerar True om alla omgångar lyckades.
    Bara rubriker skickas, aldrig artikeltext.
    """
    todo = []
    for i in items:
        if i["lang"] == "en" or not i["title"]:
            continue
        hit = cache["titlar"].get(i["title"])
        if hit:
            i["title_en"] = hit["en"]
            hit["sedd"] = NOW
        else:
            todo.append(i)

    def run(part):
        listing = "\n".join(f"{n}. {i['title']}" for n, i in enumerate(part))
        msg = client.messages.create(
            model=model, max_tokens=16000,
            system="Translate each news headline to plain, neutral English. Keep names and numbers exactly. "
                   "Answer ONLY with a JSON array of strings in the same order, one per headline.",
            messages=[{"role": "user", "content": listing}])
        text = reply_text(msg)
        return part, json.loads(text[text.find("["): text.rfind("]") + 1])

    ok = True
    parts = [todo[k:k + batch] for k in range(0, len(todo), batch)]
    with ThreadPoolExecutor(WORKERS) as pool:
        for fut in [pool.submit(run, p) for p in parts]:
            try:
                part, out = fut.result()
                for i, t in zip(part, out):
                    i["title_en"] = str(t)
                    cache["titlar"][i["title"]] = {"en": str(t), "sedd": NOW}
            except Exception as e:
                print(f"  Översättning misslyckades: {e}", file=sys.stderr)
                ok = False
    print(f"Rubriker: {len(todo)} nya översatta, {sum(1 for i in items if i.get('title_en')) - len(todo)} ur cachen")
    return ok


def load_cache():
    try:
        c = json.loads(CACHE_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        c = {}
    c.setdefault("utkast", {})
    c.setdefault("titlar", {})
    return c


def save_cache(cache):
    limit = time.time() - CACHE_DAYS * 86400
    for key in ("utkast", "titlar"):
        cache[key] = {k: v for k, v in cache[key].items() if v.get("sedd", 0) >= limit}
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    CACHE_PATH.write_text(json.dumps(cache, ensure_ascii=False, indent=1), encoding="utf-8")


def summarize(c, client, model):
    if client is None:
        return None
    msg = client.messages.create(
        model=model, max_tokens=16000, system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_prompt(c)}],
    )
    text = reply_text(msg).strip()
    text = text[text.find("{"): text.rfind("}") + 1]
    return json.loads(text)


NOW = time.time()


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

    cache = load_cache()
    items, report = fetch(load_sources(args.feeds), args.max_age_hours)
    cross_language = translate_titles(items, client, model, cache) if client else False
    clusters = cluster(items)
    events = []
    for c in clusters:
        c["topics"] = tag(c)
        c["score"] = score(c)
    clusters.sort(key=lambda c: c["score"], reverse=True)

    approved_path = ROOT / "data" / "godkanda.json"
    approved = set(json.loads(approved_path.read_text())) if approved_path.exists() else set()

    order = {"primar": 0, "forskning": 1, "media": 2, "kuraterat": 4}
    chosen = clusters[: args.limit]
    for c in chosen:
        # Primärkällor först, sedan fria källor, betalväggar och statskontrollerade medier sist
        c["items"].sort(key=lambda i: (i["state_controlled"], order.get(i["source_type"], 3), i["paywall"]))
        # Samma uppsättning artiklar ger samma id. Ny källa eller ändrad rubrik ger nytt utkast.
        c["id"] = hashlib.sha1(" ".join(sorted(i["id"] for i in c["items"])).encode()).hexdigest()[:10]
        c["fingeravtryck"] = hashlib.sha1((model + SYSTEM_PROMPT + user_prompt(c)).encode()).hexdigest()[:12]

    def draft_for(c):
        hit = cache["utkast"].get(c["id"])
        if hit and hit.get("fingeravtryck") == c["fingeravtryck"]:
            return hit["utkast"], True
        try:
            return summarize(c, client, model), False
        except Exception as e:
            return {"osaker": True, "kommentar": f"AI-utkast misslyckades: {e}", "_fel": True}, False

    with ThreadPoolExecutor(WORKERS) as pool:
        results = list(pool.map(draft_for, chosen))

    reused = 0
    for c, (draft, from_cache) in zip(chosen, results):
        reused += from_cache
        if draft is not None and not draft.get("_fel"):
            cache["utkast"][c["id"]] = {"utkast": draft, "fingeravtryck": c["fingeravtryck"], "sedd": NOW}
        elif draft is not None:
            draft.pop("_fel", None)
        lead = c["items"][0]
        events.append({
            "id": c["id"],
            "amnen": c["topics"],
            "poang": c["score"],
            "antal_kallor": len(independent(c)) or len({i["source_id"] for i in c["items"]}),
            "har_primarkalla": any(i["source_type"] in ("primar", "forskning") for i in c["items"]),
            "senast": max((i["published"] or "") for i in c["items"]) or None,
            "utkast": draft,
            "perspektiv": perspective(c),
            "reserv_rubrik": lead["title"],
            "kallor": [{"namn": i["source_name"], "rubrik": i["title"], "url": i["url"],
                        "betalvagg": i["paywall"], "typ": i["source_type"], "land": i["country"],
                        "region": i["region"], "agare": i["owner"],
                        "statskontrollerad": i["state_controlled"]} for i in c["items"]],
            "granskad": c["id"] in approved,
        })
    if client:
        print(f"Utkast: {len(chosen) - reused} nya, {reused} ur cachen")
        save_cache(cache)

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    payload = {"skapad": datetime.now(timezone.utc).isoformat(), "modell": model if client else None,
               "over_sprak": cross_language,
               "handelser": events, "kallrapport": report}
    (out / "flode.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    from newsletter import archive
    from render import render
    archive(events, approved)
    render(payload, ROOT / "site" / "index.html")

    ok = sum(1 for r in report if r["ok"])
    print(f"Källor: {ok}/{len(report)} ok · artiklar: {len(items)} · händelser: {len(events)} · AI: {'på' if client else 'av'}")
    for r in report:
        if not r["ok"]:
            print(f"  FEL {r['id']}: {r['fel'][:120]}", file=sys.stderr)


if __name__ == "__main__":
    main()
