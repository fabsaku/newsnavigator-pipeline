#!/usr/bin/env python3
"""Den publika sajten (sajt.py, eftersom site är ett modulnamn i Python): en publikation med egna sidor, byggd av granskade notiser.

Sidor: förstasidan, en sida per notis (delbar länk), en sida per sektion, Navigatorn,
Om Newsnavigator med principerna, Källor, och RSS-flöden på svenska och engelska.

Två lägen:
  tree  (produktion)       /, /n/<id>/, /varlden/, /om/, /kallor/, /feed.xml
  flat  (förhandsvisning)  index.html, n-<id>.html, varlden.html, om.html ... i en mapp

Inget på sidorna beror på klockslaget då de byggdes. Därför ändras filerna bara när
innehållet ändras, och sajten byggs bara om när något nytt har godkänts.
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

from newsletter import SECTIONS, section_of
from render import CSS, JS, REGIONS, _both, _e, _event, _mascot

ROOT = Path(__file__).parent
SITE_URL = os.environ.get("NN_SITE_URL", "https://newsnavigator.se").rstrip("/")
CONTACT = "we@newsnavigator.se"
TZ = ZoneInfo("Europe/Stockholm")
FRONT_DAYS, SECTION_DAYS = 3, 7

MONTHS_SV = ["januari", "februari", "mars", "april", "maj", "juni", "juli", "augusti",
             "september", "oktober", "november", "december"]
MONTHS_EN = ["January", "February", "March", "April", "May", "June", "July", "August",
             "September", "October", "November", "December"]
TYPES = {"media": ("Medier", "Media"), "primar": ("Primärkälla", "Primary source"),
         "forskning": ("Forskning", "Research"), "kuraterat": ("Kuraterad lista", "Curated list")}
LEANS = {"vanster": ("vänster", "left"), "lutar_vanster": ("lutar vänster", "lean left"), "mitten": ("mitten", "centre"),
         "lutar_hoger": ("lutar höger", "lean right"), "hoger": ("höger", "right")}
REGION_ORDER = ["sverige", "norden", "europa", "usa", "asien", "mellanostern", "afrika", "global"]

SITE_CSS = CSS + """
nav{border-bottom:1px solid var(--line);position:relative}
nav::after{content:'';position:absolute;right:0;top:0;bottom:1px;width:36px;background:linear-gradient(to right,transparent,var(--bg));pointer-events:none}
@media (min-width:900px){nav::after{display:none}}
nav .w{display:flex;gap:4px;overflow-x:auto;scrollbar-width:none}nav .w::-webkit-scrollbar{display:none}
nav a{flex:0 0 auto;display:flex;align-items:center;min-height:44px;padding:0 10px;text-decoration:none;font:600 14px 'Source Sans 3',sans-serif;color:var(--mut);border-bottom:2px solid transparent;white-space:nowrap}
nav a:hover{color:var(--fg)}nav a[aria-current=page]{color:var(--fg);border-bottom-color:var(--fg)}
nav a:first-child{padding-left:0}
.banner{background:var(--fg);color:var(--bg);font:600 12px 'IBM Plex Mono',monospace;letter-spacing:.06em;text-transform:uppercase;padding:8px 0}
.sechead{display:flex;align-items:baseline;gap:14px;margin:36px 0 0;padding:0 0 8px;border-bottom:2px solid var(--fg);font:600 13px 'IBM Plex Mono',monospace;letter-spacing:.1em;text-transform:uppercase}
.sechead a{text-decoration:none}.sechead .mono{margin-left:auto}
.sechead+.ev{border-top:0}
.pagetitle{font-family:'Source Serif 4',Georgia,serif;font-weight:600;font-size:40px;line-height:1.1;letter-spacing:-.01em;margin:28px 0 6px}
.lede{margin:0 0 8px;font-family:'Source Serif 4',Georgia,serif;font-style:italic;font-size:19px;line-height:1.5;color:var(--body);max-width:62ch}
.crumb{display:flex;flex-wrap:wrap;gap:6px 14px;padding:18px 0 0}.crumb a{text-decoration:none}.crumb a:hover{text-decoration:underline}
.ev.single{border-top:0;padding-top:8px}.ev.single h2{max-width:none}.ev.single .sum{font-size:21px}
.aiNote{font-size:13px;color:var(--mut);border-top:1px solid var(--line);padding-top:12px;max-width:68ch;line-height:1.5}
.more{list-style:none;margin:0;padding:0;display:flex;flex-direction:column;gap:10px}
.more li{border-top:1px solid var(--line);padding-top:10px}.more a{text-decoration:none;font-family:'Source Serif 4',Georgia,serif;font-weight:600;font-size:19px;line-height:1.25}
.more a:hover{text-decoration:underline;text-underline-offset:4px}.more .mono{display:block;margin-top:4px}
.prose{max-width:68ch}.prose p{font-size:17px;line-height:1.6;color:var(--body)}.prose h2{font-family:'Source Serif 4',Georgia,serif;font-weight:600;font-size:26px;margin:36px 0 8px}
.prose ol{padding-left:0;list-style:none;counter-reset:p;margin:0}
.prose ol li{counter-increment:p;border-top:1px solid var(--line);padding:16px 0 16px 56px;position:relative;font-size:16px;line-height:1.55;color:var(--body)}
.prose ol li::before{content:counter(p,decimal-leading-zero);position:absolute;left:0;top:18px;font:600 13px 'IBM Plex Mono',monospace;color:var(--mut)}
.prose ol li b{display:block;color:var(--fg);font-size:18px;margin-bottom:4px;font-family:'Source Serif 4',Georgia,serif}
.prose a{color:var(--fg)}
.steps{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:14px;margin:12px 0 0}
.step{border:1px solid var(--line);padding:16px}.step .mono{display:block;margin-bottom:8px}.step p{margin:0;font-size:15px;line-height:1.5;color:var(--body)}
.srcs{list-style:none;margin:0;padding:0}
.srcs li{display:grid;grid-template-columns:minmax(0,1.6fr) minmax(0,1fr) minmax(0,1.4fr);gap:8px 16px;border-top:1px solid var(--line);padding:11px 0;font-size:15px;align-items:baseline}
.srcs li a{text-decoration:none;font-weight:600}.srcs li a:hover{text-decoration:underline}
.srcs li .mono{text-transform:none;letter-spacing:0;font-size:13px}
.srcs .flags{display:flex;flex-wrap:wrap;gap:6px;justify-content:flex-end}
.legend{display:flex;flex-wrap:wrap;gap:8px 18px;font-size:13px;color:var(--mut);margin:10px 0 0}
footer nav{border:0}footer .links{display:flex;flex-wrap:wrap;gap:4px 18px;font-size:14px}footer .links a{color:var(--mut);text-decoration:none}footer .links a:hover{color:var(--fg)}
@media (max-width:600px){.pagetitle{font-size:30px}.srcs li{grid-template-columns:minmax(0,1fr) minmax(0,1fr)}.srcs li .flags{grid-column:1/-1;justify-content:flex-start}}
"""


# ---------- Adresser ----------

class Urls:
    def __init__(self, flat):
        self.flat = flat

    def home(self):
        return "./" if self.flat else "/"

    def story(self, sid):
        return f"n-{sid}.html" if self.flat else f"/n/{sid}/"

    def section(self, slug):
        return f"{slug}.html" if self.flat else f"/{slug}/"

    def page(self, name):
        return f"{name}.html" if self.flat else f"/{name}/"

    def file(self, name):
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


def _date(ts, clock=False):
    d = datetime.fromtimestamp(ts, timezone.utc).astimezone(TZ)
    t = f" {d:%H:%M}" if clock else ""
    return f"{d.day} {MONTHS_SV[d.month - 1]} {d.year}{t}", f"{d.day} {MONTHS_EN[d.month - 1]} {d.year}{t}"


def _section_names(slug):
    return next(((sv, en) for k, sv, en, _ in SECTIONS if k == slug), ("Världen", "World"))


def _write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


# ---------- Sidmall ----------

def _shell(u, *, title, body, active=None, description="", path="/", meta="", og=None, banner="", noindex=True, extra=""):
    nav = [(u.home(), "Senaste", "Latest", "hem")]
    nav += [(u.section(k), sv, en, k) for k, sv, en, _ in SECTIONS]
    nav += [(u.page("navigatorn"), "Navigatorn", "Navigatorn", "navigatorn"), (u.page("om"), "Om", "About", "om"),
            (u.page("kallor"), "Källor", "Sources", "kallor")]
    links = "".join(f'<a href="{_e(h)}"{" aria-current=page" if k == active else ""}>{_both(sv, en)}</a>' for h, sv, en, k in nav)
    canonical = u.absolute(path)
    ogtags = ""
    if og:
        ogtags = (f'<meta property="og:type" content="{og.get("type", "website")}"><meta property="og:title" content="{_e(og["title"])}">'
                  f'<meta property="og:description" content="{_e(og.get("description", ""))}"><meta property="og:url" content="{_e(canonical)}">'
                  f'<meta property="og:image" content="{_e(u.absolute(u.file("newsgator.png")))}"><meta property="og:site_name" content="Newsnavigator">'
                  f'<meta name="twitter:card" content="summary">')
    return f"""<!doctype html>
