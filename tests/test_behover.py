"""Fas 5: Behöver dig. En lista som byggs av regler, morgonrapporten och varningsmejl.

Tiderna räknas från NU = tisdag 3 november 2026 07.10 svensk tid (06.10 UTC, vintertid).
"""
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest
import yaml

import behover
import granskning_github
import instagram

NU = datetime(2026, 11, 3, 6, 10, tzinfo=timezone.utc).timestamp()
TIMME = 3600
WORKFLOWS = Path(__file__).parent.parent / ".github" / "workflows"


def iso(ts):
    return datetime.fromtimestamp(ts, timezone.utc).isoformat()


def kalla(namn="BBC", region="europa", typ="media"):
    return {"namn": namn, "rubrik": "x", "url": f"https://x/{namn}", "typ": typ, "region": region, "statskontrollerad": False}


def handelse(eid="aaaaaaaaaa", maste=False, timmar=1, rubrik="Tågolycka i Spanien", **extra):
    ev = {"id": eid, "poang": 10.0, "maste": maste, "vikt": {"timmar": timmar}, "reserv_rubrik": rubrik,
          "amnen_sektion": ["varlden"], "kallor": [kalla("a"), kalla("b", "usa"), kalla("c")],
          "utkast": {"rubrik_sv": rubrik, "sammanfattning_sv": "x", "osaker": False},
          "kallkontroll": {"ok": True, "antal": 1, "problem": []},
          "perspektiv": {"regioner": ["europa", "usa"], "blind_flack": None, "usa_blind": None}}
    ev.update(extra)
    return ev


def korning(workflow="pipeline", status="ok", minuter_sedan=60):
    start = NU - minuter_sedan * 60
    return {"workflow": workflow, "status": status, "start": iso(start), "slut": iso(start + 200), "sekunder": 200,
            "korning": str(int(start)), "url": f"https://github.com/o/r/actions/runs/{int(start)}"}


def lage(**andringar):
    """Ett friskt läge: inget ska behöva redaktören."""
    l = {"repo": "fabsaku/newsnavigator-pipeline",
         "flode": [handelse()], "godkanda": set(),
         "status": {"ko": {}, "publicerade": {}, "stoppade": {}, "startad": NU - 5 * 86400},
         "installningar": {"pa": True, "tyst": False},
         "drift": {"historik": [korning(minuter_sedan=10), korning(minuter_sedan=70)]},
         "kallstatus": {"kallor": [{"id": "svt", "namn": "SVT Nyheter", "status": "ok", "senaste": iso(NU - 3600)}]},
         "kallor_typ": {"svt": "media"},
         "arkiv": {f"id{n}": {"godkand_tid": NU - n * TIMME, "utkast": {"rubrik_sv": f"Notis {n}"}} for n in range(4)},
         "instagram": {}, "instagram_status": {}, "rattelser": []}
    l.update(andringar)
    return l


def koder(rader):
    return [r["kod"] for r in rader]


def test_friskt_lage_ger_tom_lista():
    assert behover.regler(lage(), NU) == []


# ---------- Notiser som väntar ----------

def test_maste_med_som_vantar_mer_an_tva_timmar():
    l = lage(flode=[handelse("a000000001", maste=True, timmar=5), handelse("b000000001", maste=True, timmar=3),
                    handelse("c000000001", maste=True, timmar=1), handelse("d000000001", maste=False, timmar=9)])
    rad = next(r for r in behover.regler(l, NU) if r["kod"] == "vantar")
    assert rad["rad"] == "2 notiser väntar på dig, äldst 5 h"
    assert rad["handling"] == "Till inkorgen"


