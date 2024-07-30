"""Core functionality for converting standard Python to Spack packages."""

from __future__ import annotations

import dataclasses
import logging
import pathlib
import sys
from typing import TextIO

from packaging import requirements, specifiers, version as pv
from spack import spec, version as sv
from spack.util import naming

from py2spack import conversion_tools, package_providers, pyproject_parsing


TEST_PKG_PREFIX = "test-"
USE_TEST_PREFIX = True
PRINT_PKG_TO_FILE = False
SPACK_CHECKSUM_HASHES = ["md5", "sha1", "sha224", "sha256", "sha384", "sha512"]


@dataclasses.dataclass(frozen=True)
class ParseError:
    """Error in parsing a pyproject.toml file.

    This error is not recoverable from, it means that the pyproject.toml file
    cannot be parsed or used at all (as opposed to a parsing.ConfigurationError,
    which only affects some portion of the pyproject.toml parsing).
    """

    msg: str
    file: str | None = None
    pkg_name: str | None = None
    pkg_version: str | None = None


def _format_dependency(
    dependency_spec: spec.Spec,
    when_spec: spec.Spec,
    dep_types: list[str] | None = None,
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
    prefix = f'depends_on("{dependency_spec!s}"'

    when_str = ""
    if when_spec is not None and when_spec != spec.Spec():
        if when_spec.architecture:
            platform_str = f"platform={when_spec.platform}"
            when_spec.architecture = None
        else:
            platform_str = ""
        when_str_inner = f"{platform_str} {when_spec!s}".strip()
        when_str = f', when="{when_str_inner}"'

    type_str = ""
    if dep_types is not None:
        type_str_inner = '", "'.join(dep_types)
        type_str = f', type=("{type_str_inner}")'

    return f"{prefix}{when_str}{type_str})"


def _check_dependency_satisfiability(
    dependency_list: list[tuple[spec.Spec, spec.Spec, str]],
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
    # TODO @davhofer: refactor, return list of conflicts
    sat: bool = True

    dependency_names = list({dep[0].name for dep in dependency_list if dep[0].name is not None})

    for name in dependency_names:
        pkg_dependencies = [dep for dep in dependency_list if dep[0].name == name]

        for i in range(len(pkg_dependencies)):
            for j in range(i + 1, len(pkg_dependencies)):
                dep1, when1, _ = pkg_dependencies[i]
                dep2, when2, _ = pkg_dependencies[j]

                if when1.intersects(when2) and (not dep1.intersects(dep2)):
                    sat = False
                    # TODO @davhofer: should conflicts be collected and returned instead
                    # of printed to console?
                    msg = (
                        "uncompatible requirements for dependency "
                        f"'{name}'!\nRequirement 1: {dep1!s}; when-spec: "
                        f"{when1!s}\nRequirement 2: {dep2!s}; when-spec:"
                        f" {when2!s}"
                    )
                    logging.warning(msg)
    return sat


def _people_to_strings(
    parsed_people: list[tuple[str | None, str | None]],
) -> list[str]:
    """Convert 'authors' or 'maintainers' lists to strings."""
    people: list[str] = []

    for p0, p1 in parsed_people:
        if p0 is None and p1 is None:
            continue
        if isinstance(p1, str):
            people.append(p1)
        elif isinstance(p0, str):
            people.append(p0)
        else:
            people.append(f"{p0}, {p1}")

    return people


@dataclasses.dataclass
class PyProject:
    """A class to represent a pyproject.toml file.

    Contains all fields which are present in METADATA, plus additional ones only
    found in pyproject.toml. E.g. build-backend, build dependencies.
    """

    name: str = ""
    tool: dict = dataclasses.field(default_factory=dict)
    build_backend: str | None = None
    build_requires: list[requirements.Requirement] = dataclasses.field(default_factory=list)
    dynamic: list[str] = dataclasses.field(default_factory=list)
    version: pv.Version = dataclasses.field(default=pv.Version("0"))
    description: str | None = None
    requires_python: specifiers.SpecifierSet | None = None
    license: str | None = None
    authors: list[str] = dataclasses.field(default_factory=list)
    maintainers: list[str] = dataclasses.field(default_factory=list)
    dependencies: list[requirements.Requirement] = dataclasses.field(default_factory=list)
    optional_dependencies: dict[str, list[requirements.Requirement]] = dataclasses.field(
        default_factory=dict
    )
    homepage: str | None = None
    metadata_errors: list[pyproject_parsing.ConfigurationError] = dataclasses.field(
        default_factory=list
    )
    dependency_errors: list[pyproject_parsing.ConfigurationError] = dataclasses.field(
        default_factory=list
    )

    @classmethod
    def from_toml(
        cls, file_content: dict, name: str, version: pv.Version
    ) -> PyProject | ParseError:
        """Create a PyProject instance from a pyproject.toml file.

        The version corresponding to the pyproject.toml file should be known
        a-priori and should be passed here as a string argument. Alternatively,
        it can be read from the pyproject.toml file if it is specified
        explicitly there.

        Parameters:
            path: The path to the toml file or data (dict) extracted from toml.
            version: The version of the package which the pyproject.toml
            corresponds to.

        Returns:
            A PyProject instance.
        """
        pyproject = PyProject()
        fetcher = pyproject_parsing.DataFetcher(file_content)

        if "project" not in fetcher:
            return ParseError(
                'Section "project" missing in pyproject.toml, skipping file',
                pkg_name=name,
                pkg_version=str(version),
            )

        if not name or not isinstance(name, str):
            return ParseError("'name' string is required", pkg_name=name, pkg_version=str(version))

        if not version or not isinstance(version, pv.Version):
            return ParseError(
                "'version' is required and must be of type " "requirements.version.Version",
                pkg_name=name,
                pkg_version=str(version),
            )

        # normalize the name
        pyproject.name = naming.simplify_name(name)

        pyproject.version = version

        # parse metadata
        # ConfigurationErrors in metadata fields will simply be ignored
        pyproject._load_metadata(fetcher)

        # parse build system
        pyproject._load_build_system(fetcher)

        # parse all dependencies
        pyproject._load_dependencies(fetcher)

        return pyproject

    def _load_metadata(self, fetcher: pyproject_parsing.DataFetcher) -> None:
        description = fetcher.get_str("project.description")
        if isinstance(description, pyproject_parsing.ConfigurationError):
            self.metadata_errors.append(description)
        else:
            self.description = description

        homepage = fetcher.get_homepage()
        if isinstance(homepage, pyproject_parsing.ConfigurationError):
            self.metadata_errors.append(homepage)
        else:
            self.homepage = homepage

        authors = fetcher.get_people("project.authors")
        if isinstance(authors, pyproject_parsing.ConfigurationError):
            self.metadata_errors.append(authors)
        else:
            self.authors = _people_to_strings(authors)

        maintainers = fetcher.get_people("project.maintainers")
        if isinstance(maintainers, pyproject_parsing.ConfigurationError):
            self.metadata_errors.append(maintainers)
        else:
            self.maintainers = _people_to_strings(maintainers)

        lic = fetcher.get_license()
        if isinstance(lic, pyproject_parsing.ConfigurationError):
            self.metadata_errors.append(lic)
        else:
            self.license = lic

    def _load_build_system(self, fetcher: pyproject_parsing.DataFetcher) -> None:
        build_req_result = fetcher.get_build_requires()
        if isinstance(build_req_result, pyproject_parsing.ConfigurationError):
            self.dependency_errors.append(build_req_result)
        else:
            dependencies, dependency_errors = build_req_result
            self.build_requires = dependencies
            self.dependency_errors.extend(dependency_errors)

        build_backend_result = fetcher.get_build_backend()
        if isinstance(build_backend_result, pyproject_parsing.ConfigurationError):
            self.metadata_errors.append(build_backend_result)
        else:
            self.build_backend = build_backend_result

    def _load_dependencies(self, fetcher: pyproject_parsing.DataFetcher) -> None:
        requires_python = fetcher.get_requires_python()
        if isinstance(requires_python, pyproject_parsing.ConfigurationError):
            self.dependency_errors.append(requires_python)
        else:
            self.requires_python = requires_python

        dep_result = fetcher.get_dependencies()
        if isinstance(dep_result, pyproject_parsing.ConfigurationError):
            self.dependency_errors.append(dep_result)
        else:
            dependencies, errors = dep_result
            self.dependencies = dependencies
            self.dependency_errors.extend(errors)

        opt_dep_result = fetcher.get_optional_dependencies()
        if isinstance(opt_dep_result, pyproject_parsing.ConfigurationError):
            self.dependency_errors.append(opt_dep_result)
        else:
            opt_dependencies, errors = opt_dep_result
            self.optional_dependencies = opt_dependencies
            self.dependency_errors.extend(errors)


@dataclasses.dataclass
class SpackPyPkg:
    """Class representing a Spack PythonPackage object.

    Instances are created directly from PyProject objects, by converting
    PyProject fields and semantics to their Spack equivalents (where possible).
    """

    _name: str = ""
    _pypi_name: str = ""
    _description: str | None = None
    _pypi: str = ""
    _versions_with_checksum: list[tuple[sv.Version, str, str]] = dataclasses.field(
        default_factory=list
    )
    _versions_missing_checksum: list[sv.Version] = dataclasses.field(default_factory=list)
    _all_versions: list[pv.Version] = dataclasses.field(default_factory=list)
    _variants: set[str] = dataclasses.field(default_factory=set)
    _maintainers: list[str] = dataclasses.field(default_factory=list)
    _authors: list[str] = dataclasses.field(default_factory=list)
    _license: str | None = None
    _homepage: str | None = None
    _dependencies_by_type: dict[str, list[tuple[spec.Spec, spec.Spec]]] = dataclasses.field(
        default_factory=dict
    )
    _file_parse_errors: list[tuple[str, ParseError]] = dataclasses.field(default_factory=list)
    _metadata_parse_errors: dict[str, list[pyproject_parsing.ConfigurationError]] = (
        dataclasses.field(default_factory=dict)
    )
    _dependency_parse_errors: dict[str, list[pyproject_parsing.ConfigurationError]] = (
        dataclasses.field(default_factory=dict)
    )
    _dependency_conversion_errors: dict[str, list[conversion_tools.ConversionError]] = (
        dataclasses.field(default_factory=dict)
    )
    # map each unique dependency (dependency spec, when spec) to a
    # list of package versions that have this dependency
    _specs_to_versions: dict[tuple[spec.Spec, spec.Spec], list[pv.Version]] = dataclasses.field(
        default_factory=dict
    )
    # map dependencies to their dependency types (build, run, test, ...)
    _specs_to_types: dict[tuple[spec.Spec, spec.Spec], set[str]] = dataclasses.field(
        default_factory=dict
    )

    def _metadata_from_pyproject(self, pyproject: PyProject) -> None:
        """Load and convert main metadata from given PyProject instance.

        Does not include pypi field, versions, or the dependencies.
        """
        self.pypi_name = pyproject.name
        self.name = conversion_tools.pkg_to_spack_name(pyproject.name)
        self.description = pyproject.description
        self.homepage = pyproject.homepage

        if pyproject.authors is not None:
            for elem in pyproject.authors:
                self._authors.append(elem)

        if pyproject.maintainers is not None:
            for elem in pyproject.maintainers:
                self._maintainers.append(elem)

        if pyproject.license:
            self.license = pyproject.license

    def _dependencies_from_pyproject(
        self, pyprojects: list[PyProject], provider: package_providers.PyProjectProvider
    ) -> bool:
        """Convert and combine dependencies from a list of pyprojects.

        Conversion and simplification of dependencies summarized:
        - Collect unique dependencies (dependency spec, when spec) together with
            a list of versions for which this dependency is required.
        - Condense the version list and add it to the when-spec of that
            dependency.
        - For each pair of dependencies (for the same package), make sure that
            there are no conflicts/unsatisfiable requirements, e.g. there is
            a dependency for pkg version < 4 and pkg version >= 4.2 at the same
            time.
        """
        # convert and collect dependencies for each pyproject
        for pyproject in pyprojects:
            # store dependency parse errors, will be displayed in package.py
            if pyproject.dependency_errors:
                self._dependency_parse_errors[str(pyproject.version)] = pyproject.dependency_errors

            # build dependencies
            for r in pyproject.build_requires:
                # a single requirement can translate to multiple distinct
                # dependencies
                self._requirement_from_pyproject(r, ["build"], pyproject.version, provider)

            # normal runtime dependencies
            for r in pyproject.dependencies:
                self._requirement_from_pyproject(r, ["build", "run"], pyproject.version, provider)

            # optional/variant dependencies
            for extra, deps in pyproject.optional_dependencies.items():
                self._variants.add(extra)
                for r in deps:
                    self._requirement_from_pyproject(
                        r, ["build", "run"], pyproject.version, provider, from_extra=extra
                    )

            # python dependencies
            if pyproject.requires_python is not None:
                r = requirements.Requirement("python")
                r.specifier = pyproject.requires_python

                self._requirement_from_pyproject(r, ["build", "run"], pyproject.version, provider)

        # now we have a list of versions for each requirement
        # convert versions to an equivalent condensed version list, and add this
        # list to the when spec. from there, build a complete list with all
        # dependencies

        final_dependency_list: list[tuple[spec.Spec, spec.Spec, str]] = []

        for (dep_spec, when_spec), vlist in self._specs_to_versions.items():
            types = self._specs_to_types[dep_spec, when_spec]

            # convert the set of types to a string as it would be displayed in
            # the package.py, e.g. '("build", "run")'.
            canonical_typestring = str(tuple(sorted(types))).replace("'", '"')

            versions_condensed = conversion_tools.condensed_version_list(vlist, self._all_versions)
            when_spec.versions = versions_condensed
            final_dependency_list.append((dep_spec, when_spec, canonical_typestring))

        # check for conflicts
        satisfiable = _check_dependency_satisfiability(final_dependency_list)

        if not satisfiable:
            logging.warning("Package '%s' contains incompatible requirements", self.pypi_name)

        # store dependencies by their type string (e.g. type=("build", "run"))
        for dep_spec, when_spec, typestring in final_dependency_list:
            if typestring not in self._dependencies_by_type:
                self._dependencies_by_type[typestring] = []

            self._dependencies_by_type[typestring].append((dep_spec, when_spec))

        return satisfiable

    def _requirement_from_pyproject(
        self,
        r: requirements.Requirement,
        dependency_types: list[str],
        pyproject_version: pv.Version,
        provider: package_providers.PyProjectProvider,
        from_extra: str | None = None,
    ) -> None:
        """Convert a requirement and store the package version with the result Specs."""
        spec_list = conversion_tools.convert_requirement(r, provider, from_extra=from_extra)

        if isinstance(spec_list, conversion_tools.ConversionError):
            if str(pyproject_version) not in self._dependency_conversion_errors:
                self._dependency_conversion_errors[str(pyproject_version)] = []
            self._dependency_conversion_errors[str(pyproject_version)].append(spec_list)
            return

        # for each spec, add the current version to the list of versions which have this
        # spec as a requirement
        for specs in spec_list:
            if specs not in self._specs_to_versions:
                self._specs_to_versions[specs] = []

            # add the current version to this dependency
            self._specs_to_versions[specs].append(pyproject_version)

            if specs not in self._specs_to_types:
                self._specs_to_types[specs] = set()

            # add build dependency
            for t in dependency_types:
                self._specs_to_types[specs].add(t)

    def print_pkg(self, outfile: TextIO = sys.stdout) -> None:  # noqa: C901, PLR0912, PLR0915
        """Format and write the package to 'outfile'.

        By default outfile=sys.stdout. The package can be written directly to a
        package.py file by supplying the corresponding file object.
        """
        logging.info("Outputting package.py...\n")

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
            txt = '    """FIXME: Put a proper description' ' of your package here."""'
            print(
                txt,
                file=outfile,
            )

        print("", file=outfile)

        if self.homepage:
            print(f'    homepage = "{self.homepage}"', file=outfile)
        else:
            print("    # FIXME: add homepage", file=outfile)
            print('    # homepage = ""', file=outfile)

        print(f'    pypi = "{self._pypi}"', file=outfile)

        print("", file=outfile)

        if self.license:
            print(f'    license("{self.license}")', file=outfile)
        else:
            print("    # FIXME: add license", file=outfile)

        print("", file=outfile)

        print("    # FIXME: add github names for maintainers", file=outfile)
        if self._authors:
            print("    # Authors:", file=outfile)
            for author in self._authors:
                print(f"    # {author}", file=outfile)

            print("", file=outfile)

        if self._maintainers:
            print("    # Maintainers:", file=outfile)
            for maintainer in self._maintainers:
                print(f"    # {maintainer}", file=outfile)

            print("", file=outfile)

        for v, hash_type, hash_value in self._versions_with_checksum:
            print(f'    version("{v!s}", {hash_type}="{hash_value}")', file=outfile)

        if self._versions_missing_checksum:
            print("", file=outfile)
            print("    # FIXME: add hashes/checksums for the following versions", file=outfile)
            for v in self._versions_missing_checksum:
                print(f'    version("{v!s}")', file=outfile)

        print("", file=outfile)

        # fix-me for unparsed versions
        if self._file_parse_errors:
            txt = (
                "    # FIXME: the pyproject.toml files for the following "
                "versions could not be parsed"
            )
            print(
                txt,
                file=outfile,
            )
            for v, p_err in self._file_parse_errors:
                print(f"    # version {v!s}: {p_err.msg}", file=outfile)

            print("", file=outfile)

        for v in self._variants:
            print(f'    variant("{v}", default=False)', file=outfile)

        print("", file=outfile)

        if self._dependency_parse_errors:
            txt = "    # FIXME: the following dependencies could not be parsed"
            print(
                txt,
                file=outfile,
            )
            for v, cfg_errs in self._dependency_parse_errors.items():
                print(f"    # version {v!s}:", file=outfile)
                for cfg_err in cfg_errs:
                    print(f"    #    {cfg_err.msg}", file=outfile)

            print("", file=outfile)

        if self._dependency_conversion_errors:
            txt = (
                "    # FIXME: the following dependencies could be parsed but "
                "not converted to spack"
            )
            print(
                txt,
                file=outfile,
            )
            for v, cnv_errs in self._dependency_conversion_errors.items():
                print(f"    # version {v!s}:", file=outfile)
                for cnv_err in cnv_errs:
                    print(f"    #    {cnv_err.msg}", file=outfile)

            print("", file=outfile)

        # custom key for sorting requirements in package.py:
        # looks like (is_python, has_variant, pkg_name, pkg_version_list,
        # variant_string)
        def _requirement_sort_key(
            req: tuple[spec.Spec, spec.Spec],
        ) -> tuple[int, int, str, sv.VersionList, str]:
            """Helper function for sorting requirements in the package.py."""
            dep, when = req
            # != because we want python to come first
            is_python = int(dep.name != "python")
            has_variant = int(len(str(when.variants)) > 0)
            pkg_name = dep.name
            pkg_version = dep.versions
            variant = str(when.variants)
            return (is_python, has_variant, pkg_name, pkg_version, variant)

        for dep_type in list(self._dependencies_by_type.keys()):
            dependencies = self._dependencies_by_type[dep_type]
            sorted_dependencies = sorted(dependencies, key=_requirement_sort_key)

            print(f"    with default_args(type={dep_type}):", file=outfile)
            for dep_spec, when_spec in sorted_dependencies:
                print(
                    "        " + _format_dependency(dep_spec, when_spec),
                    file=outfile,
                )

            print("", file=outfile)

        print("", file=outfile)


def convert_pkg(
    name: str, provider: package_providers.PyProjectProvider, last_n_versions: int = 20
) -> SpackPyPkg | None:
    """Convert a PyPI package to a Spack package.py."""
    # TODO @davhofer: refactor, handle outputting directly here
    # download available versions through provider (pypi, github)
    versions = provider.get_versions(name)
    if isinstance(versions, package_providers.PyProjectProviderQueryError):
        logging.warning("No valid versions found by provider %s", str(provider))
        return None

    # for each version, parse pyproject.toml
    pyprojects = []
    for v in versions:
        pyproject_dict = provider.get_pyproject(name, v)
        if isinstance(pyproject_dict, package_providers.PyProjectProviderQueryError):
            logging.warning(
                "Unable to get pyproject.toml for %s version %s: %s",
                name,
                str(v),
                str(pyproject_dict),
            )
            continue

        pyproject = PyProject.from_toml(pyproject_dict, name, v)
        if isinstance(pyproject, ParseError):
            logging.warning(
                "Unable to parse pyproject.toml for %s version %s: %s", name, str(v), str(pyproject)
            )
            continue

        pyprojects.append(pyproject)

    if not len(pyprojects):
        logging.warning("Conversion for %s failed, no valid pyproject.tomls found", name)
        return None

    if last_n_versions != -1:
        pyprojects = pyprojects[-last_n_versions:]

    # convert to spack
    spackpkg = SpackPyPkg()
    spackpkg._all_versions = versions

    if isinstance(provider, package_providers.PyPIProvider):
        spackpkg._pypi = provider.get_pypi_package_base(name)

    # get metadata from most recent version
    spackpkg._metadata_from_pyproject(pyprojects[-1])

    # get parsed versions with hashes (for display in package.py)
    # reverse order s.t. newest version is on top in package.py
    for p in reversed(pyprojects):
        spack_version = conversion_tools.packaging_to_spack_version(p.version)
        hashdict = provider.get_sdist_hash(name, p.version)
        if isinstance(hashdict, dict) and hashdict:
            hash_key, hash_value = next(iter(hashdict.items()))

            if hash_key in SPACK_CHECKSUM_HASHES:
                spackpkg._versions_with_checksum.append((spack_version, hash_key, hash_value))
                continue

        spackpkg._versions_missing_checksum.append(spack_version)

    # convert all dependencies (for the selected versions)
    spackpkg._dependencies_from_pyproject(pyprojects, provider)

    return spackpkg


if __name__ == "__main__":
    provider = package_providers.PyPIProvider()  # type: ignore[abstract]
    # Explanation of ignore: PyProjectProvider protocol requires the __hash__() method
    # to be implemented, which is done by the @dataclass decorator for PyPIProvider (but
    # mypy does not detect this)

    # convert to spack
    spack_pkg = convert_pkg("black", provider, last_n_versions=20)

    if spack_pkg is None:
        logging.warning("Could not generate spack package from PyProject")
        sys.exit()

    if USE_TEST_PREFIX:
        spack_pkg.name = TEST_PKG_PREFIX + spack_pkg.name

    logging.info("spack pkg built")

    if PRINT_PKG_TO_FILE:
        # print to file.
        out_path = pathlib.Path("output/package.py")
        with out_path.open("w+") as f:
            spack_pkg.print_pkg(outfile=f)
    else:
        # print to console
        spack_pkg.print_pkg(outfile=sys.stdout)
