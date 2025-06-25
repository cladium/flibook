"""
Determines the appropriate archive file (books, covers, images) that
contains a given `LIBID` (book ID).

Naming conventions (examples)::

    fb2-000024-030559.7z
    d.fb2-009373-367300.7z
    f.fb2-275618-280767.7z
    covers/fb2-000024-030559.zip
    covers/d.fb2-009373-367300.zip
    images/fb2-000024-030559.zip

The part before the first dashed range (``d``, ``f`` or nothing) does not
have semantic meaning for range detection, so it is ignored.  Ranges are
inclusive, i.e. ``fb2-000024-030559.7z`` contains ``LIBID`` 24 and 30559.
"""
from __future__ import annotations

import bisect
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

__all__ = [
    "ArchiveResolver",
    "ArchiveInfo",
]


@dataclass(frozen=True, order=True)
class ArchiveInfo:
    """Represents a single archive covering an inclusive ID range."""

    start: int
    end: int
    path: Path

    def contains(self, book_id: int) -> bool:
        return self.start <= book_id <= self.end


class ArchiveResolver:
    """Locate fb2/cover/image archives for a given *book_id*.

    Parameters
    ----------
    dump_root: str | Path
        Path to directory that contains archive files and sub-directories
        ``covers`` and ``images``.
    cache: bool, default ``True``
        Keep parsed lists in memory for fast re-use.
    """

    # regex matches optional leading char(s) before "fb2-" and extracts range
    _BOOK_RE = re.compile(r"(?:[a-z]\.)?fb2-(\d+)-(\d+)\.7z$", re.IGNORECASE)
    _COVER_IMG_RE = re.compile(r"(?:[a-z]\.)?fb2-(\d+)-(\d+)\.zip$", re.IGNORECASE)

    def __init__(self, dump_root: Path | str, *, cache: bool = True):
        self.dump_root = Path(dump_root).expanduser().resolve()
        if not self.dump_root.exists():
            raise FileNotFoundError(self.dump_root)

        self._book_archives: List[ArchiveInfo] = []
        self._cover_archives: List[ArchiveInfo] = []
        self._image_archives: List[ArchiveInfo] = []

        self._scan_archives()

        if cache is False:
            # allow GC to reclaim lists later if caller only needs one-off use
            import weakref

            self._book_archives = weakref.proxy(self._book_archives)  
            self._cover_archives = weakref.proxy(self._cover_archives)  
            self._image_archives = weakref.proxy(self._image_archives)  

    # public helpers
    def resolve_all(self, book_id: int) -> Dict[str, Optional[Path]]:
        """Return dictionary with keys ``fb2``, ``cover``, ``image``.

        Any of the values may be *None* if a matching archive was not located.
        """
        return {
            "fb2": self._find(book_id, self._book_archives),
            "cover": self._find(book_id, self._cover_archives),
            "image": self._find(book_id, self._image_archives),
        }

    # alias for compatibility – expected later by importer
    resolve = resolve_all

    def _scan_archives(self) -> None:
        """Populate internal lists with ArchiveInfo items."""
        # books live both in dump_root itself and potentially sub-folders
        for path in self.dump_root.rglob("*.7z"):
            m = self._BOOK_RE.search(path.name)
            if m:
                start, end = map(int, m.groups())
                self._book_archives.append(ArchiveInfo(start, end, path))

        covers_dir = self.dump_root / "covers"
        images_dir = self.dump_root / "images"
        for path in covers_dir.rglob("*.zip") if covers_dir.exists() else []:
            m = self._COVER_IMG_RE.search(path.name)
            if m:
                start, end = map(int, m.groups())
                self._cover_archives.append(ArchiveInfo(start, end, path))
        for path in images_dir.rglob("*.zip") if images_dir.exists() else []:
            m = self._COVER_IMG_RE.search(path.name)
            if m:
                start, end = map(int, m.groups())
                self._image_archives.append(ArchiveInfo(start, end, path))

        # sort lists for bisection search
        self._book_archives.sort(key=lambda a: a.start)
        self._cover_archives.sort(key=lambda a: a.start)
        self._image_archives.sort(key=lambda a: a.start)

    @staticmethod
    def _find(book_id: int, archives: List[ArchiveInfo]) -> Optional[Path]:
        """Binary-search *archives* list to find archive containing *book_id*."""
        if not archives:
            return None
        # build list of starts for bisect
        starts = [arc.start for arc in archives]
        idx = bisect.bisect_right(starts, book_id) - 1
        if idx < 0:
            return None
        candidate = archives[idx]
        return candidate.path if candidate.contains(book_id) else None
