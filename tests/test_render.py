from pathlib import Path

import pytest
import trimesh

from murray3d.render import render_screenshots


@pytest.mark.integration
def test_render_produces_pngs(tmp_path):
    glb = tmp_path / "box.glb"
    trimesh.creation.box(extents=(1, 1, 1)).export(glb)
    shots = render_screenshots(glb, tmp_path / "out", tmp_path / "cache")
    assert len(shots) == 6
    for s in shots:
        assert s.exists() and s.stat().st_size > 1000
