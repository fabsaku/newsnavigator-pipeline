#!/usr/bin/env python3
"""Den publika sajten (sajt.py, eftersom site är ett modulnamn i Python): en publikation med egna sidor, byggd av granskade notiser.

Sidor: förstasidan, en sida per notis (delbar länk), en sida per sektion, Navigatorn,
Om Newsnavigator med principerna, Källor, och RSS-flöden på svenska och engelska.

Två lägen:
  tree  (produktion)       /, /n/<id>/, /varlden/, /om/, /kallor/, /feed.xml
  flat  (förhandsvisning)  index.html, n-<id>.html, varlden.html, om.html ... i en mapp

Inget på sidorna beror på klockslaget då de byggdes. Därför ändras filerna bara när
innehållet ändras, och sajten byggs bara om när något nytt har godkänts. Dagens datum
i sidhuvudet sätts i läsarens webbläsare.
"""
import html
import os
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

import yaml

import rattelser
import spar
import utgava
from newsletter import SECTIONS, section_of, utan_upprepningar
from render import (CSS, FONTS_URL, JS, stampel, tidstext, LEANS, REGION_ORDER, REGIONS, _both, _e, _mascot, country, meta_line,
                    story_featured, story_full, story_item, story_lead)

ROOT = Path(__file__).parent
SITE_URL = os.environ.get("NN_SITE_URL", "https://newsnavigator.se").rstrip("/")
CONTACT = "we@newsnavigator.se"
TZ = ZoneInfo("Europe/Stockholm")
FRONT_DAYS, SECTION_DAYS = 3, 7
LATEST, PER_SECTION = 5, 7  # Senaste-listan, och rubriker per sektionsblock utöver den utvalda
SPAR_PER_SPAR = 6

MONTHS_SV = ["januari", "februari", "mars", "april", "maj", "juni", "juli", "augusti",
             "september", "oktober", "november", "december"]
MONTHS_EN = ["January", "February", "March", "April", "May", "June", "July", "August",
             "September", "October", "November", "December"]
TYPES = {"media": ("Medier", "Media"), "primar": ("Primärkälla", "Primary source"),
         "forskning": ("Forskning", "Research"), "kuraterat": ("Kuraterad lista", "Curated list")}

SITE_CSS = CSS + """
nav{border-bottom:1px solid var(--rule);position:relative}
nav::after{content:'';position:absolute;right:0;top:0;bottom:1px;width:36px;background:linear-gradient(to right,transparent,var(--bg));pointer-events:none}
@media (min-width:900px){nav::after{display:none}}
nav .w{display:flex;gap:2px;overflow-x:auto;scrollbar-width:none}nav .w::-webkit-scrollbar{display:none}
nav a{flex:0 0 auto;display:flex;align-items:center;min-height:46px;padding:0 11px;text-decoration:none;font:600 15px var(--sans);color:var(--mute);border-bottom:2px solid transparent;white-space:nowrap}
nav a:hover{color:var(--ink)}nav a[aria-current=page]{color:var(--ink);border-bottom-color:var(--ink)}
nav a:first-child{padding-left:0}
main.w{padding-top:28px}
.lang a{display:flex;align-items:center;height:40px;padding:0 8px;color:var(--mute);font:600 13px var(--sans);text-decoration:none}.lang a:hover{color:var(--ink);text-decoration:underline}
.pick{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:24px;max-width:860px;margin:28px 0 0}
.pick a{display:block;border-top:2px solid var(--ink);padding-top:14px;text-decoration:none;color:var(--text)}
.pick a:hover h2{text-decoration:underline}
.pick h2{font-size:32px;margin:0 0 8px}.pick p{font:400 18px/1.5 var(--serif);margin:0}
@media (max-width:640px){.pick{grid-template-columns:minmax(0,1fr)}}

/* Förstasidan */
.top{display:grid;grid-template-columns:minmax(0,7fr) minmax(0,4fr);gap:0 40px;align-items:start}
.top .story.lead{padding-right:40px;border-right:1px solid var(--rule)}
.latest h2{font:600 15px var(--sans);color:var(--ink);padding-bottom:10px;border-bottom:1px solid var(--rule);margin-bottom:14px}
.block{margin-top:44px;padding-top:14px;border-top:2px solid var(--ink)}
.block>h2{font-size:26px;margin-bottom:18px}
.block>h2 a{text-decoration:none}.block>h2 a:hover{text-decoration:underline}
.block .grid{display:grid;grid-template-columns:minmax(0,7fr) minmax(0,4fr);gap:0 40px;align-items:start}
.block .grid .story.featured{padding-right:40px;border-right:1px solid var(--rule)}
.block .one{max-width:760px}
.block .list h3{font-size:19px}
.block .more{margin-top:16px;font-size:14px}
.block .more a{color:var(--mute);text-decoration:none}.block .more a:hover{color:var(--ink);text-decoration:underline}
@media (max-width:860px){
.top,.block .grid{grid-template-columns:minmax(0,1fr)}
.top .story.lead,.block .grid .story.featured{padding-right:0;border-right:0;padding-bottom:28px;margin-bottom:24px;border-bottom:1px solid var(--rule)}
}

/* Sidor */
.pagetitle{font-size:40px;line-height:1.08;letter-spacing:-.012em;margin:4px 0 10px}
.dold{position:absolute;width:1px;height:1px;overflow:hidden;clip-path:inset(50%);white-space:nowrap}
.lede{font:400 21px/1.45 var(--serif);color:var(--text);max-width:60ch;margin:0 0 10px}
.crumb{display:flex;flex-wrap:wrap;gap:4px 18px;font-size:14px;color:var(--mute);margin:0 0 20px}
.crumb a{color:var(--ink);text-decoration:none}.crumb a:hover{text-decoration:underline}
.aiNote{font-size:14px;color:var(--mute);border-top:1px solid var(--rule);padding-top:14px;margin-top:32px;max-width:66ch;line-height:1.5}
.aiNote a{color:var(--text)}
.more-h{font-size:22px;margin:40px 0 12px;padding-top:14px;border-top:2px solid var(--ink)}
.prose{max-width:66ch}
.prose p{font:400 18px/1.55 var(--serif);color:var(--text);margin:0 0 18px}
.prose h2{font-size:28px;margin:40px 0 14px;line-height:1.15}
.prose a{color:var(--ink)}
.prose b{color:var(--ink);font-weight:600}
.steps{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:24px 32px;margin:8px 0 0;max-width:1000px}
@media (max-width:900px){.steps{grid-template-columns:repeat(2,minmax(0,1fr))}}
@media (max-width:520px){.steps{grid-template-columns:minmax(0,1fr)}}
.step h3{font-size:22px;margin:0 0 6px}
.step h3 .n{color:var(--mute);font-weight:400;margin-right:8px}
.step p{font:400 16px/1.5 var(--sans);color:var(--text);margin:0}
.princ{list-style:none;margin:0;padding:0;counter-reset:p;max-width:66ch}
.princ li{counter-increment:p;border-top:1px solid var(--rule);padding:18px 0 18px 52px;position:relative;font:400 17px/1.5 var(--serif);color:var(--text)}
.princ li::before{content:counter(p);position:absolute;left:0;top:18px;font:600 22px/1.2 var(--serif);color:var(--mute)}
.princ li b{display:block;color:var(--ink);font-size:21px;margin-bottom:4px;font-weight:600}
.srcs{list-style:none;margin:0;padding:0;max-width:960px}
.srcs li{display:grid;grid-template-columns:minmax(0,1.5fr) minmax(0,1.3fr) minmax(0,1.4fr);gap:6px 20px;border-top:1px solid var(--rule);padding:11px 0;font-size:15px;align-items:baseline}
.srcs li a{text-decoration:none;font-weight:600}.srcs li a:hover{text-decoration:underline}
.srcs li .kind{color:var(--mute)}
.srcs li .flags{color:var(--mute);text-align:right}
.group-h{font-size:24px;margin:36px 0 6px;padding-top:12px;border-top:2px solid var(--ink);display:flex;align-items:baseline;gap:12px}
.group-h .n{font:400 15px var(--sans);color:var(--mute)}
.empty{font:400 19px/1.5 var(--serif);color:var(--text);max-width:60ch}

/* Sidfot */
footer{border-top:1px solid var(--ink);margin-top:64px;padding:28px 0 48px}
.ft{display:grid;grid-template-columns:minmax(0,1.4fr) minmax(0,1fr);gap:20px 48px;font-size:14px;color:var(--mute);line-height:1.5}
.ft p{max-width:60ch;margin:0 0 8px}
.ft .links{display:flex;flex-direction:column;gap:6px;align-items:flex-start}
.ft .links a{color:var(--text);text-decoration:none}.ft .links a:hover{color:var(--ink);text-decoration:underline}
.ft .copy{grid-column:1/-1;max-width:none;padding-top:12px;border-top:1px solid var(--rule)}
@media (max-width:720px){
.pagetitle{font-size:32px}
.srcs li{grid-template-columns:minmax(0,1fr) minmax(0,1fr)}.srcs li .flags{grid-column:1/-1;text-align:left}
.ft{grid-template-columns:minmax(0,1fr)}
}
"""


