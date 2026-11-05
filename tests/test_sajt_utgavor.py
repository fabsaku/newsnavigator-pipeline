"""A4: sajten som två utgåvor, /sv/ och /en/. Separata träd, var och en på ett språk, med bara de notiser som hör hemma där."""
from html.parser import HTMLParser
from pathlib import Path

import instagram
import sajt
from test_lansering import GLOBAL, NU, historia, kalla


def notis(n, **kw):
    ev = historia(n, **kw)["ev"]
    ev["godkand_tid"] = NU - 3600
    ev["granskad"] = True
    per = {}
    for k in ev["kallor"]:
        per.setdefault(k["region"], []).append({"rubrik": k["rubrik"], "url": k["url"], "kalla": k["namn"], "land": k["land"], "statskontrollerad": False})
    ev["perspektiv"]["per_region"] = per
    return ev


SVENSK_KALLOR = [kalla("SVT", "sverige"), kalla("Ekot", "sverige"), kalla("DN", "sverige")]


def bygg(tmp_path, events, **kw):
    sajt.build_editions(tmp_path, events, **{"noindex": True, **kw})
    return tmp_path


def text(p):
    return Path(p).read_text(encoding="utf-8")


class Balans(HTMLParser):
    VOID = {"meta", "link", "br", "img", "input", "hr", "path", "circle", "rect"}

    def __init__(self):
        super().__init__()
        self.stack, self.fel = [], []

    def handle_starttag(self, tag, attrs):
        if tag not in self.VOID:
            self.stack.append(tag)

    def handle_endtag(self, tag):
        if tag in self.VOID:
            return
        if not self.stack or self.stack[-1] != tag:
            self.fel.append(tag)
        else:
            self.stack.pop()


def test_tva_trad_och_en_valsida(tmp_path):
    ut = bygg(tmp_path, [notis(1), notis(2)])
    for sid in ("sv/index.html", "en/index.html", "index.html", "sv/om/index.html", "en/kallor/index.html", "sv/feed.xml", "en/feed.xml"):
        assert (ut / sid).exists(), sid
    val = text(ut / "index.html")
    assert 'href="/sv/"' in val and 'href="/en/"' in val
    assert '<html lang="sv"' in text(ut / "sv/index.html") and '<html lang="en"' in text(ut / "en/index.html")


def test_varje_trad_ar_pa_ett_sprak(tmp_path):
    ut = bygg(tmp_path, [notis(1), notis(2)])
    for lang in ("sv", "en"):
        for sida in (ut / lang).rglob("index.html"):
            t = text(sida)
            assert '<span class="sv">' not in t and '<span class="en">' not in t, sida
            b = Balans()
            b.feed(t)
            assert not b.fel and not b.stack, (sida, b.fel, b.stack)
    assert "Latest" in text(ut / "en/index.html") and "Senaste" not in text(ut / "en/index.html")
    assert "Senaste" in text(ut / "sv/index.html") and "Latest" not in text(ut / "sv/index.html")


def test_svenskt_lokalt_finns_bara_i_svenska_tradet(tmp_path):
    lokalt = notis(1, kallor=SVENSK_KALLOR, rubrik_en="Assault in Uppsala")
    ut = bygg(tmp_path, [lokalt, notis(2)])
    assert (ut / "sv/n" / lokalt["id"] / "index.html").exists()
    assert not (ut / "en/n" / lokalt["id"]).exists()
    assert lokalt["id"] not in text(ut / "en/index.html") and lokalt["id"] not in text(ut / "en/feed.xml")
    assert (ut / "en/n" / notis(2)["id"] / "index.html").exists()


def test_engelska_tradet_kraver_engelsk_text(tmp_path):
    ev = notis(3)
    ev["utkast"]["rubrik_en"] = ""
    ev["utkast"]["sammanfattning_en"] = ""
    ut = bygg(tmp_path, [ev])
    assert (ut / "sv/n" / ev["id"] / "index.html").exists() and not (ut / "en/n" / ev["id"]).exists()


def test_notissidans_adress_ar_den_bildtexterna_lankar_till(tmp_path):
    ev = notis(4)
    ut = bygg(tmp_path, [ev])
    for lang in ("sv", "en"):
        url = instagram.notis_url(lang, ev["id"])
        assert url == f"{sajt.SITE_URL}/{lang}/n/{ev['id']}/"
        assert (ut / url.removeprefix(sajt.SITE_URL).strip("/") / "index.html").exists()


