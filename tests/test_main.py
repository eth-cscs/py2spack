"""Tests for main.py module."""

import pytest
from packaging import requirements
from py2spack import main, loading
from spack import spec


@pytest.mark.parametrize(
    "req, from_extra, expected",
    [
        (
            requirements.Requirement("black>=24.2"),
            None,
            [(spec.Spec("py-black@24.2:"), spec.Spec())],
        ),
        (
            requirements.Requirement("black>=24.2; extra == 'foo'"),
            None,
            [(spec.Spec("py-black@24.2:"), spec.Spec("+foo"))],
        ),
        (
            requirements.Requirement("black[foo]>=24.2"),
            None,
            [(spec.Spec("py-black@24.2: +foo"), spec.Spec())],
        ),
        (
            requirements.Requirement("black>=24.2"),
            "extra",
            [(spec.Spec("py-black@24.2:"), spec.Spec("+extra"))],
        ),
        (
            requirements.Requirement("black>=24.2; python_version >= '3.8'"),
            None,
            [(spec.Spec("py-black@24.2:"), spec.Spec("^python@3.8:"))],
        ),
        (
            requirements.Requirement(
                "black>=24.2; python_version >= '3.8' and sys_platform =="
                " 'linux'"
            ),
            "test",
            [
                (
                    spec.Spec("py-black@24.2:"),
                    spec.Spec("platform=linux +test ^python@3.8:"),
                )
            ],
        ),
        (
            requirements.Requirement(
                "black>=24.2; python_version >= '3.8' or sys_platform =="
                " 'windows'"
            ),
            None,
            [
                (spec.Spec("py-black@24.2:"), spec.Spec("^python@3.8:")),
                (spec.Spec("py-black@24.2:"), spec.Spec("platform=windows")),
            ],
        ),
        (
            requirements.Requirement("black>=24.2; sys_platform != 'darwin'"),
            "extra",
            [
                (
                    spec.Spec("py-black@24.2:"),
                    spec.Spec("platform=linux +extra"),
                ),
                (
                    spec.Spec("py-black@24.2:"),
                    spec.Spec("platform=windows +extra"),
                ),
                (
                    spec.Spec("py-black@24.2:"),
                    spec.Spec("platform=freebsd +extra"),
                ),
                (
                    spec.Spec("py-black@24.2:"),
                    spec.Spec("platform=cray +extra"),
                ),
            ],
        ),
    ],
)
def test_convert_requirement(req, from_extra, expected):
    lookup = loading.PyPILookup()
    result = main._convert_requirement(req, lookup, from_extra=from_extra)
    assert set(result) == set(expected)


def test_convert_requirement_invalid():
    lookup = loading.PyPILookup()
    result = main._convert_requirement(
        requirements.Requirement("black>=4.2,<4"), lookup
    )
    assert isinstance(result, main.ConversionError)


@pytest.mark.parametrize(
    "dep_list, expected",
    [
        ([(spec.Spec(), spec.Spec(), "")], True),
        ([(spec.Spec("pkg@4.2:"), spec.Spec(), "")], True),
        ([(spec.Spec("pkg@4.2:"), spec.Spec("^python@:3.11"), "")], True),
        (
            [
                (spec.Spec("pkg@4.2:"), spec.Spec("platform=linux"), ""),
                (spec.Spec("pkg@:4.3"), spec.Spec("platform=windows"), ""),
            ],
            True,
        ),
        (
            [
                (spec.Spec("pkg@4.2:"), spec.Spec("platform=windows"), ""),
                (spec.Spec("pkg@:4.3"), spec.Spec("platform=windows"), ""),
            ],
            True,
        ),
        (
            [
                (spec.Spec("pkg@:4.2"), spec.Spec("platform=windows"), ""),
                (spec.Spec("pkg@4.3:"), spec.Spec("platform=windows"), ""),
            ],
            False,
        ),
        (
            [
                (spec.Spec("pkg@:4.2"), spec.Spec("^python@:3.9"), ""),
                (spec.Spec("pkg@4.3:"), spec.Spec("^python@3.9:"), ""),
            ],
            False,
        ),
        (
            [
                (spec.Spec("pkg@:4.2"), spec.Spec("^python@:3.8"), ""),
                (spec.Spec("pkg@4.3:"), spec.Spec("^python@3.9:"), ""),
            ],
            True,
        ),
    ],
)
def test_check_dependency_satisfiability(dep_list, expected):
    assert main._check_dependency_satisfiability(dep_list) == expected


@pytest.mark.parametrize(
    "dep_spec, when_spec, expected",
    [
        (
            spec.Spec("py-typing-extensions@4.0.1:"),
            spec.Spec("@23.9: ^python@:3.10"),
            'depends_on("py-typing-extensions@4.0.1:", when="@23.9:'
            ' ^python@:3.10")',
        ),
        (
            spec.Spec("py-colorama@0.4.3:"),
            spec.Spec("platform=linux +colorama"),
            'depends_on("py-colorama@0.4.3:", when="platform=linux +colorama")',
        ),
    ],
)
def test_format_dependency(dep_spec, when_spec, expected):
    assert main._format_dependency(dep_spec, when_spec) == expected


@pytest.mark.parametrize(
    "name, expected",
    [
        ("python", "python"),
        ("package", "py-package"),
        ("special_custom-pkg", "py-special-custom-pkg"),
        ("py-pkg", "py-pkg"),
        ("py-cpuinfo", "py-py-cpuinfo"),
    ],
)
def test_pkg_to_spack_name(name, expected):
    assert main._pkg_to_spack_name(name) == expected


# TODO: functions to test:
# _get_spack_version_hash_list
# _people_to_strings
# SpackPyPkg._get_dependencies
# SpackPyPkg._get_metadata
#
# these last to maybe already integration tests?
# PyProject.from_toml
# SpackPyPkg.convert_pkg
