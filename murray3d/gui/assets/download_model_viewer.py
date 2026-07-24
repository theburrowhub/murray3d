"""Descarga model-viewer.min.js (self-contained) al directorio de assets.

Ejecutar una sola vez: `python -m murray3d.gui.assets.download_model_viewer`
"""
from __future__ import annotations

from pathlib import Path

import httpx

URL = "https://unpkg.com/@google/model-viewer@3.5.0/dist/model-viewer.min.js"
DEST = Path(__file__).resolve().parent / "model-viewer.min.js"


def main() -> None:
    print(f"Descargando {URL} ...")
    r = httpx.get(URL, follow_redirects=True, timeout=60)
    r.raise_for_status()
    DEST.write_bytes(r.content)
    print(f"Guardado en {DEST} ({DEST.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
