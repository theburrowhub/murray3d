from __future__ import annotations

import json as _json
from contextlib import contextmanager
from pathlib import Path

import typer

from .agent_gen import AgentGenError
from .ai import AiError
from .api import ApiError, Client
from .config import ConfigError, load_settings
from .convert import ConvertError
from .mesh_gen import MeshGenError
from .prompts import PromptError
from .render import RenderError

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
    except (ApiError, ConfigError, RenderError, AiError, ConvertError,
            PromptError, AgentGenError, MeshGenError) as e:
        typer.echo(str(e))
        raise typer.Exit(code=1)


def _make_generator(settings, *, claude_model: str | None = None,
                    mcp_config: str | None = None):
    """Construye el generador de imágenes (agente `claude` + MCP de Magnific)."""
    from .autogen import build_image_generator
    return build_image_generator(settings, claude_model=claude_model,
                                 mcp_config=mcp_config)


def _make_mesh_generator(settings, *, claude_model: str | None = None,
                         mcp_config: str | None = None):
    """Construye el generador de malla 3D (agente + MCP de Magnific)."""
    from .autogen import build_mesh_generator
    return build_mesh_generator(settings, claude_model=claude_model,
                                mcp_config=mcp_config)


@contextmanager
def _session():
    """Construye el cliente con manejo de errores y garantiza su cierre.

    ``ConfigError``/``ApiError`` durante la construcción (p.ej. sin API key
    configurada) se imprimen y salen con código 1, en lugar de escapar como
    traceback. El cliente se cierra siempre, incluso en el camino de error.
    """
    try:
        c = _client()
    except (ApiError, ConfigError) as e:
        typer.echo(str(e))
        raise typer.Exit(code=1)
    try:
        yield c
    finally:
        c.close()


@app.command()
def whoami(json_out: bool = typer.Option(False, "--json")):
    with _session() as c:
        prof = _run(c.whoami)
        _dump(prof.model_dump())


@models_app.command("list")
def models_list(q: str = None, tag: str = None, category: str = None,
                mine: bool = False, published: bool = typer.Option(None, "--published/--all"),
                limit: int = 100, json_out: bool = typer.Option(False, "--json")):
    with _session() as c:
        items = _run(lambda: c.list_models(q=q, tag=tag, category=category,
                                           only_published=published, mine=mine, limit=limit))
        if json_out:
            _dump([m.model_dump() for m in items])
        else:
            for m in items:
                flag = "✔" if m.published else "·"
                typer.echo(f"{flag} [{m.id}] {m.title}  ({m.category or '-'})")


@models_app.command("show")
def models_show(model_id: int, json_out: bool = typer.Option(False, "--json")):
    with _session() as c:
        m = _run(lambda: c.get_model(model_id))
        _dump(m.model_dump())


@models_app.command("upload")
def models_upload(file: Path, title: str, description: str = "", category: str = None,
                  tags: str = "", price: float = None):
    with _session() as c:
        tag_list = [t.strip() for t in tags.split(",") if t.strip()]
        m = _run(lambda: c.upload_model(file, title=title, description=description,
                                        category=category, tags=tag_list, price_eur=price))
        _dump(m.model_dump())


@models_app.command("edit")
def models_edit(model_id: int, title: str = None, description: str = None,
                category: str = None, tags: str = None, price: float = None,
                published: bool = typer.Option(None, "--published/--unpublished")):
    with _session() as c:
        fields = {}
        if title is not None: fields["title"] = title
        if description is not None: fields["description"] = description
        if category is not None: fields["category"] = category
        if tags is not None: fields["tags"] = [t.strip() for t in tags.split(",") if t.strip()]
        if price is not None: fields["price_eur"] = price
        if published is not None: fields["published"] = published
        m = _run(lambda: c.update_model(model_id, **fields))
        _dump(m.model_dump())


@models_app.command("delete")
def models_delete(model_id: int, yes: bool = typer.Option(False, "--yes")):
    if not yes:
        typer.confirm(f"¿Borrar el modelo {model_id}?", abort=True)
    with _session() as c:
        _run(lambda: c.delete_model(model_id))
        typer.echo(f"Borrado {model_id}")


@models_app.command("thumbnail")
def models_thumbnail(model_id: int, image: Path):
    with _session() as c:
        m = _run(lambda: c.set_thumbnail(model_id, image))
        _dump(m.model_dump())


@packs_app.command("list")
def packs_list(q: str = None, json_out: bool = typer.Option(False, "--json")):
    with _session() as c:
        items = _run(lambda: c.list_packs(q=q))
        if json_out:
            _dump([p.model_dump() for p in items])
        else:
            for p in items:
                typer.echo(f"[{p.id}] {p.title}  ({len(p.model_ids)} modelos)")


