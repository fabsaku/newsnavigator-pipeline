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
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

import feedparser
import yaml

import kallkontroll
import vikt as vikt_mod
from prompts import SYSTEM_PROMPT, user_prompt

ROOT = Path(__file__).parent
NEWSLETTER_ADMIN = re.compile(r"confirm|verify|welcome|subscription|subscribed|subscribing|unsubscribe|bekräfta|välkommen", re.I)
CACHE_PATH = ROOT / "data" / "cache.json"
CACHE_DAYS = 3        # utkast och översättningar som inte setts på tre dagar rensas
WORKERS = 8           # samtidiga AI-anrop
KONSEKVENS_TOPP = 80  # så många händelser får en konsekvensbedömning per körning (cachas)
STOPWORDS = set("""
och i att det som en på är av för med till den har de inte om ett han hon men var
the a an of to in and for on is are with by as at from that this it its be was were
new says said after over into vs how why what will can more
week images video photos live updates latest news today veckan bilder bild direkt senaste nytt idag
utanför near amid
about ahead you your should could would not then than has have had his her their they who which when where
while all also been but just know
""".split())

# Nyckelord som ger ämne. Hela ord, utom de som slutar med * (ordstam: "ränt*" träffar ränta, räntan, räntor).
KEYWORDS = {
    "ai": ["ai", "artificiell*", "llm*", "språkmodell*", "openai", "anthropic", "deepmind", "chatgpt", "machine learning", "maskininlärning", "generativ*"],
    "robotik": ["robot*", "humanoid*", "automation"],
    "marknader": ["ränt*", "inflation*", "börs*", "aktie*", "stocks", "stock market", "interest rate*", "rate cut*", "rate hike*",
                  "ecb", "riksbank*", "federal reserve", "fed", "kronan", "dollarn", "obligation*", "bond*", "kreditbetyg*", "credit rating*", "bnp", "gdp"],
    "halvledare": ["chip*", "halvledar*", "semiconductor*", "nvidia", "tsmc", "asml"],
    "energi": ["elpris*", "elnät*", "energy", "energi*", "kärnkraft*", "nuclear", "fusion", "vindkraft*", "solkraft*", "solar", "wind power"],
    "geopolitik": ["sanktion*", "sanction*", "nato", "tull*", "tariff*", "krig*", "war", "vapenvila*", "ceasefire*", "diplomat*"],
    "rymd": ["rymd*", "space", "satellit*", "satellite*", "nasa", "esa", "rocket*", "raket*"],
    # Geografi: vad händelsen handlar om, inte var källan finns
    "sverige": ["sverige", "svensk*", "sweden", "swedish", "riksdag*", "regeringen", "stockholm", "göteborg", "malmö", "kristersson", "riksbank*"],
    "usa": ["trump", "white house", "vita huset", "congress", "kongressen", "senate", "senaten", "washington"],
    "europa": ["eu", "bryssel", "brussels", "europeiska", "european union", "eu-*"],
    "latinamerika": ["venezuela*", "brasilien*", "brazil*", "argentin*", "mexik*", "mexic*", "colombia*", "chile*", "peru*",
                     "kuba*", "cuba*", "ecuador*", "bolivia*", "haiti*", "lula", "milei", "sheinbaum", "maduro", "latin america*", "latinamerika*"],
}
# Källornas geografiska ämnen (var de bevakar) räknas bara om alla källor delar dem.
GEO = {"sverige", "norden", "europa", "usa", "latinamerika", "asien", "mellanostern", "afrika", "varlden"}
# Källor som bara bevakar ett ämne: deras ämne styr sektionen när de är fler än hälften av källorna (eller ensamma)
DEDICATED = {"spel", "noje"}
# Platser bland de utvalda händelserna som hålls åt sektioner som sällan når upp i poäng
RESERVED = {"noje": 4}
_KW = {}