def test_engelska_tradet_gor_inte_paastaendet_saknas_i_svenska_medier(tmp_path):
    ev = notis(5, blind="saknas_i_sverige")
    ut = bygg(tmp_path, [ev], over_sprak=True)
    assert "Saknas i svenska medier" in text(ut / "sv/n" / ev["id"] / "index.html")
    en = text(ut / "en/n" / ev["id"] / "index.html")
    assert "Not in Swedish media" not in en and "Saknas" not in en


def test_titel_och_beskrivning_pa_traedets_sprak(tmp_path):
    ev = notis(6, rubrik_en="Zeta zebra quarry quartz")
    ev["utkast"]["rubrik_sv"] = "Svensk rubrik utan engelska ord"
    ut = bygg(tmp_path, [ev])
    en = text(ut / "en/n" / ev["id"] / "index.html")
    sv = text(ut / "sv/n" / ev["id"] / "index.html")
    assert "<title>Zeta zebra quarry quartz" in en and "<title>Svensk rubrik" in sv
    assert "Svensk rubrik" not in en


def test_flodena_pa_varsitt_sprak(tmp_path):
    ev = notis(7, rubrik_en="Zeta zebra quarry quartz")
    ev["utkast"]["rubrik_sv"] = "Svensk rubrik"
    ut = bygg(tmp_path, [ev])
    assert "Svensk rubrik" in text(ut / "sv/feed.xml") and "Zeta zebra" not in text(ut / "sv/feed.xml")
    assert "Zeta zebra" in text(ut / "en/feed.xml") and "<language>en</language>" in text(ut / "en/feed.xml")


def test_sprakbyte_lankar_till_andra_utgavan(tmp_path):
    ut = bygg(tmp_path, [notis(1)])
    assert 'href="/en/"' in text(ut / "sv/index.html") and 'href="/sv/"' in text(ut / "en/index.html")
    assert 'hreflang="en"' in text(ut / "sv/index.html") and 'hreflang="x-default"' in text(ut / "sv/index.html")


def test_noindex_tills_lanseringen(tmp_path):
    assert 'name="robots" content="noindex"' in text(bygg(tmp_path / "a", [notis(1)]) / "en/index.html")
    assert 'name="robots"' not in text(bygg(tmp_path / "b", [notis(1)], noindex=False) / "sv/index.html")


def test_gamla_adresser_skickas_vidare_och_gammalt_rensas(tmp_path):
    (tmp_path / "n" / "123").mkdir(parents=True)
    (tmp_path / "n" / "123" / "index.html").write_text("gammal")
    (tmp_path / "varlden").mkdir()
    (tmp_path / "varlden" / "index.html").write_text("gammal")
    (tmp_path / "feed.xml").write_text("gammal")
    ut = bygg(tmp_path, [notis(1)])
    assert not (ut / "n").exists() and not (ut / "varlden").exists() and not (ut / "feed.xml").exists()
    r = text(ut / "_redirects")
    assert "/n/* /sv/n/:splat 301" in r and "/feed.xml /sv/feed.xml 301" in r and "/feed-en.xml /en/feed.xml 301" in r


def test_lanseringens_kort_och_forhandsgranskning_rors_inte(tmp_path):
    (tmp_path / "ig/en/x").mkdir(parents=True)
    (tmp_path / "ig/en/x/1.jpg").write_bytes(b"x")
    (tmp_path / "lansering").mkdir()
    (tmp_path / "lansering/en.html").write_text("förhandsgranskning")
    ut = bygg(tmp_path, [notis(1)])
    assert (ut / "ig/en/x/1.jpg").exists() and (ut / "lansering/en.html").exists()


def test_sitemap_listar_bada_tradena():
    sv, en = notis(1, kallor=SVENSK_KALLOR, rubrik_en="Assault in Uppsala"), notis(2)
    xml = sajt.sitemap_xml({"sv": [sv, en], "en": [en]})
    assert f"{sajt.SITE_URL}/sv/n/{sv['id']}/" in xml and f"{sajt.SITE_URL}/en/n/{en['id']}/" in xml
    assert f"/en/n/{sv['id']}/" not in xml and f"{sajt.SITE_URL}/en/" in xml and f"{sajt.SITE_URL}/sv/" in xml


