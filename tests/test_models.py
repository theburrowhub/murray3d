from murray3d.models import GeneratedMeta, Model3D, Pack, Profile

SAMPLE_MODEL = {
    "title": "model (1)", "description": "", "tags": [], "filename": "model (1).glb",
    "file_format": "glb", "thumbnail": None, "owner_id": 1, "published": True,
    "updated_at": "2026-07-23T10:02:38", "id": 5, "category": "both",
    "price_eur": None, "stored_name": "u1/abc.glb", "file_size": 29116232,
    "uploader": "Manuel Zea", "author": "Manuel Zea", "created_at": "2026-07-23T10:02:38",
    "extra_field_ignored": "x",
}


def test_model3d_parses_and_ignores_extra():
    m = Model3D.model_validate(SAMPLE_MODEL)
    assert m.id == 5
    assert m.title == "model (1)"
    assert m.published is True
    assert m.file_size == 29116232


def test_pack_defaults():
    p = Pack.model_validate({"id": 1, "title": "Pack A"})
    assert p.model_ids == []
    assert p.published is False


def test_profile_parses():
    prof = Profile.model_validate({"id": 2, "email": "a@b.com", "name": "X", "author_name": "Muriano"})
    assert prof.author_name == "Muriano"


def test_generated_meta_defaults():
    g = GeneratedMeta.model_validate(
        {"title": "T", "description": "D", "tags": ["a"], "category": "both"}
    )
    assert g.best_thumbnail_index == 0
    assert g.price_eur is None
