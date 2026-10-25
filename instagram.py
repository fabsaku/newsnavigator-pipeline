#!/usr/bin/env python3
"""Instagram: bildkort (karusell) av granskade notiser, och publicering via Instagrams API.

  python instagram.py bygg                 gör kort för godkända notiser som saknar kort -> public/ig/<id>/N.jpg + caption.txt
  python instagram.py posta [--antal 1]    publicerar de bästa opostade notiserna från senaste dygnet (kräver IG_USER_ID och IG_ACCESS_TOKEN)
  python instagram.py forhandsvisning DIR  gör kort av dagens utkast (ogranskade, märkta) för att se formatet

Korten är 1080x1350 (4:5), svartvita, i sajtens typografi. Bara rubrik, vår sammanfattning, perspektiv och
källornas namn: aldrig källornas text. Bilderna hämtas av Instagram från sajten, så de måste ligga ute först.
Status sparas i data/instagram.json.
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

from newsletter import load_archive, section_of, SECTIONS
from render import REGIONS, LEANS

ROOT = Path(__file__).parent
OUT = ROOT / "public" / "ig"
STATE = ROOT / "data" / "instagram.json"
SITE_URL = os.environ.get("NN_SITE_URL", "https://newsnavigator.se").rstrip("/")
IMAGE_BASE = os.environ.get("IG_IMAGE_BASE", "https://newsnavigator.pages.dev").rstrip("/")
GRAPH = os.environ.get("IG_GRAPH", "https://graph.instagram.com").rstrip("/")
TZ = ZoneInfo("Europe/Stockholm")
MONTHS = ["januari", "februari", "mars", "april", "maj", "juni", "juli", "augusti", "september", "oktober", "november", "december"]
HASHTAGS = {"varlden": "#omvärlden #utrikes", "sverige": "#sverige #inrikes", "marknader": "#ekonomi #marknader #börsen",
            "tech": "#teknik #ai", "vetenskap": "#vetenskap #forskning"}


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
@font-face{{font-family:'SS4';src:url({_font('source-serif-4-latin-400-italic.woff2')});font-weight:400;font-style:italic}}
@font-face{{font-family:'SS3';src:url({_font('source-sans-3-latin-400-normal.woff2')});font-weight:400}}
@font-face{{font-family:'SS3';src:url({_font('source-sans-3-latin-600-normal.woff2')});font-weight:600}}
@font-face{{font-family:'SS3';src:url({_font('source-sans-3-latin-800-normal.woff2')});font-weight:800}}
@font-face{{font-family:'IPM';src:url({_font('ibm-plex-mono-latin-400-normal.woff2')});font-weight:400}}
@font-face{{font-family:'IPM';src:url({_font('ibm-plex-mono-latin-600-normal.woff2')});font-weight:600}}
*{{box-sizing:border-box;margin:0}}
html,body{{width:1080px;height:1350px;background:#0A0A0A;color:#F2F2F2;font-family:'SS3',sans-serif;-webkit-font-smoothing:antialiased}}
.card{{width:1080px;height:1350px;padding:64px 72px 60px;display:flex;flex-direction:column;overflow:hidden;position:relative}}
.top{{display:flex;align-items:center;justify-content:space-between;padding-bottom:22px;border-bottom:2px solid #F2F2F2}}
.brand{{display:flex;align-items:center;gap:18px}}.brand img{{height:76px;width:auto}}.brand span{{font-weight:800;font-size:31px;letter-spacing:.09em;text-transform:uppercase}}
.mono{{font-family:'IPM',monospace;font-size:21px;letter-spacing:.08em;text-transform:uppercase;color:#A3A3A3}}
.label{{margin:40px 0 22px;display:flex;justify-content:space-between;gap:20px}}
h1{{font-family:'SS4',serif;font-weight:600;line-height:1.06;letter-spacing:-.012em;text-wrap:balance}}
.sum{{font-family:'SS4',serif;font-style:italic;font-weight:400;font-size:36px;line-height:1.4;color:#D8D8D8;margin-top:30px}}
.body{{font-size:33px;line-height:1.42;color:#E6E6E6}}
.clamp{{display:-webkit-box;-webkit-box-orient:vertical;overflow:hidden}}
.grow{{flex:1}}
.foot{{display:flex;justify-content:space-between;align-items:flex-end;gap:20px;padding-top:22px;border-top:1px solid #2A2A2A}}
.foot .site{{font-weight:800;font-size:28px;letter-spacing:-.02em}}
.h2{{font-family:'SS4',serif;font-weight:600;font-size:54px;line-height:1.1;margin-bottom:26px}}
.regions{{display:grid;grid-template-columns:1fr 1fr;gap:28px 36px;margin-top:34px}}
.region .mono{{display:block;margin-bottom:10px;color:#F2F2F2}}
.region p{{font-size:27px;line-height:1.3;margin-bottom:10px}}
.region p>span:last-child{{display:block;font-size:21px;color:#A3A3A3;margin-top:2px}}
.cols{{display:grid;grid-template-columns:1fr 1fr 1fr;gap:28px;margin-top:34px}}
.col .mono{{display:block;color:#F2F2F2;margin-bottom:10px;padding-bottom:8px;border-bottom:1px solid #444}}
.col p{{font-size:25px;line-height:1.3;margin-bottom:10px}}.col p>span:last-child{{display:block;font-size:19px;color:#A3A3A3}}
.quote{{border-left:4px solid #F2F2F2;padding-left:28px;font-size:34px;line-height:1.4;color:#E6E6E6}}
.srcs{{columns:2;column-gap:40px;font-size:29px;line-height:1.5}}
.srcs div{{break-inside:avoid;padding:8px 0;border-bottom:1px solid #2A2A2A}}
.srcs .c{{font-family:'IPM',monospace;font-size:19px;color:#A3A3A3;margin-left:10px}}
.state{{font-family:'IPM',monospace;font-size:17px;border:1px solid #F2F2F2;padding:1px 6px;margin-left:8px;vertical-align:middle}}
.princip{{font-family:'SS4',serif;font-style:italic;font-size:38px;line-height:1.35;color:#F2F2F2}}
.swipe{{font-family:'IPM',monospace;font-size:21px;letter-spacing:.08em;color:#A3A3A3;text-transform:uppercase}}
.banner{{position:absolute;left:0;right:0;top:0;background:#F2F2F2;color:#0A0A0A;font-family:'IPM',monospace;font-size:20px;letter-spacing:.08em;text-transform:uppercase;text-align:center;padding:8px}}
"""


