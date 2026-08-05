# murray3d

Cliente local (macOS/Linux) para [3DBundle](https://murrayslab.com/3dbundle): una app
de escritorio (PySide6) y un CLI para **gestionar tus modelos y packs 3D** y
**publicarlos con metadatos generados por Claude Code** a partir de pantallazos
de cada mini.

- **App de escritorio** con visor 3D, gestión de modelos y packs.
- **Publicar con IA**: la app renderiza imágenes del modelo y `claude` propone
  título, descripción, tags, categoría, precio y miniatura; tú revisas y publicas.
- **Núcleo scriptable** (`murray3d …`): el mismo motor por línea de comandos.

Repo: <https://github.com/theburrowhub/murray3d>

---

## Requisitos

- Python 3.11+ (probado hasta 3.14) en macOS o Linux.
- El CLI **`claude`** (Claude Code) instalado en el `PATH` y autenticado — es lo
  que genera los metadatos en "Publicar con IA" y las imágenes/3D en la
  autogeneración.
- Una **API key de 3DBundle**.
- (Solo para autogeneración) el **MCP de Magnific** disponible para `claude`
  (`/mcp` → login OAuth, o `claude mcp add`).

> Verificado en Linux (Ubuntu) con Python 3.14: `make setup`, los tests
> unitarios (63) y el test de integración de render real (Chromium + Playwright)
> pasan sin cambios. En Linux, Playwright puede necesitar librerías de sistema
> para Chromium (`libnss3`, `libgbm1`, `libasound2`, …); si faltan, instálalas
> con `python -m playwright install-deps chromium`.

## Instalación

```bash
git clone git@github.com:theburrowhub/murray3d.git
cd murray3d
make setup          # crea .venv, instala deps + Chromium de Playwright + model-viewer
cp .env.dist .env   # edita .env y pon tu MURRAY_API_KEY
make run            # arranca la app
```

`make setup` equivale a:

```bash
python3 -m venv .venv && . .venv/bin/activate
pip install -e ".[dev]"
python -m playwright install chromium
python -m murray3d.gui.assets.download_model_viewer
```

La API key se lee, en este orden, de: la variable de entorno `MURRAY_API_KEY`,
`~/.config/murray3d/key.txt` (config de usuario, recomendado — no depende de la
ruta del repo), o `key.txt` en el proyecto. `.env`/`key.txt` están en `.gitignore`
y nunca se suben.

## Uso con `make`

```bash
make run          # abre la GUI (carga .env automáticamente)
make whoami       # comprueba la autenticación
make models       # lista tus modelos
make packs        # lista tus packs
make cli ARGS="models show 10"
make test         # tests unitarios
make test-integration   # render real con Chromium (lento)
```

---

## La app

Dos pestañas: **Modelos** y **Packs**. Nada llega a la tienda hasta que lo
confirmas: todo se sube/crea como **borrador** (`○`) y solo pasa a **publicado**
(`✔`) cuando tú lo decides.

### Modelos

La lista muestra **solo tus modelos** (publicados y borradores).

- **Crear** (`＋ Nuevo modelo…`): eliges un `.glb/.obj/.stl`, se **previsualiza
  en 3D localmente** y no se sube nada; pulsa **«Subir como borrador»** para
  confirmar (o «Cancelar»).
- **Subir por lotes…**: seleccionas varios ficheros y se suben todos como
  borrador, de uno en uno y por streaming (soporta lotes de **>1GB**).
- **Publicar borradores con IA**: ejecuta el flujo completo (render + Claude +
  publicar) para **todos tus borradores** de una vez.
- **Editar**: selecciona un modelo de la lista para ver su visor 3D y sus
  metadatos, con **Guardar cambios / Miniatura… / Borrar / Publicar con IA**.

**Publicar con IA (modelo):**
1. Con un modelo seleccionado → **Publicar con IA**.
2. La app renderiza varios pantallazos en órbita y llama a `claude`, que propone
   título, descripción, tags, categoría, precio y el mejor pantallazo de miniatura.
3. Revisas/editas y pulsas **Publicar** → `PATCH published:true` + miniatura.

Junto a cada botón **Publicar con IA** (modelos, packs y "Publicar borradores con
IA") hay un **desplegable** para elegir con qué modelo de Claude lanzar la
publicación: por defecto, `opus`, `sonnet`, `haiku` o `fable`.

### Packs

- **Nuevo pack** / editar: título, descripción, tags, precio y casilla
  **«Publicado»**.
- Los modelos del pack se eligen **marcando casillas** en la lista de modelos
  (incluye borradores), no escribiendo IDs.
- **Publicar con IA (pack):** con un pack guardado y con modelos, pulsa
  **Publicar con IA** → renderiza una imagen de cada modelo del pack y `claude`
  genera **título, descripción, tags y precio del bundle**; revisas y publicas.

---

## Autogeneración desde JSON de prompts (Magnific)

Genera imágenes de miniaturas **y su malla 3D** en serie a partir de un JSON con
cientos de prompts. Pensado para lotes grandes (uno a uno, `manifest.json`
reanudable, continúa ante errores). Guía completa en [`docs/autogen.md`](docs/autogen.md).

Igual que "Publicar con IA", **no usa ninguna API REST**: reutiliza el binario
**`claude`** conectado al **MCP de Magnific** (`images_generate` para imagen,
`models3d_generate` para 3D). No hace falta ninguna API key aparte.

- Requiere el **MCP de Magnific** disponible para `claude`: `/mcp` (login OAuth) o
  `claude mcp add --transport http magnific https://mcp.magnific.com`.
- **Malla 3D (`--make-3d`):** `models3d_generate` (Tripo/Trellis → `.glb`).
  ⚠️ ~580 créditos por modelo — usar con `--limit`. Pipeline: prompt → imagen →
  GLB → subir a 3DBundle.

```bash
murray3d autogen-validate examples/prompts-miniaturas.sample.json   # inspecciona (sin gasto)
murray3d autogen-image "Miniature figure of Goku, 40mm base" out.jpg   # 1 imagen
murray3d autogen examples/prompts-miniaturas.sample.json --limit 3 --seed 42
murray3d autogen examples/prompts-miniaturas.sample.json --limit 1 --make-3d   # imagen + GLB
```

En la GUI hay una pestaña **Autogeneración** (cargar JSON → tabla → Generar) con
**previsualización** de la imagen y el modelo 3D generados, y **reanudación**: si
cierras la app a mitad, al recargar el JSON marca lo ya hecho y continúa. En la app
completa incluye **Exportar a 3DBundle**, que sube los `.glb` generados a la web de
murray3d como borrador (con su miniatura), igual que la pestaña Modelos. Abre solo
la autogeneración (sin API key de 3DBundle) con `murray3d gui --autogen-only`.

## CLI (y uso por Claude Code)

El mismo núcleo por línea de comandos (usa `.venv/bin/murray3d` o `make cli`):

```bash
murray3d whoami
murray3d models list [--json] [--q dragon] [--mine] [--published/--all]
murray3d models show <id>
murray3d models upload <fichero.glb> "<título>" [--tags a,b] [--category both] [--price 4.99]
murray3d models edit <id> [--title …] [--tags …] [--price …] [--published/--unpublished]
murray3d models thumbnail <id> <imagen.png>
murray3d models delete <id> --yes
murray3d render <id> [--angles N]    # descarga + genera pantallazos, imprime rutas
murray3d ai-generate <id> [--model haiku]        # pantallazos + metadatos propuestos (JSON)
murray3d ai-publish <id> [--yes] [--model opus]  # genera, (confirma) y publica

# Lotes (soportan >1GB: streaming + secuencial + limpieza de temporales)
murray3d batch-upload <ruta…> [--json]          # sube todos los .glb/.obj/.stl como borrador
murray3d batch-ai-publish [ids…] [--all-drafts] [--yes] [--model sonnet]   # publica con IA un lote
murray3d packs list|show|create|edit|delete
murray3d packs add-model <pack_id> <model_id…>
murray3d gui                         # abre la app
```

Todos los subcomandos de consulta aceptan `--json` y devuelven código de salida
no-cero ante error.

> Nota: la descarga del fichero de un modelo (para renderizar) requiere ser el
> **propietario** del modelo; los modelos de otras cuentas están protegidos.

---

## Tests

```bash
make test                # unitarios (rápidos, sin red ni Chromium)
make test-integration    # render real con el Chromium de Playwright
```

## Arquitectura (resumen)

```
murray3d/
  config.py     carga de .env / MURRAY_API_KEY, rutas de caché
  api.py        cliente HTTP de la API de 3DBundle (errores tipados)
  models.py     modelos de datos (Model3D, Pack, GeneratedMeta, GeneratedPackMeta)
  convert.py    obj/stl -> glb (trimesh), con caché
  render.py     pantallazos con Playwright + model-viewer (servido por HTTP local)
  ai.py         invoca `claude -p` para generar metadatos (modelo y pack)
  publish.py    orquestación: descargar -> render -> IA -> publicar
  prompts.py    modelos del JSON de prompts + convención de nombres (autogen)
  agent_gen.py  imagen por agente: `claude` + MCP de Magnific (images_generate)
  mesh_gen.py   image-to-3D (GLB) por agente + MCP de Magnific (models3d_generate)
  download.py   descarga de URLs (imágenes / GLB) a disco
  autogen.py    orquestación por lotes (serie, reanudable, manifest, +3D)
  cli.py        CLI (typer)
  gui/          app PySide6 (visor, gestor de modelos/packs, autogeneración)
```
