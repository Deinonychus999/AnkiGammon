"""Keep worker threads alive until they have really ended."""

from typing import Callable, Iterable, Optional

from PySide6.QtCore import QObject, QThread, QTimer

_POLL_MS = 50


def after_threads_stop(
    threads: Iterable[Optional[QThread]],
    callback: Callable[[], None],
    context: QObject,
) -> None:
    """Run callback once every thread has returned from run(), holding them until then.

    Workers report their result by signal and keep running afterwards, shutting
    their engine down. Destroying one in that window, by closing the dialog
    that holds it or by deleteLater(), makes Qt abort the whole app ("QThread:
    Destroyed while thread is still running"; 0xC0000409 on Windows).
    """
    threads = [t for t in threads if t is not None]
    if any(t.isRunning() for t in threads):
        QTimer.singleShot(_POLL_MS, context, lambda: after_threads_stop(threads, callback, context))
        return
    callback()
