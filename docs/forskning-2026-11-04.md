# Hur Gatorn kan bli bättre: sökresultat och slutsatser (4 november 2026)

**Status på underlaget.** Djupforskningen sökte på fem spår och hittade 40 källor, men hämtningen av själva sidorna misslyckades (alla 19 försök kom tillbaka tomma), så inga påståenden har faktagranskats. Det som står under "Vad sökningarna pekar på" är sammanfattningar ur sökresultaten, alltså ledtrådar, inte verifierade fakta. Siffror ska kontrolleras mot källan innan de används offentligt. Slutsatserna längre ned är min bedömning av vad ledtrådarna betyder för Newsnavigator.

## Vad sökningarna pekar på

**Jämförbara tjänster**
- Ground News: betald, bygger på betyg från tre externa bedömare (AllSides, MBFC, Ad Fontes) och gör inga egna. Columbia Journalism Review kallar det billigare, inte bättre. Källa: help.ground.news, about.ground.news, cjr.org.
- AllSides: gratis, sida vid sida. Tangle: en berättelse om dagen med syntes. Particle: sammanfattning först, betalnivå (cirka 2,99 dollar i månaden). Kagi News: daglig pressgenomgång byggd på öppna RSS-flöden. Källor: jämförelsebloggar (readless.app, newsreel.co) från konkurrenter, behandla som ledtrådar.
- Semafor: premiumbrev, event och ett B2B-upplägg bakom ett konsumentvarumärke. Källa: twipemobile.com, pulse.bot.

**LLM, framing och neutralitet**
- Resultaten för att hitta framing beror starkt på hur man frågar, och GPT-4 räknar känslomässigt språk som framing (arXiv 2402.11621). Enighet mellan modeller kan användas för att peka ut omstridda bedömningar.
- Sammanfattningar av flera artiklar tappar ofta avvikande synsätt och speglar bara konsensus (DiverseSumm, arXiv 2309.09369).
- LLM-sammanfattningar som kallas neutrala är inte automatiskt neutrala: 20 344 sammanfattningar om fem heta amerikanska frågor visade som standard en liberal slagsida (arXiv 2410.09978). Sammanfattande modell kan själv lägga till framing (arXiv 2503.16674).
- Långa indata: faktatrohetsmått är känsliga för dokumentordning och modeller tittar mindre på mitten (arXiv 2410.23609).
- Nära vår arkitektur: BetweenTheLines (SiKDD 2025), kluster och sedan flerstegs LLM som drar ut påståenden per källa.

**Förtroende och märkning av AI**
- Reuters Institute Digital News Report 2025: förtroendet är cirka 40 procent, tre år i rad. Folk väntar sig att AI gör nyheter billigare och snabbare men mindre öppna och mindre pålitliga. I Tyskland var 54 procent obekväma med nyheter som mest är gjorda av AI. Rapporten Generative AI and News 2025 anger att bara 19 procent ser AI-märkning varje dag fast 77 procent tar del av nyheter dagligen. Alla siffror ska kontrolleras i rapporterna.

**Instagram och brev**
- Metas dokumentation: 100 API-publiceringar per 24 timmar, en karusell räknas som en, men sidan nämner också 50 på ett annat ställe, så `content_publishing_limit` ska läsas live. API-karuseller har högst 10 bilder, appen tillåter 20.
- Karuseller ger högst engagemang och flest sparningar i leverantörers mätningar (cirka 0,5 procent engagemang, andra kvartalet 2026, leverantörsdata). Instagrams chef har sagt att visningstid, gillamarkeringar och delningar via meddelande är de tre viktigaste signalerna (Buffer, andrahandsuppgift).
- Brev: öppningsgrad är ett svagt mått, tidigt engagemang avgör, och Morning Brew skickar ett personligt meddelande till dem som inte öppnat på sex veckor (Digiday).
- **Inget hittades** om hur nya Instagramkonton som postar mycket i början bedöms av Instagram. Det är en lucka, inte ett bevis för att det är ofarligt.

