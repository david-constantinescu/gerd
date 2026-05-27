"""PTY-backed bash sessions for the authenticated web terminal."""

from __future__ import annotations

import fcntl
import logging
import os
import pty
import struct
import termios
from typing import ClassVar

log = logging.getLogger("web.shell")

_DEFAULT_ROWS = 24
_DEFAULT_COLS = 80


class PtyShell:
    """One interactive bash per session key (use gunicorn -w 1 on the Pi)."""

    _sessions: ClassVar[dict[str, PtyShell]] = {}

    @classmethod
    def get(cls, key: str) -> PtyShell:
        if key not in cls._sessions:
            cls._sessions[key] = PtyShell()
        return cls._sessions[key]

    @classmethod
    def close(cls, key: str) -> None:
        sh = cls._sessions.pop(key, None)
        if sh is not None:
            sh.kill()

    def __init__(self) -> None:
        self.master_fd: int | None = None
        self.pid: int | None = None
        self._start()

    def _start(self) -> None:
        pid, fd = pty.fork()
        if pid == 0:
            home = os.path.expanduser("~")
            try:
                os.chdir(home)
            except OSError:
                pass
            os.environ.setdefault("TERM", "xterm-256color")
            os.execvp("/bin/bash", ["/bin/bash", "-l"])
        self.pid = pid
        self.master_fd = fd
        flags = fcntl.fcntl(fd, fcntl.F_GETFL)
        fcntl.fcntl(fd, fcntl.F_SETFL, flags | os.O_NONBLOCK)
        self.resize(_DEFAULT_ROWS, _DEFAULT_COLS)
        log.info("web shell started pid=%s", pid)

    def resize(self, rows: int, cols: int) -> None:
        if self.master_fd is None:
            return
        winsize = struct.pack("HHHH", rows, cols, 0, 0)
        try:
            fcntl.ioctl(self.master_fd, termios.TIOCSWINSZ, winsize)
        except OSError:
            pass

    def read(self, max_bytes: int = 8192) -> str:
        if self.master_fd is None:
            return ""
        try:
            chunk = os.read(self.master_fd, max_bytes)
            return chunk.decode(errors="replace")
        except BlockingIOError:
            return ""
        except OSError:
            return ""

    def write(self, data: str) -> None:
        if self.master_fd is None or not data:
            return
        os.write(self.master_fd, data.encode())

    def kill(self) -> None:
        if self.pid:
            try:
                os.kill(self.pid, 9)
            except OSError:
                pass
        if self.master_fd is not None:
            try:
                os.close(self.master_fd)
            except OSError:
                pass
