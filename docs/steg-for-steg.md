# Steg för steg: allt du behöver göra

Gör delarna i ordning. Del 1 och 2 spärrar mest. Del 3 och 4 går att göra när du har tio minuter över. Allt du klickar i står med den exakta menyn. Metas gränssnitt flyttas ibland, så om en knapp heter något annat: leta efter den som liknar.

Du behöver aldrig klistra in något secret i chatten. Det går bara in i GitHubs secrets.

## Del 1. Instagram (kritisk väg, cirka en timme första gången)

### 1.1 Kontona
1. Öppna Instagram på telefonen, logga in på @newsnavigator.se.
2. Profil, menyn uppe till höger, Inställningar och aktivitet, Kontotyp och verktyg, Byt till professionellt konto. Välj Skapare (Creator). Kontot ska vara publikt.
3. Gör samma sak för @news.navigator (växla konto längst ned i inställningarna).

### 1.2 Meta-appen
Metas gränssnitt flyttas ofta. Namnen nedan är de som gäller i november 2026 enligt Metas dokumentation. Leta efter närmaste motsvarighet om något heter annorlunda. Vi använder "Instagram API with Instagram Login", så du behöver varken Facebook-sida eller Facebook-inloggning för kontona, bara ett Facebookkonto för att få öppna developers.facebook.com.

1. Gå till developers.facebook.com och logga in. Godkänn utvecklarvillkoren om du blir ombedd.
2. Min appar, Skapa app. Namn: Newsnavigator. Välj användningsfallet som gäller att hantera och publicera innehåll på Instagram (typ Business om den frågar).
3. I appens vänstermeny, Instagram, "API setup with Instagram login".
4. Under "Generate access tokens", klicka "Add account" och logga in på @newsnavigator.se. Godkänn behörigheterna `instagram_business_basic` och `instagram_business_content_publish`.
5. Klicka "Generate token" vid kontot. Du får en token (giltig i 60 dagar) och ett konto-id med siffror. Kopiera båda till en anteckning på din dator, inte till något molnverktyg och inte till chatten.
6. Upprepa 4 och 5 för @news.navigator.
7. Om "Add account" inte tillåter kontot: App roles, Roles, lägg till Instagram-testare med kontonamnet. Acceptera sedan inbjudan i Instagram-appen (Inställningar, Appar och webbplatser, Testarinbjudningar) och gör om steg 4.

Du behöver varken App Review eller att appen sätts i live-läge för att publicera på dina egna konton. Appens secret behövs inte nu.

### 1.3 Lägg in secrets i GitHub och kontrollera dem
1. github.com/fabsaku/newsnavigator-pipeline, Settings, Secrets and variables, Actions, New repository secret.
2. Skapa fyra secrets, ett i taget, med exakt dessa namn:
   - `IG_USER_ID` = konto-id för @newsnavigator.se
   - `IG_ACCESS_TOKEN` = token för @newsnavigator.se
   - `IG_USER_ID_EN` = konto-id för @news.navigator
   - `IG_ACCESS_TOKEN_EN` = token för @news.navigator
3. Radera anteckningen med token när du är klar.
4. **Kontrollera.** Actions, workflowen Instagram, Run workflow, `kontroll = true`, kör. Ändra fältet från `false` till `true` innan du kör: en manuell körning med `false` postar på riktigt. Med `true` publiceras inget. Loggen visar för varje konto om secrets finns, vilket konto token hör till, kontotyp och hur många publiceringar som finns kvar i dygnskvoten. Rätt resultat är "OK" på båda raderna. Står det "fel konto" har du bytt token mellan kontona. Står det "fel kontotyp" är kontot inte professionellt (se 1.1). Står det "token fungerar inte" har den gått ut eller kopierats fel: generera en ny.
5. Tokens förnyas sedan av sig själva varje vecka (workflowen `igtoken.yml`). Du behöver inte göra något mer.

### 1.4 Bio-länkar
Sätt länken i respektive profil (Redigera profil, Länkar):
- @newsnavigator.se: `https://newsnavigator.se/sv/`
- @news.navigator: `https://newsnavigator.se/en/`

### 1.5 Besluten
Du har svarat ja på alla tre: lanseringsbatch ur veckan, du bläddrar igenom de 112 korten själv, och Analys-raden får finnas (märkt Analys, visas först efter utvärderingen i del 2). Inget mer att göra här.

### 1.6 Lanseringen
Allt här görs i GitHub: Actions (fliken överst), välj workflowen Lansering i listan till vänster, Run workflow.