## Vad det betyder för Newsnavigator (min bedömning)

Prioriterat efter nytta mot insats.

1. **Lova inte neutralitet, mät den.** Evidensen säger att "neutral AI" inte är neutral som standard. Vi har redan källkontroll för tillskrivning, men ingen mätning av slagsida. Lägg in en liten fast testmängd (till exempel 30 händelser om heta frågor) som körs om när prompten ändras, och låt utvärderingen i ärende #2 också fråga om texten kändes vinklad. Sidan "Om" bör säga "källkontrollerad och tillskriven", inte "neutral".
2. **Använd enighet som filter för berättelserna (B1).** Kör berättelsesteget två gånger med olika prompt eller modell och behåll bara de berättelser som återkommer. Det är billigt och går direkt mot det som forskningen visar: resultatet beror på prompten och känslomässigt språk läses som framing. Ska göras innan berättelserna slås på.
3. **Slumpa och begränsa indata.** Modeller tittar mindre på mitten av långa indata. För händelser med många källor: begränsa till några per region, och blanda ordningen i berättelsesteget i stället för att alltid lägga primärkällor först.
4. **Gör berättelserna till vår egen produkt, inte en kopia.** Ground News är betalvägg plus tredjepartsbetyg, AllSides är gratis sida vid sida, Kagi News är nästan samma idé som vår men utan två läsare. Det som är vårt: två utgåvor, "vad det betyder för dig" och källkontrollerad tillskrivning. Tangles lärdom, en berättelse om dagen med syntes, passar Navigatorn: låt morgonbrevet ha en "dagens berättelse" med berättelserna som huvudrad.
5. **Var tydlig om AI utan att skrämma.** Förtroendet ligger runt 40 procent och många är obekväma med nyheter som mest är gjorda av AI. Våra märkningar är redan ärliga ("Publicerad utan manuell granskning"). Lägg till motsatsen: visa hur många notiser en människa läst, och namnge ansvarig utgivare nära toppen av varje notis, inte bara i sidfoten.
6. **Instagram: bygg som en modern global text-tv.** (Rättat efter Fabians besked: vi ber aldrig om delning, och uppmaningar förstör tonen.) Text-tv i Sverige står för kortfattat, utan trams och något man litar på: första bilden är rubriken med fakta, nästa bild en saklig hänvisning ("Nästa sida: ..."), bildtexten bara rubrik, sammanfattning, källor, länk och granskningsrad. Forskningens signaler om delningar och sparningar används bara för att mäta, aldrig för att be om dem. Håll karusellerna på högst 10 bilder (vi gör redan det).
7. **Överväg att sprida lanseringen över fler dagar.** Det finns ingen evidens här för att 56 inlägg på 7,5 timmar ger problem, men det finns heller ingen för att det är ofarligt, och ett nytt konto saknar historik. En försiktig plan: prov, sedan 8 till 10 per dag första dagarna, och höj när `content_publishing_limit` och räckvidden ser friska ut. Du bestämmer; allt är förberett för båda.
8. **Brev: mät tidigt engagemang och väck sovande prenumeranter.** När Resend används: följ klick och svar snarare än öppningar, och skicka ett personligt meddelande till den som inte öppnat på sex veckor.
9. **Betalvägg och intäkter.** Konkurrenternas modeller är betalda betyg (Ground News), betalnivå för sammanfattningar (Particle) eller premiumbrev och event (Semafor). Vi tar inget betalt, vilket stämmer med principen att vi inte tjänar på att du stannar. Beslutet är senare.

## Nästa steg
Jag kan bygga 1, 2 och 3 direkt (de är kod och tester) och lägga 5 och 6 i planen. Be mig köra om forskningen med en annan hämtningsväg om du vill ha siffrorna faktagranskade.