def test_vantande_notiser_listas_med_rubrik_och_alder():
    l = lage(flode=[handelse("a000000001", maste=True, timmar=5, rubrik="Alfa"), handelse("b000000001", maste=True, timmar=9, rubrik="Beta"),
                    handelse("c000000001", maste=True, timmar=3, rubrik="Gamma"), handelse("d000000001", maste=True, timmar=2, rubrik="Delta")])
    rad = next(r for r in behover.regler(l, NU) if r["kod"] == "vantar")
    assert rad["detaljer"] == ["Beta (9 h)", "Alfa (5 h)", "Gamma (3 h)"]
    _, text = behover.rapport([rad], l, NU)
    assert "   - Beta (9 h)" in text and "Delta" not in text


def test_godkanda_koade_och_stoppade_raknas_inte():
    l = lage(flode=[handelse("a000000001", maste=True, timmar=5), handelse("b000000001", maste=True, timmar=5),
                    handelse("c000000001", maste=True, timmar=5)],
             godkanda={"a000000001"},
             status={"ko": {"b000000001": {"tillagd": NU - 600, "klar": NU + 2000}}, "publicerade": {},
                     "stoppade": {"c000000001": NU - 100}, "startad": NU - 86400})
    assert "vantar" not in koder(behover.regler(l, NU))


def test_notis_i_kon_over_taket_ar_systemet_som_det_ska_inte_ett_beslut():
    l = lage(status={"ko": {"k000000001": {"tillagd": NU - 6 * TIMME, "klar": NU - 3 * TIMME, "rubrik": "x"}},
                     "publicerade": {}, "stoppade": {}, "startad": NU - 86400})
    assert behover.regler(l, NU) == []


# ---------- Körningar ----------

def test_korning_som_fallerat_tva_ganger_i_rad():
    l = lage(drift={"historik": [korning(status="fel", minuter_sedan=10), korning(status="fel", minuter_sedan=70),
                                 korning(status="ok", minuter_sedan=130)]})
    rad = next(r for r in behover.regler(l, NU) if r["kod"] == "korning")
    assert rad["rad"] == "Pipelinen har stannat sedan 06.00"
    assert rad["handling"] == "Öppna loggen, kör igen" and rad["url"].startswith("https://github.com/o/r/actions/runs/")
    assert rad["allvarlig"] is True


def test_ett_fel_racker_inte_och_en_lyckad_senare_tar_bort_raden():
    ett = lage(drift={"historik": [korning(status="fel", minuter_sedan=10), korning(minuter_sedan=70)]})
    assert "korning" not in koder(behover.regler(ett, NU))
    lagad = lage(drift={"historik": [korning(minuter_sedan=10), korning(status="fel", minuter_sedan=70),
                                     korning(status="fel", minuter_sedan=130)]})
    assert "korning" not in koder(behover.regler(lagad, NU))


def test_avbrutna_korningar_raknas_varken_som_fel_eller_ok():
    l = lage(drift={"historik": [korning(status="fel", minuter_sedan=10), korning(status="avbruten", minuter_sedan=40),
                                 korning(status="fel", minuter_sedan=70)]})
    assert "korning" in koder(behover.regler(l, NU))


def test_fel_galler_varje_workflow_for_sig():
    l = lage(drift={"historik": [korning(status="fel", minuter_sedan=10), korning("instagram", "ok", 30),
                                 korning(status="fel", minuter_sedan=70)]})
    assert "korning" in koder(behover.regler(l, NU))
    l = lage(drift={"historik": [korning(minuter_sedan=10), korning("instagram", "fel", 30), korning("instagram", "fel", 90)]})
    rad = next(r for r in behover.regler(l, NU) if r["kod"] == "korning")
    assert rad["rad"].startswith("Instagram har stannat")


def test_klockan_har_stannat():
    l = lage(drift={"historik": [korning(minuter_sedan=200)]})
    rad = next(r for r in behover.regler(l, NU) if r["kod"] == "klocka")
    assert rad["rad"] == "Klockan har stannat: senaste körningen startade 03.50" and rad["allvarlig"] is True
    assert "klocka" not in koder(behover.regler(lage(drift={"historik": [korning(minuter_sedan=100)]}), NU))


