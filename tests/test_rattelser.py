"""Rättelsesidan och notissidor som består."""
import rattelser
import sajt


def _ev(eid="abc"):
    return {"id": eid, "reserv_rubrik": "Rubrik", "utkast": {"rubrik_sv": "Svensk", "rubrik_en": "English"}}


def test_borttagen_loggas_och_syns(tmp_path):
    fil = tmp_path / "rattelser.json"
    rattelser.borttagen(_ev(), fil, nu=1_000_000)
    assert rattelser.borttagna_id(fil) == {"abc"}
    sv = sajt.rattelser_page(sajt.Urls(flat=False, lang="sv"), rattelser.load(fil), [], "", True)
    en = sajt.rattelser_page(sajt.Urls(flat=False, lang="en"), rattelser.load(fil), [], "", True)
    assert "Svensk" in sv and "togs bort efter publicering" in sv
    assert "English" in en and "removed after publication" in en


def test_tom_sida_sager_det():
    assert "Inga rättelser än" in sajt.rattelser_page(sajt.Urls(flat=False, lang="sv"), [], [], "", True)


def test_handskriven_rattelse_hor_till_notisen(tmp_path):
    fil = tmp_path / "rattelser.json"
    fil.write_text('[{"id": "abc", "tid": 1, "typ": "rattad", "vad_sv": "Siffran var fel."}]', encoding="utf-8")
    assert rattelser.for_notis("abc", fil)[0]["vad_sv"] == "Siffran var fel."
    assert rattelser.for_notis("xyz", fil) == [] and rattelser.borttagna_id(fil) == set()


def test_gamla_notissidor_bestar_men_borttagna_forsvinner(tmp_path, monkeypatch):
    monkeypatch.setattr(rattelser, "FIL", tmp_path / "rattelser.json")
    rattelser.borttagen(_ev("bort"), tmp_path / "rattelser.json")
    ndir = tmp_path / "ut" / "sv" / "n"
    for namn in ("gammal", "bort"):
        (ndir / namn).mkdir(parents=True)
        (ndir / namn / "index.html").write_text("x", encoding="utf-8")
    sajt.build(tmp_path / "ut", [], lang="sv")
    assert (ndir / "gammal" / "index.html").exists() and not (ndir / "bort").exists()
