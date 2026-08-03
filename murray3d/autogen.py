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


BACKENDS = ("rest", "agent")


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


def run_autogen(doc: PromptDoc, generator: ImageGenerator, out_dir: Path, *,
                on_progress=None, resume: bool = True, limit: int | None = None,
                model: str | None = None, aspect_ratio: str | None = None,
                seed: int | None = None, ext: str = "jpg",
                manifest_name: str = "manifest.json") -> list[dict]:
    """Genera una imagen por prompt y las guarda en ``out_dir``.

    Devuelve una lista de dicts por trabajo:
    ``{id, name, ok, status, path?, url?, error?}``.
    ``status`` ∈ {"ok", "skipped", "error"}.
    """
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = out_dir / manifest_name

    jobs = iter_jobs(doc, model=model, aspect_ratio=aspect_ratio)
    if limit is not None:
        jobs = jobs[:limit]

    results: list[dict] = []
    total = len(jobs)
    for i, job in enumerate(jobs):
        dest = out_dir / f"{job.output_name}.{ext}"
        if on_progress:
            on_progress(i, total, job, "generando")

        if resume and dest.exists() and dest.stat().st_size > 0:
            results.append({"id": job.id, "name": job.output_name, "ok": True,
                            "status": "skipped", "path": str(dest)})
            _write_manifest(manifest_path, doc, results, total)
            continue

        try:
            urls = generator.generate(
                job.prompt, model=job.model, aspect_ratio=job.aspect_ratio,
                seed=_effective_seed(seed, job),
                negative_prompt=job.negative_prompt or None,
            )
            generator.download(urls[0], dest)
            results.append({"id": job.id, "name": job.output_name, "ok": True,
                            "status": "ok", "path": str(dest), "url": urls[0]})
        except Exception as e:  # noqa: BLE001 - continuar el lote ante error por item
            results.append({"id": job.id, "name": job.output_name, "ok": False,
                            "status": "error", "error": str(e)})
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
