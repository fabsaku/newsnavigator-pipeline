"""Bevakningsspåren: fem områden som redaktionen följer särskilt, enligt principen Fem spår.

Spåren avgör vad som bevakas och väger lite extra i urvalet (vikt.py). De ändrar aldrig hur en notis är skriven,
och ett spår handlar lika mycket om bakslag som om framsteg. Träffarna bygger på rubrikerna: i stora händelser krävs
träff i minst var femte, som för ämnena i pipeline.tag. Ingen AI, så att det alltid går att se varför en notis är med.
"""
import re

VIKT = 3    # lika mycket som ett steg på konsekvensskalan i vikt.py


def _re(ord_):
    delar = (re.escape(w.rstrip("*")) + (r"\w*" if w.endswith("*") else "") for w in ord_.split("|"))
    return re.compile(r"(?<!\w)(?:" + "|".join(delar) + r")(?!\w)", re.I)


# Rubrikord, svenska och engelska. Kriget i sig är inget spårord: det skulle fånga nästan allt.
_SAMARBETE = _re("fredssamtal|fredsavtal|fredsplan*|fredsförhandling*|vapenvila*|vapenstillestånd|peace talks|peace deal|"
                 "peace plan|peace agreement|peace accord|peace summit|peace negotiation*|ceasefire*|cease-fire*|truce|armistice|"
                 "säkerhetsråd*|security council|general assembly|generalförsamling*|förenta nationerna|united nations|"
                 "treaty|fördrag*|nedrustning*|disarmament|arms control|medla|medlar|mediation|mediate*|mediator*|"
                 "g7|g20|brics summit|african union|afrikanska unionen|asean")
_RELIGION = _re("church*|cathedral*|mosque*|synagogue*|temple*|christian*|muslim*|jew|jews|jewish|hindu*|sikh*|buddhist*|"
                "worshipper*|clergy|imam*|rabbi*|priest*|kyrka*|kyrkor*|moské*|synagog*|tempel|kristna|kristen|muslimer*|"
                "judar|judisk*|hinduer*|sikher*|buddhister*|präst*|pilgrim*")
_VALD = _re("attack*|bomb*|killed|kill|killing*|massacre*|shot|shooting*|arson|burned|burnt|torched|vandali*|persecut*|lynch*|"
            "mob|riot*|desecrat*|gunmen|angrepp*|attacker*|attentat*|dödade|dödad*|massaker*|brand*|förföljelse*|förföljd*|skändning*")
_RELIGION_ENSAM = _re("antisemit*|islamophob*|islamofob*|sectarian*|sekteristisk*|blasphemy|hädelse*|religious persecution|"
                      "religiös förföljelse|religious violence|religiöst våld|religious freedom|religionsfrihet*|hate crime*|hatbrott*")
_RATTIGHETER = _re("human rights|mänskliga rättigheter|rights group*|rights groups|människorättsorganisation*|amnesty|"
                   "un rights|fn:s människorättschef|tortyr*|torture*|torturing|war crime*|krigsbrott*|crimes against humanity|"
                   "brott mot mänskligheten|genocide*|folkmord*|ethnic cleansing|etnisk rensning|forced labour|forced labor|tvångsarbete*|"
                   "political prisoner*|politisk fånge|politiska fångar|death penalty|dödsstraff*|executed|avrättad*|avrättning*|"
                   "press freedom|pressfrihet*|censorship|censur|women's rights|kvinnors rättigheter|lgbt*|hbtq*|"
                   "international criminal court|internationella brottmålsdomstolen|icc|asylum seeker*|asylsökande")
_MILJO = _re("klimat*|climate*|utsläpp*|emissions|cop\\d+|biodiversity|biologisk mångfald|deforestation|avskogning*|pollution|"
             "förorening*|renewable*|förnybar*|wildfire*|skogsbrand*|skogsbränder*|oil spill*|oljeutsläpp*|glacier*|glaciär*|"
             "paris agreement|parisavtalet|carbon|koldioxid*|sea level*|havsnivå*|microplastic*|mikroplast*|ozone layer|ozonlager*|"
             "net zero|nettonoll|extinction|utrotning*|ecosystem*|ekosystem*|coral reef*|korallrev*|heatwave*|värmebölja*")