<html lang="sv"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{_e(title)}</title>
<meta name="description" content="{_e(description)}">
{'<meta name="robots" content="noindex">' if noindex else ''}
<link rel="canonical" href="{_e(canonical)}">
<link rel="icon" href="{_e(u.file("newsgator.png"))}">
<link rel="alternate" type="application/rss+xml" title="Newsnavigator" href="{_e(u.file("feed.xml"))}">
<link rel="alternate" type="application/rss+xml" title="Newsnavigator (English)" href="{_e(u.file("feed-en.xml"))}">
{ogtags}
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Source+Serif+4:ital,opsz,wght@0,8..60,400..700;1,8..60,400..700&family=Source+Sans+3:wght@400;500;600;700;800&family=IBM+Plex+Mono:wght@400;600&display=swap">
<style>{SITE_CSS}</style>{extra}</head>
<body>
{f'<div class="banner"><div class="w">{banner}</div></div>' if banner else ''}
<header><div class="w hd">
<a class="brand" href="{_e(u.home())}">{_mascot()}<span>Newsnavigator</span></a>
<div class="mono">{meta}</div>
<div class="lang" role="group" aria-label="Språk"><button type="button" data-l="sv" aria-pressed="true">SV</button><button type="button" data-l="en" aria-pressed="false">EN</button></div>
</div></header>
<nav aria-label="Sektioner"><div class="w">{links}</div></nav>
<div class="w">
<main>{body}</main>
<footer>
<p>{_both("Notiserna sammanfattas med hjälp av AI och granskas av redaktionen innan publicering. Varje notis länkar till originalkällorna. Statskontrollerade medier är märkta STAT. Ansvarig utgivare: Fabian Sandberg Kuylenstierna.", "Stories are summarised with the help of AI and reviewed by the editors before publication. Every story links to its original sources. State-controlled media are marked STAT. Publisher: Fabian Sandberg Kuylenstierna.")}</p>
<div class="links"><a href="{_e(u.page("om"))}">{_both("Om och principer", "About and principles")}</a><a href="{_e(u.page("kallor"))}">{_both("Källor", "Sources")}</a><a href="{_e(u.page("navigatorn"))}">Navigatorn</a><a href="{_e(u.file("feed.xml"))}">RSS</a><a href="mailto:{CONTACT}">{CONTACT}</a><span class="mono">© 2026 Newsnavigator</span></div>
</footer>
</div>
<script>{JS}</script>
</body></html>"""


# ---------- Sidor ----------

def _headmeta(sources, events):
    n_reg = len({s["region"] for s in sources} - {"global"})
    parts = [f'{len(sources)} {_both("källor", "sources")}', f'{n_reg} {_both("regioner", "regions")}']
    if events:
        latest = max(e.get("godkand_tid", 0) for e in events)
        parts.append(f'{_both("Uppdaterad", "Updated")} {_both(*_date(latest, clock=True))}')
    return " · ".join(parts)


def _waiting(u):
    return (f'<section style="padding:48px 0 48px;max-width:640px"><h1 class="pagetitle">{_both("Newsnavigator öppnar snart.", "Newsnavigator opens soon.")}</h1>'
            f'<p class="lede">{_both("Nyheter från över 90 källor i sju regioner, samlade på ett ställe och granskade innan de publiceras. Du ser hur olika länder, och blå och röda medier i USA, berättar om samma händelse. Varje notis länkar till originalet.", "News from more than 90 sources in seven regions, gathered in one place and reviewed before publication. See how different countries, and blue and red media in the US, cover the same event. Every story links to the original.")}</p>'
            f'<p class="lede">{_both("Varje morgon kommer Navigatorn, vårt morgonbrev.", "Every morning: Navigatorn, our morning brief.")} '
            f'<a href="{_e(u.page("om"))}">{_both("Läs om hur vi arbetar", "Read about how we work")}</a>.</p></section>')


def front(u, events, sources, banner, noindex):
    if not events:
        body = _waiting(u)
    else:
        lead, rest = events[0], events[1:]
        body = _event(lead, True, href=u.story(lead["id"]))
        for slug, sv, en, _ in SECTIONS:
            items = [e for e in rest if section_of(e) == slug]
            if not items:
                continue
            body += (f'<h3 class="sechead"><a href="{_e(u.section(slug))}">{_both(sv, en)}</a><span class="mono">{len(items)}</span></h3>'
                     + "".join(_event(e, False, href=u.story(e["id"])) for e in items))
    return _shell(u, title="Newsnavigator", body=body, active="hem", path="/", banner=banner, noindex=noindex,
                  description="Nyheter från hela världen, samlade och granskade. Se hur olika länder och medier berättar om samma händelse.",
                  meta=_headmeta(sources, events), og={"title": "Newsnavigator", "description": "Vi levererar nyheterna. Vad du gör av dem är upp till dig."})


def section_page(u, slug, events, sources, banner, noindex):
    sv, en = _section_names(slug)
    body = f'<h1 class="pagetitle">{_both(sv, en)}</h1>'
    if events:
        body += "".join(_event(e, i == 0, href=u.story(e["id"])) for i, e in enumerate(events))
    else:
        body += f'<p class="lede">{_both("Inga granskade notiser i den här sektionen de senaste dagarna.", "No reviewed stories in this section in the past few days.")}</p>'
    return _shell(u, title=f"{sv} · Newsnavigator", body=body, active=slug, path=u.section(slug), banner=banner, noindex=noindex,
                  description=f"Granskade nyheter: {sv}.", meta=_headmeta(sources, events))


def story_page(u, ev, related, sources, banner, noindex):
    d = ev.get("utkast") or {}
    slug = section_of(ev)
    sv, en = _section_names(slug)
    title_sv = d.get("rubrik_sv") or ev["reserv_rubrik"]
    desc_sv = d.get("sammanfattning_sv") or ""
    art = _event(ev, True).replace('class="ev lead"', 'class="ev lead single"').replace("<details>", "<details open>")
    pub = _both(*_date(ev.get("godkand_tid", 0), clock=True)) if ev.get("godkand_tid") else ""
    more = ""
    if related:
        more = (f'<h3 class="sechead">{_both("Fler notiser", "More stories")}</h3><ul class="more">'
                + "".join(f'<li><a href="{_e(u.story(r["id"]))}">{_both((r.get("utkast") or {}).get("rubrik_sv") or r["reserv_rubrik"], (r.get("utkast") or {}).get("rubrik_en") or r["reserv_rubrik"])}</a>'
                          f'<span class="mono">{r["antal_kallor"]} {_both("källor", "sources")}</span></li>' for r in related) + "</ul>")
    body = (f'<p class="crumb mono"><a href="{_e(u.section(slug))}">{_both(sv, en)}</a><span>{_both("Publicerad", "Published")} {pub}</span></p>'
            f'{art}<p class="aiNote">{_both("Sammanfattad med hjälp av AI och granskad av redaktionen. Vi återger inte text från källorna, bara rubrik och länk. Fel? Skriv till", "Summarised with the help of AI and reviewed by the editors. We do not reproduce the sources’ text, only the headline and link. Spotted an error? Write to")} <a href="mailto:{CONTACT}">{CONTACT}</a>.</p>{more}')
    return _shell(u, title=f"{title_sv} · Newsnavigator", body=body, active=slug, path=u.story(ev["id"]), banner=banner, noindex=noindex,
                  description=desc_sv[:200], meta=_headmeta(sources, [ev]),
                  og={"type": "article", "title": title_sv, "description": desc_sv})


def newsletter_page(u, sources, banner, noindex, has_issue):
    if has_issue:
        return None  # publish.py lägger in senaste brevet som egen sida
    body = (f'<h1 class="pagetitle">Navigatorn</h1>'
            f'<p class="lede">{_both("Morgonbrevet från Newsnavigator. Dagens viktigaste händelser i korthet, hur världen ser på dem, och redaktörens rad. Tre minuters läsning, varje morgon.", "The morning brief from Newsnavigator. The day’s most important events in brief, how the world sees them, and the editor’s note. A three-minute read, every morning.")}</p>'
            f'<div class="prose"><p>{_both("Första numret skickas när Newsnavigator öppnar. Vill du vara med från början, skriv till", "The first issue goes out when Newsnavigator opens. To be on the list from the start, write to")} <a href="mailto:{CONTACT}">{CONTACT}</a>.</p></div>')
    return _shell(u, title="Navigatorn · Newsnavigator", body=body, active="navigatorn", path=u.page("navigatorn"), banner=banner, noindex=noindex,
                  description="Navigatorn, morgonbrevet från Newsnavigator.", meta=_headmeta(sources, []))


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
    ("Nyheter och åsikter hålls isär", "News and opinion kept apart",
     "Allt som innehåller en bedömning märks som Analys eller Spalt, med skribentens namn. Flödet är alltid fritt från åsikter.",
     "Anything that contains a judgement is marked Analysis or Column, with the writer’s name. The feed is always free of opinion."),
    ("Primärkällor före andrahandskällor", "Primary sources before secondary ones",
     "Finns det ett beslut, en rapport eller en studie länkar vi till originalet, inte bara till artiklar om det.",
     "If there is a decision, a report or a study, we link to the original, not only to articles about it."),
    ("Egna ord, korta citat", "Our own words, short quotes",
     "Sammanfattningar skrivs med egna ord och bygger på flera källor när det går. Vi återger aldrig innehåll bakom betalväggar och citerar bara korta utdrag.",
     "Summaries are written in our own words and draw on several sources where possible. We never reproduce content behind paywalls and quote only short excerpts."),
    ("Öppet om AI", "Open about AI",
     "Utkasten skrivs med hjälp av AI. Inget publiceras innan en människa har granskat det på riktigt, och varje notis märks: ”Sammanfattad med hjälp av AI och granskad av redaktionen.”",
     "Drafts are written with the help of AI. Nothing is published before a person has genuinely reviewed it, and every story is marked: “Summarised with the help of AI and reviewed by the editors.”"),
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
]

STEPS = [
    ("01", "Samla", "Gather", "Varje timme hämtar vi rubriker och ingresser från över 90 källor i sju regioner. Från betalväggskällor används bara rubrik och länk.",
     "Every hour we gather headlines and standfirsts from more than 90 sources in seven regions. From paywalled sources we use only the headline and link."),
    ("02", "Gruppera", "Group", "Artiklar om samma händelse slås ihop, över språkgränserna. Så ser vi vilka som rapporterar, och vilka som inte gör det.",
     "Articles about the same event are grouped together, across languages. That shows who is reporting, and who is not."),
    ("03", "Skriva", "Draft", "AI skriver ett neutralt utkast på svenska och engelska, efter samma regler som redaktionen. Den får bara rubriker och ingresser, aldrig hela artiklar.",
     "AI writes a neutral draft in Swedish and English, following the same rules as the editors. It sees only headlines and standfirsts, never full articles."),
    ("04", "Granska", "Review", "Inget publiceras förrän en människa har läst utkastet mot källorna och godkänt det.",
     "Nothing is published until a person has read the draft against the sources and approved it."),
]


def about_page(u, sources, banner, noindex):
    princ = "".join(f"<li>{_bb(f'<b>{sv}</b>{tsv}', f'<b>{en}</b>{ten}')}</li>" for sv, en, tsv, ten in PRINCIPLES)
    steps = "".join(f'<div class="step"><span class="mono">{n} · {_both(sv, en)}</span><p>{_both(tsv, ten)}</p></div>' for n, sv, en, tsv, ten in STEPS)
    n_reg = len({s["region"] for s in sources} - {"global"})
    body = f"""<h1 class="pagetitle">{_both("Om Newsnavigator", "About Newsnavigator")}</h1>
