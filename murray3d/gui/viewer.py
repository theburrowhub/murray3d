"""Visor 3D embebido (QWebEngineView + model-viewer).

Se usa un patrón factory `build_viewer_widget()` que importa PySide6 de forma
perezosa y devuelve la clase `ModelViewer` (subclase de QWidget). Definir la
clase a nivel de módulo obligaría a importar QWidget al cargar el módulo y
rompería los tests headless; el factory difiere ese import. Instanciar la clase
devuelta requiere un QApplication en marcha.

El visor se sirve por HTTP local (127.0.0.1), no por `file://`: es el mismo
transporte que `render.py` tiene probado de extremo a extremo (model-viewer
carga y renderiza glb reales), y evita restricciones de origen `file://` al
hacer fetch del glb.
"""
from __future__ import annotations

import functools
import http.server
import shutil
import tempfile
import threading
from pathlib import Path

from ..convert import ensure_glb

ASSETS_DIR = Path(__file__).resolve().parent / "assets"
VIEWER_HTML = ASSETS_DIR / "viewer.html"
_ASSET_FILES = ("viewer.html", "model-viewer.min.js")


class _QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args):  # silenciar el log de acceso
        pass


class _ViewerServer:
    """Servidor HTTP local que sirve viewer.html, model-viewer.min.js y los glb.

    Vive mientras viva el widget (se para en aboutToQuit del QApplication).
    """

    def __init__(self):
        self._dir = Path(tempfile.mkdtemp(prefix="murray3d_viewer_"))
        for name in _ASSET_FILES:
            self._stage(ASSETS_DIR / name, self._dir / name)
        handler = functools.partial(_QuietHandler, directory=str(self._dir))
        self._httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
        self.port = self._httpd.server_address[1]
        self._thread = threading.Thread(target=self._httpd.serve_forever, daemon=True)
        self._thread.start()
        self._counter = 0

    @staticmethod
    def _stage(src: Path, dst: Path) -> None:
        try:
            if dst.is_symlink() or dst.exists():
                dst.unlink()
            dst.symlink_to(src)
        except OSError:
            shutil.copy2(src, dst)

    def stage_model(self, glb: Path) -> str:
        self._counter += 1
        name = f"model_{self._counter}.glb"
        self._stage(Path(glb).resolve(), self._dir / name)
        return f"http://127.0.0.1:{self.port}/{name}"

    def viewer_url(self) -> str:
        return f"http://127.0.0.1:{self.port}/viewer.html"

    def stop(self) -> None:
        try:
            self._httpd.shutdown()
            self._httpd.server_close()
            self._thread.join(timeout=2)
        except Exception:  # noqa: BLE001
            pass
        shutil.rmtree(self._dir, ignore_errors=True)


def _qt():
    from PySide6.QtWebEngineWidgets import QWebEngineView
    from PySide6.QtWidgets import QVBoxLayout, QWidget
    return QWidget, QVBoxLayout, QWebEngineView


def build_viewer_widget():
    QWidget, QVBoxLayout, QWebEngineView = _qt()
    from PySide6.QtCore import QUrl
    from PySide6.QtWidgets import QApplication

    class ModelViewer(QWidget):
        def __init__(self, parent=None):
            super().__init__(parent)
            self._server = _ViewerServer()
            self._web = QWebEngineView(self)
            layout = QVBoxLayout(self)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.addWidget(self._web)
            self._web.load(QUrl(self._server.viewer_url()))
            appi = QApplication.instance()
            if appi is not None:
                appi.aboutToQuit.connect(self._server.stop)

        def show_model(self, path: Path, cache_dir: Path) -> None:
            glb = ensure_glb(Path(path), cache_dir)
            url = self._server.stage_model(glb)
            self._web.page().runJavaScript(f"window.setModelSrc({url!r})")

        def clear(self) -> None:
            self._web.page().runJavaScript("window.setModelSrc('')")

    return ModelViewer