# Teknikspåret har delspår, från försvarsteknik till hemelektronik. Vapenanvändning i krig räknas inte, bara tekniken.
TEKNIK = (
    ("forsvar", "Försvarsteknik", "Defence technology",
     _re("hypersonic*|stealth|fighter jet*|stridsflyg*|gripen|f-35|missile defen*|air defen*|luftvärn*|robotsystem*|"
         "autonomous weapon*|defen?ce tech*|försvarsteknik*|drone maker*|drönartillverk*|military ai|laser weapon*")),
    ("ai", "AI", "AI",
     _re("ai|artificial intelligence|artificiell intelligens|openai|anthropic|deepmind|chatgpt|gemini|llm*|språkmodell*|generative|generativ*")),
    ("chip", "Halvledare", "Semiconductors",
     _re("chip|chips|chipmaker*|halvledar*|semiconductor*|nvidia|tsmc|asml")),
    ("rymd", "Rymden", "Space",
     _re("rocket*|raket*|spacex|nasa|esa|satellit*|satellite*|moon mission*|månlandning*|mars mission*|rymdstation*|space station")),
    ("energi", "Energiteknik", "Energy technology",
     _re("fusion|solar cell*|solceller*|battery|batteries|batteri*|small modular reactor*|smr|kärnkraft*|nuclear reactor*|vätgas*|hydrogen")),
    ("robot", "Robotar och kvantdatorer", "Robots and quantum",
     _re("robot*|humanoid*|quantum|kvant*|self-driving|självkörande|autonomous vehicle*")),
    ("hem", "Hemelektronik", "Consumer electronics",
     _re("smartphone*|iphone*|ipad*|galaxy|pixel|playstation|xbox|nintendo|wearable*|smart glasses|smartglasögon|apple watch|"
         "smart speaker*|oled|mobiltelefon*")),
)

SPAR = (
    ("samarbete", "Samarbete och fred", "Cooperation and peace",
     "Avtal, medling, vapenvila och det internationella samarbetet, och när det havererar.",
     "Agreements, mediation, ceasefires and international cooperation, and when they fail."),
    ("religion", "Religion och våld", "Religion and violence",
     "Angrepp på människor för deras tro, med samma mått för alla religioner.",
     "Attacks on people for their faith, with the same measure for every religion."),
    ("rattigheter", "Mänskliga rättigheter", "Human rights",
     "Brott mot och framsteg för mänskliga rättigheter, oavsett land och styrelseskick.",
     "Violations of and progress on human rights, whatever the country or system of government."),
    ("miljo", "Miljön", "The environment",
     "Klimat, utsläpp, natur och de beslut som påverkar dem, åt båda håll.",
     "Climate, emissions, nature and the decisions that affect them, in either direction."),
    ("teknik", "Teknikens utveckling", "Technology",
     "Från försvarsteknik till hemelektronik: vad som faktiskt utvecklas.",
     "From defence technology to consumer electronics: what is actually being developed."),
)


def _traff(rubrik, spar):
    if spar == "samarbete":
        return bool(_SAMARBETE.search(rubrik))
    if spar == "religion":
        return bool(_RELIGION_ENSAM.search(rubrik) or (_RELIGION.search(rubrik) and _VALD.search(rubrik)))
    if spar == "rattigheter":
        return bool(_RATTIGHETER.search(rubrik))
    if spar == "miljo":
        return bool(_MILJO.search(rubrik))
    return any(m.search(rubrik) for _, _, _, m in TEKNIK)


def av_rubriker(rubriker):
    """Spåren en samling rubriker om samma händelse hör till."""
    rubriker = [r for r in rubriker if r]
    krav = max(1, -(-len(rubriker) // 5))
    return [s[0] for s in SPAR if sum(1 for r in rubriker if _traff(r, s[0])) >= krav]


def _rubriker(ev):
    d = ev.get("utkast") or {}
    return [k.get("rubrik") for k in ev.get("kallor") or []] + [d.get("rubrik_sv"), d.get("rubrik_en")]


def av(ev):
    """Spåren en notis hör till."""
    return av_rubriker(_rubriker(ev))


def delspar(ev):
    """Teknikspårets delspår, (id, svenska, engelska), eller None."""
    rubriker = [r for r in _rubriker(ev) if r]
    traffar = [(sum(1 for r in rubriker if m.search(r)), t) for *t, m in TEKNIK]
    bast = max(traffar, key=lambda x: x[0], default=(0, None))
    return tuple(bast[1]) if bast[0] else None
