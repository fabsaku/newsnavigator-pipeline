#!/usr/bin/env python3
"""Instagram: bildkort (karusell) av granskade notiser, och publicering via Instagrams API.

  python instagram.py bygg                 gör kort för godkända notiser som saknar kort -> public/ig/<språk>/<id>/N.jpg + caption.txt
  python instagram.py posta [--antal 1] [--konto sv|en]
                                           publicerar de bästa opostade notiserna från senaste dygnet, ett konto i taget
  python instagram.py forhandsvisning DIR [--sprak en]   gör kort av dagens utkast (ogranskade, märkta) för att se formatet
  python instagram.py urval FIL DIR [--sprak en]         gör kort av handplockade notiser i en JSON-fil

Två konton: @newsnavigator.se på svenska (secrets IG_USER_ID, IG_ACCESS_TOKEN) och @news.navigator på engelska
(IG_USER_ID_EN, IG_ACCESS_TOKEN_EN). Vad varje konto får visa avgör utgava.py. Tillstånd och status ligger per konto i data/instagram/.

Korten är 1080x1350 (4:5), vit text på svart, i sajtens typografi: omslag med rubrik, sammanfattning och
täckningsremsan, sedan "Så ser världen på det" med en rubrik per region, och ett tredje kort när det finns
något att visa (data, ett diagram, USA blått och rött, eller "Källorna skiljer sig åt"). Högst tre kort.
Bara rubriker och våra egna texter, aldrig källornas text. Bilderna hämtas av Instagram från sajten.
"""
import argparse
import base64
import json
import os
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import utgava
from newsletter import load_archive, section_of, SECTIONS
from render import LEANS, REGION_ORDER, REGIONS, SHORT, country

ROOT = Path(__file__).parent
OUT = ROOT / "public" / "ig"
STATE_DIR = ROOT / "data" / "instagram"             # sv.json och en.json (kön), status-sv.json och status-en.json
LEGACY_STATE = ROOT / "data" / "instagram.json"     # före två konton: blir det svenska kontots kö
UTGAVOR = utgava.UTGAVOR
KONTON = {"sv": ("IG_USER_ID", "IG_ACCESS_TOKEN"), "en": ("IG_USER_ID_EN", "IG_ACCESS_TOKEN_EN")}
HANDTAG = {"sv": "@newsnavigator.se", "en": "@news.navigator"}
SITE_URL = os.environ.get("NN_SITE_URL", "https://newsnavigator.se").rstrip("/")
IMAGE_BASE = os.environ.get("IG_IMAGE_BASE", "https://newsnavigator.pages.dev").rstrip("/")
GRAPH = os.environ.get("IG_GRAPH", "https://graph.instagram.com").rstrip("/")
TZ = ZoneInfo("Europe/Stockholm")
MONTHS = ["januari", "februari", "mars", "april", "maj", "juni", "juli", "augusti", "september", "oktober", "november", "december"]
MONTHS_EN = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"]
HASHTAGS = {"sv": {"varlden": "#omvärlden #utrikes", "sverige": "#sverige #inrikes", "marknader": "#ekonomi #marknader #börsen",
                   "tech": "#teknik #ai", "vetenskap": "#vetenskap #forskning", "noje": "#nöje #spel #kultur"},
            "en": {"varlden": "#worldnews #global", "sverige": "#sweden #nordics", "marknader": "#markets #economy",
                   "tech": "#tech #ai", "vetenskap": "#science #research", "noje": "#entertainment #gaming #culture"}}
