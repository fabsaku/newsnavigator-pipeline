"""Analys-raden: vad en händelse betyder för just den här läsaren (B2).

Princip 4: notisens fakta innehåller aldrig åsikter. En bedömning står i en egen rad märkt Analys, efter fakta, skriven med hjälp av AI,
utan råd och utan förutsägelser, och kontrollerad av en andra läsning. Raden är svenska läsarens (vad det betyder i Sverige) och engelska
läsarens (vad det betyder för en amerikansk eller brittisk läsare). Finns ingen direkt koppling blir raden null: hellre ingen rad än en påhittad.

Resultatet sparas som `betydelse` på händelsen. Det visas först när utvärderingen (B3) är gjord och NN_BETYDELSE=1 sätts.
"""
import hashlib
import json
import os
import re
import time

from prompts import user_prompt

MIN_KALLOR = 3
MAX_ORD = 40

SYSTEM = """Du skriver Analys-raden i Newsnavigator: vad en händelse betyder för just den här läsaren. Raden märks Analys och står efter fakta. Den är en bedömning, så den måste vara spårbar och försiktig.

Du får källmaterial (rubrik och ingress) och notisens utkast. Skriv två rader:
- betydelse_sv: för en läsare i Sverige (svenska hushåll, företag, Sveriges ekonomi, säkerhet och EU- och Natorelationer).
- betydelse_en: för en engelskspråkig läsare, främst i USA och Storbritannien (hushåll, marknader, politik, säkerhet).

Regler som alltid gäller:
1. Raden är högst två meningar och högst 40 ord. Börja med fakta ur notisen som kopplingen bygger på ("Eftersom ...", "Med anledning av ..."), och säg sedan vad det innebär för läsaren.
2. Använd bara fakta som står i källmaterialet eller utkastet. Lägg aldrig till egna siffror, händelser eller bakgrund. Tillåtet utöver det är allmänt känd struktur om läsarens situation (till exempel att Sverige är medlem i EU och Nato och har kronan som valuta).
3. Allmänt kända sambandsmekanismer är tillåtna när raden bara säger att två saker hänger ihop, utan storlek och utan tidpunkt: oljepris och bränslepris, styrräntor och bolån, tullar och exportföretag, valutakurser och importpriser, krig och energipriser i Europa.
4. Ge aldrig råd till läsaren ("du bör", "överväg"). Gör aldrig förutsägelser ("kommer att", "väntas bli") och spekulera inte. Skriv vad som hänger ihop, inte vad som kommer hända.
5. Inga värdeord ("katastrof", "historisk", "chockerande") och ingen bedömning av vem som har rätt eller fel.
6. Finns ingen direkt koppling till läsaren ur fakta, sätt fältet till null. En tom rad är bättre än en forcerad. Engelska raden får vara null även när den svenska finns, och tvärtom.
7. "grund" är numren (i hakparentes i källmaterialet) på de källor vars uppgifter raden bygger på.
8. Raden ska handla om läsarens situation (pengar, jobb, priser, säkerhet, politik som berör dem), aldrig om källornas tillförlitlighet eller hur säker en uppgift är.
9. Använd aldrig tankstreck (– eller —). Skriv om med kolon, komma eller två meningar.

Svara ENDAST med ett JSON-objekt: {"betydelse_sv": sträng eller null, "betydelse_en": sträng eller null, "grund": [källnummer]}"""

KONTROLL = """Du är Newsnavigators kontrollant för Analys-rader. Du får källmaterial, ett utkast till notis och en eller två Analys-rader. Avgör för varje påstående i raderna om det håller.

Den svenska raden gäller en läsare i Sverige och den engelska en läsare i USA eller Storbritannien. Det är avsikten med raderna, flagga inte att läsargruppen skiljer sig från källmaterialets.
1. Varje sakuppgift i raden måste ha stöd i källmaterialet eller utkastet. Siffror, namn och tidsangivelser måste stämma.
1b. Allmänt känd struktur om läsarens situation (Sverige i EU och Nato, kronan) och allmänt kända sambandsmekanismer (oljepris och bränslepris, räntor och bolån, tullar och exportföretag, valutor och importpriser) är tillåtna när raden bara säger att sakerna hänger ihop, utan storlek och tidpunkt. Flagga dem inte som "saknar stöd".
2. Markera förutsägelser ("kommer att", "will"), råd till läsaren, spekulation, värdeord och slutsatser som inte följer av uppgifterna.
3. Markera kopplingar till läsaren som är långsökta eller som lägger till uppgifter. Markera också rader som handlar om källornas tillförlitlighet i stället för om vad händelsen betyder för läsaren.
4. Var strikt men inte pedantisk.

Svara ENDAST med ett JSON-objekt: {"problem": [{"text": "kort", "skal": "saknar stöd" eller "förutsägelse" eller "råd" eller "värdeord" eller "slutsats" eller "ingen koppling"}], "ok": true/false}
"ok" är true bara om listan med problem är tom."""

