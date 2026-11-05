"""Sektionen Nöje och spel: spel, kultur och nöje i en gemensam sektion."""
from pathlib import Path

import yaml

import pipeline
from newsletter import SECTIONS, section_of

FEEDS = Path(__file__).parent.parent / "feeds.yaml"


def artikel(kalla, rubrik, amnen, region="sverige", n=0):
    return {"source_id": kalla, "source_name": kalla, "source_type": "media", "title": rubrik, "description": "",
            "topics": amnen, "region": region, "epoch": 1000 - n}


def sektion(*artiklar):
    c = {"items": list(artiklar)}
    return section_of({"amnen_sektion": pipeline.tag(c)[1]})


def test_sektionen_finns_och_kommer_sist():
    assert SECTIONS[-1][:3] == ("noje", "Nöje och spel", "Entertainment and games")


def test_spelnyhet_fran_en_kalla():
    assert sektion(artikel("gameranx", "EA Reveals Restructuring Plans After Going Private", ["spel"], "usa")) == "noje"


def test_noje_gar_fore_sverige():
    assert sektion(artikel("aftonbladet-noje", "Rammstein-sångaren kommer till Sverige", ["noje"])) == "noje"


def test_tech_gar_fore_spel():
    a = artikel("gameranx", "Sakurai believes AI will harm game development", ["spel"], "usa")
    assert sektion(a) == "tech"


def test_en_nojeskalla_flyttar_inte_en_varldsnyhet():
    a = artikel("svt", "Machado tillbaka i Venezuela", ["sverige", "varlden"], n=0)
    b = artikel("bbc", "Machado returns to Venezuela", ["varlden"], "europa", n=1)
    c = artikel("aftonbladet-noje", "Machado tillbaka i Venezuela", ["noje"], n=2)
    assert sektion(a, b, c) != "noje"
    assert sektion(a, c) != "noje"


def test_platser_reserveras_for_noje_och_spel():
    def kluster(sek, poang, n):
        return {"items": [artikel(f"k{sek}{n}", f"rubrik {n}", [sek], n=n)], "score": poang,
                "section_topics": [sek]}
    varld = [kluster("varlden", 20 - n * 0.1, n) for n in range(10)]
    noje = [kluster("spel", 3 - n * 0.1, n) for n in range(6)]
    valda = pipeline.choose(varld + noje, limit=8)
    assert len(valda) == 8
    assert sum(1 for c in valda if "spel" in c["section_topics"]) == pipeline.RESERVED["noje"]
    assert [c["score"] for c in valda] == sorted((c["score"] for c in valda), reverse=True)
    # Finns det inte fler nöjesnyheter tas platserna av andra
    assert len(pipeline.choose(varld + noje[:1], limit=8)) == 8


def test_nya_kallor():
    kallor = {s["id"]: s for s in yaml.safe_load(FEEDS.read_text(encoding="utf-8"))["sources"]}
    for kid in ("gameranx", "fz", "aftonbladet-noje", "expressen-noje"):
        assert kid in kallor, kid
        assert set(kallor[kid]["amnen"]) & {"spel", "noje"}
    # Stänger ute AI-botar i robots.txt: bara rubrik och länk, ingressen går aldrig till AI:n
    assert kallor["aftonbladet-noje"]["bara_rubrik"] and kallor["expressen-noje"]["bara_rubrik"]


def test_energi_i_en_varldsnyhet_ar_inte_vetenskap():
    assert section_of({"amnen_sektion": ["energi", "usa"]}) == "varlden"
    assert section_of({"amnen_sektion": ["energi", "geopolitik"]}) == "varlden"
    assert section_of({"amnen_sektion": ["energi"]}) == "vetenskap"
    assert section_of({"amnen_sektion": ["klimat", "usa"]}) == "vetenskap"
