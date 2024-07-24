"""Integration tests for py2spack package."""

from __future__ import annotations

import sys

from py2spack import core, package_providers


def test_e2e_uninterrupted1() -> None:
    """Test end-to-end conversion of black package."""
    provider = package_providers.PyPIProvider()
    spack_pkg = core.SpackPyPkg.convert_pkg("black", provider, last_n_versions=5)

    assert spack_pkg is not None

    spack_pkg.print_package(outfile=sys.stdout)

    assert True


def test_e2e_uninterrupted2() -> None:
    """Test end-to-end conversion of tqdm package."""
    provider = package_providers.PyPIProvider()
    spack_pkg = core.SpackPyPkg.convert_pkg("tqdm", provider, last_n_versions=5)

    assert spack_pkg is not None

    spack_pkg.print_package(outfile=sys.stdout)

    assert True


def test_e2e_uninterrupted3() -> None:
    """Test end-to-end conversion of pandas package."""
    provider = package_providers.PyPIProvider()
    spack_pkg = core.SpackPyPkg.convert_pkg("pandas", provider, last_n_versions=5)

    assert spack_pkg is not None

    spack_pkg.print_package(outfile=sys.stdout)

    assert True

