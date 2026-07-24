import json

from typer.testing import CliRunner

import murray3d.cli as cli
from murray3d.models import Model3D

runner = CliRunner()


def test_models_list_json(monkeypatch):
    fake = type("C", (), {})()
    fake.list_models = lambda **kw: [Model3D(id=1, title="A", published=True)]
    fake.close = lambda: None
    monkeypatch.setattr(cli, "_client", lambda: fake)

    result = runner.invoke(cli.app, ["models", "list", "--json"])
    assert result.exit_code == 0
    data = json.loads(result.stdout)
    assert data[0]["id"] == 1


def test_models_delete(monkeypatch):
    calls = {}
    fake = type("C", (), {})()
    fake.delete_model = lambda mid: calls.setdefault("del", mid)
    fake.close = lambda: None
    monkeypatch.setattr(cli, "_client", lambda: fake)

    result = runner.invoke(cli.app, ["models", "delete", "5", "--yes"])
    assert result.exit_code == 0
    assert calls["del"] == 5


def test_whoami_error_exit_code(monkeypatch):
    from murray3d.api import AuthError

    def boom():
        raise AuthError(401, "sin clave")

    fake = type("C", (), {})()
    fake.whoami = boom
    fake.close = lambda: None
    monkeypatch.setattr(cli, "_client", lambda: fake)

    result = runner.invoke(cli.app, ["whoami"])
    assert result.exit_code != 0
    assert "sin clave" in result.stdout


def test_whoami_config_error_exit_code(monkeypatch):
    from murray3d.config import ConfigError

    def boom_client():
        raise ConfigError("no api key")

    monkeypatch.setattr(cli, "_client", boom_client)

    result = runner.invoke(cli.app, ["whoami"])
    assert result.exit_code != 0
    assert "no api key" in result.stdout


def test_ai_generate_surfaces_aierror_as_clean_exit(monkeypatch):
    from murray3d.ai import AiError

    def boom(*args, **kwargs):
        raise AiError("claude binario no encontrado")

    monkeypatch.setattr("murray3d.publish.prepare_publish", boom)

    fake = type("C", (), {})()
    fake.settings = object()
    fake.close = lambda: None
    monkeypatch.setattr(cli, "_client", lambda: fake)

    result = runner.invoke(cli.app, ["ai-generate", "5"])
    assert result.exit_code != 0
    assert "claude binario no encontrado" in result.stdout
    assert "Traceback" not in result.stdout
