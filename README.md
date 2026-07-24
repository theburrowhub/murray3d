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

Configura tu API key: copia la plantilla y rellénala (o exporta `MURRAY_API_KEY`).

```bash
cp .env.dist .env   # luego edita .env y pon tu MURRAY_API_KEY
```

`.env` está en `.gitignore`. `make run` la carga automáticamente.

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
