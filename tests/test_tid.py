"""Allt tidsstämplas: svensk tid på svenska, UTC på engelska."""
import instagram
import render

TS = 1_793_900_000


def test_svensk_tid_och_utc():
    sv, en = render.tidstext(1_762_340_000)
    assert sv.endswith("kl 11.53") and en.endswith("at 10:53 UTC")


def test_sommartid_foljer_stockholm():
    sv, en = render.tidstext(1_751_364_000)
    assert sv.endswith("kl 12.00") and en.endswith("at 10:00 UTC")


def test_stampel_ar_ett_time_element():
    assert '<time datetime="' in render.stampel(TS) and "Z\">" in render.stampel(TS)


def _ev(**x):
    return {"id": "a", "antal_kallor": 1, "reserv_rubrik": "R", "utkast": {}, "perspektiv": {"regioner": ["usa"]},
            "kallor": [{"namn": "K", "url": "https://k", "rubrik": "R", "tid": TS}], **x}


def test_listor_och_kallor_bar_tid():
    assert "<time" in render.story_item(_ev(godkand_tid=TS), "/n/a/")
    assert "<time" in render.meta_block(_ev(godkand_tid=TS))
    assert "<time" in render.source_list(_ev())


def test_utkast_utan_tid_far_ingen_stampel():
    assert "<time" not in render.story_item(_ev(), "/n/a/")


def test_gamla_kallor_utan_tid_fungerar():
    ev = _ev()
    del ev["kallor"][0]["tid"]
    assert "<time" not in render.source_list(ev)


def test_bildtexten_har_tid():
    assert "Publicerad" in instagram.caption(_ev(godkand_tid=TS), "sv")
    assert "UTC" in instagram.caption(_ev(godkand_tid=TS), "en")
