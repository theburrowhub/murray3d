import json
from pathlib import Path
from types import SimpleNamespace

from murray3d.autogen import (
    export_to_3dbundle,
    exportable_results,
    load_manifest,
)


class FakeClient:
    def __init__(self, fail_titles=None):
        self.uploaded = []
        self.updated = []
        self.fail_titles = fail_titles or set()
        self._n = 0

    def upload_model(self, file, title, thumbnail=None, **kw):
        if title in self.fail_titles:
            raise RuntimeError("upload boom")
        self._n += 1
        self.uploaded.append({"file": str(file), "title": title,
                              "thumb": str(thumbnail) if thumbnail else None})
        return SimpleNamespace(id=100 + self._n, title=title)

    def update_model(self, model_id, **fields):
        self.updated.append((model_id, fields))
        return SimpleNamespace(id=model_id, title="t")


def _mk(tmp_path, name, with_glb=True, with_jpg=True, title="Título"):
    r = {"id": 1, "name": name, "title": title, "status": "ok", "ok": True}
    if with_jpg:
        p = tmp_path / f"{name}.jpg"; p.write_bytes(b"IMG"); r["path"] = str(p)
    if with_glb:
        g = tmp_path / f"{name}.glb"; g.write_bytes(b"GLB"); r["glb_path"] = str(g)
    return r


def test_exportable_filters_by_glb(tmp_path):
    a = _mk(tmp_path, "a")
    b = _mk(tmp_path, "b", with_glb=False)  # solo imagen -> no exportable
    assert [r["name"] for r in exportable_results([a, b])] == ["a"]


def test_export_uploads_as_draft_with_thumbnail(tmp_path):
    r = _mk(tmp_path, "goku_01", title="Goku")
    c = FakeClient()
    out = export_to_3dbundle(c, [r])
    assert out[0]["ok"] and out[0]["model_id"] == 101
    # subió el glb con la jpg como miniatura
    assert c.uploaded[0]["title"] == "Goku"
    assert c.uploaded[0]["file"].endswith("goku_01.glb")
    assert c.uploaded[0]["thumb"].endswith("goku_01.jpg")
    # lo dejó como borrador
    assert c.updated == [(101, {"published": False})]


def test_export_published_skips_unpublish(tmp_path):
    r = _mk(tmp_path, "x")
    c = FakeClient()
    export_to_3dbundle(c, [r], as_draft=False)
    assert c.updated == []  # no lo marca borrador


def test_export_continues_on_error(tmp_path):
    r1 = _mk(tmp_path, "ok1", title="A")
    r2 = _mk(tmp_path, "bad", title="B")
    c = FakeClient(fail_titles={"B"})
    out = export_to_3dbundle(c, [r1, r2])
    assert out[0]["ok"] and not out[1]["ok"]
    assert "boom" in out[1]["error"]


def test_load_manifest(tmp_path):
    (tmp_path / "manifest.json").write_text(
        json.dumps({"results": [{"id": 1, "name": "a"}]}), encoding="utf-8")
    assert load_manifest(tmp_path) == [{"id": 1, "name": "a"}]
    assert load_manifest(tmp_path / "nope") == []
