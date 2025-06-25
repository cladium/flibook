"""Command-line interface for flibook utilities."""
from __future__ import annotations

import logging
from pathlib import Path

import click

from .importer import import_inpx

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")


@click.group(invoke_without_command=True)
@click.pass_context
def cli(ctx):
    """Flibook utilities.
    If invoked without a sub-command it starts the web server (same as `run`)."""
    if ctx.invoked_subcommand is None:
        ctx.forward(run)


@cli.command("build", help="Build (index) the database from an INPX dump.")
@click.argument("inpx", type=click.Path(exists=True, path_type=Path))
@click.option("--db-url", default="sqlite:///flibook.db", help="SQLAlchemy DB URL.")
@click.option("--chunk-size", default=1000, help="Insert commit chunk size.")
@click.option("--dump-root", type=click.Path(exists=True, path_type=Path), help="Root of fb2 dump (archives).")
def build(inpx: Path, db_url: str, chunk_size: int, dump_root: Path | None):
    """Parse INPX file and populate database."""
    click.echo(f"Importing '{inpx}' into {db_url}…")
    total = import_inpx(inpx, db_url=db_url, chunk_size=chunk_size, dump_root=dump_root)
    click.echo(f"Imported {total} books.")


@cli.command("run", help="Run the web server.")
@click.option("--db-url", default="sqlite:///flibook.db", help="SQLAlchemy DB URL.")
@click.option("--host", default="127.0.0.1")
@click.option("--port", default=5000, type=int)
@click.option("--debug/--no-debug", default=False)
def run(db_url: str, host: str, port: int, debug: bool):
    """Run the Flibook web application."""
    from .web import create_app

    app = create_app(db_url)
    click.echo(f"* Serving on http://{host}:{port} (debug={debug})")
    app.run(host=host, port=port, debug=debug)


if __name__ == "__main__":  # pragma: no cover
    cli()
