# Kostnadsupplägg

Mål: Newsnavigator ska kosta så nära noll som möjligt utöver domänen, utan att sajten eller Instagram blir sämre. Siffrorna nedan är mätta där det står "mätt" och annars uppskattade. Kostnaden för AI-steget mäts i `data/kostnad.json` (USD per dygn, tokens, anrop).

## Fasta kostnader

| Post | Kostnad | Kommentar |
|---|---|---|
| Domänen newsnavigator.se | cirka 100 till 300 kr per år | Beror på registrar, kontrollera där. Enda fasta kostnaden. |
| GitHub, repot | 0 | Publikt repo. |
| GitHub Actions | 0 | Gratis och obegränsat för standardrunners i publika repon. Var 2 000 minuter per månad privat, vilket tog slut 8 november. |
| Cloudflare Pages och Workers (sajt och klocka) | 0 | Inom gratisnivån vid vår trafik. Inte kontrollerat mot kontots gränser. |
| Instagram och Meta API | 0 | Både kontona publicerar via API:t. |
| Resend (morgonrapport) | 0 | Ett mejl per dygn, inom gratisnivån enligt tidigare uppgift. Kontrollera hos Resend. |
| Konsolen "Läget just nu" | 0 | Bara källornas rubriker och länkar. Ingen AI och inga nycklar. Läsarens egen AI betalas av läsaren. |

## Rörlig kostnad: AI-steget (Anthropic API)

Modell: `claude-haiku-5-5`, 0,10 USD per miljon tokens in och 0,50 USD per miljon ut.

Mätt:
- 17 november: 0,247 USD på 9 körningar.
- 18 november: 0,373 USD på 27 körningar och 974 anrop. Då stoppade taket bara nya utkast, medan översättning, konsekvens, berättelser, Analys och ny källkontroll körde vidare.
- En körning med många nya utkast: 0,06 till 0,08 USD. Lägre effort (`NN_AI_EFFORT=low`) gav cirka 25 procent lägre kostnad.

Skydd (alla i `pipeline.py`, kan ändras med miljövariabler):

| Skydd | Standard | Verkan |
|---|---|---|
| `NN_AI_DAGSTAK_USD` | 0,15 | När dygnets kostnad nått detta vid körningens start görs inga nya AI-anrop. Cachen används. |
| `NN_AI_NYA_PER_KORNING` | 4 | Högst så många nya utkast per körning, så att budgeten sprids över dygnet. |
| `NN_AI_EFFORT` | low | Färre tankningstokens. Tom sträng stänger av. |
| Cache | alltid | Utkast, översättningar och källkontroll återanvänds när underlaget är oförändrat. |

Tak per månad: 0,15 USD gånger 30 dagar är 4,50 USD. Överskjutning med högst en körning per dygn kan ge några cent till, så räkna med 5 till 7 USD per månad som övre gräns i drift. Räknat med cirka 10 kr per dollar blir det 50 till 70 kr, men kursen får du kontrollera själv.

## Vad som skulle höja kostnaden

| Förändring | Effekt |
|---|---|
| Berättelser och Analys påslagna (`NN_BERATTELSER`, `NN_BETYDELSE`) | Fler AI-steg per händelse. Inte mätt separat. Ryms inom taket, men färre notiser får AI-text. |
| Dyrare modell (Sonnet 5.5: 2,00 och 10,00 USD per miljon) | Cirka 20 gånger dyrare per token. Byt inte utan att mäta. |
| Högre tak | Linjärt: varje 0,10 USD per dygn är 3 USD per månad. |
| Fler källor eller fler körningar per timme | Fler händelser och fler nya utkast. Taket håller nere kostnaden men fler händelser får bara källornas rubriker. |

## Vad som händer när taket är nått

Nya händelser får ingen AI-rubrik eller sammanfattning förrän nästa dygn. De visas i konsolen (Läget just nu) med källornas egna rubriker och länkar. Sajtens förstasida och Instagram-korten bygger på AI-utkast och granskade notiser, så de påverkas: det går att få färre nya notiser en dag då taket nås tidigt.

## Uppföljning

- `data/kostnad.json` visar USD, tokens, anrop och körningar per dygn. Nattsessionen läser den och rapporterar i Läget.
- Rimlig kontroll efter en vecka: ligger dygnskostnaden på taket varje dag? Då är taket för snålt för att få nog nya notiser, och beslutet är om det ska höjas eller om fler notiser ska vara ren konsol.
- Sätt också en månadsgräns i Anthropic Console (Billing, spend limit), till exempel 10 USD. Det är ett andra skydd om något i koden skulle gå fel. Det kan bara du göra.

## Beslut som finns kvar

1. Är 0,15 USD per dygn rätt nivå? Mät en vecka, justera sedan.
2. Ska Berättelser och Analys slås på? Då behövs en mätning av vad de kostar och ett beslut om att de är värda det.
3. Ska förstasidan visa fler källrubriker utan AI när taket nåtts, så att sajten alltid känns levande?
