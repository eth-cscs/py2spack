"""Module for parsing pyproject.toml files and converting them to Spack package.py files.
"""
from typing import Optional, List, Dict, Tuple

import sys
import re
import requests
from packaging import requirements
from packaging import specifiers
from packaging import markers
import packaging.version as pv
import tomli # type: ignore
import pyproject_metadata as py_metadata # type: ignore , pylint: disable=import-error,
from spack import spec # type: ignore , pylint: disable=import-error
import spack.version as sv # type: ignore , pylint: disable=import-error


class PyProject:
    """
    A class to represent a pyproject.toml file. Contains all fields which are
    present in METADATA, plus additional ones only found in pyproject.toml.
    E.g. build-backend, build dependencies
    """

    def __init__(self):
        self.name: str = ""

        # TODO: check types of all the fields
        self.tool: Dict = dict()
        self.build_backend: Optional[str] = None
        self.build_requires: List[requirements.Requirement] = []
        self.metadata: Optional[py_metadata.StandardMetadata] = None
        self.dynamic: List[str] = []
        # TODO: this is technically required, just it could also be dynamic
        self.version: Optional[str] = None
        self.description: Optional[str] = None
        self.readme: Optional[str] = None
        self.requires_python: Optional[str] = None
        self.license: Optional[str] = None
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
    def from_toml(path: str, version: str = "") -> 'PyProject' | None:
        """
        Create a PyProject instance from a pyproject.toml file. 
        
        If the version cannot be read/parsed from the file, it needs to be supplied here.

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
            raise RuntimeError(f"Failed to read .toml file: {e}")

        pyproject = PyProject()

        # TODO: parse build system
        # if backend is poetry things are a bit different
        # flit older versions also different

        # TODO: wheels is also different

        # parse pyproject metadata
        pyproject.metadata = py_metadata.StandardMetadata.from_pyproject(toml_data)

        # parse build table of pyproject.toml
        pyproject.build_backend = toml_data["build-system"]["build-backend"]
        build_dependencies = toml_data["build-system"]["requires"]
        pyproject.build_requires = [requirements.Requirement(req) for req in build_dependencies]

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
        pyproject.name = _normalized_name(pyproject.name)

        pyproject.tool = toml_data.get("tool", {})

        # TODO: handling the version, make sure we have the version of the current project
        if version:
            pyproject.version = version

        # TODO:
        if pyproject.version is None or pyproject.version == "":
            print("ERROR: no version for pyproject.toml found!", file=sys.stderr)
            return None

        # TODO: build-backend-specific parsing of tool and other tables,
        # e.g. for additional dependencies
        # for example poetry could use "tool.poetry.dependencies" to specify dependencies

        return pyproject

    @staticmethod
    def from_wheel(path: str):
        """TODO: not implemented"""
        pass

    def to_spack_pkg(self) -> 'SpackPyPkg' | None:
        """Convert this PyProject instance to SpackPyPkg instance.

        Queries the PyPI JSON API in order to get information on archive file extensions, 
        file hashes, and available versions.
        """
        spackpkg = SpackPyPkg()
        spackpkg.name = _pkg_to_spack_name(self.name)
        spackpkg.pypi_name = self.name

        spackpkg.description = self.description

        r = requests.get(f"https://pypi.org/simple/{self.name}/",
                         headers={"Accept": "application/vnd.pypi.simple.v1+json"},
                         timeout=10)

        if r.status_code != 200:
            print(f"Error when querying json API. status code : {r.status_code}", file=sys.stderr)
            return None

        files = r.json()["files"]
        non_wheels = list(filter(lambda f: not f["filename"].endswith(".whl"), files))

        assert len(non_wheels) > 0

        spackpkg.archive_extension = _get_archive_extension(non_wheels[-1]["filename"])

        assert self.version is not None and self.version != ""

        filename = f"{self.name}-{self.version}{spackpkg.archive_extension}"

        matching_files = list(filter(lambda f: f["filename"] == filename, non_wheels))

        assert len(matching_files) == 1


        spackpkg.pypi = f"{self.name}/{filename}"

        file = matching_files[0]
        sha256 = file["hashes"]["sha256"]

        spackpkg.versions.append((self.version, sha256))


        spackpkg.build_dependencies = [_convert_requirement(r) for r in self.build_requires]

        spackpkg.runtime_dependencies = [_convert_requirement(r) for r in self.dependencies]

        for extra, deps in self.optional_dependencies.items():
            spackpkg.variants.append(extra)
            for r in deps:
                spackpkg.variant_dependencies.append(_convert_requirement(r, from_extra=extra))

        r = requirements.Requirement("python")
        r.specifier = self.requires_python

        spackpkg.python_dependencies.append(_convert_requirement(r))

        return spackpkg


class SpackPyPkg:
    """Class representing a Spack PythonPackage object.
    
    Instances are created directly from PyProject objects, by converting PyProject fields and 
    semantics to their Spack equivalents (where possible).
    """

    def __init__(self):
        self.name = ""
        self.pypi_name = ""
        self.description = ""
        self.pypi = ""
        self.versions = []
        self.build_dependencies = []
        self.runtime_dependencies = []
        self.variant_dependencies = []
        self.variants = []
        self.python_dependencies = []
        self.maintainers = []
        self.license = ""

        self.archive_extension = ""

        # import_modules = []



    def print_package(self, outfile=sys.stdout):
        """Format and write the package to 'outfile'.

        By default outfile=sys.stdout. The package can be written directly to a package.py file 
        by supplying the corresponding file object.
        """
        # TODO: copyright notice on top?

        print("from spack.package import *", file=outfile)
        print("", file=outfile)

        print(f"class {_name_to_class_name(self.name)}(PythonPackage):", file=outfile)

        if self.description is not None and len(self.description) > 0:
            print(f'    """{self.description}"""', file=outfile)
        else:
            print('    """FIXME: Put a proper description of your package here."""', file=outfile)

        print("", file=outfile)


        # TODO: homepage

        print(f'    pypi = "{self.pypi}"', file=outfile)

        print("", file=outfile)

        # TODO: licence

        # TODO: maintainers

        for v, sha256 in self.versions:
            print(f'    version("{v}", sha256="{sha256}")', file=outfile)

        print("", file=outfile)

        for v in self.variants:
            print(f'    variant("{v}", default=False)')

        print("", file=outfile)


        print('    with default_args(type="build"):', file=outfile)
        for dep_spec, when_spec in self.build_dependencies:
            print("        " + _format_dependency(dep_spec, when_spec), file=outfile)

        print("", file=outfile)

        print('    with default_args(type=("build", "run")):', file=outfile)

        for dep_spec, when_spec in self.python_dependencies:
            print("        " + _format_dependency(dep_spec, when_spec), file=outfile)

        for dep_spec, when_spec in self.runtime_dependencies + self.variant_dependencies:
            print("        " + _format_dependency(dep_spec, when_spec), file=outfile)




def _format_dependency(dependency_spec: spec.Spec, when_spec: spec.Spec,
                       dep_types: Optional[List[str]] = None) -> str:
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
        s += f', when="{str(when_spec)}"'

    if dep_types is not None:
        typestr = '", "'.join(dep_types)
        s += f', type=("{typestr}")'

    s += ")"

    return s


def _get_archive_extension(filename: str) -> str | None:
    if filename.endswith(".whl"):
        print("Supplied filename is a wheel file, please provide archive file!", file=sys.stderr)
        return ".whl"

    archive_formats = [".zip", ".tar", ".tar.gz", ".tar.bz2", ".rar", ".7z", ".gz", ".xz", ".bz2"]

    l = [ext for ext in archive_formats if filename.endswith(ext)]

    if len(l) == 0:
        print(f"No extension recognized for: {filename}!", file=sys.stderr)
        return None

    if len(l) == 1:
        return l[0]

    longest_matching_ext = max(l, key=len)
    return longest_matching_ext






## ----------------------------------------------------------------------------------------
# Code adapted from pypi-to-spack-package (Harmen Stoppels)

# TODO: document/comment this code
# TODO: check if everything works as expected

NAME_REGEX = re.compile(r"[-_.]+")

RE_LOCAL_SEPARATORS = re.compile(r"[\._-]")

KNOWN_PYTHON_VERSIONS = (
    (3, 6, 15),
    (3, 7, 17),
    (3, 8, 18),
    (3, 9, 18),
    (3, 10, 13),
    (3, 11, 7),
    (3, 12, 1),
    (3, 13, 0),
    (4, 0, 0),
)

evalled = dict()

def _normalized_name(name):
    return re.sub(NAME_REGEX, "-", name).lower()

def _acceptable_version(version: str) -> Optional[pv.Version]:
    """Maybe parse with packaging"""
    try:
        v = pv.parse(version)
        # do not support post releases of prereleases etc.
        if v.pre and (v.post or v.dev or v.local):
            return None
        return v
    except pv.InvalidVersion:
        return None

# TODO: handle errors in requests lookup
class JsonVersionsLookup:
    """
    Class for retrieving available versions of package from PyPI JSON API.

    Caches past requests.
    """
    def __init__(self):
        self.cache: Dict[str, List[pv.Version]] = {}

    def _query(self, name: str) -> List[pv.Version]:
        """Call JSON API.
        """
        r = requests.get(f"https://pypi.org/simple/{name}/",
                         headers={"Accept": "application/vnd.pypi.simple.v1+json"}, timeout=10)
        if r.status_code != 200:
            print(f"Json lookup error (pkg={name}): status code {r.status_code}", file=sys.stderr)
            return []
        versions = r.json()['versions']
        return sorted({vv for v in versions if (vv := _acceptable_version(v))})

    def _python_versions(self) -> List[pv.Version]:
        """Statically evaluate python versions.
        """
        return [
            pv.Version(f"{major}.{minor}.{patch}")
            for major, minor, patch in KNOWN_PYTHON_VERSIONS
            # for p in range(1, patch + 1)
        ]

    def __getitem__(self, name: str) -> List[pv.Version]:
        result = self.cache.get(name)
        if result is not None:
            return result
        if name == "python":
            result = self._python_versions()
        else:
            result = self._query(name)
        self.cache[name] = result
        return result


def _best_upperbound(curr: sv.StandardVersion, nxt: sv.StandardVersion) -> sv.StandardVersion:
    """Return the most general upperound that includes curr but not nxt. Invariant is that
    curr < nxt."""
    i = 0
    m = min(len(curr), len(nxt))
    while i < m and curr.version[0][i] == nxt.version[0][i]:
        i += 1
    if i == len(curr) < len(nxt):
        release, _ = curr.version
        release += (0,)  # one zero should be enough 1.2 and 1.2.0 are not distinct in packaging.
        seperators = (".",) * (len(release) - 1) + ("",)
        as_str = ".".join(str(x) for x in release)
        return sv.StandardVersion(as_str, (tuple(release), (sv.common.FINAL,)), seperators)
    elif i == m:
        return curr  # include pre-release of curr
    else:
        return curr.up_to(i + 1)


def _best_lowerbound(prev: sv.StandardVersion, curr: sv.StandardVersion) -> sv.StandardVersion:
    i = 0
    m = min(len(curr), len(prev))
    while i < m and curr.version[0][i] == prev.version[0][i]:
        i += 1
    if i + 1 >= len(curr):
        return curr
    else:
        return curr.up_to(i + 1)


def _packaging_to_spack_version(v: pv.Version) -> sv.StandardVersion:
    # TODO: better epoch support.
    release = []
    prerelease = (sv.common.FINAL,)
    if v.epoch > 0:
        print(f"warning: epoch {v} isn't really supported", file=sys.stderr)
        release.append(v.epoch)
    release.extend(v.release)
    separators = ["."] * (len(release) - 1)

    if v.pre is not None:
        tp, num = v.pre
        if tp == "a":
            prerelease = (sv.common.ALPHA, num)
        elif tp == "b":
            prerelease = (sv.common.BETA, num)
        elif tp == "rc":
            prerelease = (sv.common.RC, num)
        separators.extend(("-", ""))

        if v.post or v.dev or v.local:
            print(f"warning: ignoring post / dev / local version {v}", file=sys.stderr)

    else:
        if v.post is not None:
            release.extend((sv.version_types.VersionStrComponent("post"), v.post))
            separators.extend((".", ""))
        if v.dev is not None:  # dev is actually pre-release like, spack makes it a post-release.
            release.extend((sv.version_types.VersionStrComponent("dev"), v.dev))
            separators.extend((".", ""))
        if v.local is not None:
            local_bits = [
                int(i) if i.isnumeric() else sv.version_types.VersionStrComponent(i)
                for i in RE_LOCAL_SEPARATORS.split(v.local)
            ]
            release.extend(local_bits)
            separators.append("-")
            separators.extend("." for _ in range(len(local_bits) - 1))

    separators.append("")

    # Reconstruct a string.
    string = ""
    for i, rel in enumerate(release):
        string += f"{rel}{separators[i]}"
    if v.pre:
        string += f"{sv.common.PRERELEASE_TO_STRING[prerelease[0]]}{prerelease[1]}"

    spack_version = sv.StandardVersion(string, (tuple(release), tuple(prerelease)), separators)

    # print(f"packaging to spack version: {str(v)} -> {str(spack_version)}")

    return spack_version


def _condensed_version_list(
    _subset_of_versions: List[pv.Version], _all_versions: List[pv.Version]
) -> sv.VersionList:
    # Sort in Spack's order, which should in principle coincide with packaging's order, but may
    # not in unforseen edge cases.
    subset = sorted(_packaging_to_spack_version(v) for v in _subset_of_versions)
    all_spack = sorted(_packaging_to_spack_version(v) for v in _all_versions)

    # Find corresponding index
    i, j = all_spack.index(subset[0]) + 1, 1
    new_versions: List[sv.ClosedOpenRange] = []

    # If the first when entry corresponds to the first known version, use (-inf, ..] as lowerbound.
    if i == 1:
        lo = sv.StandardVersion.typemin()
    else:
        lo = _best_lowerbound(all_spack[i - 2], subset[0])

    while j < len(subset):
        if all_spack[i] != subset[j]:
            hi = _best_upperbound(subset[j - 1], all_spack[i])
            new_versions.append(sv.VersionRange(lo, hi))
            i = all_spack.index(subset[j])
            lo = _best_lowerbound(all_spack[i - 1], subset[j])
        i += 1
        j += 1

    # Similarly, if the last entry corresponds to the last known version,
    # assume the dependency continues to be used: [x, inf).
    if i == len(all_spack):
        hi = sv.StandardVersion.typemax()
    else:
        hi = _best_upperbound(subset[j - 1], all_spack[i])

    new_versions.append(sv.VersionRange(lo, hi))

    vlist = sv.VersionList(new_versions)

    print(f"built condensed version list: {str(vlist)}")
    return vlist


def _pkg_specifier_set_to_version_list(
    pkg: str, specifier_set: specifiers.SpecifierSet, version_lookup: JsonVersionsLookup
) -> sv.VersionList:
    print("pkg specifier to version list")
    key = (pkg, specifier_set)
    if key in evalled:
        return evalled[key]
    all_versions = version_lookup[pkg]
    matching = [s for s in all_versions if specifier_set.contains(s, prereleases=True)]
    result = sv.VersionList() if not matching else _condensed_version_list(matching, all_versions)
    evalled[key] = result
    return result


## ----------------------------------------------------------------------------------------

lookup = JsonVersionsLookup()

USE_SPACK_PREFIX = True

def _pkg_to_spack_name(name: str) -> str:
    """Convert PyPI package name to Spack python package name.
    """
    spack_name = name
    if USE_SPACK_PREFIX and name != "python":
        spack_name = "py-" + spack_name
    return spack_name

def _convert_requirement(r: requirements.Requirement, from_extra: Optional[str] = None
                         ) -> Tuple[spec.Spec, spec.Spec]:
    """Convert a packaging Requirement to its Spack equivalent.

    The Spack requirement consists of a main dependency Spec and "when" Spec 
    for conditions like variants or markers.

    Parameters:
        r: packaging requirement
        from_extra: If this requirement an optional requirement dependent on an 
        extra of the main package, supply the extra's name here.

    Returns:
        A tuple of (main_dependency_spec, when_spec).
    """

    assert r.name is not None

    spack_name = _pkg_to_spack_name(r.name)

    requirement_spec = spec.Spec(spack_name)

    when_spec = spec.Spec()
    if from_extra is not None:
        when_spec.constrain(spec.Spec(f"+{from_extra}"))

    if r.marker is not None:
        # TODO: handle markers!
        assert isinstance(r.marker, markers.Marker)

        marker_spec = _convert_marker(r.marker)
        when_spec.constrain(marker_spec)

    if r.extras is not None:

        assert isinstance(r.extras, set)

        for extra in r.extras:
            requirement_spec.constrain(spec.Spec(f"+{extra}"))

    if r.specifier is not None:

        assert isinstance(r.specifier, specifiers.SpecifierSet)

        vlist = _pkg_specifier_set_to_version_list(r.name, r.specifier, lookup)
        requirement_spec.versions = vlist

    return (requirement_spec, when_spec)


def _convert_marker(m: markers.Marker) -> spec.Spec:
    print("Markers not handled yet!", m, file=sys.stderr)
    return spec.Spec()



def _name_to_class_name(name: str) -> str:
    """Convert a package name to a canonical class name for package.py.
    """
    classname = ""
    # in case there would be both - and _ in name
    name = name.replace("_", "-")
    name_arr = name.split("-")
    for w in name_arr:
        classname += w.capitalize()

    return classname


FILE_PATH = "personal/black_pyproject.toml"

if __name__ == "__main__":
    py_pkg = PyProject.from_toml(FILE_PATH, version="24.3.0")

    spack_pkg = py_pkg.to_spack_pkg()

    spack_pkg.print_package()
