"""La pestaña de Autogeneración exporta los GLB a 3DBundle (con cliente falso).

Verifica que: con un `client` presente y un .glb en disco, el botón "Exportar a
3DBundle" se habilita; al pulsarlo, sube el modelo (con su imagen de miniatura)
como borrador. Sin `client`, el botón queda deshabilitado. Offscreen, subproceso.
"""
from __future__ import annotations

import subprocess
import sys
import textwrap

_SCRIPT = textwrap.dedent(
    """
    import os, json, tempfile
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from pathlib import Path
    from types import SimpleNamespace

    from PySide6.QtWidgets import (QApplication, QPushButton, QFileDialog, QMessageBox)
    from PySide6.QtCore import QTimer

    import murray3d.gui.autogen_view as av
    from murray3d.config import Settings

    SAMPLE = str(Path("examples/prompts-miniaturas.sample.json").resolve())
    OUT = Path(tempfile.mkdtemp(prefix="gui_export_"))
    job_dir = OUT / Path(SAMPLE).stem
    job_dir.mkdir(parents=True)
    name1 = "dragon_ball_goku_01_kamehameha_cargando"
    (job_dir / f"{name1}.jpg").write_bytes(b"IMG")
    (job_dir / f"{name1}.glb").write_bytes(b"GLB")
    (job_dir / "manifest.json").write_text(json.dumps({"results": [
        {"id": 1, "name": name1, "title": "Goku", "status": "ok", "ok": True,
         "path": str(job_dir / f"{name1}.jpg"),
         "glb_path": str(job_dir / f"{name1}.glb")}]}))

    class FakeClient:
        def __init__(self): self.uploaded = []; self.updated = []
        def upload_model(self, file, title, thumbnail=None, **kw):
            self.uploaded.append((str(file), title, str(thumbnail) if thumbnail else None))
            return SimpleNamespace(id=777, title=title)
        def update_model(self, mid, **f):
            self.updated.append((mid, f)); return SimpleNamespace(id=mid, title="t")

    av.ensure_magnific_auth = lambda *a, **k: None
    QFileDialog.getOpenFileName = staticmethod(lambda *a, **k: (SAMPLE, ""))
    QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.Yes)

    app = QApplication([])
    settings = Settings(base_url="x", api_key="", cache_dir=Path("/tmp/c"),
                        shots_dir=Path("/tmp/s"), known_categories=["both"],
                        autogen_dir=OUT)

    # 1) Sin client -> botón Exportar deshabilitado
    view_noc = av.build_autogen_view(settings, client=None)
    exp_noc = next(b for b in view_noc.findChildren(QPushButton) if b.text().startswith("Exportar"))
    assert not exp_noc.isEnabled(), "sin client el botón debe estar deshabilitado"

    # 2) Con client + glb en disco -> se habilita al cargar y exporta al pulsar
    fake = FakeClient()
    view = av.build_autogen_view(settings, client=fake)
    load_btn = next(b for b in view.findChildren(QPushButton) if b.text().startswith("Cargar"))
    exp_btn = next(b for b in view.findChildren(QPushButton) if b.text().startswith("Exportar"))
    load_btn.click()
    assert exp_btn.isEnabled(), "con client y .glb el botón debe habilitarse"
    exp_btn.click()

    done = {"ok": False}
    def check():
        if fake.uploaded:
            done["ok"] = True; app.quit()
    t = QTimer(); t.timeout.connect(check); t.start(50)
    QTimer.singleShot(20000, app.quit)
    app.exec()

    assert done["ok"], "no subió nada a 3DBundle"
    assert fake.uploaded[0][0].endswith(name1 + ".glb")
    assert fake.uploaded[0][2].endswith(name1 + ".jpg")   # miniatura
    assert fake.updated == [(777, {"published": False})]  # borrador
    print("OK export")
    """
)


def test_gui_export_to_3dbundle():
    proc = subprocess.run([sys.executable, "-c", _SCRIPT],
                          capture_output=True, text=True, timeout=120)
    assert proc.returncode == 0, (
        f"rc={proc.returncode}\nSTDOUT: {proc.stdout}\nSTDERR: {proc.stderr}"
    )
    assert "OK export" in proc.stdout, proc.stdout
