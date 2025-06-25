"""
Provides the same behaviour as invoking ``flibook.cli`` but is more
convenient for end-users.
"""
from __future__ import annotations

from .cli import cli

if __name__ == "__main__":
    cli()