SPRAK = {"sv": 0, "en": 1}      # plats i render.REGIONS, LEANS och country, som är (svenska, engelska)
TXT = {
    "sv": {"swipe": "Nästa sida: så ser världen på det", "world": "Så ser världen på det",
           "world_lede": "Rubrikerna från {k} regioner, en per region. Länkar till alla hos oss.",
           "usa": "USA: blått och rött", "usa_lede": "Samma händelse i medier med olika publik.",
           "bla": "Blå publik", "mitten": "Mitten", "rod": "Röd publik",
           "usa_note": "Indelningen bygger på AllSides betyg av medierna, inte på vår bedömning.",
           "differ": "Källorna skiljer sig åt", "differ_note": "Vi väljer inte vilken version som är rätt. Vi visar vem som säger vad.",
           "data": "Data bakom nyheten", "year_ago": "Ett år tidigare", "source": "Källa",
           "src1": "källa", "srcn": "källor", "in": "i", "reg1": "region", "regn": "regioner",
           "blind_sv": "Saknas i svenska medier", "only_sv": "Bara i svenska medier",
           "mest_bla": "Mest i medier med blå publik", "mest_rod": "Mest i medier med röd publik",
           "ai_granskad": "Sammanfattad med hjälp av AI och granskad av redaktionen.",
           "ai_auto": "Sammanfattad med hjälp av AI och källkontrollerad. Publicerad utan manuell granskning; rättelser syns.",
           "words": {1: "en", 2: "två", 3: "tre", 4: "fyra", 5: "fem", 6: "sex", 7: "sju", 8: "åtta", 9: "nio"}},
    "en": {"swipe": "Next page: how the world sees it", "world": "How the world sees it",
           "world_lede": "Headlines from {k} regions, one per region. Links to all of them on our site.",
           "usa": "US: blue and red", "usa_lede": "The same story in outlets with different audiences.",
           "bla": "Blue audience", "mitten": "Centre", "rod": "Red audience",
           "usa_note": "The grouping uses AllSides' ratings of the outlets, not our own judgement.",
           "differ": "Sources differ", "differ_note": "We do not pick which version is right. We show who says what.",
           "data": "The data behind the story", "year_ago": "A year earlier", "source": "Source",
           "src1": "source", "srcn": "sources", "in": "in", "reg1": "region", "regn": "regions",
           "mest_bla": "Mostly in outlets with a blue audience", "mest_rod": "Mostly in outlets with a red audience",
           "ai_granskad": "Summarised with the help of AI and reviewed by the editors.",
           "ai_auto": "Summarised with the help of AI and source-checked. Published without manual review; corrections are visible.",
           "words": {1: "one", 2: "two", 3: "three", 4: "four", 5: "five", 6: "six", 7: "seven", 8: "eight", 9: "nine"}},
}


# ---------- Typsnitt och logga som data-URI:er, så att rendering blir lika överallt ----------

def _font(name):
    p = ROOT / "assets" / "fonts" / name
    return "data:font/woff2;base64," + base64.b64encode(p.read_bytes()).decode()


def _logo():
    p = ROOT / "assets" / "newsgator-vit.png"
    return "data:image/png;base64," + base64.b64encode(p.read_bytes()).decode()


