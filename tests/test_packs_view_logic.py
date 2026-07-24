from murray3d.gui.packs_view import parse_ids


def test_parse_ids():
    assert parse_ids("1, 2 ,3") == [1, 2, 3]
    assert parse_ids("") == []
    assert parse_ids("a, 4, x, 5") == [4, 5]