@packs_app.command("show")
def packs_show(pack_id: int, json_out: bool = typer.Option(False, "--json")):
    with _session() as c:
        _dump(_run(lambda: c.get_pack(pack_id)).model_dump())


@packs_app.command("create")
def packs_create(title: str, description: str = "", tags: str = "",
                 price: float = None, model_ids: str = ""):
    with _session() as c:
        tag_list = [t.strip() for t in tags.split(",") if t.strip()]
        ids = [int(x) for x in model_ids.split(",") if x.strip()]
        p = _run(lambda: c.create_pack(title, description=description, tags=tag_list,
                                       price_eur=price, model_ids=ids))
        _dump(p.model_dump())


@packs_app.command("edit")
def packs_edit(pack_id: int, title: str = None, description: str = None,
               tags: str = None, price: float = None,
               published: bool = typer.Option(None, "--published/--unpublished")):
    with _session() as c:
        fields = {}
        if title is not None: fields["title"] = title
        if description is not None: fields["description"] = description
        if tags is not None: fields["tags"] = [t.strip() for t in tags.split(",") if t.strip()]
        if price is not None: fields["price_eur"] = price
        if published is not None: fields["published"] = published
        _dump(_run(lambda: c.update_pack(pack_id, **fields)).model_dump())


@packs_app.command("delete")
def packs_delete(pack_id: int, yes: bool = typer.Option(False, "--yes")):
    if not yes:
        typer.confirm(f"¿Borrar el pack {pack_id}?", abort=True)
    with _session() as c:
        _run(lambda: c.delete_pack(pack_id))
        typer.echo(f"Borrado pack {pack_id}")


@packs_app.command("add-model")
def packs_add_model(pack_id: int, model_ids: list[int]):
    with _session() as c:
        p = _run(lambda: c.add_models_to_pack(pack_id, list(model_ids)))
        _dump(p.model_dump())


@app.command()
def render(model_id: int, out: Path = None, angles: int = None):
    from .render import DEFAULT_ANGLES, render_screenshots
    with _session() as c:
        settings = c.settings
        m = _run(lambda: c.get_model(model_id))
        ext = (m.file_format or "glb").lstrip(".")
        work = out or (settings.shots_dir / str(model_id))
        Path(work).mkdir(parents=True, exist_ok=True)
        src = _run(lambda: c.download_model(model_id, Path(work) / f"model.{ext}"))
        angle_list = DEFAULT_ANGLES[:angles] if angles is not None else None
        shots = render_screenshots(src, Path(work), settings.cache_dir, angles=angle_list)
        _dump([str(s) for s in shots])


@app.command("ai-generate")
def ai_generate(model_id: int, model: str = typer.Option(None, "--model",
                help="Modelo de Claude: opus|sonnet|haiku|fable o nombre completo")):
    from .publish import prepare_publish
    with _session() as c:
        meta, shots = _run(lambda: prepare_publish(c, c.settings, model_id, model=model))
        _dump({"meta": meta.model_dump(), "shots": [str(s) for s in shots]})


@app.command()
def publish(model_id: int, title: str = None, description: str = None,
            category: str = None, tags: str = None, price: float = None,
            thumbnail: Path = None):
    with _session() as c:
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


@app.command("ai-publish")
def ai_publish(model_id: int, yes: bool = typer.Option(False, "--yes"),
               model: str = typer.Option(None, "--model",
               help="Modelo de Claude: opus|sonnet|haiku|fable o nombre completo")):
    from .publish import commit_publish, prepare_publish
    with _session() as c:
        meta, shots = _run(lambda: prepare_publish(c, c.settings, model_id, model=model))
        typer.echo(_json.dumps(meta.model_dump(), ensure_ascii=False, indent=2))
        if not yes:
            typer.confirm("¿Publicar con estos metadatos?", abort=True)
        m = _run(lambda: commit_publish(c, model_id, meta, shots))
        _dump(m.model_dump())


