"""Module for extracting relevant build information from cmake based projects."""

from __future__ import annotations

import dataclasses

from cmake_parser import ast, parser
from spack import spec
from spack.util import naming


CMAKE_VERSION_NUM_COMPONENTS = 4


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
    """Parse a single cmake version string (like '1.2.3.4').

    Args:
        version_string: CMake version, e.g. '1.2.3.4'

    Returns:
        A CMakeVersion instance representing that version.
    """
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
    """Parse a full cmake version specifier string.

    Args:
        version_string: CMake version or version range as a string, e.g. '1.2.3' or
        '1.2.3...4.5'.

    Returns:
        Either a single CMakeVersion, or a tuple of (min_version, max_version), or
        None if the version could not be parsed.
    """
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
    """Convert a cmake 'cmake_minimum_required' command to a packaging Requirement.

    Args:
       command: A cmake_parser.ast.Command with identifier 'cmake_minimum_required'.

    Returns:
        A Spack Spec representing the cmake version constraint.
    """
    assert len(command.args) >= 2  # noqa: PLR2004 [magic value]
    version_token = command.args[1]

    cmake_version = _parse_cmake_version(version_token.value)

    if cmake_version is None:
        result = spec.Spec("cmake")
    elif isinstance(cmake_version, CMakeVersion):
        result = spec.Spec(f"cmake @{cmake_version.format()}:")
    else:
        result = spec.Spec(f"cmake @{cmake_version[0].format()}:{cmake_version[1].format()}")

    return result


def _convert_find_package(command: ast.Command) -> spec.Spec | None:
    """Convert a cmake 'find_package' command to a Spack spec.

    Args:
       command: A cmake_parser.ast.Command with identifier 'find_package'.

    Returns:
        A Spack Spec representing the package depedency, or None.
    """
    assert command.args

    package = command.args[0].value

    # canonicalize the name for spack
    package_spack = naming.simplify_name(package)

    # check if there is a version constraint after the package name
    version = None
    if len(command.args) > 1:
        optional_version_token = command.args[1]
        version = _parse_cmake_version(optional_version_token.value)

    # check for the EXACT keyword argument
    exact_version_modifier = ""
    for arg in command.args:
        if arg.value == "EXACT":
            exact_version_modifier = "="

    version_string = ""
    if isinstance(version, CMakeVersion):
        version_string = f"@{exact_version_modifier}{version.format()}"
    elif isinstance(version, tuple):
        version_string = f"@{version[0].format()}:{version[1].format()}"

    spec_string = package_spack if version is None else f"{package_spack} {version_string}"

    return spec.Spec(spec_string)


def _convert_add_subdirectory(command: ast.Command) -> str | None:
    """Get the specified subdirectory from a cmake 'add_subdirectory' command.

    Args:
       command: A cmake_parser.ast.Command with identifier 'add_subdirectory'.

    Returns:
        The relative subdirectory path as a string, or None.
    """
    assert command.args

    subdirectory: str = command.args[0].value
    if subdirectory:
        return subdirectory

    return None


def convert_cmake_dependencies(
    cmakelists_data: str,
) -> tuple[list[tuple[spec.Spec, int]], list[str]]:
    """Convert the contents of a CMakeLists.txt to Spack Specs.

    Args:
        cmakelists_data: The contents of a CMakeLists.txt file.

    Returns:
        A list of dependencies, as well as a list of subdirectories to search
        for more CMakeLists files. Each dependency consists of the dependency Spec as
        well as the line number of the original statement.
    """
    relevant_identifiers = [
        "cmake_minimum_required",
        "find_package",
        "add_subdirectory",
    ]
    nodes = [
        x
        for x in parser.parse_raw(cmakelists_data, skip_comments=True)
        if x.identifier in relevant_identifiers
    ]

    dependencies = []
    subdirectories = []

    for node in nodes:
        converted_dependency = None
        if node.identifier == "cmake_minimum_required":
            converted_dependency = _convert_cmake_minimum_required(node)
        elif node.identifier == "find_package":
            converted_dependency = _convert_find_package(node)
        elif node.identifier == "add_subdirectory":
            subdirectory = _convert_add_subdirectory(node)
            if isinstance(subdirectory, str):
                subdirectories.append(subdirectory)

        if isinstance(converted_dependency, spec.Spec):
            dependencies.append((converted_dependency, node.line))

    return dependencies, subdirectories
