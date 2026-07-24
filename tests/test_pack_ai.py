import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from murray3d.ai import AiError, build_pack_prompt, generate_pack_metadata
from murray3d.config import Settings
from murray3d.gui.publish_dialog import pack_meta_from_form
from murray3d.models import GeneratedPackMeta, Pack
from murray3d.publish import commit_pack_publish, prepare_pack_publish


def _settings(tmp_path):
    return Settings(base_url="https://x/3dbundle/api", api_key="k",
                    cache_dir=tmp_path / "c", shots_dir=tmp_path / "s",
                    known_categories=["both"])


def test_build_pack_prompt_pairs_image_with_title(tmp_path):
    shots = [tmp_path / "cover_00.png", tmp_path / "cover_01.png"]
    prompt = build_pack_prompt(shots, ["Orco", "Dragón"])
    assert "cover_00.png: Orco" in prompt
    assert "cover_01.png: Dragón" in prompt
    assert "PACK" in prompt


def test_generate_pack_metadata_parses(tmp_path):
    inner = {"title": "Bundle de fantasía", "description": "Set completo.",
             "tags": ["orco", "dragón"], "price_eur": 12.0, "best_cover_index": 1}
    wrapper = {"result": json.dumps(inner)}
    shots = [tmp_path / "cover_00.png", tmp_path / "cover_01.png"]
    for s in shots:
        s.write_bytes(b"png")
    meta = generate_pack_metadata(shots, ["A", "B"], runner=lambda c, w: json.dumps(wrapper))
    assert isinstance(meta, GeneratedPackMeta)
    assert meta.title == "Bundle de fantasía"
    assert meta.best_cover_index == 1
    assert meta.price_eur == 12.0


def test_generate_pack_metadata_clamps_cover_index(tmp_path):
    inner = {"title": "T", "description": "D", "tags": [], "best_cover_index": 99}
    wrapper = {"result": json.dumps(inner)}
    shots = [tmp_path / "cover_00.png"]
    shots[0].write_bytes(b"png")
    meta = generate_pack_metadata(shots, ["A"], runner=lambda c, w: json.dumps(wrapper))
    assert meta.best_cover_index == 0


def test_generate_pack_metadata_empty_raises():
    with pytest.raises(AiError):
        generate_pack_metadata([], [])


def test_pack_meta_from_form():
    m = pack_meta_from_form("Pack X", "Desc", "a, b", 5.0)
    assert m.title == "Pack X" and m.tags == ["a", "b"] and m.price_eur == 5.0
    m2 = pack_meta_from_form("Y", "D", "", 0.0)
    assert m2.price_eur is None and m2.tags == []


def test_prepare_pack_publish_renders_one_shot_per_model(tmp_path):
    settings = _settings(tmp_path)
    client = MagicMock()
    client.get_pack.return_value = Pack(id=7, title="P", model_ids=[1, 2])
    client.get_model.side_effect = lambda mid: MagicMock(title=f"m{mid}", file_format="glb")
    client.download_model.side_effect = lambda mid, dest: Path(dest)

    calls = []

    def fake_render(src, out_dir, cache_dir, angles):
        calls.append(angles)
        shot = Path(out_dir) / "shot_00.png"
        shot.parent.mkdir(parents=True, exist_ok=True)
        shot.write_bytes(b"\x89PNG")
        return [shot]

    fake_ai = MagicMock(return_value=GeneratedPackMeta(
        title="Bundle", description="D", tags=["x"], price_eur=9.0, best_cover_index=0))

    meta, shots, pack = prepare_pack_publish(client, settings, 7,
                                             render_fn=fake_render, ai_fn=fake_ai)
    assert meta.title == "Bundle"
    assert len(shots) == 2  # una imagen por modelo
    assert all(len(a) == 1 for a in calls)  # un solo ángulo por modelo
    titles = fake_ai.call_args.args[1]
    assert titles == ["m1", "m2"]


def test_prepare_pack_publish_empty_pack_raises(tmp_path):
    settings = _settings(tmp_path)
    client = MagicMock()
    client.get_pack.return_value = Pack(id=7, title="P", model_ids=[])
    with pytest.raises(ValueError):
        prepare_pack_publish(client, settings, 7, render_fn=MagicMock(), ai_fn=MagicMock())


def test_commit_pack_publish_updates_and_publishes():
    client = MagicMock()
    client.update_pack.return_value = Pack(id=7, title="Bundle", published=True)
    meta = GeneratedPackMeta(title="Bundle", description="D", tags=["a", "b"], price_eur=9.0)
    out = commit_pack_publish(client, 7, meta, publish=True)
    assert out.published is True
    kwargs = client.update_pack.call_args.kwargs
    assert kwargs["title"] == "Bundle" and kwargs["published"] is True
    assert kwargs["tags"] == ["a", "b"] and kwargs["price_eur"] == 9.0