# ---------- Adresser ----------

class Urls:
    """flat: förhandsvisning i en mapp. Annars ett träd, och med `lang` ett språkträd under /sv/ eller /en/."""

    def __init__(self, flat, lang=None):
        self.flat = flat
        self.lang = None if flat else lang
        self.p = f"/{self.lang}" if self.lang else ""

    def home(self):
        return "./" if self.flat else f"{self.p}/"

    def story(self, sid):
        return f"n-{sid}.html" if self.flat else f"{self.p}/n/{sid}/"

    def section(self, slug):
        return f"{slug}.html" if self.flat else f"{self.p}/{slug}/"

    def page(self, name):
        return f"{name}.html" if self.flat else f"{self.p}/{name}/"

    def file(self, name):
        """Filer som hör till språkträdet, till exempel flödet."""
        return name if self.flat else f"{self.p}/{name}"

    def asset(self, name):
        """Delade filer i roten, till exempel loggan."""
        return name if self.flat else f"/{name}"

    def disk(self, out, url):
        if self.flat:
            return out / ("index.html" if url == "./" else url)
        if url == "/":
            return out / "index.html"
        if url.endswith("/"):
            return out / url.strip("/") / "index.html"
        return out / url.lstrip("/")

    def absolute(self, url):
        return url if self.flat else SITE_URL + url


# ---------- Hjälpare ----------

def _bb(sv, en):
    """Tvåspråkig text som redan är HTML (för texter vi skriver själva)."""
    return f'<span class="sv">{sv}</span><span class="en">{en}</span>'


def _t(u, sv, en):
    """Text för sidhuvud, titel och beskrivning på trädets språk (svenska om trädet är tvåspråkigt)."""
    return en if u.lang == "en" else sv


_SPAN = re.compile(r'<span class="(sv|en)">(.*?)</span>', re.S)


def _lock(text, lang):
    """Språkträdets sidor har bara sitt eget språk i koden, inte det gömda andra."""
    return _SPAN.sub(lambda m: m.group(2) if m.group(1) == lang else "", text)


def _date(ts, clock=False):
    if clock:
        return tidstext(ts)
    d = datetime.fromtimestamp(ts, timezone.utc).astimezone(TZ)
    return f"{d.day} {MONTHS_SV[d.month - 1]} {d.year}", f"{d.day} {MONTHS_EN[d.month - 1]} {d.year}"


def _section_names(slug):
    return next(((sv, en) for k, sv, en, _ in SECTIONS if k == slug), ("Världen", "World"))


def _write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


# ---------- Sidmall ----------

