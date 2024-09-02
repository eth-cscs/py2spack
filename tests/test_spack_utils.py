from __future__ import annotations

import os
import pathlib

from py2spack import spack_utils


def test_get_spack_repo1():
    repo = pathlib.Path.cwd() / "tests" / "test_data" / "test_repo"

    assert spack_utils.get_spack_repo(str(repo)) == repo


def test_get_spack_repo2():
    if "SPACK_ROOT" in os.environ:
        spack_dir = pathlib.Path(os.environ["SPACK_ROOT"])
        builtin_repo = spack_dir / "var" / "spack" / "repos" / "builtin"
        if builtin_repo.is_dir():
            assert spack_utils.get_spack_repo(None) == builtin_repo


def test_package_exists_in_spack():
    assert spack_utils.package_exists_in_spack("py-black")
    assert spack_utils.package_exists_in_spack("gcc")

    assert not spack_utils.package_exists_in_spack("not-a-package")
