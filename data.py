"""Data bakom nyheten: öppna dataserier som kopplas till notiser.

Visar siffror, utveckling och källa. Aldrig tolkning eller råd: läsaren drar slutsatserna.
Serierna hämtas högst en gång per dygn och sparas i data/serier.json.
"""
import csv
import io
import json
import re
import sys
import time
import urllib.request
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).parent
STORE = ROOT / "data" / "serier.json"
AGENT = "Mozilla/5.0 (compatible; NewsnavigatorBot/0.4; +https://newsnavigator.se/bot)"

# id: namn (sv, en), enhet, källa, källsida, hämtare, nyckelord som kopplar serien till en notis
SERIES = {
    "styrranta": {
        "namn": ("Riksbankens styrränta", "Riksbank policy rate"), "enhet": "%", "decimaler": 2,
        "kalla": "Riksbanken", "url": "https://www.riksbank.se/sv/statistik/rantor-och-valutakurser/",
        "hamta": ("riksbank", "SECBREPOEFF"),
        "ord": ["riksbank", "styrränta", "styrräntan", "thedéen", "swedish central bank", "riksbanken"],
    },
    "ecb_ranta": {
        "namn": ("ECB:s inlåningsränta", "ECB deposit facility rate"), "enhet": "%", "decimaler": 2,
        "kalla": "Europeiska centralbanken", "url": "https://data.ecb.europa.eu/",
        "hamta": ("ecb", "FM/B.U2.EUR.4F.KR.DFR.LEV"),
        "ord": ["ecb", "lagarde", "europeiska centralbanken", "european central bank", "eurozone", "euro area", "euroområdet"],
    },
    "inflation_se": {
        "namn": ("Inflation i Sverige (HIKP, årstakt)", "Inflation in Sweden (HICP, annual rate)"), "enhet": "%", "decimaler": 1,
        "kalla": "Eurostat", "url": "https://ec.europa.eu/eurostat/web/hicp",
        "hamta": ("eurostat", "prc_hicp_minr/M.RCH_A.CP00.SE|prc_hicp_manr/M.RCH_A.CP00.SE"),
        "ord": ["inflation", "inflationen", "inflationstakten", "kpif", "kpi", "prices", "priser", "priserna", "konsumentpriser"],
        "krav": ["sverige", "sweden", "swedish", "svensk", "riksbank", "kronan"],
    },
    "inflation_ea": {
        "namn": ("Inflation i euroområdet (HIKP, årstakt)", "Euro area inflation (HICP, annual rate)"), "enhet": "%", "decimaler": 1,
        "kalla": "Eurostat", "url": "https://ec.europa.eu/eurostat/web/hicp",
        "hamta": ("eurostat", "prc_hicp_minr/M.RCH_A.CP00.EA|prc_hicp_manr/M.RCH_A.CP00.EA"),
        "ord": ["inflation", "inflationen", "prices", "priserna"],
        "krav": ["ecb", "eurozone", "euro area", "euroområdet", "lagarde"],
    },
    "eur_sek": {
        "namn": ("Euro i kronor", "Euro in Swedish kronor"), "enhet": "kr", "decimaler": 2,
        "kalla": "Riksbanken", "url": "https://www.riksbank.se/sv/statistik/rantor-och-valutakurser/",
        "hamta": ("riksbank", "SEKEURPMI"),
        "ord": ["kronan", "krona", "valuta", "växelkurs", "sek", "euron"],
    },
    "usd_sek": {
        "namn": ("Dollar i kronor", "US dollar in Swedish kronor"), "enhet": "kr", "decimaler": 2,
        "kalla": "Riksbanken", "url": "https://www.riksbank.se/sv/statistik/rantor-och-valutakurser/",
        "hamta": ("riksbank", "SEKUSDPMI"),
        "ord": ["kronan", "krona", "dollarn", "dollar", "sek"],
        "krav": ["kronan", "krona", "sek", "sverige", "sweden", "riksbank"],
    },
}