# ---------- Källor ----------

def test_kalla_som_varit_tyst_i_tre_dygn():
    l = lage(kallstatus={"kallor": [
        {"id": "aljazeera", "namn": "Al Jazeera", "status": "ok", "senaste": iso(NU - 4 * 86400)},   # tisdag minus fyra dygn = fredag
        {"id": "svt", "namn": "SVT Nyheter", "status": "ok", "senaste": iso(NU - 2 * 86400)},
        {"id": "nyteknik", "namn": "Ny Teknik", "status": "fel", "senaste": None}]},
        kallor_typ={"aljazeera": "media", "svt": "media", "nyteknik": "media"})
    rader = [r for r in behover.regler(l, NU) if r["kod"] == "tyst"]
    assert [r["rad"] for r in rader] == ["Al Jazeera tyst sedan fredag"]
    assert rader[0]["handling"] == "Kontrollera flödet, pausa"


def test_primarkallor_far_vara_tysta_i_fjorton_dygn():
    l = lage(kallstatus={"kallor": [{"id": "riksbanken", "namn": "Riksbanken", "status": "ok", "senaste": iso(NU - 10 * 86400)},
                                    {"id": "who", "namn": "WHO", "status": "tyst", "senaste": iso(NU - 20 * 86400)}]},
             kallor_typ={"riksbanken": "primar", "who": "primar"})
    assert [r["rad"] for r in behover.regler(l, NU) if r["kod"] == "tyst"] == ["WHO tyst sedan 14 oktober"]


def test_en_tyst_kalla_over_fem_sager_kalla_i_singular():
    kallor = [{"id": f"k{n}", "namn": f"Källa {n}", "status": "ok", "senaste": iso(NU - 5 * 86400)} for n in range(6)]
    rader = [r for r in behover.regler(lage(kallstatus={"kallor": kallor}, kallor_typ={}), NU) if r["kod"] == "tyst"]
    assert rader[-1]["rad"] == "och 1 källa till är tyst"


def test_tysta_kallor_over_fem_samlas():
    kallor = [{"id": f"k{n}", "namn": f"Källa {n}", "status": "ok", "senaste": iso(NU - 5 * 86400)} for n in range(8)]
    rader = [r for r in behover.regler(lage(kallstatus={"kallor": kallor}, kallor_typ={}), NU) if r["kod"] == "tyst"]
    assert len(rader) == 6 and rader[-1]["rad"] == "och 3 källor till är tysta"


# ---------- Instagram ----------

def test_instagram_token_som_loper_ut():
    l = lage(instagram_status={"token_utgar": "2026-11-09", "secrets": True})
    rad = next(r for r in behover.regler(l, NU) if r["kod"] == "token")
    assert rad["rad"] == "Instagram-token går ut 9 november" and rad["handling"] == "Förnya" and rad["allvarlig"] is False
    assert "token" not in koder(behover.regler(lage(instagram_status={"token_utgar": "2026-12-20"}), NU))
    snart = next(r for r in behover.regler(lage(instagram_status={"token_utgar": "2026-11-05"}), NU) if r["kod"] == "token")
    assert snart["allvarlig"] is True
    gammal = next(r for r in behover.regler(lage(instagram_status={"token_utgar": "2026-11-01"}), NU) if r["kod"] == "token")
    assert gammal["rad"] == "Instagram-token gick ut 1 november"


def test_instagram_postar_inget_nar_secrets_saknas():
    l = lage(instagram_status={"secrets": False, "vantar": 12})
    rad = next(r for r in behover.regler(l, NU) if r["kod"] == "instagram")
    assert rad["rad"] == "Instagram postar inget: secrets saknas, 12 kort väntar"
    assert "IG_USER_ID" in rad["handling"] and "IG_ACCESS_TOKEN" in rad["handling"]
    assert "instagram" not in koder(behover.regler(lage(instagram_status={"secrets": False, "vantar": 0}), NU))
    assert "instagram" not in koder(behover.regler(lage(instagram_status={"secrets": True, "vantar": 3}), NU))


