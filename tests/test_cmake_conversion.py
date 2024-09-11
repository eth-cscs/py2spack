"""Tests for cmake_conversion.py module."""

from __future__ import annotations

import pathlib

import pytest
from cmake_parser import ast, lexer
from spack import spec

from py2spack import cmake_conversion


@pytest.mark.parametrize(
    ("cmakeversion", "expected"),
    [
        (cmake_conversion.CMakeVersion(4, 3, 2, 1), "4.3.2.1"),
        (cmake_conversion.CMakeVersion(4, 3, 2, None), "4.3.2"),
        (cmake_conversion.CMakeVersion(4, 3, None, None), "4.3"),
    ],
)
def test_cmakeversion_format(cmakeversion: cmake_conversion.CMakeVersion, expected: str):
    assert cmakeversion.format() == expected


@pytest.mark.parametrize(
    ("version_string", "expected"),
    [
        ("4.3.2.1", cmake_conversion.CMakeVersion(4, 3, 2, 1)),
        ("4.3.2", cmake_conversion.CMakeVersion(4, 3, 2, None)),
        ("4.3", cmake_conversion.CMakeVersion(4, 3, None, None)),
        ("1", None),
        ("1.2.3.4.5.6", None),
        ("1.2.post2", None),
    ],
)
def test_parse_single_version(version_string: str, expected: cmake_conversion.CMakeVersion | None):
    assert cmake_conversion._parse_single_version(version_string) == expected


@pytest.mark.parametrize(
    ("version_string", "expected"),
    [
        ("4.3.2.1", cmake_conversion.CMakeVersion(4, 3, 2, 1)),
        ("4.3.2", cmake_conversion.CMakeVersion(4, 3, 2, None)),
        ("4.3", cmake_conversion.CMakeVersion(4, 3, None, None)),
        ("1", None),
        ("1.2.3.4.5.6", None),
        ("1.2.post2", None),
        (
            "4.3...5.1",
            (
                cmake_conversion.CMakeVersion(4, 3, None, None),
                cmake_conversion.CMakeVersion(5, 1, None, None),
            ),
        ),
        (
            "1.2.3.4...1.2.4",
            (
                cmake_conversion.CMakeVersion(1, 2, 3, 4),
                cmake_conversion.CMakeVersion(1, 2, 4, None),
            ),
        ),
        (
            "1.2.3.4..1.2.4",
            None,
        ),
        (
            "1.2.3....1.2.4",
            None,
        ),
        (
            "1.2.3.4...1.2.pre4",
            None,
        ),
        (
            "1.2.3.4...2.0",
            (
                cmake_conversion.CMakeVersion(1, 2, 3, 4),
                cmake_conversion.CMakeVersion(2, 0, None, None),
            ),
        ),
        (
            "1.2.3.4...2",
            None,
        ),
    ],
)
def test_parse_cmake_version(
    version_string: str,
    expected: tuple[cmake_conversion.CMakeVersion, cmake_conversion.CMakeVersion]
    | cmake_conversion.CMakeVersion
    | None,
):
    assert cmake_conversion._parse_cmake_version(version_string) == expected


@pytest.mark.parametrize(
    ("cmake_minimum_required", "expected"),
    [
        (
            ast.Command(
                line=1,
                column=1,
                span=slice(0, 43, None),
                identifier="cmake_minimum_required",
                args=[
                    lexer.Token(
                        kind="RAW", value="VERSION", span=slice(23, 30, None), line=1, column=24
                    ),
                    lexer.Token(
                        kind="RAW", value="3.15...3.26", span=slice(31, 42, None), line=1, column=32
                    ),
                ],
            ),
            spec.Spec("cmake@3.15:3.26"),
        ),
        (
            ast.Command(
                line=1,
                column=1,
                span=slice(0, 43, None),
                identifier="cmake_minimum_required",
                args=[
                    lexer.Token(
                        kind="RAW", value="VERSION", span=slice(23, 30, None), line=1, column=24
                    ),
                    lexer.Token(
                        kind="RAW", value="3.15", span=slice(31, 42, None), line=1, column=32
                    ),
                ],
            ),
            spec.Spec("cmake@3.15:"),
        ),
        (
            ast.Command(
                line=1,
                column=1,
                span=slice(0, 43, None),
                identifier="cmake_minimum_required",
                args=[
                    lexer.Token(
                        kind="RAW", value="VERSION", span=slice(23, 30, None), line=1, column=24
                    ),
                    lexer.Token(
                        kind="RAW",
                        value="somethingelse",
                        span=slice(31, 42, None),
                        line=1,
                        column=32,
                    ),
                ],
            ),
            spec.Spec("cmake"),
        ),
    ],
)
def test_convert_cmake_minimum_required(cmake_minimum_required: ast.Command, expected: spec.Spec):
    assert cmake_conversion._convert_cmake_minimum_required(cmake_minimum_required) == expected


