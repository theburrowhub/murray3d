from pathlib import Path

import numpy as np
import pytest
import trimesh

from murray3d.convert import ConvertError, ensure_glb


def _write_stl(path: Path):
    mesh = trimesh.creation.box(extents=(1, 1, 1))
    mesh.export(path)


def test_glb_passthrough(tmp_path):
    glb = tmp_path / "a.glb"
    glb.write_bytes(b"glTF-fake")
    assert ensure_glb(glb, tmp_path / "cache") == glb


def test_stl_converted_to_glb(tmp_path):
    stl = tmp_path / "box.stl"
    _write_stl(stl)
    cache = tmp_path / "cache"
    out = ensure_glb(stl, cache)
    assert out.suffix == ".glb"
    assert out.parent == cache
    assert out.stat().st_size > 0
    scene = trimesh.load(out)
    assert scene is not None


def test_conversion_is_cached(tmp_path):
    stl = tmp_path / "box.stl"
    _write_stl(stl)
    cache = tmp_path / "cache"
    out1 = ensure_glb(stl, cache)
    mtime1 = out1.stat().st_mtime_ns
    out2 = ensure_glb(stl, cache)
    assert out2 == out1
    assert out2.stat().st_mtime_ns == mtime1


def test_unsupported_extension_raises(tmp_path):
    bad = tmp_path / "x.txt"
    bad.write_text("hi")
    with pytest.raises(ConvertError):
        ensure_glb(bad, tmp_path / "cache")
