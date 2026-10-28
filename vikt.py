"""Vikt: hur viktig en händelse är, mätt så att det rätta vinner över det snabba.

Fem delar, alla synliga i flödet så att det går att se varför något hamnade högt:

  bredd        andel av varje regions källor som rapporterar, summerat över regionerna (0 till 9).
               Primärkällor väger 1,5, public service 1,2, kuraterade listor 0,2.
               Fem amerikanska källor av 49 väger lika lite som de borde; två av sju afrikanska väger mycket.
  uthållighet  hur många timmar händelsen funnits i flödet (data/historik.json). Det som håller i sig är viktigt.
  tyngd        ingår i bredden via källornas vikt.
  bekräftelse  källkontrollen har spårat alla påståenden (läggs på efter utkasten).
  konsekvens   AI:n bedömer bara rubrikerna: hur många som berörs, hur allvarligt, hur varaktigt (1 till 5).
               Kändis, sport och nöje får låg konsekvens även när hela världen skriver om det.

Måste med: minst fem regioner och åtta oberoende källor med konsekvens minst 3, eller två primärkällor
med konsekvens minst 3. Sådana händelser får inte missas och går till Behöver dig om de inte granskas.
"""
import json
import math
import re
import time
from pathlib import Path

ROOT = Path(__file__).parent
HISTORIK = ROOT / "data" / "historik.json"
HISTORIK_DAGAR = 4

TYNGD = {"primar": 1.5, "forskning": 1.5, "kuraterat": 0.2}
PUBLIC_SERVICE = 1.2

KONSEKVENS_SYSTEM = """Du bedömer hur viktig en nyhetshändelse är, utifrån enbart rubrikerna. Du skriver inga texter.

Ge tre tal från 1 till 5:
- berorda: hur många människor som direkt påverkas (1 = en person eller en liten krets, 3 = en stad eller en bransch, 5 = ett helt land eller flera länder)
- allvar: vad som står på spel (1 = underhållning, kändisar, sport, kuriosa; 3 = politik, ekonomi eller säkerhet med begränsad effekt; 5 = liv, krig, val, folkhälsa, stora ekonomiska beslut)
- varaktighet: hur länge följderna består (1 = dagar, 3 = månader, 5 = år eller oåterkalleligt)

Bedöm händelsen, inte hur mycket den skrivs om. Var nykter: de flesta nyheter hamnar på 2 eller 3.
Svara ENDAST med JSON: {"berorda": n, "allvar": n, "varaktighet": n, "skal": "en kort mening"}"""


def region_totals(sources):
    """Antal oberoende källor per region (kuraterade listor räknas inte)."""
    tot = {}
    for s in sources:
        if s.get("typ") != "kuraterat":
            tot[s.get("region", "global")] = tot.get(s.get("region", "global"), 0) + 1
    return tot


def _weight(it):
    if it.get("source_type") in TYNGD:
        return TYNGD[it["source_type"]]
    if it.get("owner") == "public-service":
        return PUBLIC_SERVICE
    return 1.0


def bredd(c, totals):
    per = {}
    for it in c["items"]:
        if it.get("source_type") == "kuraterat":
            continue
        r = it.get("region", "global")
        per.setdefault(r, {})[it["source_id"]] = _weight(it)
    return round(sum(min(1.0, sum(ws.values()) / totals[r]) for r, ws in per.items() if totals.get(r)), 3), \
        {r: len(ws) for r, ws in per.items()}


# ---------- Uthållighet ----------

def _ord(c):
    from pipeline import tokens
    lead = c["items"][0]
    return tokens(lead.get("title_en") or lead["title"])


