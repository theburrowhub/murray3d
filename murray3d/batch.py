"""Operaciones por lotes: subir muchos modelos y publicar con IA en bloque.

Diseñado para lotes grandes (>1GB en total): se procesa **de uno en uno** y las
transferencias van por streaming (ver api.py), de modo que nunca se mantienen
varios ficheros grandes en memoria a la vez. Tras publicar cada modelo se
limpian sus temporales en disco. Un error en un elemento no aborta el lote:
se registra y se continúa.
"""
from __future__ import annotations

import shutil
import time
from pathlib import Path

SUPPORTED_EXT = {".glb", ".obj", ".stl"}


def collect_files(paths) -> list[Path]:
    """Expande rutas (ficheros o directorios) a una lista de modelos soportados.

    Los directorios se recorren recursivamente. Se eliminan duplicados
    preservando el orden.
    """
    out: list[Path] = []
    for p in paths:
        p = Path(p)
        if p.is_dir():
            for f in sorted(p.rglob("*")):
                if f.is_file() and f.suffix.lower() in SUPPORTED_EXT:
                    out.append(f)
        elif p.is_file() and p.suffix.lower() in SUPPORTED_EXT:
            out.append(p)
    seen = set()
    result: list[Path] = []
    for f in out:
        rp = f.resolve()
        if rp not in seen:
            seen.add(rp)
            result.append(f)
    return result


def batch_upload(client, files, on_progress=None, as_draft=True) -> list[dict]:
    """Sube cada fichero (secuencialmente) como borrador. Continúa ante errores.

    Devuelve una lista de dicts: {file, id, ok} o {file, ok:False, error}.
    """
    results: list[dict] = []
    total = len(files)
    for i, f in enumerate(files):
        f = Path(f)
        if on_progress:
            on_progress(i, total, str(f.name), "subiendo")
        try:
            m = client.upload_model(f, title=f.stem)
            if as_draft:
                # La API publica al subir; lo dejamos como borrador.
                m = client.update_model(m.id, published=False)
            results.append({"file": str(f), "id": m.id, "title": m.title, "ok": True})
        except Exception as e:  # noqa: BLE001
            results.append({"file": str(f), "ok": False, "error": str(e)})
    return results


def _cleanup_workdir(settings, model_id) -> None:
    """Borra el dir de trabajo del modelo (glb descargado + pantallazos).

    Reintenta por si un handle transitorio (p. ej. tras el render) impide borrar
    el .glb al primer intento; importante en lotes grandes para no acumular disco.
    """
    d = settings.shots_dir / str(model_id)
    for _ in range(4):
        shutil.rmtree(d, ignore_errors=True)
        if not d.exists():
            return
        time.sleep(0.2)


def batch_ai_publish(client, settings, model_ids, on_progress=None, cleanup=True,
                     prepare_fn=None, commit_fn=None) -> list[dict]:
    """Ejecuta el flujo completo de "Publicar con IA" para cada modelo del lote.

    Secuencial. Tras cada modelo borra sus temporales (glb descargado +
    pantallazos) para no acumular disco en lotes grandes. Continúa ante errores.
    """
    from .publish import commit_publish, prepare_publish
    prepare_fn = prepare_fn or prepare_publish
    commit_fn = commit_fn or commit_publish

    results: list[dict] = []
    total = len(model_ids)
    for i, mid in enumerate(model_ids):
        if on_progress:
            on_progress(i, total, mid, "publicando")
        try:
            meta, shots = prepare_fn(client, settings, mid)
            m = commit_fn(client, mid, meta, shots)
            results.append({"id": mid, "ok": True, "title": m.title})
        except Exception as e:  # noqa: BLE001
            results.append({"id": mid, "ok": False, "error": str(e)})
        finally:
            if cleanup:
                _cleanup_workdir(settings, mid)
    return results
