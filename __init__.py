"""Flibook package - digital library backend for library dump (images extracted).

This package provides:
* InpxParser – parse .inpx metadata archives into Python objects.
* SQLAlchemy ORM models (flibook.models) for persistence.
* CLI utilities under flibook.cli (Click).
"""

__all__ = [
    "InpxParser",
]

from .parser import InpxParser  # noqa: E402
