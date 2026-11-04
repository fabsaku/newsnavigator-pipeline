#!/usr/bin/env python3
"""Läsaren för källor utan flöde: en sidas rubriklista blir ett flöde.

Bara rubrik och länk läses, aldrig sidans text. robots.txt kontrolleras först och en utgivare som inte tillåter NewsnavigatorBot
(eller vars robots.txt inte går att läsa) hämtas inte. En sida har inga publiceringsdatum, så en länk får tiden då vi först såg den.
Första gången en källa läses räknas allt som redan står på sidan som gammalt, så att en hel nyhetslista inte dyker upp som färska nyheter.

I feeds.yaml:
  - {id: nato, namn: NATO, url: "https://www.nato.int/cps/en/natohq/news.htm", hamtning: sida, lankar: "^/cps/en/natohq/news_\\d+\\.htm", ...}
    lankar     reguljärt uttryck som en länks sökväg ska matcha för att räknas som en nyhet (krävs)
    bas        adress som relativa länkar utgår från (standard: url)
    rendera    true för sidor som ritar sin lista med JavaScript: hämtas med webbläsare (Playwright), efter robots.txt-kontrollen
    min_tecken kortaste rubrik (standard 20), max_antal flest länkar (standard 40)

Provas i Actions med `python kallprov.py --sida ADRESS MÖNSTER`, som visar vilka rubriker och länkar läsaren skulle hitta.
"""
import json
import re
import time
import urllib.request
from html.parser import HTMLParser
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import urldefrag, urljoin, urlsplit

ROOT = Path(__file__).parent
STATE = ROOT / "data" / "sidor.json"
MIN_TECKEN = 20
MIN_RUBRIKELEMENT = 6      # en rubrik i ett rubrikelement får vara kortare än en hel länktext ("Voxtral 3")
MAX_ANTAL = 40
BEHALL_DAGAR = 30
AGENT = "Mozilla/5.0 (compatible; NewsnavigatorBot/0.3; +https://newsnavigator.se/bot)"

_state = None
_robots_cache = {}


RUBRIK_TAGGAR = ("h1", "h2", "h3", "h4", "h5", "h6")