def test_navigatorn_per_utgava(tmp_path):
    ut = bygg(tmp_path, [notis(1)], issues={"sv": False, "en": False})
    assert (ut / "sv/navigatorn/index.html").exists() and (ut / "en/navigatorn/index.html").exists()


def test_forhandsvisningen_ar_oforandrad_tvasprakig(tmp_path):
    sajt.build(tmp_path, [notis(1)], flat=True)
    t = text(tmp_path / "index.html")
    assert 'class="sv"' in t and 'class="en"' in t and "n-" in t


def test_forstasidan_visar_hogst_tva_notiser_per_handelse():
    import newsletter
    def notis(i, rubrik, kallor):
        return {"id": str(i), "antal_kallor": kallor, "reserv_rubrik": rubrik, "kallor": [{"url": f"https://k/{i}"}], "utkast": {}}
    val = [notis(i, "Democrats win control of Congress in midterm election", i + 1) for i in range(4)]
    annan = notis(9, "Train crash near Toledo in Spain leaves many dead", 2)
    kvar = newsletter.utan_upprepningar(val + [annan])
    assert [e["id"] for e in kvar] == ["2", "3", "9"]


def _utgavenotis(i, tid, *regioner, rubrik="Budget vote in parliament"):
    return {"id": str(i), "godkand_tid": tid, "reserv_rubrik": rubrik, "utkast": {"rubrik_en": rubrik},
            "kallor": [{"region": r, "typ": "media"} for r in regioner]}


def test_utgavorna_lyfter_det_som_angar_lasaren():
    import utgava
    nu = 1_000_000
    svenskt = _utgavenotis(1, nu - 3600, "sverige", "sverige", "sverige")
    globalt = _utgavenotis(2, nu - 3600, "usa", "europa", "asien", rubrik="Summit opens in Nairobi")
    annat = _utgavenotis(3, nu, "usa", "usa", "usa", rubrik="Senate passes budget")
    for e in (svenskt, globalt, annat):
        e["poang"] = 30
    assert utgava.ordna([annat, globalt, svenskt], "sv", nu=nu)[0]["id"] == "1"
    assert utgava.ordna([annat, svenskt, globalt], "en", nu=nu)[0]["id"] == "2"


def test_viktigast_forst_och_vikten_klingar_av():
    import utgava
    nu = 1_000_000
    tung = {**_utgavenotis(1, nu - 3600, "usa", "usa", "usa"), "poang": 40}
    latt = {**_utgavenotis(2, nu, "usa", "usa", "usa"), "poang": 20}
    gammal = {**_utgavenotis(3, nu - 3 * 86400, "usa", "usa", "usa"), "poang": 40}
    assert [e["id"] for e in utgava.ordna([latt, gammal, tung], "sv", nu=nu)] == ["1", "2", "3"]


def test_lokalt_svenskt_med_tva_kallor_visas_inte_pa_engelska():
    import utgava
    assert not utgava.visa(_utgavenotis(1, 1, "sverige", "sverige", rubrik="Nato debate in parliament"), "en")
    assert utgava.visa(_utgavenotis(2, 1, "sverige", "sverige", "sverige", rubrik="Nato debate in parliament"), "en")
    assert utgava.visa(_utgavenotis(3, 1, "sverige", "sverige"), "sv")


def test_engelska_utgavan_ar_global_utan_hemland():
    import utgava
    assert utgava.angar(_utgavenotis(1, 1, "afrika", "asien", "europa", rubrik="Summit opens in Nairobi"), "en")
    assert not utgava.angar(_utgavenotis(2, 1, "usa", "usa", "usa", rubrik="Senate passes budget"), "en")


def test_varje_notis_i_listor_bar_sitt_marke():
    from render import story_item
    bas = {"id": "a", "antal_kallor": 3, "reserv_rubrik": "Rubrik", "kallor": [], "utkast": {}, "perspektiv": {"regioner": ["usa"]}}
    assert "ej manuellt granskad" in story_item({**bas, "automatisk": True}, "/n/a/")
    assert "granskad av redaktionen" in story_item({**bas, "granskad": True}, "/n/a/")
    assert "reviewed in Swedish" in story_item({**bas, "granskad": True}, "/n/a/")
    assert "AI," not in story_item(bas, "/n/a/")
