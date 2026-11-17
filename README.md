# Newsnavigator pipeline v0.2

Hämtar nyheter från drygt 60 källor i sju regioner, grupperar artiklar om samma händelse, skriver neutrala AI-utkast och låter redaktionen granska innan något publiceras.

**Vi levererar nyheterna. Vad läsaren gör av dem är upp till läsaren.** Reglerna står i [PRINCIPER.md](PRINCIPER.md) och styr både redaktionen och AI:n.

## Så fungerar det

1. **Hämta** (`pipeline.py`): läser RSS från källorna i `feeds.yaml`. Från betalväggskällor används bara rubrik och länk.
2. **Gruppera**: artiklar om samma händelse slås ihop, en källa per händelse.
3. **Tagga och rangordna**: ämnen från källan och nyckelord. Rangordningen är Vikt (`vikt.py`): bredd i förhållande till regionernas källor, hur många timmar händelsen hållit i sig, konsekvens enligt AI utifrån rubrikerna, och källkontrollens bekräftelse. Rätt före först.
4. **Utkast**: om `ANTHROPIC_API_KEY` finns skriver AI:n rubrik och sammanfattning på svenska och engelska, och noterar om källorna är oeniga. AI:n får bara rubriker och ingresser, aldrig hela artiklar.
5. **Granska** (`granska.py`): inget publiceras utan att du har godkänt det.
6. **Publicera**: `site/publicerat.html` innehåller bara godkända notiser, med källor och AI-märkning.

## Kom igång på din dator

```bash
pip install -r requirements.txt
python verify_feeds.py            # vilka källor fungerar? se data/kallstatus.json
python pipeline.py                # bygger data/flode.json och site/index.html
python granska.py lista           # läs utkasten
python granska.py godkann ID ID   # godkänn
python granska.py publicera       # bygg site/publicerat.html
```

Med AI-utkast: `export ANTHROPIC_API_KEY=...` innan `pipeline.py`. Modell väljs med `NN_MODEL` (standard `claude-haiku-5-5`).

Testa utan internet: `python pipeline.py --feeds tests/feeds-test.yaml --max-age-hours 0`

Tester: `pip install pytest` och sedan `python -m pytest tests`. Klustringen testas mot riktiga rubriker i
`tests/kluster-rubriker.json`, där varje rubrik är märkt med vilken händelse den handlar om.

Driftstatus: alla tre workflows skriver `data/drift.json` (`drift.py`) i slutet av varje körning, även när körningen fallerar:
senaste körningen per workflow, och de tjugo senaste körningarna med status, tider och länk till loggen.

## Kör automatiskt

1. Skapa ett privat repo på GitHub och lägg upp filerna.
2. Under Settings, Secrets, lägg till `ANTHROPIC_API_KEY`.
3. `.github/workflows/pipeline.yml` kör pipelinen en gång per dygn i två steg (03.17 och 04.47 UTC: kö, sedan publicering efter vetofönstret), och källkontrollen på den första. Utkast och översättningar sparas i `data/cache.json`, så bara nya eller ändrade händelser skickas till AI:n.

## Nästa version

- Gruppering över språk (svensk och engelsk rubrik om samma händelse).
- Kombinationer: AI föreslår kopplingar mellan händelser, du skriver ingressen.
- Raden "Vad betyder det för Sverige och Europa?" som eget, granskat fält.
- Koppla flödet till sajtens design i stället för förhandsvisningen.

## Formen
`render.py` är den gemensamma formen: stilmall och notiskomponenter (toppnotis, utvald, rad i rubriklista, hel notis) som
både sajten och den interna förhandsvisningen (`site/index.html`, alla utkast med ämnesfilter) använder.
Formen är en tidningssida i svartvitt, mörk först: Source Serif 4 för rubriker och löptext, Source Sans 3 för navigation
och meta, ingen monospace och inga versaletiketter. Sidhuvudet har dagens datum (sätts i läsarens webbläsare, så att
sidorna inte beror på byggtiden), ordmärket NEWSNAVIGATOR med Newsgator, och SV/EN.
Det enda som får ta plats är täckningsremsan: nio fasta celler, Sverige till Globalt, som tänds när en region rapporterar,
med antalet källor. En släckt första cell är en blind fläck i svenska medier. Samma remsa visar blå publik, mitten och röd
publik för amerikanska medier. Meta skrivs som meningar ("15 källor i sex regioner. Saknas i svenska medier.") och källorna
som en mening med länkar till originalen och "och 12 till" till notissidan, där hela listan finns med landsnamn.