def _e(s):
    import html
    return html.escape(s or "", quote=True)


def _date(ts):
    d = datetime.fromtimestamp(ts, timezone.utc).astimezone(TZ)
    return f"{d.day} {MONTHS[d.month - 1]} {d.year}"


def _headline_size(text):
    n = len(text or "")
    return 82 if n <= 48 else 70 if n <= 75 else 60 if n <= 105 else 52


def _top(section_sv, date_sv):
    return (f'<div class="top"><div class="brand"><img src="{_logo()}" alt=""><span>Newsnavigator</span></div>'
            f'<div class="mono">{_e(date_sv)}</div></div>')


def _page(inner, banner=""):
    return (f'<!doctype html><html lang="sv"><head><meta charset="utf-8"><style>{_css()}</style></head><body>'
            f'<div class="card">{f"<div class=banner>{_e(banner)}</div>" if banner else ""}{inner}</div></body></html>')


def slides(ev, banner=""):
    """HTML för varje kort i karusellen."""
    d = ev.get("utkast") or {}
    p = ev.get("perspektiv") or {}
    sec_sv = next((sv for k, sv, _, _ in SECTIONS if k == section_of(ev)), "Världen")
    date = _date(ev.get("godkand_tid") or time.time())
    title = d.get("rubrik_sv") or ev["reserv_rubrik"]
    n_src, regs = ev["antal_kallor"], p.get("regioner", [])
    foot = (f'<div class="foot"><div class="mono" style="text-transform:none;letter-spacing:0;font-size:20px">Sammanfattad med hjälp av AI · granskad av redaktionen</div>'
            f'<div class="site">newsnavigator.se</div></div>')
    meta = f'{n_src} källor · {len(regs)} regioner'
    out = []

    # 1. Omslag
    swipe = '<div class="swipe">Svep för att se hur världen rapporterar →</div>' if len(regs) >= 2 or p.get("usa") else ""
    out.append(_page(_top(sec_sv, date) + f'<div class="label"><span class="mono">{_e(sec_sv)}</span><span class="mono">{meta}</span></div>'
                     f'<h1 style="font-size:{_headline_size(title)}px">{_e(title)}</h1>'
                     + (f'<p class="sum clamp" style="-webkit-line-clamp:7">{_e(d["sammanfattning_sv"])}</p>' if d.get("sammanfattning_sv") else "")
                     + f'<div class="grow"></div>{swipe}<div style="height:18px"></div>{foot}', banner))

    # 2. Så ser världen på det
    if len(regs) >= 2:
        blocks = []
        for r in regs[:4]:
            items = p["per_region"].get(r, [])[:2]
            lines = "".join(f'<p><span class="clamp" style="-webkit-line-clamp:2;display:-webkit-box">{_e(x["rubrik"])}</span><span>{_e(x["kalla"])}'
                            f'{"<span class=state>STAT</span>" if x.get("statskontrollerad") else ""}</span></p>' for x in items)
            blocks.append(f'<div class="region"><span class="mono">{_e(REGIONS.get(r, (r, r))[0])}</span>{lines}</div>')
        persp = f'<p class="body clamp" style="-webkit-line-clamp:6">{_e(d["perspektiv_sv"])}</p>' if d.get("perspektiv_sv") else ""
        out.append(_page(_top(sec_sv, date) + f'<div class="label"><span class="mono">Så ser världen på det</span><span class="mono">{len(regs)} regioner</span></div>'
                         f'<div class="h2">Samma händelse, {len(regs)} regioner</div>{persp}<div class="regions">{"".join(blocks)}</div>'
                         f'<div class="grow"></div>{foot}', banner))

    # 3. USA: blått och rött
    usa = p.get("usa")
    if usa and d.get("usa_sv"):
        cols = []
        for key, name in (("bla", "Blå publik"), ("mitten", "Mitten"), ("rod", "Röd publik")):
            items = (usa.get(key) or [])[:2]
            lines = "".join(f'<p><span class="clamp" style="-webkit-line-clamp:3;display:-webkit-box">{_e(x["rubrik"])}</span><span>{_e(x["kalla"])} · {_e(LEANS[x["lutning"]][0])}</span></p>' for x in items) \
                or '<p style="color:#A3A3A3">Inga rubriker</p>'
            cols.append(f'<div class="col"><span class="mono">{name}</span>{lines}</div>')
        out.append(_page(_top(sec_sv, date) + f'<div class="label"><span class="mono">USA: blått och rött</span><span class="mono">AllSides</span></div>'
                         f'<p class="body clamp" style="-webkit-line-clamp:7">{_e(d["usa_sv"])}</p><div class="cols">{"".join(cols)}</div>'
                         f'<div class="grow"></div><div class="mono" style="text-transform:none;letter-spacing:0;font-size:19px">Indelningen bygger på AllSides betyg av medierna, inte på vår bedömning.</div><div style="height:18px"></div>{foot}', banner))

    # 4. Källorna skiljer sig åt
    if d.get("oenighet"):
        out.append(_page(_top(sec_sv, date) + f'<div class="label"><span class="mono">Källorna skiljer sig åt</span></div>'
                         f'<div class="h2">Uppgifterna går isär</div><div class="quote clamp" style="-webkit-line-clamp:12">{_e(d["oenighet"])}</div>'
                         f'<div class="grow"></div>{foot}', banner))

    # 5. Källor och princip
    srcs = "".join(f'<div>{_e(s["namn"])}<span class="c">{_e(s.get("land", ""))}</span>'
                   f'{"<span class=state>STAT</span>" if s.get("statskontrollerad") else ""}</div>' for s in ev["kallor"][:12])
    more = f'<div class="mono" style="margin-top:14px">och {len(ev["kallor"]) - 12} till</div>' if len(ev["kallor"]) > 12 else ""
    out.append(_page(_top(sec_sv, date) + f'<div class="label"><span class="mono">Källor</span><span class="mono">{n_src} oberoende källor</span></div>'
                     f'<div class="srcs">{srcs}</div>{more}<div class="grow"></div>'
                     f'<p class="princip">Vi levererar nyheterna. Vad du gör av dem är upp till dig.</p>'
                     f'<p class="mono" style="margin-top:22px;text-transform:none;letter-spacing:0;font-size:21px">Hela notisen, med länkar till varje källa, finns på newsnavigator.se</p>'
                     f'<div style="height:18px"></div>{foot}', banner))
    return out


