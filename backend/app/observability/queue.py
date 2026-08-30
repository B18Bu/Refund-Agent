"""有界、非阻塞的 Telemetry 发送队列。"""
from __future__ import annotations

import logging
import queue
import threading
from collections.abc import Callable
from typing import Any

logger = logging.getLogger(__name__)


class TelemetryQueue:
    """后台发送观测事件；队列满时丢弃观测，不影响业务链路。"""

    def __init__(self, maxsize: int = 1000, exporter: Callable[[dict[str, Any]], None] | None = None, *, autostart: bool = True):
        if maxsize < 1:
            raise ValueError("Telemetry 队列容量必须大于 0")
        self._queue: queue.Queue[dict[str, Any] | None] = queue.Queue(maxsize=maxsize)
        self._exporter = exporter or (lambda _: None)
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self.dropped = 0
        if autostart:
            self.start()

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="telemetry-exporter", daemon=True)
        self._thread.start()

    def emit(self, payload: dict[str, Any]) -> bool:
        try:
            self._queue.put_nowait(payload)
            return True
        except queue.Full:
            self.dropped += 1
            return False

    def close(self, timeout: float = 2.0) -> None:
        self._stop.set()
        if self._thread and self._thread.is_alive():
            try:
                self._queue.put_nowait(None)
            except queue.Full:
                pass
            self._thread.join(timeout=timeout)

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                item = self._queue.get(timeout=0.1)
            except queue.Empty:
                continue
            if item is None:
                self._queue.task_done()
                break
            try:
                self._exporter(item)
            except Exception as exc:
                logger.warning("Telemetry 上报失败: %s", exc)
            finally:
                self._queue.task_done()

