import json

import pytest

from murray3d.agent_gen import (
    AgentGenError,
    AgentImageGenerator,
    build_gen_prompt,
)


def test_build_gen_prompt_includes_params():
    p = build_gen_prompt("un goku", "flux-dev", "3:4")
    assert "flux-dev" in p and "3:4" in p and "un goku" in p
    assert "images_generate" in p
    assert "image_urls" in p


def test_generate_parses_agent_json():
    inner = {"image_urls": ["https://cdn/a.jpg", "https://cdn/b.jpg"]}
    wrapper = {"type": "result", "result": json.dumps(inner), "is_error": False}
    captured = {}

    def fake_runner(cmd, cwd=None):
        captured["cmd"] = cmd
        return json.dumps(wrapper)

    gen = AgentImageGenerator(runner=fake_runner, claude_model="haiku",
                              mcp_config="/tmp/mcp.json")
    urls = gen.generate("un goku", model="flux-dev", aspect_ratio="3:4")
    assert urls == ["https://cdn/a.jpg", "https://cdn/b.jpg"]

    cmd = captured["cmd"]
    assert cmd[0] == "claude" and "-p" in cmd
    assert "--json-schema" in cmd
    assert "--model" in cmd and "haiku" in cmd
    assert "--mcp-config" in cmd and "/tmp/mcp.json" in cmd
    assert "--allowedTools" in cmd
    assert "mcp__magnific" in cmd


def test_generate_raises_when_no_urls():
    inner = {"image_urls": []}
    wrapper = {"result": json.dumps(inner)}
    gen = AgentImageGenerator(runner=lambda cmd, cwd=None: json.dumps(wrapper))
    with pytest.raises(AgentGenError, match="no devolvió URLs"):
        gen.generate("p", model="flux-dev", aspect_ratio="1:1")
