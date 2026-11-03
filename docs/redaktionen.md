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
- Minst tre oberoende källor, varav minst en som inte är en kuraterad lista, och minst två regioner. Svenska nyheter: minst två svenska källor.
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

**3 november 01.45 UTC (nattsessionen).** Klockan: 36 Flöde-commits på 26 timmar, inga hål och ingen start mer än fem minuter sen (drift.json sparar bara de senaste 19 körningarna). Autopiloten: tio publicerade automatiskt, två stoppade, åtta i kön. Behöver dig: tre notiser väntar (äldst 32 timmar), sju källor tysta och båda Instagramkontona saknar secrets (tre svenska och två engelska kort väntar). 118 av 138 källor går att läsa; 17 ger fel, de flesta 404 (Ny Teknik, FI, NATO, Fed, IMF, Anthropic, Meta AI, Mistral, Mejlgänget) eller 403 (Haaretz, Arab News, Import AI, Washington Times) och behöver nya flödesadresser som bara går att pröva i Actions (Källprov). 250 tester gröna.

2 november 02.00 UTC. Klockan: 24 av 25 starter i tid senaste dygnet; starten 08.02 UTC den 1 november uteblev och 09.02 kom två samtidigt, så en Cloudflare-start kom en timme sent (inte något vi kan se mer om härifrån). Autopiloten: åtta notiser publicerade automatiskt (en senaste dygnet, taket är två), sex manuellt godkända, två stoppade, fem i kön. Behöver dig: en notis väntar på ditt beslut (FN:s uppdrag i Västsahara, blind fläck) och fem källor har tystnat. Instagram postar inget: `IG_USER_ID` och `IG_ACCESS_TOKEN` saknas i repots secrets, tretton kort väntar. Vakthunden i `rapport.yml` har startat bara tre gånger på 18 timmar via GitHubs schema, så mejl vid fel kommer sent tills klockan startar den (Du gör, punkt 3). 117 av 138 källor går att läsa. 129 tester gröna.

Faserna byggs av en schemalagd Claude Code-session varje natt kl 02.41 svensk tid ("Newsnavigator: nattlig byggsession"), en fas per natt, i ordningen nedan. Den hoppar över faser som väntar på något under Du gör. Natten till 29 oktober gjorde den inget: den startade utan repo. Sedan dess körs den i den session som har repot. Den stoppas eller ändras i Claude-appen under schemalagda uppgifter.

## Du gör

Det här kan bara du göra. Det som står överst spärrar mest. Spår A0 i planen nedan är den kritiska vägen för målet att ha minst 56 inlägg per konto idag.

1. **Meta och Instagram, båda kontona (spår A0).** Skapa appen, lägg till båda kontona och lägg secrets `IG_USER_ID`, `IG_ACCESS_TOKEN`, `IG_USER_ID_EN`, `IG_ACCESS_TOKEN_EN` och `IG_APP_SECRET` i repots secrets (GitHub: Settings, Secrets and variables, Actions). Stegen står under A0.
2. **Tre beslut** (längst ned i planen): lanseringsbatch ur veckan, en genomgång av de 112 korten, och Analys-raden.
3. **Morgonrapporten (fas 5).** Resend-konto, API-nyckel med "Sending access", secrets `RESEND_API_KEY` och `RAPPORT_TILL`. Prova med Actions, Rapport, Run workflow, "torrt".
4. **Klockan, tre minuter.** Nya `klocka/worker.js` i Cloudflare-Workern (Edit code, Deploy), så startar klockan rapporten kl 07.00 och vakthunden varje timme.
5. **Utvärdera berättelserna (B3, cirka 20 minuter).** Actions, Utvärdering, Run workflow, `lage=skapa`. Öppna ärendet "Utvärdering: berättelserna" under Issues, bocka stämmer eller missvisar för varje händelse, kör sedan `lage=rakna`. Det avgör om berättelserna, tesen, får visas.
6. **Panelen (spår C).** GitHub-nyckeln i Pages-projektet `redaktionen` och Access med din adress.

## Tesen och utgåvorna

**Tesen.** Kombinerar man tillräckligt bra källor kan AI analysera dem och hitta berättelsen, eller de olika berättelserna. Newsnavigator ska därför ge tre lager per händelse: fakta (kärnan som källorna är överens om, källkontrollerad), berättelser (två till fyra sätt att berätta händelsen, vilka medier och regioner som bär dem och vad de lyfter fram) och betydelse (vad händelsen innebär för just den här läsaren, märkt Analys och spårbar till källorna).

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
- **B2. Betydelse per läsare.** `betydelse_sv` och `betydelse_en`, kopplade till spårbara fakta (till exempel hur ECB:s besked hänger ihop med kronan). Kräver ditt beslut om princip 4: en rad märkt Analys, med AI-märkning, är tillåten i flödet.
- **B3. Utvärdering.** Du granskar 30 händelser, vi mäter hur ofta berättelserna och betydelsen stämmer och justerar prompten innan de får gå automatiskt. **Verktyget byggt 3 november (`utvardering.py`, workflow Utvärdering).** `lage=skapa` skapar ärendet "Utvärdering: berättelserna" med 30 händelser (högsta poäng, högst 40 procent per sektion, bara berättelser som källkontrollen godkänt); varje händelse har två rutor, stämmer eller missvisar, och bedömda står kvar när ärendet uppdateras. `lage=rakna` räknar dina bockar och skriver `data/utvardering.json`. Rekommendationen att slå på `NN_BERATTELSER=1` kommer först vid minst 30 bedömda och minst 80 procent som stämmer. Betydelsen (B2) utvärderas på samma sätt när den finns.

**Spår C: säkerhetsnät och panel (fas 5 och 6 ovan).** Resend-kontot, nya `klocka/worker.js`, panelen med Access. Oförändrat, men lägre prioritet än A.

**Spår D: Instagram i drift.** Automatisk förnyelse av båda tokens (60 dagar) med `IG_APP_SECRET`, `content_publishing_limit` i `Behöver dig`, och att taket för automatiska notiser höjs efter 4 november.

**Beslut från dig, i den här ordningen:**
1. 56 idag tolkas som lanseringsbatch ur veckan som gått, inte nya notiser (rekommenderas).
2. Du bläddrar igenom de 112 korten en gång före maratonet, i stället för att enbart lita på grindarna (rekommenderas, cirka 20 minuter).
3. Analys-raden "vad det betyder för dig" tillåts, märkt Analys (princip 4). Spår B2 väntar på det.

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
