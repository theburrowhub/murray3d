from __future__ import annotations

import base64
import http.server
import shutil
import tempfile
import threading
from functools import partial
from pathlib import Path
from urllib.parse import quote

from .convert import ensure_glb

RenderError = type("RenderError", (Exception,), {})

ASSETS = Path(__file__).resolve().parent / "gui" / "assets"
VIEWER_HTML = ASSETS / "viewer.html"

# (theta_deg, phi_deg, radius)
DEFAULT_ANGLES: list[tuple[float, float, str]] = [
    (0, 75, "auto"),      # frente
    (45, 70, "auto"),     # 3/4 derecha
    (90, 80, "auto"),     # lateral derecho
    (-45, 70, "auto"),    # 3/4 izquierda
    (180, 80, "auto"),    # atrás
    (25, 25, "auto"),     # picado
]


class _LocalAssetServer:
    """Servidor HTTP local minimo, solo-lectura, para servir archivos desde
    un directorio raiz acotado durante la vida del render.

    Chromium bloquea la carga de ``<script type="module">`` (usado por
    model-viewer.min.js) cuando la pagina se abre via ``file://``: los
    module scripts solo se permiten para los esquemas http/https/data/chrome
    (CORS los trata como origen "null" bajo file://). Sirviendo viewer.html,
    el propio model-viewer.min.js y el .glb desde ``http://127.0.0.1`` con el
    mismo origen se evita esa restriccion sin tocar el HTML de Task 7.

    ``root`` debe ser un directorio de staging que contenga UNICAMENTE los
    archivos necesarios para ese render (nunca la raiz del filesystem):
    exponer mas que eso daria lectura no autenticada de disco a cualquier
    proceso que pueda alcanzar 127.0.0.1 mientras el servidor esta vivo.
    """

    def __init__(self, root: Path):
        # No usamos Path.resolve() aqui: los archivos servidos son symlinks
        # (ver _stage) y resolverlos seguiria el symlink hasta su destino
        # real fuera del staging dir, rompiendo relative_to() en url_for.
        self._root = Path(root)
        handler = partial(http.server.SimpleHTTPRequestHandler, directory=str(self._root))
        self._httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
        self._thread = threading.Thread(target=self._httpd.serve_forever, daemon=True)

    def url_for(self, path: Path) -> str:
        port = self._httpd.server_address[1]
        rel = Path(path).relative_to(self._root)
        return f"http://127.0.0.1:{port}/{quote(rel.as_posix())}"

    def __enter__(self) -> "_LocalAssetServer":
        self._thread.start()
        return self

    def __exit__(self, *exc_info) -> None:
        self._httpd.shutdown()
        self._httpd.server_close()
        self._thread.join()


def _stage(src: Path, dest: Path) -> None:
    """Coloca ``src`` en ``dest`` dentro del directorio de staging.

    Prefiere un symlink (evita copiar el .glb, que puede ser grande); si el
    filesystem no soporta symlinks cae a una copia.
    """
    try:
        dest.symlink_to(src.resolve())
    except OSError:
        shutil.copy2(src, dest)


def render_screenshots(model_path: Path, out_dir: Path, cache_dir: Path,
                        angles=None) -> list[Path]:
    from playwright.sync_api import sync_playwright  # import perezoso

    angles = angles or DEFAULT_ANGLES
    model_path = Path(model_path)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    glb = ensure_glb(model_path, cache_dir)

    results: list[Path] = []
    try:
        with tempfile.TemporaryDirectory(prefix="murray3d_render_") as staging_dir:
            staging_root = Path(staging_dir)
            staged_assets = staging_root / "assets"
            staged_assets.mkdir()
            _stage(ASSETS / "viewer.html", staged_assets / "viewer.html")
            _stage(ASSETS / "model-viewer.min.js", staged_assets / "model-viewer.min.js")
            staged_glb = staging_root / glb.name
            _stage(glb, staged_glb)

            with _LocalAssetServer(staging_root) as server:
                file_url = (
                    server.url_for(staged_assets / "viewer.html")
                    + "?src="
                    + server.url_for(staged_glb)
                )
                with sync_playwright() as p:
                    browser = p.chromium.launch(args=["--no-sandbox"])
                    page = browser.new_page(viewport={"width": 1024, "height": 1024},
                                            device_scale_factor=2)
                    page.goto(file_url, wait_until="load")
                    page.wait_for_function("window.modelReady !== undefined")
                    page.evaluate(
                        "() => Promise.race(["
                        "window.modelReady,"
                        "new Promise((_, rej) => setTimeout("
                        "() => rej(new Error('modelReady no resolvio a tiempo')), 20000))"
                        "])"
                    )
                    page.wait_for_timeout(500)
                    for i, (theta, phi, radius) in enumerate(angles):
                        data_url = page.evaluate(
                            "([t,p,r]) => window.captureOrbit(t,p,r)", [theta, phi, radius]
                        )
                        header, b64 = data_url.split(",", 1)
                        dest = out_dir / f"shot_{i:02d}.png"
                        dest.write_bytes(base64.b64decode(b64))
                        results.append(dest)
                    browser.close()
    except Exception as e:  # noqa: BLE001
        raise RenderError(f"Fallo al renderizar {model_path.name}: {e}") from e
    if not results:
        raise RenderError("No se generó ningún pantallazo")
    return results