def _get(url):
    req = urllib.request.Request(url, headers={"User-Agent": AGENT, "Accept": "*/*"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8")


def _riksbank(series_id, start):
    rows = json.loads(_get(f"https://api.riksbank.se/swea/v1/Observations/{series_id}/{start}/{date.today()}"))
    return [[r["date"], float(r["value"])] for r in rows if r.get("value") is not None]


def _sdmx_csv(url):
    rows = list(csv.DictReader(io.StringIO(_get(url))))
    return [[r["TIME_PERIOD"], float(r["OBS_VALUE"])] for r in rows if r.get("OBS_VALUE")]


def _ecb(key, start):
    return _sdmx_csv(f"https://data-api.ecb.europa.eu/service/data/{key}?format=csvdata&startPeriod={start}")


def _eurostat(keys, start):
    """Provar flera tabeller (Eurostat byter ibland basår och tabellnamn) och tar den färskaste."""
    best, errors = [], []
    for key in keys.split("|"):
        try:
            pts = _eurostat_one(key, start)
            if pts and (not best or max(pts)[0] > max(best)[0]):
                best = pts
        except Exception as e:
            errors.append(f"{key}: {e}")
    if not best:
        raise RuntimeError("; ".join(errors))
    return best


def _eurostat_one(key, start):
    return _sdmx_csv(f"https://ec.europa.eu/eurostat/api/dissemination/sdmx/2.1/data/{key}"
                     f"?format=SDMX-CSV&startPeriod={start[:7]}")


FETCH = {"riksbank": _riksbank, "ecb": _ecb, "eurostat": _eurostat}


def load():
    try:
        return json.loads(STORE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def update(max_age_hours=20):
    """Hämtar serier som är äldre än max_age_hours. Misslyckade hämtningar behåller gammal data."""
    store, now = load(), time.time()
    start = str(date.today() - timedelta(days=760))
    for sid, s in SERIES.items():
        if now - store.get(sid, {}).get("hamtad", 0) < max_age_hours * 3600:
            continue
        kind, key = s["hamta"]
        try:
            points = sorted(FETCH[kind](key, start))
            if points:
                store[sid] = {"punkter": points, "hamtad": now}
                print(f"  Data {sid}: {len(points)} punkter, senast {points[-1]}")
        except Exception as e:
            print(f"  Data {sid} misslyckades: {e}", file=sys.stderr)
    STORE.parent.mkdir(parents=True, exist_ok=True)
    STORE.write_text(json.dumps(store, ensure_ascii=False), encoding="utf-8")
    return store


def _summary(sid, points):
    s = SERIES[sid]
    last_d, last_v = points[-1]
    # Jämför med värdet ungefär ett år tidigare
    target = str(date.fromisoformat(last_d[:10] if len(last_d) >= 10 else last_d + "-01") - timedelta(days=365))
    prev = next((p for p in reversed(points) if (p[0] if len(p[0]) >= 10 else p[0] + "-01") <= target), points[0])
    # Bara de senaste 24 månaderna, glesat till högst 60 punkter för grafen
    step = max(1, len(points) // 60)
    spark = [p[1] for p in points[::step]] + ([points[-1][1]] if (len(points) - 1) % step else [])
    return {"id": sid, "namn_sv": s["namn"][0], "namn_en": s["namn"][1], "enhet": s["enhet"],
            "decimaler": s["decimaler"], "senaste": last_v, "datum": last_d, "ar_sedan": prev[1],
            "ar_sedan_datum": prev[0], "kalla": s["kalla"], "url": s["url"], "spark": spark}


def _text(ev):
    d = ev.get("utkast") or {}
    parts = [d.get("rubrik_sv"), d.get("sammanfattning_sv"), d.get("rubrik_en"), d.get("sammanfattning_en"),
             ev.get("reserv_rubrik")] + [s.get("rubrik") for s in ev.get("kallor", [])]
    return " ".join(p for p in parts if p).lower()


def _has(text, words):
    return any(re.search(r"(?<!\w)" + re.escape(w) + r"(?!\w)", text) for w in words)


def attach(events, store=None, max_per_event=2):
    """Lägger till fältet 'data' på notiser där en serie uppenbart hör hemma."""
    store = store if store is not None else load()
    for ev in events:
        text = _text(ev)
        hits = []
        for sid, s in SERIES.items():
            pts = (store.get(sid) or {}).get("punkter")
            if not pts or not _has(text, s["ord"]):
                continue
            if s.get("krav") and not _has(text, s["krav"]):
                continue
            hits.append(_summary(sid, pts))
        ev["data"] = hits[:max_per_event] or None
    return events
