"""Pestaña "Autogeneración": carga un JSON de prompts y genera imágenes (+3D).

La lógica pesada vive en ``murray3d.autogen`` / ``murray3d.prompts``; esta vista
orquesta Qt: tabla de trabajos, configuración, un worker con progreso por fila,
un **panel de previsualización** (imagen + visor 3D) y **reanudación visible**
(al cargar un JSON marca las filas que ya tienen salida en disco; ``run_autogen``
salta lo hecho, así que si la app se cerró a medias, continúa donde iba).
"""
from __future__ import annotations

from pathlib import Path

from ..autogen import (
    build_image_generator,
    build_mesh_generator,
    run_autogen,
    summarize,
)
from ..mcp_health import ensure_magnific_auth
from ..prompts import PromptError, iter_jobs, load_prompt_doc


def build_autogen_view(settings):
    from PySide6.QtCore import QObject, QRunnable, Qt, QThreadPool, Signal, Slot
    from PySide6.QtGui import QPixmap
    from PySide6.QtWidgets import (
        QCheckBox, QComboBox, QFileDialog, QHBoxLayout, QHeaderView, QLabel,
        QLineEdit, QMessageBox, QProgressBar, QPushButton, QScrollArea, QSpinBox,
        QSplitter, QTableWidget, QTableWidgetItem, QTabWidget, QVBoxLayout, QWidget,
    )

    pool = QThreadPool.globalInstance()
    root = QWidget(); outer = QVBoxLayout(root)

    # --- Fila superior: cargar JSON ---
    top = QHBoxLayout()
    btn_load = QPushButton("Cargar JSON de prompts…")
    lbl_file = QLabel("Ningún archivo cargado.")
    top.addWidget(btn_load); top.addWidget(lbl_file, 1)
    outer.addLayout(top)

    # --- Fila de configuración ---
    cfg = QHBoxLayout()
    model = QComboBox(); model.addItems(["(del JSON)", "flux-dev", "seedream-5-pro",
                                         "mystic", "imagen3"])
    aspect = QLineEdit(); aspect.setPlaceholderText("aspect (3:4)"); aspect.setMaximumWidth(90)
    limit = QSpinBox(); limit.setMaximum(100000); limit.setSpecialValueText("todos")
    seed = QSpinBox(); seed.setMaximum(2_000_000_000); seed.setSpecialValueText("aleatoria")
    make3d = QCheckBox("También 3D (Magnific MCP)")
    make3d.setToolTip("Genera .glb por agente + MCP de Magnific. ⚠️ ~580 créditos/modelo.")
    cfg.addWidget(QLabel("Modelo:")); cfg.addWidget(model)
    cfg.addWidget(QLabel("Aspect:")); cfg.addWidget(aspect)
    cfg.addWidget(QLabel("Límite:")); cfg.addWidget(limit)
    cfg.addWidget(QLabel("Seed:")); cfg.addWidget(seed)
    cfg.addWidget(make3d)
    cfg.addStretch()
    outer.addLayout(cfg)

    # --- Fila directorio de salida ---
    out_row = QHBoxLayout()
    out_dir = QLineEdit()
    out_dir.setPlaceholderText("Directorio de salida")
    if settings.autogen_dir:
        out_dir.setText(str(settings.autogen_dir))
    btn_browse = QPushButton("…")
    out_row.addWidget(QLabel("Salida:")); out_row.addWidget(out_dir, 1); out_row.addWidget(btn_browse)
    outer.addLayout(out_row)

    # --- Centro: tabla (izq) + previsualización (der) ---
    split = QSplitter(Qt.Horizontal)

    table = QTableWidget(0, 5)
    table.setHorizontalHeaderLabels(["id", "Personaje", "Título", "Nombre salida", "Estado"])
    table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
    table.setEditTriggers(QTableWidget.NoEditTriggers)
    table.setSelectionBehavior(QTableWidget.SelectRows)
    split.addWidget(table)

    preview = QTabWidget()
    # Pestaña Imagen
    img_scroll = QScrollArea(); img_scroll.setWidgetResizable(True)
    img_label = QLabel("Selecciona una fila ya generada para previsualizar.")
    img_label.setAlignment(Qt.AlignCenter); img_label.setWordWrap(True)
    img_scroll.setWidget(img_label)
    preview.addTab(img_scroll, "Imagen")
    # Pestaña 3D (el visor se crea de forma perezosa al ver el primer .glb)
    viewer_box = QWidget(); viewer_layout = QVBoxLayout(viewer_box)
    viewer_hint = QLabel("El visor 3D se cargará al seleccionar una fila con .glb.")
    viewer_hint.setAlignment(Qt.AlignCenter); viewer_hint.setWordWrap(True)
    viewer_layout.addWidget(viewer_hint)
    preview.addTab(viewer_box, "3D")
    split.addWidget(preview)
    split.setSizes([560, 460])
    outer.addWidget(split, 1)

    # --- Fila inferior: generar + progreso ---
    bottom = QHBoxLayout()
    btn_gen = QPushButton("Generar")
    btn_gen.setEnabled(False)
    progress = QProgressBar(); progress.setTextVisible(True)
    status = QLabel("")
    bottom.addWidget(btn_gen); bottom.addWidget(progress, 1); bottom.addWidget(status)
    outer.addLayout(bottom)

    state = {"doc": None, "jobs": [], "row_by_id": {}, "running": False,
             "worker_ref": None, "viewer": None}

    def selected_model():
        return None if model.currentIndex() == 0 else model.currentText()

    def out_base() -> Path | None:
        t = out_dir.text().strip()
        return Path(t) if t else None

    # ---- Previsualización ----
    def ensure_viewer():
        if state["viewer"] is None:
            try:
                from .viewer import build_viewer_widget
                ModelViewer = build_viewer_widget()
                mv = ModelViewer()
                viewer_hint.hide()
                viewer_layout.addWidget(mv)
                state["viewer"] = mv
            except Exception as e:  # noqa: BLE001 - visor no disponible (p.ej. headless)
                viewer_hint.setText(f"Visor 3D no disponible: {e}")
                return None
        return state["viewer"]

    def preview_selected():
        it = table.currentItem()
        base = out_base()
        if it is None or base is None:
            return
        name_item = table.item(it.row(), 3)
        if name_item is None:
            return
        name = name_item.text()
        jpg = base / f"{name}.jpg"
        glb = base / f"{name}.glb"
        # Imagen
        if jpg.exists() and jpg.stat().st_size > 0:
            pix = QPixmap(str(jpg))
            if not pix.isNull():
                vp = img_scroll.viewport().width()
                w = vp if vp > 60 else 440
                img_label.setPixmap(pix.scaledToWidth(int(w), Qt.SmoothTransformation))
                img_label.setText("")
        else:
            img_label.setPixmap(QPixmap())
            img_label.setText("(esta miniatura aún no tiene imagen)")
        # 3D
        if glb.exists() and glb.stat().st_size > 0:
            mv = ensure_viewer()
            if mv is not None:
                try:
                    mv.show_model(glb, settings.cache_dir)
                except Exception:  # noqa: BLE001
                    pass
        elif state["viewer"] is not None:
            try:
                state["viewer"].clear()
            except Exception:  # noqa: BLE001
                pass

    # ---- Tabla / estado ----
    def populate_table(jobs):
        table.setRowCount(0)
        state["row_by_id"] = {}
        for r, j in enumerate(jobs):
            table.insertRow(r)
            table.setItem(r, 0, QTableWidgetItem(str(j.id)))
            table.setItem(r, 1, QTableWidgetItem(j.character))
            table.setItem(r, 2, QTableWidgetItem(j.title))
            table.setItem(r, 3, QTableWidgetItem(j.output_name))
            table.setItem(r, 4, QTableWidgetItem("—"))
            state["row_by_id"][j.id] = r

    def set_row_status(job_id, text):
        r = state["row_by_id"].get(job_id)
        if r is not None:
            table.setItem(r, 4, QTableWidgetItem(text))

    def mark_existing():
        """Marca en la tabla lo ya generado en disco (reanudación visible)."""
        base = out_base()
        if base is None:
            return 0
        done = 0
        for j in state["jobs"]:
            r = state["row_by_id"].get(j.id)
            if r is None:
                continue
            glb = base / f"{j.output_name}.glb"
            jpg = base / f"{j.output_name}.jpg"
            if glb.exists() and glb.stat().st_size > 0:
                table.setItem(r, 4, QTableWidgetItem("✔ 3D")); done += 1
            elif jpg.exists() and jpg.stat().st_size > 0:
                table.setItem(r, 4, QTableWidgetItem("✔ img")); done += 1
        return done

    def refresh_jobs():
        doc = state["doc"]
        if not doc:
            return
        jobs = iter_jobs(doc, model=selected_model(), aspect_ratio=aspect.text().strip() or None)
        state["jobs"] = jobs
        populate_table(jobs)
        btn_gen.setEnabled(bool(jobs) and not state["running"])
        done = mark_existing()
        status.setText(f"{len(jobs)} trabajos"
                       + (f" · {done} ya generados (se reanudará)" if done else ""))

    def load_json():
        path, _ = QFileDialog.getOpenFileName(root, "Elige el JSON de prompts", "",
                                              "JSON (*.json)")
        if not path:
            return
        try:
            doc = load_prompt_doc(Path(path))
        except PromptError as e:
            QMessageBox.critical(root, "JSON inválido", str(e))
            return
        state["doc"] = doc
        lbl_file.setText(f"{Path(path).name} — {len(doc.figures)} figuras")
        ig = doc.automation_config.image_generation
        if not aspect.text().strip():
            aspect.setText(ig.aspect_ratio)
        if settings.autogen_dir and out_dir.text().strip() in ("", str(settings.autogen_dir)):
            out_dir.setText(str(settings.autogen_dir / Path(path).stem))
        refresh_jobs()

    def browse_out():
        d = QFileDialog.getExistingDirectory(root, "Directorio de salida", out_dir.text() or "")
        if d:
            out_dir.setText(d)
            if state["jobs"]:
                mark_existing()

    # --- Worker con progreso ---
    class Signals(QObject):
        progress = Signal(int, int, int, str)  # done, total, job_id, name
        finished = Signal(object)
        failed = Signal(str)

    class AutogenWorker(QRunnable):
        def __init__(self, doc, generator, out, model_ov, aspect_ov, lim, sd,
                     mk3d, mesh):
            super().__init__()
            self.setAutoDelete(False)
            self.signals = Signals()
            self._args = (doc, generator, out, model_ov, aspect_ov, lim, sd, mk3d, mesh)

        @Slot()
        def run(self):
            doc, generator, out, model_ov, aspect_ov, lim, sd, mk3d, mesh = self._args

            def on_prog(i, total, job, phase):
                self.signals.progress.emit(i, total, job.id, job.output_name)

            try:
                ensure_magnific_auth()  # preflight: MCP caducado -> re-autenticar
                results = run_autogen(doc, generator, out, on_progress=on_prog,
                                      model=model_ov, aspect_ratio=aspect_ov,
                                      limit=lim, seed=sd, make_3d=mk3d,
                                      mesh_generator=mesh)
                self.signals.finished.emit(results)
            except Exception as e:  # noqa: BLE001
                self.signals.failed.emit(str(e))
            finally:
                close = getattr(generator, "close", None)
                if callable(close):
                    close()

    def on_progress(done, total, job_id, name):
        progress.setMaximum(total)
        progress.setValue(done)
        set_row_status(job_id, "generando…")
        status.setText(f"[{done + 1}/{total}] {name}")

    def on_finished(results):
        for r in results:
            set_row_status(r["id"], {"ok": "✔", "skipped": "↷ saltado",
                                     "error": "✗ " + r.get("error", "")[:40]}[r["status"]])
        mark_existing()  # distingue img / 3D según ficheros
        s = summarize(results)
        progress.setValue(progress.maximum())
        status.setText(f"Hecho: {s['ok']} ok · {s['skipped']} saltados · {s['errors']} errores")
        state["running"] = False
        state["worker_ref"] = None
        btn_gen.setEnabled(True)
        preview_selected()

    def on_failed(msg):
        QMessageBox.critical(root, "Error de autogeneración", msg)
        status.setText("Error")
        state["running"] = False
        state["worker_ref"] = None
        btn_gen.setEnabled(True)

    def generate():
        doc = state["doc"]
        if not doc or not state["jobs"]:
            return
        base = out_base()
        if base is None:
            QMessageBox.information(root, "Salida", "Indica un directorio de salida.")
            return
        mk3d = make3d.isChecked()
        try:
            generator = build_image_generator(settings)
            mesh = build_mesh_generator(settings) if mk3d else None
        except Exception as e:  # noqa: BLE001
            QMessageBox.critical(root, "Configuración", str(e))
            return
        if mk3d:
            n = limit.value() or len(state["jobs"])
            if QMessageBox.question(
                root, "Generar 3D",
                f"El 3D gasta ~580 créditos por modelo (~{n} modelos). ¿Continuar?"
            ) != QMessageBox.Yes:
                return
        state["running"] = True
        btn_gen.setEnabled(False)
        status.setText("Generando…")
        lim = limit.value() or None
        sd = seed.value() or None
        w = AutogenWorker(doc, generator, base, selected_model(),
                          aspect.text().strip() or None, lim, sd, mk3d, mesh)
        w.signals.progress.connect(on_progress, Qt.QueuedConnection)
        w.signals.finished.connect(on_finished, Qt.QueuedConnection)
        w.signals.failed.connect(on_failed, Qt.QueuedConnection)
        state["worker_ref"] = w  # retener hasta que termine
        pool.start(w)

    btn_load.clicked.connect(load_json)
    btn_browse.clicked.connect(browse_out)
    btn_gen.clicked.connect(generate)
    model.currentIndexChanged.connect(lambda *_: refresh_jobs())
    out_dir.editingFinished.connect(lambda: state["jobs"] and mark_existing())
    table.itemSelectionChanged.connect(preview_selected)

    return root
