from __future__ import annotations

from .workers import make_worker


def parse_ids(text: str) -> list[int]:
    """Parsea "1, 2 ,3" -> [1,2,3] (se mantiene para compatibilidad/entrada manual)."""
    out = []
    for tok in (text or "").split(","):
        tok = tok.strip()
        if tok.isdigit():
            out.append(int(tok))
    return out


def build_packs_view(client, settings):
    from PySide6.QtCore import Qt, QThreadPool
    from PySide6.QtWidgets import (
        QCheckBox, QDoubleSpinBox, QHBoxLayout, QLabel, QLineEdit, QListWidget,
        QListWidgetItem, QMessageBox, QPushButton, QSplitter, QTextEdit,
        QVBoxLayout, QWidget,
    )

    pool = QThreadPool.globalInstance()
    root = QWidget(); outer = QVBoxLayout(root)

    top = QHBoxLayout()
    btn_new = QPushButton("Nuevo pack")
    btn_refresh = QPushButton("Recargar")
    top.addStretch(); top.addWidget(btn_new); top.addWidget(btn_refresh)
    outer.addLayout(top)

    split = QSplitter(Qt.Horizontal); outer.addWidget(split, 1)
    listw = QListWidget(); split.addWidget(listw)

    right = QWidget(); rl = QVBoxLayout(right)
    title = QLineEdit(); title.setPlaceholderText("Título")
    tags = QLineEdit(); tags.setPlaceholderText("tags,separadas,por,comas")
    price = QDoubleSpinBox(); price.setMaximum(100000); price.setPrefix("€ ")
    desc = QTextEdit(); desc.setPlaceholderText("Descripción"); desc.setMaximumHeight(80)
    rl.addWidget(title); rl.addWidget(tags); rl.addWidget(price); rl.addWidget(desc)

    pick_header = QHBoxLayout()
    pick_header.addWidget(QLabel("Modelos del pack (marca los que incluir):"))
    lbl_count = QLabel("0 seleccionados")
    pick_header.addStretch(); pick_header.addWidget(lbl_count)
    rl.addLayout(pick_header)

    models_pick = QListWidget()  # items con casilla, uno por modelo
    rl.addWidget(models_pick, 1)

    pub_check = QCheckBox("Publicado (visible en la tienda)")
    rl.addWidget(pub_check)

    status = QLabel("")
    btns = QHBoxLayout()
    btn_save = QPushButton("Guardar")
    btn_ai = QPushButton("Publicar con IA")
    btn_delete = QPushButton("Borrar")
    for b in (btn_save, btn_ai, btn_delete):
        btns.addWidget(b)
    rl.addLayout(btns); rl.addWidget(status)
    split.addWidget(right); split.setSizes([300, 700])

    # checked_target: ids que deben quedar marcados (del pack en edición).
    state = {"packs": [], "current": None, "all_models": [], "checked_target": set()}

    def set_status(m):
        status.setText(m)

    def run_bg(fn, on_ok, busy="Trabajando…"):
        set_status(busy)
        w = make_worker(fn)
        w.signals.finished.connect(lambda v: (on_ok(v), set_status("Listo")))
        w.signals.failed.connect(lambda e: (set_status("Error"),
                                            QMessageBox.critical(root, "Error", e)))
        pool.start(w)

    def update_count():
        n = sum(
            1 for i in range(models_pick.count())
            if models_pick.item(i).checkState() == Qt.Checked
        )
        lbl_count.setText(f"{n} seleccionados")

    def populate_models(models):
        state["all_models"] = models
        models_pick.blockSignals(True)
        models_pick.clear()
        for m in models:
            flag = "✔" if m.published else "○"
            it = QListWidgetItem(f"{flag} [{m.id}] {m.title}")
            it.setData(Qt.UserRole, m.id)
            it.setFlags(it.flags() | Qt.ItemIsUserCheckable)
            it.setCheckState(
                Qt.Checked if m.id in state["checked_target"] else Qt.Unchecked
            )
            models_pick.addItem(it)
        models_pick.blockSignals(False)
        update_count()

    def apply_checks():
        """Reaplica las marcas según checked_target sobre los items actuales."""
        models_pick.blockSignals(True)
        for i in range(models_pick.count()):
            it = models_pick.item(i)
            mid = it.data(Qt.UserRole)
            it.setCheckState(Qt.Checked if mid in state["checked_target"] else Qt.Unchecked)
        models_pick.blockSignals(False)
        update_count()

    def load_models():
        # only_published=False para incluir borradores como candidatos del pack.
        run_bg(lambda: client.list_models(only_published=False, limit=200),
               populate_models, "Cargando modelos…")

    def refresh():
        load_models()
        # only_published=False incluye los packs en borrador.
        run_bg(lambda: client.list_packs(only_published=False, limit=200),
               populate, "Cargando packs…")

    def populate(packs):
        state["packs"] = packs
        target = state.pop("select_pack_id", None)
        target_row = -1
        listw.blockSignals(True); listw.clear()
        for i, p in enumerate(packs):
            flag = "✔" if p.published else "○"  # ✔ publicado · ○ borrador
            it = QListWidgetItem(f"{flag} [{p.id}] {p.title} ({len(p.model_ids)})")
            it.setData(Qt.UserRole, p.id); listw.addItem(it)
            if p.id == target:
                target_row = i
        listw.blockSignals(False)
        if target_row >= 0:
            listw.setCurrentRow(target_row)  # dispara load_selected -> state["current"]

    def load_selected():
        it = listw.currentItem()
        if not it:
            return
        p = next((x for x in state["packs"] if x.id == it.data(Qt.UserRole)), None)
        if not p:
            return
        state["current"] = p
        title.setText(p.title); tags.setText(",".join(p.tags))
        price.setValue(p.price_eur or 0); desc.setPlainText(p.description or "")
        pub_check.setChecked(bool(p.published))
        state["checked_target"] = set(p.model_ids)
        apply_checks()

    def new_pack():
        state["current"] = None
        state["checked_target"] = set()
        title.clear(); tags.clear(); price.setValue(0); desc.clear()
        pub_check.setChecked(False)
        listw.setCurrentItem(None)
        apply_checks()
        set_status("Nuevo pack (sin guardar).")

    def selected_model_ids():
        return [
            models_pick.item(i).data(Qt.UserRole)
            for i in range(models_pick.count())
            if models_pick.item(i).checkState() == Qt.Checked
        ]

    def save():
        fields = dict(
            title=title.text(),
            description=desc.toPlainText(),
            tags=[t.strip() for t in tags.text().split(",") if t.strip()],
            price_eur=price.value() or None,
            model_ids=selected_model_ids(),
            published=pub_check.isChecked(),
        )
        p = state["current"]
        if p is None:
            def _created(newp):
                # Auto-seleccionar el pack recién creado: así un guardado posterior
                # lo ACTUALIZA en vez de crear un duplicado.
                state["select_pack_id"] = newp.id
                refresh()
            run_bg(lambda: client.create_pack(**fields), _created, "Creando…")
        else:
            run_bg(lambda: client.update_pack(p.id, **fields), lambda _: refresh(), "Guardando…")

    def delete():
        p = state["current"]
        if not p:
            return
        if QMessageBox.question(root, "Borrar", f"¿Borrar pack '{p.title}'?") != QMessageBox.Yes:
            return
        run_bg(lambda: client.delete_pack(p.id), lambda _: refresh(), "Borrando…")

    def publish_ai():
        from .publish_dialog import open_pack_publish_dialog
        p = state["current"]
        if not p:
            QMessageBox.information(root, "Publicar con IA",
                                    "Selecciona o guarda primero un pack.")
            return
        if not p.model_ids:
            QMessageBox.information(root, "Publicar con IA",
                                    "El pack no tiene modelos. Marca modelos y guarda antes.")
            return

        def done():
            state["select_pack_id"] = p.id
            refresh()

        open_pack_publish_dialog(root, client, settings, p.id, on_done=done)

    btn_new.clicked.connect(new_pack)
    btn_refresh.clicked.connect(refresh)
    btn_save.clicked.connect(save)
    btn_ai.clicked.connect(publish_ai)
    btn_delete.clicked.connect(delete)
    listw.currentItemChanged.connect(lambda *_: load_selected())
    models_pick.itemChanged.connect(lambda *_: update_count())

    refresh()
    return root
