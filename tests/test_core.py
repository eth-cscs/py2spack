"""Tests for core.py module."""

from __future__ import annotations

import pathlib

import pytest
from spack import spec

from py2spack import core, package_providers


def test_load_pyprojects():
    """Not tested."""


def test_pyproject():
    """Tests for PyProject class are in test_pyproject_class.py."""


def test_spackpypkg():
    """Tests for SpackPyPkg class are in test_spackpypkg_class.py."""


def test_format_types():
    assert core._format_types({"build"}) == '"build"'
    assert core._format_types({"run", "build"}) == '("build", "run")'


def test_people_to_strings():
    parsed_people = [
        (None, None),
        ("name", None),
        (None, "hello@email.com"),
        ("name", "name@email.com"),
    ]
    expected = ["name", "hello@email.com", "name, name@email.com"]

    assert core._people_to_strings(parsed_people) == expected


@pytest.mark.parametrize(
    ("name"),
    [
        ("black"),
        ("tqdm"),
        ("https://github.com/tqdm/tqdm"),
        ("tqdm/tqdm"),
    ],
)
def test_convert_single(name: str):
    pypi_provider = package_providers.PyPIProvider()
    gh_provider = package_providers.GitHubProvider()
    assert isinstance(
        core._convert_single(name, pypi_provider, gh_provider, num_versions=5), core.SpackPyPkg
    )


def write_package_to_repo():
    pass  # TODO


@pytest.mark.parametrize(
    ("dep_list", "expected"),
    [
        ([(spec.Spec(), spec.Spec(), {})], []),
        ([(spec.Spec("pkg@4.2:"), spec.Spec(), {})], []),
        ([(spec.Spec("pkg@4.2:"), spec.Spec("^python@:3.11"), {})], []),
        (
            [
                (spec.Spec("pkg@4.2:"), spec.Spec("platform=linux"), {}),
                (spec.Spec("pkg@:4.3"), spec.Spec("platform=windows"), {}),
            ],
            [],
        ),
        (
            [
                (spec.Spec("pkg@4.2:"), spec.Spec("platform=windows"), {}),
                (spec.Spec("pkg@:4.3"), spec.Spec("platform=windows"), {}),
            ],
            [],
        ),
        (
            [
                (spec.Spec("pkg@:4.2"), spec.Spec("platform=windows"), {}),
                (spec.Spec("pkg@4.3:"), spec.Spec("platform=windows"), {}),
            ],
            [
                core.DependencyConflictError(
                    'depends_on("pkg@:4.2", when="platform=windows") and depends_on("pkg@4.3:", when="platform=windows")'
                )
            ],
        ),
        (
            [
                (spec.Spec("pkg@:4.2"), spec.Spec("^python@:3.9"), {}),
                (spec.Spec("pkg@4.3:"), spec.Spec("^python@3.9:"), {}),
            ],
            [
                core.DependencyConflictError(
                    'depends_on("pkg@:4.2", when="^python@:3.9") and depends_on("pkg@4.3:", when="^python@3.9:")'
                )
            ],
        ),
        (
            [
                (spec.Spec("pkg@:4.2"), spec.Spec("^python@:3.8"), {}),
                (spec.Spec("pkg@4.3:"), spec.Spec("^python@3.9:"), {}),
            ],
            [],
        ),
        (
            [
                (spec.Spec("pkg@:4.2"), spec.Spec("@:2.5 ^python@:3.9"), {}),
                (spec.Spec("pkg@4.3:"), spec.Spec("@2: ^python@3.9:"), {}),
            ],
            [
                core.DependencyConflictError(
                    'depends_on("pkg@:4.2", when="@:2.5 ^python@:3.9") and depends_on("pkg@4.3:", when="@2: ^python@3.9:")'
                )
            ],
        ),
        (
            [
                (spec.Spec("pkg@:4.2"), spec.Spec("@:2.5 ^python@:3.9 platform=windows"), {}),
                (spec.Spec("pkg@4.3:"), spec.Spec("@2: ^python@3.9: platform=linux"), {}),
            ],
            [],
        ),
    ],
)
def test_find_dependency_satisfiability_conflicts(
    dep_list: list[tuple[spec.Spec, spec.Spec, set[str]]],
    expected: list[core.DependencyConflictError],
) -> None:
    """Unit tests for method."""
    assert core._find_dependency_satisfiability_conflicts(dep_list) == expected


@pytest.mark.parametrize(
    ("dep_spec", "when_spec", "expected"),
    [
        (
            spec.Spec("py-typing-extensions@4.0.1:"),
            spec.Spec("@23.9: ^python@:3.10"),
            'depends_on("py-typing-extensions@4.0.1:", when="@23.9:' ' ^python@:3.10")',
        ),
        (
            spec.Spec("py-colorama@0.4.3:"),
            spec.Spec("platform=linux +colorama"),
            'depends_on("py-colorama@0.4.3:", when="platform=linux +colorama")',
        ),
    ],
)
def test_format_dependency(dep_spec: spec.Spec, when_spec: spec.Spec, expected: str) -> None:
    """Unit tests for method."""
    assert core._format_dependency(dep_spec, when_spec) == expected


