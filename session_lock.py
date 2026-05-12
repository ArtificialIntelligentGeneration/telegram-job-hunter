"""Async file lock helper for MTProto session files."""

from __future__ import annotations

import asyncio
import fcntl
import os
import time
from pathlib import Path


def get_session_lock_path(session_path: Path) -> Path:
    return session_path.with_suffix(session_path.suffix + ".lock")


class SessionFileLock:
    def __init__(self, lock_path: Path, timeout: float = 60.0, poll_interval: float = 0.2) -> None:
        self.lock_path = Path(lock_path)
        self.timeout = timeout
        self.poll_interval = poll_interval
        self._file = None

    async def acquire(self) -> "SessionFileLock":
        self.lock_path.parent.mkdir(parents=True, exist_ok=True)
        self._file = open(self.lock_path, "a+", encoding="utf-8")
        deadline = None if self.timeout <= 0 else time.monotonic() + self.timeout

        while True:
            try:
                fcntl.flock(self._file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                self._file.seek(0)
                self._file.truncate()
                self._file.write(f"pid={os.getpid()} acquired_at={time.time()}\n")
                self._file.flush()
                return self
            except BlockingIOError:
                if deadline is not None and time.monotonic() >= deadline:
                    raise TimeoutError(f"Timed out waiting for Telegram session lock: {self.lock_path}")
                await asyncio.sleep(self.poll_interval)

    def release(self) -> None:
        if not self._file:
            return
        try:
            fcntl.flock(self._file.fileno(), fcntl.LOCK_UN)
        finally:
            self._file.close()
            self._file = None

    async def __aenter__(self) -> "SessionFileLock":
        return await self.acquire()

    async def __aexit__(self, exc_type, exc, tb) -> None:
        self.release()
