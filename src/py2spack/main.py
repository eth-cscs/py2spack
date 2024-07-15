"""Tool for parsing PyPI packages and converting them to a Spack package.py."""

import sys
from typing import Dict, List, Optional, Set, Tuple

import packaging.version as pv
import requests  # type: ignore
import spack.version as sv
import tomli
from packaging import requirements, specifiers
from spack import spec
from spack.util import naming

from py2spack import conversion_tools, parsing

TEST_PKG_PREFIX = "test-"


USE_TEST_PREFIX = True

USE_SPACK_PREFIX = True


class ConversionError(Exception):
    """Error while converting a packaging requirement to spack."""

    def __init__(
        self,
        msg: str,
        *,
        requirement: str | None = None,
    ):
        """Initialize error."""
        super().__init__(msg)
        self._requirement = requirement

    @property
    def requirement(self) -> str | None:  # pragma: no cover
        """Get requirement."""
        return self._requirement


class ParseError(Exception):
    """Error in parsing a pyproject.toml file.

    This error is not recoverable from, it means that the pyproject.toml file
    cannot be parsed or used at all (as opposed to a parsing.ConfigurationError,
    which only affects some portion of the pyproject.toml parsing).
    """

    def __init__(
        self,
        msg: str,
        *,
        file: str | None = None,
        pkg_name: str | None = None,
        pkg_version: str | None = None,
    ):
        """Initialize error."""
        super().__init__(msg)
        self._file = file
        self._pkg_name = pkg_name
        self._pkg_version = pkg_version

    @property
    def file(self) -> str | None:  # pragma: no cover
        """Get file."""
        return self._file

    @property
    def pkg_name(self) -> str | None:  # pragma: no cover
        """Get package name."""
        return self._pkg_name

    @property
    def pkg_version(self) -> str | None:  # pragma: no cover
        """Get package version."""
        return self._pkg_version


class APIError(Exception):
    """Error during version lookup or querying of the PyPI JSON API."""

    def __init__(
        self,
        msg: str,
    ):
        """Initialize error."""
        super().__init__(msg)


def _format_dependency(
    dependency_spec: spec.Spec,
    when_spec: spec.Spec,
    dep_types: Optional[List[str]] = None,
) -> str:
    """Format a Spack dependency.

    Format the dependency (given as the main dependency spec and a "when" spec)
    as a "depends_on(...)" statement for package.py.

    Parameters:
        dependency_spec: Main dependency spec, e.g. "package@4.2:"
        when_spec: Spec for "when=" argument, e.g. "+extra ^python@:3.10"

    Returns:
        Formatted "depends_on(...)" statement for package.py.
    """
    s = f'depends_on("{str(dependency_spec)}"'

    if when_spec is not None and when_spec != spec.Spec():
        if when_spec.architecture:
            platform_str = f"platform={when_spec.platform}"
            when_spec.architecture = None
        else:
            platform_str = ""
        when_str = f"{platform_str} {str(when_spec)}".strip()
        s += f', when="{when_str}"'

    if dep_types is not None:
        typestr = '", "'.join(dep_types)
        s += f', type=("{typestr}")'

    s += ")"

    return s


def _get_archive_extension(filename: str) -> "str | APIError":
    archive_formats = [
        ".zip",
        ".tar",
        ".tar.gz",
        ".tar.bz2",
        ".rar",
        ".7z",
        ".gz",
        ".xz",
        ".bz2",
    ]

    extension_list = [ext for ext in archive_formats if filename.endswith(ext)]

    if len(extension_list) == 0:
        # we return an API error here because the filenames are obtained through
        # the API and the function is used during the API lookup process
        msg = f"No extension recognized for: {filename}!"
        return APIError(msg)

    if len(extension_list) == 1:
        return extension_list[0]

    longest_matching_ext = max(extension_list, key=len)
    return longest_matching_ext


# TODO: verify whether spack name actually corresponds to PyPI package
def _pkg_to_spack_name(name: str) -> str:
    """Convert PyPI package name to Spack python package name."""
    spack_name: str = naming.simplify_name(name)
    if USE_SPACK_PREFIX and spack_name != "python":
        # in general, if the package name already contains the "py-" prefix, we
        # don't want to add it again. exception: 3 existing packages on spack
        # with double "py-" prefix
        if not spack_name.startswith("py-") or spack_name in [
            "py-cpuinfo",
            "py-tes",
            "py-spy",
        ]:
            spack_name = "py-" + spack_name

    return spack_name


