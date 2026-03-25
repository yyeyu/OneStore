"""Unified entrypoint for the API application and CLI."""

from app.api.app import create_app
from app.cli.app import cli

app = create_app()


def run() -> None:
    """Run the Typer CLI."""
    cli()


if __name__ == "__main__":
    run()
