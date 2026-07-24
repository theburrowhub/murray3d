from __future__ import annotations

from pathlib import Path

from ..models import GeneratedMeta, GeneratedPackMeta
from .workers import make_worker


def meta_from_form(title, description, tags_text, category, price) -> GeneratedMeta:
    tags = [t.strip() for t in (tags_text or "").split(",") if t.strip()]
    return GeneratedMeta(
        title=title,
        description=description,
        tags=tags,
        category=category,
        price_eur=(price or None) if price else None,
        best_thumbnail_index=0,
    )


def pack_meta_from_form(title, description, tags_text, price) -> GeneratedPackMeta:
    tags = [t.strip() for t in (tags_text or "").split(",") if t.strip()]
    return GeneratedPackMeta(
        title=title,
        description=description,
        tags=tags,
        price_eur=(price or None) if price else None,
        best_cover_index=0,
    )


def open_publish_dialog(parent, client, settings, model_id, on_done):
    from PySide6.QtCore import Qt, QThreadPool, QSize
    from PySide6.QtGui import QIcon, QPixmap
    from PySide6.QtWidgets import (
        QDialog, QDoubleSpinBox, QHBoxLayout, QLabel, QLineEdit, QListView,
        QListWidget, QListWidgetItem, QMessageBox, QProgressBar, QPushButton,
        QTextEdit, QVBoxLayout,
    )

    from ..publish import commit_publish, prepare_publish

    pool = QThreadPool.globalInstance()
    dlg = QDialog(parent)
    dlg.setWindowTitle("Publicar con IA")
    dlg.resize(900, 700)
    v = QVBoxLayout(dlg)

    progress = QLabel("Renderizando pantallazos y consultando a Claude…")
    bar = QProgressBar(); bar.setRange(0, 0)
    v.addWidget(progress); v.addWidget(bar)

    shots_list = QListWidget()
    shots_list.setViewMode(QListView.IconMode)
    shots_list.setIconSize(QSize(180, 180))
    shots_list.setResizeMode(QListView.Adjust)
    shots_list.hide()
    v.addWidget(shots_list)

    form_title = QLineEdit(); form_title.setPlaceholderText("Título")
    form_cat = QLineEdit(); form_cat.setPlaceholderText("Categoría")
    form_tags = QLineEdit(); form_tags.setPlaceholderText("tags,separadas,por,comas")
    form_price = QDoubleSpinBox(); form_price.setMaximum(100000); form_price.setPrefix("€ ")
    form_desc = QTextEdit()
    for w in (form_title, form_cat, form_tags, form_price, form_desc):
        w.hide(); v.addWidget(w)

    btns = QHBoxLayout()
    btn_publish = QPushButton("Publicar"); btn_publish.setEnabled(False)
    btn_cancel = QPushButton("Cancelar")
    btns.addStretch(); btns.addWidget(btn_cancel); btns.addWidget(btn_publish)
    v.addLayout(btns)

    ctx = {"shots": [], "meta": None}

    def on_prepared(result):
        meta, shots = result
        ctx["shots"] = shots; ctx["meta"] = meta
        bar.hide(); progress.setText("Revisa y ajusta antes de publicar:")
        shots_list.show()
        for i, s in enumerate(shots):
            item = QListWidgetItem(QIcon(QPixmap(str(s))), f"{i}")
            shots_list.addItem(item)
        if 0 <= meta.best_thumbnail_index < len(shots):
            shots_list.setCurrentRow(meta.best_thumbnail_index)
        form_title.setText(meta.title); form_cat.setText(meta.category)
        form_tags.setText(",".join(meta.tags))
        form_price.setValue(meta.price_eur or 0)
        form_desc.setPlainText(meta.description)
        for w in (form_title, form_cat, form_tags, form_price, form_desc):
            w.show()
        btn_publish.setEnabled(True)

    def on_failed(msg):
        bar.hide()
        QMessageBox.critical(dlg, "Error generando metadatos", msg)
        dlg.reject()

    w = make_worker(lambda: prepare_publish(client, settings, model_id))
    w.signals.finished.connect(on_prepared)
    w.signals.failed.connect(on_failed)
    pool.start(w)

    def do_publish():
        meta = meta_from_form(form_title.text(), form_desc.toPlainText(),
                              form_tags.text(), form_cat.text(), form_price.value())
        idx = shots_list.currentRow() if shots_list.currentRow() >= 0 else 0
        btn_publish.setEnabled(False)
        progress.setText("Publicando…"); bar.show()
        w2 = make_worker(lambda: commit_publish(client, model_id, meta,
                                                ctx["shots"], thumbnail_index=idx))
        w2.signals.finished.connect(lambda _: (on_done(), dlg.accept()))
        w2.signals.failed.connect(lambda e: (bar.hide(),
                                             QMessageBox.critical(dlg, "Error", e),
                                             btn_publish.setEnabled(True)))
        pool.start(w2)

    btn_publish.clicked.connect(do_publish)
    btn_cancel.clicked.connect(dlg.reject)
    dlg.exec()


