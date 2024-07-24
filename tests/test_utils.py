"""Tests for utils.py module."""

from __future__ import annotations

import io
import pathlib

import pytest

from py2spack import utils


@pytest.mark.parametrize(
    "url",
    [
        (
            "https://files.pythonhosted.org/packages/a2/47/c9997eb470a7f48f7aaddd3d9a828244a2e4199569e38128715c48059ac1/black-24.4.2.tar.gz"
        ),
        (
            "https://files.pythonhosted.org/packages/36/bf/a462f36723824c60dc3db10528c95656755964279a6a5c287b4f9fd0fa84/black-23.10.1.tar.gz"
        ),
        (
            "https://files.pythonhosted.org/packages/5a/c0/b7599d6e13fe0844b0cda01b9aaef9a0e87dbb10b06e4ee255d3fa1c79a2/tqdm-4.66.4.tar.gz"
        ),
    ],
)
def test_download_sdist(url: str) -> None:
    """Unit tests for method."""
    assert isinstance(utils.download_sdist(url), io.BytesIO)


@pytest.mark.parametrize(
    "url",
    [
        (
            "https://files.pythonhosted.org/packages/a2/47/c9997eb470a7f48f7aaddd3d9a828244a2e4199569e38128715c48059ac1/INVALID-PACKAGE-black-24.4.2.tar.gz"
        ),
        (
            "https://files.pythonhosted.org/packages/36/bf/a462f36723824c60dc3db10528c95656755964279a6a5c287b4f9fd0fa84/black-23.10.1.tar.gz.xyz"
        ),
        (
            "https://files.pythonhosted.org/packages/5a/c0/b7599d6e13fe0844b0cda01b9aaef9a0e87dbb10b06e4ee255d3fa1c79a2/tqdm-4.66.4.tar.gz.c.b.a.a"
        ),
    ],
)
def test_download_sdist_invalid(url: str) -> None:
    """Unit tests for method."""
    assert utils.download_sdist(url) is None


def test_extract_from_tar_success() -> None:
    """Unit tests for method."""
    expected = {
        "tool": {
            "black": {
                "line-length": 88,
            }
        },
        "build-system": {
            "requires": ["hatchling>=1.8.0", "hatch-vcs", "hatch-fancy-pypi-readme"],
            "build-backend": "hatchling.build",
        },
        "project": {
            "name": "test",
            "description": "description ...",
            "license": {"text": "MIT"},
            "requires-python": ">=3.8",
            "dependencies": [
                "packaging>=22.0",
            ],
        },
    }
    toml_path = "test_archive/pyproject.toml"
    p = pathlib.Path("tests/test_data/test_archive.tar.gz")
    with p.open("rb") as file:
        file_content = file.read()
    file_like_obj = io.BytesIO(file_content)
    assert utils.extract_from_tar(file_like_obj, toml_path) == expected


def test_extract_from_tar_invalid() -> None:
    """Unit tests for method."""
    toml_path = "test_archive123/pyproject.toml"
    p = pathlib.Path("tests/test_data/test_archive.tar.gz")
    with p.open("rb") as file:
        file_content = file.read()
    file_like_obj = io.BytesIO(file_content)
    assert utils.extract_from_tar(file_like_obj, toml_path) is None
