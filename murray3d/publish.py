from __future__ import annotations

import shutil
from pathlib import Path

from .ai import generate_metadata, generate_pack_metadata
from .models import GeneratedMeta, GeneratedPackMeta, Model3D, Pack
from .render import DEFAULT_ANGLES, render_screenshots


def prepare_publish(client, settings, model_id, angles=None,
                    render_fn=None, ai_fn=None, model=None
                    ) -> tuple[GeneratedMeta, list[Path]]:
    render_fn = render_fn or render_screenshots
    ai_fn = ai_fn or generate_metadata

    model3d = client.get_model(model_id)
    ext = (model3d.file_format or "glb").lstrip(".")
    work = settings.shots_dir / str(model_id)
    work.mkdir(parents=True, exist_ok=True)
    src = client.download_model(model_id, work / f"model.{ext}")
    shots = render_fn(src, work, settings.cache_dir, angles) if angles is not None \
        else render_fn(src, work, settings.cache_dir)
    ai_kwargs = {"model": model} if model is not None else {}
    meta = ai_fn(shots, settings.known_categories, **ai_kwargs)
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


def prepare_pack_publish(client, settings, pack_id, render_fn=None, ai_fn=None,
                         model=None) -> tuple[GeneratedPackMeta, list[Path], Pack]:
    """Renderiza una imagen por modelo del pack y genera metadatos del bundle."""
    render_fn = render_fn or render_screenshots
    ai_fn = ai_fn or generate_pack_metadata

    pack = client.get_pack(pack_id)
    if not pack.model_ids:
        raise ValueError("El pack no tiene modelos; añade modelos antes de publicar con IA.")

    pack_dir = settings.shots_dir / f"pack_{pack_id}"
    pack_dir.mkdir(parents=True, exist_ok=True)
    shots: list[Path] = []
    titles: list[str] = []
    for i, mid in enumerate(pack.model_ids):
        m = client.get_model(mid)
        titles.append(m.title)
        ext = (m.file_format or "glb").lstrip(".")
        mdir = pack_dir / str(mid)
        mdir.mkdir(parents=True, exist_ok=True)
        src = client.download_model(mid, mdir / f"model.{ext}")
        rendered = render_fn(src, mdir, settings.cache_dir, [DEFAULT_ANGLES[0]])
        # Copiar la única imagen a un nombre único dentro del dir del pack.
        dest = pack_dir / f"cover_{i:02d}.png"
        shutil.copy2(rendered[0], dest)
        shots.append(dest)

    ai_kwargs = {"model": model} if model is not None else {}
    meta = ai_fn(shots, titles, **ai_kwargs)
    return meta, shots, pack


def commit_pack_publish(client, pack_id, meta: GeneratedPackMeta,
                        publish: bool = True) -> Pack:
    return client.update_pack(
        pack_id,
        title=meta.title,
        description=meta.description,
        tags=meta.tags,
        price_eur=meta.price_eur,
        published=publish,
    )
