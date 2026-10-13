#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Clark Communications Corporation
# SPDX-License-Identifier: MIT
"""Tests for the SharePoint envelope unwrapping in dev/fetch_tariff_documents.py.

Twelve SCE source documents were committed as the envelope itself, because the
curl recipe in us/ca/sce/utility.toml had no unwrapping step. The last case
here is the corpus-wide guard against that recurring: every tracked .pdf must
begin with %PDF-.

Run: python3 dev/test_fetch_unwrap.py
"""
from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "dev"))
from fetch_tariff_documents import EnvelopeError, unwrap_files, unwrap_multipart  # noqa: E402

failures: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    print(f"  {'PASS' if ok else 'FAIL'}  {name}{'' if ok or not detail else ': ' + detail}")
    if not ok:
        failures.append(name)


def raises(f) -> str | None:
    try:
        f()
    except EnvelopeError as e:
        return str(e)
    return None


# A PDF with an incremental update, so %%EOF occurs twice, ending in LF as
# SCE's do; and one ending in CRLF, as Schedule NBT's does.
PDF_LF = b"%PDF-1.7\n1 0 obj\n<<>>\nendobj\n%%EOF\n2 0 obj\n<<>>\nendobj\nstartxref\n9\n%%EOF\n"
PDF_CRLF = b"%PDF-1.4\r\n1 0 obj\r\n<<>>\r\nendobj\r\nstartxref\r\n9\r\n%%EOF\r\n"
BOUNDARY = b"fKK4dWFJkzGOhOi_cOzJ_jlvL9FLhrr9kb65JxdC"


def envelope(pdf: bytes, length: int | None = None, parts: int = 1, close: bool = True) -> bytes:
    out = b""
    for _ in range(parts):
        out += (b"--" + BOUNDARY + b"\r\n"
                b'Content-Disposition: form-data; name="pdf"; filename="ELECTRIC_SCHEDULES_TOU-D.pdf"\r\n'
                b"Content-Type: application/pdf\r\n"
                b"Content-Length: " + str(len(pdf) if length is None else length).encode() + b"\r\n"
                b"\r\n" + pdf + b"\r\n")
    return out + (b"--" + BOUNDARY + b"--\r\n" if close else b"")


def main() -> int:
    check("the part body comes back byte for byte, its trailing LF included",
          unwrap_multipart(envelope(PDF_LF)) == PDF_LF)
    check("a CRLF after %%EOF is kept",
          unwrap_multipart(envelope(PDF_CRLF)) == PDF_CRLF)
    check("a PDF passes through as the same object",
          unwrap_multipart(PDF_LF) is PDF_LF)
    check("bytes that are not an envelope pass through", unwrap_multipart(b"<html>") == b"<html>")

    e = raises(lambda: unwrap_multipart(envelope(PDF_LF, length=len(PDF_LF) - 1)))
    check("a body that disagrees with Content-Length refuses", e is not None and "Content-Length" in e, str(e))
    check("two parts refuse", raises(lambda: unwrap_multipart(envelope(PDF_LF, parts=2))) is not None)
    check("a missing closing boundary refuses",
          raises(lambda: unwrap_multipart(envelope(PDF_LF, close=False))) is not None)
    check("a first line with no boundary refuses", raises(lambda: unwrap_multipart(b"--\r\n")) is not None)

    with tempfile.TemporaryDirectory() as d:
        good, bad = Path(d, "good.pdf"), Path(d, "bad.pdf")
        good.write_bytes(envelope(PDF_LF))
        bad.write_bytes(envelope(b"<html></html>"))
        rc = unwrap_files([str(good), str(bad)])
        check("--unwrap refuses when any result is not a PDF, and writes nothing",
              rc == 3 and good.read_bytes() == envelope(PDF_LF))
        rc = unwrap_files([str(good)])
        check("--unwrap rewrites the envelope as the PDF", rc == 0 and good.read_bytes() == PDF_LF)
        rc = unwrap_files([str(good)])
        check("--unwrap leaves a PDF alone", rc == 0 and good.read_bytes() == PDF_LF)

    tracked = subprocess.run(["git", "ls-files", "-z", "--", "*.pdf", "*.PDF"], cwd=REPO,
                             capture_output=True, check=True).stdout.split(b"\0")
    tracked = [t.decode() for t in tracked if t]
    not_pdf = [t for t in tracked if (REPO / t).exists() and (REPO / t).read_bytes()[:5] != b"%PDF-"]
    check(f"every tracked .pdf begins with %PDF- ({len(tracked)} files)", tracked and not not_pdf,
          ", ".join(not_pdf[:5]))

    print(f"{'FAIL' if failures else 'ok'}: {len(failures)} failure(s)")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
