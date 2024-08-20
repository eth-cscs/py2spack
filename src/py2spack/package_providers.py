"""Utils for downloading packages from PyPI and opening the pyproject.tomls."""

from __future__ import annotations

import abc
import dataclasses
import functools
import re
from collections.abc import Hashable
from typing import Protocol

import requests
from packaging import version as vn

from py2spack import utils


KNOWN_ARCHIVE_FORMATS = [
    ".tar",
    ".tar.gz",
    ".tar.bz2",
    ".gz",
    ".xz",
    ".bz2",
]


def _parse_packaging_version(version: str) -> vn.Version | None:
    """Parse packaging version."""
    result = None
    try:
        v = vn.parse(version)
        # do not support post releases of prereleases etc.
        if not (v.pre and (v.post or v.dev or v.local)):
            result = v
    except vn.InvalidVersion:
        pass

    return result


@dataclasses.dataclass(frozen=True)
class PyProjectProviderQueryError:
    """Error during querying of the PyProjectProvider."""

    msg: str


class PyProjectProvider(Protocol, Hashable):
    """General provider interface for Python distribution packages."""

    @abc.abstractmethod
    def package_exists(self, name: str) -> bool:
        """Check whether a package exists on the provider."""

    @abc.abstractmethod
    def get_versions(self, name: str) -> list[vn.Version] | PyProjectProviderQueryError:
        """Get available package versions.

        Returns an error if no versions are found.
        """

    @abc.abstractmethod
    def get_pyproject(self, name: str, version: vn.Version) -> dict | PyProjectProviderQueryError:
        """Get the contents of the pyproject.toml file for the specified version."""

    @abc.abstractmethod
    def get_sdist_hash(
        self, name: str, version: vn.Version
    ) -> dict[str, str] | PyProjectProviderQueryError:
        """Get the sdist hash (sha256 if available) for the specified version."""


