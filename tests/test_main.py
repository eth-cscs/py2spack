"""Tests for main.py module."""

import pytest
from py2spack import main

from packaging import requirements
from packaging import version as pv
from spack import spec
from spack import version as sv


# TODO:
# def test_jsonversionslookup():
#     """."""
#     lookup = JsonVersionsLookup()


@pytest.mark.parametrize(
    "filename, expected",
    [
        ("black-24.4.2.tar.gz", ".tar.gz"),
        ("package-1.gz", ".gz"),
        ("python-3.4.5-alpha6.tar.bz2", ".tar.bz2"),
        ("pkg-0.0.1.txt", None),
        ("pkg-0.0.1.whl", None),
    ],
)
def test_get_archive_extension(filename, expected):
    """."""
    assert main._get_archive_extension(filename) == expected


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
                "black>=24.2; python_version >= '3.8' and sys_platform == 'linux'"
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
                "black>=24.2; python_version >= '3.8' or sys_platform == 'windows'"
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
                (spec.Spec("py-black@24.2:"), spec.Spec("platform=linux +extra")),
                (spec.Spec("py-black@24.2:"), spec.Spec("platform=windows +extra")),
                (spec.Spec("py-black@24.2:"), spec.Spec("platform=freebsd +extra")),
                (spec.Spec("py-black@24.2:"), spec.Spec("platform=cray +extra")),
            ],
        ),
    ],
)
def test_convert_requirement(req, from_extra, expected):
    """."""
    result = main._convert_requirement(req, from_extra=from_extra)
    assert set(result) == set(expected)


def test_get_pypi_filenames_hashes():
    """."""
    version_hashes = [
        ("24.3.0", "a0c9c4a0771afc6919578cec71ce82a3e31e054904e7197deacbc9382671c41f"),
        ("24.2.0", "bce4f25c27c3435e4dace4815bcb2008b87e167e3bf4ee47ccdc5ce906eb4894"),
        ("24.1.1", "48b5760dcbfe5cf97fd4fba23946681f3a81514c6ab8a45b50da67ac8fbc6c7b"),
        ("24.1.0", "30fbf768cd4f4576598b1db0202413fafea9a227ef808d1a12230c643cefe9fc"),
        ("23.12.1", "4ce3ef14ebe8d9509188014d96af1c456a910d5b5cbf434a09fef7e024b3d0d5"),
        ("23.12.0", "330a327b422aca0634ecd115985c1c7fd7bdb5b5a2ef8aa9888a82e2ebe9437a"),
        ("23.11.0", "4c68855825ff432d197229846f971bc4d6666ce90492e5b02013bcaca4d9ab05"),
        ("22.12.0", "229351e5a18ca30f447bf724d007f890f97e13af070bb6ad4c0a441cd7596a2f"),
        ("22.10.0", "f513588da599943e0cde4e32cc9879e825d58720d6557062d1098c5ad80080e1"),
        ("22.8.0", "792f7eb540ba9a17e8656538701d3eb1afcb134e3b45b71f20b25c77a8db7e6e"),
        ("22.6.0", "6c6d39e28aed379aec40da1c65434c77d75e65bb59a1e1c283de545fb4e7c6c9"),
        ("22.3.0", "35020b8886c022ced9282b51b5a875b6d1ab0c387b31a065b84db7c33085ca79"),
        ("22.1.0", "a7c0192d35635f6fc1174be575cb7915e92e5dd629ee79fdaf0dcfa41a80afb5"),
    ]
    versions = [pv.Version(v) for v, _ in version_hashes]

    expected_version_hashes = [(sv.Version(v), h) for v, h in version_hashes]
    expected_pypi = "black/black-24.3.0.tar.gz"

    result_pypi, result_version_hashes = main._get_pypi_filenames_hashes(
        "black", versions
    )

    assert result_pypi == expected_pypi
    assert set(result_version_hashes) == set(expected_version_hashes)


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
    """."""
    assert main._check_dependency_satisfiability(dep_list) == expected


@pytest.mark.parametrize(
    "dep_spec, when_spec, expected",
    [
        (
            spec.Spec("py-typing-extensions@4.0.1:"),
            spec.Spec("@23.9: ^python@:3.10"),
            'depends_on("py-typing-extensions@4.0.1:", when="@23.9: ^python@:3.10")',
        ),
        (
            spec.Spec("py-colorama@0.4.3:"),
            spec.Spec("platform=linux +colorama"),
            'depends_on("py-colorama@0.4.3:", when="platform=linux +colorama")',
        ),
    ],
)
def test_format_dependency(dep_spec, when_spec, expected):
    """."""
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
    """."""
    assert main._pkg_to_spack_name(name) == expected


#  To test:
"""
main.PyProject.from_toml
main.SpackPyPkg._get_metadata
main.SpackPyPkg.from_pyprojects
"""