def _css():
    return f"""
@font-face{{font-family:'SS4';src:url({_font('source-serif-4-latin-600-normal.woff2')});font-weight:600}}
@font-face{{font-family:'SS4';src:url({_font('source-serif-4-latin-400-normal.woff2')});font-weight:400}}
@font-face{{font-family:'SS3';src:url({_font('source-sans-3-latin-400-normal.woff2')});font-weight:400}}
@font-face{{font-family:'SS3';src:url({_font('source-sans-3-latin-600-normal.woff2')});font-weight:600}}
@font-face{{font-family:'SS3';src:url({_font('source-sans-3-latin-800-normal.woff2')});font-weight:800}}
*{{box-sizing:border-box;margin:0}}
html,body{{width:1080px;height:1350px;background:#000;color:#fff;font-family:'SS3',sans-serif;-webkit-font-smoothing:antialiased}}
.card{{width:1080px;height:1350px;padding:64px 72px 56px;display:flex;flex-direction:column;overflow:hidden;position:relative}}
.top{{display:flex;align-items:center;justify-content:space-between}}
.brand{{display:flex;align-items:center;gap:16px}}.brand img{{height:60px;width:auto}}
.brand span{{font-weight:800;font-size:25px;letter-spacing:.1em;text-transform:uppercase}}
.top .date{{font-size:24px;color:#8c8c8c}}
.kicker{{margin-top:58px;font-size:26px;color:#8c8c8c}}
h1{{font-family:'SS4',serif;font-weight:600;line-height:1.04;letter-spacing:-.015em;text-wrap:balance;margin-top:12px}}
.sum{{font-family:'SS4',serif;font-weight:400;font-size:37px;line-height:1.42;color:#d6d6d6;margin-top:34px}}
.clamp{{display:-webkit-box;-webkit-box-orient:vertical;overflow:hidden}}
.grow{{flex:1}}
.cov{{display:grid;grid-template-columns:repeat(9,minmax(0,1fr));gap:7px;margin-top:46px}}
.cov.usa{{grid-template-columns:repeat(3,minmax(0,1fr));max-width:560px;margin-top:0}}
.cov .c{{display:flex;flex-direction:column;gap:10px;min-width:0}}
.cov .c b{{display:block;height:10px;background:#2e2e2e}}
.cov .c i{{font-style:normal;font-size:21px;line-height:1.15;color:#8c8c8c}}
.cov .c i strong{{font-weight:700;color:#fff}}
.cov .on b{{background:#fff}}.cov .on i{{color:#d6d6d6}}
.meta{{font-size:27px;color:#8c8c8c;margin-top:26px;line-height:1.35}}
.meta b{{color:#fff;font-weight:600}}
.ai{{font-size:22px;color:#8c8c8c;margin-top:22px}}
.swipe{{font-size:24px;color:#8c8c8c}}
.foot{{display:flex;justify-content:space-between;align-items:baseline;padding-top:22px;border-top:1px solid #2e2e2e}}
.foot .site{{font-weight:600;font-size:26px}}.foot .n{{font-size:24px;color:#8c8c8c}}
.h2{{font-family:'SS4',serif;font-weight:600;font-size:54px;line-height:1.08;letter-spacing:-.01em;margin-top:56px}}
.lede{{font-family:'SS4',serif;font-weight:400;font-size:30px;line-height:1.4;color:#d6d6d6;margin-top:16px}}
.regions{{display:grid;grid-template-columns:1fr 1fr;gap:52px 48px;margin-top:48px}}
.regions.two{{grid-template-columns:1fr;gap:48px}}.regions.two p{{font-size:42px}}
.region h3{{font-size:26px;font-weight:600;padding-bottom:10px;border-bottom:1px solid #2e2e2e;margin-bottom:14px}}
.region p{{font-family:'SS4',serif;font-weight:400;font-size:37px;line-height:1.28;color:#fff}}
.region .who{{display:block;font-family:'SS3',sans-serif;font-size:24px;color:#8c8c8c;margin-top:12px}}
.region .who+p{{margin-top:30px}}
.stat{{display:inline-block;font-size:15px;font-weight:700;letter-spacing:.06em;border:1px solid #8c8c8c;color:#8c8c8c;padding:2px 5px 1px;margin-left:8px;vertical-align:2px}}
.sides{{display:grid;grid-template-columns:1fr 1fr;gap:40px 48px;margin-top:52px}}.sides p{{font-size:33px}}
.quote{{font-family:'SS4',serif;font-weight:400;font-size:38px;line-height:1.42;color:#fff;margin-top:32px}}
.bars{{margin-top:56px;display:flex;flex-direction:column;gap:52px}}
.bar{{display:grid;grid-template-columns:minmax(0,1fr);gap:14px}}
.bar .l{{display:flex;justify-content:space-between;align-items:baseline;gap:24px;font-size:30px;color:#d6d6d6}}
.bar .l b{{font-family:'SS4',serif;font-weight:600;font-size:60px;color:#fff;white-space:nowrap}}
.bar .t{{height:36px;background:#2e2e2e}}.bar .t i{{display:block;height:100%;background:#fff}}
.note{{font-size:22px;color:#8c8c8c;line-height:1.35;margin-top:24px}}
.banner{{position:absolute;left:0;right:0;top:0;background:#fff;color:#000;font-size:20px;font-weight:600;text-align:center;padding:8px}}
"""


def _e(s):
    import html
    return html.escape(s or "", quote=True)


WEEKDAYS = ["måndag", "tisdag", "onsdag", "torsdag", "fredag", "lördag", "söndag"]


def _date(ts, lang="sv"):
    d = datetime.fromtimestamp(ts, timezone.utc).astimezone(TZ)
    if lang == "en":
        return f"{d:%A} {d.day} {MONTHS_EN[d.month - 1]}"
    return f"{WEEKDAYS[d.weekday()].capitalize()} {d.day} {MONTHS[d.month - 1]}"


def _headline_size(text):
    n = len(text or "")
    return 94 if n <= 40 else 84 if n <= 60 else 74 if n <= 85 else 64 if n <= 110 else 54


def _top(date_sv):
    return (f'<div class="top"><div class="brand"><img src="{_logo()}" alt=""><span>Newsnavigator</span></div>'
            f'<div class="date">{_e(date_sv)}</div></div>')


def _foot(i, n):
    return f'<div class="foot"><span class="site">newsnavigator.se</span><span class="n">{i} / {n}</span></div>'


