# CSCS Internship: Automating Spack Package Generation for Python Packages

Github repository for the CSCS internship project with the goal of developing a Python tool for automatically generating Spark package recipes based on existing Python packages, with the ability to handle direct and transitive dependencies and flexible versions.

## Important links

- [Detailed Project Description](<CSCS Internship Project Description.md>)
- [Changelog](CHANGELOG.md)
- [Wiki](https://github.com/davhofer/py2spack/wiki)

## Installation

The package is still in development and not yet published to PyPI. It can however be installed manually.

1. [Install Spack](https://spack.readthedocs.io/en/latest/getting_started.html) on your system.
2. Make sure that the environment variable `SPACK_ROOT` is set, e.g. `export SPACK_ROOT=/home/<user>/spack`.
3. Either execute the following in your active shell or place it in your shell rc file (e.g. `.bashrc`, `.zshrc`):

   ```bash
   export PYTHONPATH=$SPACK_ROOT/lib/spack/external/_vendoring:$SPACK_ROOT/lib/spack/external:$SPACK_ROOT/lib/spack:$PYTHONPATH
   ```

   If you place it in the rc file, make sure `$SPACK_ROOT` is set when the file is executed or replace it with the explicit path.

4. Clone the [py2spack github repository](https://github.com/davhofer/py2spack):
   ```bash
   git clone git@github.com:davhofer/py2spack.git
   ```
5. `cd py2spack`
6. Install the package:
   ```bash
   python -m pip install .
   ```

## Running tests

After installing the package, the tests can be run from the project root directory as follows:

```
python -m pytest
```

## Usage

```
py2spack [-h] [--max-conversions MAX_CONVERSIONS] [--versions-per-package VERSIONS_PER_PACKAGE] [--repo-path REPO_PATH] [--ignore pkg1 pkg2 ...] [--testing] package
```

Positional arguments:
-  `package`: Name of the package

Options:
-  `-h`, `--help`: show this help message and exit
-  `--max-conversions <n>`: Maximum number of packages that are converted. Default: `10`
-  `--versions-per-package <n>`: Versions per package to be downloaded and converted. Default: `10`
-  `--repo-path <path>`: Path to local spack repository. Default: `None`  
    If no path is given, the tool will first look for the standard builtin Spack repository, and prompt the user for the path if none is found.
-  `--ignore [pkg1 pkg2 ...]`: List of packages to ignore
-  `--testing`: Optional flag for testing purposes; adds the prefix 'test-' to the package name when saving it
