"""Smoke test de la pestaña de autogeneración: construye la vista offscreen.

La lógica de generación (run_autogen) está cubierta en test_autogen.py; aquí solo
verificamos que la vista Qt se construye sin errores y que el botón "Generar"
arranca deshabilitado (no hay JSON cargado todavía). Se ejecuta en un subproceso
para aislar cualquier fallo de Qt del proceso de pytest.
"""
from __future__ import annotations

import subprocess
import sys
import textwrap

_SCRIPT = textwrap.dedent(
    """
    import os
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

    from pathlib import Path
    from PySide6.QtWidgets import QApplication, QPushButton, QTableWidget

    from murray3d.config import Settings
    from murray3d.gui.autogen_view import build_autogen_view

    app = QApplication([])
    settings = Settings(
        base_url="https://x/api", api_key="", cache_dir=Path("/tmp/c"),
        shots_dir=Path("/tmp/s"), known_categories=["both"],
        autogen_dir=Path("/tmp/autogen"),
    )
    view = build_autogen_view(settings)

    tables = view.findChildren(QTableWidget)
    assert tables and tables[0].columnCount() == 5, "tabla de trabajos ausente"

    btns = [b for b in view.findChildren(QPushButton) if b.text() == "Generar"]
    assert btns, "botón Generar ausente"
    assert not btns[0].isEnabled(), "Generar debería estar deshabilitado sin JSON"

    print("OK")
    """
)


def test_autogen_view_builds():
    proc = subprocess.run([sys.executable, "-c", _SCRIPT],
                          capture_output=True, text=True, timeout=90)
    assert proc.returncode == 0, (
        f"rc={proc.returncode}\nSTDOUT: {proc.stdout}\nSTDERR: {proc.stderr}"
    )
    assert "OK" in proc.stdout, proc.stdout
