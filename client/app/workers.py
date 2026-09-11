import traceback
from collections.abc import Callable
from typing import Any

from PySide2.QtCore import QObject, QRunnable, Signal


class WorkerSignals(QObject):
    result = Signal(object)
    error = Signal(str)
    finished = Signal()


class Worker(QRunnable):
    """Runs `fn(*args, **kwargs)` on a QThreadPool thread and reports back
    via Qt signals, which are safely queued onto the receiving (UI) thread
    automatically. This is the one mechanism through which network/disk work
    reaches the UI thread — see AGENTS.md's guardrail against blocking IO
    directly on the UI thread.
    """

    def __init__(self, fn: Callable[..., Any], *args: Any, **kwargs: Any) -> None:
        super().__init__()
        self._fn = fn
        self._args = args
        self._kwargs = kwargs
        self.signals = WorkerSignals()

    def run(self) -> None:
        try:
            result = self._fn(*self._args, **self._kwargs)
        except Exception:  # reported via signal instead of raised on this thread
            self.signals.error.emit(traceback.format_exc())
        else:
            self.signals.result.emit(result)
        finally:
            self.signals.finished.emit()
