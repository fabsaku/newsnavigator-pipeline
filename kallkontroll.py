"""Källkontroll: en andra AI-läsning som spårar varje påstående i utkastet till källmaterialet.

Principen: ansvaret för fakta ligger hos källan. Vårt utkast får bara säga det källorna själva säger,
och varje tillskrivning måste stämma. Kontrollen körs på varje nytt utkast och resultatet följer med
notisen till granskningen och sajten. Den ersätter inte människans granskning, den riktar den.
"""
import json

from prompts import user_prompt

SYSTEM = """Du är Newsnavigators källkontrollant. Du får ett utkast till notis och det källmaterial (rubriker och ingresser) som utkastet bygger på.

Avgör för varje påstående i utkastet om det har stöd i källmaterialet.
1. Ett påstående har stöd om minst en källa säger samma sak i sak. Siffror, namn, platser och tidsangivelser måste stämma. Omskrivningar med samma innebörd räknas som stöd.
2. En tillskrivning ("enligt X", "X skriver", "X lyfter") stämmer bara om X är en av källorna och X:s text innehåller uppgiften.
3. Markera värdeord och egna slutsatser som inte finns i källorna.
4. Beskrivningar av vad en källa lyfter fram i sin rubrik (i perspektivtexten) kontrolleras mot just den källans rubrik och ingress.
5. Var strikt men inte pedantisk. Dela upp texten i korta påståenden, ett per sakuppgift.

Svara ENDAST med ett JSON-objekt:
{"pastaenden": [{"text": "påståendet med egna ord, kort", "stod": [källnummer], "problem": null eller "saknar stöd" eller "fel tillskrivning" eller "värdeord" eller "egen slutsats"}],
 "ok": true/false,
 "sammanfattning": "en mening om vad som brister, eller null"}
"ok" är true bara om inget påstående har ett problem."""


def check_prompt(c, draft):
    d = draft or {}
    parts = ["Utkast:", f"Rubrik: {d.get('rubrik_sv', '')}", f"Sammanfattning: {d.get('sammanfattning_sv', '')}"]
    if d.get("perspektiv_sv"):
        parts.append(f"Perspektiv: {d['perspektiv_sv']}")
    if d.get("usa_sv"):
        parts.append(f"USA: {d['usa_sv']}")
    if d.get("oenighet"):
        parts.append(f"Oenighet: {d['oenighet']}")
    parts += ["", user_prompt(c).replace("Skriv utkastet enligt reglerna.", "Kontrollera utkastet mot källmaterialet.")]
    return "\n".join(parts)


def check(c, draft, client, model, reply_text):
    """Returnerar {"ok", "antal", "problem": [...], "pastaenden": [...], "sammanfattning"} eller None om kontrollen inte gick."""
    if client is None or not draft or not draft.get("rubrik_sv"):
        return None
    msg = client.messages.create(model=model, max_tokens=8000, system=SYSTEM,
                                 messages=[{"role": "user", "content": check_prompt(c, draft)}])
    text = reply_text(msg).strip()
    data = json.loads(text[text.find("{"): text.rfind("}") + 1])
    claims = data.get("pastaenden") or []
    problems = [f"{p.get('problem')}: {p.get('text')}" for p in claims if p.get("problem")]
    return {"ok": bool(data.get("ok")) and not problems, "antal": len(claims), "problem": problems,
            "pastaenden": claims, "sammanfattning": data.get("sammanfattning")}
