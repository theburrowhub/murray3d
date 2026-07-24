from pathlib import Path
from unittest.mock import MagicMock

from murray3d.batch import batch_ai_publish, batch_upload, collect_files
from murray3d.config import Settings
from murray3d.models import GeneratedMeta, Model3D


def _settings(tmp_path):
    return Settings(base_url="https://x/3dbundle/api", api_key="k",
                    cache_dir=tmp_path / "c", shots_dir=tmp_path / "s",
                    known_categories=["both"])


def test_collect_files_expands_dirs_and_filters(tmp_path):
    (tmp_path / "a.glb").write_bytes(b"x")
    (tmp_path / "b.stl").write_bytes(b"x")
    (tmp_path / "notes.txt").write_text("no")
    sub = tmp_path / "sub"; sub.mkdir()
    (sub / "c.obj").write_bytes(b"x")
    files = collect_files([tmp_path])
    names = sorted(f.name for f in files)
    assert names == ["a.glb", "b.stl", "c.obj"]  # .txt excluido, subcarpeta incluida


def test_collect_files_dedupes(tmp_path):
    f = tmp_path / "a.glb"; f.write_bytes(b"x")
    files = collect_files([f, tmp_path, f])  # duplicado explícito + vía carpeta
    assert len(files) == 1


def test_batch_upload_uploads_each_as_draft_and_continues_on_error(tmp_path):
    client = MagicMock()
    good = tmp_path / "ok.glb"; good.write_bytes(b"x")
    bad = tmp_path / "bad.glb"; bad.write_bytes(b"x")

    def upload(file, title):
        if Path(file).name == "bad.glb":
            raise RuntimeError("boom")
        return Model3D(id=1, title=title, published=True)

    client.upload_model.side_effect = upload
    client.update_model.return_value = Model3D(id=1, title="ok", published=False)

    seen = []
    results = batch_upload(client, [good, bad],
                           on_progress=lambda i, t, n, ph: seen.append((i, n)))
    assert results[0]["ok"] is True and results[0]["id"] == 1
    assert results[1]["ok"] is False and "boom" in results[1]["error"]
    # el borrador se fuerza con update_model(published=False)
    assert client.update_model.call_args.kwargs["published"] is False
    assert len(seen) == 2  # progreso por cada fichero


def test_batch_ai_publish_sequential_cleanup_and_continue(tmp_path):
    settings = _settings(tmp_path)
    client = MagicMock()
    # dejar dirs de trabajo para comprobar que se limpian
    for mid in (1, 2):
        d = settings.shots_dir / str(mid); d.mkdir(parents=True)
        (d / "model.glb").write_bytes(b"x")

    def prepare(c, s, mid):
        if mid == 2:
            raise RuntimeError("fallo render")
        return GeneratedMeta(title="T", description="D", tags=[], category="both"), []

    commit = MagicMock(return_value=Model3D(id=1, title="T", published=True))
    results = batch_ai_publish(client, settings, [1, 2],
                               prepare_fn=prepare, commit_fn=commit)
    assert results[0]["ok"] is True
    assert results[1]["ok"] is False and "fallo render" in results[1]["error"]
    # temporales limpiados en ambos casos (éxito y error)
    assert not (settings.shots_dir / "1").exists()
    assert not (settings.shots_dir / "2").exists()
