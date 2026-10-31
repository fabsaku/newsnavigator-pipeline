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

31 oktober 02.00 UTC. Klockan: 53 av 53 starter i tid sedan 28 oktober 21.02 UTC, fas 2 klar. Autopiloten: fem notiser publicerade automatiskt, två manuellt godkända, två stoppade i ärendet (vetot fungerar), fyra i kön. Två godkännanden i ärendet (650f3392c8, cbdd567177) gäller id som inte längre fanns i flödet när de lästes, så de notiserna publicerades aldrig; det är fas 1:s id-fel från ett annat håll. Instagram postar inget: `IG_USER_ID` och `IG_ACCESS_TOKEN` saknas i repots secrets. 118 av 138 källor går att läsa. 84 tester gröna.

Faserna byggs av en schemalagd Claude Code-session varje natt kl 02.41 svensk tid ("Newsnavigator: nattlig byggsession"), en fas per natt, i ordningen nedan. Den hoppar över faser som väntar på något under Du gör. Natten till 29 oktober gjorde den inget: den startade utan repo. Sedan dess körs den i den session som har repot. Den stoppas eller ändras i Claude-appen under schemalagda uppgifter.

## Du gör

Det här kan bara du göra. Det som står överst spärrar mest.

1. **Instagram, svenska kontot.** Lägg `IG_USER_ID` och `IG_ACCESS_TOKEN` för @newsnavigator.se i repots secrets (GitHub: Settings, Secrets and variables, Actions). Utan dem postas inget, trots att korten byggs varje morgon.
2. **Instagram, engelska kontot (fas 4).** Secrets `IG_USER_ID_EN` och `IG_ACCESS_TOKEN_EN` för @news.navigator på samma ställe.
3. **Resend (fas 5).** Skapa ett Resend-konto, verifiera underdomänen för avsändaren, och lägg `RESEND_API_KEY` i repots secrets.
4. **Panelen (fas 6).** GitHub-nyckeln i Pages-projektet `redaktionen` och Access med din adress, enligt guiden du fått.

## Faser

Målet: aggregatorn, sajten, Navigatorn och båda Instagramkontona går av sig själva. Panelen blir platsen där du stoppar, rättar och ångrar, inte där allt måste godkännas. Ordningen följer det: först det som gör att något alls publiceras utan dig, sedan säkerhetsnätet, sist panelens bekvämligheter.

**Fas 0: grunden. Klar 26 oktober.** Parvis klustring med majoritetsregel, högst tre sektioner per kluster, `kallstatus.json`, och `drift.json` från alla tre workflows.

**Fas 1: samma händelse en gång (en session). Byggd 28 och 30 oktober.** `merge_clusters` slår ihop uppdelade kluster, och en händelse som redan är publicerad känns igen mot arkivet (`match_archive` i `pipeline.py`: minst hälften gemensamma artiklar, eller minst tre gemensamma källor och rubriker som delar hälften av orden). Den får då arkivets id, arkivposten uppdateras med de nya källorna medan den publicerade texten står kvar, och notissidan visar "Uppdaterad kl". Bakgrund: 30 oktober 00.06 publicerades Lagardes avgång, och en timme senare stod samma händelse i autopilotens kö under nytt id med 15 av 17 artiklar gemensamma. Orsaken är att historikposterna i `vikt.py` slår ihop källor och ord från olika händelser till samlingsposter (räntebeskedet och Lagarde matchade samma post), så id via historiken är opålitligt. Kvar: historiken borde hålla en post per händelse; en bock i ärendet på ett id som bytts innan `las` läser det går förlorad (30 oktober: två godkännanden utan notis); och ett andra varv som missar: 28 oktober 21.34 låg Bolsonaros avresa i två kluster med tre gemensamma källor. Klart när: en händelse som får en ny källa behåller sin notis och sin adress, verifierat i drift. Verifierat 30 oktober 01.50 UTC: Lagarde-dubbletten lämnade kön, arkivposten fick nya källor och notissidan visar Uppdaterad.

**Fas 2: en klocka som går. Klar 31 oktober.** Cloudflare-Workern i `klocka/` startar pipelinen varje hel timme kl :02 och Instagram 07.45 svensk tid via workflow_dispatch; GitHubs egna scheman ligger kvar som reserv. Kriteriet uppfyllt: 53 väntade starter från 28 oktober 21.02 till 31 oktober 01.02 UTC, ingen missad, ingen mer än fem minuter sen. Tre körningar fallerade i pushen (29 och 30 oktober 06.02, 30 oktober 17.02) när reservschemat råkade starta en körning minuterna före klockan: `git pull --rebase` fick konflikter i `data/` och `public/`. Rättat 31 oktober: sparsteget i alla workflows låter den senaste körningen vinna (`-X theirs`), eftersom allt som sparas byggs om varje körning och ärendet är sanningen för bockarna. Kvar: rapporten 07.00 och Navigatorn 07.30 läggs till i klockan när fas 5 finns.

**Fas 3: autopiloten (en session). Byggd 28 oktober och påslagen med tak två per dygn: `autopilot.py` med grindarna som ren funktion, kön med 45 minuters vetofönster i granskningsärendet, tyst läge, ångra (`angra.yml`) och märkningen per notis på sajten, i brevet och på korten. Vid bygget klarade 3 av 40 händelser grindarna; första automatiska publiceringen 28 oktober 23.07 UTC. Kvar: en vecka utan ingrepp.** Grindarna i avsnittet Autopiloten som ren funktion med tester, taket, tyst läge (`data/autopilot.json`) och ångra. Tills panelen finns är granskningsärendet vetofönstret: notiser som klarar grindarna står där med klockslag och publiceras om du inte bockar ur dem. Tak två per dygn första veckan, sedan åtta. Klart när: en vecka utan ingrepp har gett notiser på sajten och i Navigatorn, och inga som borde ha stoppats. Princip 7 omskriven 28 oktober: automatiskt publicerade notiser märks "Sammanfattad med hjälp av AI och källkontrollerad. Publicerad utan manuell granskning; rättelser syns." Märkningen per notis på sajten, i Navigatorn och på Instagramkorten byggs i den här fasen; i dag står "granskad av redaktionen" överallt.

**Fas 4: Instagram av sig självt, två konton (en session).** Svenska kort och captions till @newsnavigator.se, engelska till @news.navigator (de engelska utkasten finns redan), postningsstatus per konto, och en workflow som förnyar båda tokens varannan vecka. Postar bara publicerade notiser. Klart när: båda kontona har postat varje dag i en vecka utan ingrepp. Du gör: secrets för det engelska kontot (`IG_USER_ID_EN`, `IG_ACCESS_TOKEN_EN`), kontrollerar att `IG_USER_ID` och `IG_ACCESS_TOKEN` hör till @newsnavigator.se, och skapar en token som får skriva repots secrets, så att förnyelsen kan spara de nya tokens.

**Fas 5: säkerhetsnätet (en session).** Reglerna för Behöver dig, `rapport.yml` och morgonrapporten med Resend, plus ett mejl direkt när en körning fallerat två gånger i rad. Navigatorn kan börja skickas med samma Resend-konto i samma session. Klart när: ett medvetet fel i en körning ger ett mejl inom en timme, och morgonrapporten kommer varje morgon kl 07.00. Du gör: skapar Resend-kontot och lägger `RESEND_API_KEY` i repots secrets.

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