## Navigatorn (morgonbrevet)
`newsletter.py` bygger brevet av notiser som godkänts senaste dygnet: `site/navigatorn-sv.html` och `-en.html`, plus textversioner. Inga AI-anrop.
- Sektioner: Världen, Sverige och Norden, Marknader, Tech och AI, Vetenskap. Högst fem källor per notis, resten länkas till sajten.
- Egen text: skriv `data/kolumn.md` (första raden rubrik, sedan stycken, `---` före engelsk version). Den hamnar under "Redaktörens rad".
- Förhandsvisning med ogranskade utkast (märkta UTKAST): `python newsletter.py --utkast`.
- Godkända notiser sparas i `data/arkiv.json` i 14 dagar, så brevet fungerar även när de fallit ur flödet.
- Utskick: planen är Resend Broadcasts (gratis upp till 1 000 prenumeranter). `{{unsubscribe_url}}` byts mot leverantörens avregistreringslänk.

## Den publika sajten
`publish.py` bygger `public/` med `sajt.py` som två utgåvor, var och en ett eget språkträd med bara det språket i koden:
`/sv/` och `/en/` med förstasida, en sida per notis (`/<sprak>/n/<id>/`, den adress Instagrambildtexterna länkar till), sektioner
(`/<sprak>/varlden/`, `/sverige/`, `/marknader/`, `/tech/`, `/vetenskap/`, `/noje/`), `/navigatorn/`, `/om/` med principerna, `/kallor/`
och RSS (`/<sprak>/feed.xml`). Roten `/` är en valsida. Varje utgåva visar bara de notiser som hör hemma där (`utgava.visa`), och den
engelska kräver engelsk rubrik och sammanfattning och gör inte påståendet "saknas i svenska medier". Gamla adresser (`/n/...`, `/feed.xml`)
skickas vidare till `/sv/` via `_redirects`. Förhandsvisningen (`publish.py --forhandsvisning`) är kvar som en tvåspråkig plan mapp.
Bara granskade notiser kommer med: förstasidan visar tre dygn, sektionerna sju, notissidorna lever lika länge som arkivet (14 dagar).
Inget på sidorna beror på byggtiden, så filerna ändras bara när innehållet ändras. Workflowen lägger `public/` i grenen `sajt`,
och Cloudflare Pages (projektet newsnavigator) publicerar den grenen utan byggsteg.
Innan lansering har sidorna noindex; sätt `NN_LANSERAD=1` i workflowen för att öppna för sökmotorer (ger också sitemap).
Förhandsvisning av dagens utkast som platt sajt: `python publish.py --forhandsvisning /tmp/sajt`.
`public/404.html` ger riktiga 404-svar (utan den serverar Pages förstasidan för okända adresser) och `public/_headers`
sätter säkerhetsrubriker och cache för loggan och Instagram-bilderna.

### Domän och e-post
newsnavigator.se är köpt hos Loopia och pekar på Cloudflares namnservrar (jakub och wanda). Zonen ligger i Cloudflare Free:
`newsnavigator.se` och `www` är CNAME till `newsnavigator.pages.dev` och kopplade som egna domäner i Pages-projektet, med automatisk HTTPS.
E-post går via Cloudflare Email Routing (MX, SPF och DKIM sköts av Cloudflare): `we@newsnavigator.se` vidarebefordras till
en verifierad destinationsadress. Catch-all är avstängd, så övriga adresser studsar. Utskick av Navigatorn kräver en egen
avsändartjänst (Resend eller liknande) med egna SPF/DKIM-poster för en underdomän, så att de inte krockar med vidarebefordringen.

## Källkontroll
`kallkontroll.py` låter AI:n läsa varje nytt utkast en andra gång och spåra varje påstående till källmaterialet (rubriker och ingresser). Resultatet sparas i cachen och följer med notisen: i granskningsärendet som en rad per notis (⚠️ och anmärkningarna när något saknar stöd), och på sajten som märkningen "Källkontrollerad" när allt gick att spåra.

