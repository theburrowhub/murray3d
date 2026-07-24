# CLAUDE.md — guía para agentes

Este proyecto (`murray3d`) es un cliente de 3DBundle. Además de la GUI, expone
un **CLI totalmente scriptable** pensado para que un agente lo opere. Este
fichero explica cómo usarlo.

## Puesta en marcha

```bash
make setup          # una vez: .venv + deps + Chromium de Playwright + model-viewer
cp .env.dist .env   # y rellena MURRAY_API_KEY
```

- Ejecuta el CLI con **`.venv/bin/murray3d …`** (o `make cli ARGS="…"`).
- Auth: `MURRAY_API_KEY` en `.env` o como variable de entorno. Compruébalo con
  `.venv/bin/murray3d whoami` (debe imprimir el perfil).
- El flujo "IA" ejecuta el binario **`claude`** como subproceso: debe estar en el
  `PATH` y autenticado.

## Modelo mental

- Todo se crea/sube como **borrador** (`published:false`). Nada aparece en la
  tienda hasta publicarlo explícitamente.
- Listados: por defecto solo devuelven **publicados**. Para ver borradores usa
  `--all` (modelos) o el flag equivalente; los listados del gestor usan
  `only_published=false` internamente.
- **Descargar** el fichero de un modelo (necesario para renderizar) solo funciona
  si eres el **propietario**; los modelos de otras cuentas están protegidos tras
  compra.
- La API **publica al subir**; por eso `upload` debe ir seguido de
  `edit --unpublished` si quieres dejarlo en borrador (la GUI lo hace sola).

## Comandos

```bash
murray3d whoami

# Modelos
murray3d models list [--json] [--q <texto>] [--mine] [--published/--all]
murray3d models show <id>
murray3d models upload <fichero.glb> "<título>" [--tags a,b] [--category both] [--price 4.99]
murray3d models edit <id> [--title …] [--description …] [--tags a,b] [--price …] [--published/--unpublished]
murray3d models thumbnail <id> <imagen.png>
murray3d models delete <id> --yes

# Render + IA (modelos)
murray3d render <id> [--angles N]    # descarga + pantallazos, imprime rutas JSON
murray3d ai-generate <id>            # render + metadatos propuestos (JSON: {meta, shots})
murray3d ai-publish <id> [--yes]     # ai-generate + (confirmar) + PATCH published:true + miniatura

# Lotes (pensados para muchos recursos / >1GB: streaming, secuencial,
# limpieza de temporales por modelo, y continúan ante errores por elemento)
murray3d batch-upload <ruta…> [--json]      # ficheros o carpetas -> sube todo como borrador
murray3d batch-ai-publish [ids…] [--all-drafts] [--yes] [--json]

# Packs
murray3d packs list [--json]
murray3d packs show <id>
murray3d packs create "<título>" [--tags a,b] [--price 9.99] [--model-ids 1,2,3]
murray3d packs edit <id> [--title …] [--tags …] [--price …] [--published/--unpublished]
murray3d packs add-model <pack_id> <model_id…>
murray3d packs delete <id> --yes
```

Salida `--json` en los comandos de consulta; código de salida ≠ 0 ante error
(`ApiError`, `ConfigError`, `RenderError`, `AiError`, `ConvertError`).

## Recetas típicas

**Publicar un modelo propio con IA (todo en uno):**
```bash
murray3d ai-publish <id> --yes
```

**Publicar controlando los metadatos tú mismo:**
```bash
murray3d ai-generate <id>          # inspecciona el JSON {meta, shots}
murray3d models edit <id> --title "…" --tags a,b --price 4.99 --published
murray3d models thumbnail <id> <shots[best]>
```

**Subir y publicar un lote entero (aunque sean >1GB):**
```bash
murray3d batch-upload ./mi_carpeta_de_minis   # sube todo como borrador
murray3d batch-ai-publish --all-drafts --yes  # genera metadatos y publica cada uno
```
Se procesa de uno en uno (streaming, sin cargar ficheros enteros en memoria) y
se limpian los temporales de cada modelo tras publicarlo, así que el tamaño
total del lote no es un problema.

**Crear y publicar un pack:**
```bash
murray3d packs create "Mi pack" --model-ids 10,11
# revisa; cuando quieras publicarlo:
murray3d packs edit <pack_id> --published
```
(La publicación de packs con metadatos de bundle generados por IA está en la GUI,
botón "Publicar con IA"; por CLI usa `ai-generate` sobre cada modelo y compón el
pack manualmente.)

## Flujo de trabajo del repo

- Ejecuta `make test` antes de commitear; `make test-integration` para el render real.
- No commitees `.env` (contiene la clave; está en `.gitignore`).
