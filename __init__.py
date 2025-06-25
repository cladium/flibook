"""Flibook package - digital library backend for library dump (images extracted).

This package provides:
    • InpxParser – parse .inpx metadata archives into Python objects.
    • SQLAlchemy ORM models (flibook.models) for persistence.
    • CLI utilities under flibook.cli (Click).
    • Flask web application entry-point (to be implemented).

The public API keeps IO-heavy pieces separate from web layer to ease testing.
"""

__all__ = [
    "InpxParser",
]

from .parser import InpxParser  # noqa: E402