## Autopiloten
`autopilot.py` avgör vad som får publiceras utan redaktören. Grindarna (`grindar`, ren funktion med tester): källkontrollen har spårat
alla påståenden, minst tre oberoende källor (kuraterade listor och statskontrollerade medier räknas inte) i minst två regioner, svenska
nyheter minst två svenska källor, utkastet inte märkt osäkert, högst 20 källor och 3 sektioner, inga spärrord (brottmål, självmord,
sexualbrott, barn) och ingen blind fläck. Det som klarar grindarna läggs i en kö med klockslag och visas förbockat i granskningsärendet under
"Publiceras automatiskt": bocka ur för att stoppa. Efter 45 minuter godkänns notisen av sig själv, högst `tak` per dygn (två första veckan,
sedan åtta). Inställningar i `data/autopilot.json` (`pa`, `tyst`, `tak`, `vetofonster_minuter`); `tyst` pausar all automatisk publicering
och Instagram. Status i `data/autopilot_status.json`. Automatiskt publicerade notiser märks "Publicerad utan manuell granskning" på sajten,
i Navigatorn och på Instagramkorten. Ångra: workflowen `angra.yml` med notisens id, eller `python autopilot.py angra <id>`.

## Två utgåvor
`utgava.py` avgör vilken läsare en notis hör hemma hos. Svenska utgåvan (@newsnavigator.se): svenska nyheter, och globala händelser som berör
Sverige och Europa, särskilt de som saknas i svenska medier. Engelska utgåvan (@news.navigator): globala händelser, svenskt och nordiskt bara när
det påverkar läsaren (NATO, EU, ECB, stora bolag, marknader), aldrig lokalt svenskt. Varje händelse bär `relevans` (`sv` och `en`, 0 till 3).
En notis godkänns en gång; utgåvorna avgör var den visas. Grindarna är autopilotens, utom att engelska utgåvan inte gör påståendet "saknas
i svenska medier" och inte kräver svenska källor, och att tre svenska källor räcker för svensk inrikesnyhet.

## Behöver dig och morgonrapporten
`behover.py` bygger listan över det som väntar på dig, med regler i stället för för hand: måste-med-notiser som väntat över två timmar eller
hållits tillbaka av taket, körningar som fallerat två gånger i rad, klockan som stannat, hopslagna händelser, källor som tystnat (tre dygn för
nyhetsmedier, fjorton för primärkällor), Instagram-token som löper ut och Instagram utan secrets, för få notiser till Navigatorn (bara när `navigatorn` är sant i `data/autopilot.json`),
rättelser (öppna ärenden märkta `rättelse`) och tyst läge. Pipelinen räknar ut listan varje timme (`data/behover.json`) och visar den överst i
granskningsärendet. `rapport.yml` mejlar den kl 07.00 via Resend ("Allt kört." när den är tom) och mejlar direkt när något allvarligt gått sönder,
en gång per fel och igen efter tolv timmar. Secrets: `RESEND_API_KEY` och `RAPPORT_TILL` (mottagare); valfri repovariabel `NN_RAPPORT_FRAN`
(standard är Resends testavsändare, som bara når kontots egen adress). Prova utan att skicka: starta Rapport under Actions med "torrt".

## Instagram
Två konton: **@newsnavigator.se** på svenska (secrets `IG_USER_ID`, `IG_ACCESS_TOKEN`) och **@news.navigator** på engelska (`IG_USER_ID_EN`,
`IG_ACCESS_TOKEN_EN`). Vad varje konto får visa avgör `utgava.py`. Korten byggs på kontots språk av de utkastfält som finns (`rubrik_en`,
`sammanfattning_en`, `perspektiv_en`, `oenighet_en`), och engelska kort gör aldrig påståendet "saknas i svenska medier". Tillstånd, status
och token ligger per konto i `data/instagram/` (`sv.json`, `en.json`, `status-sv.json`, `status-en.json`).