def _page(inner, banner="", lang="sv"):
    return (f'<!doctype html><html lang="{lang}"><head><meta charset="utf-8"><style>{_css()}</style></head><body>'
            f'<div class="card">{f"<div class=banner>{_e(banner)}</div>" if banner else ""}{inner}</div></body></html>')


def _words(n, lang="sv"):
    return TXT[lang]["words"].get(n, str(n))


def _coverage(ev, lang="sv"):
    p = ev.get("perspektiv") or {}
    counts = {r: len(v) for r, v in (p.get("per_region") or {}).items()}
    cells = []
    i = SPRAK[lang]
    for r in REGION_ORDER:
        n = counts.get(r, 0)
        name = SHORT.get(r, REGIONS[r])[i]
        if n:
            cells.append(f'<span class="c on"><b></b><i><strong>{n}</strong> {name}</i></span>')
        else:
            cells.append(f'<span class="c"><b></b><i>{name}</i></span>')
    return f'<div class="cov">{"".join(cells)}</div>'


def _meta(ev, lang="sv"):
    x = TXT[lang]
    p = ev.get("perspektiv") or {}
    n, k = ev["antal_kallor"], len(p.get("regioner", [])) or 1
    parts = [f"{n} {x['src1'] if n == 1 else x['srcn']} {x['in']} {_words(k, lang)} {x['reg1'] if k == 1 else x['regn']}"]
    blind = p.get("blind_flack")
    if lang == "sv":        # påståendet gäller svenska läsare och finns inte i den engelska utgåvan
        if blind == "saknas_i_sverige":
            parts.append(f"<b>{x['blind_sv']}</b>")
        elif blind == "bara_i_sverige":
            parts.append(f"<b>{x['only_sv']}</b>")
    if p.get("usa_blind") == "mest_bla":
        parts.append(f"<b>{x['mest_bla']}</b>")
    elif p.get("usa_blind") == "mest_rod":
        parts.append(f"<b>{x['mest_rod']}</b>")
    return f'<p class="meta">{". ".join(parts)}.</p>'


def _pick_regions(p, n=4):
    """Upp till fyra regioner i fast ordning, en rubrik per region (helst inte statskontrollerad)."""
    out = []
    for r in REGION_ORDER:
        items = (p.get("per_region") or {}).get(r) or []
        if not items:
            continue
        x = next((i for i in items if not i.get("statskontrollerad")), items[0])
        out.append((r, x))
    return out[:n]


def _headline_block(x, who):
    stat = '<span class="stat">STAT</span>' if x.get("statskontrollerad") else ""
    return (f'<p class="clamp" style="-webkit-line-clamp:4">{_e(x["rubrik"])}</p>'
            f'<span class="who">{_e(who)}{stat}</span>')


AI_GRANSKAD = TXT["sv"]["ai_granskad"]
AI_AUTOMATISK = TXT["sv"]["ai_auto"]


def _ai_line(ev, lang="sv"):
    return TXT[lang]["ai_auto" if ev.get("automatisk") else "ai_granskad"]


def slide_cover(ev, date, more, banner="", lang="sv"):
    d = ev.get("utkast") or {}
    i = SPRAK[lang]
    sec = next((s[1 + i] for s in SECTIONS if s[0] == section_of(ev)), "Världen" if lang == "sv" else "World")
    title = d.get(f"rubrik_{lang}") or ev["reserv_rubrik"]
    summary = d.get(f"sammanfattning_{lang}")
    size = _headline_size(title)
    lines = 5 if size <= 74 else 6
    swipe = f'<p class="swipe">{TXT[lang]["swipe"]}</p>' if more else ""
    return (_top(date) + f'<p class="kicker">{_e(sec)}</p><h1 style="font-size:{size}px">{_e(title)}</h1>'
            + (f'<p class="sum clamp" style="-webkit-line-clamp:{lines}">{_e(summary)}</p>' if summary else "")
            + f'{_coverage(ev, lang)}{_meta(ev, lang)}<p class="ai">{_ai_line(ev, lang)}</p>'
            f'<div class="grow"></div>{swipe}<div style="height:18px"></div>')


