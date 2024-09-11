"""Generic utility methods for py2spack."""

from __future__ import annotations

import functools
import io
import pathlib
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
    tar_bytes: bytes,
    file_path: str,
) -> str | None:
    """Extract and read file from tar archive.

    The file path relative to the root of the archive must be given explicitly.
    Optionally, can choose to also check for the file starting from the single top-level
    directory of the archive, if there is such a directory. File contents are returned
    as a dictionary.
    """
    # works for .gz, .bz2, .xz, ...
    tar_bytes_object = io.BytesIO(tar_bytes)
    try:
        with tarfile.open(fileobj=tar_bytes_object, mode="r:*") as tar:
            names = tar.getnames()

            # expect the file path to start either at the archive root directory,
            # or in the single top-level directory after the root
            top_level_files = list({x.split("/")[0] for x in names})
            if file_path not in names and len(top_level_files) == 1:
                file_path = f"{top_level_files[0]}/{file_path}"
                if file_path not in names:
                    return None

            member = tar.getmember(file_path)
            f = tar.extractfile(member)

            if f is not None:
                return f.read().decode("utf-8")

    except (OSError, tarfile.TarError, UnicodeDecodeError, KeyError) as e:
        print(f"Error when extracting file {file_path} from tar: {e}")

    return None


def normalize_path(path: pathlib.Path) -> pathlib.Path:
    """Remove relative path modifiers like ../ from paths to make them comparable.

    Treat path like a stack, every '..' pops off a level. Series of '..' at the
    beginning of the path remain as they are.
    """
    path_arr = str(path).split("/")

    # need to maintain start index to be able to skip past potential '..' at the
    # beginning of the path
    start_idx = 0
    while ".." in path_arr:
        try:
            i = path_arr.index("..", start_idx)
        except ValueError:
            break

        if i == start_idx:
            start_idx += 1
            continue

        path_arr.pop(i)
        path_arr.pop(i - 1)

    reconstructed_path = "/".join(path_arr)
    return pathlib.Path(reconstructed_path)
