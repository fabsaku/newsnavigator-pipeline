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
