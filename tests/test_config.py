import os
from pathlib import Path

import pytest

from murray3d.config import ConfigError, load_settings


def test_load_settings_from_env(tmp_path, monkeypatch):
    monkeypatch.setenv("MURRAY_API_KEY", "env-key-123")
    monkeypatch.setenv("HOME", str(tmp_path))
    s = load_settings(key_path=tmp_path / "missing.txt")
    assert s.api_key == "env-key-123"
    assert s.base_url == "https://murrayslab.com/3dbundle/api"
    assert s.cache_dir == tmp_path / ".murray3d" / "cache"
    assert s.shots_dir == tmp_path / ".murray3d" / "shots"
    assert s.cache_dir.is_dir()
    assert "both" in s.known_categories


def test_load_settings_from_key_file(tmp_path, monkeypatch):
    monkeypatch.delenv("MURRAY_API_KEY", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))
    key_file = tmp_path / "key.txt"
    key_file.write_text("file-key-abc\n\n")
    s = load_settings(key_path=key_file)
    assert s.api_key == "file-key-abc"


def test_env_overrides_file(tmp_path, monkeypatch):
    monkeypatch.setenv("MURRAY_API_KEY", "env-wins")
    monkeypatch.setenv("HOME", str(tmp_path))
    key_file = tmp_path / "key.txt"
    key_file.write_text("file-key\n")
    s = load_settings(key_path=key_file)
    assert s.api_key == "env-wins"


def test_missing_key_raises(tmp_path, monkeypatch):
    monkeypatch.delenv("MURRAY_API_KEY", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))
    with pytest.raises(ConfigError):
        load_settings(key_path=tmp_path / "nope.txt")


def test_load_settings_from_user_config(tmp_path, monkeypatch):
    monkeypatch.delenv("MURRAY_API_KEY", raising=False)
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))
    cfg = tmp_path / ".config" / "murray3d"
    cfg.mkdir(parents=True)
    (cfg / "key.txt").write_text("user-cfg-key\n")
    s = load_settings()  # sin env ni key_path -> lee del config de usuario
    assert s.api_key == "user-cfg-key"


def test_xdg_config_home_respected(tmp_path, monkeypatch):
    monkeypatch.delenv("MURRAY_API_KEY", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    cfg = tmp_path / "xdg" / "murray3d"
    cfg.mkdir(parents=True)
    (cfg / "key.txt").write_text("xdg-key\n")
    s = load_settings()
    assert s.api_key == "xdg-key"