class MockPackageProvider:
    def get_file_content_from_sdist(self, name, version, file_path):
        if file_path == pathlib.Path() / "CMakeLists.txt":
            return """cmake_minimum_required(VERSION 3.19)
include(CMakeDependentOption)
include(CheckIPOSupported)

# Make CUDA support throw errors if architectures remain unclear
cmake_policy(SET CMP0104 NEW)

file(READ VERSION FULL_VERSION_STRING)
string(STRIP "${FULL_VERSION_STRING}" FULL_VERSION_STRING)
if(NOT ARB_USE_BUNDLED_RANDOM123)
    find_package(Random123 REQUIRED)
    target_include_directories(ext-random123 INTERFACE ${RANDOM123_INCLUDE_DIR})
endif()
add_subdirectory(ext)
install(TARGETS ext-hwloc EXPORT arbor-targets)
find_package(Boost 3.9)
"""
        if file_path == pathlib.Path() / "ext" / "CMakeLists.txt":
            return """project(${SKBUILD_PROJECT_NAME} LANGUAGES CXX)
set(PYBIND11_NEWPYTHON ON)
find_package(pybind11 CONFIG REQUIRED)
add_subdirectory(lib ASDF)
add_subdirectory(../upanddown)

install(TARGETS example LIBRARY DESTINATION .)
"""
        if file_path == pathlib.Path() / "ext" / "lib" / "CMakeLists.txt":
            return """project(${SKBUILD_PROJECT_NAME} LANGUAGES CXX)
set(PYBIND11_NEWPYTHON ON)
find_package(mpi 1.2.3...4.5.6)
find_package(Boost)

install(TARGETS example LIBRARY DESTINATION .)
"""
        if file_path == pathlib.Path() / "upanddown" / "CMakeLists.txt":
            return """project(${SKBUILD_PROJECT_NAME} LANGUAGES CXX)
set(PYBIND11_NEWPYTHON ON)

find_package(success)

install(TARGETS example LIBRARY DESTINATION .)
"""
        return None


def test_load_cmakelists_for_pyproject():
    pyproject = core.PyProject()

    core._load_cmakelists_for_pyproject(pyproject, MockPackageProvider())

    expected = {
        "cmake": [
            (spec.Spec("cmake@3.19:"), (pathlib.Path() / "CMakeLists.txt", 1)),
        ],
        "random123": [
            (spec.Spec("random123"), (pathlib.Path() / "CMakeLists.txt", 11)),
        ],
        "boost": [
            (spec.Spec("boost@3.9"), (pathlib.Path() / "CMakeLists.txt", 16)),
            (spec.Spec("boost"), (pathlib.Path() / "ext" / "lib" / "CMakeLists.txt", 4)),
        ],
        "pybind11": [
            (spec.Spec("pybind11"), (pathlib.Path() / "ext" / "CMakeLists.txt", 3)),
        ],
        "mpi": [
            (
                spec.Spec("mpi@1.2.3:4.5.6"),
                (pathlib.Path() / "ext" / "lib" / "CMakeLists.txt", 3),
            ),
        ],
        "success": [
            (spec.Spec("success"), (pathlib.Path() / "upanddown" / "CMakeLists.txt", 4)),
        ],
    }

    assert len(pyproject.cmake_dependencies_with_sources) == len(expected)

    for k, v in pyproject.cmake_dependencies_with_sources.items():
        assert expected.get(k) == v


def test_write_package_to_repo():
    pkg = core.SpackPyPkg()
    pkg.name = "generated-test-pkg"

    repo = pathlib.Path("tests/test_data/test_repo")

    assert core._write_package_to_repo(pkg, repo)

    package_py = repo / "packages" / "generated-test-pkg" / "package.py"

    assert package_py.is_file()

    with package_py.open() as f:
        data = f.read()
        assert "class GeneratedTestPkg(PythonPackage):" in data

    if package_py.is_file():
        package_py.unlink()
        pkg_dir = repo / "packages" / "generated-test-pkg"
        pkg_dir.rmdir()

        assert not package_py.is_file()
        assert not pkg_dir.is_dir()


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
        package, max_conversions=1, versions_per_package=5, repo=str(repo), allow_duplicate=True
    )

    pkg_dir = repo / "packages" / f"py-{package}"
    file = pkg_dir / "package.py"

    assert file.is_file()

    if file.is_file():
        file.unlink()
        pkg_dir.rmdir()

        assert not file.is_file()
        assert not pkg_dir.is_dir()
