
## Implementation

### Modules overview

#### core.py

Main module, contains the main "program loop" `convert_package` which executes the workflow shown above and conversion of individual packages, as well as the classes `PyProject` and `SpackPyPkg` representing a `pyproject.toml` and `package.py` respectively, with additional data.

#### package_providers.py

Contains the PyProjectProvider protocol/interface responsible for querying external APIs in order to get available versions, metadata, and the actual source distributions/pyproject.toml files for a specific package. Currently there are 2 instantiations of this protocol:

- PyPIProvider for converting packages from PyPI
- GitHubProvider for converting packages from GitHub

#### conversion_tools.py

Utilities for converting python packaging requirements, dependencies, versions, constraints, markers etc. to their Spack equivalents and simplifying them. Large portions of this code are adapted from [pypi-to-spack-package](https://github.com/spack/pypi-to-spack-package) on GitHub.

#### pyproject_parsing.py

Utilities for parsing pyproject.toml files. The code is partially adapted from [pyproject-metadata](https://github.com/pypa/pyproject-metadata) on GitHub, with customized error handling.

#### cli.py

Makes the main `core.convert_package` method usable and configurable from the command line.

#### utils.py

Various general utilities for file handling and downloading.

### Main program

The main program is excecuted by the method `core.convert_package`. It performs or at least initiates all of the steps described in the workflow in the initial section of this page. Its arguments are

- `name`: The name of the package to be converted. If `name` is a GitHub repository url or a string of the form "user/repo-name", the package will be converted from GitHub instead of PyPI.
- `max_conversions`: The maximum number of packages that will be converted. If this limit is reached execution will stop, even if there still are uncoverted dependencies. Default: `10`
- `versions_per_package`: How many versions (at most) will be converted per package. Default: `10`
- `repo_path`: Path to the local Spack repository where converted packages will be stored and a lookup for already existing packages will be performed (in the future, all Spack repositories will be used for the existing packages lookup). If None is specified, py2spack will use the builtin Spack repository at `$SPACK_ROOT/var/spack/builtin/`
- `ignore`: A list of packages that will not be converted
- `use_test_prefix`: Flag used for development

The method maintains a queue of packages yet to be converted, which initially just holds the package specified by the user via the CLI. In each iteration, it pops the next package name from the queue, and tries to convert it. If conversion was successful, it tries to create a new directory in the chosen Spack repository and writes the recipe to a new `package.py` file there. It then goes through all of the dependencies of the package, and checks if they are not already in the queue, not in the ignore list, do not exist in the Spack repo already, and have not been attempted to be converted but failed. If all of these are true, it adds the dependency to the queue. To check if a package `my-package` already exists in Spack, it checks if a directory called `py-my-package` exists in `spack_repository/packages/` and if it contains a `package.py` file.

> Note: Currently, only the provided, single Spack repository is checked for existing packages. We plan on changing this to check all repositories in the `repos.yaml` file, in accordance to how Spack looks for packages.

In the end, the method prints a small summary with all converted packages, packages that failed to convert, and unconverted dependencies not found in Spack. For each of the unconverted dependencies, it will also display a flag if there are dependency conflicts, errors or other information in the `package.py` file that require manual review.

### Package providers interface

In order to resolve dependencies, discover existing versions, and obtain source distributions and `pyproject.toml` files, we use the `PyProjectProvider` interface. It is defined as a Python Protocol and contains the methods `package_exists`, `get_versions`, `get_pyproject`, and `get_sdist_hash`. Any implementation must also implement these methods. Currently there are two implementations, `PyPIProvider` and `GitHubProvider`.

#### PyPIProvider

The `PyPIProvider` class uses the [PyPI JSON API](https://peps.python.org/pep-0691/) (with endpoint https://pypi.org/simple/). A GET request to this endpoint for an existing package will retrieve JSON data including all known versions and metadata for all available files, such as download url, hashes/checksums, and standard package metadata. While this metadata alone could already be used for package conversion, it does not include any information on the build backend and build dependencies of the package, which is vital for converting more involved and complex python packages and can only be found in the `pyproject.toml` file. We use this metadata directly however for the methods `get_versions` and `get_sdist_hash` (and indirectly also for `package_exists`, by checking if the GET request succeeded or not), as the versions and checksums of source distributions are directly available there.

For `get_pyproject`, we obtain the download URL for a specific package version from this metadata, download the source distribution (which is usually a tarball), extract it, and return the contents of the `pyproject.toml` file as a python dictionary.

In order to minimize the number of requests to the API, we cache the results of the GET requests. We also cache calls to `get_versions` and the helper method `_get_distribution_metadata`, as these are called repeatedly during package conversion and for the resolving and conversion of dependencies.

Since Spack `PythonPackage`s support a special field `pypi` which is used to store a specially formatted string with the PyPI package base address and information, the class also contains a method `get_pypi_package_base` returning that string. This field tells Spack where to find versions and source distributions of the package.

#### GitHubProvider

The `GitHubProvider` class is used to download packages from GitHub. In order to be able to find the package, the provider does not need just the package name, but also the name of the user that owns the repository (more specifically, here the "package name" always refers to the GitHub repository name). Thus the `name` argument for the methods of the `GitHubProvider` class needs to either be the full github repository url (e.g. https://github.com/user/package), or a string of the form "user/package".
Currently, the `GitHubProvider` queries the https://api.github.com/repos/ endpoint for _releases_ of a package. GitHub repositories in general do not explicitly provide package versions, but it is standard practice that the tag name of a GitHub release contains the release version, formatted as e.g. `v1.2.3`. This is why we chose to query the releases of a repository. This does however mean that it is currently not possible to convert packages that don't have releases or releases tagged with version numbers from GitHub.

> The class could be extended to just download and convert the single "version" found in the main/master (or any specified) branch of the repository (from https://github.com/user/rep-name/archive/main.tar.gz), and then let the user explicitly provide the version number.

The list of releases obtained from the API endpoint includes the `tag_name` and `tarball_url` for each release, with the `tag_name` being used to get the package version. The `tarball_url` is used to download the source distribution and extract the `pyproject.toml` file.
Unlike PyPI, GitHub **does not provide checksums** for the source distribution archives! Since Spack requires them for each version, we compute the sha256 checksum of the tarball ourselves after downloading it. Similar to the `PyPIProvider` class, GET requests and calls to the helper methods `_get_versions_with_urls` and `_get_pyproject_and_checksum` are cached.

Instead of the `pypi` field, packages from GitHub contain a `git` and a `url` field in Spack which allow Spack to download versions and distributions. The class provides the corresponding metadata through the `get_download_url` and `get_git_repo` methods.

## Testing

After installing the package, the tests can be run from the project root directory as follows:

```
python -m pytest
```

Installation tests for converted packages are run through GitHub Actions in a Docker container, see `.github/workflows/run-installation-tests.yaml`.
