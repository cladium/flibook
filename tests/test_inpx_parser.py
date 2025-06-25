import io
import zipfile
from pathlib import Path

from flibook.parser import InpxParser


def _make_fake_inpx(tmp_path: Path) -> Path:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("structure.info", "AUTHOR;GENRE;TITLE;SERIES;SERNO;FILE;SIZE;LIBID;DEL;EXT;DATE;")
        inp_line = (
            "Doe,John,:\x04detective:\x04Sample Book\x04Sample Series\x04"
            "1\x04sample_book\x041234\x041\x04\x04fb2\x042020-01-01\x04"
        )
        zf.writestr("a.inp", inp_line)
    inpx_path = tmp_path / "test.inpx"
    inpx_path.write_bytes(buf.getvalue())
    return inpx_path


def test_inpx_parser_reads_row(tmp_path):
    inpx = _make_fake_inpx(tmp_path)
    rows = list(InpxParser().parse(inpx))
    assert len(rows) == 1
    row = rows[0]
    assert row["title"] == "Sample Book"
    assert row["authors"] == ["Doe,John,"]
    assert row["size"] == 1234
    assert row["ext"] == "fb2"
