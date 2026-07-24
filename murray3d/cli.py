from __future__ import annotations

import json as _json
from contextlib import contextmanager
from pathlib import Path

import typer

from .ai import AiError
from .api import ApiError, Client
from .config import ConfigError, load_settings
from .convert import ConvertError
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
    except (ApiError, ConfigError, RenderError, AiError, ConvertError) as e:
        typer.echo(str(e))
        raise typer.Exit(code=1)


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
def ai_generate(model_id: int):
    from .publish import prepare_publish
    with _session() as c:
        meta, shots = _run(lambda: prepare_publish(c, c.settings, model_id))
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
def ai_publish(model_id: int, yes: bool = typer.Option(False, "--yes")):
    from .publish import commit_publish, prepare_publish
    with _session() as c:
        meta, shots = _run(lambda: prepare_publish(c, c.settings, model_id))
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

        results = batch_ai_publish(c, c.settings, ids, on_progress=prog)
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


@app.command()
def gui():
    from .gui.app import run_gui
    run_gui()


if __name__ == "__main__":
    app()
