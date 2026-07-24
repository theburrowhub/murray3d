from pathlib import Path

import httpx
import pytest

from murray3d.api import Client, NotFoundError
from murray3d.config import Settings


def make_settings(tmp_path):
    return Settings(base_url="https://api.test/3dbundle/api", api_key="k",
                    cache_dir=tmp_path / "c", shots_dir=tmp_path / "s",
                    known_categories=["both"])


MODEL_JSON = {"id": 7, "title": "T", "published": False, "tags": [], "category": "both"}


def test_list_models_query_params(tmp_path):
    seen = {}

    def handler(request):
        seen["params"] = dict(request.url.params)
        return httpx.Response(200, json=[MODEL_JSON])

    c = Client(make_settings(tmp_path), transport=httpx.MockTransport(handler))
    out = c.list_models(q="dragon", category="both", only_published=True, limit=10)
    assert len(out) == 1 and out[0].id == 7
    assert seen["params"]["q"] == "dragon"
    assert seen["params"]["category"] == "both"
    assert seen["params"]["only_published"] == "true"
    assert seen["params"]["limit"] == "10"


def test_upload_model_multipart(tmp_path):
    seen = {}
    f = tmp_path / "m.glb"
    f.write_bytes(b"glTF-bytes")

    def handler(request):
        seen["content_type"] = request.headers.get("content-type", "")
        seen["body"] = request.content
        return httpx.Response(200, json={**MODEL_JSON, "title": "Dragón"})

    c = Client(make_settings(tmp_path), transport=httpx.MockTransport(handler))
    m = c.upload_model(f, title="Dragón", tags=["a", "b"], category="both")
    assert m.title == "Dragón"
    assert "multipart/form-data" in seen["content_type"]
    assert "Dragón".encode() in seen["body"]
    assert b"a,b" in seen["body"]


def test_update_model_sends_only_set_fields(tmp_path):
    seen = {}

    def handler(request):
        seen["json"] = request.read()
        return httpx.Response(200, json={**MODEL_JSON, "published": True})

    c = Client(make_settings(tmp_path), transport=httpx.MockTransport(handler))
    m = c.publish_model(7, title="Nuevo", tags=["x"])
    assert m.published is True
    body = seen["json"].decode()
    assert '"published": true' in body.replace(" ", "").replace("\n", "") or '"published":true' in body.replace(" ", "")
    assert "Nuevo" in body


def test_set_thumbnail_multipart(tmp_path):
    seen = {}
    img = tmp_path / "shot.png"
    img.write_bytes(b"\x89PNG\r\n")

    def handler(request):
        seen["ct"] = request.headers.get("content-type", "")
        return httpx.Response(200, json=MODEL_JSON)

    c = Client(make_settings(tmp_path), transport=httpx.MockTransport(handler))
    c.set_thumbnail(7, img)
    assert "multipart/form-data" in seen["ct"]


def test_delete_model(tmp_path):
    seen = {}

    def handler(request):
        seen["method"] = request.method
        return httpx.Response(204)

    c = Client(make_settings(tmp_path), transport=httpx.MockTransport(handler))
    c.delete_model(7)
    assert seen["method"] == "DELETE"


def test_download_model_writes_file(tmp_path):
    body = b"glTF-binary-bytes"
    seen = {"calls": 0}

    def handler(request):
        seen["calls"] += 1
        return httpx.Response(200, content=body)

    c = Client(make_settings(tmp_path), transport=httpx.MockTransport(handler))
    dest = tmp_path / "out.glb"
    result = c.download_model(7, dest)
    assert result == dest
    assert dest.read_bytes() == body
    assert seen["calls"] == 1


def test_download_model_error_raises_and_does_not_write(tmp_path):
    seen = {"calls": 0}

    def handler(request):
        seen["calls"] += 1
        return httpx.Response(404, json={"detail": "not found"})

    c = Client(make_settings(tmp_path), transport=httpx.MockTransport(handler))
    dest = tmp_path / "out.glb"
    with pytest.raises(NotFoundError):
        c.download_model(7, dest)
    assert not dest.exists()
    assert seen["calls"] == 1
