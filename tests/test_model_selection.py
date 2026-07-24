import json
from pathlib import Path


def _ok_runner(store, payload):
    def runner(cmd, cwd):
        store["cmd"] = cmd
        return json.dumps({"result": json.dumps(payload)})
    return runner


META = {"title": "T", "description": "D", "tags": [], "category": "both",
        "best_thumbnail_index": 0}
PACK_META = {"title": "T", "description": "D", "tags": [], "best_cover_index": 0}


def _shots(tmp_path, n=1):
    out = []
    for i in range(n):
        s = tmp_path / f"shot_{i:02d}.png"; s.write_bytes(b"png"); out.append(s)
    return out


def test_generate_metadata_threads_model(tmp_path):
    from murray3d.ai import generate_metadata
    store = {}
    generate_metadata(_shots(tmp_path), ["both"], runner=_ok_runner(store, META), model="haiku")
    cmd = store["cmd"]
    assert "--model" in cmd and cmd[cmd.index("--model") + 1] == "haiku"


def test_generate_metadata_no_model_by_default(tmp_path):
    from murray3d.ai import generate_metadata
    store = {}
    generate_metadata(_shots(tmp_path), ["both"], runner=_ok_runner(store, META))
    assert "--model" not in store["cmd"]


def test_generate_pack_metadata_threads_model(tmp_path):
    from murray3d.ai import generate_pack_metadata
    store = {}
    generate_pack_metadata(_shots(tmp_path), ["m"], runner=_ok_runner(store, PACK_META),
                           model="opus")
    cmd = store["cmd"]
    assert "--model" in cmd and cmd[cmd.index("--model") + 1] == "opus"


def test_prepare_publish_passes_model_to_ai(tmp_path):
    from unittest.mock import MagicMock

    from murray3d.config import Settings
    from murray3d.models import GeneratedMeta
    from murray3d.publish import prepare_publish

    settings = Settings(base_url="https://x/3dbundle/api", api_key="k",
                        cache_dir=tmp_path / "c", shots_dir=tmp_path / "s",
                        known_categories=["both"])
    client = MagicMock()
    client.download_model.return_value = tmp_path / "m.glb"
    ai_fn = MagicMock(return_value=GeneratedMeta(title="T", description="D", tags=[],
                                                 category="both"))
    render_fn = MagicMock(return_value=[tmp_path / "shot_00.png"])
    prepare_publish(client, settings, 9, render_fn=render_fn, ai_fn=ai_fn, model="sonnet")
    assert ai_fn.call_args.kwargs.get("model") == "sonnet"
