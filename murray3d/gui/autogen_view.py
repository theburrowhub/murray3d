"""Pestaña "Autogeneración": carga un JSON de prompts y genera imágenes en serie.

La lógica pesada vive en ``murray3d.autogen`` / ``murray3d.prompts``; esta vista
solo orquesta Qt: tabla de trabajos, configuración (backend/modelo/aspect/salida)
y un worker con señal de progreso que actualiza cada fila en vivo.
"""
from __future__ import annotations

from pathlib import Path

from ..autogen import BACKENDS, build_generator, run_autogen, summarize
from ..prompts import PromptError, iter_jobs, load_prompt_doc


def build_autogen_view(settings):
    from PySide6.QtCore import QObject, QRunnable, Qt, QThreadPool, Signal, Slot
    from PySide6.QtWidgets import (
        QComboBox, QFileDialog, QHBoxLayout, QHeaderView, QLabel, QLineEdit,
        QMessageBox, QProgressBar, QPushButton, QSpinBox, QTableWidget,
        QTableWidgetItem, QVBoxLayout, QWidget,
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
    backend = QComboBox(); backend.addItems(list(BACKENDS))
    model = QComboBox(); model.addItems(["(del JSON)", "flux-dev", "mystic", "imagen3"])
    aspect = QLineEdit(); aspect.setPlaceholderText("aspect (3:4)"); aspect.setMaximumWidth(90)
    limit = QSpinBox(); limit.setMaximum(100000); limit.setSpecialValueText("todos")
    seed = QSpinBox(); seed.setMaximum(2_000_000_000); seed.setSpecialValueText("aleatoria")
    cfg.addWidget(QLabel("Backend:")); cfg.addWidget(backend)
    cfg.addWidget(QLabel("Modelo:")); cfg.addWidget(model)
    cfg.addWidget(QLabel("Aspect:")); cfg.addWidget(aspect)
    cfg.addWidget(QLabel("Límite:")); cfg.addWidget(limit)
    cfg.addWidget(QLabel("Seed:")); cfg.addWidget(seed)
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

    # --- Tabla de trabajos ---
    table = QTableWidget(0, 5)
    table.setHorizontalHeaderLabels(["id", "Personaje", "Título", "Nombre salida", "Estado"])
    table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
    table.setEditTriggers(QTableWidget.NoEditTriggers)
    outer.addWidget(table, 1)

    # --- Fila inferior: generar + progreso ---
    bottom = QHBoxLayout()
    btn_gen = QPushButton("Generar")
    btn_gen.setEnabled(False)
    progress = QProgressBar(); progress.setTextVisible(True)
    status = QLabel("")
    bottom.addWidget(btn_gen); bottom.addWidget(progress, 1); bottom.addWidget(status)
    outer.addLayout(bottom)

    state = {"doc": None, "jobs": [], "row_by_id": {}, "running": False}

    def selected_model():
        return None if model.currentIndex() == 0 else model.currentText()

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

    def refresh_jobs():
        doc = state["doc"]
        if not doc:
            return
        jobs = iter_jobs(doc, model=selected_model(), aspect_ratio=aspect.text().strip() or None)
        state["jobs"] = jobs
        populate_table(jobs)
        btn_gen.setEnabled(bool(jobs) and not state["running"])
        status.setText(f"{len(jobs)} trabajos")

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

    # --- Worker con progreso ---
    class Signals(QObject):
        progress = Signal(int, int, int, str)  # done, total, job_id, name
        finished = Signal(object)
        failed = Signal(str)

    class AutogenWorker(QRunnable):
        def __init__(self, doc, generator, out, model_ov, aspect_ov, lim, sd):
            super().__init__()
            self.setAutoDelete(False)
            self.signals = Signals()
            self._args = (doc, generator, out, model_ov, aspect_ov, lim, sd)

        @Slot()
        def run(self):
            doc, generator, out, model_ov, aspect_ov, lim, sd = self._args

            def on_prog(i, total, job, phase):
                self.signals.progress.emit(i, total, job.id, job.output_name)

            try:
                results = run_autogen(doc, generator, out, on_progress=on_prog,
                                      model=model_ov, aspect_ratio=aspect_ov,
                                      limit=lim, seed=sd)
                self.signals.finished.emit(results)
            except Exception as e:  # noqa: BLE001
                self.signals.failed.emit(str(e))
            finally:
                close = getattr(generator, "close", None)
                if callable(close):
                    close()

    state["worker_ref"] = None

    def on_progress(done, total, job_id, name):
        progress.setMaximum(total)
        progress.setValue(done)
        set_row_status(job_id, "generando…")
        status.setText(f"[{done + 1}/{total}] {name}")

    def on_finished(results):
        for r in results:
            set_row_status(r["id"], {"ok": "✔", "skipped": "↷ saltado",
                                     "error": "✗ " + r.get("error", "")[:40]}[r["status"]])
        s = summarize(results)
        progress.setValue(progress.maximum())
        status.setText(f"Hecho: {s['ok']} ok · {s['skipped']} saltados · {s['errors']} errores")
        state["running"] = False
        state["worker_ref"] = None
        btn_gen.setEnabled(True)

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
        out = out_dir.text().strip()
        if not out:
            QMessageBox.information(root, "Salida", "Indica un directorio de salida.")
            return
        try:
            generator = build_generator(backend.currentText(), settings)
        except Exception as e:  # noqa: BLE001 - p. ej. falta FREEPIK_API_KEY
            QMessageBox.critical(root, "Configuración", str(e))
            return
        state["running"] = True
        btn_gen.setEnabled(False)
        status.setText("Generando…")
        lim = limit.value() or None
        sd = seed.value() or None
        w = AutogenWorker(doc, generator, Path(out), selected_model(),
                          aspect.text().strip() or None, lim, sd)
        w.signals.progress.connect(on_progress, Qt.QueuedConnection)
        w.signals.finished.connect(on_finished, Qt.QueuedConnection)
        w.signals.failed.connect(on_failed, Qt.QueuedConnection)
        state["worker_ref"] = w  # retener hasta que termine
        pool.start(w)

    btn_load.clicked.connect(load_json)
    btn_browse.clicked.connect(browse_out)
    btn_gen.clicked.connect(generate)
    backend.currentIndexChanged.connect(lambda *_: None)
    model.currentIndexChanged.connect(lambda *_: refresh_jobs())

    return root
