# Redaktionen: planen för en enmansredaktion

Det här är byggplanen för Newsnavigators driftpanel, skriven för att köras i Claude Code fas för fas.
Målet är att en person ska kunna sköta hela driften: gå igenom källornas nyheter, granska och godkänna
på tio minuter om morgonen, planera vad som går var, och sedan lägga bort telefonen och veta vad som
sköter sig självt och när den behövs.

## Fyra jobb

1. **Inkorgen.** Dagens händelser med utkast, källkontroll och källornas rubriker, i rangordning. Godkänn, redigera, avvisa, spara till senare. Ett tryck per notis.
2. **Planeringen.** Vad som går var och när: sajten, Navigatorn kl 07.30, Instagram-karusellen kl 07.45, reelsen. En veckovy med ett förslag som redan är ifyllt.
3. **Driften.** Vad som har körts, vad som kommer köras, vad som gick fel. Autopiloten med tydliga regler, och en strömbrytare som pausar allt.
4. **Behöver dig.** En enda lista: det som väntar på ett beslut, det som gått sönder, det som löper ut. Plus en morgonrapport kl 07.00 som säger om listan är tom.

## Principen: GitHub är databasen, Cloudflare är dörren

Allt pipelinen vet ligger redan i repot som filer: `data/flode.json` (dagens händelser), `data/arkiv.json` (godkända), `data/godkanda.json` (bockarna), `data/instagram.json` (kön), `data/kallstatus.json` (källorna). Panelen behöver därför ingen server och ingen databas. Den är en statisk sida på Cloudflare Pages med små funktioner (Pages Functions) som läser och skriver repots filer via GitHub-API:t med en nyckel som bara finns på Cloudflares sida. Varje beslut i panelen blir en commit, och pipelinen reagerar på commits precis som den redan gör på ärendet. Två till tre minuter från bock till publicerad sajt.

Dörren är Cloudflare Access: en inloggning med engångskod till en e-postadress på en lista (just nu en adress). Gratis upp till femtio användare, så en andra redaktör kostar ingenting den dagen det behövs.

```
telefon/dator ──Access (engångskod)──▶ redaktionen.newsnavigator.se (Pages)
                                          │  statisk app (HTML + JS, inget byggsteg)
                                          │  /api/* = Pages Functions med GITHUB_TOKEN
                                          ▼
                                   GitHub-repot: data/*.json ◀──▶ GitHub Actions (pipelinen, Navigatorn, Instagram)
                                                                         │
                                                              sajt-grenen ──▶ Cloudflare Pages ──▶ newsnavigator.se
```

Varför så, i stället för en egen server: inget att hålla igång, allt versionshanterat (varje godkännande är en commit som går att ångra), samma stack som sajten, fungerar lika bra i mobilen, och Claude Code kan bygga och testa alltihop lokalt med `wrangler pages dev`.

## Sidorna

### Inkorg

Listan är `data/flode.json` i poängordning, med filter för sektion, region, "saknas i svenska medier" och "källkontroll med anmärkningar". Varje notis visar rubrik på svenska och engelska, sammanfattning, täckningsremsan, källkontrollens resultat (alla påståenden spårade, eller anmärkningarna i klartext), och källorna som rubrik plus länk, med STAT och betalvägg markerade. Det räcker för att granska mot källorna utan att lämna panelen; länken öppnar källan när det behövs.

Handlingar, med tangenter på datorn och svep i mobilen: godkänn (a), avvisa (x), redigera rubrik och sammanfattning (e), spara till senare (s), öppna första källan (o). "Godkänn och sätt på Instagram" som en variant. Godkännanden skrivs till `data/godkanda.json`, redigeringar till `data/redigeringar.json` (per id: de fält som ändrats), och panelen visar status tills sajten är ombyggd: "Godkänd 07.52, publicerad 07.55".

Det som avvisas hamnar i `data/avvisade.json` så att samma händelse inte kommer tillbaka nästa timme.

### Källor

En rad per källa ur `feeds.yaml`: status (ok, fel med felkod, tyst i N dygn), senaste artikel, artiklar senaste sju dygnen, hur många som blivit godkända senaste trettio, primärkälla eller medier, region, AllSides-betyg. Pausa och återstarta en källa från panelen (en commit i `feeds.yaml`). Nya källor läggs till med Claude Code tills vidare; formuläret kommer senare.

### Planering

Veckovy, måndag till söndag, med raderna Navigatorn, Instagram-karusell, reel och sajtens toppnotis. Förslaget är ifyllt av pipelinen (högst poäng först, en per dag) och allt du ändrar sparas i `data/plan.json`, som `newsletter.py` och `instagram.py` läser före sina egna val. Här finns också "Kör nu" för pipelinen, Navigatorn och Instagram (workflow dispatch via API:t).

### Drift

Sex rutor: senaste körning (klockslag, ok eller fel, hur lång), nästa körning, sajten (senaste publicering till Pages), Navigatorn (skickad kl, till hur många), Instagram (senast postat, token löper ut om N dagar), källkontroll (andel notiser utan anmärkningar senaste veckan). Under rutorna de tjugo senaste körningarna med länk till loggen. Datat skrivs av workflowen till `data/drift.json` i slutet av varje körning; körstatus hämtas från Actions-API:t.

### Behöver dig

Listan skapas av regler, inte av hand, och varje rad har en handling:

| Regel | Rad | Handling |
|---|---|---|
| Notiser väntar längre än 2 timmar | "12 väntar, äldst 3 h" | Till inkorgen |
| Körning misslyckades två gånger i rad | "Pipelinen har stannat sedan 14.17" | Öppna loggen, kör igen |
| Källa tyst i 3 dygn | "Al Jazeera tyst sedan torsdag" | Kontrollera flödet, pausa |
| Instagram-token löper ut inom 14 dagar | "Token går ut 9 november" | Förnya |
| Kluster med fler än 20 källor eller fler än 3 sektioner | "Troligen hopslagna händelser" | Dela upp eller avvisa |
| Navigatorn skulle ha gått men hade färre än 3 notiser | "Inget brev i morse" | Godkänn, skicka nu |
| Rättelse begärd (mejl till we@) | "Rättelse: Audi" | Öppna notisen |

Morgonrapporten kl 07.00 är samma lista som mejl (via Resend, som Navigatorn ändå behöver), med en rad överst: "Allt kört. 9 väntar i inkorgen." Är listan tom säger mejlet det, och då behöver du inte öppna panelen.

## Autopiloten: vad som får gå utan dig

Autopiloten är en uppsättning grindar, ett vetofönster och ett tak. Den slås på och av i Drift, och "tyst läge" pausar all publicering (sajt, brev, Instagram) utan att stoppa insamlingen.

Grindar för att en notis får godkännas automatiskt:

- Källkontrollen har spårat alla påståenden.
- Minst tre oberoende källor, varav minst en som inte är en kuraterad lista, och minst två regioner. Svensk inrikes (bara nordiska källor, inte nöje eller utrikes): två svenska källor räcker, utan regionkrav.
- Utkastet är inte märkt osäkert, och ingen källa i klustret är statskontrollerad som enda källa för en uppgift.
- Klustret har högst 20 källor och högst 3 sektioner (annars är det troligen hopslaget).
- Inga ord på spärrlistan: namngivna privatpersoner i brottmål, självmord, sexualbrott, barn. De går alltid till dig.
- Blinda fläckar ("Saknas i svenska medier", "Mest i medier med röd/blå publik") går alltid till dig: de är våra skarpaste påståenden.

