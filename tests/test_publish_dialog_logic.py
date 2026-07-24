from murray3d.gui.publish_dialog import meta_from_form


def test_meta_from_form_parses_tags_and_price():
    meta = meta_from_form("Título", "Desc", "a, b ,c", "both", 3.5)
    assert meta.title == "Título"
    assert meta.tags == ["a", "b", "c"]
    assert meta.category == "both"
    assert meta.price_eur == 3.5


def test_meta_from_form_zero_price_is_none():
    meta = meta_from_form("T", "D", "", "figures", 0.0)
    assert meta.price_eur is None
    assert meta.tags == []
