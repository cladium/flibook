"""
extracting a single file from flibook archives.

Supports:
* 7z archives (requires `py7zr`)
* zip archives (standard library)

no external 7-Zip binary is required (finally, jeez)
"""
from __future__ import annotations

import contextlib
import shutil
import tempfile
from pathlib import Path
from typing import BinaryIO

import zipfile

try:
    import py7zr  
except ModuleNotFoundError:  
    py7zr = None  


class UnsupportedArchiveError(RuntimeError):
    pass


@contextlib.contextmanager
def open_member(archive_path: Path | str, member: str) -> BinaryIO:  # noqa: D401 (simple context manager)
    """Yield a readable binary object of *member* inside *archive_path*.

    The archive is *not* extracted to disk; instead the member is streamed via a
    temporary file to satisfy APIs that expect a real path.
    """

    archive_path = Path(archive_path).expanduser().resolve()
    if not archive_path.exists():
        raise FileNotFoundError(archive_path)

    suffix = archive_path.suffix.lower()

    if suffix == ".zip":
        with zipfile.ZipFile(archive_path) as zf:
            try:
                src = zf.open(member)
            except KeyError:
                # member absent – fallback to first non-directory entry
                for name in zf.namelist():
                    if not name.endswith('/'):
                        src = zf.open(name)
                        break
                else:
                    raise FileNotFoundError(member)
            with src:
                with tempfile.NamedTemporaryFile(delete=False) as tmp:
                    shutil.copyfileobj(src, tmp)
                    tmp.flush()
                    tmp.seek(0)
                    try:
                        yield open(tmp.name, "rb")  # type: ignore[abstract]
                    finally:
                        Path(tmp.name).unlink(missing_ok=True)
    elif suffix == ".7z":
        if py7zr is None:
            raise UnsupportedArchiveError("py7zr is not installed; cannot read .7z archives")
        with py7zr.SevenZipFile(archive_path, mode="r") as zf:
            # extract target to temp dir
            with tempfile.TemporaryDirectory() as td:
                zf.extract(targets=[member], path=td)
                path = Path(td) / member
                if not path.exists():
                    raise FileNotFoundError(member)
                yield path.open("rb")
    else:
        raise UnsupportedArchiveError(f"Unknown archive type: {archive_path}")
