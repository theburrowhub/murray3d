import httpx
import pytest

from murray3d.api import AuthError, Client, ValidationError
from murray3d.config import Settings


def make_settings(tmp_path):
    return Settings(
        base_url="https://api.test/3dbundle/api",
        api_key="k-123",
        cache_dir=tmp_path / "cache",
        shots_dir=tmp_path / "shots",
        known_categories=["both"],
    )


def test_whoami_sends_key_and_parses(tmp_path):
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["key"] = request.headers.get("X-API-Key")
        captured["url"] = str(request.url)
        return httpx.Response(200, json={"id": 2, "email": "a@b.com", "name": "N", "author_name": "Muriano"})

    client = Client(make_settings(tmp_path), transport=httpx.MockTransport(handler))
    prof = client.whoami()
    assert prof.author_name == "Muriano"
    assert captured["key"] == "k-123"
    assert captured["url"] == "https://api.test/3dbundle/api/auth/me"


def test_401_raises_auth_error(tmp_path):
    def handler(request):
        return httpx.Response(401, json={"detail": "clave inválida"})

    client = Client(make_settings(tmp_path), transport=httpx.MockTransport(handler))
    with pytest.raises(AuthError) as exc:
        client.whoami()
    assert "clave inválida" in exc.value.detail


def test_422_raises_validation_error(tmp_path):
    def handler(request):
        return httpx.Response(422, json={"detail": [{"msg": "bad"}]})

    client = Client(make_settings(tmp_path), transport=httpx.MockTransport(handler))
    with pytest.raises(ValidationError):
        client.whoami()
