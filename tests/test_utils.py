"""Tests for utils.py module."""

from __future__ import annotations

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
def test_download_bytes(url: str) -> None:
    """Unit tests for method."""
    assert isinstance(utils.download_bytes(url), bytes)


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
def test_download_bytes_invalid(url: str) -> None:
    """Unit tests for method."""
    assert utils.download_bytes(url) is None


def test_extract_file_contents_from_tar_bytes_success() -> None:
    """Unit tests for method."""
    toml_path = "sample_archive/pyproject.toml"
    p = pathlib.Path("tests/sample_data/sample_archive.tar.gz")
    with p.open("rb") as file:
        file_content = file.read()
    assert isinstance(utils.extract_file_content_from_tar_bytes(file_content, toml_path), str)


def test_extract_file_contents_from_tar_bytes_invalid() -> None:
    """Unit tests for method."""
    toml_path = "sample_archive123/pyproject.toml"
    p = pathlib.Path("tests/sample_data/sample_archive.tar.gz")
    with p.open("rb") as file:
        file_content = file.read()
    assert utils.extract_file_content_from_tar_bytes(file_content, toml_path) is None


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        (pathlib.Path("a/b/c/d"), pathlib.Path("a/b/c/d")),
        (pathlib.Path("a/b/./c/d"), pathlib.Path("a/b/c/d")),
        (pathlib.Path("a/b/../c/d"), pathlib.Path("a/c/d")),
        (pathlib.Path("a/b/c/d/../../../e/f"), pathlib.Path("a/e/f")),
        (pathlib.Path("a/b/c/d/../../e/../../f"), pathlib.Path("a/f")),
        (pathlib.Path("a/b/../../../c"), pathlib.Path("../c")),
    ],
)
def test_normalize_path(path: pathlib.Path, expected: pathlib.Path):
    assert utils.normalize_path(path) == expected
