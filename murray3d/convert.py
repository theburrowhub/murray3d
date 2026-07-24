from __future__ import annotations

from pathlib import Path

import trimesh


class ConvertError(Exception):
    pass


_PASSTHROUGH = {".glb", ".gltf"}
_CONVERTIBLE = {".obj", ".stl"}


def ensure_glb(src: Path, cache_dir: Path) -> Path:
    src = Path(src)
    ext = src.suffix.lower()
    if ext in _PASSTHROUGH:
        return src
    if ext not in _CONVERTIBLE:
        raise ConvertError(f"Extensión no soportada para render: {ext}")

    cache_dir = Path(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    st = src.stat()
    out = cache_dir / f"{src.stem}-{st.st_size}-{st.st_mtime_ns}.glb"
    if out.exists():
        return out

    try:
        mesh = trimesh.load(src, force="scene")
        mesh.export(out, file_type="glb")
    except Exception as e:  # noqa: BLE001
        raise ConvertError(f"No se pudo convertir {src.name} a glb: {e}") from e
    if not out.exists() or out.stat().st_size == 0:
        raise ConvertError(f"Conversión vacía para {src.name}")
    return out
