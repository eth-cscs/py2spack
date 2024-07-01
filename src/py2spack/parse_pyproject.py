"""Module for parsing pyproject.toml files and converting them to a Spack package.py."""

import sys
from typing import Dict, List, Optional, Tuple, Union, Set

import packaging.version as pv  # type: ignore
import pyproject_metadata as py_metadata  # type: ignore
import requests  # type: ignore
import spack.version as sv  # type: ignore
import tomli
from packaging import requirements, specifiers
from spack import spec

from py2spack import external

TEST_PKG_PREFIX = "test-"


USE_TEST_PREFIX = True

USE_SPACK_PREFIX = True


lookup = external.JsonVersionsLookup()


def _format_dependency(
    dependency_spec: spec.Spec,
    when_spec: spec.Spec,
    dep_types: Optional[List[str]] = None,
) -> str:
    """Format a Spack dependency.

    Format the dependency (given as the main dependency spec and a "when" spec) as a
    "depends_on(...)" statement for package.py.

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


def _get_archive_extension(filename: str) -> "str | None":
    if filename.endswith(".whl"):
        print(
            "Supplied filename is a wheel file, please provide archive file!",
            file=sys.stderr,
        )
        return ".whl"

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
        print(f"No extension recognized for: {filename}!", file=sys.stderr)
        return None

    if len(extension_list) == 1:
        return extension_list[0]

    longest_matching_ext = max(extension_list, key=len)
    return longest_matching_ext


# TODO: do we have to/can we further verify validity of these names?
# can we check whether a package already exists on spack? if we have the correct name?
def _pkg_to_spack_name(name: str) -> str:
    """Convert PyPI package name to Spack python package name."""
    spack_name = external.normalized_name(name)
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
    r: requirements.Requirement, from_extra: Optional[str] = None
) -> List[Tuple[spec.Spec, spec.Spec]]:
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
        # TODO: make sure we're evaluating and handling markers correctly
        # harmens code returns a list of specs for  marker => represents OR of specs
        # for each spec, add the requirement individually
        marker_eval = external.evaluate_marker(r.marker, lookup)

        if isinstance(marker_eval, bool) and marker_eval is False:
            # Marker is statically false, skip this requirement
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
        vlist = external.pkg_specifier_set_to_version_list(r.name, r.specifier, lookup)

        # TODO: how to handle the case when version list is empty, i.e. no matching
        # versions found?
        if not vlist:
            req_string = str(r)
            if from_extra:
                req_string += " from extra '" + from_extra + "'"
            raise ValueError(
                f"Could not resolve dependency {req_string}: No matching versions for"
                + f" '{r.name}' found!"
            )

        requirement_spec.versions = vlist

    if from_extra is not None:
        # further constrain when_specs with extra
        for when_spec in when_spec_list:
            when_spec.constrain(spec.Spec(f"+{from_extra}"))

    return [(requirement_spec, when_spec) for when_spec in when_spec_list]


# TODO: replace with spack mod_to_class?
def _name_to_class_name(name: str) -> str:
    """Convert a package name to a canonical class name for package.py."""
    classname = ""
    # in case there would be both - and _ in name
    name = name.replace("_", "-")
    name_arr = name.split("-")
    for w in name_arr:
        classname += w.capitalize()

    return classname


def _to_pypi_sdist_filename(pkg_name: str, version: str, extension: str):
    return f"{pkg_name}-{version}{extension}"


def _check_dependency_satisfiability(
    dependency_list: List[Tuple[spec.Spec, spec.Spec, str]],
) -> bool:
    """Checks a list of Spack dependencies for conflicts.

    The list consists of triplets (dependency spec, when spec, type string). A conflict
    arises if two dependencies specifying the same dependency package name have non-
    intersecting dependency specs but intersecting when specs. In other words, for a
    given package dependency (i.e. one specific name) and all requirements involving
    that dependency, we want that "when_spec_1.intersects(when_spec_2) =>
    dep_spec1.intersects(dep_spec_2)".
    """
    sat: bool = True

    # TODO: make sure we have checked before that names here cannot be None
    dependency_names = list({dep[0].name for dep in dependency_list})

    for name in dependency_names:
        pkg_dependencies = list(
            filter(lambda dep: dep[0].name == name, dependency_list)
        )

        for i in range(len(pkg_dependencies)):
            for j in range(i + 1, len(pkg_dependencies)):
                dep1, when1, _ = pkg_dependencies[i]
                dep2, when2, _ = pkg_dependencies[j]

                if when1.intersects(when2) and (not dep1.intersects(dep2)):
                    sat = False
                    print(
                        f"ERROR: uncompatible requirements for dependency '{name}'!\n",
                        f"Requirement 1: {str(dep1)}; when-spec: {str(when1)}\n",
                        f"Requirement 2: {str(dep2)}; when-spec: {str(when2)}",
                        file=sys.stderr,
                    )
    return sat


def _get_pypi_filenames_hashes(
    pypi_name: str, versions: List[pv.Version]
) -> Optional[Tuple[str, List[Tuple[sv.Version, str]]]]:
    """Query the JSON API for file information.

    The result includes PyPI base location, file format, as well as filenames
    and hashes for all given versions.

    Returns:
        pypi_base: a string with the pypi name and sdist filename template for the
        package.
        spack_versions: a list of (spack version, sha256 hash) for requested versions.
    """
    # TODO: since we're doing lookups in the API in multiple places (using
    # JsonVersionsLookup, here, potentially earlier to download tomls...) ->
    # combine/unify these lookups in single class
    # TODO: later move pypi/all_files stuff to get_metadata()?

    r = requests.get(
        f"https://pypi.org/simple/{pypi_name}/",
        headers={"Accept": "application/vnd.pypi.simple.v1+json"},
        timeout=10,
    )

    if r.status_code != 200:
        print(
            f"Error when querying json API. status code : {r.status_code}",
            file=sys.stderr,
        )
        if r.status_code == 404:
            print(
                f"Package {pypi_name} not found on PyPI...",
                file=sys.stderr,
            )
        return None

    files = r.json()["files"]

    # TODO: how to handle wheels? for now just exclude
    non_wheels = list(filter(lambda f: not f["filename"].endswith(".whl"), files))
    if len(non_wheels) == 0:
        print(
            "No source distributions found, only wheels!",
            "\nWheel file parsing not supported yet...",
            file=sys.stderr,
        )
        return None

    # parse the archive file extension of sdists
    # TODO: use different approach to filename parsing?
    # TODO: we're assuming all sdists have the same extension
    archive_extension = _get_archive_extension(non_wheels[-1]["filename"])

    if archive_extension is None:
        print(
            "No archive file extension recognized.",
            file=sys.stderr,
        )
        return None

    spack_versions: List[Tuple[sv.Version, str]] = []
    pypi_base = ""

    # get the version number and sha256 hash for each provided pyproject
    sorted_versions = sorted(versions)
    for version in reversed(sorted_versions):
        filename = _to_pypi_sdist_filename(
            pypi_name,
            version,
            archive_extension,
        )
        matching_files = list(filter(lambda f: f["filename"] == filename, non_wheels))

        if len(matching_files) != 1:
            # TODO: abort or skip? we skip here but it's still included later,
            # for the depenencies...
            print(
                f"No sdist for version {str(version)} found on pypi,",
                "skipping this version.",
                file=sys.stderr,
            )
            continue

        # parse the pypi base information for spack
        if pypi_base == "":
            pypi_base = f"{pypi_name}/{filename}"

        sha256 = matching_files[0]["hashes"]["sha256"]
        spack_version = external.packaging_to_spack_version(version)

        spack_versions.append((spack_version, sha256))

    return pypi_base, spack_versions


class PyProject:
    """A class to represent a pyproject.toml file.

    Contains all fields which are present in METADATA, plus additional ones only found
    in pyproject.toml. E.g. build-backend, build dependencies.
    """

    def __init__(self):
        """Initialize empty PyProject."""
        self.name: str = ""

        self.tool: Dict = dict()
        self.build_backend: Optional[str] = None
        self.build_requires: List[requirements.Requirement] = []
        self.metadata: Optional[py_metadata.StandardMetadata] = None
        self.dynamic: List[str] = []
        self.version: Optional[pv.Version] = None
        self.description: Optional[str] = None
        self.readme: Optional[str] = None
        self.requires_python: Optional[specifiers.SpecifierSet] = None
        self.license: Optional[py_metadata.License] = None
        self.authors: Optional[List] = None
        self.maintainers: Optional[List] = None
        self.keywords: Optional[List[str]] = None
        self.classifiers: Optional[List[str]] = None
        self.urls: Optional[Dict[str, str]] = None
        self.scripts: Optional[Dict[str, str]] = None
        self.gui_scripts: Optional[Dict[str, str]] = None
        self.entry_points: Optional[Dict[str, List[str]]] = None
        self.dependencies: List[requirements.Requirement] = []
        self.optional_dependencies: Dict[str, List[requirements.Requirement]] = dict()

    @staticmethod
    def from_toml(path: str, version: str = "") -> "PyProject | None":
        """Create a PyProject instance from a pyproject.toml file.

        The version corresponding to the pyproject.toml file should be known a-priori
        and should be passed here as a string argument. Alternatively, it can be read
        from the pyproject.toml file if it is specified explicitly there.

        Parameters:
            path: The path to the toml file.
            version: The version of the package which the pyproject.toml corresponds to.

        Returns:
            A PyProject instance.
        """
        try:
            with open(path, "rb") as f:
                toml_data = tomli.load(f)
        except (FileNotFoundError, IOError) as e:
            print(f"Failed to read .toml file: {e}", file=sys.stderr)
            return None

        pyproject = PyProject()

        # TODO: parse build system
        # if backend is poetry things are a bit different (dependencies)

        # parse pyproject metadata
        # this handles all the specified fields in the [project] table of pyproject.toml
        pyproject.metadata = py_metadata.StandardMetadata.from_pyproject(toml_data)

        # parse [build] table of pyproject.toml
        pyproject.build_backend = toml_data["build-system"]["build-backend"]
        build_dependencies = toml_data["build-system"]["requires"]
        pyproject.build_requires = [
            requirements.Requirement(req) for req in build_dependencies
        ]

        # transfer fields from metadata to pyproject instance
        attributes = [
            "name",
            "version",
            "description",
            "readme",
            "requires_python",
            "license",
            "authors",
            "maintainers",
            "keywords",
            "classifiers",
            "urls",
            "scripts",
            "gui_scripts",
            "entry_points",
            "dependencies",
            "optional_dependencies",
        ]

        for attr in attributes:
            setattr(pyproject, attr, getattr(pyproject.metadata, attr, None))

        # normalize the name
        pyproject.name = external.normalized_name(pyproject.name)

        pyproject.tool = toml_data.get("tool", {})

        # TODO: handling the version, make sure we have the version of the current
        # project
        # NOTE: in general, since we have downloaded and are parsing the pyproject.toml
        # of a specific version, we should know the version number a-priori. In this
        # case it should be passed as a string argument to the "from_toml(..)" method.
        if version:
            pyproject.version = external.acceptable_version(version)
        if pyproject.version is None:
            if pyproject.dynamic is not None and "version" in pyproject.dynamic:
                # TODO: get version dynamically?
                print(
                    "ERROR: version specified as dynamic, this is not supported yet!",
                    file=sys.stderr,
                )
                return None
            else:
                print("ERROR: no version for pyproject.toml found!", file=sys.stderr)
                return None

        # TODO: build-backend-specific parsing of tool and other tables,
        # e.g. for additional dependencies
        # for example poetry could use "tool.poetry.dependencies" to specify
        # dependencies

        if (
            pyproject.license is None
            or pyproject.license.text is None
            or pyproject.license.text == ""
        ):
            # license can also be specified in classifiers
            if pyproject.classifiers is not None:
                # get all classifiers detailing licenses
                license_classifiers = list(
                    filter(lambda x: x.startswith("License"), pyproject.classifiers)
                )
                # for each license classifier, split by "::" and take the last substring
                # (and strip unnecessary whitespace)
                licenses = list(
                    map(lambda x: x.split("::")[-1].strip(), license_classifiers)
                )
                if len(licenses) > 0:
                    # TODO: can we decide purely from classifiers whether AND or OR?
                    # AND is more restrictive => be safe
                    license_txt = " AND ".join(licenses)
                    pyproject.license = py_metadata.License(text=license_txt, file=None)

        # manual checking of license format & text
        if pyproject.license is not None:
            if pyproject.license.text is not None and len(pyproject.license.text) > 200:
                print(
                    "License text appears to be full license content instead of",
                    "license identifier. Please double check and add license",
                    "identifier manually to package.py file.",
                    file=sys.stderr,
                )
                pyproject.license = None
            elif pyproject.license.text is None and pyproject.license.file is not None:
                print(
                    "License is supplied as a file. This is not supported, please add",
                    "license identifier manually to package.py file.",
                    file=sys.stderr,
                )

        return pyproject


class SpackPyPkg:
    """Class representing a Spack PythonPackage object.

    Instances are created directly from PyProject objects, by converting PyProject
    fields and semantics to their Spack equivalents (where possible).
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
        self.maintainers: List[List[str]] = []
        self.authors: List[List[str]] = []
        self.license: Optional[str] = None
        self.dependencies_by_type: Dict[str, List[Tuple[spec.Spec, spec.Spec]]] = {}

        # import_modules = []

    def _get_metadata(self, pyproject: PyProject):
        """Load and convert main metadata from given PyProject instance.

        Does not include pypi field, versions, or the dependencies.
        """
        self.pypi_name = pyproject.name
        self.name = _pkg_to_spack_name(pyproject.name)
        self.description = pyproject.description

        if pyproject.authors is not None:
            for elem in pyproject.authors:
                if isinstance(elem, str):
                    self.authors.append([elem])
                elif isinstance(elem, dict):
                    if set(elem.keys()).issubset(set(["name", "email"])):
                        author = []
                        for key in ["name", "email"]:
                            if key in elem.keys():
                                author.append(elem[key])
                        self.authors.append(author)
                    else:
                        print(
                            "Expected author dict to contain keys 'name' or 'email':",
                            str(elem),
                            file=sys.stderr,
                        )
                elif isinstance(elem, tuple) or isinstance(elem, list):
                    self.authors.append(list(elem))
                else:
                    print(
                        "Expected authors to be either string or dict elements:",
                        str(elem),
                        file=sys.stderr,
                    )

        if pyproject.maintainers is not None:
            for elem in pyproject.maintainers:
                if isinstance(elem, str):
                    self.maintainers.append([elem])
                elif isinstance(elem, dict):
                    if set(elem.keys()).issubset(set(["name", "email"])):
                        maintainer = []
                        for key in ["name", "email"]:
                            if key in elem.keys():
                                maintainer.append(elem[key])
                        self.maintainers.append(maintainer)
                    else:
                        print(
                            "Maintainer dict should contain keys 'name' or 'email':",
                            str(elem),
                            file=sys.stderr,
                        )
                elif isinstance(elem, tuple) or isinstance(elem, list):
                    self.maintainers.append(list(elem))
                else:
                    print(
                        "Expected maintainer to be either string or dict elements:",
                        str(elem),
                        file=sys.stderr,
                    )

        if pyproject.license is not None and pyproject.license.text is not None:
            self.license = pyproject.license.text
        else:
            print("No license identifier found!", file=sys.stderr)

    @staticmethod
    def from_pyprojects(
        pyprojects: Union[PyProject, List[PyProject]],
    ) -> "SpackPyPkg | None":
        """Takes PyProject objects and converts them to a single SpackPyPkg.

        Metadata is extracted from the most recent PyProject version. Dependencies are
        collected for all versions and combined.
        """
        if isinstance(pyprojects, list) and len(pyprojects) == 0:
            print("Received an empty list.", file=sys.stderr)
            return None

        # make sure we are working with a list
        pyproject_list: List[PyProject] = (
            [pyprojects] if isinstance(pyprojects, PyProject) else pyprojects
        )

        # get the base pkg name
        name = pyproject_list[0].name

        # check that all have a version and the same package name
        for pyproject in pyproject_list:
            if pyproject.name != name or pyproject.version is None:
                print(
                    "All PyProject objects must have the same name and a specified",
                    "version.",
                    file=sys.stderr,
                )
                return None

        # sort by version number
        sorted_pyprojects = sorted(pyproject_list, key=lambda proj: proj.version)  # type: ignore

        pyproject_versions = [proj.version for proj in sorted_pyprojects]

        spackpkg = SpackPyPkg()

        # use the newest version to parse the metadata
        # TODO: some fields should be parsed and combined from all versions, e.g.
        # license
        most_recent = sorted_pyprojects[-1]
        spackpkg._get_metadata(most_recent)

        # load PyPI location for the spack package as well as a list of available
        # versions and hashes for the given pyprojects
        res = _get_pypi_filenames_hashes(name, pyproject_versions)

        if res is None:
            return None

        pypi_base, version_hash_list = res

        if not version_hash_list:
            print("No valid files found on PyPI.", file=sys.stderr)
            return None

        spackpkg.pypi = pypi_base
        spackpkg.versions = version_hash_list

        # load list of all versions from JSON API
        spackpkg.all_versions = lookup[spackpkg.pypi_name]

        # Conversion and simplification of dependencies summarized:
        # Collect unique dependencies (dependency spec, when spec) together with a list
        # of versions for which this dependency is required.
        # Condense the version list and add it to the when spec.
        # For each pair of dependencies (for the same package), make sure that there are
        # no conflicts/unsatisfiable requirements.

        # map each unique dependency (dependency spec, when spec) to a list of package
        # versions that have this dependency
        specs_to_versions: Dict[Tuple[spec.Spec, spec.Spec], List[pv.Version]] = {}

        # map dependencies to their dependency types (build, run, test, ...)
        specs_to_types: Dict[Tuple[spec.Spec, spec.Spec], Set[str]] = {}

        # convert and collect dependencies for each pyproject
        for pyproject in sorted_pyprojects:
            # build dependencies
            for r in pyproject.build_requires:
                # a single requirement can translate to multiple distinct dependencies
                spec_list = _convert_requirement(r)
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
                spec_list = _convert_requirement(r)
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
                    spec_list = _convert_requirement(r, from_extra=extra)
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
                spec_list = _convert_requirement(r)
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
        # convert versions to an equivalent condensed version list, and add this list to
        # the when spec. from there, build a complete list with all dependencies

        final_dependency_list: List[Tuple[spec.Spec, spec.Spec, str]] = []

        for (dep_spec, when_spec), vlist in specs_to_versions.items():
            types = specs_to_types[dep_spec, when_spec]

            # convert the set of types to a string as it would be displayed in the
            # package.py, e.g. '("build", "run")'.
            canonical_typestring = str(tuple(sorted(list(types)))).replace("'", '"')

            versions_condensed = external.condensed_version_list(
                vlist, spackpkg.all_versions
            )
            when_spec.versions = versions_condensed
            final_dependency_list.append((dep_spec, when_spec, canonical_typestring))

        # check for conflicts
        satisfiable = _check_dependency_satisfiability(final_dependency_list)

        if not satisfiable:
            print(
                f"Cannot convert package '{spackpkg.pypi_name}' due to uncompatible",
                "requirements.",
                file=sys.stderr,
            )
            return None

        # store dependencies by their type string (e.g. type=("build", "run"))
        for dep_spec, when_spec, typestring in final_dependency_list:
            if typestring not in spackpkg.dependencies_by_type:
                spackpkg.dependencies_by_type[typestring] = []

            spackpkg.dependencies_by_type[typestring].append((dep_spec, when_spec))

        return spackpkg

    def print_package(self, outfile=sys.stdout):
        """Format and write the package to 'outfile'.

        By default outfile=sys.stdout. The package can be written directly to a
        package.py file by supplying the corresponding file object.
        """
        print("Outputting package.py...\n")

        copyright = """\
# Copyright 2013-2024 Lawrence Livermore National Security, LLC and other
# Spack Project Developers. See the top-level COPYRIGHT file for details.
#
# SPDX-License-Identifier: (Apache-2.0 OR MIT)
"""

        print(copyright, file=outfile)

        print("from spack.package import *", file=outfile)
        print("", file=outfile)

        print(f"class {_name_to_class_name(self.name)}(PythonPackage):", file=outfile)

        if self.description is not None and len(self.description) > 0:
            print(f'    """{self.description}"""', file=outfile)
        else:
            print(
                '    """FIXME: Put a proper description of your package here."""',
                file=outfile,
            )

        print("", file=outfile)

        print(f'    pypi = "{self.pypi}"', file=outfile)

        print("", file=outfile)

        if self.license is not None and self.license != "":
            print(f'    license("{self.license}")', file=outfile)
            print("", file=outfile)

        if self.authors:
            print("    # Authors:", file=outfile)
            for author in self.authors:
                author_string = ", ".join(author)
                print(f"    # {author_string}", file=outfile)

            print("", file=outfile)

        if self.maintainers:
            print("    # Maintainers:", file=outfile)
            for maintainer in self.maintainers:
                maintainer_string = ", ".join(maintainer)
                print(f"    # {maintainer_string}", file=outfile)

            print("", file=outfile)

        for v, sha256 in self.versions:
            print(f'    version("{str(v)}", sha256="{sha256}")', file=outfile)

        print("", file=outfile)

        for v in self.variants:
            print(f'    variant("{v}", default=False)', file=outfile)

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
            sorted_dependencies = sorted(dependencies, key=_requirement_sort_key)

            print(f"    with default_args(type={dep_type}):", file=outfile)
            for dep_spec, when_spec in sorted_dependencies:
                print(
                    "        " + _format_dependency(dep_spec, when_spec), file=outfile
                )

            print("", file=outfile)

        print("", file=outfile)


if __name__ == "__main__":
    pyprojects = []
    for v in ["23.12.0", "23.12.1", "24.2.0", "24.4.0", "24.4.1", "24.4.2"]:
        py_pkg = PyProject.from_toml(
            f"example_pyprojects/black/pyproject{v}.toml", version=v
        )

        if py_pkg is None:
            print(
                f"Error: could not generate PyProject from pyproject{v}.toml",
                file=sys.stderr,
            )
            continue

        pyprojects.append(py_pkg)

    # convert to spack
    spack_pkg = SpackPyPkg.from_pyprojects(pyprojects)

    if spack_pkg is None:
        print("Error: could not generate spack package from PyProject", file=sys.stderr)
        exit()

    if USE_TEST_PREFIX:
        spack_pkg.name = TEST_PKG_PREFIX + spack_pkg.name

    print("spack pkg built")

    # print to console
    spack_pkg.print_package(outfile=sys.stdout)

    # or print to file.
    # TODO: allow tool to create a folder for the package and store package.py there
    # with open("package.py", "w+") as f:
    #    spack_pkg.print_package(outfile=f)

    # TODO: test new version with multiple pyprojects
