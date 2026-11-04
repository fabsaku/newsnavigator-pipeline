"""Experiment: flerspråkiga inbäddningar mot dagens klustring, mätt på de handmärkta rubrikerna (tests/kluster-rubriker.json).
Modellen är utbytbar så att testerna körs utan nätverk och utan torch."""
import math

import pytest

import inbaddningar


def test_parvisa_matt_ur_etiketter_och_forutsagelser():
    etiketter = ["a", "a", "b", "b", None]
    # förutsagt: 0-1 samma (rätt), 2-3 samma (rätt), 0-2 samma (fel); parvisa 0-4, 1-4, 2-4, 3-4 räknas inte (omärkt)
    forutsagt = lambda i, j: (i, j) in {(0, 1), (2, 3), (0, 2)}
    m = inbaddningar.parvisa_matt(etiketter, forutsagt)
    assert m == {"sant_positiva": 2, "falskt_positiva": 1, "falskt_negativa": 0, "precision": 2 / 3, "recall": 1.0, "f1": 0.8, "par": 6}


def test_inga_forutsagda_par_ger_noll_inte_fel():
    m = inbaddningar.parvisa_matt(["a", "a", "b"], lambda i, j: False)
    assert m["f1"] == 0.0 and m["precision"] == 0.0 and m["recall"] == 0.0


def test_cosinus():
    assert inbaddningar.cosinus([1, 0], [1, 0]) == pytest.approx(1.0)
    assert inbaddningar.cosinus([1, 0], [0, 1]) == pytest.approx(0.0)
    assert inbaddningar.cosinus([1, 1], [1, 0]) == pytest.approx(1 / math.sqrt(2))
    assert inbaddningar.cosinus([0, 0], [1, 0]) == 0.0


def test_troskelsvepet_hittar_basta_troskeln():
    etiketter = ["a", "a", "b", "b"]
    vek = [[1.0, 0.0], [0.95, 0.31], [0.0, 1.0], [0.31, 0.95]]
    ut = inbaddningar.svep(etiketter, vek, troskler=[0.5, 0.9, 0.99])
    basta = max(ut, key=lambda r: r["f1"])
    assert basta["troskel"] == 0.9 and basta["f1"] == 1.0
    assert [r["troskel"] for r in ut] == [0.5, 0.9, 0.99]


def test_utvardera_kor_modellen_pa_ratt_text():
    rader = [{"kalla": "A", "typ": "media", "rubrik": "Tågolycka i Spanien", "rubrik_en": "Train crash in Spain", "handelse": "tag"},
             {"kalla": "B", "typ": "media", "rubrik": "Train crash in Spain kills dozens", "handelse": "tag"},
             {"kalla": "C", "typ": "media", "rubrik": "Markets fall", "handelse": "bors"},
             {"kalla": "D", "typ": "media", "rubrik": "Omärkt", "handelse": None}]
    sett = []
    def kodare(texter):
        sett.append(list(texter))
        return [[1.0, 0.0] if "ain" in t or "åg" in t else [0.0, 1.0] for t in texter]
    inbaddningar.utvardera(rader, kodare, text_ur=lambda r: r["rubrik_en"] if r.get("rubrik_en") else r["rubrik"], troskler=[0.5])
    assert sett[0] == ["Train crash in Spain", "Train crash in Spain kills dozens", "Markets fall"]       # bara märkta rubriker


def test_dagens_klustring_ger_samma_matt_som_i_klustringstesten():
    rader = [{"kalla": "A", "typ": "media", "rubrik": "Storm Amy floods Gothenburg harbour", "handelse": "storm"},
             {"kalla": "B", "typ": "media", "rubrik": "Storm Amy floods Gothenburg, ferries cancelled to Denmark", "handelse": "storm"},
             {"kalla": "C", "typ": "media", "rubrik": "Ferries cancelled to Denmark after union strike", "handelse": "strejk"}]
    m = inbaddningar.dagens_klustring(rader)
    assert m["sant_positiva"] == 1 and m["falskt_positiva"] == 0 and m["falskt_negativa"] == 0


def test_rapporten_ar_kort_och_jamfor_metoderna():
    r = {"dagens": {"precision": 0.9, "recall": 0.5, "f1": 0.64, "par": 100, "sant_positiva": 9, "falskt_positiva": 1, "falskt_negativa": 9},
         "modeller": {"originalrubrik": [{"troskel": 0.7, "precision": 0.8, "recall": 0.8, "f1": 0.8, "par": 100, "sant_positiva": 1, "falskt_positiva": 1, "falskt_negativa": 1}],
                      "engelsk rubrik": [{"troskel": 0.6, "precision": 0.7, "recall": 0.7, "f1": 0.7, "par": 100, "sant_positiva": 1, "falskt_positiva": 1, "falskt_negativa": 1}]}}
    ut = inbaddningar.text(r, modell="m")
    assert "dagens klustring" in ut.lower() and "0.80" in ut and "originalrubrik" in ut and len(ut.splitlines()) < 25


# ---------- Högprecisionspunkten och hybriden ----------

