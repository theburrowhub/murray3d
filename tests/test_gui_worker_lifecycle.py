"""Regresión: los workers del QThreadPool no deben destruirse en el hilo worker.

El bug original (segfault en shiboken/QtWebEngine) ocurría porque el QRunnable y
su WorkerSignals (afinidad main-thread) se destruían en el hilo del pool al
terminar run() (autoDelete=True por defecto, sin referencia Python retenida).

Este test lanza muchos workers en un QApplication offscreen dentro de un
SUBPROCESO, de modo que un segfault se manifieste como código de salida ≠ 0 sin
tumbar el proceso de pytest.
"""
from __future__ import annotations

import subprocess
import sys
import textwrap

_SCRIPT = textwrap.dedent(
    """
    import os
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

    from PySide6.QtCore import QThreadPool, QTimer
    from PySide6.QtWidgets import QApplication

    from murray3d.gui.workers import make_worker

    app = QApplication([])
    pool = QThreadPool.globalInstance()
    TOTAL = 40
    done = {"n": 0}

    def submit(i):
        w = make_worker(lambda i=i: i * 2)
        w.signals.finished.connect(lambda v: done.__setitem__("n", done["n"] + 1))
        w.signals.failed.connect(lambda e: done.__setitem__("n", done["n"] + 1))
        pool.start(w)

    for i in range(TOTAL):
        submit(i)

    def check():
        if done["n"] >= TOTAL:
            app.quit()

    t = QTimer(); t.timeout.connect(check); t.start(10)
    QTimer.singleShot(20000, app.quit)  # salvaguarda anti-cuelgue
    app.exec()
    pool.waitForDone(3000)
    assert done["n"] == TOTAL, f"solo {done['n']}/{TOTAL} completados"
    print("OK", done["n"])
    """
)


def test_worker_lifecycle_no_segfault():
    proc = subprocess.run(
        [sys.executable, "-c", _SCRIPT],
        capture_output=True,
        text=True,
        timeout=90,
    )
    assert proc.returncode == 0, (
        f"El proceso Qt terminó con rc={proc.returncode} "
        f"(posible segfault).\nSTDOUT: {proc.stdout}\nSTDERR: {proc.stderr}"
    )
    assert "OK 40" in proc.stdout, f"no completó los 40 workers: {proc.stdout!r}"
