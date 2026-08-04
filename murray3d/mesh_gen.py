"""Generación de malla 3D (GLB) por **agente** + MCP de Magnific.

La herramienta `models3d_generate` (image-to-3D → GLB, usa Tripo/Trellis) SOLO
está disponible por el servidor MCP de Magnific (`mcp.magnific.com`, OAuth); no
hay endpoint REST. Por eso el paso 3D va, obligatoriamente, por un **agente
simple**: `claude` conectado a ese MCP recibe la URL de la imagen, invoca
`models3d_generate`, espera y devuelve la URL del `.glb`. murray3d lo descarga.

Requisitos en tiempo de ejecución:
- ``claude`` en el PATH y autenticado.
- El **MCP de Magnific autenticado** en `claude` (`/mcp` → login OAuth), o su
  transporte definido vía ``--mcp-config`` (ver examples/magnific-mcp.json). El
  login OAuth se hace una vez de forma interactiva con ``/mcp``.

⚠️ Coste: cada generación 3D gasta ~580–1160 créditos (Tripo/Trellis). Úsese en
lotes controlados; comprueba el saldo antes de tiradas grandes.

Implementa un protocolo compatible con el motor de lotes (``generate_from_image``
+ ``download``). El ``runner`` es inyectable para tests (sin subproceso ni red).
"""
from __future__ import annotations

import json
from pathlib import Path

from .agent_gen import default_runner
from .ai import _extract_inner_json
from .freepik import download_url

# Prefijo de herramientas del MCP de Magnific (según el nombre del server en la
# config MCP; examples/magnific-mcp.json lo llama "magnific").
DEFAULT_ALLOWED_TOOLS = "mcp__magnific"

MESH_JSON_SCHEMA = {
    "type": "object",
    "properties": {
        "model_urls": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["model_urls"],
    "additionalProperties": False,
}


class MeshGenError(Exception):
    pass


def build_mesh_prompt(image_url: str, fmt: str = "glb") -> str:
    return (
        "Usa la herramienta `models3d_generate` del servidor MCP de Magnific para "
        "generar UN modelo 3D a partir de la siguiente imagen (image-to-3D). Si la "
        "generación es asíncrona, espera (haz polling) hasta que termine y recoge "
        "la URL del modelo resultante.\n\n"
        f"Formato de salida deseado: {fmt.upper()}\n"
        f"Imagen de entrada (URL): {image_url}\n\n"
        "Cuando tengas el resultado, devuelve SOLO el objeto JSON pedido con "
        "`model_urls` (la lista de URLs de los modelos 3D generados). No descargues "
        "el modelo; solo devuelve su URL."
    )


class AgentMeshGenerator:
    """Genera mallas 3D vía `claude` + MCP de Magnific (`models3d_generate`)."""

    def __init__(self, runner=None, claude_model: str | None = None,
                 mcp_config: str | None = None,
                 allowed_tools: str = DEFAULT_ALLOWED_TOOLS,
                 extra_args: list[str] | None = None, fmt: str = "glb"):
        self.runner = runner or default_runner
        self.claude_model = claude_model
        self.mcp_config = mcp_config
        self.allowed_tools = allowed_tools
        self.extra_args = list(extra_args or [])
        self.fmt = fmt

    def _cmd(self, prompt_text: str) -> list[str]:
        cmd = [
            "claude", "-p", prompt_text,
            "--output-format", "json",
            "--json-schema", json.dumps(MESH_JSON_SCHEMA),
            "--allowedTools", self.allowed_tools,
        ]
        if self.claude_model:
            cmd += ["--model", self.claude_model]
        if self.mcp_config:
            cmd += ["--mcp-config", self.mcp_config]
        cmd += self.extra_args
        return cmd

    def generate_from_image(self, image_url: str, *, fmt: str | None = None
                            ) -> list[str]:
        if not image_url:
            raise MeshGenError("Falta la URL de la imagen de entrada para el 3D.")
        prompt_text = build_mesh_prompt(image_url, fmt or self.fmt)
        stdout = self.runner(self._cmd(prompt_text))
        inner = _extract_inner_json(stdout)
        urls = inner.get("model_urls") if isinstance(inner, dict) else None
        urls = [u for u in (urls or []) if u]
        if not urls:
            raise MeshGenError(f"El agente no devolvió URLs de modelo 3D: {inner!r}")
        return urls

    def download(self, url: str, dest: Path) -> Path:
        return download_url(url, dest)
