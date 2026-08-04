# Autogeneración desde JSON de prompts

Genera imágenes de miniaturas **en serie** a partir de un JSON con cientos de
prompts bien ordenados, usando **Freepik**. Pensado para lotes grandes: procesa
de uno en uno, escribe un `manifest.json` incremental (reanudable) y continúa
ante errores por elemento.

> **Sobre el 3D — dónde vive cada cosa (verificado):**
> - La **REST API** de Freepik/Magnific **solo genera imágenes** (flux-dev,
>   Mystic, Seedream, Imagen3) y upscaling. **No hay endpoint REST de 3D.**
> - El **MCP de Freepik** (`api.freepik.com/mcp`, API key) tampoco: imagen
>   (Mystic), vídeo (Kling), iconos, stock.
> - El **MCP de Magnific** (`mcp.magnific.com`, **OAuth**) **sí** expone
>   `models3d_generate` (image-to-3D → **GLB**, con Tripo/Trellis).
>
> Por eso el pipeline es: **prompt → imagen** (REST o agente) **→ malla 3D**
> (`--make-3d`, solo por agente + MCP de Magnific) **→** subir a 3DBundle.
> ⚠️ Cada 3D gasta **~580–1160 créditos**; usa `--make-3d` con `--limit`.

## 1. Suministrar la clave de Freepik

1. Entra en el **dashboard de desarrolladores de Freepik**:
   <https://www.freepik.com/developers/dashboard> y genera una **API key**.
2. Añádela a tu `.env` (o expórtala como variable de entorno):

   ```bash
   # en .env (git-ignored, nunca se sube)
   FREEPIK_API_KEY=fpsk_tu_clave_aqui
   ```

   Variables opcionales:
   - `FREEPIK_BASE_URL` (default `https://api.freepik.com/v1`; alternativa tras el
     rebrand: `https://api.magnific.com/v1`).
   - `FREEPIK_API_HEADER` (default `x-freepik-api-key`; alternativa `x-magnific-api-key`).

La clave se consume por **créditos** de tu cuenta Freepik. Cada imagen gasta
créditos; los rate limits se aplican por key/IP (el cliente reintenta ante 429).

## 2. Los dos backends

| Backend | Qué hace | Cuándo usarlo |
|---|---|---|
| `rest` (default) | Llama a la API REST de Freepik directamente | Cientos de prompts en serie, barato, determinista, sin supervisión |
| `agent` | Lanza `claude` + el **MCP de Freepik** como agente simple | Da sentido al MCP; el agente abstrae endpoint/polling; mismo patrón que "Publicar con IA" |

El backend `agent` requiere que el **MCP de Freepik esté disponible** para `claude`.
El servidor MCP (`https://api.freepik.com/mcp`) **autentica con la propia API key
por header** (no necesita el flujo OAuth de `/mcp`): basta pasar un `--mcp-config`
como [`examples/freepik-mcp.json`](../examples/freepik-mcp.json), que toma la clave
de `FREEPIK_API_KEY`:

```bash
murray3d autogen <prompts.json> --backend agent --mcp-config examples/freepik-mcp.json
```

> Por MCP el modelo de imagen es **Mystic** (`create_image_mystic` /
> `text_to_image_mystic_sync`); **flux-dev solo existe en el backend `rest`**.

### Qué expone el MCP de Freepik (verificado)

El "Freepik Toolkit" MCP ofrece 14 herramientas: **imagen** (Mystic), **vídeo**
image-to-video (Kling), detección de IA, **iconos** y **búsqueda/descarga de stock**.
**No incluye ninguna herramienta de generación 3D** (ni text-to-3D ni image-to-3D):
confirma que la malla 3D no es posible por API/MCP de Freepik. Lo único "3D" es
descargar recursos 3D **ya existentes** del banco de stock (`search_resources` +
`download_resource_by_id`), no generarlos desde un prompt.

## 3. Uso por CLI

```bash
# Validar el JSON y ver cuántas imágenes saldrían y con qué nombres
murray3d autogen-validate examples/prompts-miniaturas.sample.json

# Prueba de humo: una sola imagen (rápido, para verificar la clave)
murray3d autogen-image "Miniature figure of Goku, 40mm base, studio photo" out.jpg --aspect 3:4

# Lote completo (rest). Reanudable: re-ejecuta y salta lo ya hecho.
murray3d autogen examples/prompts-miniaturas.sample.json --out ./salida

# Primeras pruebas: solo los 3 primeros, semilla reproducible
murray3d autogen examples/prompts-miniaturas.sample.json --limit 3 --seed 42

# Con el agente + MCP de Freepik
murray3d autogen examples/prompts-miniaturas.sample.json --backend agent --claude-model haiku
```

