from __future__ import annotations

import os
import pathlib

from py2spack import spack_utils


def test_get_spack_repo1():
    repo = pathlib.Path.cwd() / "tests" / "sample_data" / "sample_repo"

    assert spack_utils.get_spack_repo(str(repo)) == repo


def test_get_spack_repo2():
    if "SPACK_ROOT" in os.environ:
        spack_dir = pathlib.Path(os.environ["SPACK_ROOT"])
        builtin_repo = spack_dir / "var" / "spack" / "repos" / "builtin"
        if builtin_repo.is_dir():
            assert spack_utils.get_spack_repo("builtin") == builtin_repo


def test_package_exists_in_spack():
    assert spack_utils.package_exists_in_spack("py-hatchling")
    assert spack_utils.package_exists_in_spack("automake")

    assert not spack_utils.package_exists_in_spack("not-a-package")


def test_is_spack_repo1():
    if "SPACK_ROOT" in os.environ:
        spack_dir = pathlib.Path(os.environ["SPACK_ROOT"])
        builtin_repo = spack_dir / "var" / "spack" / "repos" / "builtin"
        if builtin_repo.is_dir():
            assert spack_utils.is_spack_repo(builtin_repo)


def test_is_spack_repo2():
    repo = pathlib.Path.cwd() / "tests" / "sample_data" / "sample_repo"
    assert spack_utils.is_spack_repo(repo)


def test_is_spack_repo3():
    repo = pathlib.Path.cwd() / "tests" / "sample_data" / "invalid"
    assert not spack_utils.is_spack_repo(repo)


def test_is_spack_repo4():
    repo = pathlib.Path.cwd() / "tests" / "sample_data"
    assert not spack_utils.is_spack_repo(repo)


def test_run_spack_command():
    result = spack_utils.run_spack_command("spack -h")
    assert "usage: spack" in result
