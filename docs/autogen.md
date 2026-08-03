# Autogeneración desde JSON de prompts

Genera imágenes de miniaturas **en serie** a partir de un JSON con cientos de
prompts bien ordenados, usando **Freepik**. Pensado para lotes grandes: procesa
de uno en uno, escribe un `manifest.json` incremental (reanudable) y continúa
ante errores por elemento.

> **⚠️ Nota sobre "3D":** la API de Freepik/Magnific **solo genera imágenes**
> (flux-dev, Mystic, Imagen3) y upscaling; **no expone generación de malla 3D**
> (`.glb/.obj`) por API. El "3D Generator" de Freepik (Tripo/Trellis → GLB) solo
> está en la web app, no en la API. Por eso esta primera fase autogenera las
> **imágenes de referencia** de cada miniatura a partir de los prompts. La malla
> 3D real (para subir a 3DBundle) requiere un paso posterior: el 3D Generator web
> de Freepik, o una API de terceros (Tripo/Meshy) en una fase futura. El motor de
> lotes está desacoplado por un protocolo `ImageGenerator`, así que enchufar ese
> paso image-to-3D después es directo.

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

El backend `agent` requiere que el **MCP de Freepik esté añadido y autenticado**
en tu CLI `claude` (`/mcp` o `claude mcp add`), o pásalo con `--mcp-config`.

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
`--claude-model` y `--mcp-config` (backend agent) · `--json`.

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