Vetofönstret: notiser som klarar grindarna läggs i inkorgen med en klocka, "publiceras 08.15 om du inte stoppar". Efter 45 minuter godkänns de av sig själva. Taket är åtta automatiska notiser per dygn. Navigatorn går kl 07.30 med det som är godkänt kl 07.15, men bara om det är minst tre notiser; annars hoppar den över dagen och skriver en rad i Behöver dig. Instagram postar automatiskt bara notiser som godkänts automatiskt eller av dig, i planens ordning.

Allt som publicerats automatiskt är märkt så i panelen och går att ångra med ett tryck: notisen tas ur arkivet, sajten byggs om, Instagram-inlägget tas bort via API:t (det går), och Navigatorn får en rättelse nästa morgon om den hunnit gå.

## Din dag

- 07.00: morgonrapporten. Tom lista = ingen panel i dag.
- 07.05 till 07.15: inkorgen. Godkänn, redigera, avvisa. Det som klarar grindarna ligger redan förbockat med klocka.
- 07.30: Navigatorn går. 07.45: dagens karusell postas.
- Kväll, fem minuter: planeringen för morgondagen, en blick på Behöver dig.
- Söndag, fyrtiofem minuter: spela in veckans reel, gå igenom källornas status, läs veckans rättelser.

## Teknik, för Claude Code

Katalogen `redaktionen/` i samma repo:

```
redaktionen/
  index.html          en sida, samma typografi och svartvita form som sajten
  app.js              vanilla JS (eller Preact via htm från CDN), inget byggsteg
  app.css
  functions/api/
    flode.ts          GET: data/flode.json + data/redigeringar.json + status
    godkann.ts        POST {id, beslut: godkann|avvisa|senare}: skriver godkanda/avvisade
    redigera.ts       POST {id, falt}: skriver data/redigeringar.json
    plan.ts           GET/POST: data/plan.json
    kallor.ts         GET: feeds.yaml + kallstatus; POST {id, paus}: commit i feeds.yaml
    drift.ts          GET: data/drift.json + senaste körningarna från Actions-API:t
    kor.ts            POST {workflow}: workflow_dispatch
    _github.ts        läs/skriv fil med sha-kontroll och ett nytt försök vid krock
  wrangler.toml
```

Secrets i Pages-projektet: `GITHUB_TOKEN` (fine-grained, bara detta repo: Contents läs/skriv, Actions läs/skriv, Issues läs/skriv), `GITHUB_REPO`. Inloggning sköts av Access före funktionerna, och funktionerna läser `Cf-Access-Authenticated-User-Email` och vägrar allt annat.

Datakontraktet, filer i `data/`:

| Fil | Skrivs av | Läses av | Innehåll |
|---|---|---|---|
| `flode.json` | pipelinen | panelen | dagens händelser med utkast, källkontroll, perspektiv, källor |
| `godkanda.json` | panelen, ärendet | pipelinen, publish | lista med id |
| `avvisade.json` | panelen | pipelinen | id och tidpunkt; pipelinen hoppar över dem i 7 dygn |
| `redigeringar.json` | panelen | pipelinen, publish | per id de fält som ändrats; läggs över utkastet vid bygge |
| `plan.json` | panelen, pipelinen (förslag) | newsletter, instagram | per dag: brevets toppnotis, karusell, reel |
| `drift.json` | workflows | panelen, morgonrapporten | senaste körning, tider, fel, token-utgång, brevstatus |
| `kallstatus.json` | verify_feeds | panelen | per källa: status, senaste artikel, antal, fel (ersätter kallstatus.md) |
| `autopilot.json` | panelen | pipelinen | på/av, tyst läge, tak, vetofönster i minuter |

Pipelinen ändras på fem ställen: läser `redigeringar.json` och lägger över utkasten; hoppar över `avvisade.json`; skriver `drift.json`; tillämpar autopilotens grindar och vetofönster; fyller i `plan.json` med förslag. `newsletter.py` och `instagram.py` läser planen. En ny workflow `rapport.yml` kl 07.00 bygger Behöver dig och skickar morgonrapporten med Resend (`RESEND_API_KEY`, avsändare `navigatorn@newsnavigator.se` på en egen underdomän så att SPF och DKIM inte krockar med vidarebefordringen).

Tester: `pytest` för grindarna och planförslaget (ren logik, snabba), Playwright-rök för panelen mot en kopia av `data/`. Lokalt: `npx wrangler pages dev redaktionen` med en `.dev.vars` som pekar på ett testrepo eller på en lokal mapp i läs-läge.

## Läget

**8 november, natt (nattsessionen).** Tester: 467 gröna. Klockan: 18 av 19 timstarter kl :02 finns i drift.json (sparar bara 19 körningar); 7 november 11.02 uteblev och körningen kom 11.09, alltså 7 minuter sent. Fyra extra körningar utanför :02 är manuella eller Källprov. Autopiloten: 41 publicerade, 6 stoppade, 2 i kön. Behöver dig: fyra notiser väntar (äldst 47 timmar), två troliga hopslagningar (Israels president ger Eisenkot regeringsuppdrag, Trump utser Stephen Miller till stabschef), fem tysta källor (CNN, WHO, Microsoft AI, Svenska kraftnät, Der Spiegel International) och båda Instagramkontona saknar secrets (17 svenska och 14 engelska kort väntar). 126 av 143 källor går att läsa. Nya fel sedan igår: Breakit och arXiv AI. Meta: samma läge som 7 november, Fabian har inte hunnit med företagsportföljen. Inget nytt går att bygga utan hans secrets och beslut.

**7 november, natt (nattsessionen).** Tester: 467 gröna. Klockan: 18 av 20 timstarter kl :02 senaste dygnet i drift.json (som bara sparar 19 körningar); två startade sent, 6 november 12.10 (8 minuter) och 7 november 00.11 (9 minuter), ingen saknas. Autopiloten: 33 publicerade, 4 stoppade, 1 i kön. Behöver dig: sex notiser väntar (äldst 69 timmar), två troliga hopslagningar (Paraguays president avsatt, bombhot mot flyg och medier), fem tysta källor (CNN, WHO, Microsoft AI, Svenska kraftnät, Der Spiegel International) och båda Instagramkontona saknar secrets (30 svenska och 28 engelska kort väntar). 126 av 143 källor går att läsa; nya fel sedan igår: RNZ (inga artiklar) och The East African (403). Meta: appen Newsnavigator är skapad med Instagram-användningsfallet, men fliken "API setup with Instagram login" finns inte längre. Den heter nu "API setup with Unified login" och kräver en företagsportfölj innan "Add account" syns. Det är Chrome-agentens avläsning av din skärm, inte något jag kunnat se själv. Nästa steg för dig: skapa en gratis företagsportfölj (inte verifierad) och koppla den till appen. Ingenting nytt går att bygga utan dina secrets och beslut.

