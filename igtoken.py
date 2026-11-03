#!/usr/bin/env python3
"""Förnyar Instagram-tokens (60 dagar) och sparar när de går ut, så att Behöver dig kan varna i tid.

Metas förnyelse (ig_refresh_token) förlänger ett giltigt token som är minst ett dygn gammalt med 60 dagar. Förnyelsen sker hos Meta;
repots secrets kan inte skrivas av Actions utan en särskild nyckel, så om Meta skulle svara med ett annat token än det vi har
markeras det i status (`token_bytt`) och Behöver dig ber dig lägga in det nya. Själva token skrivs aldrig till någon fil.

  python igtoken.py    förnyar de konton som har IG_ACCESS_TOKEN (sv) och IG_ACCESS_TOKEN_EN (en)
"""
import json
import os
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, timedelta

import instagram

SECRETS = {"sv": "IG_ACCESS_TOKEN", "en": "IG_ACCESS_TOKEN_EN"}
URL = "https://graph.instagram.com/refresh_access_token?grant_type=ig_refresh_token&access_token="


def _hamta(url):
    req = urllib.request.Request(url, headers={"User-Agent": "newsnavigator"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())


def forny(lang, token, hamta=_hamta, idag=None):
    """Förnyar ett token. Returnerar {"utgar", "bytt"} eller {"fel"}; status för kontot uppdateras. Token skrivs aldrig."""
    idag = idag or date.today()
    try:
        d = hamta(URL + urllib.parse.quote(token, safe=""))
        utgar = idag + timedelta(seconds=int(d["expires_in"]))
        bytt = bool(d.get("access_token")) and d["access_token"] != token
    except urllib.error.HTTPError as e:
        fel = f"HTTP {e.code}"
    except (urllib.error.URLError, KeyError, ValueError, TypeError) as e:
        fel = type(e).__name__
    else:
        instagram.spara_status(lang, token_utgar=utgar.isoformat(), token_bytt=bytt, token_fel=None)
        return {"utgar": utgar.isoformat(), "bytt": bytt}
    instagram.spara_status(lang, token_fel=fel)
    return {"fel": fel}


def kor(hamta=_hamta, idag=None):
    ut = {}
    for lang, namn in SECRETS.items():
        token = os.environ.get(namn)
        if token:
            ut[lang] = forny(lang, token, hamta=hamta, idag=idag)
    return ut


def main():
    ut = kor()
    if not ut:
        print("Inga Instagram-tokens i miljön (secrets saknas): inget att förnya.")
    for lang, r in ut.items():
        print(f"{instagram.HANDTAG[lang]}: {r}")


if __name__ == "__main__":
    main()
