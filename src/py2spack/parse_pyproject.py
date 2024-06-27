"""Module for parsing pyproject.toml files and converting them to Spack package.py files."""

import sys
from typing import Dict, List, Optional, Tuple, Union

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


def _pkg_to_spack_name(name: str) -> str:
    """Convert PyPI package name to Spack python package name."""
    spack_name = external.normalized_name(name)
    if USE_SPACK_PREFIX and spack_name != "python":
        # in general, if the package name already contains the "py-" prefix, we don't want to add it again
        # exception: 3 existing packages on spack with double "py-" prefix
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

        print("Marker eval:", str(marker_eval))

        if marker_eval is False:
            print("Marker is statically false, skip this requirement.")
            return []

        elif marker_eval is True:
            print("Marker is statically true, don't need to include in when_spec.")

        else:
            if isinstance(marker_eval, list):
                # replace empty when spec with marker specs
                when_spec_list = marker_eval

    if r.extras is not None:
        for extra in r.extras:
            requirement_spec.constrain(spec.Spec(f"+{extra}"))

    if r.specifier is not None:
        vlist = external.pkg_specifier_set_to_version_list(r.name, r.specifier, lookup)

        # TODO: how to handle the case when version list is empty, i.e. no matching versions found?
        if not vlist:
            req_string = str(r)
            if from_extra:
                req_string += " from extra '" + from_extra + "'"
            raise ValueError(
                f"Could not resolve dependency {req_string}: No matching versions for '{r.name}' found!"
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


class PyProject:
    """
    A class to represent a pyproject.toml file. Contains all fields which are
    present in METADATA, plus additional ones only found in pyproject.toml.
    E.g. build-backend, build dependencies
    """

    def __init__(self):
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
        """
        Create a PyProject instance from a pyproject.toml file.

        The version corresponding to the pyproject.toml file should be known a-priori and
        should be passed here as a string argument. Alternatively, it can be read from the
        pyproject.toml file if it is specified explicitly there.

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

        # TODO: handling the version, make sure we have the version of the current project
        # NOTE: in general, since we have downloaded and are parsing the pyproject.toml of a specific version,
        # we should know the version number a-priori. In this case it should be passed as a string argument to
        # the "from_toml(..)" method.
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
        # for example poetry could use "tool.poetry.dependencies" to specify dependencies

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
                # for each license classifier, split by "::" and take the last substring (and strip unnecessary whitespace)
                licenses = list(
                    map(lambda x: x.split("::")[-1].strip(), license_classifiers)
                )
                if len(licenses) > 0:
                    # TODO: can we decide purely from classifiers whether AND or OR? AND is more restrictive => be safe
                    license_txt = " AND ".join(licenses)
                    pyproject.license = py_metadata.License(text=license_txt, file=None)

        # manual checking of license format & text
        if pyproject.license is not None:
            if pyproject.license.text is not None and len(pyproject.license.text) > 200:
                print(
                    "License text appears to be full license content instead of license identifier. Please double check and add license identifier manually to package.py file.",
                    file=sys.stderr,
                )
                pyproject.license = None
            elif pyproject.license.text is None and pyproject.license.file is not None:
                print(
                    "License is supplied as a file. This is not supported, please add license identifier manually to package.py file.",
                    file=sys.stderr,
                )

        return pyproject

    @staticmethod
    def from_wheel(path: str):
        """TODO: not implemented"""
        pass

    def to_spack_pkg(self) -> "SpackPyPkg | None":
        """Convert this PyProject instance to a SpackPyPkg instance.

        Queries the PyPI JSON API in order to get information on available versions, archive
        file extensions, and file hashes.
        """
        spackpkg = SpackPyPkg()
        spackpkg.name = _pkg_to_spack_name(self.name)
        spackpkg.pypi_name = self.name

        spackpkg.description = self.description

        r = requests.get(
            f"https://pypi.org/simple/{self.name}/",
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
                    f"Package {self.name} not found on PyPI...",
                    file=sys.stderr,
                )
            return None

        files = r.json()["files"]
        non_wheels = list(filter(lambda f: not f["filename"].endswith(".whl"), files))

        if len(non_wheels) == 0:
            print(
                "No archive files found, only wheels!\nWheel file parsing not supported yet...",
                file=sys.stderr,
            )
            return None

        # TODO: use different approach to filename parsing?
        spackpkg.archive_extension = _get_archive_extension(non_wheels[-1]["filename"])
        if spackpkg.archive_extension is None:
            print(
                "No archive file extension recognized!",
                file=sys.stderr,
            )
            return None

        filename = f"{self.name}-{self.version}{spackpkg.archive_extension}"

        matching_files = list(filter(lambda f: f["filename"] == filename, non_wheels))

        if len(matching_files) == 0:
            print(f"No file on PyPI matches filename '{filename}'!", file=sys.stderr)
            return None

        spackpkg.pypi = f"{self.name}/{filename}"

        file = matching_files[0]
        sha256 = file["hashes"]["sha256"]

        if self.version is not None:
            spack_version = external.packaging_to_spack_version(self.version)
            spackpkg.versions.append((spack_version, sha256))

        for r in self.build_requires:
            spec_list = _convert_requirement(r)
            for specs in spec_list:
                spackpkg.build_dependencies.append(specs)

        for r in self.dependencies:
            spec_list = _convert_requirement(r)
            for specs in spec_list:
                spackpkg.runtime_dependencies.append(specs)

        for extra, deps in self.optional_dependencies.items():
            spackpkg.variants.append(extra)
            for r in deps:
                spec_list = _convert_requirement(r, from_extra=extra)
                for specs in spec_list:
                    spackpkg.variant_dependencies.append(specs)

        if self.requires_python is not None:
            r = requirements.Requirement("python")
            r.specifier = self.requires_python
            spec_list = _convert_requirement(r)
            for specs in spec_list:
                spackpkg.python_dependencies.append(specs)

        if self.authors is not None:
            for elem in self.authors:
                if isinstance(elem, str):
                    spackpkg.authors.append([elem])
                elif isinstance(elem, dict):
                    if set(elem.keys()).issubset(set(["name", "email"])):
                        author = []
                        for key in ["name", "email"]:
                            if key in elem.keys():
                                author.append(elem[key])
                        spackpkg.authors.append(author)
                    else:
                        print(
                            f"Expected author dict to contain keys 'name' or 'email': {elem}",
                            file=sys.stderr,
                        )
                elif isinstance(elem, tuple) or isinstance(elem, list):
                    spackpkg.authors.append(list(elem))
                else:
                    print(
                        f"Expected authors to be either string or dict elements: {elem}",
                        file=sys.stderr,
                    )

        if self.maintainers is not None:
            for elem in self.maintainers:
                if isinstance(elem, str):
                    spackpkg.maintainers.append([elem])
                elif isinstance(elem, dict):
                    if set(elem.keys()).issubset(set(["name", "email"])):
                        maintainer = []
                        for key in ["name", "email"]:
                            if key in elem.keys():
                                maintainer.append(elem[key])
                        spackpkg.maintainers.append(maintainer)
                    else:
                        print(
                            f"Expected maintainer dict to contain keys 'name' or 'email': {elem}",
                            file=sys.stderr,
                        )
                elif isinstance(elem, tuple) or isinstance(elem, list):
                    spackpkg.maintainers.append(list(elem))
                else:
                    print(
                        f"Expected maintainer to be either string or dict elements: {elem}",
                        file=sys.stderr,
                    )

        if self.license is not None and self.license.text is not None:
            spackpkg.license = self.license.text
        else:
            print("No license identifier found!", file=sys.stderr)

        return spackpkg


class SpackPyPkg:
    """Class representing a Spack PythonPackage object.

    Instances are created directly from PyProject objects, by converting PyProject fields and
    semantics to their Spack equivalents (where possible).
    """

    def __init__(self):
        self.name: str = ""
        self.pypi_name: str = ""
        self.description: Optional[str] = None
        self.pypi: str = ""
        self.versions: List[Tuple[sv.Version, str]] = []
        self.build_dependencies: List[Tuple[spec.Spec, spec.Spec]] = []
        self.runtime_dependencies: List[Tuple[spec.Spec, spec.Spec]] = []
        self.variant_dependencies: List[Tuple[spec.Spec, spec.Spec]] = []
        self.variants: List[str] = []
        self.python_dependencies: List[Tuple[spec.Spec, spec.Spec]] = []
        self.maintainers: List[List[str]] = []
        self.authors: List[List[str]] = []
        self.license: Optional[str] = None

        self.archive_extension: Optional[str] = None

        # import_modules = []

    @staticmethod
    def from_pyproject(pyproject: Union[PyProject, List[PyProject]]) -> "SpackPyPkg":
        """TODO: remove PyProject.to_spack_pkg and put it here (?). Takes a single pyproject or a list of them (need to be all the same pkg but different versions) and convert them to a single SpackPyPkg."""
        # TODO: convert metadata from the most recent pkg
        # convert dependencies from all versions separately
        # condense and simplify dependencies

        # for each individual pyproject, can create separate spack conversion. for dependencies we can add the current version in when spec
        # remove by setting .versions = VersionList(":")

        # or could do a dict style approach:
        # map spack version, pkg name, => to dependency (dependency spec and when spec)
        # d[pkg_name, pkg_version] = (dependency_spec, when_spec)
        # later we have to group by pkg_name, dependency_spec and when_spec... does this data structure make sense?
        # maybe better: map name, dep spec, when spec ==> list of versions?
        # then combine this list of versions
        # actually can omit name since it is included in dependency spec

        # when creating the version ranges, make sure that there is no pkg version that fits in two different ones
        # (for the same when spec... bc i guess we can have when="@4.2" and when="@4.2 +extra") ... ? for the same dependency package??
        return SpackPyPkg()

    def print_package(self, outfile=sys.stdout):
        """Format and write the package to 'outfile'.

        By default outfile=sys.stdout. The package can be written directly to a package.py file
        by supplying the corresponding file object.
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

        if self.build_dependencies:
            print('    with default_args(type="build"):', file=outfile)
            for dep_spec, when_spec in self.build_dependencies:
                print(
                    "        " + _format_dependency(dep_spec, when_spec), file=outfile
                )

            print("", file=outfile)

        if (
            self.python_dependencies
            + self.runtime_dependencies
            + self.variant_dependencies
        ):
            print('    with default_args(type=("build", "run")):', file=outfile)

            for dep_spec, when_spec in self.python_dependencies:
                print(
                    "        " + _format_dependency(dep_spec, when_spec), file=outfile
                )

            for dep_spec, when_spec in self.runtime_dependencies:
                print(
                    "        " + _format_dependency(dep_spec, when_spec), file=outfile
                )

            print("", file=outfile)

            for dep_spec, when_spec in self.variant_dependencies:
                print(
                    "        " + _format_dependency(dep_spec, when_spec), file=outfile
                )

        print("", file=outfile)


FILE_PATH = "example_black24.3.0_pyproject.toml"

if __name__ == "__main__":
    py_pkg = PyProject.from_toml(FILE_PATH, version="24.3.0")

    if py_pkg is None:
        print("Error: could not generate PyProject from .toml", file=sys.stderr)
        exit()

    spack_pkg = py_pkg.to_spack_pkg()

    if spack_pkg is None:
        print("Error: could not generate spack package from PyProject", file=sys.stderr)
        exit()

    if USE_TEST_PREFIX:
        spack_pkg.name = TEST_PKG_PREFIX + spack_pkg.name

    print("spack pkg built")

    spack_pkg.print_package(outfile=sys.stdout)
    # with open("package.py", "w+") as f:
    #    spack_pkg.print_package(outfile=f)
