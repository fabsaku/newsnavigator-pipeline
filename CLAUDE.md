# Newsnavigator: instruktioner för Claude Code

Läs först: `README.md`, `PRINCIPER.md`, och för driftpanelen `docs/redaktionen.md` (bygg en fas per session).

## Regler
- Gränssnitt och texter på svenska (och engelska där sajten är tvåspråkig). Inga tankstreck (—) i texter. Han/hon, inte hen.
- Positionering: en modern global text-tv i Sverige-bemärkelsen: kortfattat, utan trams, och något man kan lita på. Gatorn är en nyhetskonsol: överblicken finns här, läsningen sker hos källorna, så länken till artikeln ska alltid vara nära. Rubrik, fakta och källor först; inga slogans, hashtaggar eller utfyllnad. Inga uppmaningar i kort, bildtexter eller brev: aldrig dela, följa, spara, gilla, svepa eller prenumerera (testas i `tests/test_instagram_en.py`). Varje notis säger öppet hur den granskats.
- Formen kommer från `render.py`: svartvitt, Source Serif 4 och Source Sans 3, ingen monospace, inga versaletiketter.
- Återge aldrig källornas text, bara rubrik och länk. Inget innehåll bakom betalväggar. Respektera källor som blockerar bottar.
- Secrets (API-nycklar, tokens) skrivs aldrig i kod, filer eller chatt. Fabian lägger dem själv i GitHub och Cloudflare.
- Säg secrets, inte hemligheter, i kod, kommentarer, dokumentation och commits.
- Skriv om aldrig pushad historik. Små commits.
- Commits: `git -c user.name=Claude -c user.email=noreply@anthropic.com commit`, med trailer `Co-Authored-By` och `Claude-Session`.

## Kör
- Lokalt utan nät: `python pipeline.py --feeds tests/feeds-test.yaml --max-age-hours 0`
- Förhandsvisning av sajten: `python publish.py --forhandsvisning /tmp/sajt`
- Instagramkort: `python instagram.py forhandsvisning /tmp/ig`
- Workflows startas med `gh api -X POST repos/fabsaku/newsnavigator-pipeline/actions/workflows/<fil>/dispatches -f ref=main` (GraphQL är blockerat).
- Sandboxen når sällan RSS och API:er; verifiera via en GitHub Actions-körning.