@pytest.mark.parametrize(
    ("find_package", "expected"),
    [
        (
            ast.Command(
                line=146,
                column=5,
                span=slice(5292, 5317, None),
                identifier="find_package",
                args=[
                    lexer.Token(
                        kind="RAW",
                        value="CUDAToolkit",
                        span=slice(5305, 5316, None),
                        line=146,
                        column=18,
                    )
                ],
            ),
            spec.Spec("cudatoolkit"),
        ),
        (
            ast.Command(
                line=424,
                column=5,
                span=slice(16246, 16276, None),
                identifier="find_package",
                args=[
                    lexer.Token(
                        kind="RAW", value="MPI", span=slice(16259, 16262, None), line=424, column=18
                    ),
                    lexer.Token(
                        kind="RAW",
                        value="1.2.3",
                        span=slice(16263, 16271, None),
                        line=424,
                        column=22,
                    ),
                    lexer.Token(
                        kind="RAW",
                        value="REQUIRED",
                        span=slice(16263, 16271, None),
                        line=424,
                        column=22,
                    ),
                    lexer.Token(
                        kind="RAW",
                        value="EXACT",
                        span=slice(16272, 16275, None),
                        line=424,
                        column=31,
                    ),
                ],
            ),
            spec.Spec("mpi@=1.2.3"),
        ),
        (
            ast.Command(
                line=424,
                column=5,
                span=slice(16246, 16276, None),
                identifier="find_package",
                args=[
                    lexer.Token(
                        kind="RAW", value="MPI", span=slice(16259, 16262, None), line=424, column=18
                    ),
                    lexer.Token(
                        kind="RAW",
                        value="1.2.3...2.4",
                        span=slice(16263, 16271, None),
                        line=424,
                        column=22,
                    ),
                    lexer.Token(
                        kind="RAW",
                        value="REQUIRED",
                        span=slice(16263, 16271, None),
                        line=424,
                        column=22,
                    ),
                ],
            ),
            spec.Spec("mpi@1.2.3:2.4"),
        ),
    ],
)
def test_convert_find_package(find_package: ast.Command, expected: spec.Spec | None):
    assert cmake_conversion._convert_find_package(find_package) == expected


@pytest.mark.parametrize(
    ("add_subdirectory", "expected"),
    [
        (
            ast.Command(
                line=307,
                column=1,
                span=slice(11812, 11833, None),
                identifier="add_subdirectory",
                args=[
                    lexer.Token(
                        kind="RAW", value="ext", span=slice(11829, 11832, None), line=307, column=18
                    )
                ],
            ),
            "ext",
        ),
        (
            ast.Command(
                line=307,
                column=1,
                span=slice(11812, 11833, None),
                identifier="add_subdirectory",
                args=[
                    lexer.Token(
                        kind="RAW",
                        value="../somedir",
                        span=slice(11829, 11832, None),
                        line=307,
                        column=18,
                    )
                ],
            ),
            "../somedir",
        ),
        (
            ast.Command(
                line=307,
                column=1,
                span=slice(11812, 11833, None),
                identifier="add_subdirectory",
                args=[
                    lexer.Token(
                        kind="RAW",
                        value="",
                        span=slice(11829, 11832, None),
                        line=307,
                        column=18,
                    )
                ],
            ),
            None,
        ),
    ],
)
def test_convert_add_subdirectory(add_subdirectory: ast.Command, expected: str | None):
    assert cmake_conversion._convert_add_subdirectory(add_subdirectory) == expected


def test_convert_cmake_dependencies():
    with pathlib.Path("tests/test_data/CMakeLists.txt").open() as f:
        data = f.read()

    expected_subdirectories = {
        "ext",
        "arbor/include",
        "sup",
        "modcc",
        "arbor",
        "arborenv",
        "arborio",
        "test",
        "example",
        "doc",
        "python",
        "lmorpho",
    }

    expected_dependencies = {
        (spec.Spec("cmake@3.19:"), 1),
        (spec.Spec("cudatoolkit"), 146),
        (spec.Spec("cuda"), 160),
        (spec.Spec("nlohmann-json@3.11.2"), 271),
        (spec.Spec("random123"), 278),
        (spec.Spec("hwloc"), 283),
        (spec.Spec("python3"), 396),
        (spec.Spec("python3"), 398),
        (spec.Spec("python3"), 404),
        (spec.Spec("threads"), 415),
        (spec.Spec("mpi"), 424),
        (spec.Spec("boost"), 481),
    }

    dependencies, subdirectories = cmake_conversion.convert_cmake_dependencies(data)

    assert set(subdirectories) == expected_subdirectories
    assert set(dependencies) == expected_dependencies