def _kw(word):
    if word not in _KW:
        stem = word.endswith("*")
        w = re.escape(word.rstrip("*"))
        _KW[word] = re.compile(rf"\b{w}\w*" if stem else rf"\b{w}\b")
    return _KW[word]


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
        entries = list(feed.entries)
        for extra in s.get("extra", []):
            more, _, _ = fetch_one({**s, "url": extra, "alternativ": []})
            if more is not None:
                entries += more.entries
        seen_links, n = set(), 0
        for e in entries:
            if e.get("link") and e.get("link") in seen_links:
                continue
            seen_links.add(e.get("link"))
            ts = e.get("published_parsed") or e.get("updated_parsed")
            epoch = time.mktime(ts) if ts else None
            if max_age_hours and epoch and now - epoch > max_age_hours * 3600:
                continue
            if s.get("bara_rubrik") and NEWSLETTER_ADMIN.search(e.get("title", "")):
                continue    # bekräftelse- och välkomstmejl är inga nyheter
            if s.get("avsandare") and s["avsandare"] not in (e.get("author", "") + e.get("author_detail", {}).get("email", "")):
                continue    # flera nyhetsbrev i samma flöde: ta bara det från rätt avsändare
            if s.get("rubrik_filter") and not re.search(s["rubrik_filter"], e.get("title", "")):
                continue    # t.ex. GDACS: bara orange och röda varningar
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
                "usa_lean": s.get("usa_lutning"),
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
    "accident": "crash", "collision": "crash", "collide": "crash", "collides": "crash", "collided": "crash",
    "olycka": "crash", "olyckan": "crash", "krock": "crash", "krockat": "crash", "kolliderat": "crash", "kolliderar": "crash",
    "spanish": "spain", "spaniens": "spain", "spanien": "spain", "trains": "train", "tåg": "train", "tågolyckan": "train",
    "brazilian": "brazil", "brasilien": "brazil", "brasiliens": "brazil", "elections": "election", "valet": "election",
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


MAX_SECTIONS = 3     # fler sektioner i ett kluster betyder nästan alltid hopslagna händelser


def pair_similarity(a, b, ta, tb, threshold=0.4, min_shared=3, research_threshold=0.65, curated_threshold=0.6):
    """Likhet mellan två rubriker, 0 om paret inte klarar tröskeln.

    Likhet = andel gemensamma ord av den kortaste rubriken (overlap-koefficient),
    med krav på minst `min_shared` gemensamma ord, så att korta rubriker inte slås ihop av en slump.
    """
    shared = len(ta & tb)
    if shared < min_shared:
        return 0.0
    sim = shared / (min(len(ta), len(tb)) or 1)
    # Forskningsrubriker är fulla av fackord som "model" och "agents": kräv högre likhet
    if "forskning" in (a["source_type"], b["source_type"]) and sim < research_threshold:
        return 0.0
    # Kuraterade listor (Techmeme m.fl.) har långa rubriker som delar ord med nästan allt
    if "kuraterat" in (a["source_type"], b["source_type"]) and (shared < 4 or sim < curated_threshold):
        return 0.0
    return sim if sim >= threshold else 0.0


def sections(c):
    """Sektionerna (Världen, Sverige, Marknader, Tech, Vetenskap) som klustrets sektionsämnen pekar på."""
    from newsletter import SECTIONS
    topics = set(tag(c)[1])
    return {key for key, _, _, tags in SECTIONS if topics & tags}


def cluster(items, **pair_args):
    """Grupperar artiklar om samma händelse.

    Rubrikerna jämförs par för par. En artikel går med i en händelse bara om den klarar tröskeln mot
    fler än hälften av rubrikerna där, så att den aldrig kommer in via en enda tredje artikel.
    En källa kan bara förekomma en gång per händelse, och en händelse spänner över högst MAX_SECTIONS sektioner.
    """
    clusters = []
    for it in sorted(items, key=lambda x: x["epoch"] or 0, reverse=True):
        # title_en finns när AI har översatt rubriken, annars används originalet
        tk = tokens(it.get("title_en") or it["title"])
        candidates = []
        for c in clusters:
            if it["source_id"] in c["sources"]:
                continue
            sims = [pair_similarity(it, m, tk, mt, **pair_args) for m, mt in zip(c["items"], c["item_tokens"])]
            if sum(1 for s in sims if s) * 2 > len(sims):
                candidates.append((sum(sims) / len(sims), c))
        for _, c in sorted(candidates, key=lambda x: x[0], reverse=True):
            if len(sections({"items": c["items"] + [it]})) <= MAX_SECTIONS:
                c["items"].append(it)
                c["item_tokens"].append(tk)
                c["sources"].add(it["source_id"])
                break
        else:
            clusters.append({"items": [it], "item_tokens": [tk], "sources": {it["source_id"]}})
    return clusters


