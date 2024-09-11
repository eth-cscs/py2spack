## Usage

```
usage: py2spack [-h] [--max-conversions MAX_CONVERSIONS] [--versions-per-package VERSIONS_PER_PACKAGE] [--repo REPO] [--allow-duplicate] package [--ignore [IGNORE ...]]

CLI for converting a python package and its dependencies to Spack.

positional arguments:
  package               Name of the package to be converted

options:
  -h, --help            show this help message and exit
  --max-conversions MAX_CONVERSIONS
                        Maximum number of packages that are converted
  --versions-per-package VERSIONS_PER_PACKAGE
                        Versions per package to be downloaded and converted
  --repo REPO           Name of or full path to local Spack repository where packages should be saved
  --ignore [IGNORE ...]
                        List of packages to ignore. Must be specified last (after <package> argument) for the command to work
  --allow-duplicate     Convert the package, even if a package of the same name already exists in some Spack repo. Will NOT overwrite the existing package. Only applies to the main package to be converted, not to dependencies.
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