@dataclasses.dataclass(frozen=True)
class GitHubProvider(PyProjectProvider):
    """Obtains project versions and distribution packages through GitHub.

    See: https://docs.github.com/en/rest/releases/releases?apiVersion=2022-11-28
    Various public and private methods of this class cache their return values in order
    to minimize the number of requests to the provider.
    """

    base_url: str = "https://api.github.com/repos/"

    @functools.cache  # noqa: B019
    def _get(self, repo_specifier: str) -> dict | PyProjectProviderQueryError:
        """."""
        assert len(repo_specifier.split("/")) == 2  # noqa: PLR2004 [magic value]

        url = (
            f"{self.base_url}{'' if self.base_url.endswith('/') else '/'}{repo_specifier}/releases"
        )

        r = requests.get(url, headers={"accept": "application/vnd.github+json"}, timeout=10)

        if r.status_code != utils.HTTP_STATUS_SUCCESS:
            if r.status_code == utils.HTTP_STATUS_NOT_FOUND:
                return PyProjectProviderQueryError(
                    f"Package {repo_specifier} not found on GitHub (status code 404)"
                )

            return PyProjectProviderQueryError(
                f"Error when querying GitHub API (status code {r.status_code})."
                f" Response: {r.text}"
            )

        data: dict = r.json()
        return data

    def parse_repo_name(self, name: str) -> str | None:
        """Parse the github repository name.

        'name' must be either a url to a repository, or of the form "user/repository".
        Returns a string of the form "user/repository" or None.
        """
        if len(name.split("/")) == 2:  # noqa: PLR2004 [magic value]
            return name

        github_url = "https://github.com/"
        if name.startswith(github_url):
            # remove base url
            repo_specifier = name[len(github_url) :]
            # if .git suffix exists, remove it
            if repo_specifier.endswith(".git"):
                repo_specifier = repo_specifier[:-4]
            # check formatting
            if len(repo_specifier.split("/")) == 2:  # noqa: PLR2004 [magic value]
                return repo_specifier

        return None

    def get_download_url(self, name: str) -> str:
        """Returns the tarball download url (for Spack)."""
        versions_with_urls = self._get_versions_with_urls(name)
        assert isinstance(versions_with_urls, list)
        return versions_with_urls[-1][1]

    def get_git_repo(self, name: str) -> str:
        """Returns the github repository url."""
        repo_specifier = self.parse_repo_name(name)
        assert repo_specifier is not None
        return f"https://github.com/{repo_specifier}.git"

    def get_package_name(self, name: str) -> str:
        """Returns the actual package name ('pkg-name' instead of 'user/pkg-name')."""
        repo_specifier = self.parse_repo_name(name)
        assert repo_specifier is not None
        return repo_specifier.split("/")[1]

    def package_exists(self, name: str) -> bool:
        """Check whether a package exists on the provider."""
        repo_specifier = self.parse_repo_name(name)
        if repo_specifier is None:
            return False
        response = self._get(repo_specifier)
        return not (
            isinstance(response, PyProjectProviderQueryError)
            and response.msg.endswith("(status code 404)")
        )

    def _parse_version_from_tag(self, tag: str) -> vn.Version | None:
        if tag.startswith("v"):
            tag = tag[1:]
        try:
            parsed_version: vn.Version = vn.parse(tag)
            return parsed_version

        except vn.InvalidVersion:
            return None

    def get_versions(self, name: str) -> list[vn.Version] | PyProjectProviderQueryError:
        """Get available package versions.

        Returns an error if no versions are found.
        """
        versions_with_urls = self._get_versions_with_urls(name)
        result: list[vn.Version] | PyProjectProviderQueryError = []
        if isinstance(versions_with_urls, PyProjectProviderQueryError):
            result = versions_with_urls

        elif not versions_with_urls:
            result = PyProjectProviderQueryError("No valid versions found")

        else:
            result = sorted([v for v, url in versions_with_urls])

        return result

    def _get_versions_with_urls(
        self, name: str
    ) -> list[tuple[vn.Version, str]] | PyProjectProviderQueryError:
        repo_specifier = self.parse_repo_name(name)
        if repo_specifier is None:
            return PyProjectProviderQueryError(
                f"{name} is not a correctly formatted repository specifier. Please provide either the GitHub repo url, or a string of the form 'user/repository_name'"
            )

        releases = self._get(repo_specifier)
        if isinstance(releases, PyProjectProviderQueryError):
            return releases

        # get tarball url + version pairs
        versions_with_urls = [
            (
                self._parse_version_from_tag(release.get("tag_name", "")),
                release.get("tarball_url", ""),
            )
            for release in releases
        ]
        return [(v, url) for v, url in versions_with_urls if v is not None]

    def get_pyproject(self, name: str, version: vn.Version) -> dict | PyProjectProviderQueryError:
        """Get the contents of the pyproject.toml file for the specified version."""
        versions_with_urls = self._get_versions_with_urls(name)
        if isinstance(versions_with_urls, PyProjectProviderQueryError):
            return versions_with_urls

        result = [url for v, url in versions_with_urls if v == version and url]
        if not result:
            return PyProjectProviderQueryError(f"No download url found for {name} v{version}")

        url = result[0]

        return _try_load_pyproject(url, name, ".tar.gz")

    def get_sdist_hash(
        self, name: str, version: vn.Version
    ) -> dict[str, str] | PyProjectProviderQueryError:
        """Get the sdist hash (sha256 if available) for the specified version."""
        return PyProjectProviderQueryError(
            f"GitHub doesn't provide sdist checksums ({name} v{version})"
        )