**6 november: allt tidsstämplas.** Notiser i alla listor, källorna på notissidan (`tid` på varje källa, sparas från och med nu), Instagramtexten och brevet har tid. Svensk tid i den svenska utgåvan, UTC i den engelska (`render.tidstext`, `render.stampel`). Notissidor består, och Rättelser finns (`rattelser.py`, `data/rattelser.json`).

**6 november, natt (nattsessionen).** Tester: 456 gröna. Klockan: alla timstarter kl :02 finns från 5 november 12.02 till 6 november 01.02 UTC (drift.json sparar bara de senaste 19 körningarna, så äldre timmar styrks av 35 Flöde-commits utan hål sedan 5 november 01.51). Sju extra körningar utanför :02 är manuella eller Källprov, inte försenade starter. Autopiloten: 28 publicerade, 3 stoppade, 10 i kön. Behöver dig: fem notiser väntar (äldst 25 timmar: Joshua Wong, borgmästarvalet i Los Angeles, Vance om kriget mot Iran), en trolig hopslagning (bombhot mot flyg i Europa), CNN, WHO och Microsoft AI tysta, och båda Instagramkontona saknar secrets (13 svenska och 12 engelska kort väntar). 128 av 143 källor går att läsa; felen är ESA och Mail & Guardian och Anthropic och Meta AI (404), Haaretz och Arab News och Import AI och Washington Times (403), VentureBeat AI (429, tillfälligt), Washington Post (502, tillfälligt), HuffPost och USGS (inga artiklar). Allt jag kan bygga utan dig är byggt: A1 till A4, B1 till B3, D och källläsaren är klara, A5 och Cloudflare-delen av C väntar på A0 och beslut från dig. Du är mitt i Meta-appen: skapa den med användningsfallet för Instagram (Metas guide har inget "Lägg till produkt" längre, se `docs/steg-for-steg.md` 1.2) och kör sedan Instagram, Run workflow, `kontroll = true`.

**6 november: viktigast först.** Sajten sorteras på Vikt som halveras per dygn (`utgava.viktighet`), Senaste är kronologisk och RSS likaså. Händelser märkta måste med går först i autopilotens kö och räknas inte mot taket; grindarna och vetofönstret gäller som vanligt.

**5 november kväll: bevakningsspåren.** Fem spår enligt ditt beslut (`spar.py`, princip 13, sidan /spar/): samarbete och fred, religion och våld, mänskliga rättigheter, miljön, teknikens utveckling med sju delspår. De väger som ett steg på konsekvensskalan och har två platser var i flödet, men ändrar inte notisernas text. Din sjätte punkt om kapitalism och kommunism är inte med i urvalet. Tio nya källor för spåren (143 totalt). Träffarna bygger på ordlistor i rubrikerna, så spåren missar det som inte nämner orden. Miljön följs som notiser, inte som mätvärden över tid.

**5 november (designgranskning och research).** Rättat: valnotiser stod under Vetenskap och Marknader (ett enstaka nyckelord räckte; nu krävs träff i var femte rubrik i stora händelser, och energi flyttar inte en världsnyhet), nordiska händelser får sektionsämnet sverige, förstasidan och Navigatorn visar högst två notiser per händelse (`newsletter.utan_upprepningar`), förstasidan och notissidan har h1, och sidfoten påstår inte längre att allt granskas före publicering (21 av 37 notiser i arkivet är automatiska). Instagramschemat postar bara när repo-variabeln `IG_SCHEMA` är 1 (steg 1.6b). Efter ditt beslut räcker två svenska källor för svensk inrikes (inte nöje eller utrikes), åtta platser i flödet hålls åt Sverige och Norden, och utgåvorna lyfter det som angår läsaren: svenskt på /sv/, det som minst tre regioner bevakar på /en/ (`utgava.angar`). Engelska utgåvan är global, utan hemland: en gemensam nivå för läsare var som helst. Brevet väljer per språk. Svaghet: en utrikeshändelse som bara nordiska källor skriver om kan hamna under Sverige, och två källor kan vara samma TT-text. Förstasidans toppnotis är i övrigt den senast godkända, inte den tyngsta. Navigatorn på webben är mejlmallen, utan sajtens navigering. Researchen ligger lokalt, inte i repot.

**5 november 01.45 UTC (nattsessionen).** Klockan: 35 Flöde-commits på 26 timmar, ett timhål (kl 11 UTC den 4 november), inga sena starter (de utanför :02 var mina egna körningar). Autopiloten: 20 publicerade, 2 stoppade, 14 i kön; taket är 8 per dygn sedan 4 november. Behöver dig: fyra notiser väntar (äldst 42 timmar), två "troligen hopslagna" (USA-valet med 23 och 26 källor, en enda berättelse), fyra tysta källor och båda Instagramkontona saknar secrets. 118 av 133 källor läsbara (ESA och The East African är nya fel). **Sammanhangsmått (ej använt):** klustren får `sammanhang` (medelcosinus mellan rubrikerna) för att kunna släppa igenom stora berättelser. Kalibrerat mot de handmärkta rubrikerna: 12 rena kluster låg mellan 0,47 och 0,88 (median 0,77), det enda blandade på 0,63, och de två stora valhändelserna på 0,44 och 0,53. Måttet skiljer alltså inte en hopslagning från en stor berättelse, så autopilotens grind (fler än 20 källor stoppar) är oförändrad; måttet sparas på händelsen som information. De två valhändelserna får du godkänna för hand tills vidare. 421 tester gröna.

**4 november kväll: beslut B och hybridklustringen är inkopplade.** (B) De 33 källor utan betalvägg vars robots.txt nämner Claude har `bara_rubrik: true` i feeds.yaml: ingressen skickas inte till modellen. (Hybriden) `semantisk.py` är ett andra varv efter reglerna och andra varvet: en flerspråkig inbäddning (MiniLM, `sentence-transformers`, installeras i pipeline.yml med cache och faller tyst tillbaka om den saknas) slår ihop kluster när cosinus är minst 0,60, minst två rubriker delar minst två ord och minst en fjärdedel av paren matchar. **Rättelse av min tidigare siffra:** jag jämförde mot ett för svagt utgångsläge. Dagens regler i produktion (inklusive andra varvet) har precision 0,98 och recall 0,875 på de handmärkta rubrikerna, inte 0,71; med hybriden är precisionen 0,98 och recallen 0,95. Förbättringen är alltså 8 procentenheter recall, inte 16. På riktiga data räcker det inte för stora händelser: USA-valet är kvar som 20 till 23 delhändelser (reaktioner, enskilda val, Vance), där rubrikparen matchar men bara 2 till 45 procent av alla par. Att slå ihop dem vore fel, för många är verkliga delhändelser. I stället flaggas en händelse inte längre som "saknas i svenska medier" när närliggande händelser har en svensk källa (minst två av dess rubriker matchar, cosinus 0,55); `perspektiv.grannar_svenska` visar det. Mätt i Actions: påståendet "saknas i svenska medier" föll från 13 av 40 händelser till 4 av 40 (17 markerades med svensk täckning hos grannar; de kvarvarande fyra är delhändelser som Maine-valet och Spaniens transportminister). Risken är att något verkligt blint hamnar bland de 17; det är medvetet, ett uteblivet påstående kostar mindre än ett felaktigt. Analys-stegen fick mer utrymme (max_tokens): 17 av 30 händelser fick en Analys-rad (före 14), 9 godkända (före 7), och berättelser 14 av 19, 11 godkända. NATO läses med webbläsare och är live (25 länkar).

