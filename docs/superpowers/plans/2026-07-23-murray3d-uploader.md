# murray3d Uploader Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Aplicación de escritorio nativa (PySide6) que gestiona modelos y packs 3D de la cuenta 3DBundle y los publica con metadatos generados por Claude Code a partir de pantallazos del modelo; con un núcleo compartido expuesto como CLI scriptable.

**Architecture:** Un núcleo Python sin dependencias de UI (`api`, `models`, `convert`, `render`, `ai`, `config`) que envuelve la API REST de 3DBundle, convierte/renderiza modelos y llama al CLI `claude` en headless. Sobre ese núcleo, dos frontends: un CLI (`typer`) y una GUI nativa (PySide6 con un `QWebEngineView` que embebe `<model-viewer>` para el preview 3D). El flujo de publicación con IA renderiza pantallazos con Playwright, se los pasa a `claude -p --output-format json --json-schema`, muestra lo propuesto para revisión y confirma la publicación vía `PATCH`.

**Tech Stack:** Python 3.11+, httpx, pydantic v2, typer, trimesh + pygltflib + numpy, playwright (Chromium), PySide6 (Qt + QtWebEngine), pytest. CLI externo en runtime: `claude`.

## Global Constraints

- Python floor: **3.11+**.
- Base URL de la API: **`https://murrayslab.com/3dbundle/api`** (configurable vía `MURRAY_BASE_URL`).
- Autenticación: header **`X-API-Key`**; clave desde **`key.txt`** (git-ignored, primera línea) o env **`MURRAY_API_KEY`** (env tiene prioridad).
- Extensiones de modelo permitidas: **`glb`, `obj`, `stl`**. Tamaño máx. subida: **200 MB**.
- Publicar = **`PATCH /models/{id}`** con `published: true` (no hay endpoint dedicado).
- Categoría propuesta por la IA debe pertenecer al **conjunto de categorías conocidas** (inferido de modelos existentes; fallback: `["figures", "scenery", "both"]`).
- Directorio de caché/estado de la app: **`~/.murray3d/`** (subdirs `cache/` para glb convertidos, `shots/` para pantallazos temporales).
- CLI `claude` invocado con: `claude -p <prompt> --output-format json --json-schema <schema_file> --add-dir <shots_dir> --allowedTools Read`.
- Todos los subcomandos CLI aceptan `--json` para salida máquina y devuelven código de salida no-cero ante error.
- Idioma de textos de UI y metadatos generados: **español**.
- Nombre del paquete Python: **`murray3d`**.

---

### Task 1: Scaffold del proyecto y `config.py`

**Files:**
- Create: `pyproject.toml`
- Create: `murray3d/__init__.py`
- Create: `murray3d/config.py`
- Create: `tests/__init__.py`
- Create: `tests/test_config.py`
- Create: `tests/conftest.py`

**Interfaces:**
- Consumes: nada (primera tarea).
- Produces:
  - `murray3d.config.Settings` (pydantic model) con campos: `base_url: str`, `api_key: str`, `cache_dir: Path`, `shots_dir: Path`, `known_categories: list[str]`.
  - `murray3d.config.load_settings(key_path: Path | None = None) -> Settings` — resuelve api_key desde `MURRAY_API_KEY` o `key.txt`; lanza `ConfigError` si no hay clave.
  - `murray3d.config.ConfigError(Exception)`.
  - `murray3d.config.PROJECT_ROOT: Path`.

- [ ] **Step 1: Write `pyproject.toml`**

```toml
[project]
name = "murray3d"
version = "0.1.0"
description = "Cliente local para 3DBundle: gestor de modelos/packs y publicación asistida por Claude Code"
requires-python = ">=3.11"
dependencies = [
    "httpx>=0.27",
    "pydantic>=2.6",
    "typer>=0.12",
    "trimesh>=4.4",
    "pygltflib>=1.16",
    "numpy>=1.26",
    "playwright>=1.45",
    "PySide6>=6.7",
]

[project.optional-dependencies]
dev = ["pytest>=8.0", "pytest-mock>=3.14"]

[project.scripts]
murray3d = "murray3d.cli:app"

[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[tool.setuptools.packages.find]
include = ["murray3d*"]

[tool.pytest.ini_options]
markers = [
    "integration: requiere red o Chromium de Playwright (deseleccionado por defecto)",
]
addopts = "-m 'not integration'"
```

- [ ] **Step 2: Write the failing test** `tests/test_config.py`

```python
import os
from pathlib import Path

import pytest

from murray3d.config import ConfigError, load_settings


def test_load_settings_from_env(tmp_path, monkeypatch):
    monkeypatch.setenv("MURRAY_API_KEY", "env-key-123")
    monkeypatch.setenv("HOME", str(tmp_path))
    s = load_settings(key_path=tmp_path / "missing.txt")
    assert s.api_key == "env-key-123"
    assert s.base_url == "https://murrayslab.com/3dbundle/api"
    assert s.cache_dir == tmp_path / ".murray3d" / "cache"
    assert s.shots_dir == tmp_path / ".murray3d" / "shots"
    assert s.cache_dir.is_dir()
    assert "both" in s.known_categories


def test_load_settings_from_key_file(tmp_path, monkeypatch):
    monkeypatch.delenv("MURRAY_API_KEY", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))
    key_file = tmp_path / "key.txt"
    key_file.write_text("file-key-abc\n\n")
    s = load_settings(key_path=key_file)
    assert s.api_key == "file-key-abc"


def test_env_overrides_file(tmp_path, monkeypatch):
    monkeypatch.setenv("MURRAY_API_KEY", "env-wins")
    monkeypatch.setenv("HOME", str(tmp_path))
    key_file = tmp_path / "key.txt"
    key_file.write_text("file-key\n")
    s = load_settings(key_path=key_file)
    assert s.api_key == "env-wins"


def test_missing_key_raises(tmp_path, monkeypatch):
    monkeypatch.delenv("MURRAY_API_KEY", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))
    with pytest.raises(ConfigError):
        load_settings(key_path=tmp_path / "nope.txt")
```

- [ ] **Step 3: Run test to verify it fails**

Run: `python -m pytest tests/test_config.py -v`
Expected: FAIL con `ModuleNotFoundError: No module named 'murray3d.config'`.

- [ ] **Step 4: Write `murray3d/__init__.py`**

```python
__version__ = "0.1.0"
```

- [ ] **Step 5: Write `murray3d/config.py`**

```python
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


def load_settings(key_path: Path | None = None) -> Settings:
    if key_path is None:
        key_path = PROJECT_ROOT / "key.txt"

    api_key = os.environ.get("MURRAY_API_KEY") or _read_key_file(key_path)
    if not api_key:
        raise ConfigError(
            "No se encontró la API key. Define MURRAY_API_KEY o crea key.txt "
            f"(buscado en {key_path})."
        )

    base = os.environ.get("MURRAY_BASE_URL", DEFAULT_BASE_URL).rstrip("/")
    home = Path(os.environ.get("HOME", str(Path.home())))
    root = home / ".murray3d"
    cache_dir = root / "cache"
    shots_dir = root / "shots"
    cache_dir.mkdir(parents=True, exist_ok=True)
    shots_dir.mkdir(parents=True, exist_ok=True)

    return Settings(
        base_url=base,
        api_key=api_key,
        cache_dir=cache_dir,
        shots_dir=shots_dir,
        known_categories=list(DEFAULT_CATEGORIES),
    )
```

- [ ] **Step 6: Write `tests/__init__.py` and `tests/conftest.py`**

`tests/__init__.py`: fichero vacío.

`tests/conftest.py`:
```python
import pytest


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    monkeypatch.delenv("MURRAY_BASE_URL", raising=False)
```

- [ ] **Step 7: Install and run tests to verify they pass**

Run:
```bash
python -m venv .venv && . .venv/bin/activate
pip install -e ".[dev]"
python -m pytest tests/test_config.py -v
```
Expected: 4 passed.

- [ ] **Step 8: Commit**

```bash
git add pyproject.toml murray3d/__init__.py murray3d/config.py tests/
git commit -m "feat: scaffold del proyecto y carga de configuración"
```

---

### Task 2: Modelos de datos (`models.py`)

**Files:**
- Create: `murray3d/models.py`
- Test: `tests/test_models.py`

**Interfaces:**
- Consumes: nada.
- Produces (pydantic v2 models con `model_config = ConfigDict(extra="ignore")`):
  - `Profile`: `id:int`, `email:str`, `name:str|None`, `author_name:str|None`, `key_prefix:str|None`.
  - `Model3D`: `id:int`, `title:str`, `description:str=""`, `category:str|None=None`, `tags:list[str]=[]`, `price_eur:float|None=None`, `filename:str|None=None`, `stored_name:str|None=None`, `file_format:str|None=None`, `file_size:int|None=None`, `thumbnail:str|None=None`, `uploader:str|None=None`, `owner_id:int|None=None`, `author:str|None=None`, `published:bool=False`, `created_at:str|None=None`, `updated_at:str|None=None`.
  - `Pack`: `id:int`, `title:str`, `description:str=""`, `tags:list[str]=[]`, `price_eur:float|None=None`, `cover:str|None=None`, `model_ids:list[int]=[]`, `uploader:str|None=None`, `owner_id:int|None=None`, `author:str|None=None`, `published:bool=False`, `created_at:str|None=None`, `updated_at:str|None=None`.
  - `GeneratedMeta`: `title:str`, `description:str`, `tags:list[str]`, `category:str`, `price_eur:float|None=None`, `best_thumbnail_index:int=0`.

- [ ] **Step 1: Write the failing test** `tests/test_models.py`

```python
from murray3d.models import GeneratedMeta, Model3D, Pack, Profile

SAMPLE_MODEL = {
    "title": "model (1)", "description": "", "tags": [], "filename": "model (1).glb",
    "file_format": "glb", "thumbnail": None, "owner_id": 1, "published": True,
    "updated_at": "2026-07-23T10:02:38", "id": 5, "category": "both",
    "price_eur": None, "stored_name": "u1/abc.glb", "file_size": 29116232,
    "uploader": "Manuel Zea", "author": "Manuel Zea", "created_at": "2026-07-23T10:02:38",
    "extra_field_ignored": "x",
}


def test_model3d_parses_and_ignores_extra():
    m = Model3D.model_validate(SAMPLE_MODEL)
    assert m.id == 5
    assert m.title == "model (1)"
    assert m.published is True
    assert m.file_size == 29116232


def test_pack_defaults():
    p = Pack.model_validate({"id": 1, "title": "Pack A"})
    assert p.model_ids == []
    assert p.published is False


def test_profile_parses():
    prof = Profile.model_validate({"id": 2, "email": "a@b.com", "name": "X", "author_name": "Muriano"})
    assert prof.author_name == "Muriano"


def test_generated_meta_defaults():
    g = GeneratedMeta.model_validate(
        {"title": "T", "description": "D", "tags": ["a"], "category": "both"}
    )
    assert g.best_thumbnail_index == 0
    assert g.price_eur is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_models.py -v`
Expected: FAIL con `ModuleNotFoundError: No module named 'murray3d.models'`.

- [ ] **Step 3: Write `murray3d/models.py`**