<p class="lede">{_both("Vi levererar nyheterna. Vad du gör av dem är upp till dig.", "We deliver the news. What you make of it is up to you.")}</p>
<div class="prose">
<p>{_both(f"Newsnavigator samlar nyheter från {len(sources)} källor i {n_reg} regioner och visar dem på ett ställe, på svenska och engelska. Vi är lagret ovanpå nyheterna: när flera medier rapporterar om samma händelse ser du dem bredvid varandra, hur olika länder berättar om det som hänt, och vad medier med blå och röd publik i USA lyfter fram. Varje notis länkar till originalkällorna, och vi tjänar inget på att du stannar hos oss i stället för att läsa vidare hos dem.",
            f"Newsnavigator gathers news from {len(sources)} sources in {n_reg} regions and shows them in one place, in Swedish and English. We are the layer on top of the news: when several outlets report on the same event you see them side by side, how different countries tell what happened, and what outlets with blue and red audiences in the US emphasise. Every story links to its original sources, and we gain nothing from you staying with us instead of reading on at theirs.")}</p>
<p>{_both("Det som andra tar betalt för ska hos oss kännas gratis, mindre vinklat och djupare, utan att det går ut över de medier som gör jobbet. Vi väljer inte åt dig vad som är sant. Vi visar vem som säger vad.",
            "What others charge for should feel free, less slanted and deeper here, without hurting the outlets that do the work. We do not choose for you what is true. We show who says what.")}</p>