def _convert_requirement(
    r: requirements.Requirement,
    lookup: conversion_tools.JsonVersionsLookup,
    from_extra: Optional[str] = None,
) -> List[Tuple[spec.Spec, spec.Spec]] | ConversionError:
    """Convert a packaging Requirement to its Spack equivalent.

    Each Spack requirement consists of a main dependency Spec and "when" Spec
    for conditions like variants or markers. It can happen that one requirement
    is converted into a list of multiple Spack requirements, which all need to
    be added.

    Parameters:
        r: packaging requirement
        from_extra: If this requirement an optional requirement dependent on an
        extra of the main package, supply the extra's name here.

    Returns:
        A list of tuples of (main_dependency_spec, when_spec).
    """
    spack_name = _pkg_to_spack_name(r.name)

    requirement_spec = spec.Spec(spack_name)

    # by default contains just an empty when_spec
    when_spec_list = [spec.Spec()]
    if r.marker is not None:
        # 'evaluate_marker' code returns a list of specs for  marker =>
        # represents OR of specs
        try:
            marker_eval = conversion_tools.evaluate_marker(r.marker, lookup)
        except ValueError as e:
            from_extra_str = (
                "" if not from_extra else f" from extra {from_extra}"
            )
            msg = (
                f"Unable to convert marker {r.marker} for dependency"
                f" {r}{from_extra_str}: {e}"
            )
            return ConversionError(msg, requirement=str(r))

        if isinstance(marker_eval, bool) and marker_eval is False:
            # Marker is statically false, skip this requirement
            # (because the "when" clause cannot be true)
            return []

        elif not isinstance(marker_eval, bool):
            # if the marker eval is not bool, then it is a list

            if isinstance(marker_eval, list):
                # replace empty when spec with marker specs
                when_spec_list = marker_eval

        # if marker_eval is True, then the marker is statically true, we don't
        # need to include it

    # these are the extras passed to the dependency itself; not the extras of
    # the main package for which this requirement is necessary
    if r.extras is not None:
        for extra in r.extras:
            requirement_spec.constrain(spec.Spec(f"+{extra}"))

    if r.specifier is not None:
        vlist = conversion_tools.pkg_specifier_set_to_version_list(
            r.name, r.specifier, lookup
        )

        # return Error if no version satisfies the requirement
        if not vlist:
            from_extra_str = (
                "" if not from_extra else f" from extra {from_extra}"
            )
            msg = (
                f"Unable to convert dependency"
                f" {r}{from_extra_str}: no matching versions"
            )
            return ConversionError(msg, requirement=str(r))

        requirement_spec.versions = vlist

    if from_extra is not None:
        # further constrain when_specs with extra
        for when_spec in when_spec_list:
            when_spec.constrain(spec.Spec(f"+{from_extra}"))

    return [(requirement_spec, when_spec) for when_spec in when_spec_list]


def _check_dependency_satisfiability(
    dependency_list: List[Tuple[spec.Spec, spec.Spec, str]],
) -> bool:
    """Checks a list of Spack dependencies for conflicts.

    The list consists of triplets (dependency spec, when spec, type string). A
    conflict arises if two dependencies specifying the same dependency package
    name have non-intersecting dependency specs but intersecting when specs. In
    other words, for a given package dependency (i.e. one specific name) and all
    requirements involving that dependency, we want that
    "when_spec_1.intersects(when_spec_2) => dep_spec1.intersects(dep_spec_2)",
    or "if the dependency specs intersetct, then the when specs have to
    intersect too".
    """
    sat: bool = True

    dependency_names = list(
        {dep[0].name for dep in dependency_list if dep[0].name is not None}
    )

    for name in dependency_names:
        pkg_dependencies = [
            dep for dep in dependency_list if dep[0].name == name
        ]

        for i in range(len(pkg_dependencies)):
            for j in range(i + 1, len(pkg_dependencies)):
                dep1, when1, _ = pkg_dependencies[i]
                dep2, when2, _ = pkg_dependencies[j]

                if when1.intersects(when2) and (not dep1.intersects(dep2)):
                    sat = False
                    # TODO: should conflicts be collected and returned instead
                    # of printed to console?
                    msg = (
                        f"ERROR: uncompatible requirements for dependency "
                        f"'{name}'!\nRequirement 1: {str(dep1)}; when-spec: "
                        f"{str(when1)}\nRequirement 2: {str(dep2)}; when-spec:"
                        f" {str(when2)}"
                    )
                    print(
                        msg,
                        file=sys.stderr,
                    )
    return sat


