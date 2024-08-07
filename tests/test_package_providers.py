"""Tests for package_providers.py module."""

from __future__ import annotations

import pytest
from packaging import version as pv

from py2spack import package_providers


@pytest.mark.parametrize(
    ("version_str", "expected"),
    [
        ("4.3.2.5.4", pv.Version("4.3.2.5.4")),
        ("2..4", None),
        ("2", pv.Version("2")),
        ("4.dev2", pv.Version("4.dev2")),
        ("3.pre.dev2", None),
    ],
)
def test_acceptable_version(version_str: str, expected: pv.Version | None) -> None:
    """Unit tests for method."""
    assert package_providers._parse_packaging_version(version_str) == expected


@pytest.mark.parametrize(
    ("filename", "expected"),
    [
        ("black-24.4.2.tar.gz", ".tar.gz"),
        ("package-1.gz", ".gz"),
        ("python-3.4.5-alpha6.tar.bz2", ".tar.bz2"),
    ],
)
def test_parse_archive_extension(filename: str, expected: str) -> None:
    """Unit tests for method."""
    assert package_providers._parse_archive_extension(filename) == expected


@pytest.mark.parametrize(
    "filename",
    [
        ("pkg-0.0.1.txt"),
        ("pkg-0.0.1.whl"),
    ],
)
def test_parse_archive_extension_invalid(filename: str) -> None:
    """Unit tests for method."""
    assert isinstance(
        package_providers._parse_archive_extension(filename),
        package_providers.PyProjectProviderQueryError,
    )


@pytest.mark.parametrize(
    ("dirname", "pkg_name", "expected"),
    [
        ("black-24.4.2", "black", pv.Version("24.4.2")),
        ("package-1", "package", pv.Version("1")),
        (
            "python-3.4.5-alpha6",
            "python",
            pv.Version("3.4.5-alpha6"),
        ),
        ("black-2..4.2.ok", "black", None),
        ("black-24.4??.2", "black", None),
        ("green-24.4.2", "black", None),
        ("black-otherpackage-24.4.2", "black", None),
    ],
)
def test_parse_version_from_filename(
    dirname: str, pkg_name: str, expected: pv.Version | None
) -> None:
    """Unit tests for method."""
    assert package_providers._parse_version_from_directory_name(dirname, pkg_name) == expected


tmptst = """
def test_pypilookup_get_files():
                {
                    "filename": filename,
                    "url": f["url"],
                    "version": v,
                    "extension": archive_ext,
                    "hash": sha256,
                }
    expected_files = [
        {
            pv.Version("24.3.0"),
            "a0c9c4a0771afc6919578cec71ce82a3e31e054904e7197deacbc9382671c41f",
        },
        {
            pv.Version("24.2.0"),
            "bce4f25c27c3435e4dace4815bcb2008b87e167e3bf4ee47ccdc5ce906eb4894",
        },
        {
            pv.Version("24.1.1"),
            "48b5760dcbfe5cf97fd4fba23946681f3a81514c6ab8a45b50da67ac8fbc6c7b",
        },
        {
            pv.Version("24.1.0"),
            "30fbf768cd4f4576598b1db0202413fafea9a227ef808d1a12230c643cefe9fc",
        },
        {
            pv.Version("23.12.1"),
            "4ce3ef14ebe8d9509188014d96af1c456a910d5b5cbf434a09fef7e024b3d0d5",
        },
        {
            pv.Version("23.12.0"),
            "330a327b422aca0634ecd115985c1c7fd7bdb5b5a2ef8aa9888a82e2ebe9437a",
        },
        {
            pv.Version("23.11.0"),
            "4c68855825ff432d197229846f971bc4d6666ce90492e5b02013bcaca4d9ab05",
        },
        {
            pv.Version("22.12.0"),
            "229351e5a18ca30f447bf724d007f890f97e13af070bb6ad4c0a441cd7596a2f",
        },
        {
            pv.Version("22.10.0"),
            "f513588da599943e0cde4e32cc9879e825d58720d6557062d1098c5ad80080e1",
        },
        {
            pv.Version("22.8.0"),
            "792f7eb540ba9a17e8656538701d3eb1afcb134e3b45b71f20b25c77a8db7e6e",
        },
        {
            pv.Version("22.6.0"),
            "6c6d39e28aed379aec40da1c65434c77d75e65bb59a1e1c283de545fb4e7c6c9",
        },
        {
            pv.Version("22.3.0"),
            "35020b8886c022ced9282b51b5a875b6d1ab0c387b31a065b84db7c33085ca79",
        },
        {
            pv.Version("22.1.0"),
            "a7c0192d35635f6fc1174be575cb7915e92e5dd629ee79fdaf0dcfa41a80afb5",
        },
    ]
    versions = [pv.Version(v) for v, _ in version_hashes]

    expected_version_hashes = [(sv.Version(v), h) for v, h in version_hashes]
    expected_pypi = "black/black-24.3.0.tar.gz"

    result_pypi, result_version_hashes = main._get_pypi_filenames_hashes(
        "black", versions
    )

    assert result_pypi == expected_pypi
    assert set(result_version_hashes) == set(expected_version_hashes)
"""

# TODO @davhofer:
# _acceptable_version -> same as in conversion tools
# PyPILookup functions: _get, get_versions, get_files
# _extract_from_tar
# try_load_toml