def _shell(u, *, title, body, active=None, description="", path="/", og=None, banner="", noindex=True, updated=None, nsources=0):
    nav = [(u.home(), "Senaste", "Latest", "hem")]
    nav += [(u.section(k), sv, en, k) for k, sv, en, _ in SECTIONS if not (u.lang == "en" and k == "sverige")]
    nav += [(u.page("spar"), "Spår", "Focus areas", "spar"),
            (u.page("navigatorn"), "Navigatorn", "Navigatorn", "navigatorn"), (u.page("om"), "Om", "About", "om"),
            (u.page("kallor"), "Källor", "Sources", "kallor")]
    links = "".join(f'<a href="{_e(h)}"{" aria-current=page" if k == active else ""}>{_both(sv, en)}</a>' for h, sv, en, k in nav)
    canonical = u.absolute(path)
    lang = u.lang
    other = "sv" if lang == "en" else "en"
    ogtags = ""
    if og:
        ogtags = (f'<meta property="og:type" content="{og.get("type", "website")}"><meta property="og:title" content="{_e(og["title"])}">'
                  f'<meta property="og:description" content="{_e(og.get("description", ""))}"><meta property="og:url" content="{_e(canonical)}">'
                  f'<meta property="og:image" content="{_e(u.absolute(u.asset("newsgator.png")))}"><meta property="og:site_name" content="Newsnavigator">'
                  f'<meta name="twitter:card" content="summary">')
    stamp = ""
    if updated:
        sv, en = _date(updated, clock=True)
        stamp = f'<p>{_both(f"Senast uppdaterad {sv}.", f"Last updated {en}.")} '
    else:
        stamp = "<p>"
    stamp += _both(f"{nsources} källor i åtta regioner.", f"{nsources} sources in eight regions.") + "</p>"
    alt = ""
    if lang and path == u.home():
        alt = (f'<link rel="alternate" hreflang="sv" href="{SITE_URL}/sv/"><link rel="alternate" hreflang="en" href="{SITE_URL}/en/">'
               f'<link rel="alternate" hreflang="x-default" href="{SITE_URL}/">')
    switch = (f'<div class="lang"><a href="{_e(f"/{other}/")}" hreflang="{other}" lang="{other}">{"Svenska" if other == "sv" else "English"}</a></div>' if lang else
              '<div class="lang" role="group" aria-label="Språk"><button type="button" data-l="sv" aria-pressed="true">SV</button><button type="button" data-l="en" aria-pressed="false">EN</button></div>')
    page = f"""<!doctype html>
<html lang="{lang or 'sv'}"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{_e(title)}</title>
<meta name="description" content="{_e(description)}">
{'<meta name="robots" content="noindex">' if noindex else ''}
<link rel="canonical" href="{_e(canonical)}">
<link rel="icon" href="{_e(u.asset("newsgator.png"))}">
{f'<link rel="alternate" type="application/rss+xml" title="Newsnavigator{" (English)" if lang == "en" else ""}" href="{_e(u.file("feed.xml"))}">' if lang else
 f'<link rel="alternate" type="application/rss+xml" title="Newsnavigator" href="{_e(u.file("feed.xml"))}"><link rel="alternate" type="application/rss+xml" title="Newsnavigator (English)" href="{_e(u.file("feed-en.xml"))}">'}
{alt}{ogtags}
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="stylesheet" href="{FONTS_URL}">
<style>{SITE_CSS}</style></head>
<body{' class="en"' if lang == "en" else ''}>
{f'<div class="banner"><div class="w">{banner}</div></div>' if banner else ''}
<header><div class="w mast">
<span class="date" data-date></span>
<a class="brand" href="{_e(u.home())}">{_mascot()}<span>Newsnavigator</span></a>
{switch}
</div></header>
<nav aria-label="Sektioner"><div class="w">{links}</div></nav>
<main class="w">{body}</main>
<footer><div class="w ft">
<div><p>{_both("Notiserna sammanfattas med hjälp av AI. Varje notis säger hur den har granskats: av redaktionen, eller med maskinell källkontroll utan manuell granskning. Varje notis länkar till originalkällorna. Statskontrollerade medier är märkta STAT. Ansvarig utgivare: Fabian Sandberg Kuylenstierna.", "Stories are summarised with the help of AI. Each story says how it was reviewed: by the editors, or machine source-checked without manual review. Every story links to its original sources. State-controlled media are marked STAT. Publisher: Fabian Sandberg Kuylenstierna.")}</p>{stamp}</div>
<div class="links"><a href="{_e(u.page("om"))}">{_both("Om Newsnavigator och principerna", "About Newsnavigator and the principles")}</a><a href="{_e(u.page("kallor"))}">{_both("Alla källor", "All sources")}</a><a href="{_e(u.page("rattelser"))}">{_both("Rättelser", "Corrections")}</a><a href="{_e(u.page("navigatorn"))}">{_both("Navigatorn, morgonbrevet", "Navigatorn, the morning brief")}</a><a href="{_e(u.file("feed.xml"))}">RSS</a><a href="mailto:{CONTACT}">{CONTACT}</a></div>
<p class="copy">© 2026 Newsnavigator</p>
</div></footer>
{f'<script>window.NN_LANG="{lang}"</script>' if lang else ''}<script>{JS}</script>
</body></html>"""
    return _lock(page, lang) if lang else page


# ---------- Sidor ----------

def _latest(events):
    return max((e.get("godkand_tid", 0) for e in events), default=None) or None


def _waiting(u):
    return (f'<section style="padding:20px 0 40px;max-width:640px"><h1 class="pagetitle">{_both("Newsnavigator öppnar snart.", "Newsnavigator opens soon.")}</h1>'
            f'<p class="lede">{_both("Nyheter från över 130 källor i åtta regioner, samlade på ett ställe och granskade innan de publiceras. Du ser hur olika länder, och blå och röda medier i USA, berättar om samma händelse. Varje notis länkar till originalet.", "News from more than 130 sources in eight regions, gathered in one place and reviewed before publication. See how different countries, and blue and red media in the US, cover the same event. Every story links to the original.")}</p>'
            f'<p class="lede">{_both("Varje morgon kommer Navigatorn, vårt morgonbrev.", "Every morning: Navigatorn, our morning brief.")} '
            f'<a href="{_e(u.page("om"))}">{_both("Läs om hur vi arbetar", "Read about how we work")}</a>.</p></section>')


def _section_link(u, slug):
    sv, en = _section_names(slug)
    return (_both(sv, en), u.section(slug))


def front(u, events, sources, banner, noindex):
    if not events:
        body = _waiting(u)
    else:
        alla, events = events, utan_upprepningar(events)
        lead, rest = events[0], events[1:]
        latest = sorted(rest, key=lambda e: e.get("godkand_tid", 0), reverse=True)[:LATEST]
        rest = [e for e in rest if not any(e is x for x in latest)]
        top = (f'<section class="top">{story_lead(lead, u.story(lead["id"]), kicker=_section_link(u, section_of(lead)))}'
               f'<aside class="latest"><h2>{_both("Senaste", "Latest")}</h2><ul class="list">'
               + "".join(story_item(e, u.story(e["id"]), kicker=_section_link(u, section_of(e))) for e in latest)
               + "</ul></aside></section>")
        blocks = []
        for slug, sv, en, _ in sorted(SECTIONS, key=lambda s: u.lang == "sv" and s[0] != "sverige"):
            items = [e for e in rest if section_of(e) == slug]
            if not items:
                continue
            first, more = items[0], items[1:PER_SECTION + 1]
            left = story_featured(first, u.story(first["id"]))
            tail = sum(1 for e in alla if section_of(e) == slug) - 1 - len(more)
            link = (f'<p class="more"><a href="{_e(u.section(slug))}">{_both(f"Fler notiser i {sv}", f"More in {en}")} ({tail})</a></p>'
                    if tail > 0 else "")
            if more:
                right = f'<ul class="list">{"".join(story_item(e, u.story(e["id"])) for e in more)}</ul>'
                inner = f'<div class="grid">{left}<div>{right}{link}</div></div>'
            else:
                inner = f'<div class="one">{left}{link}</div>'
            blocks.append(f'<section class="block"><h2><a href="{_e(u.section(slug))}">{_both(sv, en)}</a></h2>{inner}</section>')
        body = '<h1 class="dold">Newsnavigator</h1>' + top + "".join(blocks)
    return _shell(u, title="Newsnavigator", body=body, active="hem", path=u.home(), banner=banner, noindex=noindex,
                  description=_t(u, "Nyheter från hela världen, samlade och granskade. Se hur olika länder och medier berättar om samma händelse.",
                                 "News from around the world, gathered and reviewed. See how different countries and outlets tell the same event."),
                  og={"title": "Newsnavigator", "description": _t(u, "Vi levererar nyheterna. Vad du gör av dem är upp till dig.",
                                                                  "We deliver the news. What you make of it is up to you.")},
                  updated=_latest(events), nsources=len(sources))


