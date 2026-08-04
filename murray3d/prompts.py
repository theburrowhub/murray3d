"""Carga y normalización del JSON de prompts para autogeneración.

El JSON describe cientos de figuras (personajes) con varios prompts cada una.
Aquí lo modelamos con Pydantic (tolerante a campos extra), resolvemos el nombre
de salida de cada imagen según ``automation_config.naming_convention.pattern`` y
lo aplanamos a una lista de ``GenJob`` lista para procesar en serie.

Estructura esperada (resumen)::

    {
      "metadata": { "total_prompts": 400, ... },
      "figures": [
        {"group": "Dragon Ball", "character": "Goku", "prompts": [
          {"id": 1, "variant": 1, "title": "Kamehameha Cargando",
           "base_size": "40mm", "painting_style": "Citadel",
           "prompt": "Miniature figure of Goku...", "tags": ["anime", ...]}
        ]}
      ],
      "automation_config": {
        "image_generation": {"recommended_model": "flux-dev", "aspect_ratio": "3:4"},
        "naming_convention": {"pattern": "{group}_{character}_{variant:02d}_{title_snake_case}"}
      }
    }
"""
from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field


class PromptError(Exception):
    """JSON de prompts inválido o incompleto."""


class _Base(BaseModel):
    model_config = ConfigDict(extra="ignore")


DEFAULT_PATTERN = "{group}_{character}_{variant:02d}_{title_snake_case}"


class ImageGenConfig(_Base):
    recommended_model: str = "flux-dev"
    aspect_ratio: str = "1:1"
    negative_prompt: str = ""


class NamingConfig(_Base):
    pattern: str = DEFAULT_PATTERN


class AutomationConfig(_Base):
    image_generation: ImageGenConfig = Field(default_factory=ImageGenConfig)
    naming_convention: NamingConfig = Field(default_factory=NamingConfig)


class PromptSpec(_Base):
    id: int
    variant: int = 1
    title: str = ""
    base_size: str | None = None
    base_theme: str | None = None
    painting_style: str | None = None
    prompt: str
    tags: list[str] = Field(default_factory=list)


class Figure(_Base):
    group: str = ""
    character: str = ""
    prompts: list[PromptSpec] = Field(default_factory=list)


class PromptDoc(_Base):
    metadata: dict = Field(default_factory=dict)
    figures: list[Figure] = Field(default_factory=list)
    automation_config: AutomationConfig = Field(default_factory=AutomationConfig)


def snake_case(text: str) -> str:
    """Normaliza a un slug ascii en snake_case, seguro para nombres de fichero.

    "Kamehameha Cargando" -> "kamehameha_cargando"; quita acentos y símbolos.
    """
    text = unicodedata.normalize("NFKD", text or "")
    text = text.encode("ascii", "ignore").decode("ascii").lower()
    text = re.sub(r"[^a-z0-9]+", "_", text)
    return text.strip("_")


@dataclass
class GenJob:
    """Un trabajo de generación aplanado, listo para procesar en serie."""

    id: int
    group: str
    character: str
    variant: int
    title: str
    output_name: str
    prompt: str
    model: str
    aspect_ratio: str
    negative_prompt: str = ""
    base_size: str | None = None
    painting_style: str | None = None
    base_theme: str | None = None
    tags: list[str] = field(default_factory=list)


def resolve_name(pattern: str, figure: Figure, spec: PromptSpec) -> str:
    """Aplica el patrón de nombres a una figura+prompt y devuelve un slug seguro.

    Tokens soportados: ``group``, ``character``, ``variant`` (admite ``:02d``),
    ``id``, ``title``, ``title_snake_case``, ``base_size``, ``painting_style``,
    ``base_theme``. Ante un patrón inválido cae al patrón por defecto.
    """
    tokens = {
        "group": snake_case(figure.group),
        "character": snake_case(figure.character),
        "variant": spec.variant,
        "id": spec.id,
        "title": snake_case(spec.title),
        "title_snake_case": snake_case(spec.title),
        "base_size": snake_case(spec.base_size or ""),
        "painting_style": snake_case(spec.painting_style or ""),
        "base_theme": snake_case(spec.base_theme or ""),
    }
    try:
        name = (pattern or DEFAULT_PATTERN).format(**tokens)
    except (KeyError, ValueError, IndexError):
        name = DEFAULT_PATTERN.format(**tokens)
    # Colapsa separadores accidentales y asegura un slug de fichero válido.
    name = name.replace("/", "_").replace("\\", "_").strip()
    name = re.sub(r"_+", "_", name).strip("_")
    return name or f"figura_{spec.id:04d}"


def iter_jobs(doc: PromptDoc, *, model: str | None = None,
              aspect_ratio: str | None = None) -> list[GenJob]:
    """Aplana el documento a una lista de ``GenJob`` en orden de aparición.

    ``model`` / ``aspect_ratio`` sobreescriben los de ``automation_config`` si se
    pasan; si no, se usan los del documento. Los nombres de salida duplicados se
    desambiguan con un sufijo ``_2``, ``_3``… para no pisar ficheros.
    """
    ig = doc.automation_config.image_generation
    naming = doc.automation_config.naming_convention
    eff_model = model or ig.recommended_model
    eff_aspect = aspect_ratio or ig.aspect_ratio
    neg = ig.negative_prompt or ""

    jobs: list[GenJob] = []
    seen: dict[str, int] = {}
    for figure in doc.figures:
        for spec in figure.prompts:
            name = resolve_name(naming.pattern, figure, spec)
            if name in seen:
                seen[name] += 1
                name = f"{name}_{seen[name]}"
            else:
                seen[name] = 1
            jobs.append(GenJob(
                id=spec.id,
                group=figure.group,
                character=figure.character,
                variant=spec.variant,
                title=spec.title,
                output_name=name,
                prompt=spec.prompt,
                model=eff_model,
                aspect_ratio=eff_aspect,
                negative_prompt=neg,
                base_size=spec.base_size,
                painting_style=spec.painting_style,
                base_theme=spec.base_theme,
                tags=list(spec.tags),
            ))
    return jobs


def parse_prompt_doc(data: dict) -> PromptDoc:
    try:
        return PromptDoc.model_validate(data)
    except Exception as e:  # noqa: BLE001 - envolvemos el ValidationError de pydantic
        raise PromptError(f"JSON de prompts inválido: {e}") from e


def load_prompt_doc(path: Path) -> PromptDoc:
    path = Path(path)
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as e:
        raise PromptError(f"No se pudo leer {path}: {e}") from e
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        raise PromptError(f"{path} no es JSON válido: {e}") from e
    if not isinstance(data, dict):
        raise PromptError(f"{path}: se esperaba un objeto JSON en la raíz.")
    return parse_prompt_doc(data)
