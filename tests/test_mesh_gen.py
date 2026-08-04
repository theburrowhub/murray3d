import json

import pytest

from murray3d.mesh_gen import (
    AgentMeshGenerator,
    MeshGenError,
    build_mesh_prompt,
)


def test_build_mesh_prompt_includes_image_and_format():
    p = build_mesh_prompt("https://cdn/x.jpg", "glb")
    assert "https://cdn/x.jpg" in p
    assert "GLB" in p
    assert "models3d_generate" in p
    assert "model_urls" in p


def test_generate_from_image_parses_agent_json():
    inner = {"model_urls": ["https://cdn/model.glb"]}
    wrapper = {"type": "result", "result": json.dumps(inner), "is_error": False}
    captured = {}

    def fake_runner(cmd, cwd=None):
        captured["cmd"] = cmd
        return json.dumps(wrapper)

    gen = AgentMeshGenerator(runner=fake_runner, claude_model="sonnet",
                             mcp_config="examples/magnific-mcp.json")
    urls = gen.generate_from_image("https://cdn/x.jpg")
    assert urls == ["https://cdn/model.glb"]

    cmd = captured["cmd"]
    assert cmd[0] == "claude" and "-p" in cmd
    assert "--json-schema" in cmd
    assert "--allowedTools" in cmd
    assert "mcp__magnific" in cmd
    assert "--mcp-config" in cmd and "examples/magnific-mcp.json" in cmd
    assert "--model" in cmd and "sonnet" in cmd


def test_generate_from_image_raises_without_urls():
    wrapper = {"result": json.dumps({"model_urls": []})}
    gen = AgentMeshGenerator(runner=lambda cmd, cwd=None: json.dumps(wrapper))
    with pytest.raises(MeshGenError, match="no devolvió URLs"):
        gen.generate_from_image("https://cdn/x.jpg")


def test_generate_from_image_requires_image_url():
    gen = AgentMeshGenerator(runner=lambda cmd, cwd=None: "{}")
    with pytest.raises(MeshGenError, match="Falta la URL"):
        gen.generate_from_image("")