@dataclasses.dataclass(frozen=True)
class PyPIProvider(PyProjectProvider):
    """Obtains project versions and distribution packages through the PyPI JSON API.

    Various public and private methods of this class cache their return values in order
    to minimize the number of requests to the provider.
    """

    base_url: str = "https://pypi.org/simple/"

    @functools.cache  # noqa: B019
    def _get(self, name: str) -> dict | PyProjectProviderQueryError:
        """Load info for the available distribution files from PyPI.

        Data is cached.
        """
        name = _normalize_package_name(name)
        url = f"{self.base_url}{'' if self.base_url.endswith('/') else '/'}{name}/"
        r = requests.get(
            url,
            headers={"Accept": "application/vnd.pypi.simple.v1+json"},
            timeout=10,
        )
        if r.status_code != utils.HTTP_STATUS_SUCCESS:
            if r.status_code == utils.HTTP_STATUS_NOT_FOUND:
                return PyProjectProviderQueryError(
                    f"Package {name} not found on PyPI (status code 404)"
                )

            return PyProjectProviderQueryError(
                f"Error when querying JSON API (status code {r.status_code})."
                f" Response: {r.text}"
            )

        data: dict = r.json()
        return data

    def package_exists(self, name: str) -> bool:
        """Check whether a package exists on the provider."""
        response = self._get(name)
        return not (
            isinstance(response, PyProjectProviderQueryError)
            and response.msg.endswith("(status code 404)")
        )

    @functools.cache  # noqa: B019
    def get_versions(self, name: str) -> list[vn.Version] | PyProjectProviderQueryError:
        """Get usable versions for package.

        Returns an error if no versions are found.
        In addition to the caching of the `_get` method, we also cache all calls
        to `get_versions`, because the versions are needed frequently during the
        conversion process for dependencies, and the size of the data is small.
        """
        data = self._get(name)
        if isinstance(data, PyProjectProviderQueryError):
            return data

        versions = data["versions"]

        # parse and sort versions
        result: list[vn.Version] | PyProjectProviderQueryError = sorted(
            {vv for v in versions if (vv := _parse_packaging_version(v))}
        )

        if not result:
            result = PyProjectProviderQueryError("No valid versions found")

        return result

    def get_pyproject(self, name: str, version: vn.Version) -> dict | PyProjectProviderQueryError:
        """Download and extract the pyproject.toml for the specified package version."""
        all_metadata = self._get_distribution_metadata(name)

        if isinstance(all_metadata, PyProjectProviderQueryError):
            return all_metadata

        metadata = all_metadata.get(version)

        if metadata is None:
            return PyProjectProviderQueryError(f"No metadata for version {version} found on PyPI")

        # for type checker, we know these values are going to be strings
        assert isinstance(metadata["url"], str)
        assert isinstance(metadata["extension"], str)

        # python sdist archives contain a top level directory, e.g. "black-24.4.2/"
        return _try_load_pyproject(metadata["url"], name, metadata["extension"])

    @functools.cache  # noqa: B019
    def _get_distribution_metadata(
        self, name: str
    ) -> dict[vn.Version, dict[str, str | dict]] | PyProjectProviderQueryError:
        """Get metadata for available distribution files from PyPI.

        We cache the result in order to avoid repeatedly processing the same data
        for all method calls to `get_pyproject` (which in turn calls this method).
        """
        # NOTE: caching both the _get_distribution_metadata and the _get methods might
        # seem redundant, idea is that the caching of _get_distribution_metadata avoids
        # repeated processing and caching of _get makes sure the calls to get_versions
        # and get_pyproject do not both make a call to the API.
        data = self._get(name)
        if isinstance(data, PyProjectProviderQueryError):
            return data
        files = data["files"]

        # for now we only support tarball archives like .tar.gz
        files_known_format = [f for f in files if _is_archive_format_known(f["filename"])]

        if not files_known_format:
            return PyProjectProviderQueryError(
                "No files with known archive format found (note: wheel file"
                " parsing not supported)"
            )

        # for each file, get the filename, url, version, extension, and sha256
        # TODO @davhofer: in case of an error, skip the file or return the error?
        files_parsed: dict[vn.Version, dict[str, str | dict]] = {}
        for f in files_known_format:
            filename = f["filename"]
            archive_ext = _parse_archive_extension(filename)
            assert isinstance(archive_ext, str)

            directory_name = filename[: -len(archive_ext)]

            v = self._parse_version_from_directory_name(directory_name, name)

            if v is None:
                # if there is an error with parsing the version from the filename
                continue

            # usually we expect there to be a sha256 hash, but in theory there could be
            # other or no hashes at all
            hashes = f["hashes"]
            if not hashes:
                continue

            files_parsed[v] = {
                "filename": filename,
                "url": f["url"],
                "extension": archive_ext,
                "hashes": hashes,
                "directory": directory_name,
            }

        if not files_parsed:
            return PyProjectProviderQueryError("No valid files found")

        return files_parsed

    def get_sdist_hash(
        self, name: str, version: vn.Version
    ) -> dict[str, str] | PyProjectProviderQueryError:
        """Get the sdist hash (sha256 if available) for the specified version."""
        all_metadata = self._get_distribution_metadata(name)
        if isinstance(all_metadata, PyProjectProviderQueryError):
            return all_metadata

        metadata = all_metadata.get(version)

        if metadata:
            assert isinstance(metadata["hashes"], dict)
            hashes: dict[str, str] = metadata["hashes"]
            if hashes:
                if "sha256" in hashes:
                    return {"sha256": hashes["sha256"]}

                key, value = next(iter(hashes.items()))
                return {key: value}

        return PyProjectProviderQueryError("No hash found")

    def get_pypi_package_base(self, name: str) -> str:
        """Get the pypi string required by Spack for the specific package.

        E.g. pypi = "black/black-24.4.2.tar.gz".
        This method is specific to the PyPIProvider, as it is not required if source
        distributions are downloaded from e.g. github.
        """
        all_metadata = self._get_distribution_metadata(name)
        all_versions = self.get_versions(name)

        # this function is only called if we know that there are valid sdists/versions
        assert isinstance(all_metadata, dict)
        assert isinstance(all_versions, list)
        assert len(all_versions) > 0

        most_recent = all_metadata[all_versions[-1]]

        return f"{name}/{most_recent['filename']}"

    def _parse_version_from_directory_name(
        self, directory_name: str, pkg_name: str
    ) -> vn.Version | None:
        """Parse version from filename and check correct formatting."""
        # in some cases the filename had underscores instead of dashes; handle this by
        # normalizing the filename for the check
        prefix = f"{_normalize_package_name(pkg_name)}-"
        if not _normalize_package_name(directory_name).startswith(prefix):
            return None
        version_str = directory_name[len(prefix) :]
        try:
            parsed_version: vn.Version = vn.parse(version_str)
            return parsed_version

        except vn.InvalidVersion:
            return None


