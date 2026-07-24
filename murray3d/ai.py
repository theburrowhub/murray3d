from __future__ import annotations

import json
import subprocess
from pathlib import Path

from .models import GeneratedMeta, GeneratedPackMeta


class AiError(Exception):
    pass


# Alias de modelos de Claude que ofrece la UI (además de "por defecto").
# `claude --model` acepta estos alias o el nombre completo del modelo.
CLAUDE_MODEL_ALIASES = ["opus", "sonnet", "haiku", "fable"]


JSON_SCHEMA = {
    "type": "object",
    "properties": {
        "title": {"type": "string"},
        "description": {"type": "string"},
        "tags": {"type": "array", "items": {"type": "string"}},
        "category": {"type": "string"},
        "price_eur": {"type": ["number", "null"]},
        "best_thumbnail_index": {"type": "integer"},
    },
    "required": ["title", "description", "tags", "category", "best_thumbnail_index"],
    "additionalProperties": False,
}


def build_prompt(shots: list[Path], categories: list[str]) -> str:
    listing = "\n".join(f"- {Path(s).name}" for s in shots)
    cats = ", ".join(categories)
    return (
        "Eres un experto en catalogación de modelos 3D para una tienda de miniaturas.\n"
        "En el directorio de trabajo actual hay estos pantallazos del modelo, en orden:\n"
        f"{listing}\n\n"
        "Léelos con la herramienta Read (son imágenes) y, basándote SOLO en lo que ves, "
        "genera metadatos de venta en ESPAÑOL.\n"
        f"La categoría DEBE ser exactamente una de: {cats}.\n"
        "`best_thumbnail_index` es el índice (empezando en 0) del pantallazo más "
        "representativo para usar como miniatura.\n"
        "Devuelve solo el objeto JSON pedido: título atractivo, descripción de 1-3 frases, "
        "5-10 tags en minúsculas, categoría y un precio en euros sugerido (o null)."
    )


PACK_JSON_SCHEMA = {
    "type": "object",
    "properties": {
        "title": {"type": "string"},
        "description": {"type": "string"},
        "tags": {"type": "array", "items": {"type": "string"}},
        "price_eur": {"type": ["number", "null"]},
        "best_cover_index": {"type": "integer"},
    },
    "required": ["title", "description", "tags", "best_cover_index"],
    "additionalProperties": False,
}


def build_pack_prompt(shots: list[Path], model_titles: list[str]) -> str:
    lines = [f"- {Path(s).name}: {t}" for s, t in zip(shots, model_titles)]
    listing = "\n".join(lines)
    return (
        "Eres un experto en catalogación de PACKS (bundles) de modelos 3D para una "
        "tienda de miniaturas.\n"
        "Este pack agrupa varios modelos. En el directorio de trabajo hay una imagen "
        "por modelo, con el título actual de cada uno:\n"
        f"{listing}\n\n"
        "Lee las imágenes con la herramienta Read y, basándote en lo que ves y en los "
        "títulos, genera metadatos de venta del PACK COMPLETO en ESPAÑOL (del conjunto, "
        "no de un modelo suelto).\n"
        "`best_cover_index` es el índice (empezando en 0) de la imagen que mejor "
        "representa el pack como portada.\n"
        "Devuelve solo el JSON pedido: un título atractivo para el bundle, una "
        "descripción de 1-3 frases que venda el conjunto, 5-10 tags en minúsculas y un "
        "precio en euros sugerido para el pack (o null)."
    )


def _model_args(model) -> list[str]:
    return ["--model", model] if model else []


def generate_pack_metadata(shots: list[Path], model_titles: list[str],
                           runner=None, model=None) -> GeneratedPackMeta:
    if not shots:
        raise AiError("No hay imágenes de modelos para analizar")
    runner = runner or default_runner
    shots_dir = Path(shots[0]).resolve().parent
    prompt = build_pack_prompt(shots, model_titles)
    cmd = [
        "claude", "-p", prompt,
        "--output-format", "json",
        "--json-schema", json.dumps(PACK_JSON_SCHEMA),
        *_model_args(model),
        "--add-dir", str(shots_dir),
        "--allowedTools", "Read",
    ]
    stdout = runner(cmd, shots_dir)
    inner = _extract_inner_json(stdout)
    meta = GeneratedPackMeta.model_validate(inner)
    if not (0 <= meta.best_cover_index < len(shots)):
        meta.best_cover_index = 0
    return meta


def default_runner(cmd: list[str], cwd: Path) -> str:
    proc = subprocess.run(cmd, cwd=str(cwd), capture_output=True, text=True)
    if proc.returncode != 0:
        raise AiError(
            f"claude terminó con código {proc.returncode}.\n"
            f"stderr: {proc.stderr}\nstdout: {proc.stdout}"
        )
    return proc.stdout


def _extract_inner_json(stdout: str) -> dict:
    try:
        wrapper = json.loads(stdout)
    except json.JSONDecodeError as e:
        raise AiError(f"Salida de claude no es JSON: {e}") from e
    if isinstance(wrapper, dict) and wrapper.get("is_error"):
        raise AiError(f"claude devolvió error: {wrapper.get('result')}")
    result = wrapper.get("result", wrapper) if isinstance(wrapper, dict) else wrapper
    if isinstance(result, dict):
        return result
    try:
        return json.loads(result)
    except (json.JSONDecodeError, TypeError) as e:
        raise AiError(f"No se pudo parsear el JSON de metadatos: {e}") from e


def generate_metadata(shots: list[Path], categories: list[str], runner=None,
                      model=None) -> GeneratedMeta:
    if not shots:
        raise AiError("No hay pantallazos para analizar")
    runner = runner or default_runner
    shots_dir = Path(shots[0]).resolve().parent
    prompt = build_prompt(shots, categories)
    cmd = [
        "claude", "-p", prompt,
        "--output-format", "json",
        "--json-schema", json.dumps(JSON_SCHEMA),
        *_model_args(model),
        "--add-dir", str(shots_dir),
        "--allowedTools", "Read",
    ]
    stdout = runner(cmd, shots_dir)
    inner = _extract_inner_json(stdout)
    meta = GeneratedMeta.model_validate(inner)
    if meta.category not in categories:
        meta.category = categories[0]
    if not (0 <= meta.best_thumbnail_index < len(shots)):
        meta.best_thumbnail_index = 0
    return meta
