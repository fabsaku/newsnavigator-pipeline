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
