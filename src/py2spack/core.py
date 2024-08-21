"""Core functionality for converting standard Python to Spack packages."""

from __future__ import annotations

import dataclasses
import logging
import os
import pathlib
import subprocess
import sys
from typing import TextIO

from packaging import requirements, specifiers, version as pv
from spack import spec, version as sv
from spack.util import naming

from py2spack import conversion_tools, package_providers, pyproject_parsing


TEST_PKG_PREFIX = "test-"
USE_TEST_PREFIX = False
PRINT_PKG_TO_FILE = False
SPACK_CHECKSUM_HASHES = ["md5", "sha1", "sha224", "sha256", "sha384", "sha512"]


@dataclasses.dataclass(frozen=True)
class ParseError:
    """Error in parsing a pyproject.toml file.

    This error is not recoverable from, it means that the pyproject.toml file
    cannot be parsed or used at all (as opposed to a
    pyproject_parsing.ConfigurationError, which only affects some portion of the
    pyproject.toml parsing).
    """

    msg: str


@dataclasses.dataclass(frozen=True)
class DependencyConflictError:
    """Satisfiability conflict between two dependencies."""

    msg: str


def _format_types(types: set[str]) -> str:
    if len(types) == 1:
        t = next(iter(types))
        return f'"{t}"'

    return str(tuple(sorted(types))).replace("'", '"')