def section_page(u, slug, events, sources, banner, noindex):
    sv, en = _section_names(slug)
    body = f'<h1 class="pagetitle">{_both(sv, en)}</h1>'
    if events:
        first, more = events[0], events[1:]
        body += f'<div style="margin-top:22px">{story_lead(first, u.story(first["id"]))}</div>'
        if more:
            body += f'<ul class="list" style="margin-top:36px;max-width:760px">{"".join(story_item(e, u.story(e["id"])) for e in more)}</ul>'
    else:
        body += f'<p class="empty">{_both("Inga granskade notiser i den här sektionen de senaste dagarna.", "No reviewed stories in this section in the past few days.")}</p>'
    return _shell(u, title=f"{_t(u, sv, en)}, Newsnavigator", body=body, active=slug, path=u.section(slug), banner=banner, noindex=noindex,
                  description=_t(u, f"Granskade nyheter: {sv}.", f"Reviewed news: {en}."), updated=_latest(events), nsources=len(sources))


def spar_page(u, events, sources, banner, noindex):
    """Bevakningsspåren: det senaste i varje spår, så att ett område går att följa över tid."""
    block = []
    for slug, sv, en, om_sv, om_en in spar.SPAR:
        items = [e for e in events if slug in spar.av(e)][:SPAR_PER_SPAR]

        def rad(e):
            d = spar.delspar(e) if slug == "teknik" else None
            return story_item(e, u.story(e["id"]), kicker=(_both(d[1], d[2]), f'{u.page("spar")}#teknik') if d else "")
        lista = (f'<ul class="list" style="max-width:760px">{"".join(rad(e) for e in items)}</ul>' if items else
                 f'<p class="empty">{_both("Inga notiser i det här spåret de senaste två veckorna.", "No stories in this area in the past two weeks.")}</p>')
        block.append(f'<section class="block" id="{slug}"><h2>{_both(sv, en)}</h2><p class="lede">{_both(om_sv, om_en)}</p>{lista}</section>')
    body = (f'<h1 class="pagetitle">{_both("Spår", "Focus areas")}</h1>'
            f'<p class="lede">{_both("Fem områden som redaktionen följer särskilt. De väger lite extra i urvalet men ändrar aldrig hur en notis är skriven.", "Five areas the editors follow closely. They carry some extra weight in selection but never change how a story is written.")}</p>'
            + "".join(block))
    return _shell(u, title=f'{_t(u, "Spår", "Focus areas")}, Newsnavigator', body=body, active="spar", path=u.page("spar"), banner=banner, noindex=noindex,
                  description=_t(u, "Fem områden som redaktionen följer särskilt.", "Five areas the editors follow closely."), nsources=len(sources))


def rattelser_page(u, poster, sources, banner, noindex):
    """Allt som rättats eller tagits bort efter publicering, senast först (princip 8)."""
    def rad(p):
        rubrik = _e(p.get(f"rubrik_{'en' if u.lang == 'en' else 'sv'}") or p.get("rubrik_sv") or "")
        datum = stampel(p["tid"])
        if p.get("typ") == "borttagen":
            vad = _both("Notisen togs bort efter publicering.", "The story was removed after publication.")
        else:
            vad = _both(_e(p.get("vad_sv") or ""), _e(p.get("vad_en") or p.get("vad_sv") or ""))
        return f'<li><h3>{rubrik}</h3><p class="meta">{datum}. {vad}</p></li>'
    lista = (f'<ul class="list" style="max-width:760px">{"".join(rad(p) for p in sorted(poster, key=lambda x: x["tid"], reverse=True))}</ul>' if poster else
             f'<p class="empty">{_both("Inga rättelser än.", "No corrections yet.")}</p>')
    body = (f'<h1 class="pagetitle">{_both("Rättelser", "Corrections")}</h1>'
            f'<p class="lede">{_both("Det vi har rättat eller tagit bort efter publicering.", "What we have corrected or removed after publication.")}</p>{lista}')
    return _shell(u, title=f'{_t(u, "Rättelser", "Corrections")}, Newsnavigator', body=body, active="rattelser", path=u.page("rattelser"),
                  banner=banner, noindex=noindex, description=_t(u, "Det vi har rättat eller tagit bort efter publicering.", "What we have corrected or removed after publication."),
                  nsources=len(sources))


def _ai_note(ev):
    if ev.get("automatisk"):
        return _both("Sammanfattad med hjälp av AI och maskinellt källkontrollerad. Publicerad utan manuell granskning; rättelser syns. "
                     "Vi återger inte text från källorna, bara rubrik och länk. Fel? Skriv till",
                     "Summarised with the help of AI and machine source-checked. Published without manual review; corrections are visible. "
                     "We do not reproduce the sources’ text, only the headline and link. Spotted an error? Write to")
    return _both("Sammanfattad med hjälp av AI och granskad av redaktionen. Vi återger inte text från källorna, bara rubrik och länk. Fel? Skriv till",
                 "Summarised with the help of AI and reviewed in Swedish by the editors. We do not reproduce the sources’ text, only the headline and link. Spotted an error? Write to")


def story_page(u, ev, related, sources, banner, noindex):
    d = ev.get("utkast") or {}
    slug = section_of(ev)
    sv, en = _section_names(slug)
    lg = "en" if u.lang == "en" else "sv"
    title_sv = d.get(f"rubrik_{lg}") or d.get("rubrik_sv") or ev["reserv_rubrik"]
    desc_sv = d.get(f"sammanfattning_{lg}") or d.get("sammanfattning_sv") or ""
    pub = stampel(ev["godkand_tid"]) if ev.get("godkand_tid") else ""
    upd = (f'<span>{_both("Uppdaterad", "Updated")} {stampel(ev["uppdaterad_tid"])}</span>'
           if ev.get("uppdaterad_tid") else "")
    more = ""
    if related:
        more = (f'<h2 class="more-h">{_both("Fler notiser i", "More in")} {_both(sv, en)}</h2><ul class="list" style="max-width:760px">'
                + "".join(story_item(r, u.story(r["id"])) for r in related) + "</ul>")
    rattat = "".join(f'<p class="check"><b>{_both("Rättad", "Corrected")} {stampel(p["tid"])}.</b> '
                     f'{_both(_e(p.get("vad_sv") or ""), _e(p.get("vad_en") or p.get("vad_sv") or ""))}</p>' for p in rattelser.for_notis(ev["id"]))
    namn = {s[0]: (s[1], s[2]) for s in spar.SPAR}
    spor = "".join(f'<a href="{_e(u.page("spar"))}#{k}">{_both(*namn[k])}</a>' for k in spar.av(ev))
    body = (f'<p class="crumb"><a href="{_e(u.section(slug))}">{_both(sv, en)}</a>{spor}<span>{_both("Publicerad", "Published")} {pub}</span>{upd}</p>'
            f'{rattat}{story_full(ev, lang=u.lang, rubrik="h1")}'
            f'<p class="aiNote">{_ai_note(ev)} <a href="mailto:{CONTACT}">{CONTACT}</a>.</p>{more}')
    return _shell(u, title=f"{title_sv}, Newsnavigator", body=body, active=slug, path=u.story(ev["id"]), banner=banner, noindex=noindex,
                  description=desc_sv[:200], og={"type": "article", "title": title_sv, "description": desc_sv},
                  updated=ev.get("uppdaterad_tid") or ev.get("godkand_tid") or None, nsources=len(sources))


