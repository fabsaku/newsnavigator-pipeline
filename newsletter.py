#!/usr/bin/env python3
"""Navigatorn: Newsnavigators morgonbrev, byggt av granskade notiser.

  python newsletter.py            bygg dagens nummer av godkända notiser från senaste dygnet
  python newsletter.py --utkast   förhandsvisning: fyll på med ogranskade utkast (märkta UTKAST)

Skriver site/navigatorn-sv.html, site/navigatorn-en.html och motsvarande .txt.
Inga AI-anrop: brevet består av redan granskade notiser och redaktörens egen rad (data/kolumn.md).
"""
import argparse
import html
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).parent
ARKIV = ROOT / "data" / "arkiv.json"
FLODE = ROOT / "data" / "flode.json"
KOLUMN = ROOT / "data" / "kolumn.md"
ARKIV_DAGAR = 14
LOGO = os.environ.get("NN_LOGO_URL", "https://newsnavigator.se/newsgator.png")
SITE = os.environ.get("NN_SITE_URL", "https://newsnavigator.se")
TZ = ZoneInfo("Europe/Stockholm")

# Sektioner i brevet. En notis hamnar i den första sektion där något av dess ämnen finns.
SECTIONS = [
    ("varlden", "Världen", "World", {"varlden", "geopolitik", "europa", "usa", "latinamerika", "asien", "mellanostern", "afrika", "forsvar"}),
    ("sverige", "Sverige och Norden", "Sweden and the Nordics", {"sverige", "norden"}),
    ("marknader", "Marknader", "Markets", {"marknader"}),
    ("tech", "Tech och AI", "Tech and AI", {"ai", "teknik", "halvledare", "robotik", "startups"}),
    ("vetenskap", "Vetenskap", "Science", {"vetenskap", "rymd", "energi", "klimat"}),
    ("noje", "Nöje och spel", "Entertainment and games", {"noje", "spel", "kultur"}),
]

# Vilken sektion en notis hamnar i: ämnessektionerna går före den geografiska.
SECTION_PRIORITY = ["tech", "vetenskap", "marknader", "noje", "sverige", "varlden"]
_SECTION_TAGS = {k: tags for k, _, _, tags in SECTIONS}


def usa_text(ev, lang):
    """USA: blått och rött, bara när det är relevant (utgava.usa_relevant)."""
    import utgava
    d = ev.get("utkast") or {}
    return (d.get("usa_en" if lang == "en" else "usa_sv") or d.get("usa_sv")) if utgava.usa_relevant(ev) else None


def section_of(ev):
    """Sektion efter sektionsämnena (texten, och bevakning som alla källor delar), annars Världen.
    Äldre notiser utan sektionsämnen går på alla ämnen."""
    topics = set(ev["amnen_sektion"] if "amnen_sektion" in ev else ev.get("amnen") or [])
    return next((k for k in SECTION_PRIORITY if topics & _SECTION_TAGS[k]), "varlden")


TXT = {
    "sv": {"brev": "Morgonbrevet från Newsnavigator", "korthet": "I korthet", "minuter": "min läsning",
           "varlden": "Så ser världen på det", "usa": "USA: blått och rött", "skiljer": "Källorna skiljer sig åt:", "kallor": "Källor",
           "betalvagg": "betalvägg", "stat": "statskontrollerat", "utkast": "UTKAST",
           "rad": "Redaktörens rad", "princip": "Vi levererar nyheterna. Vad du gör av dem är upp till dig.",
           "ai": "Notiserna är skrivna med hjälp av AI utifrån källornas rubriker och ingresser och granskade av redaktionen innan utskick, eller källkontrollerade och publicerade utan manuell granskning där det står så. Läs hela artiklarna hos källorna.",
           "automatisk": "Publicerad utan manuell granskning, källkontrollerad",
           "avsluta": "Avsluta prenumerationen", "webben": "Läs på webben", "regioner": "regioner",
           "dagar": ["måndag", "tisdag", "onsdag", "torsdag", "fredag", "lördag", "söndag"],
           "manader": ["januari", "februari", "mars", "april", "maj", "juni", "juli", "augusti",
                       "september", "oktober", "november", "december"]},
    "en": {"brev": "The morning brief from Newsnavigator", "korthet": "In brief", "minuter": "min read",
           "varlden": "How the world sees it", "usa": "US: blue and red", "skiljer": "Sources differ:", "kallor": "Sources",
           "betalvagg": "paywall", "stat": "state-controlled", "utkast": "DRAFT",
           "rad": "Editor's note", "princip": "We deliver the news. What you make of it is up to you.",
           "ai": "These briefs are written with the help of AI from the sources' headlines and standfirsts, and reviewed by the editors before sending, or source-checked and published without manual review where marked. Read the full articles at the source.",
           "automatisk": "Published without manual review, source-checked",
           "avsluta": "Unsubscribe", "webben": "Read on the web", "regioner": "regions",
           "dagar": ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"],
           "manader": ["January", "February", "March", "April", "May", "June", "July", "August",
                       "September", "October", "November", "December"]},
}

