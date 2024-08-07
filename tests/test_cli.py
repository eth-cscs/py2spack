"""Tests for cli.py module."""

from __future__ import annotations

import subprocess


def test_cli_available() -> None:
    """Check if cli is callable."""
    command = [
        "py2spack",
        "-h",
    ]

    result = subprocess.run(command, capture_output=True, text=True, check=True)

    assert result.returncode == 0

    assert "CLI for converting a python package and its dependencies to Spack." in result.stdout