def test_instagram_som_misslyckats():
    rad = next(r for r in behover.regler(lage(instagram_status={"secrets": True, "vantar": 1, "fel": "Invalid token"}), NU)
               if r["kod"] == "instagram")
    assert rad["rad"] == "Instagram misslyckades: Invalid token"


# ---------- Övrigt ----------

def test_hopslagna_handelser():
    manga = handelse("h000000001", rubrik="Allt möjligt", kallor=[kalla(f"k{n}", ["europa", "usa"][n % 2]) for n in range(21)])
    rad = next(r for r in behover.regler(lage(flode=[manga]), NU) if r["kod"] == "hopslagen")
    assert rad["rad"] == "Troligen hopslagna händelser: Allt möjligt" and rad["handling"] == "Dela upp eller avvisa"


def test_navigatorn_med_for_fa_notiser_bara_nar_brevet_skickas():
    arkiv = {"a": {"godkand_tid": NU - 3600}, "b": {"godkand_tid": NU - 7200}, "c": {"godkand_tid": NU - 3 * 86400}}
    assert "brev" not in koder(behover.regler(lage(arkiv=arkiv), NU))
    l = lage(arkiv=arkiv, installningar={"pa": True, "tyst": False, "navigatorn": True})
    rad = next(r for r in behover.regler(l, NU) if r["kod"] == "brev")
    assert rad["rad"] == "Navigatorn har bara 2 notiser i dag, minst 3 krävs"


def test_rattelse_begard():
    l = lage(rattelser=[{"rubrik": "Audi", "url": "https://github.com/o/r/issues/7"}])
    rad = next(r for r in behover.regler(l, NU) if r["kod"] == "rattelse")
    assert rad["rad"] == "Rättelse: Audi" and rad["url"] == "https://github.com/o/r/issues/7"


def test_tyst_lage():
    rad = next(r for r in behover.regler(lage(installningar={"pa": True, "tyst": True}), NU) if r["kod"] == "tyst_lage")
    assert rad["rad"].startswith("Tyst läge är på")


def test_allvarliga_rader_kommer_forst():
    l = lage(drift={"historik": [korning(status="fel", minuter_sedan=10), korning(status="fel", minuter_sedan=70)]},
             rattelser=[{"rubrik": "Audi", "url": "u"}])
    rader = behover.regler(l, NU)
    assert rader[0]["kod"] == "korning" and rader[-1]["kod"] == "rattelse"


# ---------- Rapporten ----------

def test_rapport_nar_listan_ar_tom():
    l = lage(status={"ko": {"k": {}, "l": {}}, "publicerade": {"a": NU - 3600, "b": NU - 2 * 86400}, "stoppade": {}, "startad": 1},
             arkiv={"a": {"godkand_tid": NU, "utkast": {"rubrik_sv": "Lagarde avgår"}}})
    amne, text = behover.rapport([], l, NU)
    assert amne == "Newsnavigator: allt kört"
    assert text.splitlines()[0] == "Allt kört. Inget behöver dig. 1 notis publicerades automatiskt senaste dygnet, 2 väntar i kön."
    assert "Lagarde avgår" in text and "—" not in text