@app.command("batch-upload")
def batch_upload_cmd(paths: list[Path],
                     json_out: bool = typer.Option(False, "--json")):
    """Sube por lotes todos los .glb/.obj/.stl de las rutas dadas (ficheros o
    carpetas) como BORRADOR. Procesa de uno en uno y por streaming (soporta
    lotes de >1GB). Un error en un fichero no aborta el lote."""
    from .batch import batch_upload, collect_files
    files = collect_files(paths)
    if not files:
        typer.echo("No se encontraron ficheros .glb/.obj/.stl en las rutas dadas.")
        raise typer.Exit(code=1)
    with _session() as c:
        typer.echo(f"Subiendo {len(files)} ficheros como borrador…")

        def prog(i, total, name, phase):
            typer.echo(f"  [{i + 1}/{total}] {phase}: {name}")

        results = batch_upload(c, files, on_progress=prog)
        ok = [r for r in results if r["ok"]]
        fail = [r for r in results if not r["ok"]]
        if json_out:
            _dump(results)
        else:
            typer.echo(f"Hecho: {len(ok)} subidos, {len(fail)} con error.")
            for r in ok:
                typer.echo(f"  ✔ [{r['id']}] {r['file']}")
            for r in fail:
                typer.echo(f"  ✗ ERROR {r['file']}: {r['error']}")
        if fail:
            raise typer.Exit(code=1)


@app.command("batch-ai-publish")
def batch_ai_publish_cmd(model_ids: list[int] = typer.Argument(None),
                         all_drafts: bool = typer.Option(False, "--all-drafts"),
                         yes: bool = typer.Option(False, "--yes"),
                         model: str = typer.Option(None, "--model",
                             help="Modelo de Claude: opus|sonnet|haiku|fable o nombre completo"),
                         json_out: bool = typer.Option(False, "--json")):
    """Ejecuta el flujo completo "Publicar con IA" para un lote de modelos.

    Pasa IDs, o usa --all-drafts para tomar todos tus borradores. Secuencial;
    limpia los temporales de cada modelo tras publicarlo."""
    from .batch import batch_ai_publish
    with _session() as c:
        ids = list(model_ids or [])
        if all_drafts:
            mine = _run(lambda: c.list_models(only_published=False, mine=True, limit=200))
            ids = [m.id for m in mine if not m.published]
        if not ids:
            typer.echo("No hay modelos que publicar (pasa IDs o usa --all-drafts).")
            raise typer.Exit(code=1)
        typer.echo(f"Se publicarán con IA {len(ids)} modelos: {ids}")
        if not yes:
            typer.confirm("¿Continuar?", abort=True)

        def prog(i, total, mid, phase):
            typer.echo(f"  [{i + 1}/{total}] {phase} modelo {mid}…")

        results = batch_ai_publish(c, c.settings, ids, model=model, on_progress=prog)
        ok = [r for r in results if r["ok"]]
        fail = [r for r in results if not r["ok"]]
        if json_out:
            _dump(results)
        else:
            typer.echo(f"Hecho: {len(ok)} publicados, {len(fail)} con error.")
            for r in ok:
                typer.echo(f"  ✔ [{r['id']}] {r['title']}")
            for r in fail:
                typer.echo(f"  ✗ ERROR modelo {r['id']}: {r['error']}")
        if fail:
            raise typer.Exit(code=1)


@app.command("autogen-validate")
def autogen_validate(prompts_file: Path,
                     json_out: bool = typer.Option(False, "--json")):
    """Valida un JSON de prompts y muestra cuántos trabajos saldrían y sus nombres."""
    from .prompts import iter_jobs, load_prompt_doc
    doc = _run(lambda: load_prompt_doc(prompts_file))
    jobs = iter_jobs(doc)
    if json_out:
        _dump({
            "figures": len(doc.figures),
            "jobs": len(jobs),
            "model": doc.automation_config.image_generation.recommended_model,
            "aspect_ratio": doc.automation_config.image_generation.aspect_ratio,
            "names": [j.output_name for j in jobs],
        })
        return
    ig = doc.automation_config.image_generation
    typer.echo(f"Figuras: {len(doc.figures)}  ·  Trabajos (prompts): {len(jobs)}")
    typer.echo(f"Modelo: {ig.recommended_model}  ·  aspect_ratio: {ig.aspect_ratio}")
    typer.echo("Ejemplos de nombres de salida:")
    for j in jobs[:10]:
        typer.echo(f"  [{j.id}] {j.character} → {j.output_name}.jpg")
    if len(jobs) > 10:
        typer.echo(f"  … y {len(jobs) - 10} más")


