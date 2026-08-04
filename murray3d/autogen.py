"""Autogeneración por lotes de imágenes a partir del JSON de prompts.

Pensado para cientos de prompts: se procesa **de uno en uno** (serie), se escribe
un ``manifest.json`` incremental tras cada trabajo (para reanudar si se corta),
y un error en un prompt NO aborta el lote (se registra y se continúa).

El generador se pasa como dependencia (protocolo ``ImageGenerator``); en producción
es ``FreepikClient``, en tests un doble. Así el motor de lotes queda desacoplado
del proveedor y se puede enchufar un image-to-3D en el futuro.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Protocol

from .prompts import GenJob, PromptDoc, iter_jobs


class ImageGenerator(Protocol):
    def generate(self, prompt: str, *, model: str, aspect_ratio: str,
                 seed: int | None = None,
                 negative_prompt: str | None = None) -> list[str]: ...

    def download(self, url: str, dest: Path) -> Path: ...


class MeshGenerator(Protocol):
    def generate_from_image(self, image_url: str) -> list[str]: ...

    def download(self, url: str, dest: Path) -> Path: ...


BACKENDS = ("rest", "agent")


def build_mesh_generator(settings, *, claude_model: str | None = None,
                         mcp_config: str | None = None) -> MeshGenerator:
    """Generador de malla 3D (agente + MCP de Magnific). Es la única vía: no hay
    REST para 3D. Requiere el MCP de Magnific autenticado en `claude`."""
    from .mesh_gen import AgentMeshGenerator
    return AgentMeshGenerator(claude_model=claude_model, mcp_config=mcp_config)


def build_generator(backend: str, settings, *, claude_model: str | None = None,
                    mcp_config: str | None = None) -> ImageGenerator:
    """Construye el generador según el backend (compartido por CLI y GUI).

    - ``rest``: API de Freepik directa (necesita FREEPIK_API_KEY).
    - ``agent``: `claude` + MCP de Freepik (agente simple).
    """
    if backend == "rest":
        from .config import require_freepik
        from .freepik import FreepikClient
        key = require_freepik(settings)
        return FreepikClient(key, base_url=settings.freepik_base_url,
                             api_header=settings.freepik_header)
    if backend == "agent":
        from .agent_gen import AgentImageGenerator
        return AgentImageGenerator(claude_model=claude_model, mcp_config=mcp_config)
    from .config import ConfigError
    raise ConfigError(f"Backend desconocido: {backend!r}. Usa 'rest' o 'agent'.")


def _effective_seed(base_seed: int | None, job: GenJob) -> int | None:
    """Deriva una semilla reproducible por trabajo (base + id) o None (aleatoria).

    Freepik exige seed en 1..4294967295; se acota a ese rango.
    """
    if base_seed is None:
        return None
    v = int(base_seed) + int(job.id)
    return ((v - 1) % 4294967295) + 1  # acota a 1..4294967295


def _exists_nonempty(p: Path) -> bool:
    return p.exists() and p.stat().st_size > 0


def _load_prev(manifest_path: Path) -> dict[str, dict]:
    """Carga resultados previos por nombre (para reutilizar la URL de imagen en
    resume y no re-gastar créditos de imagen al reintentar solo el 3D)."""
    try:
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return {r["name"]: r for r in data.get("results", []) if r.get("name")}


def run_autogen(doc: PromptDoc, generator: ImageGenerator, out_dir: Path, *,
                on_progress=None, resume: bool = True, limit: int | None = None,
                model: str | None = None, aspect_ratio: str | None = None,
                seed: int | None = None, ext: str = "jpg",
                make_3d: bool = False, mesh_generator: MeshGenerator | None = None,
                mesh_ext: str = "glb",
                manifest_name: str = "manifest.json") -> list[dict]:
    """Genera una imagen por prompt (y opcionalmente su malla 3D) en ``out_dir``.

    Con ``make_3d=True`` y un ``mesh_generator``, tras la imagen genera el `.glb`
    a partir de su URL (image-to-3D vía agente + MCP de Magnific).

    Devuelve una lista de dicts por trabajo:
    ``{id, name, ok, status, path?, url?, glb_path?, glb_url?, error?}``.
    ``status`` ∈ {"ok", "skipped", "error"}. La decisión de "saltar" (resume) mira
    el `.glb` si ``make_3d``, o la imagen en caso contrario.
    """
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = out_dir / manifest_name
    prev = _load_prev(manifest_path) if resume else {}

    if make_3d and mesh_generator is None:
        raise ValueError("make_3d=True requiere un mesh_generator.")

    jobs = iter_jobs(doc, model=model, aspect_ratio=aspect_ratio)
    if limit is not None:
        jobs = jobs[:limit]

    results: list[dict] = []
    total = len(jobs)
    for i, job in enumerate(jobs):
        name = job.output_name
        img_dest = out_dir / f"{name}.{ext}"
        glb_dest = out_dir / f"{name}.{mesh_ext}"
        target = glb_dest if make_3d else img_dest
        if on_progress:
            on_progress(i, total, job, "generando")

        if resume and _exists_nonempty(target):
            results.append({"id": job.id, "name": name, "ok": True,
                            "status": "skipped", "path": str(target)})
            _write_manifest(manifest_path, doc, results, total)
            continue

        rec: dict = {"id": job.id, "name": name, "ok": True, "status": "ok"}
        image_url: str | None = None
        try:
            # --- Imagen: reutiliza la URL previa si ya está descargada ---
            prev_url = prev.get(name, {}).get("url")
            if _exists_nonempty(img_dest) and prev_url:
                image_url = prev_url
            else:
                urls = generator.generate(
                    job.prompt, model=job.model, aspect_ratio=job.aspect_ratio,
                    seed=_effective_seed(seed, job),
                    negative_prompt=job.negative_prompt or None,
                )
                image_url = urls[0]
                generator.download(image_url, img_dest)
            rec["path"] = str(img_dest)
            rec["url"] = image_url

            # --- Malla 3D opcional (agente + MCP de Magnific) ---
            if make_3d:
                if on_progress:
                    on_progress(i, total, job, "3D")
                m_urls = mesh_generator.generate_from_image(image_url)
                mesh_generator.download(m_urls[0], glb_dest)
                rec["glb_path"] = str(glb_dest)
                rec["glb_url"] = m_urls[0]

            results.append(rec)
        except Exception as e:  # noqa: BLE001 - continuar el lote ante error por item
            err = {"id": job.id, "name": name, "ok": False, "status": "error",
                   "error": str(e)}
            if _exists_nonempty(img_dest):  # la imagen pudo salir; el 3D no
                err["path"] = str(img_dest)
                if image_url:  # conserva la URL para reutilizarla en resume (solo 3D)
                    err["url"] = image_url
            results.append(err)
        _write_manifest(manifest_path, doc, results, total)

    return results


def _write_manifest(path: Path, doc: PromptDoc, results: list[dict], total: int
                    ) -> None:
    done = [r for r in results if r["ok"]]
    payload = {
        "total": total,
        "processed": len(results),
        "ok": len(done),
        "errors": len([r for r in results if not r["ok"]]),
        "metadata": doc.metadata,
        "results": results,
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2),
                    encoding="utf-8")


def summarize(results: list[dict]) -> dict:
    return {
        "ok": len([r for r in results if r["status"] == "ok"]),
        "skipped": len([r for r in results if r["status"] == "skipped"]),
        "errors": len([r for r in results if r["status"] == "error"]),
        "total": len(results),
    }