<h2>{_both("Så fungerar det", "How it works")}</h2>
<div class="steps">{steps}</div>
<h2>{_both("Så läser du en notis", "How to read a story")}</h2>
<p>{_bb("<b>Så ser världen på det</b> visar rubrikerna från olika regioner sida vid sida, med en saklig beskrivning av vad var och en lyfter fram. <b>USA: blått och rött</b> gör samma sak för amerikanska medier, sorterade efter AllSides betyg. <b>Källorna skiljer sig åt</b> visas när källorna lämnar olika uppgifter. <b>Data bakom nyheten</b> lägger till öppna siffror, till exempel räntor och inflation, direkt från Riksbanken och ECB, utan tolkning.",
         "<b>How the world sees it</b> shows headlines from different regions side by side, with a plain description of what each emphasises. <b>US: blue and red</b> does the same for American outlets, sorted by AllSides’ ratings. <b>Sources differ</b> appears when the sources give different accounts. <b>Data behind the news</b> adds open figures such as interest rates and inflation, straight from the Riksbank and the ECB, without interpretation.")}</p>
<h2>{_both("Principerna", "The principles")}</h2>
<ol>{princ}</ol>
<h2>{_both("Kontakt", "Contact")}</h2>
<p>{_both("Tips, rättelser och frågor:", "Tips, corrections and questions:")} <a href="mailto:{CONTACT}">{CONTACT}</a>. {_both("Ansvarig utgivare är Fabian Sandberg Kuylenstierna, Stockholm.", "The publisher is Fabian Sandberg Kuylenstierna, Stockholm.")}</p>
</div>"""
    return _shell(u, title="Om Newsnavigator", body=body, active="om", path=u.page("om"), banner=banner, noindex=noindex,
                  description="Vad Newsnavigator är, hur vi arbetar och våra elva redaktionella principer.", meta=_headmeta(sources, []))


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
                flags.append(f'<span class="badge">{_both("betalvägg", "paywall")}</span>')
            if s.get("statskontrollerad"):
                flags.append('<span class="badge strong">STAT</span>')
            if s.get("usa_lutning"):
                flags.append(f'<span class="badge">AllSides: {_both(*LEANS[s["usa_lutning"]])}</span>')
            if s.get("agare") == "public-service":
                flags.append(f'<span class="badge">public service</span>')
            kind = TYPES.get(s["typ"], (s["typ"], s["typ"]))
            rows.append(f'<li><a href="{_e(_homepage(s))}" rel="noopener">{_e(s["namn"])}</a>'
                        f'<span class="mono">{_e(s.get("land", ""))} · {_both(*kind)}</span><span class="flags">{"".join(flags)}</span></li>')
        groups.append(f'<h3 class="sechead">{_both(*REGIONS.get(region, (region, region)))}<span class="mono">{len(items)}</span></h3><ul class="srcs">{"".join(rows)}</ul>')
    body = f"""<h1 class="pagetitle">{_both("Källor", "Sources")}</h1>
