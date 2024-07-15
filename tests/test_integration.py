"""Integration tests for py2spack package."""

import sys

from py2spack import conversion_tools, main


def test_e2e_uninterrupted():
    pyprojects = []
    name = "black"
    for v in ["23.12.0", "23.12.1", "24.2.0", "24.4.0", "24.4.1", "24.4.2"]:
        py_pkg = main.PyProject.from_toml(
            f"tests/test_data/black/pyproject{v}.toml", name, v
        )

        assert py_pkg is not None

        pyprojects.append(py_pkg)

    lookup = conversion_tools.JsonVersionsLookup()
    spack_pkg = main.SpackPyPkg.from_pyprojects(pyprojects, lookup)

    assert spack_pkg is not None

    spack_pkg.print_package(outfile=sys.stdout)

    assert True