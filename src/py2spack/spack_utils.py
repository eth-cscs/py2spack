"""Utilities for interacting with the local Spack installation (repos, executable)."""

from __future__ import annotations

import os
import pathlib
import re
import subprocess


def package_exists_in_spack(name: str) -> bool:
    """Checks if a specific package exists in any local Spack repository.

    The function relies on the `spack list` cli command, thus all repositories
    known to Spack will be considered (but only those).
    """
    # result = run_spack_command(f"spack list {name}")
    result = run_spack_command(f"$SPACK_ROOT/bin/spack list {name}")
    if result is not None:
        pattern = r"(\b)(?<!-)" + re.escape(name) + r"(?!-)\b"
        return re.search(pattern, result) is not None
    return False


def is_spack_repo(repo: pathlib.Path) -> bool:
    """Check if the directory at the given path is a Spack repo."""
    return repo.is_dir() and (repo / "packages").is_dir() and (repo / "repo.yaml").is_file()


def run_spack_command(command: str) -> None | str:
    """Run spack command and return stdout."""
    return subprocess.run(command, capture_output=True, text=True, shell=True, check=False).stdout


def get_spack_repo(repo_path: str | None) -> pathlib.Path:
    """Find a valid Spack repository for the user."""
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
        result = run_spack_command("spack repo list")
        if result is not None:
            try:
                first_line = result.split("\n")[0]
                repo_path = first_line.split(" ")[-1]
                spack_repo = pathlib.Path(repo_path)
            except IndexError:
                pass

    # if no repo found, prompt user
    while spack_repo is None or not is_spack_repo(spack_repo):
        spack_repo_str = input(
            "No spack repo found. Please enter full path to local spack repository:"
        )
        spack_repo = pathlib.Path(spack_repo_str)

    return spack_repo