def test_rapport_med_rader():
    rader = [{"kod": "korning", "id": "korning:pipeline", "rad": "Pipelinen har stannat sedan 07.00",
              "handling": "Öppna loggen, kör igen", "url": "https://github.com/o/r/actions/runs/1", "allvarlig": True},
             {"kod": "rattelse", "id": "rattelse:7", "rad": "Rättelse: Audi", "handling": "Öppna notisen", "url": None, "allvarlig": False}]
    amne, text = behover.rapport(rader, lage(), NU)
    assert amne == "Newsnavigator: 2 saker behöver dig"
    assert text.splitlines()[0] == "2 saker behöver dig."
    assert "1. Pipelinen har stannat sedan 07.00" in text and "Gör: Öppna loggen, kör igen" in text
    assert "https://github.com/o/r/actions/runs/1" in text and "—" not in text
    assert behover.rapport(rader[:1], lage(), NU)[0] == "Newsnavigator: 1 sak behöver dig"


def test_varningsmejl():
    amne, text = behover.varning([{"kod": "korning", "id": "x", "rad": "Pipelinen har stannat sedan 07.00",
                                   "handling": "Öppna loggen, kör igen", "url": "https://u", "allvarlig": True}])
    assert amne == "Newsnavigator: något har gått sönder"
    assert "Pipelinen har stannat sedan 07.00" in text and "https://u" in text and "—" not in text


# ---------- När mejl skickas ----------

ALLV = [{"kod": "korning", "id": "korning:pipeline", "rad": "r", "handling": "h", "url": None, "allvarlig": True}]


def test_morgonrapporten_en_gang_per_dag_efter_sju():
    tidigt = datetime(2026, 11, 3, 5, 30, tzinfo=timezone.utc).timestamp()      # 06.30 svensk tid
    assert behover.beslut({}, [], tidigt)["rapport"] is False
    assert behover.beslut({}, [], NU)["rapport"] is True
    state = behover.markera({}, behover.beslut({}, [], NU), NU)
    assert behover.beslut(state, [], NU + 3600)["rapport"] is False
    assert behover.beslut(state, [], NU + 86400)["rapport"] is True


def test_varning_en_gang_och_igen_efter_tolv_timmar():
    b = behover.beslut({}, ALLV, NU)
    assert [r["id"] for r in b["varna"]] == ["korning:pipeline"]
    state = behover.markera({}, b, NU)
    assert behover.beslut(state, ALLV, NU + TIMME)["varna"] == []
    assert len(behover.beslut(state, ALLV, NU + 13 * TIMME)["varna"]) == 1


def test_varning_rensas_nar_felet_ar_borta_sa_nasta_fel_varnar_direkt():
    state = behover.markera({}, behover.beslut({}, ALLV, NU), NU)
    state = behover.markera(state, behover.beslut(state, [], NU + TIMME), NU + TIMME)
    assert state["varnade"] == {}
    assert len(behover.beslut(state, ALLV, NU + 2 * TIMME)["varna"]) == 1


def test_icke_allvarliga_rader_varnar_inte():
    rader = [{**ALLV[0], "allvarlig": False}]
    assert behover.beslut({}, rader, NU)["varna"] == []


# ---------- Resend ----------

class Svar:
    def __init__(self, data):
        self.data = data

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def read(self):
        return json.dumps(self.data).encode()


def test_skicka_via_resend(monkeypatch):
    anrop = []

    def fake(req, timeout=0):
        anrop.append(req)
        return Svar({"id": "mejl_1"})
    monkeypatch.setattr(behover.urllib.request, "urlopen", fake)
    svar = behover.skicka("Ämne", "Text", till="redaktionen@example.org", fran="Newsnavigator <onboarding@resend.dev>", key="NYCKEL")
    assert svar == {"id": "mejl_1"}
    req = anrop[0]
    assert req.full_url == "https://api.resend.com/emails" and req.get_method() == "POST"
    assert req.get_header("Authorization") == "Bearer NYCKEL"
    assert json.loads(req.data) == {"from": "Newsnavigator <onboarding@resend.dev>", "to": ["redaktionen@example.org"],
                                    "subject": "Ämne", "text": "Text"}


# ---------- Hela vägen: main ----------

def skriv(root, namn, data):
    (root / "data").mkdir(exist_ok=True)
    (root / "data" / namn).write_text(json.dumps(data), encoding="utf-8")


