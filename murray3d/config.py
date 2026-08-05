from __future__ import annotations

import os
from pathlib import Path

from pydantic import BaseModel

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_BASE_URL = "https://murrayslab.com/3dbundle/api"
DEFAULT_CATEGORIES = ["figures", "scenery", "both"]


class ConfigError(Exception):
    """Configuración inválida o incompleta (p. ej. falta la API key)."""


class Settings(BaseModel):
    base_url: str
    api_key: str
    cache_dir: Path
    shots_dir: Path
    known_categories: list[str]
    # Directorio de salida de la autogeneración (imágenes + GLB).
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


def user_config_key_path() -> Path:
    """Ruta del key.txt en el directorio de configuración de usuario (XDG)."""
    home = Path(os.environ.get("HOME", str(Path.home())))
    base = os.environ.get("XDG_CONFIG_HOME") or str(home / ".config")
    return Path(base) / "murray3d" / "key.txt"


def load_settings(key_path: Path | None = None, *,
                  require_api_key: bool = True) -> Settings:
    # Orden: MURRAY_API_KEY > key_path explícito > ~/.config/murray3d/key.txt >
    # key.txt del proyecto (compatibilidad).
    api_key = os.environ.get("MURRAY_API_KEY")
    if not api_key:
        if key_path is not None:
            candidates = [Path(key_path)]
        else:
            candidates = [user_config_key_path(), PROJECT_ROOT / "key.txt"]
        for cand in candidates:
            api_key = _read_key_file(cand)
            if api_key:
                break
    if not api_key and require_api_key:
        raise ConfigError(
            "No se encontró la API key. Define MURRAY_API_KEY, crea "
            f"{user_config_key_path()} o key.txt en el proyecto."
        )

    base = os.environ.get("MURRAY_BASE_URL", DEFAULT_BASE_URL).rstrip("/")
    home = Path(os.environ.get("HOME", str(Path.home())))
    root = home / ".murray3d"
    cache_dir = root / "cache"
    shots_dir = root / "shots"
    autogen_dir = root / "autogen"
    cache_dir.mkdir(parents=True, exist_ok=True)
    shots_dir.mkdir(parents=True, exist_ok=True)

    return Settings(
        base_url=base,
        api_key=api_key or "",
        cache_dir=cache_dir,
        shots_dir=shots_dir,
        known_categories=list(DEFAULT_CATEGORIES),
        autogen_dir=autogen_dir,
    )
