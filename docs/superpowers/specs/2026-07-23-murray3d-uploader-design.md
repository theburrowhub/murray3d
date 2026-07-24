# murray3d — Cliente local para 3DBundle

**Fecha:** 2026-07-23
**Estado:** Diseño aprobado, pendiente de revisión de spec

## 1. Objetivo

Aplicación de escritorio nativa (macOS) para gestionar los elementos 3D de la
cuenta en [3DBundle](https://murrayslab.com/3dbundle/api/docs) y publicarlos con
ayuda de IA. El mismo núcleo se expone como CLI scriptable para que **Claude Code**
pueda operarlo directamente en una sesión.

Dos capacidades principales:

1. **Gestor de elementos 3D**: modelos y packs (listar, ver en 3D, subir, editar,
   borrar, gestionar miniatura, gestionar packs y sus model IDs).
2. **Publicar con IA**: genera pantallazos del modelo, se los pasa a `claude` (CLI
   headless) para que proponga título, descripción, tags, categoría, precio y el
   mejor pantallazo como miniatura; el usuario revisa/edita y confirma la publicación.

## 2. La API 3DBundle (resumen relevante)

- Base URL: `https://murrayslab.com/3dbundle/api`
- Autenticación: header `X-API-Key`. La clave está en `key.txt` (git-ignored) o en
  la variable de entorno `MURRAY_API_KEY`.
- Extensiones permitidas: `glb`, `obj`, `stl`. Tamaño máx.: 200 MB (de `/config`).

Endpoints usados:

| Método | Ruta | Uso |
|---|---|---|
| GET | `/auth/me` | Verificar clave, obtener perfil (id, author_name). |
| GET | `/models` | Listar/buscar modelos (`q`, `tag`, `category`, `only_published`, `limit`, `offset`). |
| POST | `/models` | Subir modelo (multipart: `file`, `title`, `description`, `category`, `tags`, `price_eur`, `thumbnail?`). |
| GET | `/models/{id}` | Obtener un modelo. |
| PATCH | `/models/{id}` | Actualizar metadatos y **publicar** (`published: true`). |
| DELETE | `/models/{id}` | Borrar modelo. |
| POST | `/models/{id}/thumbnail` | Fijar/reemplazar miniatura (multipart: `thumbnail`). |
| GET | `/models/{id}/download` | Descargar el fichero del modelo. |
| POST/GET | `/packs` | Crear / listar packs. |
| GET/PATCH/DELETE | `/packs/{id}` | Obtener / actualizar / borrar pack. |
| GET | `/config` | Config pública (extensiones, tamaño máx.). |
| GET | `/search` | Búsqueda global (modelos + packs). |

**Schema `Model3D`** (campos relevantes): `id`, `title`, `description`, `category`,
`tags[]`, `price_eur`, `filename`, `stored_name`, `file_format`, `file_size`,
`thumbnail`, `uploader`, `owner_id`, `author`, `published`, `created_at`, `updated_at`.

**Schema `Pack`**: `id`, `title`, `description`, `tags[]`, `price_eur`, `cover`,
`model_ids[]`, `uploader`, `owner_id`, `author`, `published`, timestamps.

**Categorías**: la API no expone un enum. Se infieren de los modelos existentes
(observado: `both`). El cliente ofrece las categorías vistas + entrada libre, y
constriñe la propuesta de la IA a ese conjunto conocido.

**Publicar = `PATCH /models/{id}`** con los metadatos finales y `published: true`.
No existe un endpoint "publish" dedicado.

## 3. Arquitectura

Núcleo compartido (usable por la GUI y por el CLI/Claude Code) + capa GUI nativa.

```
murray3d/
  __init__.py
  config.py        # base URL, carga de API key (key.txt / env), rutas de caché
  api.py           # cliente httpx tipado de TODA la API
  models.py        # dataclasses/pydantic: Model3D, Pack, perfil, etc.
  render.py        # generación de pantallazos (Playwright headless + model-viewer)
  convert.py       # obj/stl -> glb con trimesh (con caché)
  ai.py            # invocación de `claude -p` headless y parseo del JSON
  cli.py           # CLI (typer): models/packs/render/ai-generate/publish/ai-publish
  gui/
    app.py         # PySide6: ventana principal, arranque
    models_view.py # rejilla de modelos, detalle/edición, subida, borrado
    packs_view.py  # gestor de packs y model IDs
    viewer.py      # QWebEngineView con <model-viewer> embebido (preview 3D)
    publish_dialog.py # flujo "Publicar con IA": pantallazos + formulario editable
    assets/
      model-viewer.min.js  # empaquetado local (self-contained)
      viewer.html          # plantilla del visor
pyproject.toml
README.md
```

### Capas

1. **`api.py`** — Cliente síncrono `httpx`. Un método por endpoint. Inyecta
   `X-API-Key`. Traduce errores HTTP (401/404/422) a excepciones tipadas
   (`AuthError`, `NotFoundError`, `ValidationError`) con mensaje legible.

2. **`convert.py`** — Convierte `.obj/.stl` a `.glb` con `trimesh`+`pygltflib` y
   cachea el resultado en `~/.murray3d/cache/`. Los `.glb` se usan tal cual.

3. **`render.py`** — Dada la ruta de un modelo (glb, o convertido), lanza Chromium
   headless con Playwright, carga `viewer.html` con `<model-viewer>`, orbita la
   cámara a N ángulos (por defecto 6: frente, 3/4 izq, lateral, 3/4 der, atrás,
   picado) y captura un PNG por ángulo vía `model-viewer.toDataURL()`. Devuelve la
   lista de rutas PNG. Camino único usado tanto por la GUI como por el CLI headless.

4. **`ai.py`** — Construye un prompt con las rutas de los pantallazos y ejecuta
   `claude -p <prompt> --output-format json` (o equivalente) como subproceso.
   Pide un JSON estricto:
   ```json
   {
     "title": "str",
     "description": "str",
     "tags": ["str", ...],
     "category": "str (de las categorías conocidas)",
     "price_eur": 0.0,
     "best_thumbnail_index": 0
   }
   ```
   Parsea y valida la respuesta. Si `claude` no está en PATH o falla, devuelve un
   error claro y la GUI permite rellenar a mano.

5. **`cli.py`** — Typer. Comandos (todos con `--json` para salida máquina):
   - `murray3d whoami`
   - `murray3d models list [--q --tag --category --mine --published]`
   - `murray3d models show <id>`
   - `murray3d models upload <file> [--title --description --category --tags --price]`
   - `murray3d models edit <id> [--title ... --published/--unpublished]`
   - `murray3d models delete <id>`
   - `murray3d models thumbnail <id> <image>`
   - `murray3d packs list|show|create|edit|delete`
   - `murray3d packs add-model <pack_id> <model_id...>`
   - `murray3d render <id|file> [--out DIR --angles N]`
   - `murray3d ai-generate <id|file>`  → imprime el JSON de metadatos propuesto
   - `murray3d publish <id> [--title ... --thumbnail IMG]`  → PATCH published:true
   - `murray3d ai-publish <id> [--yes]` → render + ai-generate + (confirmar) + publish + thumbnail
   Códigos de salida no-cero ante error.

6. **`gui/`** — App **nativa PySide6** (no navegador):
   - Ventana principal con pestañas **Modelos** y **Packs**.
   - **Modelos**: rejilla con miniaturas y estado (publicado/borrador); panel de
     detalle con visor 3D interactivo (`QWebEngineView` + model-viewer), edición de
     metadatos, botones Subir / Borrar / Miniatura / **Publicar con IA**.
   - **Packs**: lista de packs; editor con título/desc/tags/precio/cover y selector
     de model IDs (elegir de modelos existentes o subir uno nuevo y añadir su id).
   - **Publish dialog**: al pulsar "Publicar con IA" → barra de progreso mientras
     `render.py` genera pantallazos y `ai.py` llama a `claude` → muestra los
     pantallazos (con el "mejor" preseleccionado) y un formulario editable con lo
     propuesto → botón **Publicar** hace `PATCH published:true` + `POST thumbnail`
     con el pantallazo elegido.

### Flujo "Publicar con IA" (revisar y confirmar)

```
Usuario: "Publicar con IA" sobre un modelo
  -> render.py: 6 pantallazos en órbita (temp dir)
  -> ai.py: claude -p con las imágenes -> JSON metadatos + best_thumbnail_index
  -> GUI: muestra pantallazos + formulario editable precargado
  -> Usuario ajusta y pulsa "Publicar"
  -> api: PATCH /models/{id} {metadatos..., published:true}
  -> api: POST /models/{id}/thumbnail (pantallazo elegido)
  -> refresco de la rejilla
```

## 4. Manejo de errores

- **Clave ausente/ inválida**: al arrancar, `whoami`/`/auth/me`; si falla, la GUI
  muestra diálogo pidiendo la clave y ofrece guardarla en `key.txt`.
- **Errores API** (422 validación, 404, 5xx): mensaje legible en la UI y código de
  salida no-cero en CLI.
- **`claude` CLI ausente o error**: el flujo IA lo reporta y permite rellenar a mano.
- **Render falla** (modelo corrupto, timeout Playwright): mensaje claro; se puede
  publicar sin IA usando el editor manual.
- **Conversión obj/stl falla**: se avisa; el modelo sigue siendo gestionable salvo
  el preview/pantallazos.

## 5. Testing

- **`api.py`**: tests con `httpx.MockTransport` (respuestas simuladas por endpoint,
  incluidos 401/422). Un test de humo real opcional contra `/auth/me` (marcado,
  usa `key.txt`).
- **`convert.py`**: convertir un `.stl`/`.obj` mínimo a `.glb` y validar que carga.
- **`ai.py`**: parseo de JSON válido/ inválido de `claude` con subproceso mockeado.
- **`render.py`**: test de integración marcado (requiere Chromium de Playwright)
  que renderiza un `.glb` de ejemplo y comprueba que salen N PNGs no vacíos.
- **`cli.py`**: invocación de comandos con el cliente API mockeado; verificar
  códigos de salida y salida `--json`.
- La GUI se valida manualmente (checklist end-to-end en README): arrancar, listar,
  subir, previsualizar 3D, publicar con IA, gestionar un pack.

## 6. Dependencias

Python 3.11+. `httpx`, `typer`, `pydantic`, `trimesh`, `pygltflib`, `numpy`,
`playwright` (+ `playwright install chromium`), `PySide6` (incluye QtWebEngine).
`pytest` para tests. `model-viewer` empaquetado localmente en `gui/assets/`.

Requisito externo en tiempo de ejecución para el flujo IA: el CLI `claude`
(Claude Code) disponible en el PATH y autenticado.

## 7. Fuera de alcance (YAGNI)

- Endpoints admin (`/admin/*`), requests y quotes: no se gestionan desde el cliente.
- Rotación de clave (`/auth/rotate`): fuera de alcance inicial.
- Empaquetado como `.app`/instalador firmado: se ejecuta como app Python
  (`murray3d gui`). Se puede añadir después.
- Windows/Linux: objetivo macOS; el código evita APIs específicas de macOS, pero
  no se prueba en otras plataformas en esta iteración.
