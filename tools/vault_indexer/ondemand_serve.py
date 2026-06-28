"""On-demand launcher for the vault-indexer (socket-activated under launchd).

The fitness / nutrition / learning indexers are not persistent. launchd owns
their listening socket and launches this entrypoint on the first incoming
connection; we retrieve the inherited socket fd and hand it to uvicorn, which
serves the FastAPI app on it. The app self-exits after an idle window
(``IDLE_SHUTDOWN_SECONDS``); launchd relaunches us on the next connection.

Run modes:
  - Under launchd:        ``python -m tools.vault_indexer.ondemand_serve``
      → grabs the ``Listeners`` socket via ``launch_activate_socket`` and
        serves on its fd.
  - Manual / dev:         ``python -m tools.vault_indexer.ondemand_serve --port 8092``
      → no launchd socket present; binds the port normally.

Env (set by the plist): VAULT_PATH, DOMAIN, INDEXER_DB_PATH, IDLE_SHUTDOWN_SECONDS.
"""
from __future__ import annotations

import argparse
import ctypes
import logging
import sys
from typing import Optional

import uvicorn

logger = logging.getLogger("vault-indexer.ondemand")
logging.basicConfig(level=logging.INFO)

_APP = "tools.vault_indexer.app:app"
_LAUNCHD_SOCKET_NAME = b"Listeners"  # must match the plist <Sockets> key


def _launchd_socket_fd(name: bytes = _LAUNCHD_SOCKET_NAME) -> Optional[int]:
    """Return the first fd launchd passed for socket ``name``, or None.

    Wraps ``launch_activate_socket(const char *name, int **fds, size_t *cnt)``
    from libSystem (the modern replacement for the deprecated ``launch_msg``
    checkin). Returns 0 on success with a malloc'd fd array. We use the first
    fd (single IPv4 listener per plist) and free the array.
    """
    try:
        libc = ctypes.CDLL(None, use_errno=True)
        fn = libc.launch_activate_socket
    except (OSError, AttributeError):
        return None  # not macOS / symbol unavailable

    fn.argtypes = [
        ctypes.c_char_p,
        ctypes.POINTER(ctypes.POINTER(ctypes.c_int)),
        ctypes.POINTER(ctypes.c_size_t),
    ]
    fn.restype = ctypes.c_int

    fds_ptr = ctypes.POINTER(ctypes.c_int)()
    count = ctypes.c_size_t(0)
    rc = fn(name, ctypes.byref(fds_ptr), ctypes.byref(count))
    if rc != 0 or count.value < 1:
        # rc == ESRCH (3) when not launched on demand by launchd — expected in
        # the manual/dev path; caller falls back to --port.
        return None
    fd = int(fds_ptr[0])
    try:
        libc.free(fds_ptr)
    except Exception:  # noqa: BLE001 — best-effort; fd already captured
        pass
    return fd


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(prog="ondemand_serve")
    ap.add_argument("--host", default="127.0.0.1",
                    help="Fallback bind host when no launchd socket (default 127.0.0.1).")
    ap.add_argument("--port", type=int, default=None,
                    help="Fallback bind port when no launchd socket present.")
    args = ap.parse_args(argv)

    fd = _launchd_socket_fd()
    if fd is not None:
        logger.info("serving on launchd-provided socket fd=%d", fd)
        uvicorn.run(_APP, fd=fd, log_level="info")
        return 0

    if args.port is None:
        print(
            "no launchd socket and no --port given; pass --port for manual runs",
            file=sys.stderr,
        )
        return 2
    logger.info("no launchd socket — binding %s:%d", args.host, args.port)
    uvicorn.run(_APP, host=args.host, port=args.port, log_level="info")
    return 0


if __name__ == "__main__":
    sys.exit(main())
