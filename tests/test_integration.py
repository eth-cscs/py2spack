"""Integration tests for py2spack package."""

from __future__ import annotations

import pathlib

import pytest

from py2spack import core


@pytest.mark.parametrize(
    ("package"),
    [
        "black",
        "tqdm",
        "hatchling",
    ],
)
def test_convert_package_writes_file(package: str) -> None:
    """Test end-to-end conversion of black package."""
    cwd = pathlib.Path.cwd()
    repo = cwd / "tests" / "test_data" / "test_repo"

    core.convert_package(
        package,
        max_conversions=1,
        versions_per_package=5,
        repo=str(repo),
        use_test_prefix=True,
        ignore=["slack-sdk"],
    )

    file = repo / "packages" / f"test-py-{package}" / "package.py"

    assert file.is_file()

    if file.is_file():
        file.unlink()
        pkg_dir = repo / "packages" / f"test-py-{package}"
        pkg_dir.rmdir()

        assert not file.is_file()
        assert not pkg_dir.is_dir()


def test_package_py_content():
    # TODO: how to test whether content is correct?
    pass


def test_spack_install():
    # TODO: test whether spack installs packages correctly
    # TODO: separate file?
    pass
