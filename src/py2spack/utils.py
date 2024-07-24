"""Generic utility methods for py2spack."""

from __future__ import annotations

import io
import tarfile
from typing import Any

import requests
import tomli


HTTP_STATUS_SUCCESS = 200
HTTP_STATUS_NOT_FOUND = 404


def download_sdist(url: str) -> io.BytesIO | None:
    """Download source distribution from url as BytesIO object (in memory)."""
    response = requests.get(url)
    if response.status_code == HTTP_STATUS_SUCCESS:
        return io.BytesIO(response.content)

    return None


def extract_from_tar(file_like_object: io.BytesIO, file_path: str) -> dict[Any, Any] | None:
    """Extract pyproject.toml from tar archive.

    The top level directory name inside the archive must be given explicitly.
    Contents are returned as a dictionary.
    """
    result = None
    # works for .gz, .bz2, .xz, ...
    try:
        with tarfile.open(fileobj=file_like_object, mode="r:*") as tar:
            member = tar.getmember(file_path)
            f = tar.extractfile(member)

            if f is not None:
                pyproject_content = f.read().decode("utf-8")
                result = tomli.loads(pyproject_content)

    except (OSError, tarfile.TarError, UnicodeDecodeError, tomli.TOMLDecodeError, KeyError):
        pass

    return result
