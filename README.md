# Newsnavigator pipeline v0.2

Hämtar nyheter från drygt 60 källor i sju regioner, grupperar artiklar om samma händelse, skriver neutrala AI-utkast och låter redaktionen granska innan något publiceras.

**Vi levererar nyheterna. Vad läsaren gör av dem är upp till läsaren.** Reglerna står i [PRINCIPER.md](PRINCIPER.md) och styr både redaktionen och AI:n.

## Så fungerar det

1. **Hämta** (`pipeline.py`): läser RSS från källorna i `feeds.yaml`. Från betalväggskällor används bara rubrik och länk.
2. **Gruppera**: artiklar om samma händelse slås ihop, en källa per händelse.
3. **Tagga och rangordna**: ämnen från källan och nyckelord. Fler oberoende källor och en primärkälla ger högre placering.
4. **Utkast**: om `ANTHROPIC_API_KEY` finns skriver AI:n rubrik och sammanfattning på svenska och engelska, och noterar om källorna är oeniga. AI:n får bara rubriker och ingresser, aldrig hela artiklar.
5. **Granska** (`granska.py`): inget publiceras utan att du har godkänt det.
6. **Publicera**: `site/publicerat.html` innehåller bara godkända notiser, med källor och AI-märkning.

## Kom igång på din dator

```bash
pip install -r requirements.txt
python verify_feeds.py            # vilka källor fungerar? se data/kallstatus.md
python pipeline.py                # bygger data/flode.json och site/index.html
python granska.py lista           # läs utkasten
python granska.py godkann ID ID   # godkänn
python granska.py publicera       # bygg site/publicerat.html
```

Med AI-utkast: `export ANTHROPIC_API_KEY=...` innan `pipeline.py`. Modell väljs med `NN_MODEL` (standard `claude-haiku-5-5`).

Testa utan internet: `python pipeline.py --feeds tests/feeds-test.yaml --max-age-hours 0`

## Kör automatiskt

1. Skapa ett privat repo på GitHub och lägg upp filerna.
2. Under Settings, Secrets, lägg till `ANTHROPIC_API_KEY`.
3. `.github/workflows/pipeline.yml` kör pipelinen varje timme dagtid och två gånger på natten, och källkontrollen på nattkörningarna. Utkast och översättningar sparas i `data/cache.json`, så bara nya eller ändrade händelser skickas till AI:n.

## Nästa version

- Gruppering över språk (svensk och engelsk rubrik om samma händelse).
- Kombinationer: AI föreslår kopplingar mellan händelser, du skriver ingressen.
- Raden "Vad betyder det för Sverige och Europa?" som eget, granskat fält.
- Koppla flödet till sajtens design i stället för förhandsvisningen.

## Sajten
`render.py` bygger flödet i Newsnavigators design: dark mode, Newsgator, svenska och engelska (SV/EN-knapp), ämnesfilter, "Så ser världen på det" per händelse, källor med land och märkning av statskontrollerade medier. `site/index.html` visar alla utkast, `site/publicerat.html` bara granskade.

## Navigatorn (morgonbrevet)
`newsletter.py` bygger brevet av notiser som godkänts senaste dygnet: `site/navigatorn-sv.html` och `-en.html`, plus textversioner. Inga AI-anrop.
- Sektioner: Världen, Sverige och Norden, Marknader, Tech och AI, Vetenskap. Högst fem källor per notis, resten länkas till sajten.
- Egen text: skriv `data/kolumn.md` (första raden rubrik, sedan stycken, `---` före engelsk version). Den hamnar under "Redaktörens rad".
- Förhandsvisning med ogranskade utkast (märkta UTKAST): `python newsletter.py --utkast`.
- Godkända notiser sparas i `data/arkiv.json` i 14 dagar, så brevet fungerar även när de fallit ur flödet.
- Utskick: planen är Resend Broadcasts (gratis upp till 1 000 prenumeranter). `{{unsubscribe_url}}` byts mot leverantörens avregistreringslänk.

## Den publika sajten
`publish.py` bygger `public/` med `sajt.py`: förstasida, en sida per notis (`/n/<id>/`, delbar länk), sektioner
(`/varlden/`, `/sverige/`, `/marknader/`, `/tech/`, `/vetenskap/`), `/navigatorn/`, `/om/` med principerna, `/kallor/`
och RSS på svenska och engelska (`/feed.xml`, `/feed-en.xml`). Bara granskade notiser kommer med: förstasidan visar tre dygn,
sektionerna sju, notissidorna lever lika länge som arkivet (14 dagar).
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

## Instagram
`instagram.py bygg` gör karusellkort (1080x1350, JPEG) för varje godkänd notis i `public/ig/<id>/`, med caption i `caption.txt`. Korten ligger ute på sajten, så att Instagram kan hämta dem. `instagram.py posta` publicerar dagens bästa opostade notis via Instagrams API (workflowen `instagram.yml`, 07:45). Kräver ett Business- eller Creator-konto och hemligheterna `IG_USER_ID` och `IG_ACCESS_TOKEN` (long-lived token, 60 dagar, förnyas via `refresh_access_token`). Utan hemligheter skriver skriptet bara vad det skulle ha postat. Typsnitt och maskot ligger i `assets/` så att korten blir lika överallt. Förhandsvisning av dagens utkast: `python instagram.py forhandsvisning /tmp/ig`.
