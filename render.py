"""Gemensam form för Newsnavigator: stilmall, notiskomponenter och den interna förhandsvisningen av flödet.

Formen är en tidningssida i svartvitt, mörk först. Serif för rubriker och löptext, sans för navigation och meta.
Det enda som får ta plats är täckningsremsan: en cell per region som tänds när regionen rapporterar.
"""
import html
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).parent

TOPICS = {"ai": ("AI", "AI"), "robotik": ("Robotik", "Robotics"), "marknader": ("Marknader", "Markets"),
          "varlden": ("Världen", "World"), "sverige": ("Sverige", "Sweden"), "europa": ("Europa", "Europe"),
          "geopolitik": ("Geopolitik", "Geopolitics"), "teknik": ("Teknik", "Tech"), "vetenskap": ("Vetenskap", "Science"),
          "rymd": ("Rymd", "Space"), "energi": ("Energi", "Energy"), "klimat": ("Klimat", "Climate"),
          "forsvar": ("Försvar", "Defence"), "startups": ("Startups", "Startups"), "halvledare": ("Halvledare", "Chips"),
          "norden": ("Norden", "Nordics"), "usa": ("USA", "US"), "asien": ("Asien", "Asia"),
          "mellanostern": ("Mellanöstern", "Middle East"), "afrika": ("Afrika", "Africa"), "latinamerika": ("Latinamerika", "Latin America"),
          "spel": ("Spel", "Games"), "noje": ("Nöje", "Entertainment"), "kultur": ("Kultur", "Culture")}
REGIONS = {"sverige": ("Sverige", "Sweden"), "norden": ("Norden", "Nordics"), "europa": ("Europa", "Europe"),
           "usa": ("USA och Kanada", "US and Canada"), "latinamerika": ("Latinamerika", "Latin America"),
           "asien": ("Asien och Oceanien", "Asia and Oceania"), "mellanostern": ("Mellanöstern", "Middle East"),
           "afrika": ("Afrika", "Africa"), "global": ("Globalt", "Global")}
SHORT = {"mellanostern": ("Mellan\u00adöstern", "Middle East"), "latinamerika": ("Latin\u00adamerika", "Latin America"),
         "usa": ("USA", "US"), "asien": ("Asien", "Asia")}  # mjukt bindestreck i remsan
REGION_ORDER = ["sverige", "norden", "europa", "usa", "latinamerika", "afrika", "mellanostern", "asien", "global"]
COUNTRIES = {"US": ("USA", "US"), "SE": ("Sverige", "Sweden"), "GB": ("Storbritannien", "UK"), "FR": ("Frankrike", "France"),
             "DE": ("Tyskland", "Germany"), "INT": ("internationell", "international"), "BE": ("Belgien", "Belgium"),
             "EU": ("EU", "EU"), "JP": ("Japan", "Japan"), "IL": ("Israel", "Israel"), "CN": ("Kina", "China"),
             "FI": ("Finland", "Finland"), "NO": ("Norge", "Norway"), "ES": ("Spanien", "Spain"), "HK": ("Hongkong", "Hong Kong"),
             "IN": ("Indien", "India"), "QA": ("Qatar", "Qatar"), "SA": ("Saudiarabien", "Saudi Arabia"),
             "ZA": ("Sydafrika", "South Africa"), "RU": ("Ryssland", "Russia"), "DK": ("Danmark", "Denmark"),
             "NL": ("Nederländerna", "Netherlands"), "IT": ("Italien", "Italy"), "CH": ("Schweiz", "Switzerland"),
             "KR": ("Sydkorea", "South Korea"), "SG": ("Singapore", "Singapore"), "AU": ("Australien", "Australia"),
             "CA": ("Kanada", "Canada"), "TR": ("Turkiet", "Turkey"), "AE": ("Förenade Arabemiraten", "UAE"),
             "EG": ("Egypten", "Egypt"), "NG": ("Nigeria", "Nigeria"), "KE": ("Kenya", "Kenya"), "BR": ("Brasilien", "Brazil"),
             "MX": ("Mexiko", "Mexico"), "PL": ("Polen", "Poland"), "UA": ("Ukraina", "Ukraine"), "TW": ("Taiwan", "Taiwan"),
             "IE": ("Irland", "Ireland"), "AT": ("Österrike", "Austria"), "IR": ("Iran", "Iran")}
SIDES = [("bla", "Blå publik", "Blue audience"), ("mitten", "Mitten", "Centre"), ("rod", "Röd publik", "Red audience")]
LEANS = {"vanster": ("vänster", "left"), "lutar_vanster": ("lutar vänster", "lean left"), "mitten": ("mitten", "centre"),
         "lutar_hoger": ("lutar höger", "lean right"), "hoger": ("höger", "right")}

