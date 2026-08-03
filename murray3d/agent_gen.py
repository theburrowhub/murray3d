"""Backend de generación por **agente simple**: `claude` + MCP de Freepik.

En vez de llamar a la API REST de Freepik, este backend lanza el binario
``claude`` como subproceso (igual que ``ai.py`` para los metadatos) conectado al
**servidor MCP de Freepik**. El agente recibe el prompt, invoca la herramienta de
generación del MCP, espera a que termine y devuelve las URLs resultantes como
JSON. murray3d las descarga.

Esto da sentido al MCP dentro de la app: el agente abstrae la elección de
endpoint, el mapeo de parámetros y el polling; si Freepik cambia su API, el MCP
oficial se actualiza sin tocar murray3d.

Requisitos en tiempo de ejecución:
- ``claude`` en el PATH y autenticado.
- El MCP de Freepik añadido y autenticado en el CLI ``claude`` (``claude mcp add``
  o ``/mcp``), o pasado por ``--mcp-config`` (fichero JSON con ``mcpServers``).

Implementa el protocolo ``autogen.ImageGenerator`` (``generate`` + ``download``),
así que es intercambiable con ``FreepikClient`` detrás del motor de lotes.
El ``runner`` es inyectable para tests (sin subproceso ni red).
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

from .ai import _extract_inner_json  # reutilizamos el parseo del wrapper de claude
from .freepik import download_url

# Herramientas MCP permitidas por defecto (todas las del server de Freepik).
DEFAULT_ALLOWED_TOOLS = "mcp__freepik"

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
        "Usa las herramientas del servidor MCP de Freepik para generar UNA imagen "
        "a partir del siguiente prompt. Si la generación es asíncrona, espera "
        "(haz polling) hasta que termine y recoge las URLs resultantes.\n\n"
        f"Modelo de imagen preferido: {model}\n"
        f"Relación de aspecto: {aspect_ratio}\n"
        f"Prompt:\n{prompt}\n\n"
        "Cuando tengas el resultado, devuelve SOLO el objeto JSON pedido con "
        "`image_urls` (la lista de URLs de las imágenes generadas). No descargues "
        "las imágenes; solo devuelve sus URLs."
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
    """Genera imágenes vía `claude -p` + MCP de Freepik (agente simple)."""

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

    def generate(self, prompt: str, *, model: str = "flux-dev",
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
