"""Berättelserna: de två till fyra sätt som källorna berättar en händelse på, med namn.

Tesen: lägger man tillräckligt bra källor bredvid varandra kan en AI hitta de olika berättelserna. Ett steg per händelse med minst fyra
oberoende källor i minst två regioner. AI:n får bara rubrikerna och ingresserna och ska säga vad grupper av källor lyfter fram, alltid
tillskrivet, aldrig vad en källa utelämnar (promptregel 11) och aldrig vilken berättelse som är sann. Vilka källor, regioner och
AllSides-sidor som bär en berättelse räknar koden ut ur källorna, inte AI:n. En egen källkontroll läser tillskrivningarna mot källmaterialet.

Resultatet sparas på händelsen som `narrativ`. Det visas inte på sajten eller i korten förrän utvärderingen (B3) är gjord och
NN_BERATTELSER=1 sätts.
"""
import hashlib
import json
import os
import re
import time

import kallkontroll
from prompts import LEAN_LABEL, user_prompt

MIN_KALLOR, MIN_REGIONER = 4, 2
MIN_BERATTELSER, MAX_BERATTELSER = 2, 4
MAX_ORD_I_NAMN = 7
MAX_ORD_I_LYFTER = 45
MIN_KALLOR_PER_BERATTELSE = 2
LEAN_SIDE = {"vanster": "bla", "lutar_vanster": "bla", "mitten": "mitten", "lutar_hoger": "rod", "hoger": "rod"}

SYSTEM = """Du hittar de olika berättelserna i hur källor skriver om samma händelse, för Newsnavigator. Grundregel: vi visar vem som lyfter fram vad, läsaren drar slutsatserna.

Regler som alltid gäller:
1. Använd bara rubrikerna och ingresserna du får. Lägg aldrig till egen kunskap, siffror eller bakgrund.
2. Dela källorna i två till fyra grupper efter hur de ramar in händelsen i sina rubriker och ingresser: olika orsak, olika ansvarig, olika konsekvens, olika huvudperson eller olika fråga. Det som skiljer ska vara ramen, inte vilken detalj som råkar vara med.
   Varje berättelse måste bäras av minst två källor, och varje källa hör till högst en berättelse. En vinkel som bara en källa har är en detalj, inte en berättelse: lämna den utanför. Skiljer sig inte källorna åt, eller går de inte att dela så, svara med en tom lista.
3. Varje berättelse får ett kort, sakligt namn på högst sju ord som beskriver vinkeln (till exempel "Kostnaden för bönder"), aldrig en värdering och aldrig ett påstående om vad som är sant.
4. "lyfter" är EN mening på högst 40 ord som tillskriver: säg vilka källor som lyfter fram vad ("NPR och BBC lyfter fram ..."). Skriv med egna ord, inga citat längre än fem ord.
5. Beskriv vad källorna lyfter fram, aldrig vad de utelämnar. Att peka ut vad en källa inte nämner är en värdering. Använd aldrig ord som "nämner inte", "utelämnar", "ignorerar", "tiger om", "döljer".
6. Säg aldrig vilken berättelse som är sann eller rätt, och rangordna dem inte.
7. Behandla amerikanska medier med olika AllSides-betyg med samma mått. Skriv "medier som AllSides bedömer lutar vänster eller höger", aldrig "vänstermedier" eller "högermedier".
8. Statskontrollerade medier anges som sådana.
9. En kuraterad lista rapporterar inte själv. Tillskriv aldrig uppgifter till den.
10. Använd aldrig tankstreck (– eller —). Skriv om med kolon, komma eller två meningar.

Svara ENDAST med ett JSON-objekt:
{"berattelser": [{"namn_sv": "...", "namn_en": "...", "lyfter_sv": "...", "lyfter_en": "...", "kallor": [källnummer som bär berättelsen]}]}
Källnumren är numren i hakparentes i källmaterialet. En tom lista om det inte finns två olika berättelser."""

# Ord som visar att berättelsen pekar ut vad en källa utelämnar, eller påstår vad som är sant
_UTELAMNAR = re.compile(r"\b(nämner inte|nämner ej|utelämnar|utelämnade|ignorerar|tiger om|döljer|förtiger|saknar omnämnande|"
                        r"omits?|omitted|ignores?|ignored|fails? to mention|does not mention|doesn.t mention|hides?|conceals?)\b", re.I)
_SANN = re.compile(r"\b(sanningen|den sanna|det sanna|falsk\w*|lögn\w*|propaganda|the truth|the true|false|lies|lying)\b", re.I)
_TANKSTRECK = re.compile(r"[–—]")


def aktiv():
    """Visas berättelserna? Först efter utvärderingen (B3) sätts NN_BERATTELSER=1."""
    return os.environ.get("NN_BERATTELSER") == "1"


def oberoende(c):
    return {i["source_id"] for i in c["items"] if i["source_type"] != "kuraterat"}