FONTS_URL = ("https://fonts.googleapis.com/css2?family=Source+Serif+4:ital,opsz,wght@0,8..60,400..700;1,8..60,400..700"
             "&family=Source+Sans+3:wght@400;600;700;800&display=swap")

CSS = """
:root{color-scheme:dark;--bg:#000;--ink:#fff;--text:#d6d6d6;--mute:#8c8c8c;--rule:#2e2e2e;--panel:#121212;
--serif:'Source Serif 4',Georgia,'Times New Roman',serif;--sans:'Source Sans 3','Helvetica Neue',Arial,sans-serif}
*{box-sizing:border-box}html{background:var(--bg)}
body{margin:0;background:var(--bg);color:var(--text);font:400 17px/1.5 var(--sans);-webkit-font-smoothing:antialiased;text-rendering:optimizeLegibility}
a{color:var(--ink);text-decoration-thickness:1px;text-underline-offset:3px}
h1,h2,h3,h4{margin:0;font-family:var(--serif);font-weight:600;color:var(--ink);letter-spacing:-.005em}
p{margin:0}
.w{max-width:1200px;margin:0 auto;padding:0 24px}
:focus-visible{outline:2px solid var(--ink);outline-offset:3px}
.sr{position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0 0 0 0)}

/* Sidhuvud */
.mast{display:grid;grid-template-columns:1fr auto 1fr;align-items:center;padding:18px 0 14px}
.mast .date{font-size:14px;color:var(--mute)}
.brand{display:flex;align-items:center;gap:14px;text-decoration:none;color:var(--ink);justify-self:center}
.brand svg{height:52px;width:auto;display:block}
.brand span{font:800 21px/1 var(--sans);letter-spacing:.09em;text-transform:uppercase}
.lang{display:flex;justify-self:end;gap:2px}
.lang button{height:40px;padding:0 8px;border:0;background:none;color:var(--mute);font:600 13px var(--sans);letter-spacing:.04em;cursor:pointer;border-bottom:2px solid transparent}
.lang button[aria-pressed=true]{color:var(--ink);border-bottom-color:var(--ink)}
.lang button:hover{color:var(--ink)}
header{border-bottom:1px solid var(--ink)}
.banner{background:var(--ink);color:var(--bg);font:600 13px var(--sans);padding:7px 0}

/* Notiser */
.story{display:grid;gap:12px;min-width:0}
.story .kicker{font-size:14px;color:var(--mute)}
.story .kicker a{color:var(--mute);text-decoration:none}.story .kicker a:hover{color:var(--ink)}
.story h1,.story h2,.story h3{line-height:1.1}
.story h2 a,.story h3 a{text-decoration:none}.story h2 a:hover,.story h3 a:hover{text-decoration:underline}
.story .sum{font:400 19px/1.5 var(--serif);color:var(--text);max-width:64ch}
.story.lead h2{font-size:50px;line-height:1.04;letter-spacing:-.015em;max-width:20ch}
.story.lead .sum{font-size:21px}
.story.featured h3{font-size:28px;max-width:26ch}
.story.single h1,.story.single h2{font-size:48px;line-height:1.06;letter-spacing:-.015em;max-width:24ch}
.story.single .sum{font-size:22px;max-width:60ch}
.story.single .cov{max-width:760px}
.meta{font-size:14px;color:var(--mute)}
.meta b{font-weight:600;color:var(--ink)}
.srcline{font-size:14px;color:var(--mute);line-height:1.55}
.srcline a{color:var(--text);text-decoration:none}.srcline a:hover{text-decoration:underline;color:var(--ink)}
.stat{display:inline-block;font:700 10px/1 var(--sans);letter-spacing:.06em;border:1px solid currentColor;padding:2px 3px 1px;margin-left:5px;vertical-align:1px}

/* Täckningsremsan */
.cov{display:grid;grid-template-columns:repeat(9,minmax(0,1fr));gap:5px;margin:2px 0 0}
.cov.usa{grid-template-columns:repeat(3,minmax(0,1fr));max-width:330px}
.cov .c{display:flex;flex-direction:column;gap:6px;min-width:0}
.cov .c b{display:block;height:6px;background:var(--rule)}
.cov .c i{font:400 11.5px/1.15 var(--sans);font-style:normal;color:var(--mute);hyphens:manual}
.cov .c i strong{font-weight:700;color:var(--ink)}
.cov .on b{background:var(--ink)}.cov .on i{color:var(--text)}

/* Rubriklistor */
.list{list-style:none;margin:0;padding:0}
.list li{padding:14px 0;border-top:1px solid var(--rule)}
.list li:first-child{border-top:0;padding-top:0}
.list h3{font-size:20px;line-height:1.2}
.list h3 a{text-decoration:none}.list h3 a:hover{text-decoration:underline}
.list .meta{margin-top:5px}
.list .meta a{color:var(--text);text-decoration:none}.list .meta a:hover{color:var(--ink);text-decoration:underline}

/* Notissidan: regioner, USA, oenighet */
.section-h{font-size:24px;margin:34px 0 10px;line-height:1.15}
.persp{font:400 18px/1.55 var(--serif);color:var(--text);max-width:66ch;margin:0 0 18px}
.regions{display:grid;grid-template-columns:repeat(auto-fill,minmax(230px,1fr));gap:18px 24px}
.region h4{font:600 15px/1.2 var(--sans);color:var(--ink);margin:0 0 8px;padding-bottom:6px;border-bottom:1px solid var(--rule)}
.region ul{list-style:none;margin:0;padding:0;display:flex;flex-direction:column;gap:10px}
.region li{font-size:15px;line-height:1.35}.region li a{text-decoration:none}.region li a:hover{text-decoration:underline}
.region li .who{display:block;color:var(--mute);font-size:13px;margin-top:2px}
.region li.none{color:var(--mute)}
.note{font-size:13px;color:var(--mute);margin:14px 0 0;max-width:66ch}
.dis{border-left:2px solid var(--ink);padding:2px 0 2px 16px;font:400 17px/1.5 var(--serif);color:var(--text);max-width:66ch}
.srcfull{list-style:none;margin:0;padding:0;columns:2;column-gap:32px;font-size:15px;line-height:1.5;max-width:900px}
.srcfull li{break-inside:avoid;padding:3px 0}.srcfull a{text-decoration:none}.srcfull a:hover{text-decoration:underline}
.srcfull .who{color:var(--mute)}
.check{font-size:14px;color:var(--mute);margin:18px 0 0;max-width:66ch}
.check b{color:var(--ink);font-weight:600}

/* Data bakom nyheten */
.data{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:14px;margin:4px 0 0}
.datum{border-top:2px solid var(--ink);padding:10px 0 0;display:flex;flex-direction:column;gap:4px;min-width:0}
.datum .k{font-size:14px;color:var(--mute)}
.datum .v{font:600 28px/1.1 var(--serif);color:var(--ink);font-variant-numeric:tabular-nums}
.datum svg{width:100%;height:34px;display:block;color:var(--text)}
.datum .s{font-size:13px;color:var(--mute)}.datum .s a{color:var(--mute)}

/* Intern förhandsvisning */
.intro{padding:16px 0;border-bottom:1px solid var(--rule);display:flex;flex-wrap:wrap;justify-content:space-between;gap:8px 24px;font-size:15px;color:var(--mute)}
.intro p{font:400 18px/1.4 var(--serif);color:var(--text)}
.chips{display:flex;flex-wrap:wrap;gap:6px;padding:16px 0 4px}
.chips button{min-height:36px;padding:0 12px;border:1px solid var(--rule);background:none;color:var(--text);font:500 14px var(--sans);cursor:pointer}
.chips button[aria-pressed=true]{background:var(--ink);color:var(--bg);border-color:var(--ink)}
.feed .story{padding:28px 0;border-top:1px solid var(--rule)}
.feed .story:first-child{border-top:0}
.feed .story.single h2{font-size:34px}
.hidden{display:none}

body.en .sv,body:not(.en) .en{display:none}
@media (prefers-reduced-motion:no-preference){.lang button,.srcline a{transition:color .15s}}
@media (max-width:720px){
.w{padding:0 16px}
.mast{grid-template-columns:1fr auto;padding:12px 0 10px}.mast .date{display:none}
.brand{justify-self:start;gap:10px}.brand svg{height:40px}.brand span{font-size:17px}
.story.lead h2{font-size:34px}.story.single h1,.story.single h2{font-size:32px}.story.featured h3{font-size:24px}
.story.lead .sum,.story.single .sum{font-size:19px}
.cov{gap:3px}.cov .c i{font-size:10.5px}
.srcfull{columns:1}
}
"""