# TODO: change lookup data structure to support these operations
def _get_pypi_filenames_hashes(
    pypi_name: str, versions: List[pv.Version]
) -> Tuple[str, List[Tuple[sv.Version, str]]] | APIError:
    """Query the JSON API for file information.

    The result includes PyPI base location, file format, as well as filenames
    and hashes for all given versions.

    Returns:
        pypi_base: a string with the pypi name and sdist filename template for
        the package.
        spack_versions: a list of (spack version, sha256 hash) for requested
        versions.
    """
    r = requests.get(
        f"https://pypi.org/simple/{pypi_name}/",
        headers={"Accept": "application/vnd.pypi.simple.v1+json"},
        timeout=10,
    )

    if r.status_code != 200:
        if r.status_code == 404:
            msg = f"Package {pypi_name} not found on PyPI (status code 404)"
            return APIError(msg)

        msg = (
            f"Error when querying JSON API (status code {r.status_code})."
            f" Response: {r.text}"
        )
        return APIError(msg)

    files = r.json()["files"]

    # for now, don't handle wheels only
    non_wheels = [f for f in files if not f["filename"].endswith(".whl")]

    if len(non_wheels) == 0:
        msg = (
            "No source distributions found, only wheels!"
            " Wheel file parsing not supported yet."
        )
        return APIError(msg)

    # parse the archive file extension of sdists
    # TODO: we're assuming all sdists have the same extension, it would make
    # sense to allow different versions to have different file extensions
    archive_extension = _get_archive_extension(non_wheels[-1]["filename"])

    if isinstance(archive_extension, APIError):
        return archive_extension

    spack_versions: List[Tuple[sv.Version, str]] = []
    pypi_base = ""

    # get the version number and sha256 hash for each provided pyproject
    sorted_versions = sorted(versions)
    for version in reversed(sorted_versions):
        filename = f"{pypi_name}-{version}{archive_extension}"
        matching_files = [f for f in non_wheels if f["filename"] == filename]

        if len(matching_files) != 1:
            # TODO: abort or skip? we skip here but it's still included later,
            # for the depenencies...
            msg = (
                f"No sdist for version {str(version)} found on pypi,"
                " skipping this version."
            )
            print(
                msg,
                file=sys.stderr,
            )
            continue

        # parse the pypi base information for spack
        if pypi_base == "":
            pypi_base = f"{pypi_name}/{filename}"

        sha256 = matching_files[0]["hashes"]["sha256"]
        spack_version = conversion_tools.packaging_to_spack_version(version)

        spack_versions.append((spack_version, sha256))

    if not spack_versions:
        msg = "No matching sdist files found on PyPI."
        return APIError(msg)

    return pypi_base, spack_versions


def _people_to_strings(
    parsed_people: List[Tuple[str | None, str | None]],
) -> List[str]:
    """Convert 'authors' or 'maintainers' lists to strings."""
    people = []
    for p0, p1 in parsed_people:
        if p0 is None and p1 is None:
            continue
        elif p0 is None:
            people.append(p1)
        elif p1 is None:
            people.append(p0)
        else:
            people.append(f"{p0}, {p1}")

    return people  # type: ignore


def _parse_name(
    explicit_name: str | None = None,
    parsed_name: str | None | parsing.ConfigurationError = None,
) -> str | parsing.ConfigurationError:
    if explicit_name:
        return explicit_name
    elif isinstance(parsed_name, str):
        return parsed_name
    elif isinstance(parsed_name, parsing.ConfigurationError):
        return parsed_name
    elif parsed_name is None:
        msg = (
            "Field 'project.name' is missing in pyproject.toml and not "
            "explicitly provided, skipping file"
        )
        return parsing.ConfigurationError(msg, key="project.name")