def kvalificerad(c):
    """Minst fyra oberoende källor i minst två regioner."""
    reg = {i["region"] for i in c["items"] if i["source_type"] != "kuraterat"}
    return len(oberoende(c)) >= MIN_KALLOR and len(reg) >= MIN_REGIONER


def _prompt(c):
    return user_prompt(c).replace("Skriv utkastet enligt reglerna.", "Hitta berättelserna enligt reglerna.")


def _ok_text(*texter):
    return all(t and not _UTELAMNAR.search(t) and not _SANN.search(t) and not _TANKSTRECK.search(t) for t in texter)


def _validera(svar, antal_kallor):
    """Tillbaka en lista med giltiga berättelser, eller None om något brister (hellre inga berättelser än fel berättelser)."""
    lista = svar.get("berattelser") if isinstance(svar, dict) else None
    if not isinstance(lista, list) or not MIN_BERATTELSER <= len(lista) <= MAX_BERATTELSER:
        return None
    ut, anvanda = [], set()
    for b in lista:
        try:
            namn_sv, namn_en = str(b["namn_sv"]).strip(), str(b["namn_en"]).strip()
            lyfter_sv, lyfter_en = str(b["lyfter_sv"]).strip(), str(b["lyfter_en"]).strip()
            kallor = sorted({int(n) for n in b["kallor"]})
        except (KeyError, TypeError, ValueError):
            return None
        if len(kallor) < MIN_KALLOR_PER_BERATTELSE or any(not 1 <= n <= antal_kallor for n in kallor):
            return None
        if max(len(lyfter_sv.split()), len(lyfter_en.split())) > MAX_ORD_I_LYFTER:
            return None
        if max(len(namn_sv.split()), len(namn_en.split())) > MAX_ORD_I_NAMN or not _ok_text(namn_sv, namn_en, lyfter_sv, lyfter_en):
            return None
        if any(n in anvanda for n in kallor):
            return None                         # en källa hör till högst en berättelse
        anvanda.update(kallor)
        ut.append({"namn_sv": namn_sv, "namn_en": namn_en, "lyfter_sv": lyfter_sv, "lyfter_en": lyfter_en, "_nr": kallor})
    return ut


def _bar(b, c):
    """Vilka källor, regioner och AllSides-sidor som bär berättelsen räknas ut ur källorna."""
    its = [c["items"][n - 1] for n in b.pop("_nr")]
    b["kallor"] = [{"namn": i["source_name"], "region": i["region"], "lutning": i.get("usa_lean"),
                    "statskontrollerad": bool(i["state_controlled"]), "url": i["url"]} for i in its]
    b["regioner"] = sorted({i["region"] for i in its})
    b["usa_sidor"] = sorted({LEAN_SIDE[i["usa_lean"]] for i in its if i.get("usa_lean") in LEAN_SIDE})
    return b


def _underlag(berattelse):
    """Berättelserna som perspektivtext för källkontrollen: varje tillskrivning kontrolleras mot just de källornas rubriker."""
    return " ".join(f"Berättelsen {b['namn_sv']} (källor: {', '.join(k['namn'] for k in b['kallor'])}): {b['lyfter_sv']}" for b in berattelse)


def bygg(c, utkast, client, model, reply_text, cache):
    """Berättelserna för händelsen, eller None (för få källor, ingen AI, inga olika berättelser, eller ett steg som brast).
    {"berattelser": [...], "kontroll": källkontrollen, "ok": bool}. Cachas per källuppsättning."""
    if client is None or not utkast or not utkast.get("rubrik_sv") or not kvalificerad(c):
        return None
    nyckel = hashlib.sha1((SYSTEM + _prompt(c)).encode()).hexdigest()[:12]
    lager = cache.setdefault("berattelser", {})
    if nyckel in lager:
        lager[nyckel]["sedd"] = time.time()
        return lager[nyckel]["narrativ"]
    try:
        msg = client.messages.create(model=model, max_tokens=4000, system=SYSTEM, messages=[{"role": "user", "content": _prompt(c)}])
        text = reply_text(msg).strip()
        berattelse = _validera(json.loads(text[text.find("{"): text.rfind("}") + 1]), len(c["items"]))
        if not berattelse:
            narrativ = None
        else:
            berattelse = [_bar(b, c) for b in berattelse]
            kontroll = kallkontroll.check(c, {"rubrik_sv": utkast["rubrik_sv"], "sammanfattning_sv": "", "perspektiv_sv": _underlag(berattelse)},
                                          client, model, reply_text)
            narrativ = {"berattelser": berattelse, "kontroll": kontroll, "ok": bool(kontroll and kontroll["ok"])}
    except Exception as e:
        print(f"  Berättelser misslyckades: {e}")
        return None
    lager[nyckel] = {"narrativ": narrativ, "sedd": time.time()}
    return narrativ
