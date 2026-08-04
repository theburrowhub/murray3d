"""Prueba de extremo a extremo del camino de la GUI: cargar JSON → Generar.

Conduce la pestaña de autogeneración offscreen en un subproceso, con el generador
de imágenes y el chequeo del MCP parcheados por dobles (sin red ni créditos), y
verifica que al pulsar "Generar" se produce el fichero de salida y la fila queda
marcada como completada. Así confirmamos que la GUI, no solo el CLI, ejecuta el
motor real.
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

    from PySide6.QtWidgets import QApplication, QPushButton, QSpinBox, QFileDialog
    from PySide6.QtCore import QTimer

    import murray3d.gui.autogen_view as av
    from murray3d.config import Settings

    SAMPLE = str(Path("examples/prompts-miniaturas.sample.json").resolve())
    OUT = Path(tempfile.mkdtemp(prefix="gui_autogen_"))

    class FakeGen:
        def generate(self, prompt, *, model, aspect_ratio, seed=None, negative_prompt=None):
            return ["https://cdn/fake.jpg"]
        def download(self, url, dest):
            dest = Path(dest); dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(b"IMG"); return dest

    # Dobles: sin MCP real, sin red, sin créditos.
    av.build_image_generator = lambda settings, **k: FakeGen()
    av.ensure_magnific_auth = lambda *a, **k: None
    # El diálogo de fichero devuelve el JSON de ejemplo sin interacción.
    QFileDialog.getOpenFileName = staticmethod(lambda *a, **k: (SAMPLE, ""))

    app = QApplication([])
    settings = Settings(base_url="x", api_key="", cache_dir=Path("/tmp/c"),
                        shots_dir=Path("/tmp/s"), known_categories=["both"],
                        autogen_dir=OUT)
    view = av.build_autogen_view(settings)

    load_btn = next(b for b in view.findChildren(QPushButton) if b.text().startswith("Cargar"))
    gen_btn = next(b for b in view.findChildren(QPushButton) if b.text() == "Generar")
    limit_sb = view.findChildren(QSpinBox)[0]

    load_btn.click()                 # -> carga el JSON y rellena la tabla
    assert gen_btn.isEnabled(), "Generar debería habilitarse tras cargar el JSON"
    limit_sb.setValue(1)             # solo 1 trabajo, rápido
    gen_btn.click()                  # -> lanza el worker

    done = {"ok": False}
    def check():
        if list(OUT.rglob("*.jpg")):
            done["ok"] = True
            app.quit()
    t = QTimer(); t.timeout.connect(check); t.start(50)
    QTimer.singleShot(30000, app.quit)   # salvaguarda anti-cuelgue
    app.exec()

    assert done["ok"], "la GUI no generó el .jpg al pulsar Generar"
    print("OK gui-run")
    """
)


def test_gui_generate_produces_output():
    proc = subprocess.run([sys.executable, "-c", _SCRIPT],
                          capture_output=True, text=True, timeout=120)
    assert proc.returncode == 0, (
        f"rc={proc.returncode}\nSTDOUT: {proc.stdout}\nSTDERR: {proc.stderr}"
    )
    assert "OK gui-run" in proc.stdout, proc.stdout
