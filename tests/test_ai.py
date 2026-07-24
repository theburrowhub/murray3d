import json
import subprocess
from pathlib import Path

import pytest

from murray3d.ai import AiError, build_prompt, default_runner, generate_metadata


def test_build_prompt_mentions_shots_and_categories(tmp_path):
    shots = [tmp_path / "shot_00.png", tmp_path / "shot_01.png"]
    prompt = build_prompt(shots, ["figures", "both"])
    assert "shot_00.png" in prompt
    assert "figures" in prompt and "both" in prompt


def test_generate_metadata_parses_claude_wrapper(tmp_path):
    inner = {"title": "Dragón alado", "description": "Una figura detallada.",
             "tags": ["dragón", "fantasía"], "category": "both",
             "price_eur": 4.5, "best_thumbnail_index": 2}
    wrapper = {"type": "result", "result": json.dumps(inner), "is_error": False}

    captured_cmd = {}

    def fake_runner(cmd, cwd):
        assert "claude" in cmd[0]
        assert "-p" in cmd
        captured_cmd["cmd"] = cmd
        return json.dumps(wrapper)

    shots = [tmp_path / f"shot_{i:02d}.png" for i in range(3)]
    for s in shots:
        s.write_bytes(b"png")
    meta = generate_metadata(shots, ["figures", "scenery", "both"], runner=fake_runner)
    assert meta.title == "Dragón alado"
    assert meta.best_thumbnail_index == 2
    assert meta.category == "both"

    cmd = captured_cmd["cmd"]
    assert "--json-schema" in cmd
    schema_value = cmd[cmd.index("--json-schema") + 1]
    parsed_schema = json.loads(schema_value)
    assert "properties" in parsed_schema
    assert not (tmp_path / "_schema.json").exists()


def test_category_forced_into_allowed_set(tmp_path):
    inner = {"title": "T", "description": "D", "tags": [], "category": "inventada",
             "best_thumbnail_index": 0}
    wrapper = {"result": json.dumps(inner)}
    shots = [tmp_path / "shot_00.png"]
    shots[0].write_bytes(b"png")
    meta = generate_metadata(shots, ["figures", "both"], runner=lambda c, w: json.dumps(wrapper))
    assert meta.category == "figures"


def test_bad_json_raises(tmp_path):
    shots = [tmp_path / "shot_00.png"]
    shots[0].write_bytes(b"png")
    with pytest.raises(AiError):
        generate_metadata(shots, ["both"], runner=lambda c, w: "no-json")


def test_default_runner_raises_aierror_with_stderr(tmp_path, monkeypatch):
    def fake_run(cmd, cwd, capture_output, text):
        return subprocess.CompletedProcess(cmd, returncode=1, stdout="", stderr="boom")

    monkeypatch.setattr(subprocess, "run", fake_run)
    with pytest.raises(AiError, match="boom"):
        default_runner(["claude"], tmp_path)
