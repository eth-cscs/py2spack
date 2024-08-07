"""Tests for PyProject class."""

from __future__ import annotations

from packaging import requirements, specifiers, version as pv

from py2spack import core


PYPROJECT_DATA = {
    "project": {
        "name": "black",
        "description": "The uncompromising code formatter.",
        "license": {"text": "MIT"},
        "requires-python": ">=3.8",
        "authors": [{"name": "Łukasz Langa", "email": "lukasz@langa.pl"}],
        "keywords": ["automation", "autopep8", "formatter", "gofmt", "pyfmt", "rustfmt", "yapf"],
        "classifiers": [
            "Development Status :: 5 - Production/Stable",
            "License :: OSI Approved :: MIT License",
            "Programming Language :: Python",
        ],
        "dependencies": [
            "click>=8.0.0",
            "mypy_extensions>=0.4.3",
            "packaging>=22.0",
            "pathspec>=0.9.0",
            "platformdirs>=2",
            "tomli>=1.1.0; python_version < '3.11'",
            "typing_extensions>=4.0.1; python_version < '3.11'",
        ],
        "dynamic": ["readme", "version"],
        "optional-dependencies": {
            "colorama": ["colorama>=0.4.3"],
            "uvloop": ["uvloop>=0.15.2"],
            "d": [
                "aiohttp>=3.7.4; sys_platform != 'win32' or implementation_name != 'pypy'",
                "aiohttp>=3.7.4, !=3.9.0; sys_platform == 'win32' and implementation_name == 'pypy'",
            ],
            "jupyter": ["ipython>=7.8.0", "tokenize-rt>=3.2.0"],
        },
        "scripts": {"black": "black:patched_main", "blackd": "blackd:patched_main [d]"},
        "entry-points": {"validate_pyproject.tool_schema": {"black": "black.schema:get_schema"}},
        "urls": {
            "Changelog": "https://github.com/psf/black/blob/main/CHANGES.md",
            "Homepage": "https://github.com/psf/black",
        },
    },
    "build-system": {
        "requires": ["hatchling>=1.20.0", "hatch-vcs", "hatch-fancy-pypi-readme"],
        "build-backend": "hatchling.build",
    },
    "tool": {},
}


def test_pyproject_from_toml():
    name = "black"
    version = pv.Version("24.4.2")

    res = core.PyProject.from_toml(PYPROJECT_DATA, name, version)

    assert res.name == name
    assert res.version == version

    assert res.description == "The uncompromising code formatter."

    assert res.homepage == "https://github.com/psf/black"

    assert res.authors == ["Łukasz Langa, lukasz@langa.pl"]
    assert res.maintainers == []

    assert res.requires_python == specifiers.SpecifierSet(">=3.8")
    assert res.license == "MIT"

    assert res.build_requires == [
        requirements.Requirement("hatchling>=1.20.0"),
        requirements.Requirement("hatch-vcs"),
        requirements.Requirement("hatch-fancy-pypi-readme"),
    ]
    assert res.build_backend == "hatchling.build"

    dependencies = [
        requirements.Requirement("click>=8.0.0"),
        requirements.Requirement("mypy_extensions>=0.4.3"),
        requirements.Requirement("packaging>=22.0"),
        requirements.Requirement("pathspec>=0.9.0"),
        requirements.Requirement("platformdirs>=2"),
        requirements.Requirement("tomli>=1.1.0; python_version < '3.11'"),
        requirements.Requirement("typing_extensions>=4.0.1; python_version < '3.11'"),
    ]
    assert res.dependencies == dependencies

    optional_dependencies = {
        "colorama": [requirements.Requirement("colorama>=0.4.3")],
        "uvloop": [requirements.Requirement("uvloop>=0.15.2")],
        "d": [
            requirements.Requirement(
                "aiohttp>=3.7.4; sys_platform != 'win32' or implementation_name != 'pypy'"
            ),
            requirements.Requirement(
                "aiohttp>=3.7.4, !=3.9.0; sys_platform == 'win32' and implementation_name == 'pypy'"
            ),
        ],
        "jupyter": [
            requirements.Requirement("ipython>=7.8.0"),
            requirements.Requirement("tokenize-rt>=3.2.0"),
        ],
    }
    assert res.optional_dependencies == optional_dependencies