def _normalize_package_name(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def _parse_archive_extension(filename: str) -> str | PyProjectProviderQueryError:
    extension_list = [ext for ext in KNOWN_ARCHIVE_FORMATS if filename.endswith(ext)]

    if not extension_list:
        # we return an API error here because the filenames are obtained through
        # the API and the function is used during the API lookup process
        return PyProjectProviderQueryError(f"Extension not recognized for: {filename}")

    # get the longest matching extension, e.g. .tar.gz instead of .gz
    return max(extension_list, key=len)


def _is_archive_format_known(filename: str) -> bool:
    return any(filename.endswith(ext) for ext in KNOWN_ARCHIVE_FORMATS)


# TODO @davhofer: handle zip archives
# TODO @davhofer: should this function be placed in the PyProjectProvider Protocol? or in utils?
# generic function for loading any file/filetype?
def _try_load_pyproject(
    url: str, name: str, archive_ext: str
) -> dict | PyProjectProviderQueryError:
    """Load sdist from url and extract pyproject.toml contents."""
    sdist_file_obj = utils.download_bytes(url)

    result: dict | None | PyProjectProviderQueryError

    if sdist_file_obj is None:
        result = PyProjectProviderQueryError(f"Unable to download package {name} from {url}")

    elif archive_ext in KNOWN_ARCHIVE_FORMATS:
        result = utils.extract_toml_from_tar(sdist_file_obj, "pyproject.toml")
        if result is None:
            result = PyProjectProviderQueryError("Unable to extract pyproject.toml from archive")

    else:
        result = PyProjectProviderQueryError(
            "Failed to open sdist, format must be tarball archive (.tar.gz, .bz2, etc.)"
        )

    return result
