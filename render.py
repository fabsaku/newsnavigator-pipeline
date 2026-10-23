"""Bygger en förhandsvisning av flödet som statisk HTML i dark mode."""
import html
from pathlib import Path

LABELS = {"ai": "AI", "robotik": "Robotik", "marknader": "Marknader", "varlden": "Världen", "sverige": "Sverige",
          "europa": "Europa", "geopolitik": "Geopolitik", "teknik": "Teknik", "vetenskap": "Vetenskap",
          "rymd": "Rymd", "energi": "Energi", "klimat": "Klimat", "forsvar": "Försvar", "startups": "Startups",
          "halvledare": "Halvledare", "norden": "Norden", "usa": "USA", "asien": "Asien",
          "mellanostern": "Mellanöstern", "afrika": "Afrika"}
REGIONS = {"sverige": "Sverige", "norden": "Norden", "europa": "Europa", "usa": "USA", "asien": "Asien",
           "mellanostern": "Mellanöstern", "afrika": "Afrika", "global": "Global"}

CSS = """
:root{--bg:#0A0A0A;--fg:#F2F2F2;--mut:#A3A3A3;--line:#2A2A2A;--card:#161616}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);font-family:'Source Sans 3',system-ui,sans-serif}
a{color:var(--fg)}.w{max-width:820px;margin:0 auto;padding:24px 16px 64px}
h1{font-family:'Source Serif 4',Georgia,serif;font-size:40px;margin:0 0 4px}
.mono{font-family:'IBM Plex Mono',monospace;font-size:12px;letter-spacing:.06em;text-transform:uppercase;color:var(--mut)}
.ev{border-top:1px solid var(--line);padding:20px 0;display:flex;flex-direction:column;gap:8px}
.ev h2{font-family:'Source Serif 4',Georgia,serif;font-size:24px;line-height:1.2;margin:0}
.ev p{margin:0;font-family:'Source Serif 4',Georgia,serif;font-size:17px;line-height:1.5;color:#D6D6D6}
.flag{display:inline-block;border:1px solid var(--mut);padding:2px 6px;margin-right:6px}
.src{font-size:14px;color:var(--mut)}.src a{color:var(--fg)}
.note{background:var(--card);padding:16px;font-size:14px;color:var(--mut);margin:16px 0}
.dis{border-left:2px solid var(--fg);padding-left:12px;font-size:15px;color:#D6D6D6}
.world{background:var(--card);padding:12px 16px}.world summary{cursor:pointer;font-weight:600;min-height:32px}
.world ul{list-style:none;margin:8px 0 0;padding:0;display:flex;flex-direction:column;gap:10px}.world li{font-size:15px}
"""


def _e(s):
    return html.escape(s or "")


def render(payload, path, include_unreviewed=True):
    rows = []
    for ev in payload["handelser"]:
        if not include_unreviewed and not ev["granskad"]:
            continue
        d = ev.get("utkast") or {}
        title = d.get("rubrik_sv") or ev["reserv_rubrik"]
        flags = []
        if not ev["granskad"]:
            flags.append("Ej granskad")
        if not d.get("sammanfattning_sv"):
            flags.append("Ingen AI-sammanfattning")
        if d.get("osaker"):
            flags.append("Osäker")
        topics = " · ".join(LABELS.get(t, t) for t in ev["amnen"][:3])
        srcs = ", ".join(
            f'<a href="{_e(s["url"])}" rel="noopener">{_e(s["namn"])}</a>'
            + (f' ({_e(s.get("land", ""))})' if s.get("land") else "")
            + (' <span class="flag">Statskontrollerat</span>' if s.get("statskontrollerad") else "")
            + (" (betalvägg)" if s["betalvagg"] else "")
            for s in ev["kallor"])
        p = ev.get("perspektiv") or {}
        if p.get("blind_flack") == "saknas_i_sverige":
            flags.append("Saknas i svenska medier")
        elif p.get("blind_flack") == "bara_i_sverige":
            flags.append("Bara i svenska medier")
        world = ""
        if len(p.get("regioner", [])) >= 2:
            parts = []
            for reg in p["regioner"]:
                for x in p["per_region"][reg]:
                    tag = " · statskontrollerat" if x["statskontrollerad"] else ""
                    parts.append(f'<li><span class="mono">{_e(REGIONS.get(reg, reg))}, {_e(x["kalla"])}{tag}</span><br>'
                                 f'<a href="{_e(x["url"])}" rel="noopener">{_e(x["rubrik"])}</a></li>')
            world = f'<details class="world"><summary>Så ser världen på det ({len(p["regioner"])} regioner)</summary><ul>{"".join(parts)}</ul></details>'
        rows.append(f"""<article class="ev">
<div class="mono">{_e(topics)} · {ev['antal_kallor']} källor{' · primärkälla' if ev['har_primarkalla'] else ''}</div>
<h2>{_e(title)}</h2>
{f'<p>{_e(d["sammanfattning_sv"])}</p>' if d.get("sammanfattning_sv") else ''}
{f'<div class="dis">Källorna skiljer sig åt: {_e(d["oenighet"])}</div>' if d.get("oenighet") else ''}
{f'<div class="dis">Perspektiv: {_e(d["perspektiv_sv"])}</div>' if d.get("perspektiv_sv") else ''}
{world}
<div class="src">Källor: {srcs}</div>
<div class="mono">{''.join(f'<span class="flag">{f}</span>' for f in flags)}ID {ev['id']}</div>
</article>""")
    ok = sum(1 for r in payload["kallrapport"] if r["ok"])
    doc = f"""<!doctype html><html lang="sv"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Newsnavigator flöde</title>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Source+Serif+4:opsz,wght@8..60,400..700&family=Source+Sans+3:wght@400;600&family=IBM+Plex+Mono:wght@400;600&display=swap">
<style>{CSS}</style></head><body><div class="w">
<h1>Newsnavigator</h1>
<div class="mono">Förhandsvisning av flödet · skapad {_e(payload['skapad'][:16].replace('T', ' '))} UTC · {ok}/{len(payload['kallrapport'])} källor</div>
<div class="note">Notiserna sammanfattas med hjälp av AI och granskas av redaktionen innan publicering. Varje notis länkar till originalkällorna. Vi levererar nyheterna, vad du gör av dem är upp till dig.</div>
{''.join(rows) or '<p>Inga händelser.</p>'}
</div></body></html>"""
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(doc, encoding="utf-8")
