"""Module for extracting relevant build information from cmake based projects."""

from __future__ import annotations

import dataclasses

from cmake_parser import ast, lexer, parser
from spack import spec
from spack.util import naming


CMAKE_VERSION_NUM_COMPONENTS = 4


@dataclasses.dataclass(frozen=True)
class CMakeParseError:
    """Error while parsing and handling data from CMakeLists.txt."""

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
    if len(components_str) > CMAKE_VERSION_NUM_COMPONENTS:
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
    # version string should be of the form "v" or "v1...v2"
    version_range = version_string.split("...")
    result: CMakeVersion | tuple[CMakeVersion, CMakeVersion] | None = None
    if len(version_range) == 1:
        result = _parse_single_version(version_range[0])
    elif len(version_range) == 2:  # noqa: PLR2004 [magic value]
        v1 = _parse_single_version(version_range[0])
        v2 = _parse_single_version(version_range[1])

        result = None if v1 is None or v2 is None else (v1, v2)

    return result


def _convert_cmake_minimum_required(
    command: ast.Command,
) -> spec.Spec:
    """Convert a cmake 'cmake_minimum_required' command to a packaging Requirement."""
    assert len(command.args) >= 2  # noqa: PLR2004 [magic value]
    version_token = command.args[1]

    assert isinstance(version_token, lexer.Token)
    assert version_token.kind == "RAW"
    cmake_version = _parse_cmake_version(version_token.value)

    if cmake_version is None:
        result = spec.Spec("cmake")
    elif isinstance(cmake_version, CMakeVersion):
        result = spec.Spec(f"cmake @{cmake_version.format()}:")
    else:
        result = spec.Spec(f"cmake @{cmake_version[0].format()}:{cmake_version[1].format()}")

    return result


def _convert_find_package(command: ast.Command) -> spec.Spec | CMakeParseError:
    """Convert a cmake 'find_package' command to a Spack spec."""
    # TODO @davhofer: verification/error handling?
    package = command.args[0].value
    # canonicalize the name for spack
    package_spack = naming.simplify_name(package)

    version = None
    if len(command.args) > 1:
        optional_version_token = command.args[1]
        version = _parse_single_version(optional_version_token.value)

    exact_version_modifier = ""
    for arg in command.args:
        if arg.value == "EXACT":
            exact_version_modifier = "="

    spec_string = (
        package_spack
        if version is None
        else f"{package_spack} @{exact_version_modifier}{version.format()}"
    )

    return spec.Spec(spec_string)


def convert_cmake_dependencies(cmakelists_data: str) -> list[spec.Spec]:
    """Convert the contenets of a CMakeLists.txt to Spack Specs."""
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

    for node in nodes:
        converted_node = None
        if node.identifier == "cmake_minimum_required":
            converted_node = _convert_cmake_minimum_required(node)
        elif node.identifier == "find_package":
            converted_node = _convert_find_package(node)

        if isinstance(converted_node, spec.Spec):
            result.append(converted_node)

    return result
