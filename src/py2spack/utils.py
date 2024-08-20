"""Generic utility methods for py2spack."""

from __future__ import annotations

import io
import tarfile

import requests
import tomli


HTTP_STATUS_SUCCESS = 200
HTTP_STATUS_NOT_FOUND = 404


def download_bytes(url: str) -> io.BytesIO | None:
    """Download file from url as BytesIO object (in memory)."""
    response = requests.get(url)
    if response.status_code == HTTP_STATUS_SUCCESS:
        return io.BytesIO(response.content)

    return None


def extract_toml_from_tar(
    file_like_object: io.BytesIO,
    file_path: str,
) -> dict | None:
    """Extract toml file from tar archive.

    The file path relative to the root of the archive must be given explicitly.
    Optionally, can choose to also check for the file starting from the single top-level
    directory of the archive, if there is such a directory. File contents are returned
    as a dictionary.
    """
    result = None
    # works for .gz, .bz2, .xz, ...
    try:
        with tarfile.open(fileobj=file_like_object, mode="r:*") as tar:
            names = tar.getnames()

            # expect the file path to start either at the archive root directory,
            # or in the single top-level directory after the root
            top_level_files = list({x.split("/")[0] for x in names})
            if file_path not in names and len(top_level_files) == 1:
                file_path = f"{top_level_files[0]}/{file_path}"

            member = tar.getmember(file_path)
            f = tar.extractfile(member)

            if f is not None:
                pyproject_content = f.read().decode("utf-8")
                result = tomli.loads(pyproject_content)

    except (OSError, tarfile.TarError, UnicodeDecodeError, tomli.TOMLDecodeError, KeyError) as e:
        print(e)

    return result