def _format_dependency(
    dependency_spec: spec.Spec,
    when_spec: spec.Spec,
    dep_types: set[str] | None = None,
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
    if dep_types is not None and dep_types:
        type_str_inner = _format_types(dep_types)
        type_str = f", type={type_str_inner}"

    return f"{prefix}{when_str}{type_str})"


def _find_dependency_satisfiability_conflicts(
    dependency_list: list[tuple[spec.Spec, spec.Spec, set[str]]],
) -> list[DependencyConflictError]:
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
    dependency_conflicts: list[DependencyConflictError] = []

    dependency_names = list({dep[0].name for dep in dependency_list if dep[0].name is not None})

    for name in dependency_names:
        pkg_dependencies = [dep for dep in dependency_list if dep[0].name == name]

        for i in range(len(pkg_dependencies)):
            for j in range(i + 1, len(pkg_dependencies)):
                dep1, when1, types1 = pkg_dependencies[i]
                dep2, when2, types2 = pkg_dependencies[j]

                if when1.intersects(when2) and (not dep1.intersects(dep2)):
                    dep_str1 = _format_dependency(dep1, when1, dep_types=types1)
                    dep_str2 = _format_dependency(dep2, when2, dep_types=types2)
                    dependency_conflicts.append(
                        DependencyConflictError(f"{dep_str1} and {dep_str2}")
                    )
    return dependency_conflicts


def _people_to_strings(
    parsed_people: list[tuple[str | None, str | None]],
) -> list[str]:
    """Convert 'authors' or 'maintainers' lists to strings."""
    people: list[str] = []

    for p0, p1 in parsed_people:
        if p0 is None and p1 is None:
            continue
        if isinstance(p1, str) and p0 is None:
            people.append(p1)
        elif isinstance(p0, str) and p1 is None:
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
    provider: package_providers.PyProjectProvider | None = None

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
            )

        if not name or not isinstance(name, str):
            return ParseError("'name' string is required")

        if not version or not isinstance(version, pv.Version):
            return ParseError(
                "'version' is required and must be of type " "requirements.version.Version",
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

    name: str = ""
    pypi_name: str = ""
    _description: str | None = None
    pypi: str = ""
    git: str = ""
    url: str = ""
    _versions_with_checksum: list[tuple[sv.Version, str, str]] = dataclasses.field(
        default_factory=list
    )
    _versions_missing_checksum: list[sv.Version] = dataclasses.field(default_factory=list)
    all_versions: list[pv.Version] = dataclasses.field(default_factory=list)
    num_converted_versions: int = 0
    _variants: set[str] = dataclasses.field(default_factory=set)
    _maintainers: list[str] = dataclasses.field(default_factory=list)
    _authors: list[str] = dataclasses.field(default_factory=list)
    _license: str | None = None
    _homepage: str | None = None
    # store all dependencies of the package (with their original name, not converted
    # to spack)
    original_dependencies: set[str] = dataclasses.field(default_factory=set)
    _dependencies_by_type: dict[str, list[tuple[spec.Spec, spec.Spec]]] = dataclasses.field(
        default_factory=dict
    )
    _file_parse_errors: list[tuple[str, ParseError]] = dataclasses.field(default_factory=list)
    _metadata_parse_errors: dict[str, list[pyproject_parsing.ConfigurationError]] = (
        dataclasses.field(default_factory=dict)
    )
    dependency_parse_errors: dict[str, list[pyproject_parsing.ConfigurationError]] = (
        dataclasses.field(default_factory=dict)
    )
    dependency_conversion_errors: dict[str, list[conversion_tools.ConversionError]] = (
        dataclasses.field(default_factory=dict)
    )
    dependency_conflict_errors: list[DependencyConflictError] = dataclasses.field(
        default_factory=list
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

    def _metadata_from_pyproject(self, pyproject: PyProject, use_test_prefix: bool = False) -> None:
        """Load and convert main metadata from given PyProject instance.

        Does not include pypi field, versions, or the dependencies.
        """
        self.pypi_name = pyproject.name
        self.name = conversion_tools.pkg_to_spack_name(
            pyproject.name, use_test_prefix=use_test_prefix
        )
        self._description = pyproject.description
        self._homepage = pyproject.homepage

        if pyproject.authors is not None:
            for elem in pyproject.authors:
                self._authors.append(elem)

        if pyproject.maintainers is not None:
            for elem in pyproject.maintainers:
                self._maintainers.append(elem)

        if pyproject.license:
            self._license = pyproject.license

    def _dependencies_from_pyprojects(
        self, pyprojects: list[PyProject], provider: package_providers.PyProjectProvider
    ) -> None:
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
                self.dependency_parse_errors[str(pyproject.version)] = pyproject.dependency_errors

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

        final_dependency_list: list[tuple[spec.Spec, spec.Spec, set[str]]] = []

        for (dep_spec, when_spec), vlist in self._specs_to_versions.items():
            types = self._specs_to_types[dep_spec, when_spec]

            versions_condensed = conversion_tools.condensed_version_list(vlist, self.all_versions)
            when_spec.versions = versions_condensed
            final_dependency_list.append((dep_spec, when_spec, types))

        # check for conflicts
        self.dependency_conflict_errors = _find_dependency_satisfiability_conflicts(
            final_dependency_list
        )

        if self.dependency_conflict_errors:
            logging.warning("Package '%s' contains incompatible requirements", self.pypi_name)

        # store dependencies by their type string (e.g. type=("build", "run"))
        for dep_spec, when_spec, types in final_dependency_list:
            # convert the set of types to a string as it would be displayed in
            # the package.py, e.g. '("build", "run")'.
            canonical_typestring = _format_types(types)

            if canonical_typestring not in self._dependencies_by_type:
                self._dependencies_by_type[canonical_typestring] = []

            self._dependencies_by_type[canonical_typestring].append((dep_spec, when_spec))

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
            if str(pyproject_version) not in self.dependency_conversion_errors:
                self.dependency_conversion_errors[str(pyproject_version)] = []
            self.dependency_conversion_errors[str(pyproject_version)].append(spec_list)
            return

        # store dependency name
        self.original_dependencies.add(r.name)

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

    def build_from_pyprojects(
        self,
        name: str,
        pyprojects: list[PyProject],
        pypi_provider: package_providers.PyPIProvider,
        use_test_prefix: bool = False,
    ) -> None:
        """Build the spack package from pyprojects."""
        # get metadata from most recent version
        self._metadata_from_pyproject(pyprojects[-1], use_test_prefix=use_test_prefix)

        self.num_converted_versions = len(pyprojects)

        # get parsed versions with hashes (for display in package.py)
        # pyprojects are already in reverse order,
        # s.t. newest version is on top in package.py
        for p in pyprojects:
            spack_version = conversion_tools.packaging_to_spack_version(p.version)

            if p.provider is not None:
                hashdict = p.provider.get_sdist_hash(name, p.version)

                if isinstance(hashdict, dict) and hashdict:
                    hash_key, hash_value = next(iter(hashdict.items()))

                    if hash_key in SPACK_CHECKSUM_HASHES:
                        self._versions_with_checksum.append((spack_version, hash_key, hash_value))
                        continue

            self._versions_missing_checksum.append(spack_version)

        # convert all dependencies (for the selected versions)
        self._dependencies_from_pyprojects(pyprojects, pypi_provider)

    def print_pkg(self, outfile: TextIO = sys.stdout) -> None:  # noqa: C901, PLR0912, PLR0915
        """Format and write the package to 'outfile'.

        By default outfile=sys.stdout. The package can be written directly to a
        package.py file by supplying the corresponding file object.
        """
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

        if self._description is not None and len(self._description) > 0:
            print(f'    """{self._description}"""', file=outfile)
        else:
            txt = '    """FIXME: Put a proper description' ' of your package here."""'
            print(txt, file=outfile)

        print("", file=outfile)

        if self._homepage:
            print(f'    homepage = "{self._homepage}"', file=outfile)
        else:
            print("    # FIXME: add homepage", file=outfile)
            print('    # homepage = ""', file=outfile)

        if self.pypi:
            print(f'    pypi = "{self.pypi}"', file=outfile)
        elif self.git:
            print(f'    url = "{self.url}"', file=outfile)
            print(f'    git = "{self.git}"', file=outfile)

        print("", file=outfile)

        if self._license:
            print("    # FIXME: check license", file=outfile)
            print(f'    license("{self._license}")', file=outfile)
        else:
            print("    # FIXME: add license", file=outfile)

        print("", file=outfile)

        print("    # FIXME: add github names for maintainers", file=outfile)
        print('    # maintainers("...")', file=outfile)
        if self._authors:
            print("    # Authors:", file=outfile)
            for author in self._authors:
                print(f"    # {author}", file=outfile)

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
            print(txt, file=outfile)
            for v, p_err in self._file_parse_errors:
                print(f"    # version {v!s}: {p_err.msg}", file=outfile)

            print("", file=outfile)

        for v in self._variants:
            print(f'    variant("{v}", default=False)', file=outfile)

        print("", file=outfile)

        if self.dependency_parse_errors:
            txt = "    # FIXME: the following dependencies could not be parsed"
            print(txt, file=outfile)
            for v, cfg_errs in self.dependency_parse_errors.items():
                print(f"    # version {v!s}:", file=outfile)
                for cfg_err in cfg_errs:
                    print(f"    #    {cfg_err.msg}", file=outfile)

            print("", file=outfile)

        if self.dependency_conversion_errors:
            txt = (
                "    # FIXME: the following dependencies could be parsed but "
                "not converted to spack"
            )
            print(txt, file=outfile)
            for v, cnv_errs in self.dependency_conversion_errors.items():
                print(f"    # version {v!s}:", file=outfile)
                for cnv_err in cnv_errs:
                    print(f"    #    {cnv_err.msg}", file=outfile)

            print("", file=outfile)

        if self.dependency_conflict_errors:
            txt = """\
    # FIXME: the following dependency conflicts were found. A conflict arises if two dependencies
    # have intersecting 'when=...' Specs (meaning that they can both be required at the same time),
    # but non-intersecting dependency Specs (e.g. 'pkg@4.2:' and 'pkg@:3.5')"""
            print(txt, file=outfile)

            for dep_conflict in self.dependency_conflict_errors:
                print(f"    # {dep_conflict.msg}", file=outfile)

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


def _convert_single(
    name: str,
    pypi_provider: package_providers.PyPIProvider,
    gh_provider: package_providers.GitHubProvider,
    num_versions: int = 10,
    use_test_prefix: bool = False,
) -> SpackPyPkg | None:
    """Convert a PyPI package to a Spack package.py."""
    # go through providers to check if one of them has the package
    is_gh_package = gh_provider.package_exists(name)
    provider = gh_provider if is_gh_package else pypi_provider

    if not provider.package_exists(name):
        logging.warning("Package %s not found through any of the supplied providers", name)
        return None

    # download available versions through provider (pypi, github)
    versions = provider.get_versions(name)
    if isinstance(versions, package_providers.PyProjectProviderQueryError):
        logging.warning("No valid versions found by provider %s", str(provider))
        return None

    # for each version, parse pyproject.toml
    pyprojects: list[PyProject] = []
    for i, v in enumerate(reversed(versions)):
        # only look at the first `num_versions` versions
        if i == num_versions:
            break

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

        # add provider to pyproject for convenience
        pyproject.provider = provider

        pyprojects.append(pyproject)

    if not pyprojects:
        logging.warning("Conversion for %s failed, no valid pyproject.tomls found", name)
        return None

    # convert to spack
    spackpkg = SpackPyPkg()
    spackpkg.all_versions = versions

    # always use PyPIProvider for dependencies
    spackpkg.build_from_pyprojects(name, pyprojects, pypi_provider, use_test_prefix=use_test_prefix)

    if isinstance(provider, package_providers.PyPIProvider):
        spackpkg.pypi = provider.get_pypi_package_base(name)
    elif isinstance(provider, package_providers.GitHubProvider):
        spackpkg.url = provider.get_download_url(name)
        spackpkg.git = provider.get_git_repo(name)
        spackpkg.pypi_name = provider.get_package_name(name)
        spackpkg.name = conversion_tools.pkg_to_spack_name(
            spackpkg.pypi_name, use_test_prefix=use_test_prefix
        )

    return spackpkg


def _package_exists_in_spack(name: str, spack_repo: pathlib.Path) -> bool:
    """Checks if a specific package exists in the spack repository.

    The name argument is the original non-spack name, e.g. 'black' instead of
    'py-black'.
    """
    name = conversion_tools.pkg_to_spack_name(name)
    pkg_dir = spack_repo / "packages" / name
    return pkg_dir.is_dir() and (pkg_dir / "package.py").is_file()


def _is_spack_repo(repo: pathlib.Path) -> bool:
    return repo.is_dir() and (repo / "packages").is_dir() and (repo / "repo.yaml").is_file()


def _run_spack_command(command: str) -> None | str:
    """Run spack command and return stdout."""
    command_list = command.split(" ")
    if command_list[0] != "spack":
        command_list.insert(0, "spack")
    try:
        return subprocess.run(command_list, capture_output=True, text=True, check=True).stdout
    except (FileNotFoundError, subprocess.CalledProcessError):
        return None


def _get_spack_repo(repo_path: str | None) -> pathlib.Path:
    # TODO @davhofer: cleanup/improve this function

    # 1. if user provided a repo, use that
    # 2. check if default repository exists using $SPACK_ROOT
    # 3. try to use spack command to get repos
    # 4. ask user to provide a repo
    spack_repo = None

    if repo_path is not None:
        # get provided repository
        spack_repo = pathlib.Path(repo_path)
    elif "SPACK_ROOT" in os.environ:
        # or try to find default repo
        spack_root = pathlib.Path(os.environ["SPACK_ROOT"])
        spack_repo = spack_root / "var" / "spack" / "repos" / "builtin"
    else:
        # this makes it easier to use if spack was installed from github with pip
        result = _run_spack_command("spack repo list")
        if result is not None:
            try:
                first_line = result.split("\n")[0]
                repo_path = first_line.split(" ")[-1]
                spack_repo = pathlib.Path(repo_path)
            except IndexError:
                pass

    # if no repo found, prompt user
    while spack_repo is None or not _is_spack_repo(spack_repo):
        spack_repo_str = input(
            "No spack repo found. Please enter full path to local spack repository:"
        )
        spack_repo = pathlib.Path(spack_repo_str)

    return spack_repo


def _write_package_to_repo(package: SpackPyPkg, spack_repo: pathlib.Path) -> bool:
    if not spack_repo.is_dir():
        return False
    try:
        pkg_dir = spack_repo / "packages" / package.name
        pkg_dir.mkdir()

        package_py = pkg_dir / "package.py"
        package_py.touch()

        with package_py.open("w") as f:
            package.print_pkg(outfile=f)

        return True

    except (FileExistsError, OSError):
        return False


# TODO @davhofer: allow multiple providers/user specification/check a list of providers for package
# TODO @davhofer: some sort of progress bar/console output while converting, downloading archives, etc.
# TODO @davhofer: currently, dependencies for variants/optional dependencies are also converted. Make this optional? Add flag to disable conversion of optional/extra dependencies
def convert_package(  # noqa: PLR0913 [too many arguments in function definition]
    name: str,
    max_conversions: int = 10,
    versions_per_package: int = 10,
    repo_path: str | None = None,
    ignore: list[str] | None = None,
    use_test_prefix: bool = False,
) -> None:
    """Convert a package and its dependencies to Spack.

    TODO: docstring with arguments
    """
    ignore_list: list[str] = [] if ignore is None else ignore

    spack_repo = _get_spack_repo(repo_path)
    print(f"Using Spack repository at {spack_repo}")

    if _package_exists_in_spack(name, spack_repo) and not use_test_prefix:
        print(f"Package {name} already exists in Spack repository")
        return

    # Explanation of ignore comment: PyProjectProvider protocol requires the __hash__()
    # method to be implemented, which is done by the @dataclass decorator for
    # PyPIProvider (but mypy does not detect this)
    pypi_provider = package_providers.PyPIProvider()  # type: ignore[abstract]
    gh_provider = package_providers.GitHubProvider()  # type: ignore[abstract]

    # queue of packages to be converted
    queue: list[str] = [name]
    # converted packages with number of converted versions. these can still have
    # errors, FIXME's, etc.
    converted: list[tuple[str, int, bool]] = []
    # packages that could not be converted and written at all
    conversion_failures: list[str] = []

    # allow user to cancel (Ctrl+C) the process and still show summary
    try:
        while queue and (max_conversions == -1 or len(converted) < max_conversions):
            name = queue.pop()

            print(f"\nConverting package {name}...")
            spackpkg = _convert_single(
                name,
                pypi_provider,
                gh_provider,
                num_versions=versions_per_package,
                use_test_prefix=use_test_prefix,
            )

            if spackpkg is None:
                conversion_failures.append(name)
                continue

            # write package to repo
            write_successful = _write_package_to_repo(spackpkg, spack_repo)

            if not write_successful:
                logging.warning("Error when trying to write package %s to repository", name)
                conversion_failures.append(name)
                continue

            # store package name, number of converted versions, and whether there are
            # requried fixes for dependencies
            dep_requires_fix = (
                bool(spackpkg.dependency_parse_errors)
                or bool(spackpkg.dependency_conversion_errors)
                or bool(spackpkg.dependency_conflict_errors)
            )
            converted.append((name, spackpkg.num_converted_versions, dep_requires_fix))

            for dep in spackpkg.original_dependencies:
                if (
                    dep != "python"
                    and dep not in queue
                    and dep not in conversion_failures
                    and dep not in ignore_list
                    and not _package_exists_in_spack(
                        dep, spack_repo
                    )  # this also covers packages already converted in this run
                ):
                    queue.append(dep)
    except KeyboardInterrupt:
        # display the current package in summary
        queue.insert(0, name)

    _print_summary(converted, queue, conversion_failures)


def _print_summary(
    converted: list[tuple[str, int, bool]],
    queue: list[str],
    conversion_failures: list[str],
) -> None:
    print(
        "\n\nNOTE: converted packages are saved in the Spack repo with the prefix 'py-' (e.g. 'py-pandas' instead of 'pandas')."
    )
    print("\n\n * * * * * * * * * * * * * SUMMARY * * * * * * * * * * * * *\n *")

    print(f" * Converted {len(converted)} packages:")
    has_fix_dep = False
    for p, n_versions, dep_requires_fix in converted:
        if dep_requires_fix:
            has_fix_dep = True
        print(f" *  - {p} ({n_versions} versions) {'[FIX DEP.]' if dep_requires_fix else ''}")
    # only display this if a package has the FIX DEP flag
    if has_fix_dep:
        print(
            " * Dependency errors that require manual review are marked as [FIX DEP.].\n * See generated `package.py` for details."
        )

    print(" *")
    if queue:
        print(
            f" * `max_conversions` limit reached but {len(queue)} unconverted\n * dependency packages left:"
        )
        for p in queue:
            print(f" *  - {p}")

    else:
        print(" * No packages left.")

    print(" *")
    if conversion_failures:
        print(
            f" * The following {len(conversion_failures)} packages could not be converted\n * due to errors:"
        )
        for p in conversion_failures:
            print(f" *  - {p}")

    else:
        print(" * No conversion failures.")

    if converted:
        print(" *\n * All generated `package.py` files should be manually\n * reviewed.")

    print(" *")

    print(" *\n * * * * * * * * * * * * * * * * * * * * * * * * * * * * * *")
