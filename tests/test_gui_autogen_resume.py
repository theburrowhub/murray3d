"""La GUI marca como hechas las filas ya generadas en disco (reanudación visible).

Si la app se cerró a mitad de un lote, al recargar el mismo JSON con el mismo
directorio de salida, las miniaturas ya existentes deben aparecer como ✔ (y
``run_autogen`` las salta). Se conduce la vista offscreen en un subproceso.
"""
from __future__ import annotations

import subprocess
import sys
import textwrap

_SCRIPT = textwrap.dedent(
    """
    import os, tempfile
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from pathlib import Path

    from PySide6.QtWidgets import QApplication, QPushButton, QTableWidget, QFileDialog

    import murray3d.gui.autogen_view as av
    from murray3d.config import Settings

    SAMPLE = str(Path("examples/prompts-miniaturas.sample.json").resolve())
    OUT = Path(tempfile.mkdtemp(prefix="gui_resume_"))
    stem = Path(SAMPLE).stem
    job_dir = OUT / stem
    job_dir.mkdir(parents=True)
    # Simula progreso previo: la 1ª miniatura ya tiene imagen + GLB.
    name1 = "dragon_ball_goku_01_kamehameha_cargando"
    (job_dir / f"{name1}.jpg").write_bytes(b"IMG")
    (job_dir / f"{name1}.glb").write_bytes(b"GLB")

    av.ensure_magnific_auth = lambda *a, **k: None
    QFileDialog.getOpenFileName = staticmethod(lambda *a, **k: (SAMPLE, ""))

    app = QApplication([])
    settings = Settings(base_url="x", api_key="", cache_dir=Path("/tmp/c"),
                        shots_dir=Path("/tmp/s"), known_categories=["both"],
                        autogen_dir=OUT)
    view = av.build_autogen_view(settings)

    load_btn = next(b for b in view.findChildren(QPushButton) if b.text().startswith("Cargar"))
    load_btn.click()   # carga el JSON y marca lo ya existente

    table = view.findChildren(QTableWidget)[0]
    # Fila 0 = 1ª miniatura -> debe estar marcada como 3D hecho
    assert table.item(0, 4).text() == "✔ 3D", table.item(0, 4).text()
    # Fila 1 = no generada aún -> pendiente
    assert table.item(1, 4).text() == "—", table.item(1, 4).text()
    print("OK resume")
    """
)


def test_gui_marks_existing_outputs():
    proc = subprocess.run([sys.executable, "-c", _SCRIPT],
                          capture_output=True, text=True, timeout=120)
    assert proc.returncode == 0, (
        f"rc={proc.returncode}\nSTDOUT: {proc.stdout}\nSTDERR: {proc.stderr}"
    )
    assert "OK resume" in proc.stdout, proc.stdout
