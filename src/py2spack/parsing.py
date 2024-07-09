"""Utilities for parsing pyproject.toml files.

Parts of the code adapted from https://github.com/pypa/pyproject-metadata.
"""
# SPDX-License-Identifier: MIT

from __future__ import annotations

import pathlib
import re
import typing

from collections.abc import Mapping
from typing import Any, List, Tuple


from packaging import requirements
from packaging import specifiers


class ConfigurationError(Exception):
    """Error in the backend metadata."""

    def __init__(self, msg: str, *, key: str | None = None):
        """Initialize error."""
        super().__init__(msg)
        self._key = key

    @property
    def key(self) -> str | None:  # pragma: no cover
        """Get key."""
        return self._key


class DataFetcher:
    """Fetcher class for parsing and extracting the various metadata fields."""

    def __init__(self, data: Mapping[str, Any]) -> None:
        """Initialize DataFetcher with raw toml data (dictionary)."""
        self._data = data

    def __contains__(self, key: Any) -> bool:
        """Check if DataFetcher contains the (nested) key.

        Examples for key:
            'project'
            'project.dependencies'
            'project.optional-dependencies.extra'
        """
        if not isinstance(key, str):
            return False
        val = self._data
        try:
            for part in key.split("."):
                val = val[part]
        except KeyError:
            return False
        return True

    def get(self, key: str) -> Any:
        """Get value for a specific (multi-level) key."""
        val = self._data
        for part in key.split("."):
            val = val[part]
        return val

    def get_str(self, key: str) -> str | None | ConfigurationError:
        """Get string."""
        try:
            val = self.get(key)
            if not isinstance(val, str):
                msg = (
                    f'Field "{key}" has an invalid type, '
                    f'expecting a string (got "{val}")'
                )
                return ConfigurationError(msg, key=key)
            return val
        except KeyError:
            return None

    def get_list(self, key: str) -> list[str] | ConfigurationError:
        """Get list of strings."""
        try:
            val = self.get(key)
            if not isinstance(val, list):
                msg = (
                    f'Field "{key}" has an invalid type, expecting a list '
                    f'of strings (got "{val}")'
                )
                return ConfigurationError(msg, key=val)
            for item in val:
                if not isinstance(item, str):
                    msg = (
                        f'Field "{key}" contains item with invalid type, expecting a '
                        f'string (got "{item}")'
                    )
                    return ConfigurationError(msg, key=key)
            return val
        except KeyError:
            return []

    def get_dict(self, key: str) -> dict[str, str] | ConfigurationError:
        """Get dict of string keys and values."""
        try:
            val = self.get(key)
            if not isinstance(val, dict):
                msg = (
                    f'Field "{key}" has an invalid type, expecting a dictionary of '
                    f'strings (got "{val}")'
                )
                return ConfigurationError(msg, key=key)
            for subkey, item in val.items():
                if not isinstance(item, str):
                    msg = (
                        f'Field "{key}.{subkey}" has an invalid type, expecting a '
                        f'string (got "{item}")'
                    )
                    return ConfigurationError(msg, key=f"{key}.{subkey}")
            return val
        except KeyError:
            return {}

    def get_people(
        self, key: str
    ) -> list[tuple[str | None, str | None]] | ConfigurationError:
        """Used for parsing the 'authors' and 'maintainers' fields."""
        try:
            val = self.get(key)
            if not (
                isinstance(val, list)
                and all(isinstance(x, dict) for x in val)
                and all(
                    isinstance(item, str)
                    for items in [_dict.values() for _dict in val]
                    for item in items
                )
            ):
                msg = (
                    f'Field "{key}" has an invalid type, expecting a list of '
                    'dictionaries containing the "name" and/or "email" keys '
                    f'(got "{val}")'
                )
                return ConfigurationError(msg, key=key)
            return [(entry.get("name"), entry.get("email")) for entry in val]
        except KeyError:
            return []

    def get_dependencies(
        self,
    ) -> (
        tuple[list[requirements.Requirement], list[ConfigurationError]]
        | ConfigurationError
    ):
        """Parses the 'dependencies' field."""
        requirement_strings = self.get_list("project.dependencies")

        if isinstance(requirement_strings, ConfigurationError):
            return requirement_strings

        requirements_list: list[requirements.Requirement] = []
        requirement_errors: list[ConfigurationError] = []
        for req in requirement_strings:
            try:
                requirements_list.append(requirements.Requirement(req))
            except requirements.InvalidRequirement:
                msg = (
                    'Field "project.dependencies" contains an invalid PEP 508 '
                    f'requirement string "{req}"'
                )
                requirement_errors.append(
                    ConfigurationError(msg, key="project.dependencies")
                )
        return (requirements_list, requirement_errors)

    def get_optional_dependencies(
        self,
    ) -> (
        tuple[dict[str, list[requirements.Requirement]], list[ConfigurationError]]
        | ConfigurationError
    ):
        """Parses the 'optional-dependencies' field."""
        try:
            val = self.get("project.optional-dependencies")
        except KeyError:
            return {}, []

        if not isinstance(val, dict):
            msg = (
                'Field "project.optional-dependencies" has an invalid type, expecting a'
                f' dictionary of PEP 508 requirement strings (got "{val}")'
            )
            return ConfigurationError(msg, key="project.optional-dependences")

        requirements_dict: dict[str, list[requirements.Requirement]] = {}
        requirement_errors: list[ConfigurationError] = []
        for extra, requirements_list in val.copy().items():
            if not isinstance(extra, str):
                msg = (
                    "Field project.optional-dependencies contains extra of invalid"
                    f" type, expected string (got '{extra}')"
                )
                requirement_errors.append(
                    ConfigurationError(msg, key="project.optional-dependencies")
                )
                continue

            if not isinstance(requirements_list, list):
                msg = (
                    f'Field "project.optional-dependencies.{extra}" has an invalid type'
                    f", expecting a dictionary PEP 508 requirement strings "
                    f'(got "{requirements_list}")'
                )
                requirement_errors.append(
                    ConfigurationError(msg, key="project.optional-dependencies")
                )
                continue

            requirements_dict[extra] = []
            for req in requirements_list:
                if not isinstance(req, str):
                    msg = (
                        f'Field "project.optional-dependencies.{extra}" has an invalid '
                        f'type, expecting a PEP 508 requirement string (got "{req}")'
                    )
                    requirement_errors.append(
                        ConfigurationError(msg, key="project.optional-dependencies")
                    )
                    continue
                try:
                    requirements_dict[extra].append(requirements.Requirement(req))
                except requirements.InvalidRequirement:
                    msg = (
                        f'Field "project.optional-dependencies.{extra}" contains '
                        f'an invalid PEP 508 requirement string "{req}"'
                    )
                    requirement_errors.append(
                        ConfigurationError(msg, key="project.optional-dependencies")
                    )
                    continue
        return (dict(requirements_dict), requirement_errors)

    def get_license(self) -> str | None | ConfigurationError:
        """Tries to get the project license.

        Parses the 'license' field. If the license is not specified there, tries to
        parse 'classifiers' field and read license from it.
        """
        _license = self._get_license_from_field()

        if isinstance(_license, str):
            return _license

        classifier_license = self._get_license_from_classifiers()
        if classifier_license:
            return classifier_license

        return _license

    def _get_license_from_field(self) -> str | None | ConfigurationError:
        """Parses the 'license' field."""
        if "project.license" not in self:
            return None

        # license SHOULD be dict but sometimes is specified directly as a string
        _license = self.get_dict("project.license")
        license_str = self.get_str("project.license")

        if isinstance(_license, dict):
            for field in _license:
                if field not in ("file", "text"):
                    msg = f'Unexpected field "project.license.{field}"'
                    return ConfigurationError(msg, key=f"project.license.{field}")

            filename = self.get_str("project.license.file")
            text = self.get_str("project.license.text")

            if isinstance(filename, str):
                msg = "Parsing license from file not supported"
                return ConfigurationError(msg, key="project.license")
                # file = project_dir.joinpath(filename)
                # if not file.is_file():
                #    msg = f'License file not found ("{filename}")'
                #     return ConfigurationError(msg, key="project.license.file")
                # text = file.read_text(encoding="utf-8")

            if isinstance(text, ConfigurationError):
                return text

            if text is None:
                msg = (
                    "Invalid 'project.license.text' value, expecting string (got None)"
                )
                return ConfigurationError(msg, key="project.license")

            license_text = text

        elif isinstance(license_str, str):
            license_text = license_str

        elif isinstance(_license, ConfigurationError):
            return _license

        # manual checking of license format & text
        if len(license_text) > 250:
            msg = (
                "License text appears to be full license content instead of "
                "license identifier"
            )
            return ConfigurationError(msg, key="project.license")

        return license_text

    def _get_license_from_classifiers(self) -> str | None:
        """Parses the 'classifiers' field and tries to exract license from it."""
        # license can also be specified in classifiers
        classifiers = self.get_list("project.classifiers")
        if isinstance(classifiers, list):
            # get all classifiers detailing licenses
            license_classifiers = list(
                filter(lambda x: x.startswith("License"), classifiers)
            )
            # for each license classifier, split by "::" and take the
            # last substring (and strip unnecessary whitespace)
            licenses = list(
                map(lambda x: x.split("::")[-1].strip(), license_classifiers)
            )
            if len(licenses) > 0:
                # AND is more restrictive => be safe (?)
                license_text = " AND ".join(licenses)
                return license_text
        return None

    def get_requires_python(self) -> specifiers.SpecifierSet | ConfigurationError:
        """Parses the 'requires-python' field."""
        parsed_requires_python = self.get_str("project.requires-python")
        if isinstance(parsed_requires_python, str):
            try:
                requires_python = specifiers.SpecifierSet(parsed_requires_python)
                return requires_python
            except specifiers.InvalidSpecifier:
                msg = (
                    'Field "project.requires-python" contains an invalid PEP 508 '
                    f'requirement string "{parsed_requires_python}"'
                )
                return ConfigurationError(msg, key="project.requires-python")

        # if parsed_requires_python is None or ConfigurationError
        return parsed_requires_python

    def get_build_requires(
        self,
    ) -> (
        Tuple[List[requirements.Requirement], List[ConfigurationError]]
        | ConfigurationError
    ):
        """Parses the 'build-system.requires' field."""
        requirement_strings = self.get_list("build-system.requires")

        if isinstance(requirement_strings, ConfigurationError):
            return requirement_strings

        requirements_list: list[requirements.Requirement] = []
        requirement_errors: list[ConfigurationError] = []
        for req in requirement_strings:
            try:
                requirements_list.append(requirements.Requirement(req))
            except requirements.InvalidRequirement as e:
                msg = (
                    'Field "build-system.requires" contains an invalid PEP 508 '
                    f'requirement string "{req}" ("{e}")'
                )
                requirement_errors.append(
                    ConfigurationError(msg, key="build-system.requires")
                )
        return (requirements_list, requirement_errors)

    def get_build_backend(self) -> str | None | ConfigurationError:
        """Parses the 'build-system.build-backend' field."""
        build_backend = self.get_str("build-system.build-backend")
        return build_backend

    def get_homepage(self) -> str | None | ConfigurationError:
        """Parses the 'urls' field and tries to extract the homepage."""
        parsed_urls = self.get_dict("project.urls")
        if isinstance(parsed_urls, dict):
            for key in ["Homepage", "Repository", "Github", "Wiki"]:
                if key in parsed_urls:
                    return parsed_urls[key]

                if key.lower() in parsed_urls:
                    return parsed_urls[key.lower()]
            return None
        return parsed_urls


class License(typing.NamedTuple):
    """Represents the project license."""

    text: str
    file: pathlib.Path | None


class Readme(typing.NamedTuple):
    """Represents the project README."""

    text: str
    file: pathlib.Path | None
    content_type: str


def valid_pypi_name(name) -> bool:
    """Checks whether 'name' is a valid pypi name."""
    # See https://packaging.python.org/en/latest/specifications/core-metadata/#name and
    # https://packaging.python.org/en/latest/specifications/name-normalization/#name-format
    return (
        re.match(r"^([A-Z0-9]|[A-Z0-9][A-Z0-9._-]*[A-Z0-9])$", name, re.IGNORECASE)
        is not None
    )