`instagram.py bygg` gör karusellkort (1080x1350, JPEG) för varje godkänd notis i `public/ig/<språk>/<id>/`, med caption i `caption.txt`. Korten ligger ute på sajten, så att Instagram kan hämta dem. `instagram.py posta [--konto sv|en|alla]` publicerar dagens bästa opostade notis per konto via Instagrams API (workflowen `instagram.yml`, 07:45). Kräver ett Business- eller Creator-konto och kontots secrets (long-lived token, 60 dagar, förnyas via `refresh_access_token`). Utan secrets skriver skriptet bara vad det skulle ha postat. Typsnitt och maskot ligger i `assets/` så att korten blir lika överallt. Förhandsvisning av dagens utkast: `python instagram.py forhandsvisning /tmp/ig` (`--sprak en` för engelska).
Formatet: vit text på svart, högst tre kort. Omslag med rubrik, sammanfattning och täckningsremsan; sedan "Så ser världen på det"
med en rubrik per region; sist ett kort där det finns något att visa, i tur och ordning data bakom nyheten, ett stapeldiagram
(fältet `graf` på notisen: titel, staplar med etikett, värde och visat värde), USA blått och rött, eller "Källorna skiljer sig åt".
Handplockade notiser i en JSON-fil, till exempel ur flödeshistoriken: `python instagram.py urval urval.json /tmp/ig`.

## Källor utan flöde
`sidlasare.py` läser en sidas rubriklista som om den vore ett flöde, för källor vars RSS är borta (`hamtning: sida` i `feeds.yaml`, med `lankar`, ett reguljärt uttryck som nyhetslänkarnas sökväg ska matcha). Bara rubrik och länk läses, aldrig sidans text. `robots.txt` kontrolleras först, och en utgivare som inte tillåter NewsnavigatorBot eller vars robots.txt inte går att läsa hämtas inte. En sida har inga datum, så en länk får tiden då vi först såg den (`data/sidor.json`), och det som redan stod på sidan första gången räknas som gammalt. Nya sidkällor provas i Actions, Källprov, fälten `sida` och `monster`: det visar vilka sökvägar sidan har och vilka rubriker mönstret hittar. Sidor som ritar sin lista med JavaScript läses med en riktig webbläsare (`rendera: true`, Playwright, samma Chrome som korten), fortfarande efter robots.txt-kontrollen. Idag läses Finansinspektionen, IMF, Mistral och NATO så. Ny Teknik är utesluten (beslut 4 november).

## Hybridklustringen
`semantisk.py` är ett andra varv efter `pipeline.cluster` och `merge_clusters`: en flerspråkig inbäddning (sentence-transformers, MiniLM) slår ihop kluster som reglerna delat när modell och ord båda säger att rubrikerna handlar om samma sak (cosinus minst 0,60, två gemensamma ord, en fjärdedel av paren). Mätt på de handmärkta rubrikerna: precision 0,98 och recall 0,875 med reglerna ensamma, recall 0,95 med hybriden. Händelser utan svensk källa vars rubriker liknar en händelse med svensk källa får inte påståendet "saknas i svenska medier" (`perspektiv.grannar_svenska`). `NN_SEMANTISK=0` stänger av steget; saknas modellen används klustren som de är.

## Experiment: GDELT och inbäddningar
`gdelt.py` kontrollerar händelser som vi påstår saknas i svenska medier mot GDELT (öppna data, bara metadata, aldrig artikeltext), med egennamn ur rubrikerna som fråga. Körs inte i pipelinen än: provas i Actions, Källprov, `gdelt`. `inbaddningar.py` mäter flerspråkiga inbäddningar (sentence-transformers) mot dagens klustring på de handmärkta rubrikerna i `tests/kluster-rubriker.json`, Källprov, `inbaddningar`. Resultaten och besluten står i `docs/redaktionen.md`.

## Bildtext och USA-block
Bildtexten på Instagram är kort och sakligt som text-tv: rubrik, sammanfattning, en mening om var källorna skiljer sig åt (bara när de gör det), källor, länk och hur notisen granskats. Inga slogans, hashtaggar eller uppmaningar. "USA: blått och rött" visas bara när det är relevant, se `utgava.usa_relevant`: amerikansk rubrik och minst tre amerikanska medier med både blå och röd publik.

## Berättelserna
`berattelser.py` ger händelser med minst fyra oberoende källor i minst två regioner två till fyra namngivna berättelser: vad grupper av
källor lyfter fram, alltid tillskrivet, aldrig vad en källa utelämnar. Koden räknar ut vilka källor, regioner och AllSides-sidor som bär
dem, och en egen källkontroll läser tillskrivningarna. Resultatet sparas som `narrativ` på händelsen. Visas på notissidan först när
`NN_BERATTELSER=1` är satt (efter utvärderingen, B3 i planen).
