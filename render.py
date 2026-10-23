"""Bygger Newsnavigators flöde som en statisk sida i sajtens design (dark mode, svenska och engelska)."""
import html
import re
from pathlib import Path

ROOT = Path(__file__).parent

TOPICS = {"ai": ("AI", "AI"), "robotik": ("Robotik", "Robotics"), "marknader": ("Marknader", "Markets"),
          "varlden": ("Världen", "World"), "sverige": ("Sverige", "Sweden"), "europa": ("Europa", "Europe"),
          "geopolitik": ("Geopolitik", "Geopolitics"), "teknik": ("Teknik", "Tech"), "vetenskap": ("Vetenskap", "Science"),
          "rymd": ("Rymd", "Space"), "energi": ("Energi", "Energy"), "klimat": ("Klimat", "Climate"),
          "forsvar": ("Försvar", "Defence"), "startups": ("Startups", "Startups"), "halvledare": ("Halvledare", "Chips"),
          "norden": ("Norden", "Nordics"), "usa": ("USA", "US"), "asien": ("Asien", "Asia"),
          "mellanostern": ("Mellanöstern", "Middle East"), "afrika": ("Afrika", "Africa")}
REGIONS = {"sverige": ("Sverige", "Sweden"), "norden": ("Norden", "Nordics"), "europa": ("Europa", "Europe"),
           "usa": ("USA", "US"), "asien": ("Asien", "Asia"), "mellanostern": ("Mellanöstern", "Middle East"),
           "afrika": ("Afrika", "Africa"), "global": ("Global", "Global")}

CSS = """
:root{--bg:#0A0A0A;--fg:#F2F2F2;--body:#D8D8D8;--mut:#A3A3A3;--line:#2A2A2A;--card:#161616}
*{box-sizing:border-box}html{background:var(--bg)}body{margin:0;background:var(--bg);color:var(--fg);font-family:'Source Sans 3',system-ui,sans-serif;-webkit-font-smoothing:antialiased}
a{color:var(--fg)}a:hover{color:#fff}
.w{max-width:1120px;margin:0 auto;padding:0 20px}
.mono{font-family:'IBM Plex Mono',ui-monospace,monospace;font-size:12px;letter-spacing:.06em;text-transform:uppercase;color:var(--mut)}
header{border-bottom:1px solid var(--fg)}
.hd .mono{flex:1 1 260px;min-width:0;overflow-wrap:anywhere}
.hd{display:flex;flex-wrap:wrap;align-items:center;justify-content:space-between;gap:12px 24px;padding:12px 0}
.brand{display:flex;align-items:center;gap:12px;text-decoration:none;min-height:44px}
.brand svg{height:56px;width:auto;display:block}
.brand span{font-size:28px;font-weight:800;letter-spacing:-.03em}
.lang{display:flex}.lang button{height:44px;padding:0 10px;border:0;border-bottom:2px solid transparent;background:none;color:var(--mut);font:600 12px 'IBM Plex Mono',monospace;letter-spacing:.06em;cursor:pointer}
.lang button[aria-pressed=true]{color:var(--fg);border-bottom-color:var(--fg)}
.intro{border-bottom:1px solid var(--line);padding:14px 0;display:flex;flex-wrap:wrap;justify-content:space-between;gap:8px 24px}
.intro p{margin:0;font-family:'Source Serif 4',Georgia,serif;font-style:italic;font-size:17px;color:var(--body);max-width:62ch}
.chips{display:flex;flex-wrap:wrap;gap:6px;padding:16px 0 4px}
.chips button{min-height:40px;padding:0 14px;border:1px solid #444;border-radius:999px;background:none;color:var(--fg);font:500 14px 'Source Sans 3',sans-serif;cursor:pointer}
.chips button[aria-pressed=true]{background:var(--fg);color:var(--bg);border-color:var(--fg)}
.ev{border-top:1px solid var(--line);padding:24px 0;display:grid;grid-template-columns:minmax(0,1fr);gap:10px}
.ev.lead h2{font-size:44px;line-height:1.05}
.ev h2{margin:0;font-family:'Source Serif 4',Georgia,serif;font-weight:600;font-size:27px;line-height:1.15;letter-spacing:-.01em;max-width:28ch}
.ev .sum{margin:0;font-family:'Source Serif 4',Georgia,serif;font-size:18px;line-height:1.55;color:var(--body);max-width:68ch}
.badges{display:flex;flex-wrap:wrap;gap:6px}
.badge{font:600 11px 'IBM Plex Mono',monospace;letter-spacing:.06em;text-transform:uppercase;border:1px solid #555;color:var(--mut);padding:3px 7px}
.badge.strong{border-color:var(--fg);color:var(--fg)}
details{background:var(--card);padding:0 18px;max-width:820px}
details summary{cursor:pointer;min-height:48px;display:flex;align-items:center;font-weight:600;font-size:15px}
details[open]{padding-bottom:16px}
.persp{font-family:'Source Serif 4',Georgia,serif;font-size:16px;line-height:1.55;color:var(--body);margin:0 0 14px}
.regions{display:grid;grid-template-columns:repeat(auto-fill,minmax(240px,1fr));gap:14px}
.region h4{margin:0 0 6px;font:600 12px 'IBM Plex Mono',monospace;letter-spacing:.08em;text-transform:uppercase}
.region ul{list-style:none;margin:0;padding:0;display:flex;flex-direction:column;gap:8px}
.region li{font-size:14px;line-height:1.4}.region li .who{display:block;color:var(--mut);font-size:12px}
.dis{border-left:2px solid var(--fg);padding-left:12px;font-size:15px;line-height:1.5;color:var(--body);max-width:820px}
.src{font-size:14px;color:var(--mut);line-height:1.6;max-width:820px}.src a{color:var(--fg)}
.state{font:600 10px 'IBM Plex Mono',monospace;border:1px solid var(--fg);padding:1px 4px;margin-left:4px;letter-spacing:.04em}
footer{border-top:1px solid var(--line);margin-top:40px;padding:24px 0 40px;display:flex;flex-wrap:wrap;justify-content:space-between;gap:16px}
footer p{margin:0;max-width:60ch;font-size:14px;line-height:1.5;color:var(--mut)}
body.en .sv,body:not(.en) .en{display:none}
.hidden{display:none}
@media (max-width:600px){.ev.lead h2{font-size:32px}.ev h2{font-size:23px}.brand svg{height:44px}.brand span{font-size:22px}}
"""

