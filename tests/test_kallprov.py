"""Källprov: en ny källa prövas mot robots.txt innan den läggs i feeds.yaml."""
import kallprov

URL = "https://example.se/nyheter/rss.xml"


def test_tillaten_utan_regler():
    besked = kallprov.robots_besked("", URL)
    assert besked["tillaten"] is True and besked["ai_blockerade"] == []


def test_alla_botar_blockerade():
    assert kallprov.robots_besked("User-agent: *\nDisallow: /\n", URL)["tillaten"] is False


def test_var_bot_blockerad_med_namn():
    text = "User-agent: NewsnavigatorBot\nDisallow: /\n\nUser-agent: *\nAllow: /\n"
    assert kallprov.robots_besked(text, URL)["tillaten"] is False


def test_bara_flodet_blockerat():
    text = "User-agent: *\nDisallow: /nyheter/\n"
    assert kallprov.robots_besked(text, URL)["tillaten"] is False
    assert kallprov.robots_besked(text, "https://example.se/rss.xml")["tillaten"] is True


def test_ai_botar_som_blockeras_redovisas():
    text = "User-agent: GPTBot\nDisallow: /\n\nUser-agent: ClaudeBot\nDisallow: /\n\nUser-agent: *\nAllow: /\n"
    besked = kallprov.robots_besked(text, URL)
    assert besked["tillaten"] is True
    assert besked["ai_blockerade"] == ["ClaudeBot", "GPTBot"]


def test_langsta_regeln_vinner():
    # Pythons robotparser tar första regeln; standarden (RFC 9309) säger att den längsta matchningen avgör
    text = "User-agent: *\nDisallow: /\nAllow: /nyheter/\n"
    assert kallprov.robots_besked(text, URL)["tillaten"] is True
    assert kallprov.robots_besked(text, "https://example.se/sport/")["tillaten"] is False


def test_jokertecken():
    text = "User-agent: *\nDisallow: /*.xml$\n"
    assert kallprov.robots_besked(text, URL)["tillaten"] is False
    assert kallprov.robots_besked(text, "https://example.se/nyheter/rss.xml?x=1")["tillaten"] is True


def test_egen_grupp_gar_fore_stjarnan():
    text = "User-agent: *\nDisallow: /\n\nUser-agent: NewsnavigatorBot\nAllow: /\n"
    assert kallprov.robots_besked(text, URL)["tillaten"] is True


def test_regeln_som_avgor_redovisas():
    besked = kallprov.robots_besked("User-agent: *\nDisallow: /nyheter/\n", URL)
    assert besked["regel"] == "User-agent: * / Disallow: /nyheter/"


# ---------- Genomgång av hela källistan ----------

def kalla(id, url, **kw):
    return {"id": id, "namn": id.upper(), "url": url, "typ": "media", "region": "europa", "betalvagg": False, **kw}


def hamta_fran(tabell, anrop=None):
    def hamta(url):
        host = url.split("/")[2]
        if anrop is not None:
            anrop.append(host)
        return tabell[host]
    return hamta


def test_genomgang_klassar_varje_kalla():
    kallor = [kalla("a", "https://a.se/rss"), kalla("b", "https://b.se/rss"), kalla("c", "https://c.se/rss", betalvagg=True),
              kalla("d", "https://d.se/rss"), kalla("e", "https://e.se/rss")]
    tabell = {"a.se": ("User-agent: *\nAllow: /\n", None),
              "b.se": ("User-agent: *\nDisallow: /\n", None),
              "c.se": ("User-agent: ClaudeBot\nDisallow: /\n\nUser-agent: GPTBot\nDisallow: /\n", None),
              "d.se": (None, "HTTP 500"),
              "e.se": ("", None)}
    rader = {r["id"]: r for r in kallprov.genomgang(kallor, hamta=hamta_fran(tabell))}
    assert rader["a"]["robots"] == "tillaten" and rader["a"]["ai_blockerade"] == []
    assert rader["b"]["robots"] == "blockerar"
    assert rader["c"]["robots"] == "tillaten" and rader["c"]["ai_blockerade"] == ["ClaudeBot", "GPTBot"] and rader["c"]["claude_blockerad"]
    assert rader["d"]["robots"] == "oklart" and "HTTP 500" in rader["d"]["fel"]
    assert rader["e"]["robots"] == "tillaten"


