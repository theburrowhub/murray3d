"""Salud/autenticación del MCP de Magnific en el CLI `claude`.

La autogeneración depende de que el MCP de Magnific esté **autenticado** en
`claude` (el connector OAuth de claude.ai caduca cada cierto tiempo). Aquí
comprobamos su estado (parseando `claude mcp list`) para, como *preflight*,
avisar y pedir re-autenticación en vez de fallar con un error opaco a mitad de
lote.

El ``runner`` (que devuelve la salida de `claude mcp list`) es inyectable para
tests, sin subproceso.
"""
from __future__ import annotations

import subprocess

# Identificamos el servidor por su URL (robusto al nombre del connector).
MAGNIFIC_URL_MATCH = "mcp.magnific.com"

REAUTH_HINT = (
    "El MCP de Magnific no está autenticado (o su sesión ha caducado).\n"
    "Re-autentícalo y reintenta:\n"
    "  • En Claude Code: ejecuta /mcp y autentica «Magnific», o\n"
    "  • claude mcp add --transport http magnific https://mcp.magnific.com"
)


class McpAuthError(Exception):
    """El MCP de Magnific no está disponible/autenticado."""


def _default_list_runner() -> str:
    try:
        proc = subprocess.run(["claude", "mcp", "list"],
                              capture_output=True, text=True, timeout=90)
    except FileNotFoundError as e:
        raise McpAuthError("No se encontró el binario `claude` en el PATH.") from e
    except subprocess.TimeoutExpired as e:
        raise McpAuthError("`claude mcp list` no respondió a tiempo.") from e
    return f"{proc.stdout}\n{proc.stderr}"


def magnific_status(runner=None) -> tuple[bool, str]:
    """Devuelve ``(conectado, detalle)`` del MCP de Magnific.

    ``conectado`` es True solo si aparece y está "Connected"/✔ y NO "Needs
    authentication". ``detalle`` es la línea de estado (o un motivo).
    """
    out = (runner or _default_list_runner)()
    line = next((r.strip() for r in out.splitlines() if MAGNIFIC_URL_MATCH in r), None)
    if line is None:
        return False, "no está configurado en `claude` (no aparece en `claude mcp list`)"
    low = line.lower()
    connected = ("connected" in low or "✔" in line) and "needs authentication" not in low
    return connected, line


def ensure_magnific_auth(runner=None) -> None:
    """Lanza ``McpAuthError`` con instrucciones si el MCP no está autenticado."""
    ok, detail = magnific_status(runner=runner)
    if not ok:
        raise McpAuthError(f"{detail}\n\n{REAUTH_HINT}")
