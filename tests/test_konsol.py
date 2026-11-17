"""Konsolen /lage/: alla aktuella händelser som källornas egna rubriker och länkar, utan AI-text, med valfri koppling till läsarens egen AI."""
import re
from pathlib import Path

from test_lansering import historia
from test_sajt_utgavor import bygg, text


def handelse(n, **kw):
    ev = historia(n, **kw)["ev"]
    ev["senast"] = "2026-11-17T13:52:18+00:00"
    ev["utkast"] = {"rubrik_sv": "AI-RUBRIK-SV", "sammanfattning_sv": "AI-TEXT-SV", "rubrik_en": "AI-HEAD-EN", "sammanfattning_en": "AI-TEXT-EN"}
    ev["kallor"][0]["url"] = "https://exempel.se/a?utm_source=RSS&utm_medium=x&id=7"
    ev["kallor"][0]["rubrik"] = "Källans egen rubrik"
    return ev


def test_konsolen_visar_kallornas_rubriker_och_lankar_men_ingen_ai_text(tmp_path):
    ev = handelse(1)
    bygg(tmp_path, [], konsol=[ev])
    sida = text(tmp_path / "sv" / "lage" / "index.html")
    assert "Källans egen rubrik" in sida and 'href="https://exempel.se/a?id=7"' in sida, "spårningsparametrar ska bort, länken ska finnas"
    assert "AI-RUBRIK-SV" not in sida and "AI-TEXT-SV" not in sida, "konsolen får inte visa AI-skriven text"
    assert "—" not in sida


def test_konsolen_finns_i_bada_utgavorna_och_i_menyn(tmp_path):
    bygg(tmp_path, [], konsol=[handelse(1)])
    for lang in ("sv", "en"):
        assert (tmp_path / lang / "lage" / "index.html").exists()
    assert 'href="/sv/lage/"' in text(tmp_path / "sv" / "index.html")


def test_utan_handelser_ar_konsolen_tom_men_byggs(tmp_path):
    bygg(tmp_path, [], konsol=[])
    assert "lage" in " ".join(str(p) for p in tmp_path.rglob("index.html"))


def test_fraga_din_ai_ar_ren_lank_eller_kopiera_utan_nyckel_och_utan_kallornas_text(tmp_path):
    ev = handelse(2)
    bygg(tmp_path, [], konsol=[ev])
    sida = text(tmp_path / "sv" / "lage" / "index.html")
    m = re.search(r'data-prompt="([^"]+)"', sida)
    assert m, "varje händelse har en färdig prompt för läsarens egen AI"
    prompt = m.group(1)
    assert "Källans egen rubrik" in prompt and "https://exempel.se/a?id=7" in prompt
    assert "AI-TEXT" not in prompt
    # ingen nyckel eller token lagras eller skickas av sajten: bara vanliga länkar och urklipp
    assert "claude.ai/new?q=" in sida and "chatgpt.com/?q=" in sida
    assert "api_key" not in sida.lower() and "apikey" not in sida.lower() and "x-api-key" not in sida.lower()
    assert "fetch(" not in sida, "konsolen anropar inga AI-tjänster själv"


def test_konsolen_markerar_betalvagg_och_statsmedier(tmp_path):
    ev = handelse(3)
    ev["kallor"][2]["betalvagg"] = True
    ev["kallor"].append({**ev["kallor"][0], "namn": "RT", "url": "https://rt.example/1", "rubrik": "RT rubrik", "statskontrollerad": True, "betalvagg": False})
    bygg(tmp_path, [], konsol=[ev])
    sida = text(tmp_path / "sv" / "lage" / "index.html")
    assert "betalvägg" in sida.lower() and "STAT" in sida


def test_konsolen_ar_noindex_tills_lanseringen(tmp_path):
    bygg(tmp_path, [], konsol=[handelse(1)], noindex=True)
    assert 'content="noindex"' in text(tmp_path / "sv" / "lage" / "index.html")


def test_publish_skickar_flodets_alla_handelser_till_konsolen():
    kod = (Path(__file__).parent.parent / "publish.py").read_text(encoding="utf-8")
    assert "konsol=" in kod
