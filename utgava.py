"""Två utgåvor, en för varje läsare.

  sv  Svenska läsaren: svenska nyheter, och globala händelser som berör Sverige och Europa. Särskilt de som saknas i
      svenska medier, eftersom det är där läsaren har minst att hämta annars.
  en  Global English: en gemensam nivå för läsare var som helst i världen, utan hemland. Svenskt och nordiskt bara när
      det påverkar läsaren. Aldrig lokalt svenskt.

En notis godkänns en gång (redaktören eller autopiloten). Utgåvorna avgör var den visas: sajtens /sv/ och /en/, de två
Instagramkontona och breven. `relevans` är deterministisk och bygger på var källorna finns och vad rubrikerna nämner;
en AI-förfining kan läggas ovanpå utan att ändra gränssnittet.
"""
import re

import autopilot

UTGAVOR = ("sv", "en")
TROSKEL = {"sv": 1, "en": 2}        # lägsta relevans för att notisen ska visas i utgåvan
SVENSK_REGION = {"sverige", "norden"}
FORSPRANG = 12 * 3600               # sekunder: så mycket nyare en notis räknas när den angår utgåvans läsare mest

# Det som gör en svensk eller nordisk nyhet relevant för engelska läsaren: stormakter, allianser, marknader, stora bolag.
_EN_GLOBALT = re.compile(r"\b(nato|ukraine|russia\w*|putin|china|chinese|taiwan|tariffs?|eu|ecb|opec|nobel|ericsson|spotify|"
                         r"volvo|ikea|klarna|northvolt|saab|skf|bitcoin|nvidia|openai|dollar|oil|gas|nuclear)\b", re.I)
# Det som kopplar en händelse till amerikanska läsare.
_US_CI = re.compile(r"\b(usa|u\.s\.|american\w*|trump|washington|white house|congress|senate|wall street|pentagon|nasdaq|dollar)\b", re.I)
_US_CS = re.compile(r"\b(US|Fed|GOP)\b")
# Det som kopplar en global händelse till svenska läsare.
_SV_RELEVANT = re.compile(r"\b(sverige\w*|svensk\w*|sweden|swedish|stockholm|göteborg|malmö|riksbank\w*|kronan|norden|nordic\w*|"
                          r"nato|ecb|eu|europe\w*|europa\w*|europeisk\w*|finland|norway|denmark)\b", re.I)


def _kontrollera(utgava):
    if utgava not in UTGAVOR:
        raise ValueError(f"okänd utgåva: {utgava!r}")


def _oberoende(ev):
    return [k for k in ev.get("kallor") or [] if k.get("typ") != "kuraterat" and not k.get("statskontrollerad")]


def _text(ev):
    d = ev.get("utkast") or {}
    return " ".join(str(x) for x in (d.get("rubrik_en"), d.get("sammanfattning_en"), d.get("rubrik_sv"),
                                     d.get("sammanfattning_sv"), ev.get("reserv_rubrik")) if x)


def relevans(ev):
    """{"sv": 0 till 3, "en": 0 till 3}: hur mycket händelsen angår läsaren i varje utgåva."""
    kallor = _oberoende(ev)
    regioner = {k["region"] for k in kallor}
    text = _text(ev)
    n_sv = sum(1 for k in kallor if k["region"] == "sverige")
    n_nordiskt = sum(1 for k in kallor if k["region"] == "norden")
    globalt = len(kallor) >= 3 and len(regioner) >= 2

    if n_sv >= 2:
        sv = 3
    elif n_sv == 1 or n_nordiskt or _SV_RELEVANT.search(text):
        sv = 2 if globalt or n_sv >= 1 or n_nordiskt else 1
    elif globalt:
        sv = 1
    else:
        sv = 0

    if kallor and regioner <= SVENSK_REGION:
        en = 2 if _EN_GLOBALT.search(text) and len(kallor) >= 3 else 0
    elif globalt:
        en = 2
    else:
        en = 1 if kallor else 0
    if en >= 2 and ("usa" in regioner or _US_CI.search(text) or _US_CS.search(text)):
        en = 3
    return {"sv": sv, "en": en}


