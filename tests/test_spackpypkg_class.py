"""Tests for SpackPyPackage class."""

from __future__ import annotations

import pathlib

from packaging import requirements, version as pv
from spack import spec

from py2spack import core, package_providers


def test_spackpypkg_metadata_from_pyproject():
    """Not tested.

    Trivial method, no need to test.
    """


def test_spackpypkg_dependencies_from_pyprojects():
    """Not tested.

    Method mostly just calls _requirement_from_pyproject and _combine_dependencies,
    covered by testing these two.
    """


def test_spackpypkg_print_pkg():
    """Not tested."""


def test_spackpypkg_build_from_pyprojects():
    """Not tested."""


class MockPackageProvider:
    """Mock PackageProvider class."""

    def get_versions(
        self, name: str
    ) -> list[pv.Version] | package_providers.PackageProviderQueryError:
        """."""
        if name == "example1":
            versions = ["1.1", "1.2", "1.3", "2.0", "2.1", "2.1.1", "2.1.2", "2.2"]
            return [pv.Version(v) for v in versions]

        if name == "example2":
            versions = ["1.1", "1.2", "1.9", "2.0"]
            return [pv.Version(v) for v in versions]

        if name == "example3":
            versions = [
                "3.1.5",
                "3.1.6",
                "3.4.2",
                "3.5",
                "4.2",
                "4.3",
                "4.4.0",
                "4.4.1",
                "4.6",
                "5.0",
            ]
            return [pv.Version(v) for v in versions]

        return package_providers.PackageProviderQueryError(f"No versions found for package {name}")


def test_spackpypkg_requirement_from_pyproject1():
    spackpkg = core.SpackPyPkg()
    spackpkg._requirement_from_pyproject(
        requirements.Requirement("example1>=2.1; python_version < '3.10'"),
        ["build", "run"],
        pv.Version("1.2"),
        MockPackageProvider(),
        from_extra="old",
    )

    assert "example1" in spackpkg.original_dependencies
    dep_spec = spec.Spec("py-example1@2.1:")
    when_spec = spec.Spec("+old ^python@:3.9")
    pkg_version = pv.Version("1.2")

    assert spackpkg._specs_to_versions.get((dep_spec, when_spec)) == [pkg_version]
    assert spackpkg._specs_to_types.get((dep_spec, when_spec)) == {"build", "run"}


def test_spackpypkg_requirement_from_pyproject2():
    spackpkg = core.SpackPyPkg()
    spackpkg._requirement_from_pyproject(
        requirements.Requirement("example2>1,<2"),
        ["build"],
        pv.Version("1.2"),
        MockPackageProvider(),
    )

    assert "example2" in spackpkg.original_dependencies
    dep_spec = spec.Spec("py-example2@:1")
    when_spec = spec.Spec()
    pkg_version = pv.Version("1.2")

    assert spackpkg._specs_to_versions.get((dep_spec, when_spec)) == [pkg_version]
    assert spackpkg._specs_to_types.get((dep_spec, when_spec)) == {"build"}


def test_spackpypkg_requirement_from_pyproject3():
    spackpkg = core.SpackPyPkg()
    spackpkg._requirement_from_pyproject(
        requirements.Requirement("example3<4; sys_platform != 'windows'"),
        ["build"],
        pv.Version("1.2"),
        MockPackageProvider(),
    )

    assert "example3" in spackpkg.original_dependencies
    for platform in ["linux", "cray", "darwin", "freebsd"]:
        dep_spec = spec.Spec("py-example3@:3")
        when_spec = spec.Spec(f"platform={platform}")
        pkg_version = pv.Version("1.2")

        assert spackpkg._specs_to_versions.get((dep_spec, when_spec)) == [pkg_version]
        assert spackpkg._specs_to_types.get((dep_spec, when_spec)) == {"build"}


def test_spackpypkg_combine_dependencies():
    spackpkg = core.SpackPyPkg()
    spackpkg.all_versions = [pv.Version(str(i)) for i in range(1, 11)]
    dep = (spec.Spec("py-example1@2.0:"), spec.Spec("platform=unix"))
    spackpkg._specs_to_versions = {
        dep: [pv.Version(str(i)) for i in [1, 2, 3, 7, 8]],
    }
    spackpkg._specs_to_types[dep] = {"build"}

    spackpkg._combine_dependencies()

    assert not spackpkg.dependency_conflict_errors

    assert spackpkg._dependencies_by_type.get('"build"') == [
        (
            spec.Spec("py-example1@2.0:"),
            spec.Spec("@:3,7:8 platform=unix"),
        )
    ]


def test_spackpypkg_cmake_dependencies_from_pyproject():
    pyproject = core.PyProject()
    pyproject.cmake_dependencies_with_sources["dep1"] = [
        (spec.Spec("dep1"), (pathlib.Path("path/to/file"), 10)),
        (spec.Spec("dep1@3.4:"), (pathlib.Path("path/to/file"), 15)),
    ]

    pyproject.cmake_dependencies_with_sources["dep2"] = [
        (spec.Spec("dep2"), (pathlib.Path("path/to/file"), 2)),
        (spec.Spec("dep2@1:2"), (pathlib.Path("path/to/other_file"), 10)),
    ]

    spackpkg = core.SpackPyPkg()

    spackpkg._cmake_dependencies_from_pyproject(pyproject)

    assert spackpkg.cmake_dependency_names == {"dep1", "dep2"}

    assert list(spackpkg._cmake_dependencies_with_sources.items()) == [
        (
            "dep1",
            [
                (spec.Spec("dep1"), (pathlib.Path("path/to/file"), 10)),
                (spec.Spec("dep1@3.4:"), (pathlib.Path("path/to/file"), 15)),
            ],
        ),
        (
            "dep2",
            [
                (spec.Spec("dep2"), (pathlib.Path("path/to/file"), 2)),
                (spec.Spec("dep2@1:2"), (pathlib.Path("path/to/other_file"), 10)),
            ],
        ),
    ]