def test_robots_hamtas_en_gang_per_utgivare():
    anrop = []
    kallor = [kalla("a1", "https://a.se/rss"), kalla("a2", "https://a.se/annat.xml", extra=["https://a.se/tredje.xml"])]
    kallprov.genomgang(kallor, hamta=hamta_fran({"a.se": ("", None)}, anrop))
    assert anrop == ["a.se"]


def test_sidkalla_provas_pa_sidans_adress():
    k = kalla("s", "https://s.se/nyheter/", hamtning="sida", lankar="^/nyheter/")
    rad = kallprov.genomgang([k], hamta=hamta_fran({"s.se": ("User-agent: *\nDisallow: /nyheter/\n", None)}))[0]
    assert rad["robots"] == "blockerar"


def test_forslag_for_ai_blockerare_utan_bara_rubrik():
    tabell = {"a.se": ("User-agent: GPTBot\nDisallow: /\n", None), "b.se": ("User-agent: GPTBot\nDisallow: /\n", None), "c.se": ("", None)}
    kallor = [kalla("a", "https://a.se/rss"), kalla("b", "https://b.se/rss", bara_rubrik=True), kalla("c", "https://c.se/rss")]
    rader = {r["id"]: r for r in kallprov.genomgang(kallor, hamta=hamta_fran(tabell))}
    assert rader["a"]["atgard"] == "satt bara_rubrik" and rader["b"]["atgard"] is None and rader["c"]["atgard"] is None


def test_betalvagg_och_ai_blockering_ar_inte_en_atgard_i_sig_men_markeras_for_beslut():
    tabell = {"c.se": ("User-agent: ClaudeBot\nDisallow: /\n", None)}
    rad = kallprov.genomgang([kalla("c", "https://c.se/rss", betalvagg=True)], hamta=hamta_fran(tabell))[0]
    assert rad["atgard"] is None and rad["beslut"] == "betalvägg och blockerar Claude"


def test_blockerar_oss_ar_en_atgard():
    rad = kallprov.genomgang([kalla("b", "https://b.se/rss")], hamta=hamta_fran({"b.se": ("User-agent: *\nDisallow: /\n", None)}))[0]
    assert rad["atgard"] == "ta bort, utgivaren tillåter inte oss"


def test_sammanfattningen_raknar_grupperna():
    kallor = [kalla("a", "https://a.se/rss"), kalla("b", "https://b.se/rss"), kalla("c", "https://c.se/rss", betalvagg=True)]
    tabell = {"a.se": ("", None), "b.se": ("User-agent: *\nDisallow: /\n", None), "c.se": ("User-agent: ClaudeBot\nDisallow: /\n", None)}
    sam = kallprov.sammanfatta(kallprov.genomgang(kallor, hamta=hamta_fran(tabell)))
    assert sam == {"totalt": 3, "tillaten": 2, "blockerar": 1, "oklart": 0, "ai_blockerar": 1, "claude_blockerar": 1, "beslut": 1, "atgarder": 1}


def test_uteslutna_kallor_ar_inte_med_i_kallistan():
    """Utgivare som stänger ute oss i robots.txt (genomgång 4 november) och Ny Teknik (Fabians beslut) hämtas inte."""
    from pathlib import Path
    import yaml
    ids = {s["id"] for s in yaml.safe_load((Path(__file__).parent.parent / "feeds.yaml").read_text(encoding="utf-8"))["sources"]}
    assert not ids & {"nyteknik", "euractiv", "the-decoder", "unnews", "balkaninsight"}


def test_kallor_som_stanger_ute_claude_ar_bara_rubrik():
    """Beslut B (4 november): de 33 källor utan betalvägg vars robots.txt nämner Claude skickar inte sin ingress till modellen."""
    from pathlib import Path
    import yaml
    kallor = {s["id"]: s for s in yaml.safe_load((Path(__file__).parent.parent / "feeds.yaml").read_text(encoding="utf-8"))["sources"]}
    ids = "svt,sr-ekot,nrk,guardian,france24,spiegel,politico-eu,thehill,cnbc,thehindu,aljazeera,mit-tr,verge,techcrunch,ieee-robotics,fz,wired-ai,huffpost,vox,nypost,daily-caller,rest-of-world,ieee-spectrum,nation-ke,yonhap,rappler,abc-au,rnz,dr,ruv,eltiempo,theeastafrican,eurasianet".split(",")
    assert len(ids) == 33 and all(kallor[i].get("bara_rubrik") is True for i in ids)
    assert kallor["bbc"].get("bara_rubrik") is not True                       # blockerar inte Claude: ingressen används som förr
