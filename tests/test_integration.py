"""Integration tests for py2spack package."""

from __future__ import annotations

import pathlib

import pytest
from spack import spec

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