def _parse_version(
    explicit_version: str | None = None,
    parsed_version: str | None | parsing.ConfigurationError = None,
) -> pv.Version | parsing.ConfigurationError:
    if explicit_version:
        candidate_version_str = explicit_version
    elif isinstance(parsed_version, str):
        candidate_version_str = parsed_version
    elif isinstance(parsed_version, parsing.ConfigurationError):
        return parsed_version
    elif parsed_version is None:
        msg = (
            "Field 'project.version' is missing in pyproject.toml and not "
            "explicitly provided, skipping file"
        )
        return parsing.ConfigurationError(msg, key="project.version")

    # check version validity
    candidate_version = conversion_tools.acceptable_version(
        candidate_version_str
    )
    if candidate_version:
        return candidate_version
    else:
        msg = f"Invalid version: {candidate_version_str}"
        return parsing.ConfigurationError(msg, key="project.version")


class PyProject:
    """A class to represent a pyproject.toml file.

    Contains all fields which are present in METADATA, plus additional ones only
    found in pyproject.toml. E.g. build-backend, build dependencies.
    """

    def __init__(self):
        """Initialize empty PyProject."""
        self.name: str = ""
        self.data: Dict = {}
        self.tool: Dict = {}
        self.build_backend: Optional[str] = None
        self.build_requires: List[requirements.Requirement] = []
        self.dynamic: List[str] = []
        self.version: Optional[pv.Version] = None
        self.description: Optional[str] = None
        self.requires_python: Optional[specifiers.SpecifierSet] = None
        self.license: Optional[str] = None
        self.authors: List[str] = []
        self.maintainers: List[str] = []
        self.dependencies: List[requirements.Requirement] = []
        self.optional_dependencies: Dict[
            str, List[requirements.Requirement]
        ] = {}
        self.homepage: Optional[str] = None
        self.metadata_errors: List[parsing.ConfigurationError] = []
        self.dependency_errors: List[parsing.ConfigurationError] = []

    @classmethod
    def from_toml(
        cls, path: str, name: str, version: str
    ) -> "PyProject | ParseError":
        """Create a PyProject instance from a pyproject.toml file.

        The version corresponding to the pyproject.toml file should be known
        a-priori and should be passed here as a string argument. Alternatively,
        it can be read from the pyproject.toml file if it is specified
        explicitly there.

        Parameters:
            path: The path to the toml file.
            version: The version of the package which the pyproject.toml
            corresponds to.

        Returns:
            A PyProject instance.
        """
        try:
            with open(path, "rb") as f:
                data = tomli.load(f)
        except (FileNotFoundError, IOError) as e:
            msg = f"Failed to read pyproject.toml, skipping file. Error: {e}"
            return ParseError(
                msg, file=path, pkg_name=name, pkg_version=version
            )

        pyproject = PyProject()
        fetcher = parsing.DataFetcher(data)

        if "project" not in fetcher:
            msg = 'Section "project" missing in pyproject.toml, skipping file'
            return ParseError(
                msg, file=path, pkg_name=name, pkg_version=version
            )

        # parse project name, which should be provided explicitly (otherwise it
        # is parsed from pyproject.toml)
        parsed_name = _parse_name(
            explicit_name=name, parsed_name=fetcher.get_str("project.name")
        )
        if isinstance(parsed_name, parsing.ConfigurationError):
            return ParseError(
                str(parsed_name), file=path, pkg_name=name, pkg_version=version
            )

        # normalize the name
        pyproject.name = naming.simplify_name(parsed_name)

        # parse project version, which should be provided explicitly (otherwise
        # it is parsed from pyproject.toml)
        parsed_version = _parse_version(
            explicit_version=version,
            parsed_version=fetcher.get_str("project.version"),
        )
        if isinstance(parsed_version, parsing.ConfigurationError):
            return ParseError(
                str(parsed_name),
                file=path,
                pkg_name=pyproject.name,
                pkg_version=version,
            )
        pyproject.version = parsed_version

        # parse metadata
        # ConfigurationErrors in metadata fields will simply be ignored

        description = fetcher.get_str("project.description")
        if not isinstance(description, parsing.ConfigurationError):
            pyproject.description = description

        homepage = fetcher.get_homepage()
        if not isinstance(homepage, parsing.ConfigurationError):
            pyproject.homepage = homepage

        authors = fetcher.get_people("project.authors")
        if not isinstance(authors, parsing.ConfigurationError):
            pyproject.authors = _people_to_strings(authors)

        maintainers = fetcher.get_people("project.maintainers")
        if not isinstance(maintainers, parsing.ConfigurationError):
            pyproject.maintainers = _people_to_strings(maintainers)

        lic = fetcher.get_license()
        if not isinstance(lic, parsing.ConfigurationError):
            pyproject.license = lic

        # parse build system
        build_req_result = fetcher.get_build_requires()
        if isinstance(build_req_result, parsing.ConfigurationError):
            pyproject.dependency_errors.append(build_req_result)
        else:
            dependencies, errors = build_req_result
            pyproject.build_requires = dependencies
            pyproject.dependency_errors.extend(errors)

        build_backend_result = fetcher.get_build_backend()
        if isinstance(build_backend_result, parsing.ConfigurationError):
            pyproject.metadata_errors.append(build_backend_result)
        else:
            pyproject.build_backend = build_backend_result

        # parse all dependencies
        requires_python = fetcher.get_requires_python()
        if isinstance(requires_python, parsing.ConfigurationError):
            pyproject.dependency_errors.append(requires_python)
        else:
            pyproject.requires_python = requires_python

        dep_result = fetcher.get_dependencies()
        if isinstance(dep_result, parsing.ConfigurationError):
            pyproject.dependency_errors.append(dep_result)
        else:
            dependencies, errors = dep_result
            pyproject.dependencies = dependencies
            pyproject.dependency_errors.extend(errors)

        opt_dep_result = fetcher.get_optional_dependencies()
        if isinstance(opt_dep_result, parsing.ConfigurationError):
            pyproject.dependency_errors.append(opt_dep_result)
        else:
            opt_dependencies, errors = opt_dep_result
            pyproject.optional_dependencies = opt_dependencies
            pyproject.dependency_errors.extend(errors)

        return pyproject


