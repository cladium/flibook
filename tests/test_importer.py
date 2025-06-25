"""Tests for database importer."""
from pathlib import Path

from flibook.importer import import_inpx
from flibook.models import get_session, init_db, Author, Book, Series
from .test_inpx_parser import _make_fake_inpx


def test_importer_inserts_rows(tmp_path: Path):
    db_url = f"sqlite:///{tmp_path / 'test.db'}"
    inpx_path = _make_fake_inpx(tmp_path)
    # run importer
    total = import_inpx(inpx_path, db_url=db_url, chunk_size=10)
    assert total == 1

    # query session
    init_db(db_url)  # ensure same engine
    session = get_session()
    assert session.query(Book).count() == 1
    book: Book = session.query(Book).first()
    assert book.title == "Sample Book"
    # author joined
    assert len(book.authors) == 1
    author: Author = book.authors[0]
    assert author.last_name == "Doe"
    # series
    assert book.series is not None
    assert book.series.name == "Sample Series"
