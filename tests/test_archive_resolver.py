import os
from pathlib import Path

import pytest

from flibook.archive_resolver import ArchiveResolver


@pytest.fixture()
def dummy_dump(tmp_path: Path) -> Path:
    """Create a fake dump directory with a handful of archives."""
    # top-level 7z archives
    (tmp_path / "fb2-10-20.7z").touch()
    (tmp_path / "d.fb2-21-30.7z").touch()

    # covers and images sub-dirs
    covers = tmp_path / "covers"
    images = tmp_path / "images"
    covers.mkdir()
    images.mkdir()
    (covers / "fb2-10-20.zip").touch()
    (covers / "d.fb2-21-30.zip").touch()
    (images / "fb2-10-20.zip").touch()
    (images / "d.fb2-21-30.zip").touch()
    return tmp_path


def test_resolve_inside_range(dummy_dump: Path):
    resolver = ArchiveResolver(dummy_dump)

    result = resolver.resolve(15)
    assert result["fb2"].name == "fb2-10-20.7z"
    assert result["cover"].name == "fb2-10-20.zip"
    assert result["image"].name == "fb2-10-20.zip"

    result2 = resolver.resolve(25)
    assert result2["fb2"].name == "d.fb2-21-30.7z"
    assert result2["cover"].name == "d.fb2-21-30.zip"
    assert result2["image"].name == "d.fb2-21-30.zip"


def test_resolve_boundary_values(dummy_dump: Path):
    resolver = ArchiveResolver(dummy_dump)

    assert resolver.resolve(10)["fb2"].name == "fb2-10-20.7z"
    assert resolver.resolve(20)["fb2"].name == "fb2-10-20.7z"
    assert resolver.resolve(21)["fb2"].name == "d.fb2-21-30.7z"
    assert resolver.resolve(30)["fb2"].name == "d.fb2-21-30.7z"


def test_resolve_not_found(dummy_dump: Path):
    resolver = ArchiveResolver(dummy_dump)
    assert resolver.resolve(31)["fb2"] is None