def caption(ev):
    d = ev.get("utkast") or {}
    p = ev.get("perspektiv") or {}
    sec = section_of(ev)
    parts = [d.get("rubrik_sv") or ev["reserv_rubrik"], ""]
    if d.get("sammanfattning_sv"):
        parts += [d["sammanfattning_sv"], ""]
    if d.get("perspektiv_sv") and len(p.get("regioner", [])) >= 2:
        parts += ["Så ser världen på det: " + d["perspektiv_sv"], ""]
    if d.get("oenighet"):
        parts += ["Källorna skiljer sig åt: " + d["oenighet"], ""]
    names = [s["namn"] + (" (statskontrollerat)" if s.get("statskontrollerad") else "") for s in ev["kallor"][:8]]
    parts += ["Källor: " + ", ".join(names) + (f" och {len(ev['kallor']) - 8} till" if len(ev["kallor"]) > 8 else ""), ""]
    parts += [f"Hela notisen med alla länkar: {SITE_URL}/n/{ev['id']}/", ""]
    if d.get("rubrik_en"):
        parts += ["In English: " + d["rubrik_en"], ""]
    parts += ["Sammanfattad med hjälp av AI och granskad av redaktionen. Vi levererar nyheterna. Vad du gör av dem är upp till dig.", "",
              f"#nyheter #newsnavigator {HASHTAGS.get(sec, '')} #sammanhang #källor".strip()]
    text = "\n".join(parts)
    return text[:2190]


