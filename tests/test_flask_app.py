from pathlib import Path
import zipfile

from flibook.web import create_app
from flibook.models import Book, Author, get_session, init_db


def _create_zip(path: Path, name: str, data: bytes):
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr(name, data)


def _setup_db(tmp_path: Path):
    db_path = tmp_path / "test.db"
    db_url = f"sqlite:///{db_path}"
    init_db(db_url)
    sess = get_session()

    # create sample author
    author = Author(last_name="Doe")
    sess.add(author)
    sess.flush([author])

    book_id = 1
    file_stub = "sample"

    # archives
    fb2_arch = tmp_path / "fb2.zip"
    cover_arch = tmp_path / "covers.zip"
    img_arch = tmp_path / "img.zip"

    fb2_xml = """<?xml version='1.0' encoding='utf-8'?><FictionBook xmlns='http://www.gribuser.ru/xml/fictionbook/2.0'></FictionBook>"""
    _create_zip(fb2_arch, f"{book_id}.fb2", fb2_xml.encode())
    _create_zip(cover_arch, f"{book_id}.jpg", b"COVER")
    _create_zip(img_arch, f"{file_stub}_1.jpg", b"IMG")

    book = Book(
        id=book_id,
        title="Sample",
        file_stub=file_stub,
        file_ext="fb2",
        size=len(fb2_xml),
        fb2_archive=str(fb2_arch),
        cover_archive=str(cover_arch),
        images_archive=str(img_arch),
    )
    book.authors.append(author)
    sess.add(book)
    sess.commit()
    sess.close()
    return db_url, book_id


def test_flask_endpoints(tmp_path):
    db_url, book_id = _setup_db(tmp_path)
    app = create_app(db_url)
    app.testing = True
    client = app.test_client()

    # index
    resp = client.get("/")
    assert resp.status_code == 200

    # search
    resp = client.get("/search", query_string={"q": "Sample"})
    assert resp.status_code == 200
    assert b"Sample" in resp.data

    # book detail
    resp = client.get(f"/book/{book_id}")
    assert resp.status_code == 200

    # download
    resp = client.get(f"/download/{book_id}")
    assert resp.status_code == 200
    assert resp.headers["Content-Type"].startswith("application/xml")
    assert resp.data.startswith(b"<?xml")