def slide_world(ev, lang="sv"):
    p = ev.get("perspektiv") or {}
    picks = _pick_regions(p)
    if len(picks) < 2:
        return None
    i = SPRAK[lang]
    blocks = "".join(f'<div class="region"><h3>{_e(REGIONS[r][i])}</h3>'
                     + _headline_block(x, x["kalla"] + (", " + country(x["land"])[i] if x.get("land") else ""))
                     + "</div>" for r, x in picks)
    k = len(p.get("regioner", []))
    return (f'<div class="h2">{TXT[lang]["world"]}</div><p class="lede">{TXT[lang]["world_lede"].format(k=_words(k, lang))}</p>'
            f'<div class="regions{" two" if len(picks) == 2 else ""}">{blocks}</div><div class="grow"></div>')


def slide_usa(ev, lang="sv"):
    p = ev.get("perspektiv") or {}
    usa = p.get("usa")
    if not usa or not (usa.get("bla") and usa.get("rod")):
        return None
    x, i = TXT[lang], SPRAK[lang]
    cells = []
    for key, name in (("bla", x["bla"]), ("mitten", x["mitten"]), ("rod", x["rod"])):
        n = len(usa.get(key) or [])
        cells.append(f'<span class="c{" on" if n else ""}"><b></b><i>{f"<strong>{n}</strong> " if n else ""}{name}</i></span>')
    cols = []
    for key, name in (("bla", x["bla"]), ("rod", x["rod"])):
        items = (usa.get(key) or [])[:2]
        cols.append(f'<div class="region"><h3>{name}</h3>'
                    + "".join(_headline_block(it, f'{it["kalla"]}, AllSides: {LEANS[it["lutning"]][i]}') for it in items) + "</div>")
    return (f'<div class="h2">{x["usa"]}</div><p class="lede">{x["usa_lede"]}</p>'
            f'<div class="cov usa" style="margin-top:34px">{"".join(cells)}</div><div class="sides">{"".join(cols)}</div>'
            f'<div class="grow"></div><p class="note">{x["usa_note"]}</p><div style="height:18px"></div>')


def slide_chart(ev, lang="sv"):
    """Stapeldiagram när notisen har en 'graf': {"titel", "enhet", "staplar": [[etikett, värde, visat värde], ...]}.
    Engelska kort kräver 'titel_en'."""
    g = ev.get("graf")
    if not g or not g.get("staplar") or (lang == "en" and not g.get("titel_en")):
        return None
    top = max(v for _, v, *_ in g["staplar"]) or 1
    bars = "".join(f'<div class="bar"><div class="l"><span>{_e(l)}</span><b>{_e(shown[0] if shown else str(v))}</b></div>'
                   f'<div class="t"><i style="width:{v / top * 100:.1f}%"></i></div></div>' for l, v, *shown in g["staplar"])
    note = f'<p class="note">{_e(g.get("not_en" if lang == "en" else "not"))}</p>' if g.get("not_en" if lang == "en" else "not") else ""
    return (f'<div class="h2">{TXT[lang]["differ"]}</div><p class="lede">{_e(g["titel_en" if lang == "en" else "titel"])}</p><div class="bars">{bars}</div>'
            f'<div class="grow"></div>{note}<div style="height:18px"></div>')


def slide_data(ev, lang="sv"):
    """Data bakom nyheten: första serien som stor siffra med kurva."""
    items = ev.get("data") or []
    if not items:
        return None
    d = items[0]
    vals = d.get("spark") or []
    svg = ""
    if len(vals) >= 2:
        lo, hi = min(vals), max(vals)
        span = (hi - lo) or 1
        pts = " ".join(f"{i * 936 / (len(vals) - 1):.1f},{200 - (v - lo) / span * 180:.1f}" for i, v in enumerate(vals))
        x, y = pts.split(" ")[-1].split(",")
        svg = (f'<svg viewBox="0 0 936 210" width="936" height="210" style="margin-top:36px;display:block">'
               f'<polyline points="{pts}" fill="none" stroke="#fff" stroke-width="4"/><circle cx="{x}" cy="{y}" r="9" fill="#fff"/></svg>')
    dec = d["decimaler"]
    now, was = f"{d['senaste']:.{dec}f} {d['enhet']}", f"{d['ar_sedan']:.{dec}f} {d['enhet']}"
    if lang == "sv":
        now, was = now.replace(".", ","), was.replace(".", ",")
    x = TXT[lang]
    return (f'<div class="h2">{x["data"]}</div><p class="lede">{_e(d["namn_" + lang])}, {_e(d["datum"])}</p>'
            f'<div style="font-family:SS4,serif;font-weight:600;font-size:150px;line-height:1;margin-top:40px;letter-spacing:-.02em">{_e(now)}</div>'
            f'<p class="meta" style="margin-top:14px">{x["year_ago"]} {_e(was)}. {x["source"]}: {_e(d["kalla"])}.</p>{svg}<div class="grow"></div>')


