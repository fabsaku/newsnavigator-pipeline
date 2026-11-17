"""Kostnadsskydd för AI-steget.

`RaknandeKlient` lindar Anthropic-klienten och räknar tokens i varje anrop, `spara` skriver summan per dygn till
data/kostnad.json, och `Budget` stoppar nya utkast när körningens eller dygnets tak är nått. Texter som redan finns
i cachen kostar ingenting och påverkas inte. Priser i USD per miljon tokens (in, ut); okänd modell prissätts
försiktigt som Sonnet 5.5."""
import json
import threading
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).parent
SOKVAG = ROOT / "data" / "kostnad.json"
PRISER = {"claude-haiku-5-5": (0.10, 0.50), "claude-sonnet-5-5": (2.00, 10.00), "claude-opus-5-5": (4.00, 20.00)}
FORSIKTIGT = (2.00, 10.00)


class Rakning:
    def __init__(self, modell):
        self.modell = modell
        self.okand_modell = modell not in PRISER
        self.anrop = self.tokens_in = self.tokens_ut = 0
        self._las = threading.Lock()

    def lagg_till(self, usage):
        if usage is None:
            return
        with self._las:
            self.anrop += 1
            self.tokens_in += (getattr(usage, "input_tokens", 0) or 0) + (getattr(usage, "cache_creation_input_tokens", 0) or 0) \
                + (getattr(usage, "cache_read_input_tokens", 0) or 0)
            self.tokens_ut += getattr(usage, "output_tokens", 0) or 0

    def usd(self):
        pris_in, pris_ut = PRISER.get(self.modell, FORSIKTIGT)
        return self.tokens_in / 1e6 * pris_in + self.tokens_ut / 1e6 * pris_ut


class _Meddelanden:
    def __init__(self, klient, rakning):
        self._k, self._r = klient, rakning

    def create(self, **kw):
        msg = self._k.messages.create(**kw)
        self._r.lagg_till(getattr(msg, "usage", None))
        return msg


class RaknandeKlient:
    """Samma gränssnitt som Anthropic-klienten för de anrop pipelinen gör, men räknar tokens."""

    def __init__(self, klient, rakning):
        self._klient = klient
        self.messages = _Meddelanden(klient, rakning)

    def __getattr__(self, namn):
        return getattr(self._klient, namn)


def _las(sokvag):
    try:
        return json.loads(Path(sokvag).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def idag_str():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def dagens_usd(sokvag=SOKVAG, idag=None):
    return float(_las(sokvag).get("dagar", {}).get(idag or idag_str(), {}).get("usd", 0))


def spara(rakning, sokvag=SOKVAG, idag=None, behall=60):
    d = _las(sokvag)
    dagar = d.setdefault("dagar", {})
    dag = dagar.setdefault(idag or idag_str(), {"usd": 0, "in": 0, "ut": 0, "anrop": 0, "korningar": 0})
    dag["usd"] = round(dag["usd"] + rakning.usd(), 6)
    dag["in"] += rakning.tokens_in
    dag["ut"] += rakning.tokens_ut
    dag["anrop"] += rakning.anrop
    dag["korningar"] += 1
    if rakning.okand_modell:
        dag["okand_modell"] = rakning.modell
    for gammal in sorted(dagar)[:-behall]:
        dagar.pop(gammal)
    d["modell"] = rakning.modell
    Path(sokvag).parent.mkdir(parents=True, exist_ok=True)
    Path(sokvag).write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")


class Budget:
    """Hur många nya utkast (som kostar) en körning får göra. `dagstak_usd` 0 betyder ingen gräns."""

    def __init__(self, max_nya, dagstak_usd, redan_idag_usd):
        self.max_nya, self.dagstak, self.redan = max_nya, dagstak_usd, redan_idag_usd
        self.nya = 0
        self.nekade = 0
        self._las = threading.Lock()

    def far_nytt(self):
        with self._las:
            if (self.max_nya and self.nya >= self.max_nya) or (self.dagstak and self.redan >= self.dagstak):
                self.nekade += 1
                return False
            self.nya += 1
            return True