class SpackPyPkg:
    """Class representing a Spack PythonPackage object.

    Instances are created directly from PyProject objects, by converting
    PyProject fields and semantics to their Spack equivalents (where possible).
    """

    def __init__(self):
        """Initialize empty SpackPyPkg."""
        self.name: str = ""
        self.pypi_name: str = ""
        self.description: Optional[str] = None
        self.pypi: str = ""
        self.versions: List[Tuple[sv.Version, str]] = []
        self.all_versions: List[pv.Version]
        self.variants: Set[str] = set()
        self.maintainers: List[str] = []
        self.authors: List[str] = []
        self.license: Optional[str] = None
        self.dependencies_by_type: Dict[
            str, List[Tuple[spec.Spec, spec.Spec]]
        ] = {}
        self.file_parse_errors: List[Tuple[str, ParseError]] = []
        self.metadata_parse_errors: Dict[
            str, List[parsing.ConfigurationError]
        ] = {}
        self.dependency_parse_errors: Dict[
            str, List[parsing.ConfigurationError]
        ] = {}
        self.dependency_conversion_errors: Dict[str, List[ConversionError]] = {}

        # self.import_modules = []

    def get_metadata(self, pyproject: PyProject):
        """Load and convert main metadata from given PyProject instance.

        Does not include pypi field, versions, or the dependencies.
        """
        self.pypi_name = pyproject.name
        self.name = _pkg_to_spack_name(pyproject.name)
        self.description = pyproject.description

        if pyproject.authors is not None:
            for elem in pyproject.authors:
                self.authors.append(elem)

        if pyproject.maintainers is not None:
            for elem in pyproject.maintainers:
                self.maintainers.append(elem)

        if pyproject.license:
            self.license = pyproject.license

    @staticmethod
    def from_pyprojects(
        pyprojects: List[PyProject],
        lookup: conversion_tools.JsonVersionsLookup,
    ) -> "SpackPyPkg | None":
        """Takes PyProject objects and converts them to a single SpackPyPkg.

        Metadata is extracted from the most recent PyProject version.
        Dependencies are collected for all versions and combined.
        """
        if len(pyprojects) == 0:
            print("Received an empty list.", file=sys.stderr)
            return None

        # get the base pkg name
        name = pyprojects[0].name

        # check that all have a version and the same package name
        for pyproject in pyprojects:
            if pyproject.name != name or pyproject.version is None:
                msg = (
                    "All PyProject objects must have the same name and a "
                    "specified version."
                )

                print(
                    msg,
                    file=sys.stderr,
                )
                return None

        # sort by version number
        sorted_pyprojects = sorted(pyprojects, key=lambda proj: proj.version)  # type: ignore

        pyproject_versions = [proj.version for proj in sorted_pyprojects]

        spackpkg = SpackPyPkg()

        # use the newest version to parse the metadata
        # TODO: some fields should be parsed and combined from all versions,
        # e.g. license
        most_recent = sorted_pyprojects[-1]
        spackpkg.get_metadata(most_recent)

        # load PyPI location for the spack package as well as a list of
        # available versions and hashes for the given pyprojects
        res = _get_pypi_filenames_hashes(name, pyproject_versions)

        if isinstance(res, APIError):
            msg = f"API Error: {str(res)}"
            print(msg, file=sys.stderr)
            return None

        pypi_base, version_hash_list = res

        spackpkg.pypi = pypi_base
        spackpkg.versions = version_hash_list

        # load list of all versions from JSON API
        spackpkg.all_versions = lookup[spackpkg.pypi_name]

        # Conversion and simplification of dependencies summarized:
        # Collect unique dependencies (dependency spec, when spec) together with
        # a list of versions for which this dependency is required.
        # Condense the version list and add it to the when spec.
        # For each pair of dependencies (for the same package), make sure that
        # there are no conflicts/unsatisfiable requirements.

        # map each unique dependency (dependency spec, when spec) to a list of
        # package versions that have this dependency
        specs_to_versions: Dict[
            Tuple[spec.Spec, spec.Spec], List[pv.Version]
        ] = {}

        # map dependencies to their dependency types (build, run, test, ...)
        specs_to_types: Dict[Tuple[spec.Spec, spec.Spec], Set[str]] = {}

        # convert and collect dependencies for each pyproject
        for pyproject in sorted_pyprojects:
            if pyproject.dependency_errors:
                spackpkg.dependency_parse_errors[str(pyproject.version)] = (
                    pyproject.dependency_errors
                )

            # build dependencies
            for r in pyproject.build_requires:
                # a single requirement can translate to multiple distinct
                # dependencies
                spec_list = _convert_requirement(r, lookup)
                if isinstance(spec_list, ConversionError):
                    if (
                        str(pyproject.version)
                        not in spackpkg.dependency_conversion_errors
                    ):
                        spackpkg.dependency_conversion_errors[
                            str(pyproject.version)
                        ] = []
                    spackpkg.dependency_conversion_errors[
                        str(pyproject.version)
                    ].append(spec_list)
                    continue

                for specs in spec_list:
                    if specs not in specs_to_versions:
                        specs_to_versions[specs] = []

                    # add the current version to this dependency
                    specs_to_versions[specs].append(pyproject.version)

                    if specs not in specs_to_types:
                        specs_to_types[specs] = set()

                    # add build dependency
                    specs_to_types[specs].add("build")
            # normal runtime dependencies
            for r in pyproject.dependencies:
                spec_list = _convert_requirement(r, lookup)
                if isinstance(spec_list, ConversionError):
                    if (
                        str(pyproject.version)
                        not in spackpkg.dependency_conversion_errors
                    ):
                        spackpkg.dependency_conversion_errors[
                            str(pyproject.version)
                        ] = []
                    spackpkg.dependency_conversion_errors[
                        str(pyproject.version)
                    ].append(spec_list)
                    continue

                for specs in spec_list:
                    if specs not in specs_to_versions:
                        specs_to_versions[specs] = []

                    specs_to_versions[specs].append(pyproject.version)

                    if specs not in specs_to_types:
                        specs_to_types[specs] = set()

                    # add build and runtime dependency
                    specs_to_types[specs].add("build")
                    specs_to_types[specs].add("run")

            # optional/variant dependencies
            for extra, deps in pyproject.optional_dependencies.items():
                spackpkg.variants.add(extra)
                for r in deps:
                    spec_list = _convert_requirement(
                        r, lookup, from_extra=extra
                    )
                    if isinstance(spec_list, ConversionError):
                        if (
                            str(pyproject.version)
                            not in spackpkg.dependency_conversion_errors
                        ):
                            spackpkg.dependency_conversion_errors[
                                str(pyproject.version)
                            ] = []
                        spackpkg.dependency_conversion_errors[
                            str(pyproject.version)
                        ].append(spec_list)
                        continue

                    for specs in spec_list:
                        if specs not in specs_to_versions:
                            specs_to_versions[specs] = []

                        specs_to_versions[specs].append(pyproject.version)

                        if specs not in specs_to_types:
                            specs_to_types[specs] = set()

                        # add build and runtime dependency
                        specs_to_types[specs].add("build")
                        specs_to_types[specs].add("run")

            # python dependencies
            if pyproject.requires_python is not None:
                r = requirements.Requirement("python")
                r.specifier = pyproject.requires_python
                spec_list = _convert_requirement(r, lookup)
                if isinstance(spec_list, ConversionError):
                    if (
                        str(pyproject.version)
                        not in spackpkg.dependency_conversion_errors
                    ):
                        spackpkg.dependency_conversion_errors[
                            str(pyproject.version)
                        ] = []
                    spackpkg.dependency_conversion_errors[
                        str(pyproject.version)
                    ].append(spec_list)
                    continue

                for specs in spec_list:
                    if specs not in specs_to_versions:
                        specs_to_versions[specs] = []

                    specs_to_versions[specs].append(pyproject.version)

                    if specs not in specs_to_types:
                        specs_to_types[specs] = set()

                    # add build and runtime dependency
                    specs_to_types[specs].add("build")
                    specs_to_types[specs].add("run")

        # now we have a list of versions for each requirement
        # convert versions to an equivalent condensed version list, and add this
        # list to the when spec. from there, build a complete list with all
        # dependencies

        final_dependency_list: List[Tuple[spec.Spec, spec.Spec, str]] = []

        for (dep_spec, when_spec), vlist in specs_to_versions.items():
            types = specs_to_types[dep_spec, when_spec]

            # convert the set of types to a string as it would be displayed in
            # the package.py, e.g. '("build", "run")'.
            canonical_typestring = str(tuple(sorted(list(types)))).replace(
                "'", '"'
            )

            versions_condensed = conversion_tools.condensed_version_list(
                vlist, spackpkg.all_versions
            )
            when_spec.versions = versions_condensed
            final_dependency_list.append(
                (dep_spec, when_spec, canonical_typestring)
            )

        # check for conflicts
        satisfiable = _check_dependency_satisfiability(final_dependency_list)

        if not satisfiable:
            msg = (
                f"Cannot convert package '{spackpkg.pypi_name}' due to "
                "incompatible requirements."
            )
            print(
                msg,
                file=sys.stderr,
            )
            return None

        # store dependencies by their type string (e.g. type=("build", "run"))
        for dep_spec, when_spec, typestring in final_dependency_list:
            if typestring not in spackpkg.dependencies_by_type:
                spackpkg.dependencies_by_type[typestring] = []

            spackpkg.dependencies_by_type[typestring].append(
                (dep_spec, when_spec)
            )

        return spackpkg

    def print_package(self, outfile=sys.stdout):
        """Format and write the package to 'outfile'.

        By default outfile=sys.stdout. The package can be written directly to a
        package.py file by supplying the corresponding file object.
        """
        print("Outputting package.py...\n")

        cpright = """\
# Copyright 2013-2024 Lawrence Livermore National Security, LLC and other
# Spack Project Developers. See the top-level COPYRIGHT file for details.
#
# SPDX-License-Identifier: (Apache-2.0 OR MIT)
"""

        print(cpright, file=outfile)

        print("from spack.package import *", file=outfile)
        print("", file=outfile)

        print(
            f"class {naming.mod_to_class(self.name)}(PythonPackage):",
            file=outfile,
        )

        if self.description is not None and len(self.description) > 0:
            print(f'    """{self.description}"""', file=outfile)
        else:
            txt = (
                '    """FIXME: Put a proper description'
                ' of your package here."""'
            )
            print(
                txt,
                file=outfile,
            )

        print("", file=outfile)

        print(f'    pypi = "{self.pypi}"', file=outfile)

        print("", file=outfile)

        if self.license is not None and self.license != "":
            print(f'    license("{self.license}")', file=outfile)
        else:
            print("    # FIXME: add license", file=outfile)

        print("", file=outfile)

        print("    # FIXME: add github names for maintainers", file=outfile)
        if self.authors:
            print("    # Authors:", file=outfile)
            for author in self.authors:
                print(f"    # {author}", file=outfile)

            print("", file=outfile)

        if self.maintainers:
            print("    # Maintainers:", file=outfile)
            for maintainer in self.maintainers:
                print(f"    # {maintainer}", file=outfile)

            print("", file=outfile)

        for v, sha256 in self.versions:
            print(f'    version("{str(v)}", sha256="{sha256}")', file=outfile)

        print("", file=outfile)

        # fixme for unparsed versions
        if self.file_parse_errors:
            txt = (
                "    # FIXME: the pyproject.toml files for the following "
                "versions could not be parsed"
            )
            print(
                txt,
                file=outfile,
            )
            for v, p_err in self.file_parse_errors:
                print(f"    # version {str(v)}: {str(p_err)}")

            print("", file=outfile)

        for v in self.variants:
            print(f'    variant("{v}", default=False)', file=outfile)

        print("", file=outfile)

        if self.dependency_parse_errors:
            txt = "    # FIXME: the following dependencies could not be parsed"
            print(
                txt,
                file=outfile,
            )
            for v, cfg_errs in self.dependency_parse_errors.items():
                print(f"    # version {str(v)}:", file=outfile)
                for cfg_err in cfg_errs:
                    print(f"    #    {str(cfg_err)}", file=outfile)

            print("", file=outfile)

        if self.dependency_conversion_errors:
            txt = (
                "    # FIXME: the following dependencies could be parsed but "
                "not converted to spack"
            )
            print(
                txt,
                file=outfile,
            )
            for v, cnv_errs in self.dependency_conversion_errors.items():
                print(f"    # version {str(v)}:", file=outfile)
                for cnv_err in cnv_errs:
                    print(f"    #    {str(cnv_err)}", file=outfile)

            print("", file=outfile)

        # custom key for sorting requirements in package.py:
        # (is_python, has_variant, pkg_name, pkg_version_list, variant_string)
        def _requirement_sort_key(req: Tuple[spec.Spec, spec.Spec]):
            dep, when = req
            # != because we want python to come first
            is_python = int(dep.name != "python")
            has_variant = int(len(str(when.variants)) > 0)
            pkg_name = dep.name
            pkg_version = dep.versions
            variant = str(when.variants)
            return (is_python, has_variant, pkg_name, pkg_version, variant)

        for dep_type in list(self.dependencies_by_type.keys()):
            dependencies = self.dependencies_by_type[dep_type]
            sorted_dependencies = sorted(
                dependencies, key=_requirement_sort_key
            )

            print(f"    with default_args(type={dep_type}):", file=outfile)
            for dep_spec, when_spec in sorted_dependencies:
                print(
                    "        " + _format_dependency(dep_spec, when_spec),
                    file=outfile,
                )

            print("", file=outfile)

        print("", file=outfile)


