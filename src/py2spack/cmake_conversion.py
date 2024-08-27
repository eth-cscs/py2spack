"""Module for extracting relevant build information from cmake based projects."""

from __future__ import annotations

import dataclasses

from cmake_parser import ast, lexer, parser
from spack import spec
from spack.util import naming


@dataclasses.dataclass(frozen=True)
class CMakeParseError:
    """."""

    msg: str


@dataclasses.dataclass
class CMakeVersion:
    """Represents versions specified in cmake."""

    major: int
    minor: int
    patch: int | None
    tweak: int | None

    def format(self) -> str:
        """Format CMakeVersion as a standard .-separated version string."""
        components = [self.major, self.minor]
        if self.patch is not None:
            components.append(self.patch)
        if self.tweak is not None:
            components.append(self.tweak)

        return ".".join([str(x) for x in components])


def _parse_single_version(version_string: str) -> CMakeVersion | None:
    components_str = version_string.split(".")
    if len(components_str) > 4:
        return None
    try:
        components: list[int | None] = [int(x) for x in components_str]
        # add None for the missing components
        components += [None for _ in range(4 - len(components))]
        # first two components need to be present
        result = (
            CMakeVersion(*components)  # type: ignore [arg-type]
            if not (components[0] is None or components[1] is None)
            else None
        )

    except ValueError:
        result = None

    return result


def _parse_cmake_version(
    version_string: str,
) -> CMakeVersion | tuple[CMakeVersion, CMakeVersion] | None:
    version_range = version_string.split("...")
    result: CMakeVersion | tuple[CMakeVersion, CMakeVersion] | None = None
    if len(version_range) == 1:
        result = _parse_single_version(version_range[0])
    elif len(version_range) == 2:
        v1 = _parse_single_version(version_range[0])
        v2 = _parse_single_version(version_range[1])

        result = None if v1 is None or v2 is None else (v1, v2)

    return result


def _convert_cmake_minimum_required(
    command: ast.Command,
) -> spec.Spec | CMakeParseError:
    """Convert a cmake 'cmake_minimum_required' command to a packaging Requirement."""
    # TODO: check command isinstance of cmake_minimum_required ??
    assert len(command.args) >= 2
    version_token = command.args[1]
    assert isinstance(version_token, lexer.Token)
    assert version_token.kind == "RAW"
    cmake_version = _parse_cmake_version(version_token.value)
    result: CMakeParseError | spec.Spec

    if cmake_version is None:
        result = CMakeParseError(
            f"Unable to convert 'cmake_minimum_required(\"{version_token.value}\")'"
        )
        # TODO: add cmake dependency outside
    elif isinstance(cmake_version, CMakeVersion):
        result = spec.Spec(f"cmake @{cmake_version.format()}:")
    else:
        result = spec.Spec(f"cmake @{cmake_version[0].format()}:{cmake_version[1].format()}")

    return result


def _convert_find_package(command: ast.Command) -> spec.Spec | CMakeParseError:
    """Convert a cmake 'find_package' command to a Spack spec."""
    # TODO: check command isinstance of find_package ??
    # TODO: verification/error handling
    package = command.args[0].value
    package_spack = naming.simplify_name(package)

    version = None
    if len(command.args) > 1:
        optional_version_token = command.args[1]
        version = _parse_single_version(optional_version_token.value)

    # TODO: semantics of find_package dependency version, look for EXACT keyword (or whatever its called)

    # TODO: correct semantics, is >= fine/desired?
    spec_string = package_spack if version is None else f"{package_spack} @{version.format()}"

    return spec.Spec(spec_string)


# TODO: extract cmakelists.txt data from source dist archive... extract toml, parse toml, parse backend
# and then if necessary directly extract cmakelists...


def convert_cmake_dependencies(cmakelists_data: str) -> list[spec.Spec]:
    relevant_identifiers = [
        "cmake_minimum_required",
        "find_package",
        "if",
        "else",
        "endif",
        "project",
    ]
    nodes = [
        x
        for x in parser.parse_raw(cmakelists_data, skip_comments=True)
        if x.identifier in relevant_identifiers
    ]

    result = []

    # TODO: canonicalize the name for spack

    for node in nodes:
        converted_node = None
        if node.identifier == "cmake_minimum_required":
            converted_node = _convert_cmake_minimum_required(node)
        elif node.identifier == "find_package":
            converted_node = _convert_find_package(node)

        if isinstance(converted_node, spec.Spec):
            result.append(converted_node)

    return result
