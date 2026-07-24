from pathlib import Path
from unittest.mock import MagicMock

from murray3d.config import Settings
from murray3d.models import GeneratedMeta, Model3D
from murray3d.publish import commit_publish, prepare_publish


def make_settings(tmp_path):
    return Settings(base_url="https://x/3dbundle/api", api_key="k",
                    cache_dir=tmp_path / "c", shots_dir=tmp_path / "s",
                    known_categories=["figures", "both"])


def test_prepare_publish_wires_render_and_ai(tmp_path):
    settings = make_settings(tmp_path)
    client = MagicMock()
    client.download_model.return_value = tmp_path / "m.glb"
    shots = [tmp_path / "shot_00.png", tmp_path / "shot_01.png"]
    meta = GeneratedMeta(title="T", description="D", tags=["a"], category="both",
                         best_thumbnail_index=1)

    render_fn = MagicMock(return_value=shots)
    ai_fn = MagicMock(return_value=meta)
    got_meta, got_shots = prepare_publish(client, settings, 9,
                                          render_fn=render_fn, ai_fn=ai_fn)
    assert got_meta is meta and got_shots == shots
    client.download_model.assert_called_once()
    render_fn.assert_called_once()
    ai_fn.assert_called_once_with(shots, settings.known_categories)


def test_commit_publish_calls_patch_and_thumbnail(tmp_path):
    client = MagicMock()
    client.publish_model.return_value = Model3D(id=9, title="T", published=True)
    shots = [tmp_path / "shot_00.png", tmp_path / "shot_01.png"]
    meta = GeneratedMeta(title="T", description="D", tags=["a", "b"],
                         category="both", price_eur=3.0, best_thumbnail_index=1)
    out = commit_publish(client, 9, meta, shots)
    assert out.published is True
    kwargs = client.publish_model.call_args.kwargs
    assert kwargs["title"] == "T" and kwargs["category"] == "both"
    assert kwargs["tags"] == ["a", "b"] and kwargs["price_eur"] == 3.0
    client.set_thumbnail.assert_called_once_with(9, shots[1])