def slide_differ(ev, lang="sv"):
    d = ev.get("utkast") or {}
    text = d.get("oenighet" if lang == "sv" else "oenighet_en")
    if not text:
        return None
    size = 42 if len(text) < 380 else 38 if len(text) < 560 else 34
    return (f'<div class="h2">{TXT[lang]["differ"]}</div><p class="quote clamp" style="-webkit-line-clamp:13;font-size:{size}px">{_e(text)}</p>'
            f'<div class="grow"></div><p class="note">{TXT[lang]["differ_note"]}</p><div style="height:18px"></div>')


def slides(ev, banner="", max_slides=3, lang="sv"):
    """HTML för varje kort i karusellen: omslag, så ser världen på det, och ett tredje kort där det finns något att visa."""
    date = _date(ev.get("godkand_tid") or time.time(), lang)
    extra = [s for s in (slide_world(ev, lang), slide_data(ev, lang), slide_chart(ev, lang), slide_usa(ev, lang), slide_differ(ev, lang)) if s][:max_slides - 1]
    n = 1 + len(extra)
    out = [_page(slide_cover(ev, date, bool(extra), lang=lang) + _foot(1, n), banner, lang)]
    for i, inner in enumerate(extra, 2):
        out.append(_page(_top(date) + inner + _foot(i, n), banner, lang))
    return out


def caption(ev, lang="sv"):
    d = ev.get("utkast") or {}
    p = ev.get("perspektiv") or {}
    sec = section_of(ev)
    sv = lang == "sv"
    parts = [d.get(f"rubrik_{lang}") or ev["reserv_rubrik"], ""]
    if d.get(f"sammanfattning_{lang}"):
        parts += [d[f"sammanfattning_{lang}"], ""]
    if d.get(f"perspektiv_{lang}") and len(p.get("regioner", [])) >= 2:
        parts += [("Så ser världen på det: " if sv else "How the world sees it: ") + d[f"perspektiv_{lang}"], ""]
    if d.get("oenighet" if sv else "oenighet_en"):
        parts += [("Källorna skiljer sig åt: " if sv else "Sources differ: ") + d["oenighet" if sv else "oenighet_en"], ""]
    stat = " (statskontrollerat)" if sv else " (state-controlled)"
    names = [s["namn"] + (stat if s.get("statskontrollerad") else "") for s in ev["kallor"][:8]]
    more = f" och {len(ev['kallor']) - 8} till" if sv else f" and {len(ev['kallor']) - 8} more"
    parts += [("Källor: " if sv else "Sources: ") + ", ".join(names) + (more if len(ev["kallor"]) > 8 else ""), ""]
    parts += [("Hela notisen med alla länkar: " if sv else "Full story with all links: ") + notis_url(lang, ev["id"]), ""]
    if sv and d.get("rubrik_en"):
        parts += ["In English: " + d["rubrik_en"], ""]
    slut = ("Vi levererar nyheterna. Vad du gör av dem är upp till dig." if sv
            else "We deliver the news. What you do with it is up to you.")
    tags = "#nyheter #newsnavigator" if sv else "#news #newsnavigator"
    ending = "#sammanhang #källor" if sv else "#context #sources"
    parts += [_ai_line(ev, lang) + " " + slut, "", f"{tags} {HASHTAGS[lang].get(sec, '')} {ending}".replace("  ", " ").strip()]
    text = "\n".join(parts)
    return text[:2190]


def notis_url(lang, eid):
    return f"{SITE_URL}/{lang}/n/{eid}/"


def kan_byggas(ev, lang):
    """Det engelska kontot kräver engelsk rubrik och sammanfattning; det svenska tar vad som finns."""
    d = ev.get("utkast") or {}
    return bool(d.get("rubrik_en") and d.get("sammanfattning_en")) if lang == "en" else True


def _rubrik(ev, lang):
    return (ev.get("utkast") or {}).get(f"rubrik_{lang}") or ev["reserv_rubrik"]


# ---------- Rendering ----------

def _browser(p):
    try:
        return p.chromium.launch(channel="chrome")
    except Exception:
        return p.chromium.launch()


