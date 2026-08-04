"""Descarga de URLs públicas a disco por streaming (imágenes y modelos 3D).

Utilidad compartida por los generadores por agente; sin dependencia de ninguna
API concreta.
"""
from __future__ import annotations

from pathlib import Path

import httpx


class DownloadError(Exception):
    pass


def download_url(url: str, dest: Path) -> Path:
    """Descarga ``url`` a ``dest`` por streaming (sin auth). Crea el directorio."""
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    with httpx.stream("GET", url, timeout=120.0, follow_redirects=True) as r:
        if r.status_code >= 400:
            r.read()
            raise DownloadError(f"[{r.status_code}] al descargar {url}")
        with open(dest, "wb") as f:
            for chunk in r.iter_bytes(chunk_size=1024 * 256):
                f.write(chunk)
    return dest
