import httpx

from murray3d.api import Client
from murray3d.config import Settings


def make_settings(tmp_path):
    return Settings(base_url="https://api.test/3dbundle/api", api_key="k",
                    cache_dir=tmp_path / "c", shots_dir=tmp_path / "s",
                    known_categories=["both"])


def test_create_pack(tmp_path):
    seen = {}

    def handler(request):
        seen["json"] = request.read().decode()
        return httpx.Response(200, json={"id": 3, "title": "Pack", "model_ids": [1, 2]})

    c = Client(make_settings(tmp_path), transport=httpx.MockTransport(handler))
    p = c.create_pack("Pack", model_ids=[1, 2])
    assert p.id == 3 and p.model_ids == [1, 2]
    assert "Pack" in seen["json"]


def test_add_models_to_pack_merges_without_dupes(tmp_path):
    state = {"model_ids": [1, 2]}
    calls = []

    def handler(request):
        calls.append(request.method)
        if request.method == "GET":
            return httpx.Response(200, json={"id": 3, "title": "P", "model_ids": state["model_ids"]})
        # PATCH
        body = request.read().decode()
        import json
        state["model_ids"] = json.loads(body)["model_ids"]
        return httpx.Response(200, json={"id": 3, "title": "P", "model_ids": state["model_ids"]})

    c = Client(make_settings(tmp_path), transport=httpx.MockTransport(handler))
    p = c.add_models_to_pack(3, [2, 5, 7])
    assert p.model_ids == [1, 2, 5, 7]
    assert calls == ["GET", "PATCH"]
