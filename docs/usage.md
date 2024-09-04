## Usage

```
py2spack [-h] [--max-conversions MAX_CONVERSIONS] [--versions-per-package VERSIONS_PER_PACKAGE] [--repo-path REPO_PATH] [--ignore pkg1 pkg2 ...] [--testing] package
```

Positional arguments:

- `package`: Name of the package

Options:

- `-h`, `--help`: show this help message and exit
- `--max-conversions <n>`: Maximum number of packages/dependencies that are converted. Default: `10`
- `--versions-per-package <n>`: Versions per package to be downloaded and converted. Default: `10`
- `--repo-path <path>`: Path to local spack repository, converted packages will be stored here. If none is provided, py2spack will look for the default repo at `$SPACK_ROOT/var/spack/repos/builtin/` Default: `None`
- `--ignore [pkg1 pkg2 ...]`: List of packages to ignore for conversion
- `--testing`: Optional flag for testing purposes; adds the prefix 'test-' to the package name when saving it

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
