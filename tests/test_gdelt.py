"""GDELT som oberoende kontroll av påståendet "saknas i svenska medier". Bara metadata (rubrik, domän, språk), ingen artikeltext."""
import json

import pytest

import gdelt


@pytest.fixture(autouse=True)
def cache(tmp_path, monkeypatch):
    monkeypatch.setattr(gdelt, "CACHE", tmp_path / "gdelt.json")


def ev(rubrik_en="Strikes hit Qeshm island in Iran, Tehran says", blind="saknas_i_sverige", eid="a" * 10):
    return {"id": eid, "reserv_rubrik": rubrik_en, "utkast": {"rubrik_en": rubrik_en, "rubrik_sv": "x"},
            "perspektiv": {"blind_flack": blind, "regioner": ["usa", "asien"]}}


def artiklar(*domaner):
    return {"articles": [{"url": f"https://{d}/a", "title": "t", "domain": d, "language": "Swedish", "sourcecountry": "Sweden", "seendate": "20261104T120000Z"}
                         for d in domaner]}


# ---------- Frågan ----------

def test_fragan_bygger_pa_egennamn_och_begransar_till_svenska_kallor():
    q = gdelt.fraga(ev())
    assert '"Qeshm"' in q and '"Iran"' in q and "Strikes" not in q and "sourcecountry:sweden" in q


def test_hogst_tre_egennamn_och_inga_dubbletter():
    q = gdelt.fraga(ev("Trump meets Putin and Zelensky in Budapest, Trump says"))
    namn = [t for t in q.split('"')[1::2]]
    assert len(namn) <= 3 and len(set(namn)) == len(namn)


def test_for_fa_egennamn_ger_ingen_fraga():
    assert gdelt.fraga(ev("Oil prices fall as talks resume")) is None          # inget att kontrollera pa
    assert gdelt.fraga(ev("Strikes hit Iran")) is None                         # ett namn ar for allmant, matchar allt


def test_inledande_ord_i_rubriken_ar_inget_egennamn():
    assert '"Strikes"' not in (gdelt.fraga(ev("Strikes hit Qeshm island in Iran")) or "")


# ---------- Utlåtandet ----------

def test_inga_svenska_traffar_stoder_paastaendet():
    r = gdelt.kontrollera(ev(), hamta=lambda q: artiklar(), vila=lambda s: None)
    assert r["utlatande"] == "stoder" and r["svenska_domaner"] == []


def test_minst_tva_svenska_domaner_motsager_paastaendet():
    r = gdelt.kontrollera(ev(), hamta=lambda q: artiklar("svt.se", "dn.se", "svt.se"), vila=lambda s: None)
    assert r["utlatande"] == "motsager" and r["svenska_domaner"] == ["dn.se", "svt.se"]


def test_en_domaen_ar_oklart():
    r = gdelt.kontrollera(ev(), hamta=lambda q: artiklar("svt.se", "svt.se"), vila=lambda s: None)
    assert r["utlatande"] == "oklart"


def test_fel_fran_gdelt_ger_oklart_inte_krasch():
    def trasig(q):
        raise OSError("nät")
    r = gdelt.kontrollera(ev(), hamta=trasig, vila=lambda s: None)
    assert r["utlatande"] == "oklart" and r["fel"]


def test_ogiltigt_svar_ger_oklart():
    assert gdelt.kontrollera(ev(), hamta=lambda q: {"fel": "x"}, vila=lambda s: None)["utlatande"] == "stoder"
    assert gdelt.kontrollera(ev(), hamta=lambda q: None, vila=lambda s: None)["utlatande"] == "oklart"


def test_handelse_utan_paastaende_om_blind_flack_kontrolleras_inte():
    assert gdelt.kontrollera(ev(blind=None), hamta=lambda q: pytest.fail("ska inte fraga"), vila=lambda s: None) is None


# ---------- Flera händelser ----------

def test_kor_vilar_mellan_fragorna_och_stannar_vid_taket():
    vilor, fragor = [], []
    handelser = [ev(f"Strikes hit Qeshm island in Iran, number {n}", eid=f"{n:010d}") for n in range(5)]
    ut = gdelt.kor(handelser, hamta=lambda q: fragor.append(q) or artiklar(), vila=vilor.append, max_fragor=3)
    assert len(ut) == 3 and len(fragor) == 3 and vilor == [gdelt.VILA, gdelt.VILA]


def test_resultat_cachas_per_handelse_i_ett_dygn(tmp_path, monkeypatch):
    monkeypatch.setattr(gdelt, "CACHE", tmp_path / "gdelt.json")
    fragor = []
    h = ev()
    gdelt.kor([h], hamta=lambda q: fragor.append(q) or artiklar("svt.se", "dn.se"), vila=lambda s: None, nu=1_000_000.0)
    gdelt.kor([h], hamta=lambda q: fragor.append(q) or artiklar(), vila=lambda s: None, nu=1_000_000.0 + 3600)
    assert len(fragor) == 1
    gdelt.kor([h], hamta=lambda q: fragor.append(q) or artiklar(), vila=lambda s: None, nu=1_000_000.0 + 2 * 86400)
    assert len(fragor) == 2


def test_felaktiga_svar_cachas_inte(tmp_path, monkeypatch):
    monkeypatch.setattr(gdelt, "CACHE", tmp_path / "gdelt.json")
    def trasig(q):
        raise OSError("nät")
    gdelt.kor([ev()], hamta=trasig, vila=lambda s: None, nu=1.0)
    fragor = []
    gdelt.kor([ev()], hamta=lambda q: fragor.append(q) or artiklar(), vila=lambda s: None, nu=2.0)
    assert len(fragor) == 1


def test_workflowen_har_gdelt_lage():
    from pathlib import Path
    text = (Path(__file__).parent.parent / ".github" / "workflows" / "kallprov.yml").read_text(encoding="utf-8")
    assert "python gdelt.py" in text and "gdelt:" in text


def test_endast_metadata_sparas():
    r = gdelt.kontrollera(ev(), hamta=lambda q: artiklar("svt.se", "dn.se"), vila=lambda s: None)
    sparat = json.dumps(r)
    assert "title" not in sparat and "https://" not in sparat
