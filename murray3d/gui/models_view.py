from __future__ import annotations

from pathlib import Path

from .workers import make_worker


def build_models_view(client, settings):
    from PySide6.QtCore import QObject, Qt, QThreadPool, Signal
    from PySide6.QtWidgets import (
        QApplication, QDoubleSpinBox, QFileDialog, QHBoxLayout, QLabel, QLineEdit,
        QListWidget, QListWidgetItem, QMessageBox, QPushButton, QSplitter, QTextEdit,
        QVBoxLayout, QWidget,
    )

    from .publish_dialog import open_publish_dialog
    from .viewer import build_viewer_widget

    ModelViewer = build_viewer_widget()
    pool = QThreadPool.globalInstance()

    root = QWidget()
    outer = QVBoxLayout(root)

    # --- barra superior ---
    top = QHBoxLayout()
    search = QLineEdit(); search.setPlaceholderText("Buscar en mis modelos…")
    btn_search = QPushButton("Buscar")
    btn_new = QPushButton("＋ Nuevo modelo…")
    btn_batch = QPushButton("Subir por lotes…")
    btn_batch_ai = QPushButton("Publicar borradores con IA")
    btn_refresh = QPushButton("Recargar")
    top.addWidget(search); top.addWidget(btn_search)
    top.addStretch()
    top.addWidget(btn_new); top.addWidget(btn_batch); top.addWidget(btn_batch_ai)
    top.addWidget(btn_refresh)
    outer.addLayout(top)

    split = QSplitter(Qt.Horizontal)
    outer.addWidget(split, 1)

    listw = QListWidget()
    split.addWidget(listw)

    # --- panel derecho ---
    right = QWidget(); rl = QVBoxLayout(right)
    header = QLabel("")
    header.setStyleSheet("font-weight: bold; padding: 2px 0;")
    viewer = ModelViewer()
    title = QLineEdit(); title.setPlaceholderText("Título")
    category = QLineEdit(); category.setPlaceholderText("Categoría")
    tags = QLineEdit(); tags.setPlaceholderText("tags separadas por comas")
    price = QDoubleSpinBox(); price.setMaximum(100000); price.setPrefix("€ ")
    desc = QTextEdit(); desc.setPlaceholderText("Descripción")

    rl.addWidget(header)
    rl.addWidget(viewer, 1)
    rl.addWidget(title)
    edit_fields = [category, tags, price, desc]
    for w in edit_fields:
        rl.addWidget(w)

    # Botonera del modo NUEVO (crear)
    new_box = QWidget(); nb = QHBoxLayout(new_box); nb.setContentsMargins(0, 0, 0, 0)
    btn_upload_confirm = QPushButton("Subir como borrador")
    btn_cancel_new = QPushButton("Cancelar")
    nb.addStretch(); nb.addWidget(btn_cancel_new); nb.addWidget(btn_upload_confirm)
    rl.addWidget(new_box)

    # Botonera del modo EDITAR
    edit_box = QWidget(); eb = QHBoxLayout(edit_box); eb.setContentsMargins(0, 0, 0, 0)
    btn_save = QPushButton("Guardar cambios")
    btn_thumb = QPushButton("Miniatura…")
    btn_delete = QPushButton("Borrar")
    btn_ai = QPushButton("Publicar con IA")
    for b in (btn_save, btn_thumb, btn_delete, btn_ai):
        eb.addWidget(b)
    rl.addWidget(edit_box)

    status = QLabel("")
    rl.addWidget(status)
    split.addWidget(right)
    split.setSizes([320, 700])

    state = {"models": [], "current": None, "pending_upload": None, "mode": None}

    def set_status(msg):
        status.setText(msg)

    def run_bg(fn, on_ok, busy="Trabajando…", on_error=None):
        set_status(busy)
        QApplication.setOverrideCursor(Qt.WaitCursor)
        w = make_worker(fn)

        def _ok(v):
            QApplication.restoreOverrideCursor()
            set_status("Listo")
            on_ok(v)

        def _fail(e):
            QApplication.restoreOverrideCursor()
            set_status("Error")
            if on_error is not None:
                on_error()
            QMessageBox.critical(root, "Error", e)

        w.signals.finished.connect(_ok)
        w.signals.failed.connect(_fail)
        pool.start(w)

    # Emisor de progreso para lotes: la señal se emite desde el hilo worker y se
    # entrega (en cola) al hilo principal, donde actualiza el estado.
    class _Prog(QObject):
        tick = Signal(str)

    prog = _Prog()
    prog.tick.connect(set_status)
    state["_prog"] = prog  # mantener referencia viva

    def set_mode(mode, header_text=""):
        """mode: 'empty' | 'new' | 'edit'. Muestra/oculta lo relevante."""
        state["mode"] = mode
        is_new = mode == "new"
        is_edit = mode == "edit"
        header.setText(header_text)
        title.setVisible(is_new or is_edit)
        for w in edit_fields:
            w.setVisible(is_edit)
        new_box.setVisible(is_new)
        edit_box.setVisible(is_edit)

    # ---------------- listar / editar ----------------
    def refresh():
        q = search.text().strip() or None
        # Preserva la selección actual al recargar (salvo que ya se pidiera otra).
        if "select_id" not in state and state.get("current"):
            state["select_id"] = state["current"].id
        # mine=True: solo MIS modelos. only_published=False: incluye borradores.
        run_bg(lambda: client.list_models(q=q, only_published=False, mine=True, limit=200),
               populate, "Cargando mis modelos…")

    def populate(models):
        state["models"] = models
        target = state.pop("select_id", None)
        target_row = -1
        listw.blockSignals(True)
        listw.clear()
        for i, m in enumerate(models):
            flag = "✔" if m.published else "○"  # ✔ publicado · ○ borrador
            it = QListWidgetItem(f"{flag} [{m.id}] {m.title}")
            it.setData(Qt.UserRole, m.id)
            listw.addItem(it)
            if m.id == target:
                target_row = i
        listw.blockSignals(False)
        if target_row >= 0:
            listw.setCurrentRow(target_row)  # -> load_selected (modo editar)
        else:
            state["current"] = None
            if not models:
                set_mode("empty", "No tienes modelos. Pulsa «＋ Nuevo modelo…» para subir uno.")
            elif state["mode"] != "new":
                set_mode("empty", "Selecciona un modelo de la lista para editarlo.")

    def load_selected():
        it = listw.currentItem()
        if not it:
            return
        mid = it.data(Qt.UserRole)
        m = next((x for x in state["models"] if x.id == mid), None)
        if not m:
            return
        state["current"] = m
        state["pending_upload"] = None
        title.setText(m.title)
        category.setText(m.category or "")
        tags.setText(",".join(m.tags))
        price.setValue(m.price_eur or 0)
        desc.setPlainText(m.description or "")
        estado = "publicado" if m.published else "borrador"
        set_mode("edit", f"Editando  [{m.id}]  ·  {estado}")

        def dl():
            ext = (m.file_format or "glb").lstrip(".")
            dest = settings.shots_dir / str(m.id) / f"model.{ext}"
            dest.parent.mkdir(parents=True, exist_ok=True)
            return client.download_model(m.id, dest)

        run_bg(dl, lambda path: viewer.show_model(path, settings.cache_dir), "Cargando 3D…")

    def save():
        m = state["current"]
        if not m or state["mode"] != "edit":
            return
        fields = dict(title=title.text(), description=desc.toPlainText(),
                      category=category.text() or None,
                      tags=[t.strip() for t in tags.text().split(",") if t.strip()],
                      price_eur=price.value() or None)
        state["select_id"] = m.id
        run_bg(lambda: client.update_model(m.id, **fields), lambda _: refresh(),
               "Guardando cambios…")

    def set_thumb():
        m = state["current"]
        if not m or state["mode"] != "edit":
            return
        path, _ = QFileDialog.getOpenFileName(
            root, "Miniatura", "", "Imágenes (*.png *.jpg *.jpeg *.webp)")
        if not path:
            return
        state["select_id"] = m.id
        run_bg(lambda: client.set_thumbnail(m.id, Path(path)), lambda _: refresh(),
               "Subiendo miniatura…")

    def delete():
        m = state["current"]
        if not m or state["mode"] != "edit":
            return
        if QMessageBox.question(root, "Borrar", f"¿Borrar '{m.title}'?") != QMessageBox.Yes:
            return

        def _ok(_):
            state["current"] = None
            viewer.clear()
            refresh()

        run_bg(lambda: client.delete_model(m.id), _ok, "Borrando…")

    def publish_ai():
        m = state["current"]
        if not m or state["mode"] != "edit":
            return

        def done():
            state["select_id"] = m.id
            refresh()

        open_publish_dialog(root, client, settings, m.id, on_done=done)

    # ---------------- crear (flujo separado) ----------------
    def new_model():
        path, _ = QFileDialog.getOpenFileName(
            root, "Elegir modelo 3D nuevo", "", "Modelos 3D (*.glb *.obj *.stl)")
        if not path:
            return
        p = Path(path)
        state["pending_upload"] = p
        state["current"] = None
        listw.blockSignals(True)
        listw.setCurrentItem(None)
        listw.blockSignals(False)
        title.setText(p.stem)
        btn_upload_confirm.setEnabled(True)
        btn_cancel_new.setEnabled(True)
        set_mode("new", f"Nuevo modelo (sin subir):  {p.name}")
        set_status("Revisa el modelo en el visor y pulsa «Subir como borrador».")
        try:
            viewer.show_model(p, settings.cache_dir)  # preview local, sin subir
        except Exception:  # noqa: BLE001
            set_status(f"No se pudo previsualizar {p.name}, pero puedes subirlo igual.")

    def confirm_upload():
        p = state.get("pending_upload")
        if not p or state["mode"] != "new":
            return
        new_title = title.text().strip() or p.stem
        btn_upload_confirm.setEnabled(False)
        btn_cancel_new.setEnabled(False)

        def _do():
            m = client.upload_model(p, title=new_title)
            # La API publica al subir; lo dejamos como BORRADOR hasta que
            # "Publicar con IA" genere metadatos + miniatura y publique.
            return client.update_model(m.id, published=False)

        def _ok(m):
            btn_upload_confirm.setEnabled(True)
            btn_cancel_new.setEnabled(True)
            state["pending_upload"] = None
            state["select_id"] = m.id  # se seleccionará -> modo editar
            set_status(f"Subido como borrador [{m.id}]. Usa «Publicar con IA» para completarlo.")
            refresh()

        def _err():
            btn_upload_confirm.setEnabled(True)
            btn_cancel_new.setEnabled(True)

        run_bg(_do, _ok, f"Subiendo {p.name}…", on_error=_err)

    def cancel_new():
        state["pending_upload"] = None
        viewer.clear()
        set_mode("empty", "Selecciona un modelo de la lista o pulsa «＋ Nuevo modelo…».")
        set_status("Creación cancelada.")

    # ---------------- lotes ----------------
    def _set_batch_enabled(on):
        for b in (btn_new, btn_batch, btn_batch_ai, btn_refresh):
            b.setEnabled(on)

    def batch_upload_files():
        paths, _ = QFileDialog.getOpenFileNames(
            root, "Elegir modelos para subir por lotes", "",
            "Modelos 3D (*.glb *.obj *.stl)")
        if not paths:
            return
        from ..batch import batch_upload
        files = [Path(p) for p in paths]
        _set_batch_enabled(False)

        def _do():
            return batch_upload(
                client, files,
                on_progress=lambda i, t, name, ph: prog.tick.emit(f"[{i + 1}/{t}] {ph}: {name}"))

        def _ok(results):
            _set_batch_enabled(True)
            ok = [r for r in results if r["ok"]]
            fail = [r for r in results if not r["ok"]]
            msg = f"Subidos como borrador: {len(ok)}.  Errores: {len(fail)}."
            if fail:
                msg += "\n\n" + "\n".join(f"• {r['file']}: {r['error']}" for r in fail[:10])
            QMessageBox.information(root, "Subida por lotes", msg)
            refresh()

        run_bg(_do, _ok, f"Subiendo {len(files)} ficheros por lotes…",
               on_error=lambda: _set_batch_enabled(True))

    def batch_publish_drafts():
        drafts = [m for m in state["models"] if not m.published]
        if not drafts:
            QMessageBox.information(root, "Publicar con IA",
                                    "No tienes borradores que publicar.")
            return
        ids = [m.id for m in drafts]
        if QMessageBox.question(
                root, "Publicar borradores con IA",
                f"Se publicarán con IA {len(ids)} borradores (render + Claude por cada "
                f"uno). Puede tardar. ¿Continuar?") != QMessageBox.Yes:
            return
        from ..batch import batch_ai_publish
        _set_batch_enabled(False)

        def _do():
            return batch_ai_publish(
                client, settings, ids,
                on_progress=lambda i, t, mid, ph: prog.tick.emit(
                    f"[{i + 1}/{t}] {ph} modelo {mid}…"))

        def _ok(results):
            _set_batch_enabled(True)
            ok = [r for r in results if r["ok"]]
            fail = [r for r in results if not r["ok"]]
            msg = f"Publicados: {len(ok)}.  Errores: {len(fail)}."
            if fail:
                msg += "\n\n" + "\n".join(f"• modelo {r['id']}: {r['error']}" for r in fail[:10])
            QMessageBox.information(root, "Publicar borradores con IA", msg)
            refresh()

        run_bg(_do, _ok, f"Publicando {len(ids)} borradores con IA…",
               on_error=lambda: _set_batch_enabled(True))

    btn_refresh.clicked.connect(refresh)
    btn_search.clicked.connect(refresh)
    search.returnPressed.connect(refresh)
    btn_new.clicked.connect(new_model)
    btn_batch.clicked.connect(batch_upload_files)
    btn_batch_ai.clicked.connect(batch_publish_drafts)
    btn_upload_confirm.clicked.connect(confirm_upload)
    btn_cancel_new.clicked.connect(cancel_new)
    listw.currentItemChanged.connect(lambda *_: load_selected())
    btn_save.clicked.connect(save)
    btn_thumb.clicked.connect(set_thumb)
    btn_delete.clicked.connect(delete)
    btn_ai.clicked.connect(publish_ai)

    set_mode("empty", "Cargando…")
    refresh()
    return root