```python
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class _Base(BaseModel):
    model_config = ConfigDict(extra="ignore")


class Profile(_Base):
    id: int
    email: str
    name: str | None = None
    author_name: str | None = None
    key_prefix: str | None = None


class Model3D(_Base):
    id: int
    title: str
    description: str = ""
    category: str | None = None
    tags: list[str] = Field(default_factory=list)
    price_eur: float | None = None
    filename: str | None = None
    stored_name: str | None = None
    file_format: str | None = None
    file_size: int | None = None
    thumbnail: str | None = None
    uploader: str | None = None
    owner_id: int | None = None
    author: str | None = None
    published: bool = False
    created_at: str | None = None
    updated_at: str | None = None


class Pack(_Base):
    id: int
    title: str
    description: str = ""
    tags: list[str] = Field(default_factory=list)
    price_eur: float | None = None
    cover: str | None = None
    model_ids: list[int] = Field(default_factory=list)
    uploader: str | None = None
    owner_id: int | None = None
    author: str | None = None
    published: bool = False
    created_at: str | None = None
    updated_at: str | None = None


class GeneratedMeta(_Base):
    title: str
    description: str
    tags: list[str] = Field(default_factory=list)
    category: str
    price_eur: float | None = None
    best_thumbnail_index: int = 0
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_models.py -v`
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add murray3d/models.py tests/test_models.py
git commit -m "feat: modelos de datos pydantic (Model3D, Pack, Profile, GeneratedMeta)"
```

---

### Task 3: Cliente API — núcleo, auth y errores (`api.py` parte 1)

**Files:**
- Create: `murray3d/api.py`
- Test: `tests/test_api_auth.py`

**Interfaces:**
- Consumes: `murray3d.config.Settings`, `murray3d.models.Profile`.
- Produces:
  - `murray3d.api.ApiError(Exception)` con `.status:int` y `.detail:str`.
  - `AuthError(ApiError)`, `NotFoundError(ApiError)`, `ValidationError(ApiError)`.
  - `class Client`:
    - `__init__(self, settings: Settings, transport: httpx.BaseTransport | None = None)`
    - `whoami(self) -> Profile` → `GET /auth/me`.
    - Método interno `_request(method, path, **kwargs) -> httpx.Response` que inyecta el header `X-API-Key` y convierte errores HTTP en excepciones tipadas (401→AuthError, 404→NotFoundError, 422→ValidationError, otros 4xx/5xx→ApiError). El `detail` sale de `resp.json()["detail"]` si existe, si no del texto.
    - `close(self)` y soporte de context manager (`__enter__`/`__exit__`).

- [ ] **Step 1: Write the failing test** `tests/test_api_auth.py`

```python
import httpx
import pytest

from murray3d.api import AuthError, Client, ValidationError
from murray3d.config import Settings


def make_settings(tmp_path):
    return Settings(
        base_url="https://api.test/3dbundle/api",
        api_key="k-123",
        cache_dir=tmp_path / "cache",
        shots_dir=tmp_path / "shots",
        known_categories=["both"],
    )


def test_whoami_sends_key_and_parses(tmp_path):
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["key"] = request.headers.get("X-API-Key")
        captured["url"] = str(request.url)
        return httpx.Response(200, json={"id": 2, "email": "a@b.com", "name": "N", "author_name": "Muriano"})

    client = Client(make_settings(tmp_path), transport=httpx.MockTransport(handler))
    prof = client.whoami()
    assert prof.author_name == "Muriano"
    assert captured["key"] == "k-123"
    assert captured["url"] == "https://api.test/3dbundle/api/auth/me"


def test_401_raises_auth_error(tmp_path):
    def handler(request):
        return httpx.Response(401, json={"detail": "clave inválida"})

    client = Client(make_settings(tmp_path), transport=httpx.MockTransport(handler))
    with pytest.raises(AuthError) as exc:
        client.whoami()
    assert "clave inválida" in exc.value.detail


def test_422_raises_validation_error(tmp_path):
    def handler(request):
        return httpx.Response(422, json={"detail": [{"msg": "bad"}]})

    client = Client(make_settings(tmp_path), transport=httpx.MockTransport(handler))
    with pytest.raises(ValidationError):
        client.whoami()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_api_auth.py -v`
Expected: FAIL con `ModuleNotFoundError: No module named 'murray3d.api'`.

- [ ] **Step 3: Write `murray3d/api.py`**

```python
from __future__ import annotations

import json as _json

import httpx

from .config import Settings
from .models import Model3D, Pack, Profile


class ApiError(Exception):
    def __init__(self, status: int, detail: str):
        self.status = status
        self.detail = detail
        super().__init__(f"[{status}] {detail}")


class AuthError(ApiError):
    pass


class NotFoundError(ApiError):
    pass


class ValidationError(ApiError):
    pass


def _detail(resp: httpx.Response) -> str:
    try:
        data = resp.json()
    except ValueError:
        return resp.text or resp.reason_phrase
    if isinstance(data, dict) and "detail" in data:
        d = data["detail"]
        return d if isinstance(d, str) else _json.dumps(d, ensure_ascii=False)
    return _json.dumps(data, ensure_ascii=False)


class Client:
    def __init__(self, settings: Settings, transport: httpx.BaseTransport | None = None):
        self.settings = settings
        self._http = httpx.Client(
            base_url=settings.base_url,
            headers={"X-API-Key": settings.api_key},
            timeout=120.0,
            transport=transport,
        )

    def __enter__(self) -> "Client":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def close(self) -> None:
        self._http.close()

    def _request(self, method: str, path: str, **kwargs) -> httpx.Response:
        resp = self._http.request(method, path, **kwargs)
        if resp.status_code >= 400:
            detail = _detail(resp)
            if resp.status_code == 401:
                raise AuthError(401, detail)
            if resp.status_code == 404:
                raise NotFoundError(404, detail)
            if resp.status_code == 422:
                raise ValidationError(422, detail)
            raise ApiError(resp.status_code, detail)
        return resp

    def whoami(self) -> Profile:
        resp = self._request("GET", "/auth/me")
        return Profile.model_validate(resp.json())
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_api_auth.py -v`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add murray3d/api.py tests/test_api_auth.py
git commit -m "feat: cliente API núcleo con auth y errores tipados"
```

---

### Task 4: Cliente API — modelos (`api.py` parte 2)

**Files:**
- Modify: `murray3d/api.py` (añadir métodos a `Client`)
- Test: `tests/test_api_models.py`

**Interfaces:**
- Consumes: Task 3 (`Client`, errores), `Model3D`.
- Produces (métodos de `Client`):
  - `list_models(self, q=None, tag=None, category=None, only_published=None, mine=False, limit=100, offset=0) -> list[Model3D]` → `GET /models` (si `mine`, filtra por `owner_id == self.whoami().id` en cliente; cachea el id de perfil en `self._me_id`).
  - `get_model(self, model_id: int) -> Model3D` → `GET /models/{id}`.
  - `upload_model(self, file: Path, title: str, description="", category=None, tags: list[str] | None=None, price_eur: float | None=None, thumbnail: Path | None=None) -> Model3D` → `POST /models` multipart. `tags` se envía como cadena separada por comas.
  - `update_model(self, model_id: int, **fields) -> Model3D` → `PATCH /models/{id}` JSON (solo campos no-None; `tags` como lista).
  - `publish_model(self, model_id: int, **fields) -> Model3D` → conveniencia: `update_model(model_id, published=True, **fields)`.
  - `delete_model(self, model_id: int) -> None` → `DELETE /models/{id}`.
  - `set_thumbnail(self, model_id: int, image: Path) -> Model3D` → `POST /models/{id}/thumbnail` multipart campo `thumbnail`.
  - `download_model(self, model_id: int, dest: Path) -> Path` → `GET /models/{id}/download` (stream a `dest`).

- [ ] **Step 1: Write the failing test** `tests/test_api_models.py`

```python
from pathlib import Path

import httpx

from murray3d.api import Client
from murray3d.config import Settings


def make_settings(tmp_path):
    return Settings(base_url="https://api.test/3dbundle/api", api_key="k",
                    cache_dir=tmp_path / "c", shots_dir=tmp_path / "s",
                    known_categories=["both"])


MODEL_JSON = {"id": 7, "title": "T", "published": False, "tags": [], "category": "both"}


def test_list_models_query_params(tmp_path):
    seen = {}

    def handler(request):
        seen["params"] = dict(request.url.params)
        return httpx.Response(200, json=[MODEL_JSON])

    c = Client(make_settings(tmp_path), transport=httpx.MockTransport(handler))
    out = c.list_models(q="dragon", category="both", only_published=True, limit=10)
    assert len(out) == 1 and out[0].id == 7
    assert seen["params"]["q"] == "dragon"
    assert seen["params"]["category"] == "both"
    assert seen["params"]["only_published"] == "true"
    assert seen["params"]["limit"] == "10"


def test_upload_model_multipart(tmp_path):
    seen = {}
    f = tmp_path / "m.glb"
    f.write_bytes(b"glTF-bytes")

    def handler(request):
        seen["content_type"] = request.headers.get("content-type", "")
        seen["body"] = request.content
        return httpx.Response(200, json={**MODEL_JSON, "title": "Dragón"})

    c = Client(make_settings(tmp_path), transport=httpx.MockTransport(handler))
    m = c.upload_model(f, title="Dragón", tags=["a", "b"], category="both")
    assert m.title == "Dragón"
    assert "multipart/form-data" in seen["content_type"]
    assert b"Dragón" in seen["body"]
    assert b"a,b" in seen["body"]


def test_update_model_sends_only_set_fields(tmp_path):
    seen = {}

    def handler(request):
        seen["json"] = request.read()
        return httpx.Response(200, json={**MODEL_JSON, "published": True})

    c = Client(make_settings(tmp_path), transport=httpx.MockTransport(handler))
    m = c.publish_model(7, title="Nuevo", tags=["x"])
    assert m.published is True
    body = seen["json"].decode()
    assert '"published": true' in body.replace(" ", "").replace("\n", "") or '"published":true' in body.replace(" ", "")
    assert "Nuevo" in body


def test_set_thumbnail_multipart(tmp_path):
    seen = {}
    img = tmp_path / "shot.png"
    img.write_bytes(b"\x89PNG\r\n")

    def handler(request):
        seen["ct"] = request.headers.get("content-type", "")
        return httpx.Response(200, json=MODEL_JSON)

    c = Client(make_settings(tmp_path), transport=httpx.MockTransport(handler))
    c.set_thumbnail(7, img)
    assert "multipart/form-data" in seen["ct"]


def test_delete_model(tmp_path):
    seen = {}

    def handler(request):
        seen["method"] = request.method
        return httpx.Response(204)

    c = Client(make_settings(tmp_path), transport=httpx.MockTransport(handler))
    c.delete_model(7)
    assert seen["method"] == "DELETE"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_api_models.py -v`
Expected: FAIL con `AttributeError: 'Client' object has no attribute 'list_models'`.

- [ ] **Step 3: Add model methods to `murray3d/api.py`**

Añade al inicio del fichero (imports):
```python
from pathlib import Path
```