if __name__ == "__main__":
    pprojects = []
    for vn in ["23.12.0", "23.12.1", "24.2.0", "24.4.0", "24.4.1", "24.4.2"]:
        py_pkg = PyProject.from_toml(
            f"example_pyprojects/black/pyproject{vn}.toml", "black", vn
        )
        # for v in ["4.66.1", "4.66.2", "4.66.3", "4.66.4"]:
        #     py_pkg = PyProject.from_toml(
        #         f"example_pyprojects/tqdm/pyproject{v}.toml", version=v
        #     )

        if isinstance(py_pkg, ParseError):
            err_txt = (
                f"Error: could not generate PyProject from pyproject{vn}.toml:"
                f" {py_pkg}"
            )
            print(
                err_txt,
                file=sys.stderr,
            )
            continue

        pprojects.append(py_pkg)

    lookup = conversion_tools.JsonVersionsLookup()

    # convert to spack
    spack_pkg = SpackPyPkg.from_pyprojects(pprojects, lookup)

    if spack_pkg is None:
        print(
            "Error: could not generate spack package from PyProject",
            file=sys.stderr,
        )
        exit()

    if USE_TEST_PREFIX:
        spack_pkg.name = TEST_PKG_PREFIX + spack_pkg.name

    print("spack pkg built")

    # print to console
    spack_pkg.print_package(outfile=sys.stdout)

    # or print to file.
    # TODO: allow tool to create a folder for the package and store package.py
    # there
    # with open("output/package.py", "w+") as f:
    #     spack_pkg.print_package(outfile=f)

    # TODO: test new version with multiple pyprojects