@app.command("autogen")
def autogen_cmd(prompts_file: Path,
                out: Path = typer.Option(None, "--out", help="Directorio de salida"),
                model: str = typer.Option(None, "--model",
                    help="Modelo de imagen (mode de Magnific): flux-dev|seedream-5-pro|… "
                         "(default: el del JSON)"),
                aspect: str = typer.Option(None, "--aspect",
                    help="Relación de aspecto, p. ej. 3:4 (default: la del JSON)"),
                limit: int = typer.Option(None, "--limit", help="Procesa solo los N primeros"),
                seed: int = typer.Option(None, "--seed", help="Semilla base reproducible"),
                resume: bool = typer.Option(True, "--resume/--no-resume",
                    help="Salta los que ya tengan imagen (o GLB con --make-3d)"),
                make_3d: bool = typer.Option(False, "--make-3d",
                    help="Genera también la malla 3D (.glb) vía `models3d_generate`"),
                claude_model: str = typer.Option(None, "--claude-model",
                    help="Modelo de Claude para el agente: opus|sonnet|haiku|fable"),
                mcp_config: str = typer.Option(None, "--mcp-config",
                    help="Fichero JSON de configuración del MCP (si no está ya en `claude`)"),
                json_out: bool = typer.Option(False, "--json")):
    """Autogenera una imagen por prompt del JSON (procesa en serie, reanudable).

    Usa el CLI `claude` + el MCP de Magnific (`images_generate`). Diseñado para
    lotes: uno a uno, manifest.json incremental, continúa ante errores. Con
    `--make-3d` añade el paso image-to-3D (GLB) por `models3d_generate`.

    ⚠️ `--make-3d` gasta ~580 créditos por modelo: úsalo con `--limit`.
    """
    from .autogen import run_autogen, summarize
    from .prompts import load_prompt_doc

    doc = _run(lambda: load_prompt_doc(prompts_file))
    settings = _run(lambda: load_settings(require_api_key=False))
    out_dir = Path(out) if out else (settings.autogen_dir / Path(prompts_file).stem)
    gen = _run(lambda: _make_generator(settings, claude_model=claude_model,
                                       mcp_config=mcp_config))
    mesh = None
    if make_3d:
        mesh = _run(lambda: _make_mesh_generator(settings, claude_model=claude_model,
                                                 mcp_config=mcp_config))

    typer.echo(f"Autogeneración{' +3D' if make_3d else ''} → {out_dir}")

    def prog(i, total, job, phase):
        typer.echo(f"  [{i + 1}/{total}] {phase}: {job.output_name}")

    try:
        results = run_autogen(doc, gen, out_dir, on_progress=prog, resume=resume,
                              limit=limit, model=model, aspect_ratio=aspect, seed=seed,
                              make_3d=make_3d, mesh_generator=mesh)
    finally:
        close = getattr(gen, "close", None)
        if callable(close):
            close()

    s = summarize(results)
    if json_out:
        _dump({"summary": s, "out_dir": str(out_dir), "results": results})
    else:
        typer.echo(f"Hecho: {s['ok']} generadas, {s['skipped']} saltadas, "
                   f"{s['errors']} con error.  (manifest en {out_dir}/manifest.json)")
        for r in results:
            if r["status"] == "error":
                typer.echo(f"  ✗ [{r['id']}] {r['name']}: {r['error']}")
    if s["errors"]:
        raise typer.Exit(code=1)


@app.command("autogen-image")
def autogen_image(prompt: str, out: Path,
                  model: str = typer.Option("flux-dev", "--model",
                      help="mode de Magnific: flux-dev|seedream-5-pro|…"),
                  aspect: str = typer.Option("3:4", "--aspect"),
                  seed: int = typer.Option(None, "--seed"),
                  claude_model: str = typer.Option(None, "--claude-model"),
                  mcp_config: str = typer.Option(None, "--mcp-config")):
    """Prueba de humo: genera UNA imagen desde un prompt y la guarda en `out`."""
    settings = _run(lambda: load_settings(require_api_key=False))
    gen = _run(lambda: _make_generator(settings, claude_model=claude_model,
                                       mcp_config=mcp_config))
    try:
        urls = _run(lambda: gen.generate(prompt, model=model, aspect_ratio=aspect,
                                         seed=seed))
        _run(lambda: gen.download(urls[0], Path(out)))
    finally:
        close = getattr(gen, "close", None)
        if callable(close):
            close()
    _dump({"url": urls[0], "path": str(out)})


@app.command("autogen-3d")
def autogen_3d(image_url: str, out: Path,
               claude_model: str = typer.Option(None, "--claude-model"),
               mcp_config: str = typer.Option(None, "--mcp-config")):
    """Prueba de humo 3D: genera un .glb desde la URL de una imagen y lo guarda.

    Vía agente + MCP de Magnific (`models3d_generate`). ⚠️ Gasta ~580–1160 créditos.
    """
    settings = _run(lambda: load_settings(require_api_key=False))
    mesh = _run(lambda: _make_mesh_generator(settings, claude_model=claude_model,
                                             mcp_config=mcp_config))
    urls = _run(lambda: mesh.generate_from_image(image_url))
    _run(lambda: mesh.download(urls[0], Path(out)))
    _dump({"model_url": urls[0], "path": str(out)})


@app.command()
def gui():
    from .gui.app import run_gui
    run_gui()


if __name__ == "__main__":
    app()
