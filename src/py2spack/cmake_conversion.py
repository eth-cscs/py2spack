"""Module for extracting relevant build information from cmake based projects."""

from __future__ import annotations

import dataclasses

from cmake_parser import ast, lexer, parser
from spack import spec
from spack.util import naming


r"""
interesting symbols:
- cmake_minimum_required
    cmake_minimum_required(VERSION <min>[...<policy_max>] [FATAL_ERROR])
    <min> and the optional <policy_max> are each CMake versions of the form
    major.minor[.patch[.tweak]], and the ... is literal.

    int.int.int.other

    regex: [0-9]+\.[0-9]+(\.[0-9]+)?

- find_package
    find_package(<package_name> [<version>] [REQUIRED] [COMPONENTS <components>...])
    just look for package name and version
    find_package(<PackageName> [version] [EXACT] [QUIET] [MODULE]
             [REQUIRED] [[COMPONENTS] [components...]]
             [OPTIONAL_COMPONENTS components...]
             [REGISTRY_VIEW  (64|32|64_32|32_64|HOST|TARGET|BOTH)]
             [GLOBAL]
             [NO_POLICY_SCOPE]
             [BYPASS_PROVIDER])
    The [version] argument requests a version with which the package found should be
    compatible. There are two possible forms in which it may be specified:

    A single version with the format major[.minor[.patch[.tweak]]], where each component
    is a numeric value.

    regex: [0-9]+\.[0-9]+(\.[0-9]+(\.[0-9]+)?)?

    A version range with the format versionMin...[<]versionMax where versionMin and
    versionMax have the same format and constraints on components being integers as the
    single version. By default, both end points are included. By specifying <, the upper
    end point will be excluded. Version ranges are only supported with CMake 3.19 or
    later.
    The EXACT option requests that the version be matched exactly. This option is
    incompatible with the specification of a version range.



- FetchContent module? 
FetchContent_Declare(
  <name>
  <contentOptions>...
  [EXCLUDE_FROM_ALL]
  [SYSTEM]
  [OVERRIDE_FIND_PACKAGE |
   FIND_PACKAGE_ARGS args...]
)
FetchContent_Declare(
  googletest
  GIT_REPOSITORY https://github.com/google/googletest.git
  GIT_TAG        703bd9caab50b139428cea1aaff9974ebee5742e # release-1.10.0
)
FetchContent_Declare(
  myCompanyIcons
  URL      https://intranet.mycompany.com/assets/iconset_1.12.tar.gz
  URL_HASH MD5=5588a7b18261c20068beabfb4f530b87
)
FetchContent_Declare(
  myCompanyCertificates
  SVN_REPOSITORY svn+ssh://svn.mycompany.com/srv/svn/trunk/certs
  SVN_REVISION   -r12345
)


FetchContent_Populate(
  <name>
  [QUIET]
  [SUBBUILD_DIR <subBuildDir>]
  [SOURCE_DIR <srcDir>]
  [BINARY_DIR <binDir>]
  ...
)



- project
    - languages
    project(... LANGUAGES xxx NEXT_KEY? ...)


- set
    sets eg. environment variable to some value
    shouldn't need to add this to spack

- option
    relation to variant?


-----------------------------------------------------------------------

special values:
find_package(PythonInterp) => just a python dependency




-----------------------------------------------------------------------

could build a cmake dependency tree with a trace of conditions
but need to reconstruct original condition string from parsed tokens

if(SI_UNIT_TESTS)
    find_package(A ...)
    if(SI_BENCHMARKS)
        find_package(B ...)
    endif()
endif()
find_package(Boost 1.79.0 REQUIRED COMPONENTS ${BOOST_REQ_COMPONENTS})

=>


file_path = ""
with open(file_path) as f:
    data = f.read()


"""


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
