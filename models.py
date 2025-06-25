"""SQLAlchemy ORM models for Flibook."""

from __future__ import annotations

import datetime as _dt
from typing import List

from sqlalchemy import Column, Date, ForeignKey, Integer, String, create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, sessionmaker


class Base(DeclarativeBase):
    pass


class Author(Base):
    __tablename__ = "authors"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    last_name: Mapped[str] = mapped_column(String, nullable=False)
    first_name: Mapped[str | None] = mapped_column(String, nullable=True)
    middle_name: Mapped[str | None] = mapped_column(String, nullable=True)

    books: Mapped[List["Book"]] = relationship(back_populates="authors", secondary="book_authors")

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Author {self.last_name} {self.first_name or ''} {self.middle_name or ''}>"


class Series(Base):
    __tablename__ = "series"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String, unique=True, nullable=False)

    books: Mapped[List["Book"]] = relationship(back_populates="series")


class Book(Base):
    __tablename__ = "books"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)  # library ID from .inp (LIBID)
    title: Mapped[str] = mapped_column(String, nullable=False)
    file_stub: Mapped[str] = mapped_column(String, nullable=False)  # FILE without extension
    file_ext: Mapped[str] = mapped_column(String, nullable=False)
    folder: Mapped[str | None] = mapped_column(String, nullable=True)
    size: Mapped[int] = mapped_column(Integer)
    date: Mapped[_dt.date | None] = mapped_column(Date)
    deleted: Mapped[bool] = mapped_column(Integer, default=0)

    series_id: Mapped[int | None] = mapped_column(ForeignKey("series.id"))
    series: Mapped[Series | None] = relationship(back_populates="books")

    authors: Mapped[List[Author]] = relationship(back_populates="books", secondary="book_authors")

    # paths to archives
    fb2_archive: Mapped[str | None] = mapped_column(String)
    cover_archive: Mapped[str | None] = mapped_column(String)
    images_archive: Mapped[str | None] = mapped_column(String)


class BookAuthor(Base):
    __tablename__ = "book_authors"

    book_id: Mapped[int] = mapped_column(ForeignKey("books.id"), primary_key=True)
    author_id: Mapped[int] = mapped_column(ForeignKey("authors.id"), primary_key=True)


# database helpers

_engine = None
_Session = None


def init_db(url: str = "sqlite:///flibook.db") -> None:
    """Create engine, create tables if not exist, globally store session factory."""
    global _engine, _Session
    from sqlalchemy import event

    _engine = create_engine(url, future=True)

    # register Unicode-aware lower() that SQLite will use in SQL
    @event.listens_for(_engine, "connect")
    def register_unicode_lower(dbapi_conn, _): 
        dbapi_conn.create_function("lower", 1, lambda s: s.lower() if isinstance(s, str) else s)

    Base.metadata.create_all(_engine)
    _Session = sessionmaker(_engine, expire_on_commit=False, future=True)


def get_session():
    if _Session is None:
        raise RuntimeError("Database not initialized. Call init_db() first.")
    return _Session()