def newsletter_page(u, sources, banner, noindex, has_issue):
    if has_issue:
        return None  # publish.py lägger in senaste brevet som egen sida
    body = (f'<h1 class="pagetitle">Navigatorn</h1>'
            f'<p class="lede">{_both("Morgonbrevet från Newsnavigator. Dagens viktigaste händelser i korthet, hur världen ser på dem, och redaktörens rad. Tre minuters läsning, varje morgon.", "The morning brief from Newsnavigator. The day’s most important events in brief, how the world sees them, and the editor’s note. A three-minute read, every morning.")}</p>'
            f'<div class="prose"><p>{_both("Första numret skickas när Newsnavigator öppnar. Vill du vara med från början, skriv till", "The first issue goes out when Newsnavigator opens. To be on the list from the start, write to")} <a href="mailto:{CONTACT}">{CONTACT}</a>.</p></div>')
    return _shell(u, title="Navigatorn, Newsnavigator", body=body, active="navigatorn", path=u.page("navigatorn"), banner=banner, noindex=noindex,
                  description=_t(u, "Navigatorn, morgonbrevet från Newsnavigator.", "Navigatorn, the morning brief from Newsnavigator."), nsources=len(sources))


PRINCIPLES = [
    ("Källan först", "Sources first",
     "Varje notis bygger på namngivna källor och länkar till dem. Ett påstående som inte går att spåra till en källa publiceras inte.",
     "Every story is built on named sources and links to them. A claim that cannot be traced to a source is not published."),
    ("Neutral ton i flödet", "A neutral tone in the feed",
     "Notiserna beskriver vad som har hänt, vem som säger vad och vad som är känt. Inga värdeord, inga egna slutsatser och inga spekulationer om framtiden. Påståenden tillskrivs den som gör dem: ”enligt Riksbanken”, ”skriver Reuters”.",
     "Stories describe what happened, who says what and what is known. No loaded words, no conclusions of our own and no speculation about the future. Claims are attributed to whoever makes them: “according to the Riksbank”, “Reuters writes”."),
    ("Visa oenighet, välj inte sida", "Show disagreement, take no side",
     "När källor beskriver samma händelse olika visar vi det under ”Källorna skiljer sig åt”. Vi väljer inte vilken version som är rätt.",
     "When sources describe the same event differently, we show it under “Sources differ”. We do not choose which version is right."),
    ("Nyheter och bedömningar hålls isär", "News and judgement kept apart",
     "Notisens fakta innehåller aldrig åsikter. En bedömning, till exempel vad en händelse betyder för dig, står i en egen rad märkt Analys, efter fakta, skriven med hjälp av AI och kontrollerad mot källorna. Spalter märks Spalt och har skribentens namn.",
     "The facts of a story never contain opinion. A judgement, for example what an event means for you, sits in a line of its own marked Analysis, after the facts, written with the help of AI and checked against the sources. Columns are marked Column and carry the writer’s name."),
    ("Primärkällor före andrahandskällor", "Primary sources before secondary ones",
     "Finns det ett beslut, en rapport eller en studie länkar vi till originalet, inte bara till artiklar om det.",
     "If there is a decision, a report or a study, we link to the original, not only to articles about it."),
    ("Egna ord, korta citat", "Our own words, short quotes",
     "Sammanfattningar skrivs med egna ord och bygger på flera källor när det går. Vi återger aldrig innehåll bakom betalväggar och citerar bara korta utdrag.",
     "Summaries are written in our own words and draw on several sources where possible. We never reproduce content behind paywalls and quote only short excerpts."),
    ("Öppet om AI", "Open about AI",
     "Utkasten skrivs med hjälp av AI, och varje notis säger hur den har granskats: ”granskad av redaktionen” när redaktionen har läst den, eller ”maskinellt källkontrollerad, publicerad utan manuell granskning” när den gått automatiskt. Automatisk publicering kräver att alla påståenden är spårade till källorna, minst tre oberoende källor i minst två regioner (två svenska källor för svenska inrikesnyheter), inga känsliga ämnen och ingen blind fläck, och notisen går att ta bort med ett tryck. Ansvarig utgivare står för allt som publiceras.",
     "Drafts are written with the help of AI, and every story says how it was reviewed: “reviewed by the editors” when an editor has read it, or “machine source-checked, published without manual review” when it went out automatically. Automatic publication requires every claim to be traced to its sources, at least three independent sources in at least two regions (two Swedish sources for Swedish domestic news), no sensitive topics and no blind spot, and the story can be removed with one tap. The responsible publisher answers for everything published."),
    ("Rättelser syns", "Corrections are visible",
     "Ett fel rättas öppet, med en notis om vad som ändrades och när.",
     "An error is corrected openly, with a note on what changed and when."),
    ("Inga lockrubriker", "No clickbait",
     "Rubriken säger vad som har hänt. Den överdriver inte och undanhåller inte svaret för att få klick.",
     "The headline says what happened. It does not exaggerate and does not withhold the answer to get clicks."),
    ("Ansvarig utgivare", "Publisher",
     "Fabian Sandberg Kuylenstierna är ansvarig utgivare och har sista ordet om vad som publiceras.",
     "Fabian Sandberg Kuylenstierna is the publisher and has the final say on what is published."),
    ("USA: blått och rött, med lånade betyg", "US: blue and red, with borrowed ratings",
     "Vi visar hur amerikanska medier med olika publik berättar om samma händelse. Vilken publik ett medium vänder sig till avgör vi inte själva: vi använder AllSides betyg och anger det vid varje källa. Båda sidor beskrivs med samma mått och samma ton, och vi säger aldrig vilken sida som har rätt. Betygen kontrolleras minst en gång per kvartal. Ett enda betygsinstitut har sina begränsningar, vilket vi är öppna med.",
     "We show how American outlets with different audiences cover the same event. We do not decide ourselves which audience an outlet serves: we use AllSides’ ratings and state them beside every source. Both sides are described with the same measure and the same tone, and we never say which side is right. The ratings are checked at least once a quarter. A single ratings institute has its limitations, which we are open about."),
    ("Källkontroll", "Source check",
     "Varje utkast läses en andra gång av AI, som spårar varje påstående till källmaterialet. Ansvaret för fakta ligger hos källan; vårt jobb är att lyfta fram deras granskning och återge den rätt. Notiser där allt går att spåra märks ”Källkontrollerad”.",
     "Every draft is read a second time by AI, which traces each claim to the source material. Responsibility for the facts rests with the source; our job is to highlight their reporting and render it correctly. Stories where everything can be traced are marked “Source-checked”."),
    ("Fem spår", "Five focus areas",
     "Redaktionen följer fem områden särskilt: samarbete och fred, angrepp på människor för deras tro, mänskliga rättigheter, miljön och teknikens utveckling. Det är ett öppet val av vad vi tycker är viktigt att bevaka, och spåren väger lite extra i urvalet. De ändrar aldrig hur en notis är skriven. Ett bakslag får samma plats som ett framsteg, och alla länder och religioner mäts med samma mått.",
     "The editors follow five areas closely: cooperation and peace, attacks on people for their faith, human rights, the environment and the development of technology. This is an open choice of what we think matters, and the areas carry some extra weight in selection. They never change how a story is written. A setback gets the same place as progress, and every country and religion is measured the same way."),
]