**4 november, verktyg och experiment efter "gå igenom GitHub-repon".** (1) NATO läses nu med webbläsare (27 nyhetsrubriker, `sidlasare.py` med `rendera`). (2) GDELT som kontroll av "saknas i svenska medier": första försöket gav 1 stöd, 0 motsägelser, 13 oklara av 14, eftersom GDELT svarade 429 på takten (fyra av fem frågor) och rubrikerna ofta saknar egennamn ("Democrats win control of Congress"). Efter rättningen (längre vila, nya försök, egennamn ur källornas rubriker): 9 kontrollerade, GDELT stöder 6, motsäger 0, oklart 3. Men "stöder" är inte trovärdigt: GDELT hittar inga svenska artiklar om Trump och Republicans fast Ekot och DN skrivit om valet (3 av våra 13 valnotiser har svensk källa). GDELT-kontrollen används därför inte. Det den däremot avslöjade: 7 av dagens 9 påståenden om "saknas i svenska medier" gäller USA-valet, som svenska medier täckt. Orsaken är att klustringen delar valet i 13 fragment och bara 3 har en svensk källa. Det felaktiga påståendet i signaturen är alltså en följd av klustringens recall, och är det starkaste skälet att införa hybriden i (3). (3) Inbäddningar mot dagens klustring på 5 460 handmärkta par: dagens regler precision 1,00, recall 0,71, F1 0,83. Enbart inbäddningar (MiniLM, flerspråkig) når samma recall (0,70 till 0,72) vid precision minst 0,98, alltså ingen vinst. Hybriden "dagens regler ELLER (cosinus minst 0,55 och minst två gemensamma ord)" ger precision 0,98, recall 0,87, F1 0,92: 16 procentenheter mer recall (färre splittrade händelser) mot 2 procentenheter lägre precision (fler felaktiga sammanslagningar). Kostar torch och en modell (cirka 120 MB) i varje körning, så den är inte inkopplad; beslut åt dig. (4) Jämförelse A mot B (bara rubrik för de 33 som nämner Claude): 17 av 27 händelser berörs; osäkra utkast 2 mot 4, källkontroll godkänd 14 mot 12, klarar autopilotens grindar 5 mot 3, anmärkningar per händelse 0,24 mot 0,47, sammanfattningens längd oförändrad; bruset i de 10 oberörda händelserna var ±1. Liten men tydlig försämring, svagare än jag väntade.

**4 november (genomgång av hela källistan mot robots.txt, Actions, Källprov med `alla`).** 137 källor: 133 tillåter oss, 4 stänger ute oss och är därför borttagna (Euractiv, The Decoder, UN News, Balkan Insight; vi hämtade dem tidigare utan att kontrollera robots.txt vid körning, bara när en källa lades till). Ny Teknik är utesluten på ditt beslut. 133 källor kvar. 53 blockerar AI-botar (41 av dem Claude, 33 av dessa utan betalvägg). Beslut åt dig: se Du gör, punkt 2.

**4 november 01.45 UTC (nattsessionen).** Klockan: Flöde-commit varje timme i dygnet, inga hål, och de 19 körningar drift.json sparar är alla ok. Autopiloten: tolv publicerade automatiskt, två stoppade, fem i kön; taket höjs från 2 till 8 per dygn i kväll (en vecka efter start, 4 november cirka 21.30 UTC, inte klockan 00 som jag skrev tidigare). Behöver dig: fyra notiser väntar på dig, äldst 96 timmar, två hopslagna händelser väntar på uppdelning eller avvisning ("Trump säger att USA slutar med militärt stöd till Israel vid årets slut" och "Ossoff och Warner vinner omval i USA:s mellanårsval"), fem källor tysta, och båda Instagramkontona saknar secrets (tre kort väntar per konto). 118 av 138 källor går att läsa. Källprov i Actions hittade fungerande adresser för Federal Reserve (`press_monetary.xml` och `press_other.xml`) och Microsoft AI (`news.microsoft.com`), som nu ligger i `feeds.yaml`. Ny Teknik, Finansinspektionen, Mistral, IMF och NATO gav fortfarande 404 på de adresser jag prövade; Haaretz, Arab News, Import AI och Washington Times ger 403 och lämnas (vi respekterar källor som blockerar botar). Spår C (panelen) är parkerad: den kräver att du först bestämmer om panelen eller GitHub-ärendet är den som godkännandena går igenom, eftersom båda skriver `godkanda.json`. 282 tester gröna.

**3 november 01.45 UTC (nattsessionen).** Klockan: 36 Flöde-commits på 26 timmar, inga hål och ingen start mer än fem minuter sen (drift.json sparar bara de senaste 19 körningarna). Autopiloten: tio publicerade automatiskt, två stoppade, åtta i kön. Behöver dig: tre notiser väntar (äldst 32 timmar), sju källor tysta och båda Instagramkontona saknar secrets (tre svenska och två engelska kort väntar). 118 av 138 källor går att läsa; 17 ger fel, de flesta 404 (Ny Teknik, Finansinspektionen, NATO, Fed, IMF, Mail & Guardian, Anthropic, Meta AI, Mistral) eller 403 (Haaretz, Arab News, Import AI, Washington Times) och behöver nya flödesadresser som bara går att pröva i Actions (Källprov). 250 tester gröna.

2 november 02.00 UTC. Klockan: 24 av 25 starter i tid senaste dygnet; starten 08.02 UTC den 1 november uteblev och 09.02 kom två samtidigt, så en Cloudflare-start kom en timme sent (inte något vi kan se mer om härifrån). Autopiloten: åtta notiser publicerade automatiskt (en senaste dygnet, taket är två), sex manuellt godkända, två stoppade, fem i kön. Behöver dig: en notis väntar på ditt beslut (FN:s uppdrag i Västsahara, blind fläck) och fem källor har tystnat. Instagram postar inget: `IG_USER_ID` och `IG_ACCESS_TOKEN` saknas i repots secrets, tretton kort väntar. Vakthunden i `rapport.yml` har startat bara tre gånger på 18 timmar via GitHubs schema, så mejl vid fel kommer sent tills klockan startar den (Du gör, punkt 3). 117 av 138 källor går att läsa. 129 tester gröna.

Faserna byggs av en schemalagd Claude Code-session varje natt kl 02.41 svensk tid ("Newsnavigator: nattlig byggsession"), en fas per natt, i ordningen nedan. Den hoppar över faser som väntar på något under Du gör. Natten till 29 oktober gjorde den inget: den startade utan repo. Sedan dess körs den i den session som har repot. Den stoppas eller ändras i Claude-appen under schemalagda uppgifter.

## Du gör