JS = """
(function(){
  var b=document.body, btns=document.querySelectorAll('.lang button');
  function setLang(l){b.classList.toggle('en',l==='en');document.documentElement.lang=l;
    btns.forEach(function(x){x.setAttribute('aria-pressed',x.dataset.l===l)});
    try{localStorage.setItem('nn-lang',l)}catch(e){}}
  btns.forEach(function(x){x.addEventListener('click',function(){setLang(x.dataset.l)})});
  try{var s=localStorage.getItem('nn-lang');if(s)setLang(s)}catch(e){}
  var chips=document.querySelectorAll('.chips button'), evs=document.querySelectorAll('.ev');
  chips.forEach(function(c){c.addEventListener('click',function(){
    chips.forEach(function(x){x.setAttribute('aria-pressed',x===c)});
    var t=c.dataset.t; evs.forEach(function(e){e.classList.toggle('hidden',t!=='alla'&&e.dataset.t.split(' ').indexOf(t)<0)});
  })});
})();
"""


def _e(s):
    return html.escape(s or "", quote=True)


def _both(sv, en):
    sv, en = _e(sv), _e(en or sv)
    return sv if sv == en else f'<span class="sv">{sv}</span><span class="en">{en}</span>'


def _mascot():
    p = ROOT / "assets" / "newsgator.svg"
    if not p.exists():
        return ""
    svg = p.read_text(encoding="utf-8")
    return re.sub(r"<svg ", '<svg role="img" aria-label="Newsgator" ', svg, count=1)