def open_pack_publish_dialog(parent, client, settings, pack_id, on_done):
    """'Publicar con IA' para un pack: genera título/descr/tags/precio del bundle
    a partir de una imagen de cada modelo incluido, para revisar y publicar."""
    from PySide6.QtCore import QSize, Qt, QThreadPool
    from PySide6.QtGui import QIcon, QPixmap
    from PySide6.QtWidgets import (
        QDialog, QDoubleSpinBox, QHBoxLayout, QLabel, QLineEdit, QListView,
        QListWidget, QListWidgetItem, QMessageBox, QProgressBar, QPushButton,
        QTextEdit, QVBoxLayout,
    )

    from ..publish import commit_pack_publish, prepare_pack_publish

    pool = QThreadPool.globalInstance()
    dlg = QDialog(parent)
    dlg.setWindowTitle("Publicar pack con IA")
    dlg.resize(900, 700)
    v = QVBoxLayout(dlg)

    progress = QLabel("Renderizando los modelos del pack y consultando a Claude…")
    bar = QProgressBar(); bar.setRange(0, 0)
    v.addWidget(progress); v.addWidget(bar)

    shots_list = QListWidget()
    shots_list.setViewMode(QListView.IconMode)
    shots_list.setIconSize(QSize(160, 160))
    shots_list.setResizeMode(QListView.Adjust)
    shots_list.hide()
    v.addWidget(shots_list)

    form_title = QLineEdit(); form_title.setPlaceholderText("Título del pack")
    form_tags = QLineEdit(); form_tags.setPlaceholderText("tags,separadas,por,comas")
    form_price = QDoubleSpinBox(); form_price.setMaximum(100000); form_price.setPrefix("€ ")
    form_desc = QTextEdit()
    for w in (form_title, form_tags, form_price, form_desc):
        w.hide(); v.addWidget(w)

    btns = QHBoxLayout()
    btn_publish = QPushButton("Publicar pack"); btn_publish.setEnabled(False)
    btn_cancel = QPushButton("Cancelar")
    btns.addStretch(); btns.addWidget(btn_cancel); btns.addWidget(btn_publish)
    v.addLayout(btns)

    def on_prepared(result):
        meta, shots, pack = result
        bar.hide(); progress.setText(f"Pack de {len(shots)} modelos. Revisa y ajusta:")
        shots_list.show()
        for i, s in enumerate(shots):
            shots_list.addItem(QListWidgetItem(QIcon(QPixmap(str(s))), f"{i}"))
        form_title.setText(meta.title)
        form_tags.setText(",".join(meta.tags))
        form_price.setValue(meta.price_eur or 0)
        form_desc.setPlainText(meta.description)
        for w in (form_title, form_tags, form_price, form_desc):
            w.show()
        btn_publish.setEnabled(True)

    def on_failed(msg):
        bar.hide()
        QMessageBox.critical(dlg, "Error generando metadatos del pack", msg)
        dlg.reject()

    w = make_worker(lambda: prepare_pack_publish(client, settings, pack_id))
    w.signals.finished.connect(on_prepared)
    w.signals.failed.connect(on_failed)
    pool.start(w)

    def do_publish():
        meta = pack_meta_from_form(form_title.text(), form_desc.toPlainText(),
                                   form_tags.text(), form_price.value())
        btn_publish.setEnabled(False)
        progress.setText("Publicando pack…"); bar.show()
        w2 = make_worker(lambda: commit_pack_publish(client, pack_id, meta, publish=True))
        w2.signals.finished.connect(lambda _: (on_done(), dlg.accept()))
        w2.signals.failed.connect(lambda e: (bar.hide(),
                                             QMessageBox.critical(dlg, "Error", e),
                                             btn_publish.setEnabled(True)))
        pool.start(w2)

    btn_publish.clicked.connect(do_publish)
    btn_cancel.clicked.connect(dlg.reject)
    dlg.exec()