def render(ev, out_dir, banner="", lang="sv"):
    from playwright.sync_api import sync_playwright
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    for old in out_dir.glob("*.jpg"):
        old.unlink()
    files = []
    with sync_playwright() as p:
        b = _browser(p)
        pg = b.new_page(viewport={"width": 1080, "height": 1350}, device_scale_factor=1)
        for i, html_ in enumerate(slides(ev, banner, lang=lang), 1):
            pg.set_content(html_, wait_until="load")
            pg.wait_for_timeout(150)
            f = out_dir / f"{i}.jpg"
            pg.screenshot(path=str(f), type="jpeg", quality=92)
            files.append(f.name)
        b.close()
    (out_dir / "caption.txt").write_text(caption(ev, lang), encoding="utf-8")
    return files


# ---------- Tillstånd och status per konto ----------

def state_path(lang):
    return STATE_DIR / f"{lang}.json"


def status_path(lang):
    return STATE_DIR / f"status-{lang}.json"


def _las(path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def load_state(lang="sv"):
    s = _las(state_path(lang))
    if s is None and lang == "sv":
        s = _las(LEGACY_STATE)      # kön före två konton var det svenska kontots
    return s or {}


def save_state(s, lang="sv"):
    state_path(lang).parent.mkdir(parents=True, exist_ok=True)
    state_path(lang).write_text(json.dumps(s, ensure_ascii=False, indent=1), encoding="utf-8")


def load_status(lang="sv"):
    return _las(status_path(lang)) or {}


def spara_status(lang, **kv):
    status = load_status(lang)
    status.update(kv)
    status_path(lang).parent.mkdir(parents=True, exist_ok=True)
    status_path(lang).write_text(json.dumps(status, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


# ---------- Bygge ----------

def bygg(sprak=UTGAVOR):
    """Kort för alla godkända notiser i arkivet som hör hemma i kontots utgåva och saknar kort.
    Tar bort kort för notiser som lämnat arkivet eller utgåvan."""
    import shutil
    arkiv = load_archive()
    for lang in sprak:
        state, made = load_state(lang), 0
        valda = {sid: ev for sid, ev in arkiv.items() if utgava.visa(ev, lang) and kan_byggas(ev, lang)}
        for sid, ev in valda.items():
            dest = OUT / lang / sid
            if sid in state and (dest / "1.jpg").exists():
                continue
            try:
                files = render(ev, dest, lang=lang)
            except Exception as e:
                print(f"Instagram {HANDTAG[lang]}: kunde inte göra kort för {sid}: {e}", file=sys.stderr)
                continue
            state[sid] = {**state.get(sid, {}), "skapad": time.time(), "bilder": files, "poang": ev.get("poang", 0),
                          "godkand_tid": ev.get("godkand_tid", 0), "rubrik": _rubrik(ev, lang)}
            made += 1
        if (OUT / lang).exists():
            from lansering import skyddade      # lanseringens kort ska stå kvar tills batchen är postad
            for d in (OUT / lang).iterdir():
                if d.is_dir() and d.name not in valda and d.name not in skyddade(lang):
                    shutil.rmtree(d)
        for sid in [k for k in state if k not in valda and not state[k].get("postad")]:
            state.pop(sid)
        save_state(state, lang)
        print(f"Instagram {HANDTAG[lang]}: {made} nya kort, {len(state)} i kön")
    if OUT.exists():        # kort från före språkmapparna
        for d in OUT.iterdir():
            if d.is_dir() and d.name not in UTGAVOR:
                shutil.rmtree(d)


# ---------- Publicering ----------

def _api(path, params, method="POST"):
    if method == "GET":
        req = urllib.request.Request(f"{GRAPH}/{path}?{urllib.parse.urlencode(params)}")
    elif method == "DELETE":
        req = urllib.request.Request(f"{GRAPH}/{path}?{urllib.parse.urlencode(params)}", method="DELETE")
    else:
        req = urllib.request.Request(f"{GRAPH}/{path}", data=urllib.parse.urlencode(params).encode(), method="POST")
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read())


def publish_one(lang, sid, item, user, token):
    urls = [f"{IMAGE_BASE}/ig/{lang}/{sid}/{f}" for f in item["bilder"]]
    cap = (OUT / lang / sid / "caption.txt").read_text(encoding="utf-8")
    if len(urls) == 1:
        container = _api(f"{user}/media", {"image_url": urls[0], "caption": cap, "access_token": token})["id"]
    else:
        children = [_api(f"{user}/media", {"image_url": u, "is_carousel_item": "true", "access_token": token})["id"] for u in urls]
        container = _api(f"{user}/media", {"media_type": "CAROUSEL", "children": ",".join(children), "caption": cap, "access_token": token})["id"]
    for _ in range(20):  # vänta tills Instagram har hämtat bilderna
        st = _api(container, {"fields": "status_code", "access_token": token}, method="GET").get("status_code")
        if st == "FINISHED":
            break
        if st == "ERROR":
            raise RuntimeError("Instagram kunde inte bearbeta bilderna")
        time.sleep(3)
    return _api(f"{user}/media_publish", {"creation_id": container, "access_token": token})["id"]


def _posta_konto(lang, antal, hours):
    user_var, token_var = KONTON[lang]
    user, token = os.environ.get(user_var), os.environ.get(token_var)
    state = load_state(lang)
    since = time.time() - hours * 3600
    queue = sorted((sid for sid, it in state.items() if not it.get("postad") and it.get("godkand_tid", 0) >= since),
                   key=lambda sid: state[sid].get("poang", 0), reverse=True)[:antal]
    fel = None
    if not queue:
        print(f"Instagram {HANDTAG[lang]}: inget nytt att posta")
    for sid in queue:
        if not (user and token):
            print(f"Instagram {HANDTAG[lang]}: skulle posta {sid}: {state[sid]['rubrik'][:70]} ({user_var}/{token_var} saknas)")
            continue
        try:
            media_id = publish_one(lang, sid, state[sid], user, token)
            state[sid].update({"postad": time.time(), "ig_id": media_id})
            print(f"Instagram {HANDTAG[lang]}: postade {sid} ({media_id})")
        except Exception as e:
            fel = str(e)[:120]
            print(f"Instagram {HANDTAG[lang]}: misslyckades med {sid}: {e}", file=sys.stderr)
    save_state(state, lang)
    spara_status(lang, senast=time.time(), secrets=bool(user and token), fel=fel,
                 vantar=sum(1 for it in state.values() if not it.get("postad") and it.get("godkand_tid", 0) >= since))


def posta(antal=1, hours=36, konton=None):
    import autopilot
    if autopilot.load_settings().get("tyst"):
        print("Instagram: tyst läge, inget postas")
        return
    for lang in konton or UTGAVOR:
        _posta_konto(lang, antal, hours)


def urval(fil, out, lang="sv"):
    """Kort för handplockade notiser i en JSON-fil (lista av händelser, gärna med 'graf')."""
    evs = json.loads(Path(fil).read_text(encoding="utf-8"))
    for i, e in enumerate(evs, 1):
        e.setdefault("godkand_tid", time.time())
        files = render(e, Path(out) / f"{i:02d}-{e['id']}", lang=lang)
        print(f"{i:02d}", len(files), "kort:", _rubrik(e, lang)[:60])


def forhandsvisning(out, n=2, lang="sv"):
    flode = json.loads((ROOT / "data" / "flode.json").read_text(encoding="utf-8"))
    evs = [e for e in flode["handelser"] if (e.get("utkast") or {}).get(f"rubrik_{lang}") and not (e.get("utkast") or {}).get("osaker")
           and utgava.visa(e, lang) and kan_byggas(e, lang)][:n]
    for e in evs:
        e["godkand_tid"] = time.time()
        banner = "Förhandsvisning · ogranskat utkast" if lang == "sv" else "Preview · unreviewed draft"
        files = render(e, Path(out) / e["id"], banner=banner, lang=lang)
        print(e["id"], len(files), "kort:", _rubrik(e, lang)[:60])


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("kommando", choices=["bygg", "posta", "forhandsvisning", "urval"])
    ap.add_argument("mapp", nargs="?")
    ap.add_argument("mapp2", nargs="?")
    ap.add_argument("--antal", type=int, default=1)
    ap.add_argument("--konto", choices=["sv", "en", "alla"], default="alla")
    ap.add_argument("--sprak", choices=["sv", "en"], default="sv")
    a = ap.parse_args()
    if a.kommando == "bygg":
        bygg()
    elif a.kommando == "posta":
        posta(a.antal, konton=None if a.konto == "alla" else [a.konto])
    elif a.kommando == "urval":
        urval(a.mapp, a.mapp2 or "/tmp/ig", a.sprak)
    else:
        forhandsvisning(a.mapp or "/tmp/ig", a.antal if a.antal > 1 else 2, a.sprak)
