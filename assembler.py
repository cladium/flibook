"""Real-time assembly of full FB2 books with embedded images.

With `Book` SQLAlchemy object (already containing archive paths), the
function `assemble_fb2` returns `bytes` of the complete FB2 XML with all
binary images and cover embedded.

For speed we *stream* from the archives without extracting them entirely.
The result is suitable for immediate `send_file` / `send_bytes` in Flask.
"""
from __future__ import annotations

import base64
import io
import re
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import List, Tuple

from .archive_extract import open_member
from .models import Book

# namespace helpers
NSMAP = {
    "fb": "http://www.gribuser.ru/xml/fictionbook/2.0",
    "l": "http://www.w3.org/1999/xlink",
}
for prefix, uri in NSMAP.items():
    ET.register_namespace(prefix if prefix != "fb" else "", uri)


def _build_binary_element(fname: str, data: bytes) -> ET.Element:
    elem = ET.Element("binary", attrib={"id": fname, "content-type": _mime_from_name(fname)})
    elem.text = base64.b64encode(data).decode()
    return elem


def _mime_from_name(fname: str) -> str:
    ext = Path(fname).suffix.lower()
    if ext:
        return {
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".png": "image/png",
            ".gif": "image/gif",
        }.get(ext, "application/octet-stream")
    # assume JPEG for extensionless names
    return "image/jpeg"


# ---------------------------------------------------------------------------

def assemble_fb2(book: Book) -> bytes:
    """Assemble and return full FB2 XML for *book* (with images)."""

    if not book.fb2_archive:
        raise FileNotFoundError("fb2 archive path missing in DB")

    fb2_filename = f"{book.id}.fb2"

    # load original FB2 XML
    with open_member(book.fb2_archive, fb2_filename) as fp:
        tree = ET.parse(fp)
    root = tree.getroot()

    # collect images to embed
    binaries: List[Tuple[str, bytes]] = []

    # determine existing coverpage reference, if any
    cover_elem = root.find('.//{http://www.gribuser.ru/xml/fictionbook/2.0}coverpage/{http://www.w3.org/1999/xlink}image')
    cover_id = None
    if cover_elem is not None:
        href = cover_elem.attrib.get('{http://www.w3.org/1999/xlink}href', '')
        if href.startswith('#'):
            cover_id = href[1:]
    if cover_id is None:
        cover_id = 'cover.jpg'
    if book.cover_archive:
        import zipfile, py7zr
        cov_path = Path(book.cover_archive)
        cov_data: bytes | None = None
        if cov_path.suffix.lower() == ".zip":
            with zipfile.ZipFile(cov_path) as zf:
                # candidate names: id or id.jpg else first file
                cand = None
                for n in zf.namelist():
                    base = Path(n).name
                    if base in {str(book.id), f"{book.id}.jpg"} and not n.endswith('/'):
                        cand = n
                        break
                if cand is None:
                    cand = next((n for n in zf.namelist() if not n.endswith('/')), None)
                if cand:
                    with zf.open(cand) as fp:
                        cov_data = fp.read()
                        cov_name = cand
        elif cov_path.suffix.lower() == ".7z":
            with py7zr.SevenZipFile(cov_path, mode="r") as zf:
                names = [n for n in zf.getnames() if not n.endswith('/')]
                cand = None
                for n in names:
                    base = Path(n).name
                    if base in {str(book.id), f"{book.id}.jpg"}:
                        cand = n
                        break
                if cand is None and names:
                    cand = names[0]
                if cand:
                    cov_data = zf.read([cand])[cand]
                    cov_name = cand
        if cov_data:
            binaries.append((cover_id, cov_data))

    # ensure <coverpage> references the cover_id
    ns_fb = "{http://www.gribuser.ru/xml/fictionbook/2.0}"
    ns_l = "{http://www.w3.org/1999/xlink}"
    if cover_id:
        if cover_elem is not None:
            cover_elem.attrib[f"{ns_l}href"] = f"#{cover_id}"
        else:
            title_info = root.find(f".//{ns_fb}title-info")
            if title_info is not None:
                coverpage = ET.SubElement(title_info, f"{ns_fb}coverpage")
                img = ET.SubElement(coverpage, f"{ns_fb}image")
                img.attrib[f"{ns_l}href"] = f"#{cover_id}"

    # embed images referenced in the FB2 body
    if book.images_archive:
        # collect all xlink hrefs in <image> elements
        href_ids: set[str] = set()
        for img in root.findall('.//{http://www.gribuser.ru/xml/fictionbook/2.0}image'):
            href = img.attrib.get('{http://www.w3.org/1999/xlink}href')
            if href and href.startswith('#'):
                href_ids.add(href[1:])

        if href_ids:
            arch_path = Path(book.images_archive)
            if arch_path.suffix.lower() == '.zip':
                import zipfile

                with zipfile.ZipFile(arch_path) as zf:
                    namelist = {}
                    for n in zf.namelist():
                        if n.endswith('/'):
                            continue
                        parts = Path(n).parts
                        if len(parts) >= 2 and parts[0] == str(book.id):
                            namelist[parts[-1]] = n
                    for img_id in href_ids:
                        if any(img_id == b[0] for b in binaries):
                            continue  # already embedded (e.g., cover)
                        cand = None
                        for variant in (img_id, f"{img_id}.jpg", f"{img_id}.png", f"{img_id}.gif"):
                            if variant in namelist:
                                cand = namelist[variant]
                                break
                        if cand:
                            with zf.open(cand) as fp:
                                binaries.append((img_id, fp.read()))
            else:
                import py7zr

                with py7zr.SevenZipFile(arch_path, mode='r') as zf:
                    all_names = {}
                    for n in zf.getnames():
                        if n.endswith('/'):
                            continue
                        parts = Path(n).parts
                        if len(parts) >= 2 and parts[0] == str(book.id):
                            all_names[parts[-1]] = n
                    for img_id in href_ids:
                        if any(img_id == b[0] for b in binaries):
                            continue
                        cand = None
                        for variant in (img_id, f"{img_id}.jpg", f"{img_id}.png", f"{img_id}.gif"):
                            if variant in all_names:
                                cand = all_names[variant]
                                break
                        if cand:
                            data = zf.read([cand])[cand]
                            binaries.append((img_id, data))

    # append <binary> elements at the end of FB2 root
    for fname, data in binaries:
        root.append(_build_binary_element(fname, data))

    buf = io.BytesIO()
    tree.write(buf, encoding="utf-8", xml_declaration=True)
    return buf.getvalue()