_FORUTSAGELSE = re.compile(r"\b(kommer att|kommer att bli|väntas bli|förväntas bli|lär bli|will|going to|is expected to|are expected to|expected to)\b", re.I)
_RAD = re.compile(r"\b(du bör|ni bör|bör du|överväg|se till att|you should|consider|make sure)\b", re.I)
_VARDE = re.compile(r"\b(katastrof\w*|historisk\w*|chockerande|dramatisk\w*|skandal\w*|fruktansvärd\w*|disaster|catastroph\w*|historic|shocking|dramatic|scandal\w*|terrible)\b", re.I)
_TANKSTRECK = re.compile(r"[–—]")


def aktiv():
    return os.environ.get("NN_BETYDELSE") == "1"


def _ok_rad(text):
    return bool(text) and len(text.split()) <= MAX_ORD and not any(r.search(text) for r in (_FORUTSAGELSE, _RAD, _VARDE, _TANKSTRECK))


def _oberoende(c):
    return {i["source_id"] for i in c["items"] if i["source_type"] != "kuraterat"}


def _prompt(c, utkast):
    d = utkast
    return "\n".join([user_prompt(c).replace("Skriv utkastet enligt reglerna.", ""), "Notisens utkast:", f"Rubrik: {d.get('rubrik_sv', '')}",
                      f"Sammanfattning: {d.get('sammanfattning_sv', '')}", "", "Skriv Analys-raderna enligt reglerna."])


def _kontrollprompt(c, utkast, sv, en):
    rader = [r for r in (f"Analys (sv): {sv}" if sv else "", f"Analys (en): {en}" if en else "") if r]
    return "\n".join([user_prompt(c).replace("Skriv utkastet enligt reglerna.", ""), "Notisens utkast:", f"Rubrik: {utkast.get('rubrik_sv', '')}",
                      f"Sammanfattning: {utkast.get('sammanfattning_sv', '')}", "", *rader, "", "Kontrollera raderna."])


def _json(text):
    return json.loads(text[text.find("{"): text.rfind("}") + 1])


def bygg(c, utkast, client, model, reply_text, cache):
    """{"sv", "en", "grund", "grund_kallor", "kontroll", "ok"} eller None (ingen AI, för få källor, ingen koppling, underkänd rad eller fel)."""
    if client is None or not utkast or not utkast.get("rubrik_sv") or utkast.get("osaker") or len(_oberoende(c)) < MIN_KALLOR:
        return None
    nyckel = hashlib.sha1((SYSTEM + KONTROLL + _prompt(c, utkast)).encode()).hexdigest()[:12]
    lager = cache.setdefault("betydelse", {})
    if nyckel in lager:
        lager[nyckel]["sedd"] = time.time()
        return lager[nyckel]["betydelse"]
    try:
        msg = client.messages.create(model=model, max_tokens=2000, system=SYSTEM, messages=[{"role": "user", "content": _prompt(c, utkast)}])
        d = _json(reply_text(msg).strip())
        sv, en = (d.get("betydelse_sv") or None), (d.get("betydelse_en") or None)
        grund = sorted({int(n) for n in d.get("grund") or []})
        if (sv and not _ok_rad(sv)) or (en and not _ok_rad(en)) or (not sv and not en) or not grund or any(not 1 <= n <= len(c["items"]) for n in grund):
            resultat = None
        else:
            kmsg = client.messages.create(model=model, max_tokens=2000, system=KONTROLL,
                                          messages=[{"role": "user", "content": _kontrollprompt(c, utkast, sv, en)}])
            k = _json(reply_text(kmsg).strip())
            problem = [f"{p.get('skal')}: {p.get('text')}" for p in k.get("problem") or []]
            kontroll = {"ok": bool(k.get("ok")) and not problem, "problem": problem}
            resultat = {"sv": sv, "en": en, "grund": grund,
                        "grund_kallor": [{"namn": c["items"][n - 1]["source_name"], "url": c["items"][n - 1]["url"]} for n in grund],
                        "kontroll": kontroll, "ok": kontroll["ok"]}
    except Exception as e:
        print(f"  Betydelse misslyckades: {e}")
        return None
    lager[nyckel] = {"betydelse": resultat, "sedd": time.time()}
    return resultat