Det här kan bara du göra. Det som står överst spärrar mest. Två ärenden väntar också på dig i GitHub: fyra notiser i granskningsärendet (två av dem är stora valhändelser med över 20 källor som autopiloten inte släpper igenom) och utvärderingen i ärende 2. Spår A0 i planen nedan är den kritiska vägen för målet att ha minst 56 inlägg per konto idag.

1. **Meta och Instagram, båda kontona (spår A0).** Skapa appen, lägg till båda kontona och lägg secrets `IG_USER_ID`, `IG_ACCESS_TOKEN`, `IG_USER_ID_EN`, `IG_ACCESS_TOKEN_EN` och `IG_APP_SECRET` i repots secrets (GitHub: Settings, Secrets and variables, Actions). Stegen står i `docs/steg-for-steg.md` (1.2 och 1.3) och under A0. Meta kräver nu en gratis företagsportfölj (Newsnavigator, ej verifierad) innan "Add account" syns under "API setup with Unified login". Därefter kontrollerar du allt utan att publicera: Actions, Instagram, Run workflow, `kontroll = true` (visar vilket konto varje token hör till, kontotyp och kvarvarande kvot). `IG_APP_SECRET` behövs inte än.
2. ~~Källor som stänger ute AI-botar~~ Avgjort 4 november: alternativ B. De 33 källor som nämner Claude är bara rubrik.
3. ~~Tre beslut~~ Besvarade med ja 3 november. Du bläddrar alltså igenom korten själv före godkännandet (steg 1.6 i `docs/steg-for-steg.md`).
4. **Morgonrapporten (fas 5).** Resend-konto, API-nyckel med "Sending access", secrets `RESEND_API_KEY` och `RAPPORT_TILL`. Prova med Actions, Rapport, Run workflow, "torrt".
5. **Klockan, tre minuter.** Nya `klocka/worker.js` i Cloudflare-Workern (Edit code, Deploy), så startar klockan rapporten kl 07.00 och vakthunden varje timme.
6. **Utvärdera berättelserna (B3, cirka 20 minuter).** Ärendet "Utvärdering: berättelserna" (nummer 2, under Issues) finns redan med 30 händelser. Bocka stämmer eller missvisar för varje händelse, kör sedan Actions, Utvärdering, Run workflow, `lage=rakna`. Det avgör om berättelserna, tesen, får visas.
7. **Panelen (spår C).** GitHub-nyckeln i Pages-projektet `redaktionen` och Access med din adress.

## Tesen och utgåvorna

**Tesen.** Kombinerar man tillräckligt bra källor kan AI analysera dem och hitta berättelsen, eller de olika berättelserna. Newsnavigator ska därför ge tre lager per händelse: fakta (kärnan som källorna är överens om, källkontrollerad), berättelser (två till fyra sätt att berätta händelsen, vilka medier och regioner som bär dem och vad de lyfter fram) och betydelse (vad händelsen innebär för just den här läsaren, märkt Analys och spårbar till källorna).

**Tonen: en modern global text-tv.** Text-tv i Sverige är kortfattad, utan trams och något man litar på. Så ska Newsnavigator vara: rubrik, ett par rader fakta och källor, öppet om hur notisen granskats, inga slogans, hashtaggar eller utfyllnad. Bildtexten på Instagram är därför bara rubrik, sammanfattning, en enda mening om var källorna skiljer sig åt (och ingen alls när de är eniga), källor, länk och granskningsrad. "USA: blått och rött" visas bara när det är relevant: rubriken handlar om amerikanska aktörer, politik eller ekonomi och minst tre amerikanska medier med både en blå och en röd publik enligt AllSides har skrivit om händelsen (`utgava.usa_relevant`, gäller notissidan, Instagramkortet och brevet). Av dagens nio händelser med någon USA-uppdelning visas tre. Förtroendet kommer av att det som står stämmer och är tillskrivet, inte av stil. Vi ber aldrig läsaren att dela, följa, spara eller svepa, varken i Instagramkort, bildtexter, brev eller på sajten; kortet pekar bara vidare med en sidhänvisning ("Nästa sida: så ser världen på det"). Räckvidden kommer av att det är bra och lätt att läsa, inte av att vi ber om den.

**Två läsare, två utgåvor.** De delar händelser men inte urval, språk eller konto.

| | Svenska utgåvan (@newsnavigator.se, newsnavigator.se/sv) | Engelska utgåvan (@news.navigator, newsnavigator.se/en) |
|---|---|---|
| Läsaren | Svensk som inte ser hur mycket världen påverkar henne eller honom | Amerikan (och brittisk) som inte får en tydlig, kort bild av världen |
| Urval | Svenska nyheter med minst två svenska källor, globala händelser som berör Sverige, Norden och Europa, och särskilt händelser som saknas i svenska medier (signaturen, 15 av 40 i dag) | Globala händelser med minst tre källor i två regioner. Svenskt och nordiskt bara när det påverkar läsaren (`relevans_en` 2 eller högre). Aldrig lokalt svenskt |
| Tillägg | Vad det betyder för dig i Sverige (Analys) | Hur resten av världen berättar händelsen, USA blått och rött, vad det betyder för dig (Analys). Kort: vad hände, vilka berättelser finns, vad är oklart |
| Grindar | Som autopilotens, men "blind fläck" är här innehållet, inte ett hinder: går till din batchgranskning | Samma utan grinden "saknas i svenska medier", som inte är ett påstående i den utgåvan. "Mest blå/röd publik" går fortfarande till dig |

## Siffror (mätt 2 november)

- Veckan som gick: 318 unika berättelser. 27 klarar alla grindar, 111 klarar allt utom blind fläck (runt 16 per dygn). Autopiloten publicerar i dag högst 2 per dygn (8 från 4 november).
- 56 inlägg per konto på ett dygn är alltså sju gånger vad grindarna släpper igenom på ett dygn. Det går som en lanseringsbatch ur veckans 111, per utgåva (olika urval), efter en enda genomgång av dig. Det går inte som nya notiser.
- Instagram: dokumenterad gräns är 100 API-publiceringar per 24 timmar och konto, en karusell räknas som ett inlägg. Metas sida anger också 50 på ett annat ställe, så `content_publishing_limit` kontrolleras per konto före start. Takt: ett inlägg var 8:e minut, alltså 56 på 7,5 timmar. Fler på kortare tid ökar risken att kontot flaggas som spam.

## Planen från 2 november

Mål idag: sajten fungerar som två utgåvor och båda Instagramkontona har minst 56 inlägg. Mål veckan: tesen, alltså berättelser och betydelse, på riktigt.

