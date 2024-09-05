# py2spack: Automating conversion of standard python packages to Spack package recipes

Github repository for the CSCS internship project with the goal of developing a Python tool for automatically generating Spark package recipes based on existing Python packages, with the ability to handle direct and transitive dependencies and flexible versions.

For more information, see the [Wiki](https://github.com/davhofer/py2spack/wiki).

## Installation

The package is still in development and not yet published to PyPI. It can however be installed manually.

1. If you don't have it yet, [install Spack](https://spack.readthedocs.io/en/latest/getting_started.html) on your system.
2. py2spack imports various modules from Spack and thus needs to find those through `$PYTHONPATH`

   1. Make sure that the environment variable `SPACK_ROOT` is set, e.g. `export SPACK_ROOT=/home/<user>/spack`.
   2. Either execute the following in your active shell or place it in your shell rc file (e.g. `.bashrc`, `.zshrc`). If you place it in the `.rc` file, make sure `$SPACK_ROOT` is set or replace it with the explicit path.

   ```bash
   export PYTHONPATH=$SPACK_ROOT/lib/spack/external/_vendoring:$SPACK_ROOT/lib/spack/external:$SPACK_ROOT/lib/spack:$PYTHONPATH
   ```

3. Install py2spack
   1. Directly from GitHub:
   ```bash
   pip install git+https://github.com/davhofer/py2spack
   ```
   2. Or clone and install manually:
   ```bash
   git clone git@github.com:davhofer/py2spack.git
   cd py2spack
   pip install .
   ```

## Usage

```
usage: py2spack [-h] [--max-conversions MAX_CONVERSIONS]
                [--versions-per-package VERSIONS_PER_PACKAGE]
                [--repo REPO] [--ignore [IGNORE ...]] [--testing]
                package

CLI for converting a python package and its dependencies to Spack.

positional arguments:
  package               Name of the package to be converted

options:
  -h, --help            show this help message and exit
  --max-conversions MAX_CONVERSIONS
                        Maximum number of packages that are converted
  --versions-per-package VERSIONS_PER_PACKAGE
                        Versions per package to be downloaded and
                        converted
  --repo REPO           Name of or full path to local Spack
                        repository where packages should be saved
  --ignore [IGNORE ...]
                        List of packages to ignore. Must be specified
                        last (after <package> argument) for the
                        command to work
  --testing             For testing purposes; adds the prefix 'test-'
                        when saving packages
```

### Conversion from PyPI

```bash
py2spack package-name
```

### Conversion from GitHub

```bash
py2spack https://github.com/user/package-name
```

or

```bash
py2spack user/package-name
```

> NOTE: dependencies will always be resolved through PyPI, even when converting a package from GitHub

## Documentation

To check out the detailed documentation (API docs, usage, implementation, package conversion, etc.), you need to clone the repository and build the docs:

```bash
pip install .[docs]
cd docs; make html
```

You can then browse it locally, e.g.

```bash
firefox _build/html/index.html
```

## Running tests

After installing the package, the tests can be run from the project root directory as follows:

```bash
python -m pytest
```

## Important links

- [Detailed Project Description](<CSCS Internship Project Description.md>)
- [Wiki](https://github.com/davhofer/py2spack/wiki)
- [Changelog](CHANGELOG.md)