def tom_rot(tmp_path, historik):
    skriv(tmp_path, "flode.json", {"handelser": [handelse()]})
    skriv(tmp_path, "godkanda.json", [])
    skriv(tmp_path, "arkiv.json", {f"id{n}": {"godkand_tid": NU - n * TIMME, "utkast": {"rubrik_sv": f"Notis {n}"}} for n in range(4)})
    skriv(tmp_path, "autopilot_status.json", {"ko": {}, "publicerade": {}, "stoppade": {}, "startad": 1})
    skriv(tmp_path, "autopilot.json", {"pa": True})
    skriv(tmp_path, "drift.json", {"historik": historik})
    skriv(tmp_path, "kallstatus.json", {"kallor": []})
    (tmp_path / "feeds.yaml").write_text(yaml.safe_dump({"sources": [{"id": "svt", "typ": "media"}]}), encoding="utf-8")
    return tmp_path


MILJO = {"RESEND_API_KEY": "NYCKEL", "RAPPORT_TILL": "redaktionen@example.org"}


def test_main_skickar_rapport_en_gang_och_skriver_behover_json(tmp_path, monkeypatch):
    rot = tom_rot(tmp_path, [korning(minuter_sedan=10), korning(minuter_sedan=70)])
    anrop = []
    monkeypatch.setattr(behover.urllib.request, "urlopen", lambda req, timeout=0: anrop.append(json.loads(req.data)) or Svar({"id": "1"}))
    behover.main(["--skicka"], root=rot, now=NU, miljo=MILJO)
    assert len(anrop) == 1 and anrop[0]["subject"] == "Newsnavigator: allt kört"
    data = json.loads((rot / "data" / "behover.json").read_text(encoding="utf-8"))
    assert data["rader"] == [] and data["rapport"]["amne"] == "Newsnavigator: allt kört"
    assert json.loads((rot / "data" / "rapport.json").read_text(encoding="utf-8"))["rapport_datum"] == "2026-11-03"
    behover.main(["--skicka"], root=rot, now=NU + 600, miljo=MILJO)
    assert len(anrop) == 1


def test_main_varnar_direkt_vid_fel(tmp_path, monkeypatch):
    rot = tom_rot(tmp_path, [korning(status="fel", minuter_sedan=10), korning(status="fel", minuter_sedan=70)])
    skriv(rot, "rapport.json", {"rapport_datum": "2026-11-03"})
    anrop = []
    monkeypatch.setattr(behover.urllib.request, "urlopen", lambda req, timeout=0: anrop.append(json.loads(req.data)) or Svar({"id": "1"}))
    behover.main(["--skicka"], root=rot, now=NU, miljo=MILJO)
    assert [a["subject"] for a in anrop] == ["Newsnavigator: något har gått sönder"]


def test_main_utan_nyckel_skickar_inget_och_markerar_inget(tmp_path, monkeypatch, capsys):
    rot = tom_rot(tmp_path, [korning(minuter_sedan=10)])
    monkeypatch.setattr(behover.urllib.request, "urlopen", lambda *a, **k: pytest.fail("ska inte skicka"))
    behover.main(["--skicka"], root=rot, now=NU, miljo={})
    assert "RESEND_API_KEY" in capsys.readouterr().out
    assert not (rot / "data" / "rapport.json").exists() or "rapport_datum" not in json.loads((rot / "data" / "rapport.json").read_text())


def test_main_torrt_skriver_ut_men_skickar_inget(tmp_path, monkeypatch, capsys):
    rot = tom_rot(tmp_path, [korning(minuter_sedan=10)])
    monkeypatch.setattr(behover.urllib.request, "urlopen", lambda *a, **k: pytest.fail("ska inte skicka"))
    behover.main(["--skicka", "--torrt"], root=rot, now=NU, miljo=MILJO)
    assert "Allt kört." in capsys.readouterr().out