**Spår A: lansera idag (kritisk väg).**
- **A0. Du: Meta, båda kontona (cirka en timme, det enda jag inte kan göra).** Båda Instagramkontona ska vara professionella (Business eller Creator) och publika. På developers.facebook.com: skapa en app (typ Business, produkten Instagram), öppna "API setup with Instagram login", under "Generate access tokens" välj "Add account" och logga in på @newsnavigator.se, sedan på @news.navigator. Kopiera token och konto-id för varje konto. Lägg dem som secrets: `IG_USER_ID`, `IG_ACCESS_TOKEN` (svenska), `IG_USER_ID_EN`, `IG_ACCESS_TOKEN_EN` (engelska), och appens secret som `IG_APP_SECRET` (behövs för att byta kortlivat token mot 60-dagarstoken och förnya det). Stegen i Metas gränssnitt flyttas ibland; Metas dokumentation säger att Standard Access räcker för konton du äger och lagt till i appen, men att publicering i utvecklingsläge fungerar för egna konton är inte verifierat här.
- **A1. Utgåvor i koden. Klar 2 november.** `utgava.py`: `relevans` per händelse och utgåva (regler på var källorna finns och vad rubrikerna nämner; AI-förfining kan läggas ovanpå), `visa`, `grindar` per utgåva, `urval`. Mot veckans 318 berättelser: svenska utgåvan har 223 relevanta och 86 som klarar grindarna (varav 59 bär "saknas i svenska medier" och går till din genomgång), engelska utgåvan har 157 relevanta och 84 som klarar grindarna utan någon genomgång. Alltså räcker materialet till 56 per konto. Känd begränsning: autopiloten godkänner fortfarande globalt, så en berättelse med blind fläck publiceras inte automatiskt i engelska utgåvan förrän godkännandet blir per utgåva (spår D).
- **A2. Engelska kort och separata konton. Klar 2 november.** `instagram.py` har språk som parameter genom alla kort och captions (engelska rubriker, regionnamn, datum, USA blått och rött, utan svenska påståenden), korten ligger under `public/ig/<språk>/<id>/`, varje konto har eget tillstånd och egen status i `data/instagram/`, egna secrets, och `Behöver dig` och ångra fungerar per konto. Kontrollerat med riktiga renderade kort och i Actions 2 november 02.58 UTC: 10 svenska och 8 engelska kort byggdes, med eget tillstånd per konto. Captions pekar på `/sv/n/<id>/` och `/en/n/<id>/`, som skapas i A4: ingenting postas innan dess.
- **A3. Lanseringsbatchen.** `lansering.py`: väljer de 56 bästa per konto ur veckan (variation i sektion, högst tre per händelsefamilj), bygger korten, skriver en förhandsgranskningssida med alla 112 kort som du bläddrar igenom en gång. Därefter ett maraton som postar ett inlägg var 8:e minut per konto, i en egen concurrency-grupp så att timmens pipeline inte blockeras, med avbrott via tyst läge. Först ett testinlägg per konto. **Klar 2 november.** Torrkörning i Actions (valj, båda kontona): 56 + 56 valda, korten byggda, förhandsgranskningen på `/lansering/{sv,en}.html`; svenska kontot har 34 inlägg som kräver din genomgång (påståendet "saknas i svenska medier"), engelska 0. Sektionerna är skeva (varlden 36 av 56 svenska, 38 av 56 engelska) eftersom veckans material är det. Postning vägrar utan godkänd batch (verifierat). Körs i Actions → Lansering, i tre steg: `lage=valj` (väljer, bygger korten, förhandsgranskning på `/lansering/`), `lage=godkann` (med `uteslut=3,17` för det du stryker), `lage=posta` (`antal=1` som prov, sedan 56; `torrt=true` postar inget). Ett konto per körning (`konto=sv` eller `en`), de går parallellt och lämnar över till en ny körning efter 5,5 timmar. Inget postas utan godkänd batch, secrets, tyst läge noll, fri kvot och bilder på sajten; tre fel i rad stoppar; varje inlägg sparas i git direkt.
- **A4. Sajten.** `/sv/` och `/en/` som egna sajtträd med egna sektioner, flöden och sitemap, en utgåvsväljare på roten, länkar från båda Instagram-biografierna, `NN_LANSERAD=1` (tar bort noindex). Domänen kan inte nås från den här sessionen: antingen tillåter du `newsnavigator.se` i sessionens nätverksinställningar eller kontrollerar du själv att sidorna laddar. **Byggd 2 november, ej synlig på domänen än.** Träden `/sv/` och `/en/`, valsida i roten, sitemap och `_redirects` byggs av `publish.py` (tester i `tests/test_sajt_utgavor.py`). Kvar för dig: i Instagrambiografierna, länka @newsnavigator.se till `https://newsnavigator.se/sv/` och @news.navigator till `https://newsnavigator.se/en/`; sätt `NN_LANSERAD=1` i `pipeline.yml` när du vill öppna för sökmotorer (sker i A5, inte före).
- **A5. Verifiering.** Torrkörning av hela vägen, ett testinlägg per konto, kontroll av `content_publishing_limit`, sedan maraton.

**Spår B: tesen, vecka 1.**
- **B1. Berättelser.** Ett AI-steg per händelse med minst fyra källor: två till fyra berättelser med namn, vad de lyfter fram, vilka källor, regioner och AllSides-sidor som bär dem. Bara rubriker och ingresser, alltid tillskrivet, aldrig vad en källa utelämnar (promptregel 11), och källkontrollen utökas till att spåra tillskrivningarna. Visas på notissidan som "Berättelserna" och som kort två på Instagram. **Klar 2 november (`berattelser.py`), körd mot riktig modell i Actions.** Tredje prompten gav 11 händelser med berättelser av 40, 10 godkända av källkontrollen (första försöket 11 av 14 men mest detaljer från en enda källa, andra 4 av 13 underkända för tillskrivning till hela gruppen). Det är fortfarande mest tematiska grupperingar, inte tydligt motstridiga berättelser: det är det du bedömer i B3. Körs i pipelinen för upp till 30 händelser per körning med minst fyra oberoende källor i två regioner, cachas per källuppsättning. Koden, inte AI:n, räknar ut vilka källor, regioner och AllSides-sidor som bär varje berättelse; ord som pekar ut vad en källa utelämnar, tankstreck och "sanningen" underkänns i koden; en egen källkontroll läser tillskrivningarna. Sparas som `narrativ` på händelsen. Visas på notissidan ("Berättelserna") först när `NN_BERATTELSER=1` är satt, vilket görs efter B3. Instagramkort två för berättelserna byggs efter utvärderingen.
- **B2. Betydelse per läsare.** `betydelse_sv` och `betydelse_en`, kopplade till spårbara fakta (till exempel hur ECB:s besked hänger ihop med kronan). Ditt ja till Analys-raden kom 3 november och princip 4 är omskriven (PRINCIPER.md och Om-sidan). **Byggd 3 november (`betydelse.py`).** Ett AI-steg per händelse med minst tre oberoende källor ger en rad per läsare (svenska läsaren i Sverige, engelska läsaren i USA och Storbritannien) eller null om ingen direkt koppling finns. Koden underkänner råd, förutsägelser ("kommer att", "will"), värdeord, tankstreck och för långa rader, och en andra läsning kontrollerar sakuppgifterna mot källorna och utkastet. Sparas som `betydelse`; visas efter fakta på notissidan, märkt Analys eller Analysis med en förklaring, först när `NN_BETYDELSE=1` är satt (efter B3). Instagram får ingen Analys-rad än. Körd mot riktig modell i Actions 3 november: första prompten 4 av 10 godkända (kontrollen underkände oljepris till bränslepris som "saknar stöd"), andra 8 av 13 godkända, med rader som kopplar till läsaren (bränslepriser, säkerhetsläget i Europa, hur amerikanska val genomförs). Underkända rader var oftast långsökta kopplingar eller slutsatser om väljare, vilket är rätt. Det är fortfarande ett första utkast att bedöma i B3.
- **B3. Utvärdering.** Du granskar 30 händelser, vi mäter hur ofta berättelserna och betydelsen stämmer och justerar prompten innan de får gå automatiskt. **Verktyget byggt 3 november (`utvardering.py`, workflow Utvärdering).** `lage=skapa` skapar ärendet "Utvärdering: berättelserna" med 30 händelser (högsta poäng, högst 40 procent per sektion, bara berättelser som källkontrollen godkänt); varje händelse har två rutor, stämmer eller missvisar, och bedömda står kvar när ärendet uppdateras. `lage=rakna` räknar dina bockar och skriver `data/utvardering.json`. Rekommendationen att slå på `NN_BERATTELSER=1` kommer först vid minst 30 bedömda och minst 80 procent som stämmer. Analys-raderna utvärderas i samma ärende med egna rutor (`bstammer`/`bfel`) och egen räkning, och slås på var för sig.

