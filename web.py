"""Flask web interface for Flibook."""
from __future__ import annotations

import io
import logging
from typing import List

from flask import Flask, abort, jsonify, render_template, request, send_file, url_for
from sqlalchemy import and_, or_, func

from .assembler import assemble_fb2
from .models import Book, Author, get_session, init_db

logger = logging.getLogger(__name__)


def create_app(db_url: str = "sqlite:///flibook.db") -> Flask:  # pragma: no cover
    app = Flask(__name__)
    init_db(db_url)

    @app.route("/")
    def index():
        return render_template("index.html")

    @app.route("/search")
    def search():
        q = request.args.get("q", "").strip()
        session = get_session()
        if not q:
            return render_template("search.html", books=[])
        import re
        tokens = [w for w in re.split(r"\s+", q) if w]
        if not tokens:
            return render_template("search.html", books=[])

        from sqlalchemy import and_, or_

        import unicodedata
        def variants(word: str) -> list[str]:
            v = [word]
            if word and word[0].isalpha():
                v.append(word.capitalize())
            return list(dict.fromkeys(v))  # unique

        token_conds = []
        for tok in tokens:
            pats = [f"%{v}%" for v in variants(tok)]
            cond_parts = []
            for p in pats:
                cond_parts.append(Book.title.like(p))
                cond_parts.append(Author.last_name.like(p))
                cond_parts.append(Author.first_name.like(p))
                cond_parts.append(Author.middle_name.like(p))
            token_conds.append(or_(*cond_parts))

        final_cond = and_(*token_conds)

        books: List[Book] = (
            session.query(Book)
            .join(Book.authors)
            .filter(final_cond)
            .order_by(Book.date.desc())
            .distinct()
            .all()
        )

        books: List[Book] = (
            session.query(Book)
            .join(Book.authors)
            .filter(final_cond)
            .order_by(Book.date.desc())
            .distinct()
            .all()
        )
        return render_template("search.html", books=books, query=q)

    @app.route("/book/<int:book_id>")
    def book_detail(book_id: int):
        session = get_session()
        book = session.get(Book, book_id)
        if not book:
            abort(404)
        pub_year = None 
        # detect cover presence strictly (no fallback)
        cover_exists = False
        if book.cover_archive:
            from pathlib import Path
            import zipfile
            arch_path = Path(book.cover_archive)
            try:
                if arch_path.suffix.lower() == '.zip':
                    with zipfile.ZipFile(arch_path) as zf:
                        cover_exists = any(
                            Path(n).name in {str(book.id), f"{book.id}.jpg"} for n in zf.namelist() if not n.endswith('/')
                        )
                elif arch_path.suffix.lower() == '.7z':
                    import py7zr  # type: ignore
                    with py7zr.SevenZipFile(arch_path, mode='r') as zf:
                        cover_exists = any(
                            Path(n).name in {str(book.id), f"{book.id}.jpg"} for n in zf.getnames() if not n.endswith('/')
                        )
            except FileNotFoundError:
                cover_exists = False

        annotation_html = None
        if book.fb2_archive:
            from .archive_extract import open_member
            fb2_name = f"{book.id}.fb2"
            try:
                with open_member(book.fb2_archive, fb2_name) as fp:
                    import xml.etree.ElementTree as ET, html
                    tree = ET.parse(fp)
                    ns = {
                        'fb': 'http://www.gribuser.ru/xml/fictionbook/2.0',
                    }
                                        # publication year
                    yr_elem = tree.find('.//fb:publish-info/fb:year', ns)
                    if yr_elem is not None and yr_elem.text:
                        pub_year = yr_elem.text.strip()
                    # annotation
                    ann = tree.find('.//fb:annotation', ns)
                    if ann is not None:
                        # Simple serialize inner XML to HTML
                        parts = [ET.tostring(e, encoding='unicode', method='html') for e in ann]
                        annotation_html = ''.join(parts)
            except FileNotFoundError:
                pass
        return render_template(
            "book.html",
            book=book,
            annotation=annotation_html,
            cover_exists=cover_exists,
            pub_year=pub_year,
        )

    @app.route("/cover/<int:book_id>")
    def cover(book_id: int):
        session = get_session()
        book = session.get(Book, book_id)
        if not book or not book.cover_archive:
            abort(404)
        import mimetypes
        from .archive_extract import open_member

        import zipfile
        from pathlib import Path
        archive_path = Path(book.cover_archive)
        data: bytes | None = None
        if archive_path.suffix.lower() == ".zip":
            with zipfile.ZipFile(archive_path) as zf:
                # candidate names: id or id.jpg
                cand = None
                for name in zf.namelist():
                    base = Path(name).name
                    if base in {str(book_id), f"{book_id}.jpg"}:
                        cand = name
                        break
                if cand is None:
                    abort(404)
                with zf.open(cand) as fp:
                    data = fp.read()
        elif archive_path.suffix.lower() == ".7z":
            import py7zr  # type: ignore

            with py7zr.SevenZipFile(archive_path, mode="r") as zf:
                names = zf.getnames()
                cand = None
                for name in names:
                    base = Path(name).name
                    if base in {str(book_id), f"{book_id}.jpg"}:
                        cand = name
                        break
                if cand is None:
                    abort(404)
                data = zf.read([cand])[cand]
        else:
            abort(404)

        if data is None:
            abort(404)
        buf = io.BytesIO(data)
        buf.seek(0)
        return send_file(buf, mimetype="image/jpeg")

    @app.route("/download/<int:book_id>")
    def download(book_id: int):
        session = get_session()
        book = session.get(Book, book_id)
        if not book:
            abort(404)
        try:
            fb2_bytes = assemble_fb2(book)
        except FileNotFoundError as e:
            logger.error("%s", e)
            abort(404)
        buf = io.BytesIO(fb2_bytes)
        buf.seek(0)
        return send_file(
            buf,
            as_attachment=True,
            download_name=f"{book_id}.fb2",
            mimetype="application/xml+fictionbook",
        )

    return app