def load_history():
    try:
        return json.loads(HISTORIK.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []


def save_history(hist, now=None):
    now = now or time.time()
    hist = [h for h in hist if h["senast"] >= now - HISTORIK_DAGAR * 86400]
    HISTORIK.parent.mkdir(parents=True, exist_ok=True)
    HISTORIK.write_text(json.dumps(hist, ensure_ascii=False, indent=0), encoding="utf-8")


def match_history(c, hist):
    """Samma händelse i en tidigare körning: källöverlapp eller tydligt ordöverlapp i rubrikerna."""
    srcs = {it["source_id"] for it in c["items"]}
    words = _ord(c)
    best, best_s = None, 0.0
    for h in hist:
        src_overlap = len(srcs & set(h["kallor"])) / max(1, min(len(srcs), len(h["kallor"])))
        hw = set(h["ord"])
        word_overlap = len(words & hw) / max(1, min(len(words), len(hw)))
        s = max(src_overlap * (word_overlap >= 0.3), word_overlap * (word_overlap >= 0.6))
        if s > best_s:
            best, best_s = h, s
    return best if best_s >= 0.5 else None


def update_history(clusters, hist, now=None):
    """Registrerar körningen. Sätter c['timmar'] = antal olika timmar händelsen funnits i flödet."""
    now = now or time.time()
    hour = int(now // 3600)
    for c in clusters:
        h = match_history(c, hist)
        if h is None:
            h = {"forst": now, "timmar": [], "kallor": [], "ord": []}
            hist.append(h)
        if hour not in h["timmar"]:
            h["timmar"].append(hour)
        h["timmar"] = h["timmar"][-96:]
        h["kallor"] = sorted(set(h["kallor"]) | {it["source_id"] for it in c["items"]})[-60:]
        h["ord"] = sorted(set(h["ord"]) | _ord(c))[-40:]
        h["senast"] = now
        c["timmar"] = len(h["timmar"])
        c["_hist"] = h
        c["forst_sedd"] = h["forst"]
    return hist


# ---------- Konsekvens ----------

def konsekvens_prompt(c):
    lines = ["Rubriker om samma händelse:"]
    seen = set()
    for it in c["items"][:12]:
        t = it.get("title_en") or it["title"]
        if t not in seen:
            seen.add(t)
            lines.append(f"- {t} ({it['source_name']})")
    return "\n".join(lines)


def konsekvens(c, client, model, reply_text, cache):
    """Värde 1 till 5 (medel av de tre talen), eller None utan AI. Cachas per rubrikuppsättning."""
    if client is None:
        return None
    import hashlib
    key = hashlib.sha1(konsekvens_prompt(c).encode()).hexdigest()[:12]
    hit = cache.setdefault("konsekvens", {}).get(key)
    if hit:
        hit["sedd"] = time.time()
        return hit["varde"]
    msg = client.messages.create(model=model, max_tokens=4000, system=KONSEKVENS_SYSTEM,
                                 messages=[{"role": "user", "content": konsekvens_prompt(c)}])
    text = reply_text(msg)
    d = json.loads(text[text.find("{"): text.rfind("}") + 1])
    nums = [max(1, min(5, int(d.get(k, 3)))) for k in ("berorda", "allvar", "varaktighet")]
    varde = {"berorda": nums[0], "allvar": nums[1], "varaktighet": nums[2],
             "medel": round(sum(nums) / 3, 2), "skal": str(d.get("skal", ""))[:200]}
    cache["konsekvens"][key] = {"varde": varde, "sedd": time.time()}
    return varde


# ---------- Själva måttet ----------

def vikt(c, totals, kons=None, bekraftad=None):
    """Returnerar (vikt, delar). kons = konsekvens-dict eller None, bekraftad = True/False/None."""
    b, per_region = bredd(c, totals)
    timmar = c.get("timmar", 1)
    k = kons["medel"] if kons else 2.5          # utan AI: neutral mitt
    bek = 1.0 if bekraftad else 0.0 if bekraftad is False else 0.5
    total = 10 * b + 3 * math.log2(1 + timmar) + 3 * (k - 1) + 2 * bek
    independent = sum(per_region.values())
    primar = len({it["source_id"] for it in c["items"] if it.get("source_type") in ("primar", "forskning")})
    maste = k >= 3 and ((len(per_region) >= 5 and independent >= 8) or primar >= 2)
    return round(total, 1), {"bredd": b, "regioner": per_region, "timmar": timmar, "konsekvens": kons,
                             "bekraftad": bekraftad, "maste": maste}