# ---------- Ärendet och Instagram-status ----------

def test_arendet_visar_behover_dig_overst():
    rader = [{"kod": "korning", "id": "k", "rad": "Pipelinen har stannat sedan 07.00", "handling": "Öppna loggen, kör igen",
              "url": "https://u", "allvarlig": True}]
    block = granskning_github.behover_block(rader)
    assert block[0] == "### Behöver dig" and "Pipelinen har stannat sedan 07.00. Öppna loggen, kör igen." in "\n".join(block)
    assert not any(rad.startswith("- [") for rad in block)
    assert "Inget just nu." in granskning_github.behover_block([])


def test_instagram_skriver_status(tmp_path, monkeypatch):
    monkeypatch.setattr(instagram, "STATE", tmp_path / "instagram.json")
    monkeypatch.setattr(instagram, "STATUS", tmp_path / "instagram_status.json")
    import autopilot
    monkeypatch.setattr(autopilot, "INSTALLNINGAR", tmp_path / "finns-inte.json")
    (tmp_path / "instagram_status.json").write_text(json.dumps({"token_utgar": "2026-12-20"}), encoding="utf-8")
    nu = __import__("time").time()
    instagram.save_state({"a": {"rubrik": "A", "poang": 5, "godkand_tid": nu - 100},
                          "b": {"rubrik": "B", "poang": 4, "godkand_tid": nu - 100, "postad": nu - 50}})
    monkeypatch.delenv("IG_USER_ID", raising=False)
    monkeypatch.delenv("IG_ACCESS_TOKEN", raising=False)
    instagram.posta()
    status = json.loads((tmp_path / "instagram_status.json").read_text(encoding="utf-8"))
    assert status["secrets"] is False and status["vantar"] == 1 and status["token_utgar"] == "2026-12-20"
    assert status["senast"] > nu - 5


# ---------- Workflows och klockan ----------

def test_rapport_workflow():
    y = yaml.safe_load((WORKFLOWS / "rapport.yml").read_text(encoding="utf-8"))
    text = (WORKFLOWS / "rapport.yml").read_text(encoding="utf-8")
    crons = [s["cron"] for s in y[True]["schedule"]]
    assert "5 5,6 * * *" in crons and any(c.startswith("47 ") for c in crons)
    assert "workflow_dispatch" in y[True]
    assert y["concurrency"]["group"] == "newsnavigator"
    assert "python behover.py --skicka" in text and "RESEND_API_KEY" in text and "RAPPORT_TILL" in text
    assert "git add data/rapport.json" in text and "-X theirs" in text
    assert "git add data/rapport.json 2>/dev/null || true" in text, "filen finns inte förrän något skickats"
    assert text.index("git checkout -- data/behover.json") < text.index("git pull --rebase"), "osparade ändringar stoppar pull --rebase"


def test_pipelinen_raknar_ut_behover_dig_fore_arendet():
    steg = [s.get("run", "") for s in next(iter(yaml.safe_load((WORKFLOWS / "pipeline.yml").read_text(encoding="utf-8"))["jobs"].values()))["steps"]]
    forst = next(n for n, r in enumerate(steg) if "python behover.py" in r and "--skicka" not in r)
    arende = next(n for n, r in enumerate(steg) if "granskning_github.py uppdatera" in r)
    assert forst < arende


def test_instagram_workflow_sparar_status():
    assert "data/instagram_status.json" in (WORKFLOWS / "instagram.yml").read_text(encoding="utf-8")


def test_klockan_startar_rapporten_klockan_sju_och_som_vakthund_varje_timme():
    js = (Path(__file__).parent.parent / "klocka" / "worker.js").read_text(encoding="utf-8")
    assert js.count('jobs.push("rapport.yml")') == 2
    assert "t.hour === 7 && t.minute < 15" in js and "t.minute >= 30 && t.minute < 45" in js