1. **Välj.** `lage = valj`, `konto = alla`, `torrt = true`. Vänta ett par minuter tills den är grön. Då har 56 inlägg per konto valts och korten byggts om med dagens material.
2. **Bläddra.** Öppna `https://newsnavigator.se/lansering/sv.html` och `https://newsnavigator.se/lansering/en.html`. Varje inlägg har ett löpnummer. Inlägg märkta "Kräver din genomgång" gäller påståendet "saknas i svenska medier": kontrollera mot källorna. Skriv upp löpnumren du vill stryka.
3. **Godkänn.** `lage = godkann`, `konto = alla`, `uteslut` = löpnumren du strök, kommaseparerade (till exempel `3,17`), eller tomt. Det är här batchen blir granskad, så gör det först när du faktiskt har tittat.
4. **Prov.** `lage = posta`, `konto = sv`, `antal = 1`, `torrt = false`. Kolla att inlägget syns på @newsnavigator.se, att bilderna är rätt och att länken i texten öppnar en sida. Gör samma sak med `konto = en`.
5. **Kör alla.** Först när proven ser bra ut: `lage = posta`, `konto = sv`, `antal = 56`, `intervall = 8`, `torrt = false`. Starta sedan en egen körning för `konto = en` med samma värden. De går parallellt. Ett inlägg var åttonde minut tar cirka 7,5 timmar per konto, och körningen lämnar över till en ny av sig själv. Du behöver inte sitta kvar.
6. **Stoppa.** Sätt `tyst` till sant i `data/autopilot.json` (eller säg till mig i chatten). Körningen stoppar före nästa inlägg. Avbryt också gärna körningen under Actions.

Om något ser fel ut efter provet: skriv till mig innan du går vidare.

### 1.6b Slå på den dagliga postningen (först efter lanseringen)
Schemat i workflowen Instagram postar inget förrän du slår på det, så att secrets inte ensamma startar postningen. När batchen är postad: Settings, Secrets and variables, Actions, fliken Variables, New repository variable. Namn `IG_SCHEMA`, värde `1`. Tar du bort variabeln slutar schemat posta igen.

### 1.7 Öppna för sökmotorer (först efter lyckad lansering)
Säg till mig när lanseringen är klar, så sätter jag `NN_LANSERAD=1`. Det tar bort noindex och skapar sitemap.

## Del 2. Utvärdera berättelserna (cirka 20 minuter, kan göras direkt)
Det här är tesen: att AI hittar de olika berättelserna i hur källorna skriver.

1. Öppna ärendet "Utvärdering: berättelserna": github.com/fabsaku/newsnavigator-pipeline/issues/2.
   Just nu ligger 12 händelser där (så många har både berättelser eller Analys-rad som kontrollen godkänt). Bedöm dem, kör sedan Actions, Utvärdering, `lage = skapa` igen en dag senare: bedömda står kvar och nya fylls på upp till 30.
2. För varje av de 30 händelserna: läs berättelserna och öppna några av källorna. Bocka EN ruta:
   - **stämmer** om varje berättelse går att spåra till just de källor som anges, och inget sägs om vad en källa utelämnar
   - **missvisar** om en berättelse är fel, vinklad eller inte hör ihop
   Rör ingen ruta om du inte hunnit.
   Händelser med en Analys-rad har två egna rutor för raden: stämmer om den följer av fakta och är försiktig (inga råd, inga förutsägelser), missvisar annars.
3. Actions, Utvärdering, Run workflow, `lage = rakna`. Resultatet står i loggen och i `data/utvardering.json`.
4. Berättelserna och Analys-raderna slås på var för sig, först när minst 30 är bedömda och minst 80 procent stämmer. Säg till mig hur det gick, så justerar jag prompten eller slår på dem.

## Del 3. Säkerhetsnätet (cirka 15 minuter)

### 3.1 Morgonrapporten kl 07.00
1. resend.com, skapa konto med din e-postadress.
2. API Keys, Create API Key, behörighet Sending access. Kopiera nyckeln.
3. GitHub, samma ställe som ovan, två nya secrets:
   - `RESEND_API_KEY` = nyckeln
   - `RAPPORT_TILL` = din e-postadress (samma som Resend-kontot, annars når inte mejlet fram med testavsändaren)
4. Actions, Rapport, Run workflow, `torrt = true`. Den visar mejlet i loggen utan att skicka. Kör sedan en gång med `torrt = false` och kolla inkorgen.

### 3.2 Klockan (tre minuter)
Workern finns redan. Den behöver bara den nya koden så att den också startar rapporten.
1. Öppna filen `klocka/worker.js` i repot på GitHub, klicka Raw, markera allt och kopiera.
2. Cloudflare, Workers & Pages, `newsnavigator-klocka`, Edit code. Ta bort allt och klistra in det kopierade. Deploy.
3. Öppna Workerns adress. Sidan ska visa `"token": true`.

## Del 4. Panelen (vänta)
Panelen (inkorg, planering) är inte byggd än. Gör inget här nu. Jag bygger den, och först då behöver du lägga en GitHub-nyckel i Cloudflare Pages och sätta upp Access med din adress. Jag säger till.

## Underhåll som syns i Behöver dig
- Källor som gett 404 eller 403 (NATO, Mail & Guardian, Anthropic, Meta AI och några till) behöver nya flödesadresser. Det går att pröva i Actions, Källprov, men jag gör det när jag har dina beslut klara.
- Instagram-tokens förnyas av sig själva varje måndag när secrets finns. Om Behöver dig säger att Meta bytt token: skapa ett nytt i Meta (steg 1.2.4 och 1.2.5) och uppdatera secreten.
