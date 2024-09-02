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
    result = run_spack_command(f"spack list {name}")
    if result is not None:
        pattern = r"(\b)(?<!-)" + re.escape(name) + r"(?!-)\b"
        return re.search(pattern, result) is not None
    return False


def is_spack_repo(repo: pathlib.Path) -> bool:
    """Check if the directory at the given path is a Spack repo."""
    return repo.is_dir() and (repo / "packages").is_dir() and (repo / "repo.yaml").is_file()


def run_spack_command(command: str) -> None | str:
    """Run spack command and return stdout."""
    # check if spack command is available (returncode != 0 => not available)
    if subprocess.run(
        "spack -h", capture_output=True, text=True, shell=True, check=False
    ).returncode:
        cmd_list = command.split(" ")
        assert cmd_list[0] == "spack"
        cmd_list[0] = "$SPACK_ROOT/bin/spack"
        command = " ".join(cmd_list)

    return subprocess.run(command, capture_output=True, text=True, shell=True, check=False).stdout



def get_spack_repo(spack_repository: str | None) -> pathlib.Path:
    """Find a valid Spack repository for the user."""
    # TODO @davhofer: cleanup/improve this function
    # TODO @davhofer: allow user to choose spack repo from available ones

    # 1. if user provided a repo, use that
    # 2. check if default repository exists using $SPACK_ROOT
    # 3. try to use spack command to get repos
    # 4. ask user to provide a repo
    repo_dict = {}

    result = run_spack_command("spack repo list")
    if result:
        for line in result.split("\n"):
            if not line: 
                continue 

            words = line.split(" ")

            if not words:
                continue

            name = words[0]
            path = words[-1]

            repo_dict[name] = path

    repo_path = None

    if spack_repository is not None:
        # get provided repository
        if spack_repository in repo_dict:
            spack_repository = repo_dict[spack_repository]

        repo_path = pathlib.Path(spack_repository)



    # if no repo found, prompt user
    while repo_path is None or not is_spack_repo(repo_path):
        if repo_path is not None and not is_spack_repo(repo_path):
            print(f"Not a Spack repository: {repo_path}\n")
        elif repo_path is None:
            print("No repository provided.\n")

        if result:
            print("Repositories found by Spack:")
            print(result)
        else:
            print("No local repositories found by Spack.")

        spack_repo_str = input(
            "Enter name of/path to local Spack repo where converted packages should be saved (see --repo CLI option): "
        )
        print()

        if spack_repo_str in repo_dict:
            spack_repo_str = repo_dict[spack_repo_str]
        
        repo_path = pathlib.Path(spack_repo_str)

    print(f"Using Spack repository at {repo_path}\n")
    return repo_path
