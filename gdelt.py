#!/usr/bin/env python3
"""GDELT som oberoende kontroll av påståendet "saknas i svenska medier".

Vår egen signatur bygger på de källor vi följer. GDELT (öppen, fri för all användning mot att man anger källan) bevakar tusentals svenska och
andra medier och är inte vår källista, så den kan säga emot oss: hittar GDELT svenska artiklar om samma sak är påståendet tveksamt.
Bara metadata används (domän och språk), aldrig artikeltext, och inget av det visas publikt. Frågan är egennamnen i rubriken, eftersom GDELT
söker i maskinöversatt text och egennamn är samma på alla språk.

  python gdelt.py [flode.json]    kontrollerar händelserna som påstås saknas i svenska medier och skriver utlåtanden
"""
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).parent
CACHE = ROOT / "data" / "gdelt.json"
API = "https://api.gdeltproject.org/api/v2/doc/doc"
VILA = 9.0                 # sekunder mellan frågor: 5,5 räckte inte, GDELT svarade 429 på fyra av fem
VANTA_429 = [15, 30]       # sekunder att vänta före ny försök när GDELT svarar 429
MAX_FRAGOR = 15
CACHE_SEKUNDER = 86400
MIN_NAMN, MAX_NAMN = 2, 3
AGENT = "NewsnavigatorBot/0.3 (+https://newsnavigator.se/bot)"
_VERKTYG = {"Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday", "January", "February", "March", "April", "June", "July",
            "August", "September", "October", "November", "December", "According", "After", "Before", "Over", "Under", "With", "Without"}


def _namn(rubrik):
    """Egennamn i rubriken: versaler utom första ordet, minst fyra bokstäver, utan dubbletter, i ordning."""
    ut = []
    for i, ord_ in enumerate(rubrik.replace(",", " ").replace(":", " ").split()):
        ren = ord_.strip(".;\"'()“”’‘")
        if i and ren[:1].isupper() and ren.isalpha() and len(ren) >= 4 and ren not in _VERKTYG and ren not in ut:
            ut.append(ren)
    return ut


def _namn_ur_kallor(ev):
    """Egennamn (versaler, minst fyra bokstäver) som finns i minst två av källornas rubriker, vanligast först. Tål att händelsens egen rubrik är allmän."""
    antal = {}
    for k in ev.get("kallor") or []:
        for n in set(_namn("x " + (k.get("rubrik") or ""))):          # "x " så att även första ordet räknas
            antal[n] = antal.get(n, 0) + 1
    return [n for n, c in sorted(antal.items(), key=lambda x: (-x[1], -len(x[0]))) if c >= 2]


def fraga(ev):
    """GDELT-frågan för en händelse, eller None när rubrikerna har för få egennamn för att frågan ska vara träffsäker."""
    d = ev.get("utkast") or {}
    egna = _namn(d.get("rubrik_en") or ev.get("reserv_rubrik") or "")
    namn = egna if len(egna) >= MIN_NAMN else _namn_ur_kallor(ev)
    if len(namn) < MIN_NAMN:
        return None
    return " ".join(f'"{n}"' for n in namn[:MAX_NAMN]) + " sourcecountry:sweden"


def _hamta(q):
    url = f"{API}?{urllib.parse.urlencode({'query': q, 'mode': 'artlist', 'format': 'json', 'maxrecords': 50, 'timespan': '3days', 'sort': 'datedesc'})}"
    with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": AGENT}), timeout=40) as r:
        return json.loads(r.read())


def kontrollera(ev, hamta=_hamta, vila=time.sleep):
    """{"fraga", "svenska_domaner", "utlatande": stoder | motsager | oklart, "fel"} eller None om händelsen inte påstås saknas i svenska medier."""
    if (ev.get("perspektiv") or {}).get("blind_flack") != "saknas_i_sverige":
        return None
    q = fraga(ev)
    if q is None:
        return {"fraga": None, "svenska_domaner": [], "utlatande": "oklart", "fel": "för få egennamn i rubriken"}
    svar, fel = None, None
    for vanta in [0, *VANTA_429]:
        if vanta:
            vila(vanta)
        try:
            svar, fel = hamta(q), None
            break
        except urllib.error.HTTPError as e:
            fel = f"{type(e).__name__}: {str(e)[:100]}"
            if e.code != 429:
                break
        except Exception as e:
            fel = f"{type(e).__name__}: {str(e)[:100]}"
            break
    if fel:
        return {"fraga": q, "svenska_domaner": [], "utlatande": "oklart", "fel": fel}
    if not isinstance(svar, dict):
        return {"fraga": q, "svenska_domaner": [], "utlatande": "oklart", "fel": "oväntat svar"}
    domaner = sorted({a.get("domain") for a in svar.get("articles") or [] if a.get("domain")})
    utlatande = "stoder" if not domaner else "motsager" if len(domaner) >= 2 else "oklart"
    return {"fraga": q, "svenska_domaner": domaner, "utlatande": utlatande, "fel": None}


def _las():
    try:
        return json.loads(CACHE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def kor(handelser, hamta=_hamta, vila=time.sleep, nu=None, max_fragor=MAX_FRAGOR):
    """Kontrollerar händelserna med påståendet. Resultat återanvänds i ett dygn, fel cachas aldrig. Returnerar {id: utlåtande}."""
    nu = time.time() if nu is None else nu
    cache, ut, fragade = _las(), {}, 0
    for ev in handelser:
        if (ev.get("perspektiv") or {}).get("blind_flack") != "saknas_i_sverige":
            continue
        hit = cache.get(ev["id"])
        if hit and nu - hit["kontrollerad"] < CACHE_SEKUNDER:
            ut[ev["id"]] = hit["resultat"]
            continue
        if fragade >= max_fragor:
            continue
        if fragade:
            vila(VILA)
        fragade += 1
        r = kontrollera(ev, hamta=hamta, vila=vila)
        ut[ev["id"]] = r
        if r and not r["fel"]:
            cache[ev["id"]] = {"kontrollerad": nu, "resultat": r}
    if cache != _las():
        CACHE.parent.mkdir(parents=True, exist_ok=True)
        CACHE.write_text(json.dumps({k: v for k, v in cache.items() if nu - v["kontrollerad"] < 7 * 86400}, ensure_ascii=False, indent=1), encoding="utf-8")
    return ut


def main(argv):
    sokvag = Path(argv[0]) if argv else ROOT / "data" / "flode.json"
    handelser = json.loads(sokvag.read_text(encoding="utf-8"))["handelser"]
    ut = kor(handelser)
    per = {"stoder": 0, "motsager": 0, "oklart": 0}
    for ev in handelser:
        r = ut.get(ev["id"])
        if not r:
            continue
        per[r["utlatande"]] += 1
        rubrik = (ev.get("utkast") or {}).get("rubrik_en") or ev["reserv_rubrik"]
        print(f"{r['utlatande']:<9} {len(r['svenska_domaner'])} dom. | {rubrik[:70]} | {r['fraga']}" + (f" | FEL {r['fel']}" if r["fel"] else "")
              + (f" | {', '.join(r['svenska_domaner'][:4])}" if r["svenska_domaner"] else ""))
    print(f"\n{sum(per.values())} händelser som påstås saknas i svenska medier: GDELT stöder {per['stoder']}, motsäger {per['motsager']}, oklart {per['oklart']}.")


if __name__ == "__main__":
    main(sys.argv[1:])