def _event(ev, lead):
    d = ev.get("utkast") or {}
    p = ev.get("perspektiv") or {}
    regs = p.get("regioner", [])
    topics = ev.get("amnen", [])
    label_sv = " · ".join(TOPICS.get(t, (t, t))[0] for t in topics[:3])
    label_en = " · ".join(TOPICS.get(t, (t, t))[1] for t in topics[:3])
    n = ev["antal_kallor"]
    meta = (f'<div class="mono">{_both(label_sv, label_en)} · {n} {_both("källor", "sources")}'
            f' · {len(regs)} {_both("regioner", "regions")}</div>')

    badges = []
    if not ev.get("granskad"):
        badges.append(f'<span class="badge">{_both("Ej granskad", "Not reviewed")}</span>')
    if d.get("osaker"):
        badges.append(f'<span class="badge">{_both("Tunt underlag", "Thin sourcing")}</span>')
    if ev.get("har_primarkalla"):
        badges.append(f'<span class="badge">{_both("Primärkälla", "Primary source")}</span>')
    blind = p.get("blind_flack")
    if blind == "saknas_i_sverige" and ev.get("_over_sprak"):
        badges.append(f'<span class="badge strong">{_both("Saknas i svenska medier", "Not in Swedish media")}</span>')
    elif blind == "bara_i_sverige":
        badges.append(f'<span class="badge strong">{_both("Bara i svenska medier", "Only in Swedish media")}</span>')

    title = _both(d.get("rubrik_sv") or ev["reserv_rubrik"], d.get("rubrik_en") or ev["reserv_rubrik"])
    summary = ""
    if d.get("sammanfattning_sv"):
        summary = f'<p class="sum">{_both(d["sammanfattning_sv"], d.get("sammanfattning_en"))}</p>'

    world = ""
    if len(regs) >= 2:
        cols = []
        for r in regs:
            items = "".join(
                f'<li><a href="{_e(x["url"])}" rel="noopener">{_e(x["rubrik"])}</a>'
                f'<span class="who">{_e(x["kalla"])}{" (" + _e(x["land"]) + ")" if x.get("land") else ""}'
                f'{"<span class=state>STAT</span>" if x.get("statskontrollerad") else ""}</span></li>'
                for x in p["per_region"][r])
            cols.append(f'<div class="region"><h4>{_both(*REGIONS.get(r, (r, r)))}</h4><ul>{items}</ul></div>')
        persp = f'<p class="persp">{_both(d["perspektiv_sv"], d.get("perspektiv_en"))}</p>' if d.get("perspektiv_sv") else ""
        world = (f'<details><summary>{_both("Så ser världen på det", "How the world sees it")} '
                 f'&nbsp;<span class="mono">{len(regs)} {_both("regioner", "regions")}</span></summary>'
                 f'{persp}<div class="regions">{"".join(cols)}</div></details>')

    dis = f'<div class="dis"><b>{_both("Källorna skiljer sig åt:", "Sources differ:")}</b> {_both(d["oenighet"], d.get("oenighet_en"))}</div>' \
        if d.get("oenighet") else ""
    srcs = ", ".join(
        f'<a href="{_e(s["url"])}" rel="noopener">{_e(s["namn"])}</a>'
        + (f' ({_e(s["land"])})' if s.get("land") else "")
        + ('<span class="state">STAT</span>' if s.get("statskontrollerad") else "")
        + (f' <span class="mono">{_both("betalvägg", "paywall")}</span>' if s.get("betalvagg") else "")
        for s in ev["kallor"])
    return (f'<article class="ev{" lead" if lead else ""}" data-t="{_e(" ".join(topics))}" id="h-{ev["id"]}">'
            f'{meta}<h2>{title}</h2>{summary}'
            f'{"<div class=badges>" + "".join(badges) + "</div>" if badges else ""}'
            f'{world}{dis}<div class="src">{_both("Källor", "Sources")}: {srcs}</div></article>')


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
    body = "".join(_event(e, i == 0) for i, e in enumerate(events)) or \
        f'<p class="sum" style="padding:40px 0">{_both("Inga godkända notiser än.", "No approved stories yet.")}</p>'
    mode = _both("Förhandsvisning: ogranskade utkast", "Preview: unreviewed drafts") if include_unreviewed else \
        _both("Granskat och publicerat", "Reviewed and published")
    doc = f"""<!doctype html>
<html lang="sv"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Newsnavigator</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Source+Serif+4:ital,opsz,wght@0,8..60,400..700;1,8..60,400..700&family=Source+Sans+3:wght@400;500;600;700;800&family=IBM+Plex+Mono:wght@400;600&display=swap">
<style>{CSS}</style></head>
<body>
<header><div class="w hd">
<a class="brand" href="#">{_mascot()}<span>Newsnavigator</span></a>
<div class="mono">{_e(when)} UTC · {ok}/{len(payload["kallrapport"])} {_both("källor", "sources")} · {len(regions)} {_both("regioner", "regions")}</div>
<div class="lang" role="group" aria-label="Språk"><button type="button" data-l="sv" aria-pressed="true">SV</button><button type="button" data-l="en" aria-pressed="false">EN</button></div>
</div></header>
<div class="w">
<div class="intro"><p>{_both("Vi levererar nyheterna. Vad du gör av dem är upp till dig.", "We deliver the news. What you make of it is up to you.")}</p>
<span class="mono">{mode}</span></div>
<div class="chips" role="group" aria-label="Ämnen">{"".join(chips)}</div>
<main>{body}</main>
<footer><p>{_both("Notiserna sammanfattas med hjälp av AI och granskas av redaktionen innan publicering. Varje notis länkar till originalkällorna. Statskontrollerade medier är märkta STAT. Ansvarig utgivare: Fabian Sandberg Kuylenstierna.", "Stories are summarised with the help of AI and reviewed by the editors before publication. Every story links to its original sources. State-controlled media are marked STAT. Publisher: Fabian Sandberg Kuylenstierna.")}</p>
<span class="mono">© 2026 Newsnavigator</span></footer>
</div>
<script>{JS}</script>
</body></html>"""
    for e in events:
        e.pop("_over_sprak", None)
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(doc, encoding="utf-8")
