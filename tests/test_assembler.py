from pathlib import Path
import base64
import xml.etree.ElementTree as ET

from flibook.assembler import assemble_fb2
from flibook.models import Book
import zipfile


def _create_zip(archive: Path, name: str, data: bytes):
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr(name, data)


def test_assemble_fb2(tmp_path: Path):
    book_id = 42
    file_stub = "test"

    # create tiny fb2 xml
    fb2_xml = f"""<?xml version='1.0' encoding='utf-8'?>\n<FictionBook xmlns='http://www.gribuser.ru/xml/fictionbook/2.0' xmlns:l='http://www.w3.org/1999/xlink'>\n <description><title-info><book-title>Test</book-title></title-info></description>\n <body><section><p>Sample</p></section></body>\n</FictionBook>"""

    fb2_archive = tmp_path / "fb2-40-50.zip"
    _create_zip(fb2_archive, f"{book_id}.fb2", fb2_xml.encode())

    # cover image
    cover_data = b"COVER"  # dummy bytes
    cover_archive = tmp_path / "covers.zip"
    _create_zip(cover_archive, f"{book_id}.jpg", cover_data)

    # images
    img_data = b"IMG1"
    images_archive = tmp_path / "images.zip"
    _create_zip(images_archive, f"{file_stub}_1.jpg", img_data)

    # build Book object
    book = Book(
        id=book_id,
        title="Test",
        file_stub=file_stub,
        file_ext="fb2",
        folder=None,
        size=len(fb2_xml),
        fb2_archive=str(fb2_archive),
        cover_archive=str(cover_archive),
        images_archive=str(images_archive),
    )

    result = assemble_fb2(book)

    root = ET.fromstring(result)
    ns_fb = "{http://www.gribuser.ru/xml/fictionbook/2.0}"
    ns_l = "{http://www.w3.org/1999/xlink}"
    binaries = root.findall(f"{ns_fb}binary")
    assert len(binaries) == 2

    ids = {b.get("id") for b in binaries}
    # must contain image binary and some cover binary (cover.jpg or book_id.jpg)
    assert f"{file_stub}_1.jpg" in ids
    assert (f"{book_id}.jpg" in ids) or ("cover.jpg" in ids)

    # ensure base64 content matches original bytes
    for b in binaries:
        data = base64.b64decode(b.text.encode())
        if b.get("id") in {f"{book_id}.jpg", "cover.jpg"}:
            assert data == cover_data
        else:
            assert data == img_data

    # verify coverpage href
    cover_img = root.find(f".//{ns_fb}coverpage/{ns_fb}image")
    assert cover_img is not None
    href = cover_img.attrib.get(f"{ns_l}href")
    assert href and href[1:] in ids
