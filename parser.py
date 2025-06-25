"""Parser for .inpx archives (non-standard ZIP without EOCD).

The .inpx file is a ZIP archive with extension changed and, in
some dumps, without the 22-byte *End of Central Directory* (EOCD) record.
`zipfile` fails on such files.  We work around this by appending a minimal
EOCD stub in memory and then opening the resulting stream with `zipfile`.

Exposes a single high-level helper `InpxParser.parse()` which yields dicts
representing each book row as parsed from the .inp files.

Example:
>>> for row in InpxParser().parse(Path("flibusta_fb2_local.inpx")):
...     print(row["title"], row["authors"])
"""
from __future__ import annotations

import io
import zipfile

from pathlib import Path
from typing import Iterable, List

_DEFAULT_STRUCTURE = (
    "AUTHOR;GENRE;TITLE;SERIES;SERNO;FILE;SIZE;LIBID;DEL;EXT;DATE;LANG;KEYWORDS;FOLDER;"
)


class InpxParser:
    """Parse .inpx file and yield book metadata rows (dicts)."""

    FIELD_SEPARATOR = "\x04"

    def __init__(self, encoding: str = "utf-8", fallback_encoding: str = "cp1251") -> None:
        self.encoding = encoding
        self.fallback_encoding = fallback_encoding

    # ---------------------------------------------------------------------
    # Public API
    # ---------------------------------------------------------------------

    def parse(
        self,
        path: Path | str,
        *,
        progress_cb: "Callable[[str,int,int],None] | None" = None,
    ) -> Iterable[dict]:
        """Yield dictionaries with book metadata for every record in .inp files.

        If *progress_cb* is provided, it will be called periodically with
        arguments *(file_name, processed_bytes, total_bytes)*.
        """
        from typing import Callable  # local import to avoid top-level overhead

        path = Path(path)
        with self._open_zip(path) as zf:
            structure = self._read_structure(zf)
            for inp_name in (n for n in zf.namelist() if n.endswith(".inp")):
                data = zf.read(inp_name)
                total_len = len(data)
                processed = 0
                for line in data.splitlines(keepends=False):
                    processed += len(line) + 1  # +1 for newline approx
                    if progress_cb and processed % 500000 == 0:  # every ~0.5 MB
                        progress_cb(inp_name, processed, total_len)
                    row = self._parse_line(line, structure)
                    if row:
                        yield row
                if progress_cb:
                    progress_cb(inp_name, total_len, total_len)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _open_zip(self, path: Path) -> zipfile.ZipFile:
        """Open a .inpx file tolerant to missing EOCD.

        Strategy: try the standard way first; if it fails with BadZipFile,
        read bytes, append a minimal EOCD record, and reopen from memory.
        """
        try:
            zf = zipfile.ZipFile(path)
            if zf.namelist():
                return zf
            zf.close()
        except zipfile.BadZipFile:
            pass  # fallback below

        # ------------------------------------------------------------------
        # Fallback: minimal ZIP parser sufficient for .inpx (no EOCD needed)
        # ------------------------------------------------------------------
        import struct, zlib, types, io

        data = Path(path).read_bytes()
        cd_sig = b"PK\x01\x02"
        lf_sig = b"PK\x03\x04"

        entries: dict[str, bytes] = {}
        offset = 0
        dlen = len(data)
        # scan entire file for central directory headers
        while offset < dlen:
            pos = data.find(cd_sig, offset)
            if pos == -1:
                break
            # central dir fixed part length
            if pos + 46 > dlen:
                break
            # headers 
            comp_method = int.from_bytes(data[pos + 10 : pos + 12], "little")
            name_len = int.from_bytes(data[pos + 28 : pos + 30], "little")
            extra_len = int.from_bytes(data[pos + 30 : pos + 32], "little")
            comment_len = int.from_bytes(data[pos + 32 : pos + 34], "little")
            lfh_off = int.from_bytes(data[pos + 42 : pos + 46], "little")
            name_start = pos + 46
            name_end = name_start + name_len
            fname = data[name_start:name_end].decode(errors="replace")

            # extract .inp and structure.info
            if fname.endswith(".inp") or fname == "structure.info":
                # parse local file header to locate data start
                lfh_pos = lfh_off
                if lfh_pos + 30 > dlen or data[lfh_pos : lfh_pos + 4] != lf_sig:
                    offset = pos + 4
                    continue
                # local header fields
                comp_size = int.from_bytes(data[lfh_pos + 18 : lfh_pos + 22], "little")
                uncomp_size = int.from_bytes(data[lfh_pos + 22 : lfh_pos + 26], "little")
                lf_name_len = int.from_bytes(data[lfh_pos + 26 : lfh_pos + 28], "little")
                lf_extra_len = int.from_bytes(data[lfh_pos + 28 : lfh_pos + 30], "little")
                data_start = lfh_pos + 30 + lf_name_len + lf_extra_len
                comp_data = data[data_start : data_start + comp_size]
                if comp_method == 0:  # stored
                    file_bytes = comp_data[:uncomp_size]
                elif comp_method == 8:  # deflate
                    file_bytes = zlib.decompress(comp_data, -15)
                else:
                    offset = pos + 4
                    continue
                entries[fname] = file_bytes
            offset = pos + 46  # continue searching

        # build a minimal in-memory ZipFile-like frontend
        class _PseudoZip:
            def __init__(self, files: dict[str, bytes]):
                self._files = files
            def namelist(self):
                return list(self._files)
            def open(self, name):
                return io.BytesIO(self._files[name])
            def read(self, name):
                return self._files[name]
            def __enter__(self):
                return self
            def __exit__(self, exc_type, exc, tb):
                return False
        return _PseudoZip(entries)

        # Fallback: build a valid EOCD record so that ``zipfile`` can parse the
        # central directory.  The *End of Central Directory* structure is::
        #     struct EOCD {
        #         uint32 signature = 0x06054b50;
        #         uint16 this_disk;
        #         uint16 cd_start_disk;
        #         uint16 records_on_this_disk;
        #         uint16 total_records;
        #         uint32 cd_size;
        #         uint32 cd_offset;
        #         uint16 comment_len;
        #     }
        # We locate the first occurrence of the central-directory header
        # signature (0x02014b50 = ``PK\x01\x02``) to find the
        # directory offset, count the number of headers and compute the
        # directory size.  A minimally-valid EOCD is then added so that the
        # standard :pymod:`zipfile` can work unmodified.
        import struct

        data = Path(path).read_bytes()

        # If EOCD already present, re-raise original exception instead of
        # corrupting data further - something else went wrong.
        if data[-22:].startswith(b"PK\x05\x06"):
            raise zipfile.BadZipFile("ZIP appears to contain EOCD yet could not be opened")

        cd_sig = b"PK\x01\x02"
        # Find first central-directory header.
        first_cd = data.find(cd_sig)
        if first_cd == -1:
            raise zipfile.BadZipFile("Central directory not found in INPX - cannot recover")

        # count of central-directory records
        total_records = 0
        ptr = first_cd
        dlen = len(data)
        while ptr + 46 <= dlen and data[ptr : ptr + 4] == cd_sig:
            # Central dir file header fixed part = 46 bytes
            # struct format <4s4B4HL2L5H (see spec) - we only need three 2-byte
            # length fields at the tail.
            name_len = int.from_bytes(data[ptr + 28 : ptr + 30], "little")
            extra_len = int.from_bytes(data[ptr + 30 : ptr + 32], "little")
            comment_len = int.from_bytes(data[ptr + 32 : ptr + 34], "little")
            header_size = 46 + name_len + extra_len + comment_len
            ptr += header_size
            total_records += 1
        # ``ptr`` now points to first byte after last header - start of EOCD
        cd_size = ptr - first_cd
        # Craft EOCD
        eocd = struct.pack(
            "<4s4H2LH",
            b"PK\x05\x06",  # signature
            0,                # this_disk
            0,                # cd_start_disk
            min(total_records, 0xFFFF),  # records_on_this_disk
            min(total_records, 0xFFFF),  # total_records
            cd_size & 0xFFFFFFFF,        # cd_size
            first_cd & 0xFFFFFFFF,       # cd_offset
            0,                # comment_len
        )
        data += eocd
        return zipfile.ZipFile(io.BytesIO(data))

    # ------------------------------------------------------------------
    # Line parsing helper extracted from old _parse_inp
    # ------------------------------------------------------------------
    def _parse_line(self, line_bytes: bytes, structure: List[str]):
        decode_errors = "replace"
        try:
            line_str = line_bytes.decode(self.encoding)
        except UnicodeDecodeError:
            line_str = line_bytes.decode(self.fallback_encoding, errors=decode_errors)
        line_str = line_str.rstrip("\r\n")
        if not line_str:
            return None
        fields = line_str.split(self.FIELD_SEPARATOR)
        row = {name.lower(): (fields[i] if i < len(fields) else "") for i, name in enumerate(structure)}
        # normalise fields as before
        row["authors"] = self._split_authors(row.get("author", ""))
        row["genres"] = self._split_many(row.get("genre", ""))
        row["deleted"] = row.get("del", "") == "1"
        def _to_int(val: str | None):
            try:
                return int(val) if val not in (None, "") else None
            except ValueError:
                return None
        row["serno"] = _to_int(row.get("serno"))
        row["size"] = _to_int(row.get("size"))
        row["libid"] = _to_int(row.get("libid"))
        return row

    def _read_structure(self, zf: zipfile.ZipFile) -> List[str]:
        """Return list of field names according to structure.info or default."""
        if "structure.info" in zf.namelist():
            with zf.open("structure.info") as fh:
                raw = fh.read()
            structure_line = raw.decode().strip()
        else:
            structure_line = _DEFAULT_STRUCTURE
        # remove trailing ';' and split
        return [f for f in structure_line.rstrip(";").split(";") if f]

    def _parse_inp(self, fh: io.BufferedReader, structure: List[str]):
        decode_errors = "replace"
        for line in fh:
            try:
                line_str = line.decode(self.encoding)
            except UnicodeDecodeError:
                line_str = line.decode(self.fallback_encoding, errors=decode_errors)
            line_str = line_str.rstrip("\r\n")
            if not line_str:
                continue
            fields = line_str.split(self.FIELD_SEPARATOR)
            row = {name.lower(): (fields[i] if i < len(fields) else "") for i, name in enumerate(structure)}
            # Normalise some fields
            row["authors"] = self._split_authors(row.get("author", ""))
            row["genres"] = self._split_many(row.get("genre", ""))
            row["deleted"] = row.get("del", "") == "1"
            def _to_int(val: str | None):
                try:
                    return int(val) if val not in (None, "") else None
                except ValueError:
                    return None
            row["serno"] = _to_int(row.get("serno"))
            row["size"] = _to_int(row.get("size"))
            row["libid"] = _to_int(row.get("libid"))
            yield row

    # -------------------------- split helpers --------------------------

    @staticmethod
    def _split_authors(authors_field: str) -> List[str]:
        # AUTHOR field example: "Last,First,:Another,Second,:"
        authors = [a for a in authors_field.split(":") if a]
        return authors

    @staticmethod
    def _split_many(field: str) -> List[str]:
        return [x for x in field.split(":") if x]