# ---------- Rendering ----------

def _browser(p):
    try:
        return p.chromium.launch(channel="chrome")
    except Exception:
        return p.chromium.launch()


def render(ev, out_dir, banner=""):
    from playwright.sync_api import sync_playwright
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    for old in out_dir.glob("*.jpg"):
        old.unlink()
    files = []
    with sync_playwright() as p:
        b = _browser(p)
        pg = b.new_page(viewport={"width": 1080, "height": 1350}, device_scale_factor=1)
        for i, html_ in enumerate(slides(ev, banner), 1):
            pg.set_content(html_, wait_until="load")
            pg.wait_for_timeout(150)
            f = out_dir / f"{i}.jpg"
            pg.screenshot(path=str(f), type="jpeg", quality=92)
            files.append(f.name)
        b.close()
    (out_dir / "caption.txt").write_text(caption(ev), encoding="utf-8")
    return files


def load_state():
    try:
        return json.loads(STATE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def save_state(s):
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(s, ensure_ascii=False, indent=1), encoding="utf-8")


def bygg():
    """Kort för alla godkända notiser i arkivet som saknar kort. Tar bort kort för notiser som lämnat arkivet."""
    arkiv, state = load_archive(), load_state()
    made = 0
    for sid, ev in arkiv.items():
        if sid in state and (OUT / sid / "1.jpg").exists():
            continue
        try:
            files = render(ev, OUT / sid)
        except Exception as e:
            print(f"Instagram: kunde inte göra kort för {sid}: {e}", file=sys.stderr)
            continue
        state[sid] = {**state.get(sid, {}), "skapad": time.time(), "bilder": files, "poang": ev.get("poang", 0),
                      "godkand_tid": ev.get("godkand_tid", 0), "rubrik": (ev.get("utkast") or {}).get("rubrik_sv") or ev["reserv_rubrik"]}
        made += 1
    if OUT.exists():
        for d in OUT.iterdir():
            if d.is_dir() and d.name not in arkiv:
                for f in d.iterdir():
                    f.unlink()
                d.rmdir()
    for sid in [k for k in state if k not in arkiv and not state[k].get("postad")]:
        state.pop(sid)
    save_state(state)
    print(f"Instagram: {made} nya kort, {len(state)} i kön")


