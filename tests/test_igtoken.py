"""D: Instagram-tokens förnyas och dess utgångsdatum syns i Behöver dig. Inget token skrivs någonsin till en fil."""
import json
import urllib.error
from datetime import date
from pathlib import Path

import pytest
import yaml

import behover
import igtoken
import instagram
from test_behover import NU, koder, lage

IDAG = date(2026, 11, 3)
SECRET_TOKEN = "IGAAtoken1234567890hemligt"


@pytest.fixture(autouse=True)
def tillstand(tmp_path, monkeypatch):
    monkeypatch.setattr(instagram, "status_path", lambda lang: tmp_path / f"status-{lang}.json")
    return tmp_path


def hamta_ok(expires=5184000, nytt=None):
    def hamta(url):
        assert url.startswith("https://graph.instagram.com/refresh_access_token?grant_type=ig_refresh_token&access_token=")
        return {"access_token": nytt or SECRET_TOKEN, "token_type": "bearer", "expires_in": expires}
    return hamta


def test_forny_sparar_utgangsdatum_i_kontots_status():
    r = igtoken.forny("sv", SECRET_TOKEN, hamta=hamta_ok(), idag=IDAG)
    assert r == {"utgar": "2027-01-02", "bytt": False}
    assert instagram.load_status("sv")["token_utgar"] == r["utgar"]
    assert instagram.load_status("en") == {}


def test_utgangsdatum_ar_idag_plus_expires_in():
    r = igtoken.forny("en", SECRET_TOKEN, hamta=hamta_ok(expires=86400 * 60), idag=IDAG)
    assert r["utgar"] == "2027-01-02"


def test_nytt_token_fran_meta_markeras_men_skrivs_aldrig():
    r = igtoken.forny("sv", SECRET_TOKEN, hamta=hamta_ok(nytt="IGAAnytt0987654321"), idag=IDAG)
    assert r["bytt"] is True
    lagrat = instagram.status_path("sv").read_text(encoding="utf-8")
    assert "IGAAnytt" not in lagrat and SECRET_TOKEN not in lagrat and json.loads(lagrat)["token_bytt"] is True


def test_samma_token_rensar_bytt_markeringen():
    igtoken.forny("sv", SECRET_TOKEN, hamta=hamta_ok(nytt="IGAAannat"), idag=IDAG)
    igtoken.forny("sv", SECRET_TOKEN, hamta=hamta_ok(), idag=IDAG)
    assert instagram.load_status("sv")["token_bytt"] is False


def test_fel_fran_meta_sparas_utan_token():
    def hamta(url):
        raise urllib.error.HTTPError(url, 400, "Bad Request", {}, None)
    r = igtoken.forny("en", SECRET_TOKEN, hamta=hamta, idag=IDAG)
    s = instagram.load_status("en")
    assert r["fel"] and s["token_fel"] and SECRET_TOKEN not in json.dumps(s) and SECRET_TOKEN not in json.dumps(r)
    assert "token_utgar" not in s


def test_kor_hoppar_over_konton_utan_token(monkeypatch):
    monkeypatch.setenv("IG_ACCESS_TOKEN", SECRET_TOKEN)
    monkeypatch.delenv("IG_ACCESS_TOKEN_EN", raising=False)
    ut = igtoken.kor(hamta=hamta_ok(), idag=IDAG)
    assert set(ut) == {"sv"} and "token_utgar" in instagram.load_status("sv") and instagram.load_status("en") == {}


def test_behover_visar_att_meta_bytt_token_och_att_fornyelsen_felade():
    rad = next(r for r in behover.regler(lage(instagram_status={"sv": {"token_bytt": True, "token_utgar": "2027-01-02"}, "en": {}}), NU) if r["id"] == "token:sv")
    assert "nytt token" in rad["rad"] and rad["allvarlig"] is True
    fel = next(r for r in behover.regler(lage(instagram_status={"sv": {}, "en": {"token_fel": "HTTP 400"}}), NU) if r["id"] == "token:en")
    assert "Förnyelsen" in fel["rad"] and "HTTP 400" in fel["rad"]
    assert "token" not in koder(behover.regler(lage(instagram_status={"sv": {"token_utgar": "2027-01-02"}, "en": {}}), NU))


def test_workflow():
    y = yaml.safe_load((Path(__file__).parent.parent / ".github" / "workflows" / "igtoken.yml").read_text(encoding="utf-8"))
    text = (Path(__file__).parent.parent / ".github" / "workflows" / "igtoken.yml").read_text(encoding="utf-8")
    assert "schedule" in y[True] and "workflow_dispatch" in y[True]
    for namn in ("IG_ACCESS_TOKEN", "IG_ACCESS_TOKEN_EN"):
        assert f"{namn}: ${{{{ secrets.{namn} }}}}" in text
    assert "python igtoken.py" in text and "data/instagram" in text and "-X theirs" in text