# En händelse är amerikansk när själva rubriken handlar om amerikanska aktörer, politik eller ekonomi.
_USA_RUBRIK_CI = re.compile(r"\b(usa|u\.s\.|american\w*|trump|biden|harris|vance|washington|white house|vita huset|congress|kongress\w*|senat\w*|"
                            r"senate|house of representatives|representanthus\w*|democrat\w*|demokrat\w*|republican\w*|republikan\w*|midterm\w*|"
                            r"supreme court|högsta domstol\w*|federal reserve|wall street|pentagon\w*|nasdaq|dollar\w*|fbi|cia)\b", re.I)
_USA_RUBRIK_CS = re.compile(r"\b(US|Fed|GOP|DOJ|IRS)\b")


def usa_relevant(ev):
    """Ska "USA: blått och rött" visas? Bara när händelsen är amerikansk (rubriken nämner amerikanska aktörer, politik eller ekonomi) och
    det finns en verklig kontrast: minst tre amerikanska medier, med både en blå och en röd publik enligt AllSides."""
    usa = (ev.get("perspektiv") or {}).get("usa")
    if not usa or not (usa.get("bla") and usa.get("rod")):
        return False
    if len({x["kalla"] for sida in usa.values() for x in sida}) < 3:
        return False
    d = ev.get("utkast") or {}
    rubrik = " ".join(str(x) for x in (d.get("rubrik_en"), d.get("rubrik_sv"), ev.get("reserv_rubrik")) if x)
    return bool(_USA_RUBRIK_CI.search(rubrik) or _USA_RUBRIK_CS.search(rubrik))


def angar(ev, utgava):
    """Angår händelsen utgåvans läsare mest? Svenskt i den svenska utgåvan. Den engelska är en gemensam global nivå,
    utan hemland: där lyfts det som minst tre regioner bevakar."""
    _kontrollera(utgava)
    if utgava == "sv":
        return relevans(ev)["sv"] == 3
    return visa(ev, "en") and len({k["region"] for k in _oberoende(ev)}) >= 3


def visa(ev, utgava):
    """Ska notisen visas för den här utgåvans läsare?"""
    _kontrollera(utgava)
    return relevans(ev)[utgava] >= TROSKEL[utgava]


def ordna(events, utgava):
    """Nyast först, men det som angår utgåvans läsare mest (`angar`) ligger som om det vore FORSPRANG nyare."""
    return sorted(events, key=lambda e: e.get("godkand_tid", 0) + (FORSPRANG if angar(e, utgava) else 0), reverse=True)


def kraver_genomgang(ev, utgava):
    """Innehåller notisen ett påstående som redaktören ska se själv: att den saknas eller bara finns i svenska medier
    (svenska utgåvan), eller att den mest bärs av medier med blå eller röd publik (båda)?"""
    _kontrollera(utgava)
    p = ev.get("perspektiv") or {}
    return bool(p.get("usa_blind") or (utgava == "sv" and p.get("blind_flack")))


def grindar(ev, utgava, batch=False):
    """Skälen till att notisen inte får publiceras automatiskt i utgåvan. Samma grindar som autopilotens, med två skillnader.
    Engelska utgåvan gör inte påståendet "saknas i svenska medier", så det är inget hinder där, och kräver inga svenska källor.
    Vid en lanseringsbatch (`batch`) går de svenska blinda fläckarna till redaktörens genomgång av hela batchen i stället."""
    _kontrollera(utgava)
    skal = autopilot.grindar(ev)
    kallor = _oberoende(ev)
    n_sv = sum(1 for k in kallor if k["region"] == "sverige")
    ut = []
    for s in skal:
        if s == "blind fläck":
            continue
        if s == "färre än två svenska källor" and utgava == "en":
            continue
        if s == "bara en region" and utgava == "sv" and n_sv >= 2 and len(kallor) >= 3:
            continue        # svensk inrikesnyhet: tre svenska källor räcker, regionkravet kan inte uppfyllas
        ut.append(s)
    p = ev.get("perspektiv") or {}
    if p.get("usa_blind") or (utgava == "sv" and not batch and "blind fläck" in skal):
        ut.append("blind fläck")
    return ut


def urval(events, utgava, batch=False, grindar_=True):
    """Notiserna som hör hemma i utgåvan, högst poäng först. Med `grindar_` falskt ges alla relevanta."""
    _kontrollera(utgava)
    valda = [e for e in events if visa(e, utgava) and (not grindar_ or not grindar(e, utgava, batch))]
    return sorted(valda, key=lambda e: e.get("poang", 0), reverse=True)