Opciones de `autogen`:
`--out DIR` · `--backend rest|agent` · `--model flux-dev|mystic|imagen3` ·
`--aspect 3:4` · `--limit N` · `--seed S` · `--resume/--no-resume` ·
`--make-3d` · `--claude-model` y `--mcp-config` (agente / 3D) · `--json`.

### Paso 3D (image-to-3D → GLB)

El 3D **solo** es posible por el **MCP de Magnific** (OAuth); no hay REST. Va por
un agente: `claude` + `models3d_generate`. Requisitos:

1. Autentica el MCP de Magnific en `claude` **una vez**: `/mcp` (login OAuth), o
   añádelo con su transporte ([`examples/magnific-mcp.json`](../examples/magnific-mcp.json)).
2. Ejecuta con `--make-3d` (usa `--limit`: cada modelo gasta ~580–1160 créditos):

```bash
# Prueba de humo: 1 imagen -> 1 GLB
murray3d autogen examples/prompts-miniaturas.sample.json --limit 1 --make-3d \
    --mcp-config examples/magnific-mcp.json

# Solo el 3D desde una imagen ya generada (URL pública)
murray3d autogen-3d "https://cdn.freepik/imagen.jpg" salida.glb \
    --mcp-config examples/magnific-mcp.json
```

Cada trabajo produce `<nombre>.jpg` y `<nombre>.glb`; el `manifest.json` guarda
`glb_path`/`glb_url`. Si el 3D falla, la imagen se conserva y en la siguiente
pasada (resume) se **reutiliza su URL** para reintentar solo el 3D (no re-gasta
créditos de imagen).

**Costes reales (verificados en vivo con `simulate_cost` + una generación real):**

| Paso | Modelo | Créditos |
|---|---|---|
| Imagen | flux-dev | 10 |
| Imagen | seedream-5-pro | 100 |
| 3D | tripo-p1 (rápido) | 580 |
| 3D | tripo-v31 (HQ, hasta 2M caras) | 580 |
| 3D | trellis-2 | 730 |

Una mini imagen+3D con flux-dev + tripo-p1 ≈ **590 créditos**. Un GLB de tripo-p1
sale ~570 KB / ~10k caras (cargable con trimesh → subible a 3DBundle). Detalle de
API: `models3d_generate` recibe un `creationIdentifier` (imagen ya en Magnific),
no una URL; el agente importa la imagen primero. Admite **multiview** (2–4 vistas)
para mejor malla.

Salida: una imagen por prompt en `--out` (nombre según
`automation_config.naming_convention.pattern`, p. ej.
`dragon_ball_goku_01_kamehameha_cargando.jpg`) y un `manifest.json` con el estado
de cada trabajo (`ok` / `skipped` / `error`).

## 4. Uso por GUI

Pestaña **Autogeneración**:
1. **Cargar JSON de prompts…** → se rellena la tabla (id, personaje, título,
   nombre de salida) y se autodetecta modelo/aspect del JSON.
2. Ajusta backend, modelo, aspect, límite, semilla y directorio de salida.
3. **Generar** → procesa en serie con barra de progreso y estado por fila.

## 5. Formato del JSON de prompts

```json
{
  "metadata": { "total_prompts": 400, "figures_count": 20 },
  "figures": [
    {
      "group": "Dragon Ball",
      "character": "Goku",
      "prompts": [
        {
          "id": 1, "variant": 1, "title": "Kamehameha Cargando",
          "base_size": "40mm", "base_theme": "rocky_wasteland",
          "painting_style": "Citadel",
          "prompt": "Miniature figure of Goku...",
          "tags": ["anime", "dragon_ball", "goku"]
        }
      ]
    }
  ],
  "automation_config": {
    "image_generation": {
      "recommended_model": "flux-dev",
      "aspect_ratio": "3:4",
      "negative_prompt": "blurry, low quality, ..."
    },
    "naming_convention": {
      "pattern": "{group}_{character}_{variant:02d}_{title_snake_case}"
    }
  }
}
```

Tokens del patrón de nombres: `group`, `character`, `variant` (admite `:02d`),
`id`, `title`, `title_snake_case`, `base_size`, `painting_style`, `base_theme`.

Notas de compatibilidad con la API:
- `aspect_ratio: "3:4"` se **mapea** al enum de Freepik `traditional_3_4`.
- `negative_prompt` **no** lo admiten `flux-dev`/`mystic` (se omite en esos modelos).

Hay un ejemplo válido y ejecutable en
[`examples/prompts-miniaturas.sample.json`](../examples/prompts-miniaturas.sample.json).
