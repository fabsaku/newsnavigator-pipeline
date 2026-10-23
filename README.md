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