Añade estos métodos dentro de `class Client`:
```python
    def _params(self, **kw) -> dict:
        out = {}
        for k, v in kw.items():
            if v is None:
                continue
            out[k] = "true" if v is True else "false" if v is False else v
        return out

    def list_models(self, q=None, tag=None, category=None, only_published=None,
                    mine=False, limit=100, offset=0) -> list[Model3D]:
        params = self._params(q=q, tag=tag, category=category,
                              only_published=only_published, limit=limit, offset=offset)
        resp = self._request("GET", "/models", params=params)
        models = [Model3D.model_validate(x) for x in resp.json()]
        if mine:
            me = self.whoami()
            models = [m for m in models if m.owner_id == me.id]
        return models

    def get_model(self, model_id: int) -> Model3D:
        resp = self._request("GET", f"/models/{model_id}")
        return Model3D.model_validate(resp.json())

    def upload_model(self, file: Path, title: str, description="", category=None,
                     tags=None, price_eur=None, thumbnail=None) -> Model3D:
        file = Path(file)
        data = {"title": title, "description": description}
        if category is not None:
            data["category"] = category
        if tags:
            data["tags"] = ",".join(tags)
        if price_eur is not None:
            data["price_eur"] = str(price_eur)
        files = {"file": (file.name, file.read_bytes())}
        if thumbnail is not None:
            thumbnail = Path(thumbnail)
            files["thumbnail"] = (thumbnail.name, thumbnail.read_bytes())
        resp = self._request("POST", "/models", data=data, files=files)
        return Model3D.model_validate(resp.json())

    def update_model(self, model_id: int, **fields) -> Model3D:
        payload = {k: v for k, v in fields.items() if v is not None}
        resp = self._request("PATCH", f"/models/{model_id}", json=payload)
        return Model3D.model_validate(resp.json())

    def publish_model(self, model_id: int, **fields) -> Model3D:
        return self.update_model(model_id, published=True, **fields)

    def delete_model(self, model_id: int) -> None:
        self._request("DELETE", f"/models/{model_id}")

    def set_thumbnail(self, model_id: int, image: Path) -> Model3D:
        image = Path(image)
        files = {"thumbnail": (image.name, image.read_bytes())}
        resp = self._request("POST", f"/models/{model_id}/thumbnail", files=files)
        return Model3D.model_validate(resp.json())

    def download_model(self, model_id: int, dest: Path) -> Path:
        dest = Path(dest)
        with self._http.stream("GET", f"/models/{model_id}/download") as r:
            if r.status_code >= 400:
                r.read()
                self._request("GET", f"/models/{model_id}/download")  # levanta error tipado
            dest.write_bytes(r.read())
        return dest
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_api_models.py -v`
Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add murray3d/api.py tests/test_api_models.py
git commit -m "feat: métodos de modelos en el cliente API (listar/subir/editar/publicar/borrar/miniatura/descarga)"
```

---

### Task 5: Cliente API — packs y config (`api.py` parte 3)

**Files:**
- Modify: `murray3d/api.py`
- Test: `tests/test_api_packs.py`

**Interfaces:**
- Consumes: Task 3-4 (`Client`), `Pack`.
- Produces (métodos de `Client`):
  - `list_packs(self, q=None, limit=100, offset=0) -> list[Pack]` → `GET /packs`.
  - `get_pack(self, pack_id: int) -> Pack` → `GET /packs/{id}`.
  - `create_pack(self, title, description="", tags=None, price_eur=None, cover=None, model_ids=None, published=False) -> Pack` → `POST /packs` JSON.
  - `update_pack(self, pack_id: int, **fields) -> Pack` → `PATCH /packs/{id}` JSON (solo no-None).
  - `delete_pack(self, pack_id: int) -> None` → `DELETE /packs/{id}`.
  - `add_models_to_pack(self, pack_id: int, model_ids: list[int]) -> Pack` → lee el pack, une (sin duplicados, preservando orden) y hace `update_pack(model_ids=...)`.
  - `get_config(self) -> dict` → `GET /config`.

- [ ] **Step 1: Write the failing test** `tests/test_api_packs.py`

```python
import httpx

from murray3d.api import Client
from murray3d.config import Settings


def make_settings(tmp_path):
    return Settings(base_url="https://api.test/3dbundle/api", api_key="k",
                    cache_dir=tmp_path / "c", shots_dir=tmp_path / "s",
                    known_categories=["both"])


def test_create_pack(tmp_path):
    seen = {}

    def handler(request):
        seen["json"] = request.read().decode()
        return httpx.Response(200, json={"id": 3, "title": "Pack", "model_ids": [1, 2]})

    c = Client(make_settings(tmp_path), transport=httpx.MockTransport(handler))
    p = c.create_pack("Pack", model_ids=[1, 2])
    assert p.id == 3 and p.model_ids == [1, 2]
    assert "Pack" in seen["json"]


