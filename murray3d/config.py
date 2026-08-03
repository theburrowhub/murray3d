from __future__ import annotations

import os
from pathlib import Path

from pydantic import BaseModel

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_BASE_URL = "https://murrayslab.com/3dbundle/api"
DEFAULT_CATEGORIES = ["figures", "scenery", "both"]
DEFAULT_FREEPIK_BASE_URL = "https://api.freepik.com/v1"
DEFAULT_FREEPIK_HEADER = "x-freepik-api-key"


class ConfigError(Exception):
    """Configuración inválida o incompleta (p. ej. falta la API key)."""


class Settings(BaseModel):
    base_url: str
    api_key: str
    cache_dir: Path
    shots_dir: Path
    known_categories: list[str]
    # Autogeneración (Freepik). Opcionales: solo hacen falta para `autogen`.
    freepik_api_key: str | None = None
    freepik_base_url: str = DEFAULT_FREEPIK_BASE_URL
    freepik_header: str = DEFAULT_FREEPIK_HEADER
    autogen_dir: Path | None = None


def _read_key_file(key_path: Path) -> str | None:
    try:
        first = key_path.read_text().splitlines()
    except OSError:
        return None
    for line in first:
        line = line.strip()
        if line:
            return line
    return None


def load_settings(key_path: Path | None = None, *,
                  require_api_key: bool = True) -> Settings:
    if key_path is None:
        key_path = PROJECT_ROOT / "key.txt"

    api_key = os.environ.get("MURRAY_API_KEY") or _read_key_file(key_path)
    if not api_key and require_api_key:
        raise ConfigError(
            "No se encontró la API key. Define MURRAY_API_KEY o crea key.txt "
            f"(buscado en {key_path})."
        )

    base = os.environ.get("MURRAY_BASE_URL", DEFAULT_BASE_URL).rstrip("/")
    home = Path(os.environ.get("HOME", str(Path.home())))
    root = home / ".murray3d"
    cache_dir = root / "cache"
    shots_dir = root / "shots"
    autogen_dir = root / "autogen"
    cache_dir.mkdir(parents=True, exist_ok=True)
    shots_dir.mkdir(parents=True, exist_ok=True)

    fp_base = os.environ.get("FREEPIK_BASE_URL", DEFAULT_FREEPIK_BASE_URL).rstrip("/")

    return Settings(
        base_url=base,
        api_key=api_key or "",
        cache_dir=cache_dir,
        shots_dir=shots_dir,
        known_categories=list(DEFAULT_CATEGORIES),
        freepik_api_key=os.environ.get("FREEPIK_API_KEY") or None,
        freepik_base_url=fp_base,
        freepik_header=os.environ.get("FREEPIK_API_HEADER", DEFAULT_FREEPIK_HEADER),
        autogen_dir=autogen_dir,
    )


def require_freepik(settings: Settings) -> str:
    """Devuelve la API key de Freepik o lanza ConfigError si no está configurada."""
    if not settings.freepik_api_key:
        raise ConfigError(
            "No se encontró la API key de Freepik. Define FREEPIK_API_KEY en .env "
            "o como variable de entorno (obtén la clave en "
            "https://www.freepik.com/developers/dashboard)."
        )
    return settings.freepik_api_key
