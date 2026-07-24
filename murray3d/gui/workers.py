from __future__ import annotations

import itertools
import traceback

# Workers vivos, indexados por un id entero. Retenemos aquí una referencia
# Python a cada QRunnable para que QThreadPool NO lo destruya en el hilo worker
# (lo que provocaba un segfault al deallocar su QObject de afinidad main-thread
# fuera del hilo principal). La referencia se libera en el hilo principal cuando
# el worker emite su señal de finalización.
_ALIVE: dict[int, object] = {}
_counter = itertools.count()


def run_callable(fn):
    """Ejecuta fn() y devuelve (ok, resultado_o_mensaje_error). Sin dependencia de Qt."""
    try:
        return True, fn()
    except Exception as e:  # noqa: BLE001
        return False, f"{e}\n{traceback.format_exc()}"


def make_worker(fn):
    """Crea un QRunnable que ejecuta fn en un hilo y emite señales.

    Import de Qt perezoso. El worker se retiene en `_ALIVE` hasta que termina y
    se libera en el hilo principal (las señales son de cola entre hilos), de modo
    que su destrucción ocurra siempre en el hilo principal.
    """
    from PySide6.QtCore import QObject, QRunnable, Signal, Slot

    class WorkerSignals(QObject):
        finished = Signal(object)
        failed = Signal(str)

    class Worker(QRunnable):
        def __init__(self):
            super().__init__()
            # Que QThreadPool no borre el QRunnable en el hilo worker.
            self.setAutoDelete(False)
            self.signals = WorkerSignals()

        @Slot()
        def run(self):
            ok, value = run_callable(fn)
            if ok:
                self.signals.finished.emit(value)
            else:
                self.signals.failed.emit(str(value))

    wid = next(_counter)
    w = Worker()
    _ALIVE[wid] = w
    # El lambda captura solo `wid` (un int), nunca `w`, para no crear un ciclo
    # que un GC pudiera recolectar en otro hilo. Al ejecutarse en el hilo
    # principal, `pop` suelta la última referencia y `w` se destruye ahí.
    w.signals.finished.connect(lambda *_: _ALIVE.pop(wid, None))
    w.signals.failed.connect(lambda *_: _ALIVE.pop(wid, None))
    return w
