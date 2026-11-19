# Drift dygnet runt, året om

Mål: sajten uppdateras varje timme, 24 timmar om dygnet, 365 dagar om året, medan trafiken byggs upp och motorn testas. Appen kommer om några veckor.

## Hur det är byggt
1. **Klockan (Cloudflare Worker)** startar pipelinen varje timme med workflow_dispatch.
2. **Reserv (GitHub schema)** startar pipelinen kl :17 varje timme, dygnet runt. Concurrency-gruppen `newsnavigator` gör att körningar köar i stället för att köras dubbelt.
3. **Pipelinen** hämtar källor, bygger flödet, bygger sajten, sparar i repot och uppdaterar grenen `sajt`, som Cloudflare Pages publicerar.
4. **Sajten** är öppen för sökmotorer (`NN_LANSERAD=1`): ingen noindex, robots.txt tillåter, sitemap skapas.
5. **status.json** på sajten visar när den byggdes, när flödet skapades och hur många händelser det finns. Går att övervaka utifrån.
6. **Kostnad:** se `docs/kostnader.md`. Tak per dygn så att AI-steget aldrig kan skena.

## Vad som går sönder och hur det hanteras
| Fel | Hantering |
|---|---|
| En källa ger fel | Pipelinen går vidare, källan visas som trasig i Behöver dig |
| AI-tjänsten svarar inte eller dygnstaket är nått | Cachen används, nya händelser visas i konsolen med källornas rubriker |
| Klockan i Cloudflare stannar | Reservschemat i GitHub tar över inom en timme |
| GitHubs schema försenas | Klockan startar körningen |
| En körning tar för lång tid | Tidsgräns 25 minuter (normal körning 6 till 12) |
| Actions-minuter | Obegränsade i publikt repo |
| Larmet "klockan har stannat" | Efter 27 timmar utan körning (Behöver dig) |

## Svagheter som finns kvar
- **Larm utanför GitHub saknas** tills Resend är på plats (morgonrapport och varning vid fel). Utan det märker ingen ett stopp förrän någon tittar.
- **Reposstorlek** växer cirka 3 MB per dygn (226 MB packat 19 november), mest bilder och sajtfiler. Det är inget problem på månader, men över ett år närmar vi oss 1 GB. Åtgärd när det behövs: flytta Instagrambilder ur git.
- **Tokens förfaller.** GitHub-nyckeln i Cloudflare (fine-grained, högst ett år), Instagram-tokens (60 dagar, förnyas varje måndag av `igtoken.yml`), Anthropic-nyckelns kredit. Kontrollera datum.
- **En enda region och en enda leverantör** för körning (GitHub Actions) och publicering (Cloudflare). Det räcker för nu.

## Det Fabian gör för full 24/7
1. Resend-konto och secrets `RESEND_API_KEY`, `RAPPORT_TILL` (steg 3.1 i steg-for-steg.md), så att fel mejlas en gång per dygn i stället för varje timme.
2. Klistra in nya `klocka/worker.js` i Cloudflare (steg 3.2).
3. En gratis extern övervakning av `https://newsnavigator.se/status.json` (till exempel UptimeRobot, nyckelordsövervakning) så att du får larm om sajten inte svarar.
4. Sätt en månadsgräns i Anthropic Console (Billing, spend limit).
5. Notera förfallodatum för GitHub-nyckeln i Cloudflare.