def _core(c):
    """Kärnorden i ett kluster: ord som finns i minst hälften av rubrikerna (minst två)."""
    n = len(c["item_tokens"])
    counts = Counter(w for tk in c["item_tokens"] for w in tk)
    need = max(2, (n + 1) // 2) if n > 1 else 1
    return {w for w, k in counts.items() if k >= need}


def _cross_rate(a, b, rate):
    """Klarar tillräckligt många rubrikpar mellan de två klustren tröskeln?"""
    hits = total = 0
    for x, tx in zip(a["items"], a["item_tokens"]):
        for y, ty in zip(b["items"], b["item_tokens"]):
            total += 1
            hits += pair_similarity(x, y, tx, ty) > 0
    return total and hits / total >= rate


def merge_clusters(clusters, min_core=3, core_overlap=0.6, pair_rate=0.25):
    """Andra varvet: slår ihop kluster om samma händelse som det första varvet delade upp
    (till exempel när en källa har flera artiklar, eller rubrikerna skiljer sig i ordval).
    Två kluster slås ihop när kärnorden till stor del är desamma och sektionerna räcker till.
    En källa förekommer fortfarande bara en gång: den nyaste artikeln behålls."""
    merged = True
    while merged:
        merged = False
        multi = [c for c in clusters if len(c["items"]) >= 2]
        for a in multi:
            ca = _core(a)
            if len(ca) < min_core:
                continue
            for b in multi:
                if b is a or b.get("_gone") or a.get("_gone"):
                    continue
                cb = _core(b)
                shared = len(ca & cb)
                same_core = shared >= min_core and shared / min(len(ca), len(cb)) >= core_overlap
                if not same_core and not _cross_rate(a, b, pair_rate):
                    continue
                pool = sorted(a["items"] + b["items"], key=lambda x: x["epoch"] or 0, reverse=True)
                keep, seen = [], set()
                for it in pool:
                    if it["source_id"] not in seen:
                        seen.add(it["source_id"])
                        keep.append(it)
                if len(sections({"items": keep})) > MAX_SECTIONS:
                    continue
                toks = {id(it): tk for it, tk in zip(a["items"] + b["items"], a["item_tokens"] + b["item_tokens"])}
                a["items"], a["item_tokens"], a["sources"] = keep, [toks[id(it)] for it in keep], seen
                b["_gone"] = True
                ca = _core(a)
                merged = True
        clusters = [c for c in clusters if not c.get("_gone")]
    return clusters


def tag(c):
    """Ämnen för en händelse: nyckelord i texten, plus källornas bevakningsämnen när minst hälften av källorna
    (och minst två) delar dem. Returnerar (alla ämnen, sektionsämnen). Sektionsämnena är textens ämnen plus
    de bevakningsämnen som alla källor delar; de styr vilken sektion notisen hamnar i. Att hälften av
    källorna bevakar marknader räcker inte (CNBC skriver om mycket annat)."""
    counts = Counter(t for i in c["items"] for t in i["topics"])
    n = len(c["items"])
    from_sources = {t for t, k in counts.items() if (k == n if t in GEO else (k * 2 >= n and k >= 2))}
    shared_by_all = {t for t, k in counts.items() if k == n and n >= 2 and t not in GEO}
    dedicated = {t for t, k in counts.items() if t in DEDICATED and (n == 1 or k * 2 > n)}
    # Nyckelord i rubrikerna räcker; i ingresserna krävs träff hos minst två källor, så att ett
    # enstaka "energy" eller "AI" i en ingress inte flyttar notisen till fel sektion.
    titles = " ".join(i["title"] for i in c["items"]).lower()
    descs = [(i["description"] or "").lower() for i in c["items"]]
    from_text = set()
    for topic, words in KEYWORDS.items():
        pats = [_kw(w) for w in words]
        if any(p.search(titles) for p in pats):
            from_text.add(topic)
            continue
        hits = sum(1 for d in descs if any(p.search(d) for p in pats))
        if hits >= 2 or (n == 1 and hits == 1):
            from_text.add(topic)
    return sorted(from_sources | from_text | dedicated), sorted(from_text | shared_by_all | dedicated)


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
    return {"regioner": sorted(names), "per_region": regions, "blind_flack": blind, **usa_spectrum(c)}


# AllSides skala grupperad i tre: vänster (blå publik), mitten, höger (röd publik)
LEAN_SIDE = {"vanster": "bla", "lutar_vanster": "bla", "mitten": "mitten", "lutar_hoger": "rod", "hoger": "rod"}


def usa_spectrum(c):
    """Så berättar USA: amerikanska rubriker grupperade efter mediernas publik enligt AllSides.

    Visas bara när minst två sidor finns med. Blind fläck när minst tre amerikanska medier
    från en sida rapporterar och ingen från den andra.
    """
    sides = {}
    for i in c["items"]:
        side = LEAN_SIDE.get(i.get("usa_lean") or "")
        if side:
            sides.setdefault(side, []).append({"kalla": i["source_name"], "rubrik": i["title"], "url": i["url"],
                                               "lutning": i["usa_lean"]})
    blind = None
    for a, b in (("bla", "rod"), ("rod", "bla")):
        if len({x["kalla"] for x in sides.get(a, [])}) >= 3 and not sides.get(b):
            blind = f"mest_{a}"
    return {"usa": sides if len(sides) >= 2 else None, "usa_blind": blind}


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


def choose(clusters, limit, reserved=None):
    """De `limit` högst rankade händelserna, men med RESERVED platser för vissa sektioner när de har händelser."""
    from newsletter import section_of
    reserved = RESERVED if reserved is None else reserved
    ranked = sorted(clusters, key=lambda c: c["score"], reverse=True)
    sec = {id(c): section_of({"amnen_sektion": c["section_topics"]}) for c in ranked}
    chosen = ranked[:limit]
    for section, places in reserved.items():
        missing = places - sum(1 for c in chosen if sec[id(c)] == section)
        for extra in [c for c in ranked[limit:] if sec[id(c)] == section][:max(missing, 0)]:
            drop = next((c for c in reversed(chosen) if sec[id(c)] not in reserved), None)
            if drop is None:
                break
            chosen.remove(drop)
            chosen.append(extra)
    return sorted(chosen, key=lambda c: c["score"], reverse=True)


def assign_id(c, used_ids):
    """Samma uppsättning artiklar ger samma id, och en händelse som historiken känner igen behåller sitt,
    så att en publicerad notis uppdateras i stället för att publiceras igen. Två händelser i samma
    flöde får aldrig samma id: då får den senare ett nytt."""
    cid = hashlib.sha1(" ".join(sorted(i["id"] for i in c["items"])).encode()).hexdigest()[:10]
    h = c.get("_hist")
    if h is not None and h.get("id") and h["id"] not in used_ids:
        cid = h["id"]
    while cid in used_ids:
        cid = hashlib.sha1(cid.encode()).hexdigest()[:10]
    if h is not None:
        h["id"] = cid
    used_ids.add(cid)
    c["id"] = cid
    return cid


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
    for key in ("utkast", "titlar", "konsekvens"):
        cache[key] = {k: v for k, v in cache.get(key, {}).items() if v.get("sedd", 0) >= limit}
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
    sources = load_sources(args.feeds)
    totals = vikt_mod.region_totals(sources)
    items, report = fetch(sources, args.max_age_hours)
    cross_language = translate_titles(items, client, model, cache) if client else False
    clusters = merge_clusters(cluster(items))
    events = []
    for c in clusters:
        c["topics"], c["section_topics"] = tag(c)
    # Vikt (vikt.py): bredd i förhållande till regionernas källor, uthållighet över körningarna,
    # konsekvens enligt AI (bara rubrikerna) och, efter utkasten, källkontrollens bekräftelse.
    hist = vikt_mod.load_history()
    vikt_mod.update_history([c for c in clusters if len(independent(c)) >= 2], hist)
    for c in clusters:
        c["score"], c["vikt"] = vikt_mod.vikt(c, totals)
    clusters.sort(key=lambda c: c["score"], reverse=True)
    if client:
        top = clusters[:KONSEKVENS_TOPP]

        def kons_for(c):
            try:
                return vikt_mod.konsekvens(c, client, model, reply_text, cache)
            except Exception as e:
                print(f"  Konsekvens misslyckades: {e}", file=sys.stderr)
                return None
        with ThreadPoolExecutor(WORKERS) as pool:
            for c, k in zip(top, pool.map(kons_for, top)):
                c["konsekvens"] = k
                c["score"], c["vikt"] = vikt_mod.vikt(c, totals, k)
        clusters.sort(key=lambda c: c["score"], reverse=True)

    approved_path = ROOT / "data" / "godkanda.json"
    approved = set(json.loads(approved_path.read_text())) if approved_path.exists() else set()

    order = {"primar": 0, "forskning": 1, "media": 2, "kuraterat": 4}
    chosen = choose(clusters, args.limit)
    used_ids = set()
    for c in chosen:
        # Primärkällor först, sedan fria källor, betalväggar och statskontrollerade medier sist
        c["items"].sort(key=lambda i: (i["state_controlled"], order.get(i["source_type"], 3), i["paywall"]))
        assign_id(c, used_ids)
        c["fingeravtryck"] = hashlib.sha1((model + SYSTEM_PROMPT + user_prompt(c)).encode()).hexdigest()[:12]

    def draft_for(c):
        """Returnerar (utkast, källkontroll, ur_cachen). Källkontrollen körs på varje nytt utkast."""
        hit = cache["utkast"].get(c["id"])
        if hit and hit.get("fingeravtryck") == c["fingeravtryck"]:
            kontroll = hit.get("kontroll")
            if kontroll is None and client:
                try:
                    kontroll = kallkontroll.check(c, hit["utkast"], client, model, reply_text)
                except Exception as e:
                    print(f"  Källkontroll misslyckades: {e}", file=sys.stderr)
            return hit["utkast"], kontroll, True
        try:
            draft = summarize(c, client, model)
        except Exception as e:
            return {"osaker": True, "kommentar": f"AI-utkast misslyckades: {e}", "_fel": True}, None, False
        kontroll = None
        try:
            kontroll = kallkontroll.check(c, draft, client, model, reply_text)
        except Exception as e:
            print(f"  Källkontroll misslyckades: {e}", file=sys.stderr)
        return draft, kontroll, False

    with ThreadPoolExecutor(WORKERS) as pool:
        results = list(pool.map(draft_for, chosen))

    reused = 0
    for c, (draft, kontroll, from_cache) in zip(chosen, results):
        reused += from_cache
        c["score"], c["vikt"] = vikt_mod.vikt(c, totals, c.get("konsekvens"), kontroll["ok"] if kontroll else None)
        if draft is not None and not draft.get("_fel"):
            cache["utkast"][c["id"]] = {"utkast": draft, "kontroll": kontroll, "fingeravtryck": c["fingeravtryck"], "sedd": NOW}
        elif draft is not None:
            draft.pop("_fel", None)
        lead = c["items"][0]
        events.append({
            "id": c["id"],
            "amnen": c["topics"],
            "amnen_sektion": c["section_topics"],
            "poang": c["score"],
            "vikt": c["vikt"],
            "maste": c["vikt"]["maste"],
            "antal_kallor": len(independent(c)) or len({i["source_id"] for i in c["items"]}),
            "har_primarkalla": any(i["source_type"] in ("primar", "forskning") for i in c["items"]),
            "senast": max((i["published"] or "") for i in c["items"]) or None,
            "utkast": draft,
            "kallkontroll": kontroll,
            "perspektiv": perspective(c),
            "reserv_rubrik": lead["title"],
            "kallor": [{"namn": i["source_name"], "rubrik": i["title"], "url": i["url"],
                        "betalvagg": i["paywall"], "typ": i["source_type"], "land": i["country"],
                        "region": i["region"], "agare": i["owner"],
                        "statskontrollerad": i["state_controlled"]} for i in c["items"]],
            "granskad": c["id"] in approved,
        })
    events.sort(key=lambda e: e["poang"], reverse=True)
    vikt_mod.save_history(hist)

    # Autopiloten: notiser som klarar grindarna köas med klockslag och godkänns när fönstret gått ut
    import autopilot
    auto_status = autopilot.load_status()
    nya = autopilot.kor(events, approved, autopilot.load_settings(), auto_status)
    autopilot.save_status(auto_status)
    if nya:
        approved |= nya
        approved_path.write_text(json.dumps(sorted(approved), indent=2), encoding="utf-8")
        print(f"Autopiloten: {len(nya)} godkända, {len(auto_status['ko'])} väntar i kön")
    for e in events:
        e["granskad"] = e["id"] in approved
        e["autopilot"] = autopilot.grindar(e)
    if client:
        checked = [e["kallkontroll"] for e in events if e.get("kallkontroll")]
        flagged = sum(1 for k in checked if not k["ok"])
        print(f"Utkast: {len(chosen) - reused} nya, {reused} ur cachen · källkontroll: {len(checked)} kontrollerade, {flagged} med anmärkning")
        save_cache(cache)

    # Data bakom nyheten: öppna serier som kopplas till notiser (hämtas högst en gång per dygn)
    try:
        from data import attach, update
        attach(events, update())
    except Exception as e:
        print(f"  Data bakom nyheten misslyckades: {e}", file=sys.stderr)

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    payload = {"skapad": datetime.now(timezone.utc).isoformat(), "modell": model if client else None,
               "over_sprak": cross_language,
               "handelser": events, "kallrapport": report}
    (out / "flode.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    from newsletter import archive
    from render import render
    archive(events, approved, automatic=autopilot.automatiska(auto_status))
    render(payload, ROOT / "site" / "index.html")

    ok = sum(1 for r in report if r["ok"])
    print(f"Källor: {ok}/{len(report)} ok · artiklar: {len(items)} · händelser: {len(events)} · AI: {'på' if client else 'av'}")
    for r in report:
        if not r["ok"]:
            print(f"  FEL {r['id']}: {r['fel'][:120]}", file=sys.stderr)


if __name__ == "__main__":
    main()