**Källor utan flöde (klart 4 november).** `sidlasare.py` läser rubriklistan på en nyhetssida när flödet är borta; Finansinspektionen, IMF och Mistral går nu så (rubrik och länk, robots.txt först, datum är när länken först sågs). Ny Teknik provades men är utesluten på ditt beslut (betalvägg, och stänger ute AI-botar). NATO:s nyhetssida ritas med JavaScript och går inte att läsa utan webbläsare, så NATO står kvar som trasig källa. Haaretz, Arab News, Import AI och Washington Times blockerar botar och lämnas.

**Spår C: säkerhetsnät och panel (fas 5 och 6 ovan).** Resend-kontot, nya `klocka/worker.js`, panelen med Access. Lägre prioritet än A. Panelen är parkerad tills du bestämt vem som är källan för godkännanden (ärendet eller panelen, båda kan inte skriva `godkanda.json` samtidigt) och har lagt Cloudflare-nyckeln; den kan inte provas utan dem.

**Spår D: Instagram i drift.** Automatisk förnyelse av båda tokens (60 dagar) med `IG_APP_SECRET`, `content_publishing_limit` i `Behöver dig`, och att taket för automatiska notiser höjs efter 4 november. **Förnyelsen byggd 3 november (`igtoken.py`, workflow Instagram-token, måndagar 04.17 UTC):** förlänger varje kontos token hos Meta med 60 dagar, sparar utgångsdatum i `data/instagram/status-<språk>.json` så att Behöver dig varnar (före bara läsning, ingen skrev datumet) och markerar `token_bytt` om Meta svarar med ett annat token än det vi har. Repots secrets kan Actions inte skriva utan en särskild nyckel, så i det fallet ber Behöver dig dig lägga in det nya. Ej verifierad mot Instagram förrän secrets finns. Taket höjs av sig självt 4 november (en vecka efter autopilotens start). Kvar: `content_publishing_limit` per konto i Behöver dig, när secrets finns.

**Beslut från dig, i den här ordningen:**
Alla tre besvarade med ja den 3 november:
1. 56 idag är en lanseringsbatch ur veckan som gått, inte nya notiser.
2. Du bläddrar igenom de 112 korten en gång före maratonet (cirka 20 minuter).
3. Analys-raden "vad det betyder för dig" är tillåten, märkt Analys (princip 4 omskriven). Den visas först efter utvärderingen.

## Faser

Fas 4 (engelska Instagram) och fas 6 och 7 (panelen) ersätts av spår A och C ovan; de äldre beskrivningarna står kvar som underlag.

Målet: aggregatorn, sajten, Navigatorn och båda Instagramkontona går av sig själva. Panelen blir platsen där du stoppar, rättar och ångrar, inte där allt måste godkännas. Ordningen följer det: först det som gör att något alls publiceras utan dig, sedan säkerhetsnätet, sist panelens bekvämligheter.

**Fas 0: grunden. Klar 26 oktober.** Parvis klustring med majoritetsregel, högst tre sektioner per kluster, `kallstatus.json`, och `drift.json` från alla tre workflows.

**Fas 1: samma händelse en gång (en session). Byggd 28 oktober till 1 november.** `merge_clusters` slår ihop uppdelade kluster, och en händelse som redan är publicerad känns igen mot arkivet (`match_archive` i `pipeline.py`: minst hälften gemensamma artiklar, eller minst tre gemensamma källor och rubriker som delar hälften av orden). Den får då arkivets id, arkivposten uppdateras med de nya källorna medan den publicerade texten står kvar, och notissidan visar "Uppdaterad kl". Bakgrund: 30 oktober 00.06 publicerades Lagardes avgång, och en timme senare stod samma händelse i autopilotens kö under nytt id med 15 av 17 artiklar gemensamma. Orsaken är att historikposterna i `vikt.py` slår ihop källor och ord från olika händelser till samlingsposter (räntebeskedet och Lagarde matchade samma post), så id via historiken är opålitligt. Sedan 1 november håller id:t också mot det du sett i ärendet: `las` sparar rubrik och källor per id i `data/bockar.json`, och `reclaim_ids` i `pipeline.py` ger en ändrad händelse samma id igen när hälften av artiklarna eller 60 procent av rubrikens ord är gemensamma, så att bockar och veton följer med (30 oktober gick två godkännanden förlorade så). Verifierat 1 november 01.48 UTC: `bockar.json` skrivs varje körning med alla 40 poster; inga falska träffar mot dagens flöde. Mätt 2 november över 45 flödesversioner: delberättelser av samma händelse (räddningsarbetet, samtalet från kontrollrummet, de saknade vid Toledo) blir egna kluster med två artiklar, men de klarar inte autopilotens grind om tre oberoende källor och publiceras därför inte. Ingen riktig dubblett med tre källor vardera hittades, så klustringen lämnas som den är. Kvar: historiken borde hålla en post per händelse, och ett andra varv som missar: 28 oktober 21.34 låg Bolsonaros avresa i två kluster med tre gemensamma källor. Klart när: en händelse som får en ny källa behåller sin notis och sin adress, verifierat i drift. Verifierat 30 oktober 01.50 UTC: Lagarde-dubbletten lämnade kön, arkivposten fick nya källor och notissidan visar Uppdaterad.

**Fas 2: en klocka som går. Klar 31 oktober.** Cloudflare-Workern i `klocka/` startar pipelinen varje hel timme kl :02 och Instagram 07.45 svensk tid via workflow_dispatch; GitHubs egna scheman ligger kvar som reserv. Kriteriet uppfyllt: 53 väntade starter från 28 oktober 21.02 till 31 oktober 01.02 UTC, ingen missad, ingen mer än fem minuter sen. Tre körningar fallerade i pushen (29 och 30 oktober 06.02, 30 oktober 17.02) när reservschemat råkade starta en körning minuterna före klockan: `git pull --rebase` fick konflikter i `data/` och `public/`. Rättat 31 oktober: sparsteget i alla workflows låter den senaste körningen vinna (`-X theirs`), eftersom allt som sparas byggs om varje körning och ärendet är sanningen för bockarna. Kvar: rapporten 07.00 och Navigatorn 07.30 läggs till i klockan när fas 5 finns.