STEPS = [
    ("Samla", "Gather", "Varje timme hämtar vi rubriker och ingresser från över 130 källor i åtta regioner. Från betalväggskällor används bara rubrik och länk.",
     "Every hour we gather headlines and standfirsts from more than 130 sources in eight regions. From paywalled sources we use only the headline and link."),
    ("Gruppera", "Group", "Artiklar om samma händelse slås ihop, över språkgränserna. Så ser vi vilka som rapporterar, och vilka som inte gör det.",
     "Articles about the same event are grouped together, across languages. That shows who is reporting, and who is not."),
    ("Skriva", "Draft", "AI skriver ett neutralt utkast på svenska och engelska, efter samma regler som redaktionen. Den får bara rubriker och ingresser, aldrig hela artiklar.",
     "AI writes a neutral draft in Swedish and English, following the same rules as the editors. It sees only headlines and standfirsts, never full articles."),
    ("Granska", "Review", "Inget publiceras förrän en människa har läst utkastet mot källorna och godkänt det.",
     "Nothing is published until a person has read the draft against the sources and approved it."),
]


HEADERS = """/*
  X-Content-Type-Options: nosniff
  X-Frame-Options: DENY
  Referrer-Policy: strict-origin-when-cross-origin
  Permissions-Policy: camera=(), microphone=(), geolocation=()
/newsgator.png
  Cache-Control: public, max-age=604800
/ig/*
  Cache-Control: public, max-age=86400
"""


def not_found_page(u, banner, nsources=0):
    """404-sida. Utan den serverar Cloudflare Pages förstasidan med status 200 för alla okända adresser."""
    body = (f'<section style="padding:20px 0 40px;max-width:640px"><h1 class="pagetitle">{_both("Sidan finns inte.", "Page not found.")}</h1>'
            f'<p class="lede">{_bb("Notiser ligger kvar i två veckor. Sedan tas sidan bort, men källorna finns kvar hos utgivarna. ", "Stories stay up for two weeks. Then the page is removed, but the sources remain with their publishers. ")}'
            f'<a href="{_e(u.home())}">{_both("Till senaste notiserna", "To the latest stories")}</a>.</p></section>')
    return _shell(u, title="Sidan finns inte, Newsnavigator", body=body, description="", path="/404.html", banner=banner, noindex=True, nsources=nsources)


def about_page(u, sources, banner, noindex):
    princ = "".join(f"<li>{_bb(f'<b>{sv}</b>{tsv}', f'<b>{en}</b>{ten}')}</li>" for sv, en, tsv, ten in PRINCIPLES)
    steps = "".join(f'<div class="step"><h3><span class="n">{i}.</span>{_both(sv, en)}</h3><p>{_both(tsv, ten)}</p></div>'
                    for i, (sv, en, tsv, ten) in enumerate(STEPS, 1))
    n_reg = len({s["region"] for s in sources} - {"global"})
    body = f"""<h1 class="pagetitle">{_both("Om Newsnavigator", "About Newsnavigator")}</h1>
<p class="lede">{_both("Vi levererar nyheterna. Vad du gör av dem är upp till dig.", "We deliver the news. What you make of it is up to you.")}</p>
<div class="prose">
<p>{_both(f"Newsnavigator samlar nyheter från {len(sources)} källor i {n_reg} regioner och visar dem på ett ställe, på svenska och engelska. Vi är lagret ovanpå nyheterna: när flera medier rapporterar om samma händelse ser du dem bredvid varandra, hur olika länder berättar om det som hänt, och vad medier med blå och röd publik i USA lyfter fram. Varje notis länkar till originalkällorna, och vi tjänar inget på att du stannar hos oss i stället för att läsa vidare hos dem.",
            f"Newsnavigator gathers news from {len(sources)} sources in {n_reg} regions and shows them in one place, in Swedish and English. We are the layer on top of the news: when several outlets report on the same event you see them side by side, how different countries tell what happened, and what outlets with blue and red audiences in the US emphasise. Every story links to its original sources, and we gain nothing from you staying with us instead of reading on at theirs.")}</p>
<p>{_both("Det som andra tar betalt för ska hos oss kännas gratis, mindre vinklat och djupare, utan att det går ut över de medier som gör jobbet. Vi väljer inte åt dig vad som är sant. Vi visar vem som säger vad.",
            "What others charge for should feel free, less slanted and deeper here, without hurting the outlets that do the work. We do not choose for you what is true. We show who says what.")}</p>
<h2>{_both("Så fungerar det", "How it works")}</h2>
</div>
<div class="steps">{steps}</div>
<div class="prose">
<h2>{_both("Så läser du en notis", "How to read a story")}</h2>
<p>{_bb("Remsan under varje rubrik visar vilka regioner som rapporterar om händelsen, från Sverige till globalt, med antalet källor. En släckt cell är en region där vi inte hittat någon rapportering. <b>Så ser världen på det</b> visar rubrikerna från olika regioner sida vid sida, med en saklig beskrivning av vad var och en lyfter fram. <b>USA: blått och rött</b> gör samma sak för amerikanska medier, sorterade efter AllSides betyg. <b>Källorna skiljer sig åt</b> visas när källorna lämnar olika uppgifter. <b>Data bakom nyheten</b> lägger till öppna siffror, till exempel räntor och inflation, direkt från Riksbanken och ECB, utan tolkning.",
         "The strip under each headline shows which regions report on the event, from Sweden to global, with the number of sources. An unlit cell is a region where we found no coverage. <b>How the world sees it</b> shows headlines from different regions side by side, with a plain description of what each emphasises. <b>US: blue and red</b> does the same for American outlets, sorted by AllSides’ ratings. <b>Sources differ</b> appears when the sources give different accounts. <b>Data behind the news</b> adds open figures such as interest rates and inflation, straight from the Riksbank and the ECB, without interpretation.")}</p>
<h2>{_both("Principerna", "The principles")}</h2>
</div>
<ol class="princ">{princ}</ol>
<div class="prose">
<h2>{_both("Kontakt", "Contact")}</h2>
<p>{_both("Tips, rättelser och frågor:", "Tips, corrections and questions:")} <a href="mailto:{CONTACT}">{CONTACT}</a>. {_both("Ansvarig utgivare är Fabian Sandberg Kuylenstierna, Stockholm.", "The publisher is Fabian Sandberg Kuylenstierna, Stockholm.")}</p>
</div>"""
    return _shell(u, title=_t(u, "Om Newsnavigator", "About Newsnavigator"), body=body, active="om", path=u.page("om"), banner=banner, noindex=noindex,
                  description=_t(u, "Vad Newsnavigator är, hur vi arbetar och våra tretton redaktionella principer.",
                                 "What Newsnavigator is, how we work and our editorial principles."), nsources=len(sources))


