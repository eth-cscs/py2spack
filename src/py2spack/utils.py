"""Generic utility methods for py2spack."""

from __future__ import annotations

import functools
import io
import tarfile

import requests


HTTP_STATUS_SUCCESS = 200
HTTP_STATUS_NOT_FOUND = 404


@functools.lru_cache
def download_bytes(url: str) -> bytes | None:
    """Download file from url as bytes (in memory).

    Responses are cached (cache size of 128).
    """
    response = requests.get(url)
    if response.status_code == HTTP_STATUS_SUCCESS and isinstance(response.content, bytes):
        return response.content

    return None


def extract_file_content_from_tar_bytes(
    file_bytes: bytes,
    file_path: str,
) -> str | None:
    """Extract and read file from tar archive.

    The file path relative to the root of the archive must be given explicitly.
    Optionally, can choose to also check for the file starting from the single top-level
    directory of the archive, if there is such a directory. File contents are returned
    as a dictionary.
    """
    # works for .gz, .bz2, .xz, ...
    file_bytes_object = io.BytesIO(file_bytes)
    try:
        with tarfile.open(fileobj=file_bytes_object, mode="r:*") as tar:
            names = tar.getnames()

            # expect the file path to start either at the archive root directory,
            # or in the single top-level directory after the root
            top_level_files = list({x.split("/")[0] for x in names})
            if file_path not in names and len(top_level_files) == 1:
                file_path = f"{top_level_files[0]}/{file_path}"

            member = tar.getmember(file_path)
            f = tar.extractfile(member)

            if f is not None:
                return f.read().decode("utf-8")

    except (OSError, tarfile.TarError, UnicodeDecodeError, KeyError) as e:
        print(e)

    return None
