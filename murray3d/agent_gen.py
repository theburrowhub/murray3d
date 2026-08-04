"""Generación de imágenes por **agente**: `claude` + MCP de Magnific.

murray3d no llama a ninguna API REST: reutiliza el binario ``claude`` (el mismo
patrón que ``ai.py`` para los metadatos) conectado al **MCP de Magnific**. El
agente recibe el prompt, invoca `images_generate`, espera (`creations_wait`) y
devuelve la URL de la imagen. murray3d la descarga.

Requisitos en tiempo de ejecución:
- ``claude`` en el PATH y autenticado.
- El **MCP de Magnific** disponible para `claude` (`/mcp` → login OAuth, o
  ``claude mcp add --transport http magnific https://mcp.magnific.com``), o su
  transporte vía ``--mcp-config``.

Implementa el protocolo ``autogen.ImageGenerator`` (``generate`` + ``download``),
intercambiable con cualquier otro generador. El ``runner`` es inyectable (tests).
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

from .ai import _extract_inner_json  # reutilizamos el parseo del wrapper de claude
from .download import download_url

# Herramientas MCP permitidas por defecto: todo el server de Magnific.
# El connector de claude.ai se registra como "claude.ai Magnific" -> prefijo
# `mcp__claude_ai_Magnific`. Si lo añades con `claude mcp add magnific …`, el
# prefijo sería `mcp__magnific`: ajústalo con `allowed_tools`/`--allowedTools`.
DEFAULT_ALLOWED_TOOLS = "mcp__claude_ai_Magnific"
DEFAULT_IMAGE_MODEL = "flux-dev"  # `mode` de Magnific (flux-dev, seedream-5-pro, …)

AGENT_JSON_SCHEMA = {
    "type": "object",
    "properties": {
        "image_urls": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["image_urls"],
    "additionalProperties": False,
}


class AgentGenError(Exception):
    pass


def build_gen_prompt(prompt: str, model: str, aspect_ratio: str) -> str:
    return (
        "Genera UNA imagen usando la herramienta `images_generate` del MCP de "
        "Magnific.\n"
        f"Modelo (`mode`): {model}\n"
        f"Relación de aspecto (`aspectRatio`): {aspect_ratio}\n"
        "count: 1\n\n"
        f"Prompt:\n{prompt}\n\n"
        "Espera a que termine con `creations_wait` y toma la URL de resultado "
        "(`url`). Devuelve SOLO el objeto JSON pedido con `image_urls` (la lista "
        "de URLs de las imágenes generadas). No descargues las imágenes; solo "
        "devuelve sus URLs."
    )


def default_runner(cmd: list[str], cwd: Path | None = None) -> str:
    proc = subprocess.run(cmd, cwd=str(cwd) if cwd else None,
                          capture_output=True, text=True)
    if proc.returncode != 0:
        raise AgentGenError(
            f"claude terminó con código {proc.returncode}.\n"
            f"stderr: {proc.stderr}\nstdout: {proc.stdout}"
        )
    return proc.stdout


class AgentImageGenerator:
    """Genera imágenes vía `claude -p` + MCP de Magnific (`images_generate`)."""

    def __init__(self, runner=None, claude_model: str | None = None,
                 mcp_config: str | None = None,
                 allowed_tools: str = DEFAULT_ALLOWED_TOOLS,
                 extra_args: list[str] | None = None):
        self.runner = runner or default_runner
        self.claude_model = claude_model
        self.mcp_config = mcp_config
        self.allowed_tools = allowed_tools
        self.extra_args = list(extra_args or [])

    def _cmd(self, prompt_text: str) -> list[str]:
        cmd = [
            "claude", "-p", prompt_text,
            "--output-format", "json",
            "--json-schema", json.dumps(AGENT_JSON_SCHEMA),
            "--allowedTools", self.allowed_tools,
        ]
        if self.claude_model:
            cmd += ["--model", self.claude_model]
        if self.mcp_config:
            cmd += ["--mcp-config", self.mcp_config]
        cmd += self.extra_args
        return cmd

    def generate(self, prompt: str, *, model: str = DEFAULT_IMAGE_MODEL,
                 aspect_ratio: str = "1:1", seed: int | None = None,
                 negative_prompt: str | None = None) -> list[str]:
        # seed/negative_prompt se ignoran aquí: el agente/MCP decide los detalles.
        prompt_text = build_gen_prompt(prompt, model, aspect_ratio)
        stdout = self.runner(self._cmd(prompt_text))
        inner = _extract_inner_json(stdout)
        urls = inner.get("image_urls") if isinstance(inner, dict) else None
        urls = [u for u in (urls or []) if u]
        if not urls:
            raise AgentGenError(f"El agente no devolvió URLs de imagen: {inner!r}")
        return urls

    def download(self, url: str, dest: Path) -> Path:
        return download_url(url, dest)