def _homepage(s):
    if s.get("hemsida"):
        return s["hemsida"]
    if s.get("lanka"):
        return s["lanka"]
    host = urlparse(s["url"]).netloc
    host = re.sub(r"^(www|feeds|feed|rss|api|export|moxie)\.", "", host)
    return f"https://{host}/"


def sources_page(u, sources, banner, noindex):
    groups = []
    for region in REGION_ORDER:
        items = sorted((s for s in sources if s.get("region") == region), key=lambda s: (s["typ"] != "primar", s["namn"].lower()))
        if not items:
            continue
        rows = []
        for s in items:
            flags = []
            if s.get("betalvagg"):
                flags.append(_both("Betalvägg", "Paywall"))
            if s.get("statskontrollerad"):
                flags.append(_both("Statskontrollerad", "State-controlled") + '<span class="stat">STAT</span>')
            if s.get("usa_lutning"):
                flags.append(f'AllSides: {_both(*LEANS[s["usa_lutning"]])}')
            if s.get("agare") == "public-service":
                flags.append("Public service")
            kind = TYPES.get(s["typ"], (s["typ"], s["typ"]))
            land = _both(*country(s["land"])) if s.get("land") and region not in ("sverige", "usa") else ""
            rows.append(f'<li><a href="{_e(_homepage(s))}" rel="noopener">{_e(s["namn"])}</a>'
                        f'<span class="kind">{_both(*kind)}{", " + land if land else ""}</span><span class="flags">{", ".join(flags)}</span></li>')
        groups.append(f'<h2 class="group-h">{_both(*REGIONS.get(region, (region, region)))}<span class="n">{len(items)} {_both("källor", "sources")}</span></h2><ul class="srcs">{"".join(rows)}</ul>')
    body = f"""<h1 class="pagetitle">{_both("Källor", "Sources")}</h1>
<p class="lede">{_both(f"{len(sources)} källor i åtta regioner. Alla är öppna om vilka de är, så att du kan bedöma dem själv.", f"{len(sources)} sources in eight regions. All of them are listed openly, so you can judge them yourself.")}</p>
<div class="prose">
<p>{_both("Från källor bakom betalvägg använder vi bara rubrik och länk. Statskontrollerade medier tas med för att visa hur olika stater berättar om samma händelse, och märks alltid STAT. Kuraterade listor och nyhetsbrev räknas inte som oberoende källor i rangordningen. Amerikanska medier anges med AllSides betyg på skalan vänster till höger, och betyget är deras, inte vårt.",
            "From paywalled sources we use only the headline and link. State-controlled media are included to show how different states tell the same event, and are always marked STAT. Curated lists and newsletters do not count as independent sources in the ranking. American outlets carry AllSides’ rating on the left-to-right scale, and the rating is theirs, not ours.")}</p>
<p>{_both("Saknar du en källa, eller driver du en? Skriv till", "Missing a source, or do you run one? Write to")} <a href="mailto:{CONTACT}">{CONTACT}</a>.</p>
</div>
{"".join(groups)}"""
    return _shell(u, title=_t(u, "Källor, Newsnavigator", "Sources, Newsnavigator"), body=body, active="kallor", path=u.page("kallor"), banner=banner, noindex=noindex,
                  description=_t(u, f"Alla {len(sources)} källor Newsnavigator bevakar, med region, typ och märkning.",
                                 f"All {len(sources)} sources Newsnavigator follows, with region, type and labels."), nsources=len(sources))


# ---------- RSS ----------

def _x(s):
    return html.escape(s or "", quote=True)


def _rss_marke(ev, lang):
    if ev.get("automatisk"):
        return "AI, ej manuellt granskad. " if lang == "sv" else "AI, not manually reviewed. "
    return "AI, granskad av redaktionen. " if lang == "sv" else "AI, reviewed in Swedish by the editors. "


def feed(u, events, lang):
    items = []
    for ev in sorted(events, key=lambda e: e.get("godkand_tid", 0), reverse=True)[:50]:
        d = ev.get("utkast") or {}
        title = d.get(f"rubrik_{lang}") or d.get("rubrik_sv") or ev["reserv_rubrik"]
        desc = d.get(f"sammanfattning_{lang}") or d.get("sammanfattning_sv") or ""
        srcs = ", ".join(s["namn"] for s in ev["kallor"][:5])
        link = u.absolute(u.story(ev["id"]))
        pub = datetime.fromtimestamp(ev.get("godkand_tid", 0), timezone.utc).strftime("%a, %d %b %Y %H:%M:%S +0000")
        items.append(f"<item><title>{_x(title)}</title><link>{_x(link)}</link><guid isPermaLink=\"true\">{_x(link)}</guid>"
                     f"<pubDate>{pub}</pubDate><description>{_x(_rss_marke(ev, lang) + desc + (' (' + ('Källor' if lang == 'sv' else 'Sources') + ': ' + srcs + ')' if srcs else ''))}</description></item>")
    latest = max((e.get("godkand_tid", 0) for e in events), default=0)
    build = datetime.fromtimestamp(latest, timezone.utc).strftime("%a, %d %b %Y %H:%M:%S +0000") if latest else ""
    title = "Newsnavigator" if lang == "sv" else "Newsnavigator (English)"
    desc = "Vi levererar nyheterna. Vad du gör av dem är upp till dig." if lang == "sv" else "We deliver the news. What you make of it is up to you."
    return (f'<?xml version="1.0" encoding="UTF-8"?><rss version="2.0"><channel><title>{title}</title><link>{_x(u.absolute(u.home()))}</link>'
            f'<description>{desc}</description><language>{lang}</language>{f"<lastBuildDate>{build}</lastBuildDate>" if build else ""}'
            f'{"".join(items)}</channel></rss>')


# ---------- Bygg allt ----------

def load_sources():
    return yaml.safe_load((ROOT / "feeds.yaml").read_text(encoding="utf-8"))["sources"]


