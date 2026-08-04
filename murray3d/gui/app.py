from __future__ import annotations

import sys
from pathlib import Path

from ..api import ApiError, Client
from ..config import PROJECT_ROOT, ConfigError, load_settings


def _load_or_ask_settings(app):
    from PySide6.QtWidgets import QInputDialog, QMessageBox
    try:
        return load_settings()
    except ConfigError:
        key, ok = QInputDialog.getText(None, "API Key", "Introduce tu API key de 3DBundle:")
        if not ok or not key.strip():
            QMessageBox.critical(None, "Sin clave", "No se puede continuar sin API key.")
            sys.exit(1)
        (PROJECT_ROOT / "key.txt").write_text(key.strip() + "\n")
        return load_settings()


def run_gui():
    from PySide6.QtWidgets import (
        QApplication, QMainWindow, QMessageBox, QTabWidget,
    )
    from .autogen_view import build_autogen_view
    from .models_view import build_models_view
    from .packs_view import build_packs_view

    app = QApplication(sys.argv)
    app.setApplicationName("murray3d")

    settings = _load_or_ask_settings(app)
    client = Client(settings)
    try:
        profile = client.whoami()
    except ApiError as e:
        QMessageBox.critical(None, "Error de autenticación", str(e))
        sys.exit(1)

    win = QMainWindow()
    win.setWindowTitle(f"murray3d — {profile.author_name or profile.email}")
    win.resize(1200, 800)

    tabs = QTabWidget()
    tabs.addTab(build_models_view(client, settings), "Modelos")
    tabs.addTab(build_packs_view(client, settings), "Packs")
    tabs.addTab(build_autogen_view(settings), "Autogeneración")
    win.setCentralWidget(tabs)
    win.show()

    code = app.exec()
    client.close()
    sys.exit(code)
