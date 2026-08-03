import httpx
import pytest

from murray3d.freepik import (
    FreepikClient,
    FreepikError,
    map_aspect_ratio,
)


def make_client(handler, **kw):
    return FreepikClient("fk-test", transport=httpx.MockTransport(handler),
                         sleep=lambda *_: None, **kw)


def test_map_aspect_ratio():
    assert map_aspect_ratio("3:4") == "traditional_3_4"
    assert map_aspect_ratio("1:1") == "square_1_1"
    assert map_aspect_ratio("traditional_3_4") == "traditional_3_4"  # ya válido
    assert map_aspect_ratio(None) == "square_1_1"


def test_create_task_sends_key_and_maps_aspect():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["key"] = request.headers.get("x-freepik-api-key")
        captured["path"] = request.url.path
        import json as _j
        captured["body"] = _j.loads(request.content)
        return httpx.Response(200, json={"data": {"task_id": "t1", "status": "CREATED"}})

    c = make_client(handler)
    tid = c.create_task("un goku", model="flux-dev", aspect_ratio="3:4", seed=5)
    assert tid == "t1"
    assert captured["key"] == "fk-test"
    assert captured["path"] == "/v1/ai/text-to-image/flux-dev"
    assert captured["body"]["aspect_ratio"] == "traditional_3_4"
    assert captured["body"]["seed"] == 5
    # flux-dev no debe llevar negative_prompt aunque se pase
    assert "negative_prompt" not in captured["body"]


def test_generate_polls_until_completed():
    calls = {"n": 0}

    def handler(request):
        if request.method == "POST":
            return httpx.Response(200, json={"data": {"task_id": "t9", "status": "CREATED"}})
        calls["n"] += 1
        if calls["n"] < 2:
            return httpx.Response(200, json={"data": {"status": "IN_PROGRESS", "generated": []}})
        return httpx.Response(200, json={
            "data": {"status": "COMPLETED", "generated": ["https://cdn/x.jpg"]}})

    c = make_client(handler)
    urls = c.generate("p", model="flux-dev", aspect_ratio="3:4", poll_interval=0.01)
    assert urls == ["https://cdn/x.jpg"]
    assert calls["n"] == 2


def test_generate_raises_on_failed():
    def handler(request):
        if request.method == "POST":
            return httpx.Response(200, json={"data": {"task_id": "t", "status": "CREATED"}})
        return httpx.Response(200, json={"data": {"status": "FAILED", "generated": []}})

    c = make_client(handler)
    with pytest.raises(FreepikError, match="FAILED"):
        c.generate("p", poll_interval=0.01)


def test_retry_on_429_then_success():
    state = {"posts": 0}

    def handler(request):
        if request.method == "POST":
            state["posts"] += 1
            if state["posts"] == 1:
                return httpx.Response(429, headers={"Retry-After": "0"}, json={"message": "slow down"})
            return httpx.Response(200, json={"data": {"task_id": "t", "status": "CREATED"}})
        return httpx.Response(200, json={"data": {"status": "COMPLETED", "generated": ["u"]}})

    c = make_client(handler)
    urls = c.generate("p", poll_interval=0.01)
    assert urls == ["u"]
    assert state["posts"] == 2


def test_http_error_raises():
    def handler(request):
        return httpx.Response(400, json={"message": "prompt inválido"})

    c = make_client(handler)
    with pytest.raises(FreepikError, match="inválido"):
        c.create_task("p")


def test_unknown_model_raises():
    c = make_client(lambda r: httpx.Response(200, json={}))
    with pytest.raises(FreepikError, match="no soportado"):
        c.create_task("p", model="dalle")