# ---------- Publicering ----------

def _api(path, params, method="POST"):
    if method == "GET":
        req = urllib.request.Request(f"{GRAPH}/{path}?{urllib.parse.urlencode(params)}")
    else:
        req = urllib.request.Request(f"{GRAPH}/{path}", data=urllib.parse.urlencode(params).encode(), method="POST")
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read())


def publish_one(sid, item, user, token):
    urls = [f"{IMAGE_BASE}/ig/{sid}/{f}" for f in item["bilder"]]
    cap = (OUT / sid / "caption.txt").read_text(encoding="utf-8")
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


def posta(antal=1, hours=36):
    user, token = os.environ.get("IG_USER_ID"), os.environ.get("IG_ACCESS_TOKEN")
    state = load_state()
    since = time.time() - hours * 3600
    queue = sorted((sid for sid, it in state.items() if not it.get("postad") and it.get("godkand_tid", 0) >= since),
                   key=lambda sid: state[sid].get("poang", 0), reverse=True)[:antal]
    if not queue:
        print("Instagram: inget nytt att posta")
        return
    for sid in queue:
        if not (user and token):
            print(f"Instagram: skulle posta {sid}: {state[sid]['rubrik'][:70]} (IG_USER_ID/IG_ACCESS_TOKEN saknas)")
            continue
        try:
            media_id = publish_one(sid, state[sid], user, token)
            state[sid].update({"postad": time.time(), "ig_id": media_id})
            print(f"Instagram: postade {sid} ({media_id})")
        except Exception as e:
            print(f"Instagram: misslyckades med {sid}: {e}", file=sys.stderr)
    save_state(state)


def forhandsvisning(out, n=2):
    flode = json.loads((ROOT / "data" / "flode.json").read_text(encoding="utf-8"))
    evs = [e for e in flode["handelser"] if (e.get("utkast") or {}).get("rubrik_sv") and not (e.get("utkast") or {}).get("osaker")][:n]
    for e in evs:
        e["godkand_tid"] = time.time()
        files = render(e, Path(out) / e["id"], banner="Förhandsvisning · ogranskat utkast")
        print(e["id"], len(files), "kort:", (e["utkast"] or {}).get("rubrik_sv", "")[:60])


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("kommando", choices=["bygg", "posta", "forhandsvisning"])
    ap.add_argument("mapp", nargs="?")
    ap.add_argument("--antal", type=int, default=1)
    a = ap.parse_args()
    if a.kommando == "bygg":
        bygg()
    elif a.kommando == "posta":
        posta(a.antal)
    else:
        forhandsvisning(a.mapp or "/tmp/ig", a.antal if a.antal > 1 else 2)
