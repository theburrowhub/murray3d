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