**Fas 3: autopiloten (en session). Byggd 28 oktober och påslagen med tak två per dygn: `autopilot.py` med grindarna som ren funktion, kön med 45 minuters vetofönster i granskningsärendet, tyst läge, ångra (`angra.yml`) och märkningen per notis på sajten, i brevet och på korten. Vid bygget klarade 3 av 40 händelser grindarna; första automatiska publiceringen 28 oktober 23.07 UTC. Kvar: en vecka utan ingrepp.** Grindarna i avsnittet Autopiloten som ren funktion med tester, taket, tyst läge (`data/autopilot.json`) och ångra. Tills panelen finns är granskningsärendet vetofönstret: notiser som klarar grindarna står där med klockslag och publiceras om du inte bockar ur dem. Tak två per dygn första veckan, sedan åtta. Klart när: en vecka utan ingrepp har gett notiser på sajten och i Navigatorn, och inga som borde ha stoppats. Princip 7 omskriven 28 oktober: automatiskt publicerade notiser märks "Sammanfattad med hjälp av AI och källkontrollerad. Publicerad utan manuell granskning; rättelser syns." Märkningen per notis på sajten, i Navigatorn och på Instagramkorten byggs i den här fasen; i dag står "granskad av redaktionen" överallt.

**Fas 4: Instagram av sig självt, två konton (en session).** Svenska kort och captions till @newsnavigator.se, engelska till @news.navigator (de engelska utkasten finns redan), postningsstatus per konto, och en workflow som förnyar båda tokens varannan vecka. Postar bara publicerade notiser. Klart när: båda kontona har postat varje dag i en vecka utan ingrepp. Du gör: secrets för det engelska kontot (`IG_USER_ID_EN`, `IG_ACCESS_TOKEN_EN`), kontrollerar att `IG_USER_ID` och `IG_ACCESS_TOKEN` hör till @newsnavigator.se, och skapar en token som får skriva repots secrets, så att förnyelsen kan spara de nya tokens.

**Fas 5: säkerhetsnätet (en session). Byggd 1 november, utskicket väntar på Resend.** `behover.py` bygger listan Behöver dig av regler (`data/behover.json`, varje timme, och överst i granskningsärendet): måste-med-notiser som väntat över två timmar eller hållits tillbaka av taket, körningar som fallerat två gånger i rad, klockan som stannat, hopslagna händelser, tysta källor (tre dygn för nyhetsmedier, fjorton för primärkällor), Instagram-token som löper ut och Instagram utan secrets (nytt: `data/instagram_status.json` skrivs av varje postningsvarv), för få notiser till Navigatorn, rättelser (öppna ärenden märkta `rättelse`) och tyst läge. `rapport.yml` mejlar morgonrapporten kl 07.00 ("Allt kört." när listan är tom) och varnar direkt för allvarliga rader, en gång per fel och igen efter tolv timmar. Klockan startar rapporten kl 07.00 när du klistrat in nya `klocka/worker.js`; GitHubs scheman är reserv och vakthund varje timme. Klart när: ett medvetet fel i en körning ger ett mejl inom en timme, och morgonrapporten kommer varje morgon kl 07.00. Verifierat 1 november 07.13 UTC i Actions: pipelinen skriver listan varje timme och visar den överst i ärendet; Rapport körs med "torrt" (skriver ut mejlet) och utan secrets (säger att de saknas och lyckas ändå). Kvar: det är inte provat med riktiga mejl, eftersom `RESEND_API_KEY` och `RAPPORT_TILL` saknas; allt annat är testat (45 tester). Navigatorn till prenumeranter kräver en egen domän och en målgrupp i Resend och byggs separat. Du gör: skapar Resend-kontot och lägger `RESEND_API_KEY` och `RAPPORT_TILL` (din mejladress) i repots secrets. Utan verifierad domän når Resends testavsändare bara kontots egen adress, vilket räcker för rapporten.

**Fas 6: panelen och inkorgen (en till två sessioner).** Pages-projektet `redaktionen` med Access (guiden finns, skalet är uppe), `flode.ts`, `godkann.ts`, `redigera.ts` och sidan Inkorg. Inkorgen visar vad autopiloten publicerat och vad som väntar, med stoppa, redigera, godkänn och ångra. Klart när: en rättad rubrik i mobilen syns på sajten, i Navigatorn och på Instagram inom fem minuter. Du gör: GitHub-nyckeln i Pages och Access med din adress.

**Fas 7: driften, källorna och planeringen i panelen (en session var).** Sidan Drift (`drift.ts`), sidan Källor med pausa och återstarta, och veckovyn med en rad per Instagramkonto (`data/plan.json`). Klart när: en pausad källa försvinner ur nästa körning och återkommer när den startas, och en flyttad karusell postas den dag du satt den.

Efter fas 7 kan reelsgeneratorn (9:16-video av korten) byggas som en egen session; den rör inte panelen.

**Vikt (klar 28 oktober).** Rangordningen bygger på `vikt.py`: bredd i förhållande till varje regions källor, uthållighet i timmar (`data/historik.json`), konsekvens enligt AI utifrån rubrikerna, och källkontrollens bekräftelse. Golvregeln Måste med (minst fem regioner och åtta källor, eller två primärkällor, och konsekvens minst 3) märks i granskningsärendet och blir en regel i Behöver dig i fas 5. Kvar: kvällskontrollen mot Wikipedias Current events.

Små saker utan egen fas: platserna i Nöje och spel delas mellan spel och nöje (i dag tar nöjet alla fyra), och ett beslut om källor som stänger ute AI-botar ska gå som bara rubrik.

## Så briefar du Claude Code

En fas per session, och börja varje session med samma tre rader: läs `CLAUDE.md`, läs `docs/redaktionen.md` fas N, och lista vad som finns innan något byggs. Be om acceptanskriteriet som test innan koden. Allt på svenska i gränssnittet, inga tankstreck, samma form som sajten (`render.py` är källan till färger och typografi). Secrets skrivs aldrig i kod eller i chatten: du lägger dem själv i GitHub och Cloudflare. Commits små och i presens, som i repot.

## Risker och svar

- **Två skrivningar krockar** (panelen och pipelinen commit:ar samtidigt): funktionerna skriver med sha-kontroll och gör om försöket; pipelinen gör redan `git pull --rebase`.
- **GitHub-nyckeln läcker:** den ligger bara i Pages, är begränsad till ett repo, och roteras var tredje månad (en rad i Behöver dig).
- **Latens:** två till tre minuter från beslut till sajt är acceptabelt för en morgonredaktion; panelen visar status så att det inte känns trasigt.
- **Instagram-token** löper ut efter sextio dagar: förnyelsen är ett API-anrop som workflowen kan göra själv varannan vecka, med en rad i Behöver dig om den misslyckas.
- **Autopiloten publicerar fel:** grindarna är konservativa, taket lågt, allt märkt och ångringsbart, och de skarpaste påståendena (blinda fläckar) går aldrig utan dig.
