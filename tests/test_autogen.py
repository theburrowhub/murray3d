import json
from pathlib import Path

from murray3d.autogen import run_autogen, summarize
from murray3d.prompts import parse_prompt_doc

DOC = {
    "figures": [
        {"group": "Dragon Ball", "character": "Goku", "prompts": [
            {"id": 1, "variant": 1, "title": "A", "prompt": "p1"},
            {"id": 2, "variant": 2, "title": "B", "prompt": "p2"},
        ]},
        {"group": "Star Wars", "character": "Vader", "prompts": [
            {"id": 3, "variant": 1, "title": "C", "prompt": "p3"},
        ]},
    ],
    "automation_config": {
        "image_generation": {"recommended_model": "flux-dev", "aspect_ratio": "3:4"},
        "naming_convention": {"pattern": "{group}_{character}_{variant:02d}_{title_snake_case}"},
    },
}


class FakeGen:
    def __init__(self, fail_on=None):
        self.calls = []
        self.fail_on = fail_on or set()

    def generate(self, prompt, *, model, aspect_ratio, seed=None, negative_prompt=None):
        self.calls.append({"prompt": prompt, "model": model, "aspect": aspect_ratio,
                           "seed": seed})
        if prompt in self.fail_on:
            raise RuntimeError("boom")
        return [f"https://cdn/{prompt}.jpg"]

    def download(self, url, dest):
        dest = Path(dest)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(b"IMG:" + url.encode())
        return dest


def test_run_autogen_generates_all_and_manifest(tmp_path):
    doc = parse_prompt_doc(DOC)
    gen = FakeGen()
    results = run_autogen(doc, gen, tmp_path)
    s = summarize(results)
    assert s == {"ok": 3, "skipped": 0, "errors": 0, "total": 3}
    assert (tmp_path / "dragon_ball_goku_01_a.jpg").read_bytes().startswith(b"IMG:")
    manifest = json.loads((tmp_path / "manifest.json").read_text())
    assert manifest["ok"] == 3 and manifest["total"] == 3
    # model/aspect heredados del doc
    assert all(c["model"] == "flux-dev" and c["aspect"] == "3:4" for c in gen.calls)


def test_run_autogen_resumes_existing(tmp_path):
    doc = parse_prompt_doc(DOC)
    # pre-crear la salida del primer trabajo
    (tmp_path / "dragon_ball_goku_01_a.jpg").write_bytes(b"already")
    gen = FakeGen()
    results = run_autogen(doc, gen, tmp_path, resume=True)
    s = summarize(results)
    assert s["skipped"] == 1 and s["ok"] == 2
    assert len(gen.calls) == 2  # el saltado no llama al generador


def test_run_autogen_continues_on_error(tmp_path):
    doc = parse_prompt_doc(DOC)
    gen = FakeGen(fail_on={"p2"})
    results = run_autogen(doc, gen, tmp_path)
    s = summarize(results)
    assert s["errors"] == 1 and s["ok"] == 2
    err = [r for r in results if r["status"] == "error"][0]
    assert err["id"] == 2 and "boom" in err["error"]


def test_run_autogen_limit(tmp_path):
    doc = parse_prompt_doc(DOC)
    gen = FakeGen()
    results = run_autogen(doc, gen, tmp_path, limit=1)
    assert len(results) == 1


def test_seed_is_reproducible_per_job(tmp_path):
    doc = parse_prompt_doc(DOC)
    gen = FakeGen()
    run_autogen(doc, gen, tmp_path, seed=100)
    seeds = [c["seed"] for c in gen.calls]
    assert seeds == [101, 102, 103]  # base 100 + id


class FakeMesh:
    def __init__(self, fail_on=None):
        self.calls = []
        self.fail_on = fail_on or set()

    def generate_from_image(self, image_url):
        self.calls.append(image_url)
        if image_url in self.fail_on:
            raise RuntimeError("3d-boom")
        return [image_url.replace(".jpg", ".glb")]

    def download(self, url, dest):
        dest = Path(dest); dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(b"GLB:" + url.encode()); return dest


def test_make_3d_generates_glb_and_records_manifest(tmp_path):
    doc = parse_prompt_doc(DOC)
    gen, mesh = FakeGen(), FakeMesh()
    results = run_autogen(doc, gen, tmp_path, make_3d=True, mesh_generator=mesh, limit=1)
    assert summarize(results)["ok"] == 1
    glb = tmp_path / "dragon_ball_goku_01_a.glb"
    assert glb.read_bytes().startswith(b"GLB:")
    # el mesh recibe la URL de imagen del generador
    assert mesh.calls == ["https://cdn/p1.jpg"]
    rec = json.loads((tmp_path / "manifest.json").read_text())["results"][0]
    assert rec["glb_path"].endswith(".glb") and rec["glb_url"].endswith(".glb")


def test_make_3d_requires_mesh_generator(tmp_path):
    doc = parse_prompt_doc(DOC)
    import pytest
    with pytest.raises(ValueError, match="mesh_generator"):
        run_autogen(doc, FakeGen(), tmp_path, make_3d=True)


def test_make_3d_error_keeps_image(tmp_path):
    doc = parse_prompt_doc(DOC)
    gen = FakeGen()
    mesh = FakeMesh(fail_on={"https://cdn/p1.jpg"})
    results = run_autogen(doc, gen, tmp_path, make_3d=True, mesh_generator=mesh, limit=1)
    assert summarize(results)["errors"] == 1
    # la imagen se descargó aunque el 3D fallara
    assert (tmp_path / "dragon_ball_goku_01_a.jpg").exists()
    assert "3d-boom" in results[0]["error"]
    assert results[0]["path"].endswith(".jpg")


def test_make_3d_resume_reuses_image_url_no_image_regen(tmp_path):
    doc = parse_prompt_doc(DOC)
    # Primera pasada: imagen ok, pero el 3D falla -> glb no existe
    gen1 = FakeGen()
    mesh_fail = FakeMesh(fail_on={"https://cdn/p1.jpg"})
    run_autogen(doc, gen1, tmp_path, make_3d=True, mesh_generator=mesh_fail, limit=1)
    assert not (tmp_path / "dragon_ball_goku_01_a.glb").exists()
    # Segunda pasada: reintenta. La imagen ya está y su URL está en el manifest,
    # así que NO se vuelve a generar la imagen; solo se hace el 3D.
    gen2 = FakeGen()
    mesh_ok = FakeMesh()
    results = run_autogen(doc, gen2, tmp_path, make_3d=True, mesh_generator=mesh_ok, limit=1)
    assert summarize(results)["ok"] == 1
    assert gen2.calls == []  # imagen NO regenerada (URL reutilizada del manifest)
    assert mesh_ok.calls == ["https://cdn/p1.jpg"]
    assert (tmp_path / "dragon_ball_goku_01_a.glb").exists()