JS = """
(function(){
  var b=document.body, btns=document.querySelectorAll('.lang button'), dateEl=document.querySelector('[data-date]');
  function date(l){
    if(!dateEl)return;
    var s=new Date().toLocaleDateString(l==='en'?'en-GB':'sv-SE',{weekday:'long',day:'numeric',month:'long',year:'numeric'});
    dateEl.textContent=s.charAt(0).toUpperCase()+s.slice(1);
  }
  function setLang(l){b.classList.toggle('en',l==='en');document.documentElement.lang=l;
    btns.forEach(function(x){x.setAttribute('aria-pressed',x.dataset.l===l)});date(l);
    if(!window.NN_LANG){try{localStorage.setItem('nn-lang',l)}catch(e){}}}
  btns.forEach(function(x){x.addEventListener('click',function(){setLang(x.dataset.l)})});
  var s=null;try{s=localStorage.getItem('nn-lang')}catch(e){}
  setLang(window.NN_LANG||(s==='en'?'en':'sv'));
  var chips=document.querySelectorAll('.chips button'), evs=document.querySelectorAll('.feed .story');
  chips.forEach(function(c){c.addEventListener('click',function(){
    chips.forEach(function(x){x.setAttribute('aria-pressed',x===c)});
    var t=c.dataset.t; evs.forEach(function(e){e.classList.toggle('hidden',t!=='alla'&&e.dataset.t.split(' ').indexOf(t)<0)});
  })});
})();
"""