class _Lankar(HTMLParser):
    """Samlar länkar med texten i dem. Ligger ett rubrikelement (h1 till h6) i länken är det rubriken, annars hela länktexten."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.lankar, self._href, self._text, self._rubrik, self._i_rubrik, self._ignorera = [], None, [], [], 0, 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "noscript", "template"):
            self._ignorera += 1
        elif tag == "a" and not self._ignorera:
            self._href, self._text, self._rubrik, self._i_rubrik = dict(attrs).get("href"), [], [], 0
        elif tag in RUBRIK_TAGGAR and self._href is not None:
            self._i_rubrik += 1

    def handle_endtag(self, tag):
        if tag in ("script", "style", "noscript", "template"):
            self._ignorera = max(0, self._ignorera - 1)
        elif tag in RUBRIK_TAGGAR and self._href is not None:
            self._i_rubrik = max(0, self._i_rubrik - 1)
            self._text.append(" ")
        elif tag == "a" and self._href is not None:
            hel = " ".join("".join(self._text).split())
            rubrik = " ".join("".join(self._rubrik).split())
            self.lankar.append((self._href, hel, rubrik))
            self._href = None
        elif self._href is not None:
            self._text.append(" ")

    def handle_data(self, data):
        if self._href is not None and not self._ignorera:
            self._text.append(data)
            if self._i_rubrik:
                self._rubrik.append(data)


_DATUM_FORST = re.compile(
    r"^(?:(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.? \d{1,2},? \d{4}|\d{1,2} (?:jan|feb|mar|apr|maj|may|jun|jul|aug|sep|okt|oct|nov|dec)\w* \d{4}|\d{4}-\d{2}-\d{2})\s*",
    re.I)


def _rubrik(text):
    """Ett datum först i länktexten ("October 7, 2026Coming Soon: ...") hör inte till rubriken."""
    ren = _DATUM_FORST.sub("", text).strip()
    return ren or text


def lankar(html, bas, monster, min_tecken=MIN_TECKEN, max_antal=MAX_ANTAL):
    """[(rubrik, länk)] för länkar på samma webbplats vars sökväg matchar `monster`, i sidans ordning, en per länk."""
    if not monster:
        return []
    p = _Lankar()
    p.feed(html)
    host = urlsplit(bas).netloc.removeprefix("www.")
    funna = {}
    for href, hel, rubrik in p.lankar:
        if not href or len(hel) < min_tecken:
            continue
        url = urldefrag(urljoin(bas, href))[0]
        delar = urlsplit(url)
        if delar.scheme not in ("http", "https") or delar.netloc.removeprefix("www.") != host:
            continue
        if not (re.search(monster, delar.path) or re.search(monster, delar.path.rstrip("/"))):
            continue
        text = _rubrik(rubrik if len(rubrik) >= MIN_RUBRIKELEMENT else hel)
        if url not in funna or len(text) > len(funna[url]):
            funna[url] = text
    return [(t, u) for u, t in funna.items()][:max_antal]


# ---------- Hämtning ----------

def _robots(url):
    import kallprov
    return kallprov.hamta_robots(url)


def _sida(url):
    req = urllib.request.Request(url, headers={"User-Agent": AGENT, "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.5"})
    with urllib.request.urlopen(req, timeout=25) as r:
        return r.read().decode("utf-8", errors="replace")


def _rendera(url):
    """Sidor som ritar sin lista med JavaScript: hämtas med en riktig webbläsare (Chrome finns på GitHubs körmiljö, som för Instagramkorten)."""
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        try:
            b = p.chromium.launch(channel="chrome")
        except Exception:
            b = p.chromium.launch()
        try:
            sida = b.new_page(user_agent=AGENT)
            sida.goto(url, wait_until="networkidle", timeout=45000)
            return sida.content()
        finally:
            b.close()


def nollstall_robots():
    _robots_cache.clear()


def _tillaten(url):
    """(tillåten, orsak). robots.txt hämtas en gång per utgivare och körning."""
    import kallprov
    host = urlsplit(url).netloc
    if host not in _robots_cache:
        _robots_cache[host] = _robots(url)
    text, fel = _robots_cache[host]
    if text is None:
        return False, f"robots.txt kunde inte läsas ({fel}), sidan hämtas inte"
    besked = kallprov.robots_besked(text, url)
    return (True, None) if besked["tillaten"] else (False, f"robots.txt tillåter inte NewsnavigatorBot ({besked['regel']})")


# ---------- Tillstånd: när varje länk först sågs ----------

def _las_state():
    global _state
    if _state is None:
        try:
            _state = json.loads(STATE.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            _state = {}
        for kalla, v in list(_state.items()):
            if "lankar" not in v:                       # äldre format: bara länkarna
                _state[kalla] = {"start": time.time(), "lankar": v}
    return _state


_sedda = {}


def oversikt(html, bas, min_tecken=MIN_TECKEN):
    """Hur många rubrikliknande länkar sidan har per sökvägsstart (de två första delarna): underlag för att välja `lankar`."""
    p = _Lankar()
    p.feed(html)
    host = urlsplit(bas).netloc.removeprefix("www.")
    antal, sedda = {}, set()
    for href, text, _ in p.lankar:
        if not href or len(text) < min_tecken:
            continue
        url = urldefrag(urljoin(bas, href))[0]
        delar = urlsplit(url)
        if url not in sedda and delar.scheme in ("http", "https") and delar.netloc.removeprefix("www.") == host:
            sedda.add(url)
            start = "/" + "/".join([d for d in delar.path.split("/") if d][:2])
            antal[start] = antal.get(start, 0) + 1
    return dict(sorted(antal.items(), key=lambda kv: -kv[1]))


def spara(nu=None, aktiva=None):
    """Sparar tillståndet. `aktiva`: id för de sidkällor som finns i feeds.yaml; tillstånd för borttagna eller uteslutna källor rensas."""
    nu = time.time() if nu is None else nu
    state = _las_state()
    if aktiva is not None:
        for gammal in [k for k in state if k not in aktiva]:
            del state[gammal]
        for k in [k for k in _sedda if k not in aktiva]:
            del _sedda[k]
    if not state:
        return
    for kalla, urls in _sedda.items():
        state[kalla]["lankar"] = {u: t for u, t in state[kalla]["lankar"].items()
                                  if u in urls or (t > 0 and t >= nu - BEHALL_DAGAR * 86400)}
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(state, ensure_ascii=False, indent=1, sort_keys=True) + "\n", encoding="utf-8")


def som_flode(s, nu=None):
    """Som pipeline.fetch_one: (flöde med .entries, använd adress, fel). Varje post har title, link och published_parsed."""
    nu = time.time() if nu is None else nu
    url = s["url"]
    try:
        if url.startswith("file:"):
            html = (ROOT / url[5:]).read_text(encoding="utf-8")
        else:
            ok, orsak = _tillaten(url)
            if not ok:
                return None, None, orsak
            html = (_rendera if s.get("rendera") else _sida)(url)
    except Exception as e:
        return None, None, str(e)[:160]
    rubriker = lankar(html, s.get("bas") or url, s.get("lankar"), s.get("min_tecken", MIN_TECKEN), s.get("max_antal", MAX_ANTAL))
    if not rubriker:
        return None, None, "inga rubriker hittades på sidan (kontrollera mönstret under lankar)"
    state = _las_state()
    forsta_gangen = s["id"] not in state
    post = state.setdefault(s["id"], {"start": nu, "lankar": {}})
    kalla = post["lankar"]
    _sedda[s["id"]] = {u for _, u in rubriker}
    poster = []
    for titel, lank in rubriker:
        kalla.setdefault(lank, 0.0 if forsta_gangen else nu)       # det som redan stod där första gången räknas som gammalt
        # senast_sedd: när länken dök upp, eller när vi började läsa källan om den stod där från början (för källstatus, inte för åldern)
        poster.append({"title": titel, "link": lank, "published_parsed": time.gmtime(kalla[lank]), "senast_sedd": kalla[lank] or post["start"]})
    return SimpleNamespace(entries=poster), url, None
