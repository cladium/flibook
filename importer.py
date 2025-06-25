"""Database population helpers."""

from __future__ import annotations

from pathlib import Path
from typing import Iterable

from sqlalchemy.exc import IntegrityError

from .archive_resolver import ArchiveResolver

from .models import Author, Book, Series, get_session, init_db
from .parser import InpxParser

__all__ = ["import_inpx"]


def import_inpx(
    inpx: Path,
    db_url: str = "sqlite:///flibook.db",
    chunk_size: int = 1000,
    dump_root: Path | None = None,
) -> int:
    """Parse *inpx* and insert rows into DB specified by *db_url*.

    Returns the number of imported books.
    """
    init_db(db_url)
    session = get_session()
    parser = InpxParser()
    resolver = ArchiveResolver(dump_root) if dump_root else None

    # performance optimisation caches
    authors_cache: dict[tuple[str | None, str | None, str | None], Author] = {}
    series_cache: dict[str, Series] = {}

    count = 0
    buffer: list[dict] = []
    import sys, time
    start_ts = time.time()
    last_report = 0.0

    def _progress_cb(fname: str, done: int, total: int):
        nonlocal last_report
        pct = done / total * 100 if total else 0
        if pct - last_report >= 5 or done == total:  # report every 5%
            elapsed = time.time() - start_ts
            sys.stderr.write(
                f"\r[{fname}] {pct:5.1f}%  | {done//1024//1024}MB/{total//1024//1024}MB  | {elapsed:,.0f}s elapsed"
            )
            sys.stderr.flush()
            last_report = pct

    for row in parser.parse(inpx, progress_cb=_progress_cb):
        buffer.append(row)
        if len(buffer) >= chunk_size:
            _flush(buffer, session, resolver, authors_cache, series_cache)
            count += len(buffer)
            buffer.clear()
    if buffer:
        _flush(buffer, session, resolver, authors_cache, series_cache)
        count += len(buffer)
    session.commit()
    session.close()
    return count


def _flush(buffer: list[dict], session, resolver, authors_cache, series_cache):
    for row in buffer:
        # skip records lacking numeric book ID
        if row.get("libid") is None:
            continue

        authors = _ensure_authors(session, row["authors"], authors_cache)
        series_obj = _ensure_series(session, row.get("series"), series_cache)
        # convert ISO date string to date object if present
        date_obj = None
        if row.get("date"):
            from datetime import date as _date
            try:
                date_obj = _date.fromisoformat(row["date"])
            except ValueError:
                pass  # leave None if bad format
        # resolve archives if possible
        fb2_path = cover_path = img_path = None
        if resolver:
            resolved = resolver.resolve(row["libid"])
            fb2_path = resolved["fb2"].as_posix() if resolved["fb2"] else None
            cover_path = resolved["cover"].as_posix() if resolved["cover"] else None
            img_path = resolved["image"].as_posix() if resolved["image"] else None

        # skip if already in DB
        if session.get(Book, row["libid"]):
            continue

        book = Book(
            id=row["libid"],
            title=row["title"],
            file_stub=row["file"],
            file_ext=row["ext"],
            folder=row.get("folder"),
            size=row["size"],
            date=date_obj,
            deleted=row.get("deleted", False),
            fb2_archive=fb2_path,
            cover_archive=cover_path,
            images_archive=img_path,
            series=series_obj,
            # archive paths will be added later by additional logic
        )
        book.authors = authors
        session.add(book)
    session.flush()


def _ensure_authors(session, authors_list: Iterable[str], cache: dict):
    objs: list[Author] = []
    for full in authors_list:
        parts = [p.strip() for p in full.split(",")]
        last = parts[0] if len(parts) > 0 and parts[0] else None
        first = parts[1] if len(parts) > 1 and parts[1] else None
        middle = parts[2] if len(parts) > 2 and parts[2] else None
        # Ensure last_name is never NULL – shift first name if necessary
        if last is None:
            last, first = first, None
        key = (
            (last or "").lower() if last else None,
            (first or "").lower() if first else None,
            (middle or "").lower() if middle else None,
        )
        obj = cache.get(key)
        if obj is None:
            obj = (
                session.query(Author)
                .filter_by(last_name=last, first_name=first, middle_name=middle)
                .one_or_none()
            )
            if obj is None:
                obj = Author(last_name=last, first_name=first, middle_name=middle)
                session.add(obj)
                session.flush([obj])
            cache[key] = obj
        objs.append(obj)
    return objs


def _ensure_series(session, name: str | None, cache: dict[str, Series]):
    if not name:
        return None
    key = name.strip().lower()
    obj = cache.get(key)
    if obj is None:
        obj = session.query(Series).filter_by(name=name).one_or_none()
        if obj is None:
            obj = Series(name=name)
            session.add(obj)
            session.flush([obj])
        cache[key] = obj
    return obj