def _e(s):
    return html.escape(s or "", quote=True)


MANADER_SV = ["januari", "februari", "mars", "april", "maj", "juni", "juli", "augusti", "september", "oktober", "november", "december"]
MANADER_EN = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"]


def tidstext(ts, kort=False):
    """(svenska, engelska). Svensk tid i den svenska utgåvan, UTC i den engelska, som är global. `kort` utan år."""
    s = datetime.fromtimestamp(ts, timezone.utc).astimezone(ZoneInfo("Europe/Stockholm"))
    u = datetime.fromtimestamp(ts, timezone.utc)
    ar_s, ar_u = ("", "") if kort else (f" {s.year}", f" {u.year}")
    return (f"{s.day} {MANADER_SV[s.month - 1]}{ar_s} kl {s:%H.%M}",
            f"{u.day} {MANADER_EN[u.month - 1]}{ar_u} at {u:%H:%M} UTC")


def stampel(ts, kort=False):
    """Tidsstämpel som riktigt <time>-element."""
    iso = datetime.fromtimestamp(ts, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return f'<time datetime="{iso}">{_both(*tidstext(ts, kort))}</time>'


def _both(sv, en):
    sv, en = _e(sv), _e(en or sv)
    return sv if sv == en else f'<span class="sv">{sv}</span><span class="en">{en}</span>'


def _mascot():
    p = ROOT / "assets" / "newsgator.svg"
    if not p.exists():
        return ""
    svg = p.read_text(encoding="utf-8")
    return re.sub(r"<svg ", '<svg role="img" aria-label="Newsgator" ', svg, count=1)


def country(code):
    """Landsnamn på svenska och engelska, eller koden om den är okänd."""
    return COUNTRIES.get(code, (code, code))


# ---------- Små delar ----------

def _words_sv(n):
    return {1: "en", 2: "två", 3: "tre", 4: "fyra", 5: "fem", 6: "sex", 7: "sju", 8: "åtta", 9: "nio"}.get(n, str(n))


def _words_en(n):
    return {1: "one", 2: "two", 3: "three", 4: "four", 5: "five", 6: "six", 7: "seven", 8: "eight"}.get(n, str(n))


def meta_line(ev):
    """'15 källor i sex regioner', i båda språken."""
    n = ev["antal_kallor"]
    k = len((ev.get("perspektiv") or {}).get("regioner", [])) or 1
    sv = f"{n} {'källa' if n == 1 else 'källor'} i {_words_sv(k)} {'region' if k == 1 else 'regioner'}"
    en = f"{n} {'source' if n == 1 else 'sources'} in {_words_en(k)} {'region' if k == 1 else 'regions'}"
    return _both(sv, en)


def notes(ev, internal=False):
    """Det som avviker, som korta meningar i vitt: blind fläck, tunt underlag, USA-slagsida."""
    d = ev.get("utkast") or {}
    p = ev.get("perspektiv") or {}
    out = []
    if internal and not ev.get("granskad"):
        out.append(_both("Ej granskad", "Not reviewed"))
    if d.get("osaker"):
        out.append(_both("Tunt underlag", "Thin sourcing"))
    blind = p.get("blind_flack")
    if blind == "saknas_i_sverige" and ev.get("_over_sprak"):
        out.append(_both("Saknas i svenska medier", "Not in Swedish media"))
    elif blind == "bara_i_sverige":
        out.append(_both("Bara i svenska medier", "Only in Swedish media"))
    if p.get("usa_blind") == "mest_bla":
        out.append(_both("Mest i medier med blå publik", "Mostly in blue-audience media"))
    elif p.get("usa_blind") == "mest_rod":
        out.append(_both("Mest i medier med röd publik", "Mostly in red-audience media"))
    return out


def ai_marke(ev):
    """Kort märke för varje publicerad notis: att AI skrev och vad en människa gjorde. Tomt för utkast."""
    if ev.get("automatisk"):
        return _both("AI, ej manuellt granskad", "AI, not manually reviewed")
    if ev.get("granskad"):
        return _both("AI, granskad av redaktionen", "AI, reviewed in Swedish by the editors")
    return ""


def _nar(ev):
    return stampel(ev["godkand_tid"], kort=True) if ev.get("godkand_tid") else ""


def _kalltid(x):
    return f', {stampel(x["tid"], kort=True)}' if x.get("tid") else ""


def meta_block(ev, internal=False, tid=True):
    parts = ([_nar(ev)] if tid and _nar(ev) else []) + [meta_line(ev)] + [f"<b>{n}</b>" for n in notes(ev, internal)]
    parts += [ai_marke(ev)] if ai_marke(ev) and not internal else []
    return f'<p class="meta">{". ".join(parts)}.</p>'


def coverage(ev):
    """Täckningsremsan: en cell per region i fast ordning, tänd när regionen rapporterar."""
    p = ev.get("perspektiv") or {}
    per = p.get("per_region") or {}
    counts = {r: len(v) for r, v in per.items()}
    if not counts:
        counts = {}
        for s in ev["kallor"]:
            counts[s.get("region", "global")] = counts.get(s.get("region", "global"), 0) + 1
    cells, lit = [], []
    for r in REGION_ORDER:
        sv, en = SHORT.get(r, REGIONS[r])
        n = counts.get(r, 0)
        if n:
            cells.append(f'<span class="c on"><b></b><i><strong>{n}</strong> {_both(sv, en)}</i></span>')
            lit.append(f"{REGIONS[r][0]} {n}")
        else:
            cells.append(f'<span class="c"><b></b><i>{_both(sv, en)}</i></span>')
    label = _e("Rapporteras i: " + ", ".join(lit))
    return f'<div class="cov" role="img" aria-label="{label}">{"".join(cells)}</div>'


def coverage_usa(p):
    sides = p.get("usa")
    if not sides:
        return ""
    cells = []
    for key, sv, en in SIDES:
        n = len(sides.get(key) or [])
        if n:
            cells.append(f'<span class="c on"><b></b><i><strong>{n}</strong> {_both(sv, en)}</i></span>')
        else:
            cells.append(f'<span class="c"><b></b><i>{_both(sv, en)}</i></span>')
    return f'<div class="cov usa" role="img" aria-label="USA: {_e(", ".join(f"{sv} {len(sides.get(k) or [])}" for k, sv, _ in SIDES))}">{"".join(cells)}</div>'


def source_sentence(ev, more_href=None, limit=3):
    """'The Guardian, South China Morning Post, Al Jazeera och 12 till', namnen länkade till originalen."""
    srcs = ev["kallor"]
    names = [f'<a href="{_e(s["url"])}" rel="noopener">{_e(s["namn"])}</a>' + ('<span class="stat">STAT</span>' if s.get("statskontrollerad") else "")
             for s in srcs[:limit]]
    rest = len(srcs) - limit
    if rest > 0:
        tail = _both(f"och {rest} till", f"and {rest} more")
        tail = f'<a href="{_e(more_href)}">{tail}</a>' if more_href else tail
        if len(names) > 1:
            text = ", ".join(names) + " " + tail
        else:
            text = names[0] + " " + tail
    elif len(names) > 1:
        text = ", ".join(names[:-1]) + " " + _both("och", "and") + " " + names[-1]
    else:
        text = names[0] if names else ""
    return f'<p class="srcline">{text}</p>'


def source_list(ev):
    """Hela källistan på notissidan: namn, land, betalvägg, STAT."""
    items = []
    for s in ev["kallor"]:
        who = []
        if s.get("land"):
            who.append(_both(*country(s["land"])))
        if s.get("betalvagg"):
            who.append(_both("betalvägg", "paywall"))
        if s.get("tid"):
            who.append(stampel(s["tid"], kort=True))
        tail = f' <span class="who">{", ".join(who)}</span>' if who else ""
        stat = '<span class="stat">STAT</span>' if s.get("statskontrollerad") else ""
        items.append(f'<li><a href="{_e(s["url"])}" rel="noopener">{_e(s["namn"])}</a>{stat}{tail}</li>')
    return f'<ul class="srcfull">{"".join(items)}</ul>'


def _num(v, dec, lang):
    s = f"{v:.{dec}f}"
    return s.replace(".", ",") if lang == "sv" else s


def _spark(vals):
    if len(vals) < 2:
        return ""
    lo, hi = min(vals), max(vals)
    span = (hi - lo) or 1
    pts = " ".join(f"{i * 200 / (len(vals) - 1):.1f},{32 - (v - lo) / span * 28:.1f}" for i, v in enumerate(vals))
    x, y = pts.split(" ")[-1].split(",")
    return (f'<svg viewBox="0 0 200 34" preserveAspectRatio="none" aria-hidden="true">'
            f'<polyline points="{pts}" fill="none" stroke="currentColor" stroke-width="1.5" vector-effect="non-scaling-stroke"/>'
            f'<circle cx="{x}" cy="{y}" r="2.5" fill="currentColor"/></svg>')


def data_block(ev):
    items = ev.get("data") or []
    if not items:
        return ""
    cards = []
    for d in items:
        unit, dec, when = d["enhet"], d["decimaler"], d["datum"]
        now_sv, now_en = f'{_num(d["senaste"], dec, "sv")} {unit}', f'{_num(d["senaste"], dec, "en")} {unit}'
        was_sv = f'{when}, ett år tidigare {_num(d["ar_sedan"], dec, "sv")} {unit}. '
        was_en = f'{when}, a year earlier {_num(d["ar_sedan"], dec, "en")} {unit}. '
        cards.append(
            f'<div class="datum"><span class="k">{_both(d["namn_sv"], d["namn_en"])}</span>'
            f'<span class="v">{_both(now_sv, now_en)}</span>{_spark(d["spark"])}'
            f'<span class="s">{_both(was_sv, was_en)}<a href="{_e(d["url"])}" rel="noopener">{_e(d["kalla"])}</a></span></div>')
    return (f'<h3 class="section-h">{_both("Data bakom nyheten", "Data behind the news")}</h3>'
            f'<div class="data">{"".join(cards)}</div>')


# ---------- Notisen i olika storlekar ----------

def _title(ev):
    d = ev.get("utkast") or {}
    return _both(d.get("rubrik_sv") or ev["reserv_rubrik"], d.get("rubrik_en") or ev["reserv_rubrik"])


def _summary(ev):
    d = ev.get("utkast") or {}
    return f'<p class="sum">{_both(d["sammanfattning_sv"], d.get("sammanfattning_en"))}</p>' if d.get("sammanfattning_sv") else ""


def _disagreement(ev):
    d = ev.get("utkast") or {}
    if not d.get("oenighet"):
        return ""
    return f'<div class="dis"><b>{_both("Källorna skiljer sig åt.", "Sources differ.")}</b> {_both(d["oenighet"], d.get("oenighet_en"))}</div>'


def story_lead(ev, href, kicker=None):
    """Toppnotisen: rubrik, ingress, täckning, meta, oenighet, källor. kicker = (text, länk)."""
    k = f'<p class="kicker"><a href="{_e(kicker[1])}">{kicker[0]}</a></p>' if kicker else ""
    return (f'<article class="story lead">{k}<h2><a href="{_e(href)}">{_title(ev)}</a></h2>{_summary(ev)}'
            f'{coverage(ev)}{meta_block(ev)}{_disagreement(ev)}{source_sentence(ev, href)}</article>')


def story_featured(ev, href, kicker=""):
    """Utvald notis i ett sektionsblock."""
    k = f'<p class="kicker">{kicker}</p>' if kicker else ""
    return (f'<article class="story featured">{k}<h3><a href="{_e(href)}">{_title(ev)}</a></h3>{_summary(ev)}'
            f'{coverage(ev)}{meta_block(ev)}{source_sentence(ev, href)}</article>')


def story_item(ev, href, kicker=""):
    """Rad i en rubriklista."""
    k = f'<a href="{_e(kicker[1])}">{kicker[0]}</a> ' if kicker else ""
    return f'<li><h3><a href="{_e(href)}">{_title(ev)}</a></h3><p class="meta">{k}{_nar(ev) + ". " if _nar(ev) else ""}{meta_line(ev)}{". " + ai_marke(ev) if ai_marke(ev) else ""}</p></li>'


def narratives_block(ev):
    """Berättelserna (berattelser.py): tomt tills utvärderingen är gjord och NN_BERATTELSER=1, och bara om källkontrollen godkänt dem."""
    n = ev.get("narrativ")
    if os.environ.get("NN_BERATTELSER") != "1" or not n or not n.get("ok") or not n.get("berattelser"):
        return ""
    cols = []
    for b in n["berattelser"]:
        who = ", ".join(
            _e(k["namn"]) + (f' ({_both(*REGIONS.get(k["region"], (k["region"], k["region"])))}'
                             + (f', AllSides: {_both(*LEANS[k["lutning"]])}' if k.get("lutning") in LEANS else "")
                             + ("<span class=stat>STAT</span>" if k.get("statskontrollerad") else "") + ")")
            for k in b["kallor"])
        cols.append(f'<div class="region"><h4>{_both(b["namn_sv"], b["namn_en"])}</h4><p class="persp">{_both(b["lyfter_sv"], b["lyfter_en"])}</p>'
                    f'<p class="who">{_both("Bärs av", "Carried by")}: {who}</p></div>')
    return (f'<h3 class="section-h">{_both("Berättelserna", "The narratives")}</h3><div class="regions">{"".join(cols)}</div>'
            f'<p class="note">{_both("Grupperingen är gjord med hjälp av AI och kontrollerad mot källorna. Varje beskrivning gäller bara vad de namngivna källorna lyfter fram. Vi säger inte vilken berättelse som stämmer.", "The grouping is made with the help of AI and checked against the sources. Each description covers only what the named sources highlight. We do not say which narrative is right.")}</p>')


def betydelse_block(ev, lang=None):
    """Analys-raden (betydelse.py): efter fakta, märkt Analys, tom tills utvärderingen är gjord och NN_BETYDELSE=1, och bara om kontrollen godkänt den.
    Med `lang` visas bara det språkets rad; utan (den tvåspråkiga förhandsvisningen) visas båda med språkväxlaren."""
    b = ev.get("betydelse")
    if os.environ.get("NN_BETYDELSE") != "1" or not b or not b.get("ok"):
        return ""
    sv, en = b.get("sv"), b.get("en")
    if lang == "sv":
        en = None
    elif lang == "en":
        sv = None
    if not (sv or en):
        return ""
    text = (f'<span class="sv">{_e(sv)}</span>' if sv else "") + (f'<span class="en">{_e(en)}</span>' if en else "")
    rubrik = (f'<span class="sv">Analys</span>' if sv else "") + (f'<span class="en">Analysis</span>' if en else "")
    note = (f'<span class="sv">Det här är en bedömning, inte en nyhet. Raden är skriven med hjälp av AI, bygger på fakta ovan och kontrollerad mot källorna. Den innehåller inga råd och inga förutsägelser.</span>' if sv else "") + \
           (f'<span class="en">This is a judgement, not news. The line is written with the help of AI, builds on the facts above and is checked against the sources. It contains no advice and no predictions.</span>' if en else "")
    return f'<h3 class="section-h">{rubrik}</h3><p class="persp">{text}</p><p class="note">{note}</p>'


def _usa_relevant(ev):
    import utgava
    return utgava.usa_relevant(ev)


def story_full(ev, internal=False, lang=None, rubrik="h2"):
    """Hela notisen: notissidan och den interna förhandsvisningen."""
    d = ev.get("utkast") or {}
    p = ev.get("perspektiv") or {}
    regs = p.get("regioner", [])
    parts = [f'<{rubrik}>{_title(ev)}</{rubrik}>', _summary(ev), coverage(ev), meta_block(ev, internal, tid=False)]

    if len(regs) >= 2 or d.get("perspektiv_sv"):
        cols = []
        for r in regs:
            items = "".join(
                f'<li><a href="{_e(x["url"])}" rel="noopener">{_e(x["rubrik"])}</a>'
                f'<span class="who">{_e(x["kalla"])}{", " + _both(*country(x["land"])) if x.get("land") else ""}{_kalltid(x)}'
                f'{"<span class=stat>STAT</span>" if x.get("statskontrollerad") else ""}</span></li>'
                for x in p["per_region"][r])
            cols.append(f'<div class="region"><h4>{_both(*REGIONS.get(r, (r, r)))}</h4><ul>{items}</ul></div>')
        persp = f'<p class="persp">{_both(d["perspektiv_sv"], d.get("perspektiv_en"))}</p>' if d.get("perspektiv_sv") else ""
        parts.append(f'<h3 class="section-h">{_both("Så ser världen på det", "How the world sees it")}</h3>{persp}'
                     f'<div class="regions">{"".join(cols) if len(regs) >= 2 else ""}</div>')

    if _usa_relevant(ev):
        cols = []
        for key, sv, en in SIDES:
            items = p["usa"].get(key) or []
            lis = "".join(
                f'<li><a href="{_e(x["url"])}" rel="noopener">{_e(x["rubrik"])}</a>'
                f'<span class="who">{_e(x["kalla"])}, AllSides: {_both(*LEANS[x["lutning"]])}{_kalltid(x)}</span></li>' for x in items)
            cols.append(f'<div class="region"><h4>{_both(sv, en)}</h4><ul>{lis or "<li class=none>" + _both("Inga rubriker", "No headlines") + "</li>"}</ul></div>')
        txt = f'<p class="persp">{_both(d["usa_sv"], d.get("usa_en"))}</p>' if d.get("usa_sv") else ""
        parts.append(f'<h3 class="section-h">{_both("USA: blått och rött", "US: blue and red")}</h3>{coverage_usa(p)}{txt}'
                     f'<div class="regions" style="margin-top:18px">{"".join(cols)}</div>'
                     f'<p class="note">{_both("Indelningen bygger på AllSides betyg av medierna, inte på vår bedömning.", "Grouping based on AllSides ratings of the outlets, not our own judgement.")}</p>')

    parts.append(narratives_block(ev))

    dis = _disagreement(ev)
    if dis:
        parts.append(f'<h3 class="section-h">{_both("Källorna skiljer sig åt", "Sources differ")}</h3>'
                     + dis.replace(f'<b>{_both("Källorna skiljer sig åt.", "Sources differ.")}</b> ', ""))
    parts.append(data_block(ev))
    parts.append(f'<h3 class="section-h">{_both("Källor", "Sources")}</h3>{source_list(ev)}')

    k = ev.get("kallkontroll")
    if k and k.get("ok"):
        parts.append(f'<p class="check"><b>{_both("Maskinellt källkontrollerad.", "Machine source-checked.")}</b> '
                     f'{_both(f"Alla {k['antal']} påståenden i notisen går att spåra till källorna.", f"All {k['antal']} claims in this story can be traced to the sources.")}</p>')
    elif k and internal:
        n_issues = len(k.get("problem", []))
        parts.append(f'<p class="check"><b>{_both(f"Källkontroll: {n_issues} anmärkningar.", f"Source check: {n_issues} issues.")}</b> '
                     f'{_e(" ".join(k.get("problem", [])[:4]))}</p>')
    parts.append(betydelse_block(ev, lang))
    topics = " ".join(ev.get("amnen", []))
    return f'<article class="story single" data-t="{_e(topics)}" id="h-{ev["id"]}">{"".join(parts)}</article>'


# Bakåtkompatibelt namn
def _event(ev, lead, href=None):
    return story_lead(ev, href) if href else story_full(ev)


# ---------- Intern förhandsvisning av flödet (site/index.html) ----------

def render(payload, path, include_unreviewed=True):
    events = [e for e in payload["handelser"] if include_unreviewed or e.get("granskad")]
    for e in events:
        e["_over_sprak"] = payload.get("over_sprak")
    topics = []
    for e in events:
        for t in e.get("amnen", []):
            if t not in topics and t in TOPICS:
                topics.append(t)
    chips = [f'<button type="button" aria-pressed="true" data-t="alla">{_both("Alla", "All")}</button>'] + [
        f'<button type="button" aria-pressed="false" data-t="{t}">{_both(*TOPICS[t])}</button>' for t in topics[:12]]
    ok = sum(1 for r in payload["kallrapport"] if r["ok"])
    regions = {r for e in events for r in (e.get("perspektiv") or {}).get("regioner", [])}
    when = payload["skapad"][:16].replace("T", " ")
    empty = f'<p class="sum" style="padding:40px 0">{_both("Inga notiser än.", "No stories yet.")}</p>'
    body = "".join(story_full(e, internal=True) for e in events) or empty
    mode = _both("Intern förhandsvisning av ogranskade utkast", "Internal preview of unreviewed drafts") if include_unreviewed else \
        _both("Granskat och publicerat", "Reviewed and published")
    doc = f"""<!doctype html>
<html lang="sv"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Newsnavigator</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="stylesheet" href="{FONTS_URL}">
<style>{CSS}</style></head>
<body>
<header><div class="w mast">
<span class="date" data-date></span>
<a class="brand" href="#">{_mascot()}<span>Newsnavigator</span></a>
<div class="lang" role="group" aria-label="Språk"><button type="button" data-l="sv" aria-pressed="true">SV</button><button type="button" data-l="en" aria-pressed="false">EN</button></div>
</div></header>
<div class="w">
<div class="intro"><p>{mode}</p><span>{_e(when)} UTC, {ok} {_both("av", "of")} {len(payload["kallrapport"])} {_both("källor svarade", "sources answered")}, {len(regions)} {_both("regioner", "regions")}</span></div>
{'<div class="chips" role="group" aria-label="Ämnen">' + "".join(chips) + '</div>' if events else ""}
<main class="feed">{body}</main>
</div>
<script>{JS}</script>
</body></html>"""
    for e in events:
        e.pop("_over_sprak", None)
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(doc, encoding="utf-8")
