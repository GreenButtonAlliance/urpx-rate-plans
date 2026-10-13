#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Clark Communications Corporation
# SPDX-License-Identifier: MIT
"""Run dev/shacl_gate.clj in a running nREPL, so JVM, Clojure and Jena startup
is paid once rather than per invocation.

Usage: python3 dev/shacl_nrepl.py --port PORT [shacl-gate options]

The evaluation loads dev/urpx_rate_plans.clj and dev/shacl_gate.clj from THIS
checkout with load-file, so the code that runs is the code in the tree under
test, whichever checkout started the REPL, and passes this checkout's root to
shacl-gate/run with this process's URPX_CHECKOUT, and shacl-gate/run reads
every graph afresh. Runs are serialized on one
JVM-wide lock, so two gates sharing a REPL cannot reload the namespace under
each other.

Exit: the shacl-gate exit code (0-3); 3 also when the evaluation throws.
UNAVAILABLE (125) when nothing answers on the port or the REPL's classpath
lacks com.dcj/clj-shacl; dev/shacl.sh then starts a fresh JVM instead.
"""
from __future__ import annotations

import json
import os
import socket
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
UNAVAILABLE = 125


# --- bencode ----------------------------------------------------------------

def encode(x) -> bytes:
    if isinstance(x, int):
        return b"i%de" % x
    if isinstance(x, str):
        x = x.encode()
    if isinstance(x, bytes):
        return b"%d:%s" % (len(x), x)
    if isinstance(x, list):
        return b"l" + b"".join(encode(i) for i in x) + b"e"
    if isinstance(x, dict):
        return b"d" + b"".join(encode(k) + encode(v) for k, v in sorted(x.items())) + b"e"
    raise TypeError(type(x))


class Reader:
    def __init__(self, sock: socket.socket):
        self.sock = sock
        self.buf = b""

    def _need(self, n: int) -> None:
        while len(self.buf) < n:
            chunk = self.sock.recv(65536)
            if not chunk:
                raise ConnectionError("nREPL closed the connection")
            self.buf += chunk

    def _take(self, n: int) -> bytes:
        self._need(n)
        out, self.buf = self.buf[:n], self.buf[n:]
        return out

    def _until(self, end: bytes) -> bytes:
        while end not in self.buf:
            self._need(len(self.buf) + 1)
        i = self.buf.index(end)
        out, self.buf = self.buf[:i], self.buf[i + 1:]
        return out

    def read(self):
        c = self._take(1)
        if c == b"i":
            return int(self._until(b"e"))
        if c == b"l":
            out = []
            while True:
                self._need(1)
                if self.buf[:1] == b"e":
                    self._take(1)
                    return out
                out.append(self.read())
        if c == b"d":
            out = {}
            while True:
                self._need(1)
                if self.buf[:1] == b"e":
                    self._take(1)
                    return out
                k = self.read()
                out[k] = self.read()
        n = int(c + self._until(b":"))
        return self._take(n).decode("utf-8", errors="replace")


# --- evaluation ---------------------------------------------------------------

def clj_str(s: str) -> str:
    """A Clojure string literal; JSON's escapes are a subset Clojure reads."""
    return json.dumps(s)


def form(args: list[str]) -> str:
    root = str(REPO)
    checkout = os.environ.get("URPX_CHECKOUT")
    env = "{}" if checkout is None else "{\"URPX_CHECKOUT\" " + clj_str(checkout) + "}"
    return f"""
(locking (.intern "urpx-rate-plans/shacl-gate")
  (if-not (try (require 'shacl.core) true
               (catch java.io.FileNotFoundException _ false))
    :no-clj-shacl
    (do (load-file {clj_str(root + "/dev/urpx_rate_plans.clj")})
        (load-file {clj_str(root + "/dev/shacl_gate.clj")})
        ((resolve 'shacl-gate/run) {clj_str(root)} [{" ".join(clj_str(a) for a in args)}] {env}))))
"""


def main() -> int:
    argv = sys.argv[1:]
    if len(argv) < 2 or argv[0] != "--port":
        print("usage: dev/shacl_nrepl.py --port PORT [shacl-gate options]", file=sys.stderr)
        return 3
    port, args = int(argv[1]), argv[2:]
    try:
        sock = socket.create_connection(("127.0.0.1", port), timeout=2)
    except OSError as e:
        print(f"shacl: no nREPL on port {port} ({e}); starting a fresh JVM", file=sys.stderr)
        return UNAVAILABLE
    sock.settimeout(None)
    reader = Reader(sock)
    sock.sendall(encode({"op": "eval", "code": form(args), "ns": "user", "id": "shacl-gate"}))
    value, failed = None, False
    while True:
        msg = reader.read()
        if "out" in msg:
            sys.stdout.write(msg["out"])
            sys.stdout.flush()
        if "err" in msg:
            sys.stderr.write(msg["err"])
            sys.stderr.flush()
        if "value" in msg:
            value = msg["value"]
        if "ex" in msg:
            failed = True
        if "done" in msg.get("status", []):
            break
    sock.close()
    if value == ":no-clj-shacl":
        print(f"shacl: the nREPL on port {port} lacks com.dcj/clj-shacl; starting a fresh "
              f"JVM. Run (clojure.repl.deps/sync-deps) in that REPL, or restart it, to use it.",
              file=sys.stderr)
        return UNAVAILABLE
    if failed or value is None or not value.isdigit():
        print(f"REFUSED  the evaluation in the nREPL on port {port} failed (value {value!r})",
              file=sys.stderr)
        return 3
    return int(value)


if __name__ == "__main__":
    sys.exit(main())