def test_add_models_to_pack_merges_without_dupes(tmp_path):
    state = {"model_ids": [1, 2]}
    calls = []

    def handler(request):
        calls.append(request.method)
        if request.method == "GET":
            return httpx.Response(200, json={"id": 3, "title": "P", "model_ids": state["model_ids"]})
        # PATCH
        body = request.read().decode()
        import json
        state["model_ids"] = json.loads(body)["model_ids"]
        return httpx.Response(200, json={"id": 3, "title": "P", "model_ids": state["model_ids"]})

    c = Client(make_settings(tmp_path), transport=httpx.MockTransport(handler))
    p = c.add_models_to_pack(3, [2, 5, 7])
    assert p.model_ids == [1, 2, 5, 7]
    assert calls == ["GET", "PATCH"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_api_packs.py -v`
Expected: FAIL con `AttributeError: 'Client' object has no attribute 'create_pack'`.

- [ ] **Step 3: Add pack/config methods to `murray3d/api.py`**

```python
    def list_packs(self, q=None, limit=100, offset=0) -> list[Pack]:
        resp = self._request("GET", "/packs", params=self._params(q=q, limit=limit, offset=offset))
        return [Pack.model_validate(x) for x in resp.json()]

    def get_pack(self, pack_id: int) -> Pack:
        resp = self._request("GET", f"/packs/{pack_id}")
        return Pack.model_validate(resp.json())

    def create_pack(self, title, description="", tags=None, price_eur=None,
                    cover=None, model_ids=None, published=False) -> Pack:
        payload = {
            "title": title,
            "description": description,
            "tags": tags or [],
            "model_ids": model_ids or [],
            "published": published,
        }
        if price_eur is not None:
            payload["price_eur"] = price_eur
        if cover is not None:
            payload["cover"] = cover
        resp = self._request("POST", "/packs", json=payload)
        return Pack.model_validate(resp.json())

    def update_pack(self, pack_id: int, **fields) -> Pack:
        payload = {k: v for k, v in fields.items() if v is not None}
        resp = self._request("PATCH", f"/packs/{pack_id}", json=payload)
        return Pack.model_validate(resp.json())

    def delete_pack(self, pack_id: int) -> None:
        self._request("DELETE", f"/packs/{pack_id}")

    def add_models_to_pack(self, pack_id: int, model_ids: list[int]) -> Pack:
        pack = self.get_pack(pack_id)
        merged = list(pack.model_ids)
        for mid in model_ids:
            if mid not in merged:
                merged.append(mid)
        return self.update_pack(pack_id, model_ids=merged)

    def get_config(self) -> dict:
        resp = self._request("GET", "/config")
        return resp.json()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_api_packs.py -v`
Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add murray3d/api.py tests/test_api_packs.py
git commit -m "feat: métodos de packs y config en el cliente API"
```

---

### Task 6: Conversión de modelos a glTF (`convert.py`)

**Files:**
- Create: `murray3d/convert.py`
- Test: `tests/test_convert.py`

**Interfaces:**
- Consumes: nada del proyecto (usa `trimesh`).
- Produces:
  - `murray3d.convert.ensure_glb(src: Path, cache_dir: Path) -> Path` — si `src` es `.glb`/`.gltf`, lo devuelve tal cual; si es `.obj`/`.stl`, lo convierte con trimesh a un `.glb` en `cache_dir` (nombre = `<stem>-<size>-<mtime_ns>.glb`) y cachea (no reconvierte si ya existe). Lanza `ConvertError` para extensiones no soportadas o mallas ilegibles.
  - `murray3d.convert.ConvertError(Exception)`.

- [ ] **Step 1: Write the failing test** `tests/test_convert.py`

```python
from pathlib import Path

import numpy as np
import pytest
import trimesh

from murray3d.convert import ConvertError, ensure_glb


def _write_stl(path: Path):
    mesh = trimesh.creation.box(extents=(1, 1, 1))
    mesh.export(path)


def test_glb_passthrough(tmp_path):
    glb = tmp_path / "a.glb"
    glb.write_bytes(b"glTF-fake")
    assert ensure_glb(glb, tmp_path / "cache") == glb


def test_stl_converted_to_glb(tmp_path):
    stl = tmp_path / "box.stl"
    _write_stl(stl)
    cache = tmp_path / "cache"
    out = ensure_glb(stl, cache)
    assert out.suffix == ".glb"
    assert out.parent == cache
    assert out.stat().st_size > 0
    scene = trimesh.load(out)
    assert scene is not None


def test_conversion_is_cached(tmp_path):
    stl = tmp_path / "box.stl"
    _write_stl(stl)
    cache = tmp_path / "cache"
    out1 = ensure_glb(stl, cache)
    mtime1 = out1.stat().st_mtime_ns
    out2 = ensure_glb(stl, cache)
    assert out2 == out1
    assert out2.stat().st_mtime_ns == mtime1


def test_unsupported_extension_raises(tmp_path):
    bad = tmp_path / "x.txt"
    bad.write_text("hi")
    with pytest.raises(ConvertError):
        ensure_glb(bad, tmp_path / "cache")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_convert.py -v`
Expected: FAIL con `ModuleNotFoundError: No module named 'murray3d.convert'`.

- [ ] **Step 3: Write `murray3d/convert.py`**

```python
from __future__ import annotations

from pathlib import Path

import trimesh


class ConvertError(Exception):
    pass


_PASSTHROUGH = {".glb", ".gltf"}
_CONVERTIBLE = {".obj", ".stl"}


def ensure_glb(src: Path, cache_dir: Path) -> Path:
    src = Path(src)
    ext = src.suffix.lower()
    if ext in _PASSTHROUGH:
        return src
    if ext not in _CONVERTIBLE:
        raise ConvertError(f"Extensión no soportada para render: {ext}")

    cache_dir = Path(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    st = src.stat()
    out = cache_dir / f"{src.stem}-{st.st_size}-{st.st_mtime_ns}.glb"
    if out.exists():
        return out

    try:
        mesh = trimesh.load(src, force="scene")
        mesh.export(out, file_type="glb")
    except Exception as e:  # noqa: BLE001
        raise ConvertError(f"No se pudo convertir {src.name} a glb: {e}") from e
    if not out.exists() or out.stat().st_size == 0:
        raise ConvertError(f"Conversión vacía para {src.name}")
    return out
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_convert.py -v`
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add murray3d/convert.py tests/test_convert.py
git commit -m "feat: conversión obj/stl -> glb con caché (trimesh)"
```

---

### Task 7: Assets del visor (`gui/assets/viewer.html` + model-viewer)

**Files:**
- Create: `murray3d/gui/__init__.py`
- Create: `murray3d/gui/assets/viewer.html`
- Create: `murray3d/gui/assets/download_model_viewer.py` (script de descarga del vendor)
- Create: `murray3d/gui/assets/model-viewer.min.js` (descargado por el script)
- Test: `tests/test_assets.py`

**Interfaces:**
- Consumes: nada.
- Produces:
  - Fichero `murray3d/gui/assets/model-viewer.min.js` presente y no vacío.
  - `viewer.html` que carga el JS local y define un `<model-viewer id="mv" camera-controls>` cuyo `src` se fija vía query param `?src=` o mensaje JS, y expone una función global `window.captureOrbit(theta, phi, radius)` que fija `camera-orbit` y devuelve `mv.toDataURL('image/png')` tras el render. Usado por `render.py` (Playwright) y por `viewer.py` (QWebEngineView).

- [ ] **Step 1: Write the download script** `murray3d/gui/assets/download_model_viewer.py`

```python
"""Descarga model-viewer.min.js (self-contained) al directorio de assets.

Ejecutar una sola vez: `python -m murray3d.gui.assets.download_model_viewer`
"""
from __future__ import annotations

from pathlib import Path

import httpx

URL = "https://unpkg.com/@google/model-viewer@3.5.0/dist/model-viewer.min.js"
DEST = Path(__file__).resolve().parent / "model-viewer.min.js"


def main() -> None:
    print(f"Descargando {URL} ...")
    r = httpx.get(URL, follow_redirects=True, timeout=60)
    r.raise_for_status()
    DEST.write_bytes(r.content)
    print(f"Guardado en {DEST} ({DEST.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run the download script**

Run: `python -m murray3d.gui.assets.download_model_viewer`
Expected: imprime "Guardado en .../model-viewer.min.js (N bytes)" con N > 100000.
(Crea también `murray3d/gui/__init__.py` vacío y `murray3d/gui/assets/__init__.py` vacío antes si es necesario para el `-m`.)

- [ ] **Step 3: Write `murray3d/gui/assets/viewer.html`**

```html
<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<style>
  html, body { margin: 0; height: 100%; background: #1b1d22; }
  model-viewer { width: 100vw; height: 100vh; --poster-color: transparent; }
</style>
<script type="module" src="./model-viewer.min.js"></script>
</head>
<body>
<model-viewer id="mv" camera-controls interaction-prompt="none"
              shadow-intensity="1" exposure="1" environment-image="neutral"></model-viewer>
<script>
  const mv = document.getElementById('mv');
  const params = new URLSearchParams(location.search);
  const src = params.get('src');
  if (src) mv.src = src;

  window.setModelSrc = (s) => { mv.src = s; };

  // Espera a que el modelo cargue.
  window.modelReady = new Promise((resolve) => {
    mv.addEventListener('load', () => resolve(true), { once: true });
  });

  // Fija la cámara y captura un PNG. theta/phi en grados, radius en metros o 'auto'.
  window.captureOrbit = async (theta, phi, radius) => {
    mv.cameraOrbit = `${theta}deg ${phi}deg ${radius}`;
    mv.jumpCameraToGoal ? mv.jumpCameraToGoal() : null;
    await new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r)));
    return mv.toDataURL('image/png');
  };
</script>
</body>
</html>
```

- [ ] **Step 4: Write the failing test** `tests/test_assets.py`

```python
from pathlib import Path

ASSETS = Path(__file__).resolve().parent.parent / "murray3d" / "gui" / "assets"


def test_model_viewer_present_and_nonempty():
    js = ASSETS / "model-viewer.min.js"
    assert js.exists(), "Ejecuta: python -m murray3d.gui.assets.download_model_viewer"
    assert js.stat().st_size > 100_000


def test_viewer_html_references_local_js_and_capture():
    html = (ASSETS / "viewer.html").read_text()
    assert "./model-viewer.min.js" in html
    assert "captureOrbit" in html
    assert "window.modelReady" in html
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/test_assets.py -v`
Expected: 2 passed.

- [ ] **Step 6: Commit**

```bash
git add murray3d/gui/__init__.py murray3d/gui/assets/ tests/test_assets.py
git commit -m "feat: assets del visor (model-viewer local + viewer.html con captureOrbit)"
```

---

### Task 8: Renderizado de pantallazos (`render.py`)

**Files:**
- Create: `murray3d/render.py`
- Test: `tests/test_render.py`

**Interfaces:**
- Consumes: `murray3d.convert.ensure_glb`, assets de Task 7.
- Produces:
  - `murray3d.render.DEFAULT_ANGLES: list[tuple[float,float,str]]` — 6 órbitas (theta, phi, radius) representativas.
  - `murray3d.render.RenderError(Exception)`.
  - `murray3d.render.render_screenshots(model_path: Path, out_dir: Path, cache_dir: Path, angles=None) -> list[Path]` — convierte a glb si hace falta, lanza Chromium (Playwright), carga `viewer.html?src=<file url>`, espera `window.modelReady`, y para cada ángulo llama `captureOrbit` y guarda `shot_00.png ...`. Devuelve rutas ordenadas. Marca de test: `@pytest.mark.integration`.

- [ ] **Step 1: Write `murray3d/render.py`**

```python
from __future__ import annotations

import base64
from pathlib import Path

from .convert import ensure_glb

RenderError = type("RenderError", (Exception,), {})

ASSETS = Path(__file__).resolve().parent / "gui" / "assets"
VIEWER_HTML = ASSETS / "viewer.html"

# (theta_deg, phi_deg, radius)
DEFAULT_ANGLES: list[tuple[float, float, str]] = [
    (0, 75, "auto"),      # frente
    (45, 70, "auto"),     # 3/4 derecha
    (90, 80, "auto"),     # lateral derecho
    (-45, 70, "auto"),    # 3/4 izquierda
    (180, 80, "auto"),    # atrás
    (25, 25, "auto"),     # picado
]


def render_screenshots(model_path: Path, out_dir: Path, cache_dir: Path,
                        angles=None) -> list[Path]:
    from playwright.sync_api import sync_playwright  # import perezoso

    angles = angles or DEFAULT_ANGLES
    model_path = Path(model_path)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    glb = ensure_glb(model_path, cache_dir)

    file_url = VIEWER_HTML.as_uri() + "?src=" + glb.resolve().as_uri()
    results: list[Path] = []
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(args=["--no-sandbox"])
            page = browser.new_page(viewport={"width": 1024, "height": 1024},
                                    device_scale_factor=2)
            page.goto(file_url, wait_until="load")
            page.wait_for_function("window.modelReady !== undefined")
            page.evaluate("window.modelReady")
            page.wait_for_timeout(500)
            for i, (theta, phi, radius) in enumerate(angles):
                data_url = page.evaluate(
                    "([t,p,r]) => window.captureOrbit(t,p,r)", [theta, phi, radius]
                )
                header, b64 = data_url.split(",", 1)
                dest = out_dir / f"shot_{i:02d}.png"
                dest.write_bytes(base64.b64decode(b64))
                results.append(dest)
            browser.close()
    except Exception as e:  # noqa: BLE001
        raise RenderError(f"Fallo al renderizar {model_path.name}: {e}") from e
    if not results:
        raise RenderError("No se generó ningún pantallazo")
    return results
```

- [ ] **Step 2: Write the integration test** `tests/test_render.py`

```python
from pathlib import Path

import pytest
import trimesh

from murray3d.render import render_screenshots


@pytest.mark.integration
def test_render_produces_pngs(tmp_path):
    glb = tmp_path / "box.glb"
    trimesh.creation.box(extents=(1, 1, 1)).export(glb)
    shots = render_screenshots(glb, tmp_path / "out", tmp_path / "cache")
    assert len(shots) == 6
    for s in shots:
        assert s.exists() and s.stat().st_size > 1000
```

- [ ] **Step 3: Install the Playwright browser and run the integration test**

Run:
```bash
python -m playwright install chromium
python -m pytest tests/test_render.py -v -m integration
```
Expected: 1 passed (genera 6 PNG no vacíos).

- [ ] **Step 4: Verify the default suite still ignores the integration test**

Run: `python -m pytest tests/test_render.py -v`
Expected: 1 deselected (0 ejecutados por el marcador).

- [ ] **Step 5: Commit**

```bash
git add murray3d/render.py tests/test_render.py
git commit -m "feat: render de pantallazos en órbita con Playwright + model-viewer"
```

---

### Task 9: Generación de metadatos con Claude (`ai.py`)

**Files:**
- Create: `murray3d/ai.py`
- Test: `tests/test_ai.py`

**Interfaces:**
- Consumes: `murray3d.models.GeneratedMeta`.
- Produces:
  - `murray3d.ai.AiError(Exception)`.
  - `murray3d.ai.JSON_SCHEMA: dict` — JSON Schema de `GeneratedMeta`.
  - `murray3d.ai.build_prompt(shots: list[Path], categories: list[str]) -> str`.
  - `murray3d.ai.generate_metadata(shots: list[Path], categories: list[str], runner=None) -> GeneratedMeta` — construye el prompt, ejecuta `claude` (o `runner` inyectable para test) y parsea. `runner(cmd: list[str], cwd: Path) -> str` devuelve el stdout JSON de `claude --output-format json`. Extrae el campo `result` (texto) del wrapper de Claude, parsea el JSON interno a `GeneratedMeta`, y fuerza `category` a una de `categories` (si no coincide, usa la primera).
  - `murray3d.ai.default_runner(cmd, cwd) -> str` — ejecuta con `subprocess.run`, `check=True`, captura stdout.

- [ ] **Step 1: Write the failing test** `tests/test_ai.py`

```python
import json
from pathlib import Path

import pytest

from murray3d.ai import AiError, build_prompt, generate_metadata


def test_build_prompt_mentions_shots_and_categories(tmp_path):
    shots = [tmp_path / "shot_00.png", tmp_path / "shot_01.png"]
    prompt = build_prompt(shots, ["figures", "both"])
    assert "shot_00.png" in prompt
    assert "figures" in prompt and "both" in prompt


def test_generate_metadata_parses_claude_wrapper(tmp_path):
    inner = {"title": "Dragón alado", "description": "Una figura detallada.",
             "tags": ["dragón", "fantasía"], "category": "both",
             "price_eur": 4.5, "best_thumbnail_index": 2}
    wrapper = {"type": "result", "result": json.dumps(inner), "is_error": False}

    def fake_runner(cmd, cwd):
        assert "claude" in cmd[0]
        assert "-p" in cmd
        return json.dumps(wrapper)

    shots = [tmp_path / f"shot_{i:02d}.png" for i in range(3)]
    for s in shots:
        s.write_bytes(b"png")
    meta = generate_metadata(shots, ["figures", "scenery", "both"], runner=fake_runner)
    assert meta.title == "Dragón alado"
    assert meta.best_thumbnail_index == 2
    assert meta.category == "both"


def test_category_forced_into_allowed_set(tmp_path):
    inner = {"title": "T", "description": "D", "tags": [], "category": "inventada",
             "best_thumbnail_index": 0}
    wrapper = {"result": json.dumps(inner)}
    shots = [tmp_path / "shot_00.png"]
    shots[0].write_bytes(b"png")
    meta = generate_metadata(shots, ["figures", "both"], runner=lambda c, w: json.dumps(wrapper))
    assert meta.category == "figures"


def test_bad_json_raises(tmp_path):
    shots = [tmp_path / "shot_00.png"]
    shots[0].write_bytes(b"png")
    with pytest.raises(AiError):
        generate_metadata(shots, ["both"], runner=lambda c, w: "no-json")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_ai.py -v`
Expected: FAIL con `ModuleNotFoundError: No module named 'murray3d.ai'`.

- [ ] **Step 3: Write `murray3d/ai.py`**

```python
from __future__ import annotations

import json
import subprocess
from pathlib import Path

from .models import GeneratedMeta


class AiError(Exception):
    pass


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


def default_runner(cmd: list[str], cwd: Path) -> str:
    proc = subprocess.run(cmd, cwd=str(cwd), capture_output=True, text=True, check=True)
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


def generate_metadata(shots: list[Path], categories: list[str], runner=None) -> GeneratedMeta:
    if not shots:
        raise AiError("No hay pantallazos para analizar")
    runner = runner or default_runner
    shots_dir = Path(shots[0]).resolve().parent
    schema_file = shots_dir / "_schema.json"
    schema_file.write_text(json.dumps(JSON_SCHEMA))
    prompt = build_prompt(shots, categories)
    cmd = [
        "claude", "-p", prompt,
        "--output-format", "json",
        "--json-schema", str(schema_file),
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_ai.py -v`
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add murray3d/ai.py tests/test_ai.py
git commit -m "feat: generación de metadatos vía claude CLI headless (ai.py)"
```

---

### Task 10: Orquestación de publicación (`publish.py`)

**Files:**
- Create: `murray3d/publish.py`
- Test: `tests/test_publish.py`

**Interfaces:**
- Consumes: `Client`, `render.render_screenshots`, `ai.generate_metadata`, `GeneratedMeta`, `Model3D`, `Settings`.
- Produces:
  - `murray3d.publish.prepare_publish(client, settings, model_id, angles=None, render_fn=None, ai_fn=None) -> tuple[GeneratedMeta, list[Path]]` — descarga el modelo (`client.download_model`), renderiza pantallazos (`render_fn` o `render.render_screenshots`) y genera metadatos (`ai_fn` o `ai.generate_metadata`). `render_fn`/`ai_fn` inyectables para test. Los pantallazos van a `settings.shots_dir / str(model_id)`.
  - `murray3d.publish.commit_publish(client, model_id, meta: GeneratedMeta, shots: list[Path], thumbnail_index: int | None = None) -> Model3D` — hace `client.publish_model(model_id, title=..., description=..., category=..., tags=..., price_eur=...)` y luego `client.set_thumbnail(model_id, shots[idx])` con `idx = thumbnail_index if not None else meta.best_thumbnail_index`. Devuelve el modelo actualizado.

- [ ] **Step 1: Write the failing test** `tests/test_publish.py`

```python
from pathlib import Path
from unittest.mock import MagicMock

from murray3d.config import Settings
from murray3d.models import GeneratedMeta, Model3D
from murray3d.publish import commit_publish, prepare_publish


def make_settings(tmp_path):
    return Settings(base_url="https://x/3dbundle/api", api_key="k",
                    cache_dir=tmp_path / "c", shots_dir=tmp_path / "s",
                    known_categories=["figures", "both"])


def test_prepare_publish_wires_render_and_ai(tmp_path):
    settings = make_settings(tmp_path)
    client = MagicMock()
    client.download_model.return_value = tmp_path / "m.glb"
    shots = [tmp_path / "shot_00.png", tmp_path / "shot_01.png"]
    meta = GeneratedMeta(title="T", description="D", tags=["a"], category="both",
                         best_thumbnail_index=1)

    render_fn = MagicMock(return_value=shots)
    ai_fn = MagicMock(return_value=meta)
    got_meta, got_shots = prepare_publish(client, settings, 9,
                                          render_fn=render_fn, ai_fn=ai_fn)
    assert got_meta is meta and got_shots == shots
    client.download_model.assert_called_once()
    render_fn.assert_called_once()
    ai_fn.assert_called_once_with(shots, settings.known_categories)


def test_commit_publish_calls_patch_and_thumbnail(tmp_path):
    client = MagicMock()
    client.publish_model.return_value = Model3D(id=9, title="T", published=True)
    shots = [tmp_path / "shot_00.png", tmp_path / "shot_01.png"]
    meta = GeneratedMeta(title="T", description="D", tags=["a", "b"],
                         category="both", price_eur=3.0, best_thumbnail_index=1)
    out = commit_publish(client, 9, meta, shots)
    assert out.published is True
    kwargs = client.publish_model.call_args.kwargs
    assert kwargs["title"] == "T" and kwargs["category"] == "both"
    assert kwargs["tags"] == ["a", "b"] and kwargs["price_eur"] == 3.0
    client.set_thumbnail.assert_called_once_with(9, shots[1])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_publish.py -v`
Expected: FAIL con `ModuleNotFoundError: No module named 'murray3d.publish'`.

- [ ] **Step 3: Write `murray3d/publish.py`**

```python
from __future__ import annotations

from pathlib import Path

from .ai import generate_metadata
from .models import GeneratedMeta, Model3D
from .render import render_screenshots


def prepare_publish(client, settings, model_id, angles=None,
                    render_fn=None, ai_fn=None) -> tuple[GeneratedMeta, list[Path]]:
    render_fn = render_fn or render_screenshots
    ai_fn = ai_fn or generate_metadata

    model = client.get_model(model_id)
    ext = (model.file_format or "glb").lstrip(".")
    work = settings.shots_dir / str(model_id)
    work.mkdir(parents=True, exist_ok=True)
    src = client.download_model(model_id, work / f"model.{ext}")
    shots = render_fn(src, work, settings.cache_dir, angles) if angles is not None \
        else render_fn(src, work, settings.cache_dir)
    meta = ai_fn(shots, settings.known_categories)
    return meta, shots


def commit_publish(client, model_id, meta: GeneratedMeta, shots: list[Path],
                   thumbnail_index: int | None = None) -> Model3D:
    updated = client.publish_model(
        model_id,
        title=meta.title,
        description=meta.description,
        category=meta.category,
        tags=meta.tags,
        price_eur=meta.price_eur,
    )
    idx = thumbnail_index if thumbnail_index is not None else meta.best_thumbnail_index
    if shots and 0 <= idx < len(shots):
        client.set_thumbnail(model_id, shots[idx])
    return updated
```

Nota: el test `test_prepare_publish_wires_render_and_ai` no pasa `angles`, por lo que se usa la rama sin `angles`; ajusta la firma de `render_fn` mock en consecuencia (el mock acepta cualquier args). Para que `render_fn.assert_called_once` no dependa de `angles`, la implementación llama `render_fn(src, work, settings.cache_dir)` cuando `angles is None`.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_publish.py -v`
Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add murray3d/publish.py tests/test_publish.py
git commit -m "feat: orquestación de publicación (prepare/commit)"
```

---

### Task 11: CLI (`cli.py`)

**Files:**
- Create: `murray3d/cli.py`
- Test: `tests/test_cli.py`

**Interfaces:**
- Consumes: todo el núcleo (`config`, `api`, `publish`).
- Produces:
  - `murray3d.cli.app` (typer.Typer) con subcomandos: `whoami`, `models list/show/upload/edit/delete/thumbnail`, `packs list/show/create/edit/delete add-model`, `render`, `ai-generate`, `publish`, `ai-publish`, y `gui` (lanza la GUI; ver Task 15).
  - Helper `murray3d.cli._client() -> Client` que carga settings y crea el cliente (inyectable en tests vía monkeypatch de `cli._client`).
  - Salida `--json` en los comandos de consulta.

- [ ] **Step 1: Write the failing test** `tests/test_cli.py`

```python
import json

from typer.testing import CliRunner

import murray3d.cli as cli
from murray3d.models import Model3D

runner = CliRunner()


def test_models_list_json(monkeypatch):
    fake = type("C", (), {})()
    fake.list_models = lambda **kw: [Model3D(id=1, title="A", published=True)]
    fake.close = lambda: None
    monkeypatch.setattr(cli, "_client", lambda: fake)

    result = runner.invoke(cli.app, ["models", "list", "--json"])
    assert result.exit_code == 0
    data = json.loads(result.stdout)
    assert data[0]["id"] == 1


def test_models_delete(monkeypatch):
    calls = {}
    fake = type("C", (), {})()
    fake.delete_model = lambda mid: calls.setdefault("del", mid)
    fake.close = lambda: None
    monkeypatch.setattr(cli, "_client", lambda: fake)

    result = runner.invoke(cli.app, ["models", "delete", "5", "--yes"])
    assert result.exit_code == 0
    assert calls["del"] == 5


def test_whoami_error_exit_code(monkeypatch):
    from murray3d.api import AuthError

    def boom():
        raise AuthError(401, "sin clave")

    fake = type("C", (), {})()
    fake.whoami = boom
    fake.close = lambda: None
    monkeypatch.setattr(cli, "_client", lambda: fake)

    result = runner.invoke(cli.app, ["whoami"])
    assert result.exit_code != 0
    assert "sin clave" in result.stdout
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_cli.py -v`
Expected: FAIL con `ModuleNotFoundError: No module named 'murray3d.cli'`.

- [ ] **Step 3: Write `murray3d/cli.py`**

```python
from __future__ import annotations

import json as _json
from pathlib import Path

import typer

from .api import ApiError, Client
from .config import ConfigError, load_settings

app = typer.Typer(help="Cliente local de 3DBundle")
models_app = typer.Typer(help="Gestión de modelos")
packs_app = typer.Typer(help="Gestión de packs")
app.add_typer(models_app, name="models")
app.add_typer(packs_app, name="packs")


def _client() -> Client:
    return Client(load_settings())


def _dump(obj) -> None:
    typer.echo(_json.dumps(obj, ensure_ascii=False, indent=2))


def _run(fn):
    try:
        return fn()
    except (ApiError, ConfigError) as e:
        typer.echo(str(e))
        raise typer.Exit(code=1)


@app.command()
def whoami():
    c = _client()
    prof = _run(c.whoami)
    _dump(prof.model_dump())
    c.close()


@models_app.command("list")
def models_list(q: str = None, tag: str = None, category: str = None,
                mine: bool = False, published: bool = typer.Option(None, "--published/--all"),
                limit: int = 100, json_out: bool = typer.Option(False, "--json")):
    c = _client()
    items = _run(lambda: c.list_models(q=q, tag=tag, category=category,
                                       only_published=published, mine=mine, limit=limit))
    if json_out:
        _dump([m.model_dump() for m in items])
    else:
        for m in items:
            flag = "✔" if m.published else "·"
            typer.echo(f"{flag} [{m.id}] {m.title}  ({m.category or '-'})")
    c.close()


@models_app.command("show")
def models_show(model_id: int):
    c = _client()
    m = _run(lambda: c.get_model(model_id))
    _dump(m.model_dump())
    c.close()


@models_app.command("upload")
def models_upload(file: Path, title: str, description: str = "", category: str = None,
                  tags: str = "", price: float = None):
    c = _client()
    tag_list = [t.strip() for t in tags.split(",") if t.strip()]
    m = _run(lambda: c.upload_model(file, title=title, description=description,
                                    category=category, tags=tag_list, price_eur=price))
    _dump(m.model_dump())
    c.close()


@models_app.command("edit")
def models_edit(model_id: int, title: str = None, description: str = None,
                category: str = None, tags: str = None, price: float = None,
                published: bool = typer.Option(None, "--published/--unpublished")):
    c = _client()
    fields = {}
    if title is not None: fields["title"] = title
    if description is not None: fields["description"] = description
    if category is not None: fields["category"] = category
    if tags is not None: fields["tags"] = [t.strip() for t in tags.split(",") if t.strip()]
    if price is not None: fields["price_eur"] = price
    if published is not None: fields["published"] = published
    m = _run(lambda: c.update_model(model_id, **fields))
    _dump(m.model_dump())
    c.close()


@models_app.command("delete")
def models_delete(model_id: int, yes: bool = typer.Option(False, "--yes")):
    if not yes:
        typer.confirm(f"¿Borrar el modelo {model_id}?", abort=True)
    c = _client()
    _run(lambda: c.delete_model(model_id))
    typer.echo(f"Borrado {model_id}")
    c.close()


@models_app.command("thumbnail")
def models_thumbnail(model_id: int, image: Path):
    c = _client()
    m = _run(lambda: c.set_thumbnail(model_id, image))
    _dump(m.model_dump())
    c.close()


@packs_app.command("list")
def packs_list(q: str = None, json_out: bool = typer.Option(False, "--json")):
    c = _client()
    items = _run(lambda: c.list_packs(q=q))
    if json_out:
        _dump([p.model_dump() for p in items])
    else:
        for p in items:
            typer.echo(f"[{p.id}] {p.title}  ({len(p.model_ids)} modelos)")
    c.close()


@packs_app.command("show")
def packs_show(pack_id: int):
    c = _client()
    _dump(_run(lambda: c.get_pack(pack_id)).model_dump())
    c.close()


@packs_app.command("create")
def packs_create(title: str, description: str = "", tags: str = "",
                 price: float = None, model_ids: str = ""):
    c = _client()
    tag_list = [t.strip() for t in tags.split(",") if t.strip()]
    ids = [int(x) for x in model_ids.split(",") if x.strip()]
    p = _run(lambda: c.create_pack(title, description=description, tags=tag_list,
                                   price_eur=price, model_ids=ids))
    _dump(p.model_dump())
    c.close()


@packs_app.command("edit")
def packs_edit(pack_id: int, title: str = None, description: str = None,
               tags: str = None, price: float = None,
               published: bool = typer.Option(None, "--published/--unpublished")):
    c = _client()
    fields = {}
    if title is not None: fields["title"] = title
    if description is not None: fields["description"] = description
    if tags is not None: fields["tags"] = [t.strip() for t in tags.split(",") if t.strip()]
    if price is not None: fields["price_eur"] = price
    if published is not None: fields["published"] = published
    _dump(_run(lambda: c.update_pack(pack_id, **fields)).model_dump())
    c.close()


@packs_app.command("delete")
def packs_delete(pack_id: int, yes: bool = typer.Option(False, "--yes")):
    if not yes:
        typer.confirm(f"¿Borrar el pack {pack_id}?", abort=True)
    c = _client()
    _run(lambda: c.delete_pack(pack_id))
    typer.echo(f"Borrado pack {pack_id}")
    c.close()


@packs_app.command("add-model")
def packs_add_model(pack_id: int, model_ids: list[int]):
    c = _client()
    p = _run(lambda: c.add_models_to_pack(pack_id, list(model_ids)))
    _dump(p.model_dump())
    c.close()


@app.command()
def render(model_id: int, out: Path = None, angles: int = None):
    from .render import render_screenshots
    c = _client()
    settings = c.settings
    m = _run(lambda: c.get_model(model_id))
    ext = (m.file_format or "glb").lstrip(".")
    work = out or (settings.shots_dir / str(model_id))
    Path(work).mkdir(parents=True, exist_ok=True)
    src = _run(lambda: c.download_model(model_id, Path(work) / f"model.{ext}"))
    shots = render_screenshots(src, Path(work), settings.cache_dir)
    _dump([str(s) for s in shots])
    c.close()


@app.command("ai-generate")
def ai_generate(model_id: int):
    from .publish import prepare_publish
    c = _client()
    meta, shots = _run(lambda: prepare_publish(c, c.settings, model_id))
    _dump({"meta": meta.model_dump(), "shots": [str(s) for s in shots]})
    c.close()


@app.command()
def publish(model_id: int, title: str = None, description: str = None,
            category: str = None, tags: str = None, price: float = None,
            thumbnail: Path = None):
    c = _client()
    fields = {}
    if title is not None: fields["title"] = title
    if description is not None: fields["description"] = description
    if category is not None: fields["category"] = category
    if tags is not None: fields["tags"] = [t.strip() for t in tags.split(",") if t.strip()]
    if price is not None: fields["price_eur"] = price
    m = _run(lambda: c.publish_model(model_id, **fields))
    if thumbnail is not None:
        _run(lambda: c.set_thumbnail(model_id, thumbnail))
    _dump(m.model_dump())
    c.close()


@app.command("ai-publish")
def ai_publish(model_id: int, yes: bool = typer.Option(False, "--yes")):
    from .publish import commit_publish, prepare_publish
    c = _client()
    meta, shots = _run(lambda: prepare_publish(c, c.settings, model_id))
    typer.echo(_json.dumps(meta.model_dump(), ensure_ascii=False, indent=2))
    if not yes:
        typer.confirm("¿Publicar con estos metadatos?", abort=True)
    m = _run(lambda: commit_publish(c, model_id, meta, shots))
    _dump(m.model_dump())
    c.close()


@app.command()
def gui():
    from .gui.app import run_gui
    run_gui()


if __name__ == "__main__":
    app()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_cli.py -v`
Expected: 3 passed.

- [ ] **Step 5: Verify the CLI runs end-to-end against the real API**

Run:
```bash
murray3d whoami
murray3d models list
```
Expected: `whoami` imprime el perfil (author "Muriano"); `models list` lista modelos con `[id] título`.

- [ ] **Step 6: Commit**

```bash
git add murray3d/cli.py tests/test_cli.py
git commit -m "feat: CLI typer completa (models, packs, render, ai-generate, publish, ai-publish, gui)"
```

---

### Task 12: GUI — visor 3D embebido (`gui/viewer.py`)

**Files:**
- Create: `murray3d/gui/viewer.py`
- Test: `tests/test_gui_viewer.py`

**Interfaces:**
- Consumes: assets de Task 7, `murray3d.convert.ensure_glb`.
- Produces:
  - `murray3d.gui.viewer.ModelViewer(QWidget)` — envuelve un `QWebEngineView` que carga `viewer.html`. Método `show_model(self, path: Path, cache_dir: Path)` que convierte a glb si hace falta y ejecuta `window.setModelSrc('<file url>')`. Import de PySide6 perezoso dentro del módulo para no romper entornos sin display en tests que no la usan.
  - `murray3d.gui.viewer.ASSETS_DIR: Path`, `VIEWER_HTML: Path` (constantes reutilizables).

- [ ] **Step 1: Write the failing test** `tests/test_gui_viewer.py`

```python
from pathlib import Path

from murray3d.gui.viewer import ASSETS_DIR, VIEWER_HTML


def test_viewer_paths_exist():
    assert VIEWER_HTML.exists()
    assert (ASSETS_DIR / "model-viewer.min.js").exists()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_gui_viewer.py -v`
Expected: FAIL con `ModuleNotFoundError: No module named 'murray3d.gui.viewer'`.

- [ ] **Step 3: Write `murray3d/gui/viewer.py`**

```python
from __future__ import annotations

from pathlib import Path

from ..convert import ensure_glb

ASSETS_DIR = Path(__file__).resolve().parent / "assets"
VIEWER_HTML = ASSETS_DIR / "viewer.html"


def _qt():
    from PySide6.QtWebEngineWidgets import QWebEngineView
    from PySide6.QtWidgets import QVBoxLayout, QWidget
    return QWidget, QVBoxLayout, QWebEngineView


def build_viewer_widget():
    QWidget, QVBoxLayout, QWebEngineView = _qt()

    class ModelViewer(QWidget):
        def __init__(self, parent=None):
            super().__init__(parent)
            self._web = QWebEngineView(self)
            layout = QVBoxLayout(self)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.addWidget(self._web)
            self._web.load(_file_url(VIEWER_HTML))

        def show_model(self, path: Path, cache_dir: Path) -> None:
            glb = ensure_glb(Path(path), cache_dir)
            url = _file_url(glb)
            self._web.page().runJavaScript(f"window.setModelSrc({url.toString()!r})")

    return ModelViewer


def _file_url(path: Path):
    from PySide6.QtCore import QUrl
    return QUrl.fromLocalFile(str(Path(path).resolve()))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_gui_viewer.py -v`
Expected: 1 passed.

- [ ] **Step 5: Commit**

```bash
git add murray3d/gui/viewer.py tests/test_gui_viewer.py
git commit -m "feat: widget visor 3D embebido (QWebEngineView + model-viewer)"
```

---

### Task 13: GUI — gestor de modelos (`gui/models_view.py`)

**Files:**
- Create: `murray3d/gui/models_view.py`
- Create: `murray3d/gui/workers.py`
- Test: `tests/test_gui_workers.py`

**Interfaces:**
- Consumes: `Client`, `Model3D`, `viewer.build_viewer_widget`, `publish` (para el diálogo, Task 14).
- Produces:
  - `murray3d.gui.workers.Worker(QRunnable)` genérico: ejecuta una función en un hilo (`QThreadPool`) y emite `finished(object)` / `failed(str)` vía `WorkerSignals(QObject)`. Import de PySide6 perezoso; función pura `run_callable(fn) -> tuple[bool, object]` testeable sin Qt.
  - `murray3d.gui.models_view.build_models_view(client, settings)` → devuelve un `QWidget` con: barra de búsqueda, botón "Subir", rejilla/lista de modelos (id, título, estado, miniatura si hay), panel derecho con visor 3D y formulario de edición, y botones "Guardar", "Borrar", "Miniatura…", "Publicar con IA". Las llamadas de red van por `Worker` para no bloquear la UI.

- [ ] **Step 1: Write the failing test** `tests/test_gui_workers.py`

```python
from murray3d.gui.workers import run_callable


def test_run_callable_success():
    ok, value = run_callable(lambda: 40 + 2)
    assert ok is True and value == 42


def test_run_callable_captures_exception():
    def boom():
        raise ValueError("nope")

    ok, value = run_callable(boom)
    assert ok is False
    assert isinstance(value, str) and "nope" in value
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_gui_workers.py -v`
Expected: FAIL con `ModuleNotFoundError: No module named 'murray3d.gui.workers'`.

- [ ] **Step 3: Write `murray3d/gui/workers.py`**

```python
from __future__ import annotations

import traceback


def run_callable(fn):
    """Ejecuta fn() y devuelve (ok, resultado_o_mensaje_error). Sin dependencia de Qt."""
    try:
        return True, fn()
    except Exception as e:  # noqa: BLE001
        return False, f"{e}\n{traceback.format_exc()}"


def make_worker(fn):
    """Crea un QRunnable que ejecuta fn en un hilo y emite señales. Import Qt perezoso."""
    from PySide6.QtCore import QObject, QRunnable, Signal, Slot

    class WorkerSignals(QObject):
        finished = Signal(object)
        failed = Signal(str)

    class Worker(QRunnable):
        def __init__(self):
            super().__init__()
            self.signals = WorkerSignals()

        @Slot()
        def run(self):
            ok, value = run_callable(fn)
            if ok:
                self.signals.finished.emit(value)
            else:
                self.signals.failed.emit(str(value))

    return Worker()
```

- [ ] **Step 4: Write `murray3d/gui/models_view.py`**

```python
from __future__ import annotations

from pathlib import Path

from .workers import make_worker


def build_models_view(client, settings):
    from PySide6.QtCore import Qt, QThreadPool
    from PySide6.QtWidgets import (
        QDoubleSpinBox, QFileDialog, QHBoxLayout, QLabel, QLineEdit, QListWidget,
        QListWidgetItem, QMessageBox, QPushButton, QSplitter, QTextEdit, QVBoxLayout,
        QWidget,
    )

    from .publish_dialog import open_publish_dialog
    from .viewer import build_viewer_widget

    ModelViewer = build_viewer_widget()
    pool = QThreadPool.globalInstance()

    root = QWidget()
    outer = QVBoxLayout(root)

    # --- barra superior ---
    top = QHBoxLayout()
    search = QLineEdit(); search.setPlaceholderText("Buscar modelos…")
    btn_search = QPushButton("Buscar")
    btn_upload = QPushButton("Subir modelo…")
    btn_refresh = QPushButton("Recargar")
    top.addWidget(search); top.addWidget(btn_search)
    top.addStretch(); top.addWidget(btn_upload); top.addWidget(btn_refresh)
    outer.addLayout(top)

    split = QSplitter(Qt.Horizontal)
    outer.addWidget(split, 1)

    listw = QListWidget()
    split.addWidget(listw)

    right = QWidget(); rl = QVBoxLayout(right)
    viewer = ModelViewer()
    title = QLineEdit(); title.setPlaceholderText("Título")
    category = QLineEdit(); category.setPlaceholderText("Categoría")
    tags = QLineEdit(); tags.setPlaceholderText("tags separadas por comas")
    price = QDoubleSpinBox(); price.setMaximum(100000); price.setPrefix("€ ")
    desc = QTextEdit(); desc.setPlaceholderText("Descripción")
    status = QLabel("")
    rl.addWidget(viewer, 1)
    for w in (title, category, tags, price, desc):
        rl.addWidget(w)
    btns = QHBoxLayout()
    btn_save = QPushButton("Guardar")
    btn_thumb = QPushButton("Miniatura…")
    btn_delete = QPushButton("Borrar")
    btn_ai = QPushButton("Publicar con IA")
    for b in (btn_save, btn_thumb, btn_delete, btn_ai):
        btns.addWidget(b)
    rl.addLayout(btns); rl.addWidget(status)
    split.addWidget(right)
    split.setSizes([300, 700])

    state = {"models": [], "current": None}

    def set_status(msg):
        status.setText(msg)

    def run_bg(fn, on_ok, busy="Trabajando…"):
        set_status(busy)
        w = make_worker(fn)
        w.signals.finished.connect(lambda v: (on_ok(v), set_status("Listo")))
        w.signals.failed.connect(lambda e: (set_status("Error"),
                                            QMessageBox.critical(root, "Error", e)))
        pool.start(w)

    def refresh():
        q = search.text().strip() or None
        run_bg(lambda: client.list_models(q=q, limit=200), populate, "Cargando modelos…")

    def populate(models):
        state["models"] = models
        listw.clear()
        for m in models:
            flag = "✔" if m.published else "·"
            it = QListWidgetItem(f"{flag} [{m.id}] {m.title}")
            it.setData(Qt.UserRole, m.id)
            listw.addItem(it)

    def load_selected():
        it = listw.currentItem()
        if not it:
            return
        mid = it.data(Qt.UserRole)
        m = next((x for x in state["models"] if x.id == mid), None)
        if not m:
            return
        state["current"] = m
        title.setText(m.title); category.setText(m.category or "")
        tags.setText(",".join(m.tags)); price.setValue(m.price_eur or 0)
        desc.setPlainText(m.description or "")

        def dl():
            ext = (m.file_format or "glb").lstrip(".")
            dest = settings.shots_dir / str(m.id) / f"model.{ext}"
            dest.parent.mkdir(parents=True, exist_ok=True)
            return client.download_model(m.id, dest)

        run_bg(dl, lambda path: viewer.show_model(path, settings.cache_dir),
               "Cargando 3D…")

    def save():
        m = state["current"]
        if not m:
            return
        fields = dict(title=title.text(), description=desc.toPlainText(),
                      category=category.text() or None,
                      tags=[t.strip() for t in tags.text().split(",") if t.strip()],
                      price_eur=price.value() or None)
        run_bg(lambda: client.update_model(m.id, **fields), lambda _: refresh(),
               "Guardando…")

    def upload():
        path, _ = QFileDialog.getOpenFileName(
            root, "Elegir modelo", "", "Modelos 3D (*.glb *.obj *.stl)")
        if not path:
            return
        name = Path(path).stem
        run_bg(lambda: client.upload_model(Path(path), title=name),
               lambda _: refresh(), "Subiendo…")

    def set_thumb():
        m = state["current"]
        if not m:
            return
        path, _ = QFileDialog.getOpenFileName(root, "Miniatura", "", "Imágenes (*.png *.jpg *.jpeg *.webp)")
        if not path:
            return
        run_bg(lambda: client.set_thumbnail(m.id, Path(path)), lambda _: refresh(),
               "Subiendo miniatura…")

    def delete():
        m = state["current"]
        if not m:
            return
        if QMessageBox.question(root, "Borrar", f"¿Borrar '{m.title}'?") != QMessageBox.Yes:
            return
        run_bg(lambda: client.delete_model(m.id), lambda _: refresh(), "Borrando…")

    def publish_ai():
        m = state["current"]
        if not m:
            return
        open_publish_dialog(root, client, settings, m.id, on_done=refresh)

    btn_refresh.clicked.connect(refresh)
    btn_search.clicked.connect(refresh)
    search.returnPressed.connect(refresh)
    listw.currentItemChanged.connect(lambda *_: load_selected())
    btn_save.clicked.connect(save)
    btn_upload.clicked.connect(upload)
    btn_thumb.clicked.connect(set_thumb)
    btn_delete.clicked.connect(delete)
    btn_ai.clicked.connect(publish_ai)

    refresh()
    return root
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/test_gui_workers.py -v`
Expected: 2 passed.
(Nota: `models_view` se valida manualmente en Task 15; aquí solo se testea la lógica pura `run_callable`.)

- [ ] **Step 6: Commit**

```bash
git add murray3d/gui/workers.py murray3d/gui/models_view.py tests/test_gui_workers.py
git commit -m "feat: gestor de modelos GUI (lista, edición, subida, borrado, miniatura) + workers"
```

---

### Task 14: GUI — diálogo "Publicar con IA" (`gui/publish_dialog.py`)

**Files:**
- Create: `murray3d/gui/publish_dialog.py`
- Test: `tests/test_publish_dialog_logic.py`

**Interfaces:**
- Consumes: `publish.prepare_publish`, `publish.commit_publish`, `make_worker`.
- Produces:
  - `murray3d.gui.publish_dialog.open_publish_dialog(parent, client, settings, model_id, on_done)` — abre un `QDialog` modal: muestra barra de progreso mientras corre `prepare_publish` en un `Worker`; al terminar, pinta los pantallazos (thumbnails clicables, con el `best_thumbnail_index` preseleccionado) y un formulario editable con `GeneratedMeta`; botón "Publicar" corre `commit_publish` con el índice elegido y llama `on_done()`.
  - Función pura testeable `murray3d.gui.publish_dialog.meta_from_form(title, description, tags_text, category, price) -> GeneratedMeta`.

- [ ] **Step 1: Write the failing test** `tests/test_publish_dialog_logic.py`

```python
from murray3d.gui.publish_dialog import meta_from_form


def test_meta_from_form_parses_tags_and_price():
    meta = meta_from_form("Título", "Desc", "a, b ,c", "both", 3.5)
    assert meta.title == "Título"
    assert meta.tags == ["a", "b", "c"]
    assert meta.category == "both"
    assert meta.price_eur == 3.5


def test_meta_from_form_zero_price_is_none():
    meta = meta_from_form("T", "D", "", "figures", 0.0)
    assert meta.price_eur is None
    assert meta.tags == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_publish_dialog_logic.py -v`
Expected: FAIL con `ModuleNotFoundError: No module named 'murray3d.gui.publish_dialog'`.

- [ ] **Step 3: Write `murray3d/gui/publish_dialog.py`**

```python
from __future__ import annotations

from pathlib import Path

from ..models import GeneratedMeta
from .workers import make_worker


def meta_from_form(title, description, tags_text, category, price) -> GeneratedMeta:
    tags = [t.strip() for t in (tags_text or "").split(",") if t.strip()]
    return GeneratedMeta(
        title=title,
        description=description,
        tags=tags,
        category=category,
        price_eur=(price or None) if price else None,
        best_thumbnail_index=0,
    )


def open_publish_dialog(parent, client, settings, model_id, on_done):
    from PySide6.QtCore import Qt, QThreadPool, QSize
    from PySide6.QtGui import QIcon, QPixmap
    from PySide6.QtWidgets import (
        QDialog, QDoubleSpinBox, QHBoxLayout, QLabel, QLineEdit, QListView,
        QListWidget, QListWidgetItem, QMessageBox, QProgressBar, QPushButton,
        QTextEdit, QVBoxLayout,
    )

    from ..publish import commit_publish, prepare_publish

    pool = QThreadPool.globalInstance()
    dlg = QDialog(parent)
    dlg.setWindowTitle("Publicar con IA")
    dlg.resize(900, 700)
    v = QVBoxLayout(dlg)

    progress = QLabel("Renderizando pantallazos y consultando a Claude…")
    bar = QProgressBar(); bar.setRange(0, 0)
    v.addWidget(progress); v.addWidget(bar)

    shots_list = QListWidget()
    shots_list.setViewMode(QListView.IconMode)
    shots_list.setIconSize(QSize(180, 180))
    shots_list.setResizeMode(QListView.Adjust)
    shots_list.hide()
    v.addWidget(shots_list)

    form_title = QLineEdit(); form_title.setPlaceholderText("Título")
    form_cat = QLineEdit(); form_cat.setPlaceholderText("Categoría")
    form_tags = QLineEdit(); form_tags.setPlaceholderText("tags,separadas,por,comas")
    form_price = QDoubleSpinBox(); form_price.setMaximum(100000); form_price.setPrefix("€ ")
    form_desc = QTextEdit()
    for w in (form_title, form_cat, form_tags, form_price, form_desc):
        w.hide(); v.addWidget(w)

    btns = QHBoxLayout()
    btn_publish = QPushButton("Publicar"); btn_publish.setEnabled(False)
    btn_cancel = QPushButton("Cancelar")
    btns.addStretch(); btns.addWidget(btn_cancel); btns.addWidget(btn_publish)
    v.addLayout(btns)

    ctx = {"shots": [], "meta": None}

    def on_prepared(result):
        meta, shots = result
        ctx["shots"] = shots; ctx["meta"] = meta
        bar.hide(); progress.setText("Revisa y ajusta antes de publicar:")
        shots_list.show()
        for i, s in enumerate(shots):
            item = QListWidgetItem(QIcon(QPixmap(str(s))), f"{i}")
            shots_list.addItem(item)
        if 0 <= meta.best_thumbnail_index < len(shots):
            shots_list.setCurrentRow(meta.best_thumbnail_index)
        form_title.setText(meta.title); form_cat.setText(meta.category)
        form_tags.setText(",".join(meta.tags))
        form_price.setValue(meta.price_eur or 0)
        form_desc.setPlainText(meta.description)
        for w in (form_title, form_cat, form_tags, form_price, form_desc):
            w.show()
        btn_publish.setEnabled(True)

    def on_failed(msg):
        bar.hide()
        QMessageBox.critical(dlg, "Error generando metadatos", msg)
        dlg.reject()

    w = make_worker(lambda: prepare_publish(client, settings, model_id))
    w.signals.finished.connect(on_prepared)
    w.signals.failed.connect(on_failed)
    pool.start(w)

    def do_publish():
        meta = meta_from_form(form_title.text(), form_desc.toPlainText(),
                              form_tags.text(), form_cat.text(), form_price.value())
        idx = shots_list.currentRow() if shots_list.currentRow() >= 0 else 0
        btn_publish.setEnabled(False)
        progress.setText("Publicando…"); bar.show()
        w2 = make_worker(lambda: commit_publish(client, model_id, meta,
                                                ctx["shots"], thumbnail_index=idx))
        w2.signals.finished.connect(lambda _: (on_done(), dlg.accept()))
        w2.signals.failed.connect(lambda e: (bar.hide(),
                                             QMessageBox.critical(dlg, "Error", e),
                                             btn_publish.setEnabled(True)))
        pool.start(w2)

    btn_publish.clicked.connect(do_publish)
    btn_cancel.clicked.connect(dlg.reject)
    dlg.exec()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_publish_dialog_logic.py -v`
Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add murray3d/gui/publish_dialog.py tests/test_publish_dialog_logic.py
git commit -m "feat: diálogo Publicar con IA (revisión de pantallazos + metadatos editables)"
```

---

### Task 15: GUI — gestor de packs (`gui/packs_view.py`)

**Files:**
- Create: `murray3d/gui/packs_view.py`
- Test: `tests/test_packs_view_logic.py`

**Interfaces:**
- Consumes: `Client`, `Pack`, `make_worker`.
- Produces:
  - `murray3d.gui.packs_view.parse_ids(text: str) -> list[int]` — parsea "1, 2, 3" → `[1,2,3]`, ignora vacíos/no numéricos.
  - `murray3d.gui.packs_view.build_packs_view(client, settings)` → `QWidget` con lista de packs, editor (título, desc, tags, precio, model_ids), botones "Nuevo", "Guardar", "Borrar", "Añadir modelos seleccionados" (recibe ids del gestor de modelos vía campo de texto o selección). Llamadas por `Worker`.

- [ ] **Step 1: Write the failing test** `tests/test_packs_view_logic.py`

```python
from murray3d.gui.packs_view import parse_ids


def test_parse_ids():
    assert parse_ids("1, 2 ,3") == [1, 2, 3]
    assert parse_ids("") == []
    assert parse_ids("a, 4, x, 5") == [4, 5]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_packs_view_logic.py -v`
Expected: FAIL con `ModuleNotFoundError: No module named 'murray3d.gui.packs_view'`.

- [ ] **Step 3: Write `murray3d/gui/packs_view.py`**

```python
from __future__ import annotations

from .workers import make_worker


def parse_ids(text: str) -> list[int]:
    out = []
    for tok in (text or "").split(","):
        tok = tok.strip()
        if tok.isdigit():
            out.append(int(tok))
    return out


def build_packs_view(client, settings):
    from PySide6.QtCore import Qt, QThreadPool
    from PySide6.QtWidgets import (
        QDoubleSpinBox, QHBoxLayout, QLabel, QLineEdit, QListWidget,
        QListWidgetItem, QMessageBox, QPushButton, QSplitter, QTextEdit,
        QVBoxLayout, QWidget,
    )

    pool = QThreadPool.globalInstance()
    root = QWidget(); outer = QVBoxLayout(root)

    top = QHBoxLayout()
    btn_new = QPushButton("Nuevo pack")
    btn_refresh = QPushButton("Recargar")
    top.addStretch(); top.addWidget(btn_new); top.addWidget(btn_refresh)
    outer.addLayout(top)

    split = QSplitter(Qt.Horizontal); outer.addWidget(split, 1)
    listw = QListWidget(); split.addWidget(listw)

    right = QWidget(); rl = QVBoxLayout(right)
    title = QLineEdit(); title.setPlaceholderText("Título")
    tags = QLineEdit(); tags.setPlaceholderText("tags,separadas,por,comas")
    price = QDoubleSpinBox(); price.setMaximum(100000); price.setPrefix("€ ")
    desc = QTextEdit(); desc.setPlaceholderText("Descripción")
    ids = QLineEdit(); ids.setPlaceholderText("model_ids: 1,2,3")
    status = QLabel("")
    for w in (title, tags, price, desc, QLabel("Modelos del pack:"), ids):
        rl.addWidget(w)
    btns = QHBoxLayout()
    btn_save = QPushButton("Guardar")
    btn_delete = QPushButton("Borrar")
    for b in (btn_save, btn_delete):
        btns.addWidget(b)
    rl.addLayout(btns); rl.addWidget(status)
    split.addWidget(right); split.setSizes([300, 700])

    state = {"packs": [], "current": None}

    def set_status(m): status.setText(m)

    def run_bg(fn, on_ok, busy="Trabajando…"):
        set_status(busy)
        w = make_worker(fn)
        w.signals.finished.connect(lambda v: (on_ok(v), set_status("Listo")))
        w.signals.failed.connect(lambda e: (set_status("Error"),
                                            QMessageBox.critical(root, "Error", e)))
        pool.start(w)

    def refresh():
        run_bg(lambda: client.list_packs(limit=200), populate, "Cargando packs…")

    def populate(packs):
        state["packs"] = packs; listw.clear()
        for p in packs:
            it = QListWidgetItem(f"[{p.id}] {p.title} ({len(p.model_ids)})")
            it.setData(Qt.UserRole, p.id); listw.addItem(it)

    def load_selected():
        it = listw.currentItem()
        if not it:
            return
        p = next((x for x in state["packs"] if x.id == it.data(Qt.UserRole)), None)
        if not p:
            return
        state["current"] = p
        title.setText(p.title); tags.setText(",".join(p.tags))
        price.setValue(p.price_eur or 0); desc.setPlainText(p.description or "")
        ids.setText(",".join(str(i) for i in p.model_ids))

    def new_pack():
        state["current"] = None
        title.clear(); tags.clear(); price.setValue(0); desc.clear(); ids.clear()

    def save():
        fields = dict(
            title=title.text(),
            description=desc.toPlainText(),
            tags=[t.strip() for t in tags.text().split(",") if t.strip()],
            price_eur=price.value() or None,
            model_ids=parse_ids(ids.text()),
        )
        p = state["current"]
        if p is None:
            run_bg(lambda: client.create_pack(**fields), lambda _: refresh(), "Creando…")
        else:
            run_bg(lambda: client.update_pack(p.id, **fields), lambda _: refresh(), "Guardando…")

    def delete():
        p = state["current"]
        if not p:
            return
        if QMessageBox.question(root, "Borrar", f"¿Borrar pack '{p.title}'?") != QMessageBox.Yes:
            return
        run_bg(lambda: client.delete_pack(p.id), lambda _: refresh(), "Borrando…")

    btn_new.clicked.connect(new_pack)
    btn_refresh.clicked.connect(refresh)
    btn_save.clicked.connect(save)
    btn_delete.clicked.connect(delete)
    listw.currentItemChanged.connect(lambda *_: load_selected())

    refresh()
    return root
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_packs_view_logic.py -v`
Expected: 1 passed.

- [ ] **Step 5: Commit**

```bash
git add murray3d/gui/packs_view.py tests/test_packs_view_logic.py
git commit -m "feat: gestor de packs GUI"
```

---

### Task 16: GUI — ventana principal y arranque (`gui/app.py`)

**Files:**
- Create: `murray3d/gui/app.py`
- Test: `tests/test_gui_app_import.py`

**Interfaces:**
- Consumes: `config.load_settings`, `api.Client`, `models_view.build_models_view`, `packs_view.build_packs_view`.
- Produces:
  - `murray3d.gui.app.run_gui()` — carga settings (si falla por clave, muestra `QInputDialog` para pedir la clave y la guarda en `key.txt`), verifica `whoami`, crea `QMainWindow` con `QTabWidget` (pestañas "Modelos" y "Packs"), muestra el `author_name` en el título, y ejecuta el bucle Qt.

- [ ] **Step 1: Write the failing test** `tests/test_gui_app_import.py`

```python
def test_run_gui_is_callable():
    from murray3d.gui.app import run_gui
    assert callable(run_gui)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_gui_app_import.py -v`
Expected: FAIL con `ModuleNotFoundError: No module named 'murray3d.gui.app'`.

- [ ] **Step 3: Write `murray3d/gui/app.py`**

```python
from __future__ import annotations

import sys
from pathlib import Path

from ..api import ApiError, Client
from ..config import PROJECT_ROOT, ConfigError, load_settings


def _load_or_ask_settings(app):
    from PySide6.QtWidgets import QInputDialog, QMessageBox
    try:
        return load_settings()
    except ConfigError:
        key, ok = QInputDialog.getText(None, "API Key", "Introduce tu API key de 3DBundle:")
        if not ok or not key.strip():
            QMessageBox.critical(None, "Sin clave", "No se puede continuar sin API key.")
            sys.exit(1)
        (PROJECT_ROOT / "key.txt").write_text(key.strip() + "\n")
        return load_settings()


def run_gui():
    from PySide6.QtWidgets import (
        QApplication, QMainWindow, QMessageBox, QTabWidget,
    )
    from .models_view import build_models_view
    from .packs_view import build_packs_view

    app = QApplication(sys.argv)
    app.setApplicationName("murray3d")

    settings = _load_or_ask_settings(app)
    client = Client(settings)
    try:
        profile = client.whoami()
    except ApiError as e:
        QMessageBox.critical(None, "Error de autenticación", str(e))
        sys.exit(1)

    win = QMainWindow()
    win.setWindowTitle(f"murray3d — {profile.author_name or profile.email}")
    win.resize(1200, 800)

    tabs = QTabWidget()
    tabs.addTab(build_models_view(client, settings), "Modelos")
    tabs.addTab(build_packs_view(client, settings), "Packs")
    win.setCentralWidget(tabs)
    win.show()

    code = app.exec()
    client.close()
    sys.exit(code)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_gui_app_import.py -v`
Expected: 1 passed.

- [ ] **Step 5: Run the full non-integration suite**

Run: `python -m pytest -v`
Expected: todos los tests no-integration en verde.

- [ ] **Step 6: Commit**

```bash
git add murray3d/gui/app.py tests/test_gui_app_import.py
git commit -m "feat: ventana principal GUI y arranque (murray3d gui)"
```

---

### Task 17: README, verificación end-to-end y checklist manual

**Files:**
- Create: `README.md`

**Interfaces:**
- Consumes: todo.
- Produces: documentación de instalación, uso del CLI, uso por Claude Code, y checklist manual de la GUI.

- [ ] **Step 1: Write `README.md`**

````markdown
# murray3d

Cliente local (macOS) para [3DBundle](https://murrayslab.com/3dbundle): gestor de
modelos y packs 3D + publicación asistida por Claude Code.

## Instalación

```bash
python3 -m venv .venv && . .venv/bin/activate
pip install -e ".[dev]"
python -m playwright install chromium
python -m murray3d.gui.assets.download_model_viewer
```

La API key se lee de `key.txt` (primera línea) o de `MURRAY_API_KEY`.

## GUI

```bash
murray3d gui
```

Pestañas **Modelos** (listar, ver en 3D, subir, editar, borrar, miniatura,
**Publicar con IA**) y **Packs** (crear, editar, borrar, gestionar model_ids).

### Flujo "Publicar con IA"
1. Selecciona un modelo → **Publicar con IA**.
2. La app renderiza 6 pantallazos y llama a `claude` para proponer título,
   descripción, tags, categoría, precio y mejor miniatura.
3. Revisa/edita y pulsa **Publicar** (PATCH `published:true` + miniatura).

Requiere el CLI `claude` en el PATH y autenticado.

## CLI (y uso por Claude Code)

```bash
murray3d whoami
murray3d models list [--json] [--q dragon] [--mine]
murray3d models show <id>
murray3d models upload <fichero.glb> "<título>" [--tags a,b] [--category both]
murray3d models edit <id> [--title ...] [--published/--unpublished]
murray3d models delete <id> --yes
murray3d models thumbnail <id> <imagen.png>
murray3d render <id>                 # genera pantallazos, imprime rutas
murray3d ai-generate <id>            # pantallazos + metadatos propuestos (JSON)
murray3d ai-publish <id> [--yes]     # genera, (confirma) y publica
murray3d packs list|show|create|edit|delete|add-model
```

## Tests

```bash
pytest                 # unitarios (rápidos)
pytest -m integration  # requiere Chromium de Playwright (render real)
```
````

- [ ] **Step 2: Run the complete verification (real API + real render + real claude)**

Ejecuta y confirma cada paso (marca de verificación end-to-end del CLAUDE.md):

```bash
# 1. Suite completa unitaria
pytest

# 2. Render de integración
pytest -m integration

# 3. CLI contra API real
murray3d whoami
murray3d models list

# 4. ai-generate real sobre un modelo propio (NO publica)
murray3d ai-generate <un_model_id_propio>
```
Expected:
- pytest: todo verde.
- pytest -m integration: render pasa.
- `whoami` muestra el perfil; `models list` lista.
- `ai-generate` imprime un JSON con `meta` (título/desc/tags/categoría en español) y `shots` (6 rutas PNG existentes).

- [ ] **Step 3: Manual GUI checklist**

Lanza `murray3d gui` y verifica manualmente:
- [ ] La ventana abre y el título muestra el autor ("Muriano").
- [ ] La pestaña Modelos lista modelos.
- [ ] Al seleccionar un modelo se ve el 3D en el visor y se rellenan los campos.
- [ ] "Subir modelo…" sube un `.glb`/`.stl` y aparece en la lista.
- [ ] "Guardar" persiste un cambio de metadatos.
- [ ] "Publicar con IA" muestra pantallazos + metadatos editables y publica.
- [ ] Pestaña Packs: crear un pack con model_ids, guardarlo y borrarlo.

- [ ] **Step 4: Commit**

```bash
git add README.md
git commit -m "docs: README con instalación, CLI, flujo IA y checklist de verificación"
```

---

## Notas de ejecución

- **Orden estricto de dependencias:** Task 1 → 2 → 3 → 4 → 5 (núcleo API) → 6 (convert) → 7 (assets) → 8 (render) → 9 (ai) → 10 (publish) → 11 (CLI) → 12-16 (GUI) → 17 (docs/E2E).
- Tasks 12-16 (GUI) dependen del núcleo pero son mayormente independientes entre sí salvo `app.py` (Task 16), que las une; `models_view` (Task 13) referencia `publish_dialog` (Task 14).
- La verificación end-to-end real (Task 17, paso 2) es obligatoria antes de considerar el trabajo completo, por política del proyecto.
