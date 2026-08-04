# Autogeneración desde JSON de prompts

Genera imágenes de miniaturas **y su malla 3D** en serie a partir de un JSON con
cientos de prompts bien ordenados. Pensado para lotes grandes: procesa de uno en
uno, escribe un `manifest.json` incremental (reanudable) y continúa ante errores
por elemento.

**Arquitectura:** igual que "Publicar con IA", murray3d **no llama a ninguna API
REST**. Reutiliza el binario **`claude`** conectado al **MCP de Magnific**:
`images_generate` para la imagen y `models3d_generate` para el 3D. Un solo camino,
sin API keys aparte.

> **Pipeline:** prompt → **imagen** (`images_generate`) → **malla 3D**
> (`models3d_generate` → GLB, con `--make-3d`) → subir a 3DBundle.
> ⚠️ Cada 3D gasta **~580 créditos**; usa `--make-3d` con `--limit`.

## 1. Requisito: el MCP de Magnific en `claude`

La autogeneración usa el MCP de Magnific a través del CLI `claude`. Autentícalo
**una vez** (login OAuth):

```bash
# Opción A: connector de claude.ai
/mcp            # y autentica "Magnific"

# Opción B: añadir el servidor MCP al CLI
claude mcp add --transport http magnific https://mcp.magnific.com
claude mcp list # debe salir "magnific" como connected
```

Alternativa: pasar el transporte con `--mcp-config`
([`examples/magnific-mcp.json`](../examples/magnific-mcp.json)) — el login OAuth
sigue siendo necesario una vez. No hace falta ninguna API key: el gasto va por
**créditos** de tu cuenta Magnific (compruébalo con la herramienta `account_balance`
del MCP).

## 2. Modelos disponibles

- **Imagen** (`--model`, `mode` de Magnific): `flux-dev` (barato, ~10 cr),
  `seedream-5-pro` (~100 cr), `mystic`, `imagen3`, etc. Default: el
  `recommended_model` del JSON.
- **3D** (`models3d_generate`): `tripo-p1` (default, rápido), `tripo-v31` (HQ,
  hasta 2M caras), `trellis-2`. Salida **GLB**. Admite **multiview** (2–4 vistas).

## 3. Uso por CLI

```bash
# Validar el JSON y ver cuántas imágenes saldrían y con qué nombres (sin gasto)
murray3d autogen-validate examples/prompts-miniaturas.sample.json

# Prueba de humo: una sola imagen (rápido, para verificar el MCP)
murray3d autogen-image "Miniature figure of Goku, 40mm base, studio photo" out.jpg --aspect 3:4

# Lote de imágenes. Reanudable: re-ejecuta y salta lo ya hecho.
murray3d autogen examples/prompts-miniaturas.sample.json --out ./salida

# Primeras pruebas: solo los 3 primeros, semilla reproducible
murray3d autogen examples/prompts-miniaturas.sample.json --limit 3 --seed 42
```

Opciones de `autogen`:
`--out DIR` · `--model flux-dev|seedream-5-pro|…` · `--aspect 3:4` · `--limit N` ·
`--seed S` · `--resume/--no-resume` · `--make-3d` · `--claude-model` ·
`--mcp-config` · `--json`.

### Paso 3D (image-to-3D → GLB)

Añade `--make-3d`: tras cada imagen, `models3d_generate` produce el `.glb`.
Usa `--limit` (cada modelo gasta ~580 créditos):

```bash
# Prueba de humo: 1 imagen -> 1 GLB
murray3d autogen examples/prompts-miniaturas.sample.json --limit 1 --make-3d

# Solo el 3D desde una imagen ya generada (URL pública)
murray3d autogen-3d "https://.../imagen.jpg" salida.glb
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
2. Ajusta modelo, aspect, límite, semilla, **También 3D** y directorio de salida.
3. **Generar** → procesa en serie con barra de progreso y estado por fila (con 3D,
   pide confirmación por el coste en créditos).

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

Notas:
- `aspect_ratio: "3:4"` se pasa tal cual a `images_generate` (Magnific acepta
  `3:4`, `1:1`, `16:9`, `2:3`, etc.).
- `recommended_model` es el `mode` de Magnific (`flux-dev`, `seedream-5-pro`…).
- `negative_prompt` es orientativo; el agente decide si lo aplica según el modelo.

Hay un ejemplo válido y ejecutable en
[`examples/prompts-miniaturas.sample.json`](../examples/prompts-miniaturas.sample.json).