<p class="lede">{_both(f"{len(sources)} källor i sju regioner. Alla är öppna om vilka de är, så att du kan bedöma dem själv.", f"{len(sources)} sources in seven regions. All of them are listed openly, so you can judge them yourself.")}</p>
<div class="prose">
<p>{_both("Från källor bakom betalvägg använder vi bara rubrik och länk. Statskontrollerade medier tas med för att visa hur olika stater berättar om samma händelse, och märks alltid STAT. Kuraterade listor och nyhetsbrev räknas inte som oberoende källor i rangordningen. Amerikanska medier anges med AllSides betyg på skalan vänster till höger, och betyget är deras, inte vårt.",
            "From paywalled sources we use only the headline and link. State-controlled media are included to show how different states tell the same event, and are always marked STAT. Curated lists and newsletters do not count as independent sources in the ranking. American outlets carry AllSides’ rating on the left-to-right scale, and the rating is theirs, not ours.")}</p>
<p>{_both("Saknar du en källa, eller driver du en? Skriv till", "Missing a source, or do you run one? Write to")} <a href="mailto:{CONTACT}">{CONTACT}</a>.</p>
</div>
{"".join(groups)}"""
    return _shell(u, title="Källor · Newsnavigator", body=body, active="kallor", path=u.page("kallor"), banner=banner, noindex=noindex,
                  description=f"Alla {len(sources)} källor Newsnavigator bevakar, med region, typ och märkning.", meta=_headmeta(sources, []))


# ---------- RSS ----------

def _x(s):
    return html.escape(s or "", quote=True)


def feed(u, events, lang):
    items = []
    for ev in events[:50]:
        d = ev.get("utkast") or {}
        title = d.get(f"rubrik_{lang}") or d.get("rubrik_sv") or ev["reserv_rubrik"]
        desc = d.get(f"sammanfattning_{lang}") or d.get("sammanfattning_sv") or ""
        srcs = ", ".join(s["namn"] for s in ev["kallor"][:5])
        link = u.absolute(u.story(ev["id"]))
        pub = datetime.fromtimestamp(ev.get("godkand_tid", 0), timezone.utc).strftime("%a, %d %b %Y %H:%M:%S +0000")
        items.append(f"<item><title>{_x(title)}</title><link>{_x(link)}</link><guid isPermaLink=\"true\">{_x(link)}</guid>"
                     f"<pubDate>{pub}</pubDate><description>{_x(desc + (' (' + ('Källor' if lang == 'sv' else 'Sources') + ': ' + srcs + ')' if srcs else ''))}</description></item>")
    latest = max((e.get("godkand_tid", 0) for e in events), default=0)
    build = datetime.fromtimestamp(latest, timezone.utc).strftime("%a, %d %b %Y %H:%M:%S +0000") if latest else ""
    title = "Newsnavigator" if lang == "sv" else "Newsnavigator (English)"
    desc = "Vi levererar nyheterna. Vad du gör av dem är upp till dig." if lang == "sv" else "We deliver the news. What you make of it is up to you."
    return (f'<?xml version="1.0" encoding="UTF-8"?><rss version="2.0"><channel><title>{title}</title><link>{_x(SITE_URL)}/</link>'
            f'<description>{desc}</description><language>{lang}</language>{f"<lastBuildDate>{build}</lastBuildDate>" if build else ""}'
            f'{"".join(items)}</channel></rss>')


# ---------- Bygg allt ----------

def load_sources():
    return yaml.safe_load((ROOT / "feeds.yaml").read_text(encoding="utf-8"))["sources"]


def build(out, events, *, flat=False, banner="", noindex=True, has_issue=False, over_sprak=False):
    """events: granskade notiser, nyast först, var och en med godkand_tid. Skriver alla sidor till out."""
    out = Path(out)
    u = Urls(flat)
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
    ndir = out / "n"
    if not flat and ndir.exists():
        shutil.rmtree(ndir)
    if flat:
        for old in out.glob("n-*.html"):
            old.unlink()
    for ev in events:
        related = [r for r in sect_events if r["id"] != ev["id"] and section_of(r) == section_of(ev)][:3]
        _write(u.disk(out, u.story(ev["id"])), story_page(u, ev, related, sources, banner, noindex))
    _write(u.disk(out, u.page("om")), about_page(u, sources, banner, noindex))
    _write(u.disk(out, u.page("kallor")), sources_page(u, sources, banner, noindex))
    nl = newsletter_page(u, sources, banner, noindex, has_issue)
    if nl:
        _write(u.disk(out, u.page("navigatorn")), nl)
    _write(u.disk(out, u.file("feed.xml")), feed(u, events, "sv"))
    _write(u.disk(out, u.file("feed-en.xml")), feed(u, events, "en"))
    for e in events:
        e.pop("_over_sprak", None)
    return {"notiser": len(events), "forstasida": len(front_events)}