def test_basta_recall_med_hog_precision():
    tabell = [{"troskel": 0.4, "precision": 0.80, "recall": 0.95, "f1": 0.87}, {"troskel": 0.6, "precision": 0.98, "recall": 0.60, "f1": 0.74},
              {"troskel": 0.7, "precision": 1.0, "recall": 0.55, "f1": 0.71}]
    assert inbaddningar.bast_med_precision(tabell)["troskel"] == 0.6
    assert inbaddningar.bast_med_precision([{"troskel": 0.4, "precision": 0.5, "recall": 1.0, "f1": 0.7}]) is None


def test_hybriden_slar_ihop_det_reglerna_redan_gor_och_det_inbaddningar_foreslar_med_gemensamma_ord():
    rader = [{"kalla": "A", "typ": "media", "rubrik": "Storm Amy floods Gothenburg harbour", "handelse": "storm"},
             {"kalla": "B", "typ": "media", "rubrik": "Storm Amy floods Gothenburg, ferries cancelled", "handelse": "storm"},
             {"kalla": "C", "typ": "media", "rubrik": "Hamnen i Göteborg översvämmas av stormen Amy", "handelse": "storm"},     # inga gemensamma ord
             {"kalla": "D", "typ": "media", "rubrik": "Ferries cancelled after union strike", "handelse": "strejk"}]
    vek = [[1.0, 0.0], [0.99, 0.1], [0.95, 0.3], [0.1, 0.99]]
    rent = inbaddningar.hybrid(rader, vek, troskler=[0.9], min_delade=0)[0]
    assert rent["sant_positiva"] == 3 and rent["falskt_positiva"] == 0           # med C har inga gemensamma ord men hög cosinus
    strang = inbaddningar.hybrid(rader, vek, troskler=[0.9], min_delade=2)[0]
    assert strang["sant_positiva"] == 1 and strang["falskt_negativa"] == 2


# ---------- Produktionsvägen: regler, andra varvet och hybridens andra varv ----------

def test_dagens_klustring_ar_regler_och_andra_varvet():
    import inspect
    assert "merge_clusters" in inspect.getsource(inbaddningar._dagens_hem)


def test_hybridens_klustervag_matt_pa_samma_satt():
    rader = [{"kalla": "A", "typ": "media", "rubrik": "Democrats win Congress control in midterm election", "handelse": "valet"},
             {"kalla": "B", "typ": "media", "rubrik": "Democrats win Congress control in midterm vote", "handelse": "valet"},
             {"kalla": "C", "typ": "media", "rubrik": "Storm Amy floods Gothenburg harbour", "handelse": "storm"}]
    vek = {r["rubrik"]: v for r, v in zip(rader, [[1.0, 0.0], [0.99, 0.1], [0.0, 1.0]])}
    m = inbaddningar.hybridens_kluster(rader, vek, tau=0.9, min_delade=2, pair_rate=0.25)
    assert m["sant_positiva"] == 1 and m["falskt_positiva"] == 0 and m["falskt_negativa"] == 0 and m["tau"] == 0.9


def test_parametersvepet_ger_en_rad_per_kombination():
    rader = [{"kalla": "A", "typ": "media", "rubrik": "Democrats win Congress control in midterm election", "handelse": "valet"},
             {"kalla": "B", "typ": "media", "rubrik": "Democrats win Congress control in midterm vote", "handelse": "valet"}]
    vek = {r["rubrik"]: v for r, v in zip(rader, [[1.0, 0.0], [0.99, 0.1]])}
    ut = inbaddningar.parametersvep(rader, vek, taus=[0.5, 0.6], delade=[1, 2], rater=[0.25])
    assert len(ut) == 4 and {(r["tau"], r["min_delade"]) for r in ut} == {(0.5, 1), (0.5, 2), (0.6, 1), (0.6, 2)}


# ---------- Diagnos på riktiga händelser ----------

def test_handelsediagnosen_visar_vilka_handelsepar_som_ligger_narmast_varandra():
    def h(eid, rubriker):
        return {"id": eid, "reserv_rubrik": rubriker[0], "utkast": {"rubrik_en": rubriker[0]},
                "kallor": [{"namn": f"K{eid}{n}", "rubrik": r} for n, r in enumerate(rubriker)]}
    handelser = [h("a", ["Democrats win Congress control in midterm election", "Democrats win Congress in midterms again vote"]),
                 h("b", ["Democrats win Congress control in midterm vote", "Congress control: Democrats win midterm election"]),
                 h("c", ["Storm Amy floods Gothenburg harbour", "Gothenburg harbour floods in Storm Amy"])]
    vek = {t: [1.0, 0.0] if "Democrats" in t or "Congress" in t else [0.0, 1.0] for e in handelser for t in [k["rubrik"] for k in e["kallor"]]}
    par = inbaddningar.handelsepar(handelser, lambda texter: [vek[t] for t in texter], tau=0.6, min_delade=2)
    assert par[0]["a"] == "a" and par[0]["b"] == "b" and par[0]["traffar"] >= 2 and 0 < par[0]["andel"] <= 1
    assert all({p["a"], p["b"]} != {"a", "c"} for p in par)