# Färger och typsnitt. Svart och vitt, dark mode först.
BG, FG, MUTED, RULE = "#0b0b0b", "#f2f2f2", "#9a9a9a", "#2a2a2a"
SERIF = "'Source Serif 4', Georgia, 'Times New Roman', serif"
SANS = "'Source Sans 3', -apple-system, 'Segoe UI', Helvetica, Arial, sans-serif"
MONO = "'IBM Plex Mono', Menlo, Consolas, monospace"


MAX_KALLOR = 5


def _clean(s):
    """Tankstreck ersätts med kolon eller komma, enligt husstilen."""
    if not s:
        return s
    return s.replace(" – ", ": ").replace(" — ", ": ").replace("—", ", ").replace("–", "-")


def _e(s):
    return html.escape(_clean(s) or "", quote=True)


# ---------- Arkiv över godkända notiser ----------

def load_archive():
    try:
        return json.loads(ARKIV.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def archive(events, approved, automatic=()):
    """Sparar godkända notiser så att brevet kan byggas även när de fallit ur flödet.
    `automatic` är id som autopiloten godkänt; de märks så att sajten, brevet och korten kan säga det."""
    arkiv, now = load_archive(), time.time()
    for ev in events:
        if ev["id"] in approved and ev["id"] not in arkiv:
            arkiv[ev["id"]] = {**ev, "granskad": True, "godkand_tid": now, "automatisk": ev["id"] in automatic}
        elif ev["id"] in arkiv:
            # Samma händelse med nya källor: källorna uppdateras, den publicerade texten står kvar
            post = arkiv[ev["id"]]
            if {k["url"] for k in ev.get("kallor") or []} != {k["url"] for k in post.get("kallor") or []}:
                keep = {k: post[k] for k in ("utkast", "kallkontroll", "godkand_tid", "automatisk", "granskad") if k in post}
                arkiv[ev["id"]] = {**post, **ev, **keep, "uppdaterad_tid": now}
    limit = now - ARKIV_DAGAR * 86400
    arkiv = {k: v for k, v in arkiv.items() if v.get("godkand_tid", 0) >= limit}
    ARKIV.parent.mkdir(parents=True, exist_ok=True)
    ARKIV.write_text(json.dumps(arkiv, ensure_ascii=False, indent=1), encoding="utf-8")
    return arkiv


# ---------- Urval ----------

def pick(include_drafts, hours=24, limit=12):
    since = time.time() - hours * 3600
    chosen = sorted((e for e in load_archive().values() if e.get("godkand_tid", 0) >= since),
                    key=lambda e: e.get("poang", 0), reverse=True)
    if include_drafts and len(chosen) < limit and FLODE.exists():
        have = {e["id"] for e in chosen}
        for e in json.loads(FLODE.read_text(encoding="utf-8"))["handelser"]:
            d = e.get("utkast") or {}
            if e["id"] in have or not d.get("rubrik_sv") or d.get("osaker"):
                continue
            chosen.append({**e, "granskad": False})
            if len(chosen) >= limit:
                break
    chosen = chosen[:limit]
    groups = {key: [] for key, *_ in SECTIONS}
    for e in chosen:
        groups[section_of(e)].append(e)
    return chosen, groups


def column(lang):
    """data/kolumn.md: första raden rubrik, resten stycken. Valfri '---' delar svensk och engelsk text."""
    if not KOLUMN.exists():
        return None
    parts = KOLUMN.read_text(encoding="utf-8").split("\n---\n")
    text = parts[1] if lang == "en" and len(parts) > 1 else parts[0]
    lines = [l for l in text.strip().splitlines()]
    if not lines:
        return None
    paras = [p.strip() for p in "\n".join(lines[1:]).split("\n\n") if p.strip()]
    return lines[0].lstrip("# ").strip(), paras


def dateline(lang, now):
    t = TXT[lang]
    if lang == "sv":
        return f"{t['dagar'][now.weekday()].capitalize()} {now.day} {t['manader'][now.month - 1]} {now.year}"
    return f"{t['dagar'][now.weekday()]} {now.day} {t['manader'][now.month - 1]} {now.year}"


def reading_minutes(chosen, col):
    words = sum(len(" ".join(str((e.get("utkast") or {}).get(f) or "") for f in
                             ("rubrik_sv", "sammanfattning_sv", "perspektiv_sv", "oenighet")).split()) + 10 for e in chosen)
    if col:
        words += sum(len(p.split()) for p in col[1])
    return max(2, round(words / 200))


# ---------- HTML för e-post ----------

def _source_links(ev, lang):
    t = TXT[lang]
    out = []
    for s in ev["kallor"][:MAX_KALLOR]:
        bits = f'<a href="{_e(s["url"])}" style="color:{FG};text-decoration:underline">{_e(s["namn"])}</a>'
        notes = [n for n, on in ((t["betalvagg"], s.get("betalvagg")), (t["stat"], s.get("statskontrollerad"))) if on]
        if notes:
            bits += f' <span style="color:{MUTED}">({", ".join(notes)})</span>'
        out.append(bits)
    rest = len(ev["kallor"]) - MAX_KALLOR
    if rest > 0:
        more = f"och {rest} till" if lang == "sv" else f"and {rest} more"
        out.append(f'<a href="{_e(SITE)}/#h-{ev["id"]}" style="color:{MUTED}">{more}</a>')
    return ", ".join(out)


def _story(ev, lang, first):
    t, d = TXT[lang], ev.get("utkast") or {}
    title = d.get(f"rubrik_{lang}") or d.get("rubrik_sv") or ev["reserv_rubrik"]
    summary = d.get(f"sammanfattning_{lang}") or d.get("sammanfattning_sv")
    persp = d.get(f"perspektiv_{lang}") or d.get("perspektiv_sv")
    dis = d.get("oenighet_en" if lang == "en" else "oenighet") or d.get("oenighet")
    regs = (ev.get("perspektiv") or {}).get("regioner", [])
    draft = "" if ev.get("granskad") else (
        f'<span style="font-family:{MONO};font-size:11px;letter-spacing:.08em;border:1px solid {FG};'
        f'padding:1px 5px;margin-right:6px">{t["utkast"]}</span>')
    auto = (f'<p style="margin:-4px 0 10px 0;font-family:{SANS};font-size:12px;color:{MUTED}">{t["automatisk"]}.</p>'
            if ev.get("automatisk") else "")
    rows = [f'<tr><td style="padding:{"4px" if first else "22px"} 0 0 0;border-top:{"0" if first else "1px solid " + RULE}">'
            f'<h2 style="margin:0 0 8px 0;padding-top:{"0" if first else "18px"};font-family:{SERIF};font-weight:600;'
            f'font-size:22px;line-height:1.25;color:{FG}">{draft}{_e(title)}</h2>{auto}']
    if summary:
        rows.append(f'<p style="margin:0 0 10px 0;font-family:{SANS};font-size:16px;line-height:1.55;color:{FG}">{_e(summary)}</p>')
    if persp and len(regs) >= 2:
        rows.append(f'<p style="margin:0 0 10px 0;padding-left:12px;border-left:2px solid {FG};font-family:{SANS};'
                    f'font-size:15px;line-height:1.5;color:{FG}"><b>{t["varlden"]}</b> '
                    f'<span style="font-family:{MONO};font-size:11px;color:{MUTED}">{len(regs)} {t["regioner"]}</span><br>{_e(persp)}</p>')
    for x in ev.get("data") or []:
        v = f'{x["senaste"]:.{x["decimaler"]}f}'
        prev = f'{x["ar_sedan"]:.{x["decimaler"]}f}'
        if lang == "sv":
            v, prev = v.replace(".", ","), prev.replace(".", ",")
        name = x["namn_en"] if lang == "en" else x["namn_sv"]
        year = "a year earlier" if lang == "en" else "ett år tidigare"
        rows.append(f'<p style="margin:0 0 10px 0;font-family:{MONO};font-size:13px;line-height:1.5;color:{FG}">'
                    f'{_e(name)}: <b>{v} {x["enhet"]}</b> ({_e(x["datum"])}, {year} {prev} {x["enhet"]}) · '
                    f'<a href="{_e(x["url"])}" style="color:{MUTED}">{_e(x["kalla"])}</a></p>')
    usa = usa_text(ev, lang)
    if usa:
        rows.append(f'<p style="margin:0 0 10px 0;padding-left:12px;border-left:2px solid {FG};font-family:{SANS};'
                    f'font-size:15px;line-height:1.5;color:{FG}"><b>{t["usa"]}</b> '
                    f'<span style="font-family:{MONO};font-size:11px;color:{MUTED}">AllSides</span><br>{_e(usa)}</p>')
    if dis:
        rows.append(f'<p style="margin:0 0 10px 0;font-family:{SANS};font-size:15px;line-height:1.5;color:{FG}">'
                    f'<b>{t["skiljer"]}</b> {_e(dis)}</p>')
    rows.append(f'<p style="margin:0;font-family:{SANS};font-size:13px;line-height:1.6;color:{MUTED}">'
                f'{t["kallor"]}: {_source_links(ev, lang)}</p></td></tr>')
    return "".join(rows)


def build_html(lang, chosen, groups, col, now):
    t = TXT[lang]
    label = {k: (sv if lang == "sv" else en) for k, sv, en, _ in SECTIONS}
    mins = reading_minutes(chosen, col)
    topline = "".join(
        f'<li style="margin:0 0 6px 0">{_e((e.get("utkast") or {}).get(f"rubrik_{lang}") or (e.get("utkast") or {}).get("rubrik_sv") or e["reserv_rubrik"])}</li>'
        for e in chosen[:3])
    body = []
    for key, items in groups.items():
        if not items:
            continue
        body.append(f'<tr><td style="padding:34px 0 6px 0"><div style="font-family:{MONO};font-size:12px;letter-spacing:.14em;'
                    f'text-transform:uppercase;color:{FG};border-bottom:2px solid {FG};padding-bottom:6px">{label[key]}</div></td></tr>')
        body.extend(_story(e, lang, i == 0) for i, e in enumerate(items))
    col_html = ""
    if col:
        paras = "".join(f'<p style="margin:0 0 12px 0;font-family:{SERIF};font-size:18px;line-height:1.55;color:{FG}">{_e(p)}</p>' for p in col[1])
        col_html = (f'<tr><td style="padding:34px 0 0 0"><div style="font-family:{MONO};font-size:12px;letter-spacing:.14em;'
                    f'text-transform:uppercase;color:{FG};border-bottom:2px solid {FG};padding-bottom:6px">{t["rad"]}</div>'
                    f'<h2 style="margin:16px 0 10px 0;font-family:{SERIF};font-style:italic;font-weight:600;font-size:24px;color:{FG}">{_e(col[0])}</h2>'
                    f'{paras}</td></tr>')
    preheader = " · ".join(((e.get("utkast") or {}).get(f"rubrik_{lang}") or e["reserv_rubrik"]) for e in chosen[:2])
    return f"""<!doctype html>
<html lang="{lang}"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="color-scheme" content="dark light"><meta name="supported-color-schemes" content="dark light">
<title>Navigatorn · {dateline(lang, now)}</title>
<link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono&family=Source+Sans+3:wght@400;600&family=Source+Serif+4:ital,wght@0,600;1,600&display=swap" rel="stylesheet">
</head>
<body style="margin:0;padding:0;background:{BG};color:{FG}">
<div style="display:none;max-height:0;overflow:hidden;opacity:0">{_e(preheader)}</div>
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:{BG}"><tr><td align="center" style="padding:28px 16px">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="max-width:600px">
<tr><td style="padding-bottom:18px;border-bottom:1px solid {FG}">
  <table role="presentation" cellpadding="0" cellspacing="0"><tr>
    <td style="padding-right:14px;vertical-align:middle"><img src="{_e(LOGO)}" width="78" height="56" alt="Newsgator" style="display:block;border:0"></td>
    <td style="vertical-align:middle"><div style="font-family:{SERIF};font-size:30px;font-weight:600;line-height:1;color:{FG}">Navigatorn</div>
      <div style="font-family:{MONO};font-size:12px;color:{MUTED};padding-top:6px">{t["brev"]}</div></td>
  </tr></table>
</td></tr>
<tr><td style="padding:12px 0;font-family:{MONO};font-size:12px;color:{MUTED};border-bottom:1px solid {RULE}">
  {dateline(lang, now)} · {len(chosen)} {"notiser" if lang == "sv" else "stories"} · {mins} {t["minuter"]} · <a href="{_e(SITE)}" style="color:{MUTED}">{t["webben"]}</a>
</td></tr>
<tr><td style="padding:24px 0 0 0">
  <div style="font-family:{MONO};font-size:12px;letter-spacing:.14em;text-transform:uppercase;color:{FG};padding-bottom:10px">{t["korthet"]}</div>
  <ul style="margin:0;padding-left:20px;font-family:{SERIF};font-size:18px;line-height:1.4;color:{FG}">{topline}</ul>
</td></tr>
{"".join(body)}
{col_html}
<tr><td style="padding:40px 0 0 0;border-bottom:1px solid {FG}"></td></tr>
<tr><td style="padding:18px 0 0 0;font-family:{SERIF};font-style:italic;font-size:17px;color:{FG}">{t["princip"]}</td></tr>
<tr><td style="padding:10px 0 0 0;font-family:{SANS};font-size:12px;line-height:1.6;color:{MUTED}">{t["ai"]}</td></tr>
<tr><td style="padding:14px 0 30px 0;font-family:{SANS};font-size:12px;color:{MUTED}">Newsnavigator · <a href="{_e(SITE)}" style="color:{MUTED}">newsnavigator.se</a> · <a href="{{{{unsubscribe_url}}}}" style="color:{MUTED}">{t["avsluta"]}</a></td></tr>
</table></td></tr></table>
</body></html>"""


def build_text(lang, chosen, groups, col, now):
    t = TXT[lang]
    label = {k: (sv if lang == "sv" else en) for k, sv, en, _ in SECTIONS}
    out = [f"NAVIGATORN · {dateline(lang, now)}", t["brev"], "", t["korthet"].upper()]
    out += [f"- {(e.get('utkast') or {}).get(f'rubrik_{lang}') or e['reserv_rubrik']}" for e in chosen[:3]]
    for key, items in groups.items():
        if not items:
            continue
        out += ["", label[key].upper(), ""]
        for e in items:
            d = e.get("utkast") or {}
            tag = "" if e.get("granskad") else f"[{t['utkast']}] "
            out.append(tag + (d.get(f"rubrik_{lang}") or d.get("rubrik_sv") or e["reserv_rubrik"]))
            if d.get(f"sammanfattning_{lang}") or d.get("sammanfattning_sv"):
                out.append(d.get(f"sammanfattning_{lang}") or d.get("sammanfattning_sv"))
            persp = d.get(f"perspektiv_{lang}") or d.get("perspektiv_sv")
            if persp and len((e.get("perspektiv") or {}).get("regioner", [])) >= 2:
                out.append(f"{t['varlden']}: {persp}")
            usa = usa_text(e, lang)
            if usa:
                out.append(f"{t['usa']}: {usa}")
            for s in e["kallor"][:MAX_KALLOR]:
                out.append(f"  {s['namn']}{' (' + t['betalvagg'] + ')' if s.get('betalvagg') else ''}: {s['url']}")
            out.append("")
    if col:
        out += ["", t["rad"].upper(), col[0], ""] + col[1]
    out += ["", t["princip"], t["ai"], "", f"Newsnavigator · {SITE}", f"{t['avsluta']}: {{{{unsubscribe_url}}}}"]
    return _clean("\n".join(out))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--utkast", action="store_true", help="fyll på med ogranskade utkast för förhandsvisning")
    ap.add_argument("--timmar", type=float, default=24)
    ap.add_argument("--out", default=str(ROOT / "site"))
    args = ap.parse_args()

    if FLODE.exists():
        godk = ROOT / "data" / "godkanda.json"
        approved = set(json.loads(godk.read_text())) if godk.exists() else set()
        archive(json.loads(FLODE.read_text(encoding="utf-8"))["handelser"], approved)

    chosen, groups = pick(args.utkast, args.timmar)
    if not chosen:
        print("Inga godkända notiser senaste dygnet. Kör granska.py godkann, eller --utkast för förhandsvisning.")
        return
    now = datetime.now(timezone.utc).astimezone(TZ)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    for lang in ("sv", "en"):
        col = column(lang)
        (out / f"navigatorn-{lang}.html").write_text(build_html(lang, chosen, groups, col, now), encoding="utf-8")
        (out / f"navigatorn-{lang}.txt").write_text(build_text(lang, chosen, groups, col, now), encoding="utf-8")
    reviewed = sum(1 for e in chosen if e.get("granskad"))
    print(f"Navigatorn: {len(chosen)} notiser ({reviewed} granskade, {len(chosen) - reviewed} utkast) -> {out}/navigatorn-*.html")


if __name__ == "__main__":
    main()