def build(out, events, *, flat=False, lang=None, banner="", noindex=True, has_issue=False, over_sprak=False):
    """events: granskade notiser, nyast först, var och en med godkand_tid. Skriver alla sidor till out.
    Med `lang` skrivs ett språkträd under out/<lang>/ (se build_editions); utan är sajten tvåspråkig (förhandsvisningen)."""
    out = Path(out)
    u = Urls(flat, lang)
    sources = load_sources()
    for e in events:
        e["_over_sprak"] = over_sprak
    import time
    now = time.time()
    front_events = [e for e in events if e.get("godkand_tid", now) >= now - FRONT_DAYS * 86400]
    sect_events = [e for e in events if e.get("godkand_tid", now) >= now - SECTION_DAYS * 86400]

    _write(u.disk(out, u.home()), front(u, front_events, sources, banner, noindex))
    for slug, *_ in SECTIONS:
        _write(u.disk(out, u.section(slug)), section_page(u, slug, [e for e in sect_events if section_of(e) == slug], sources, banner, noindex))
    # Notissidor: rensa gamla och skriv alla i arkivet, så att länkar lever lika länge som arkivet
    ndir = out / u.p.strip("/") / "n"
    if not flat and ndir.exists():      # notissidorna består, så att gamla länkar håller; bara borttagna notiser försvinner
        for bort in rattelser.borttagna_id():
            shutil.rmtree(ndir / bort, ignore_errors=True)
    if flat:
        for old in out.glob("n-*.html"):
            old.unlink()
    for ev in events:
        related = [r for r in sect_events if r["id"] != ev["id"] and section_of(r) == section_of(ev)][:4]
        _write(u.disk(out, u.story(ev["id"])), story_page(u, ev, related, sources, banner, noindex))
    _write(u.disk(out, u.page("om")), about_page(u, sources, banner, noindex))
    _write(u.disk(out, u.page("spar")), spar_page(u, events, sources, banner, noindex))
    _write(u.disk(out, u.page("rattelser")), rattelser_page(u, rattelser.load(), sources, banner, noindex))
    if not flat and not lang:
        _write(out / "404.html", not_found_page(u, banner, len(sources)))
        _write(out / "_headers", HEADERS)
    _write(u.disk(out, u.page("kallor")), sources_page(u, sources, banner, noindex))
    nl = newsletter_page(u, sources, banner, noindex, has_issue)
    if nl:
        _write(u.disk(out, u.page("navigatorn")), nl)
    _write(u.disk(out, u.file("feed.xml")), feed(u, events, lang or "sv"))
    if not lang:
        _write(u.disk(out, u.file("feed-en.xml")), feed(u, events, "en"))
    for e in events:
        e.pop("_over_sprak", None)
    return {"notiser": len(events), "forstasida": len(front_events)}


# ---------- Två utgåvor ----------

def har_text(ev, lang):
    """Engelska trädet kräver engelsk rubrik och sammanfattning, så att ingen svensk text hamnar där."""
    d = ev.get("utkast") or {}
    return bool(d.get("rubrik_en") and d.get("sammanfattning_en")) if lang == "en" else True


def utgavans_notiser(events, lang):
    return utgava.ordna([e for e in events if utgava.visa(e, lang) and har_text(e, lang)], lang)


CHOOSER = (
    ("sv", "Svenska", "Världen sedd från Sverige: det som berör oss, och hur andra länders medier berättar om samma händelse."),
    ("en", "English", "The world’s news side by side: how different countries, and blue and red media in the US, tell the same event."),
)

LEGACY = [f"{k}" for k, *_ in SECTIONS] + ["n", "om", "kallor", "navigatorn", "feed.xml", "feed-en.xml"]


def chooser_page(banner="", noindex=True):
    u = Urls(False)
    cards = "".join(f'<a href="/{k}/" hreflang="{k}" lang="{k}"><h2>{_e(name)}</h2><p>{_e(text)}</p></a>' for k, name, text in CHOOSER)
    body = (f'<h1 class="pagetitle">Newsnavigator</h1><p class="lede">Välj utgåva. Choose your edition.</p><div class="pick">{cards}</div>')
    nav_free = f"""<!doctype html>
<html lang="sv"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Newsnavigator</title>
<meta name="description" content="Newsnavigator: nyheter från hela världen, på svenska och engelska. News from around the world, in Swedish and English.">
{'<meta name="robots" content="noindex">' if noindex else ''}
<link rel="canonical" href="{SITE_URL}/">
<link rel="alternate" hreflang="sv" href="{SITE_URL}/sv/"><link rel="alternate" hreflang="en" href="{SITE_URL}/en/"><link rel="alternate" hreflang="x-default" href="{SITE_URL}/">
<link rel="icon" href="/newsgator.png">
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="stylesheet" href="{FONTS_URL}">
<style>{SITE_CSS}</style></head>
<body>
{f'<div class="banner"><div class="w">{banner}</div></div>' if banner else ''}
<header><div class="w mast"><span></span><a class="brand" href="/">{_mascot()}<span>Newsnavigator</span></a><span></span></div></header>
<main class="w">{body}</main>
<footer><div class="w ft"><div><p>Ansvarig utgivare: Fabian Sandberg Kuylenstierna. Publisher: Fabian Sandberg Kuylenstierna.</p></div>
<div class="links"><a href="mailto:{CONTACT}">{CONTACT}</a></div><p class="copy">© 2026 Newsnavigator</p></div></footer>
</body></html>"""
    return nav_free


def redirects():
    """Adresserna från tiden före utgåvorna pekar nu på det svenska trädet."""
    rader = ["/n/* /sv/n/:splat 301", "/feed.xml /sv/feed.xml 301", "/feed-en.xml /en/feed.xml 301",
             "/navigatorn /sv/navigatorn/ 301", "/navigatorn/ /sv/navigatorn/ 301", "/navigatorn/en.html /en/navigatorn/ 301",
             "/om /sv/om/ 301", "/om/ /sv/om/ 301", "/kallor /sv/kallor/ 301", "/kallor/ /sv/kallor/ 301"]
    rader += [f"/{k}/ /sv/{k}/ 301" for k, *_ in SECTIONS]
    return "\n".join(rader) + "\n"


def sitemap_xml(per_utgava):
    urls = ["/"]
    for lang, events in per_utgava.items():
        urls += [f"/{lang}/", f"/{lang}/om/", f"/{lang}/spar/", f"/{lang}/rattelser/", f"/{lang}/kallor/", f"/{lang}/navigatorn/"]
        urls += [f"/{lang}/{k}/" for k, *_ in SECTIONS]
        urls += [f"/{lang}/n/{e['id']}/" for e in events]
    return ('<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
            + "".join(f"<url><loc>{SITE_URL}{u}</loc></url>" for u in urls) + "</urlset>")


def build_editions(out, events, *, banner="", noindex=True, issues=None, over_sprak=False):
    """Bygger sajten som två språkträd, /sv/ och /en/, var och en med de notiser som hör hemma i utgåvan, och en valsida i roten.
    Lanseringens kort (ig/) och förhandsgranskning (lansering/) ligger kvar orörda."""
    out = Path(out)
    issues = issues or {}
    out.mkdir(parents=True, exist_ok=True)
    for namn in LEGACY:                                   # sajten före utgåvorna
        gammal = out / namn
        if gammal.is_dir():
            shutil.rmtree(gammal)
        elif gammal.exists():
            gammal.unlink()
    stats = {"notiser": 0, "forstasida": 0, "per_utgava": {}}
    for lang in utgava.UTGAVOR:
        evs = utgavans_notiser(events, lang)
        st = build(out, evs, lang=lang, banner=banner, noindex=noindex, has_issue=issues.get(lang, False),
                   over_sprak=over_sprak if lang == "sv" else False)
        stats["per_utgava"][lang] = evs
        stats["notiser"] += st["notiser"]
        stats["forstasida"] += st["forstasida"]
    _write(out / "index.html", chooser_page(banner, noindex))
    _write(out / "404.html", not_found_page(Urls(False), banner, len(load_sources())))
    _write(out / "_headers", HEADERS)
    _write(out / "_redirects", redirects())
    return stats
