## Conversion workflow

The high level workflow or description of what happens when you convert a package with Spack, e.g. after running `py2spack my-package`, is as follows:

1. Try to find a local Spack repository (if not specified via CLI). This will be used to store converted packages and check for existing ones.
2. Check if `my-package` exists on PyPI.
3. Discover available versions and source distributions on PyPI.
4. For each version (or at most `--versions-per-package` many):
   1. Download the source distribution
   2. Parse the pyproject.toml file
   3. Convert metadata and dependencies from the python packaging format to their Spack equivalent, where possible.
   4. Depending on the build-backend, if supported, check for non-python dependencies and build steps and try to convert those **\[UNDER DEVELOPMENT\]**.
5. Combine the dependencies of all downloaded versions and simplify the specs/constraints.
6. Check for conflicts/unsatisfiable dependency requirements.
7. If successful, save the converted package to the local Spack repository (by creating a directory `packages/py-my-package/` and writing a `package.py` file inside of it).
8. Check for dependencies of `my-package` that are not in Spack/converted/in the queue yet. Add those to the conversion queue.
9. Repeat from 2. with the next package from the queue.


### Package conversion
This section describes how an individual python package is converted to Spack.

Conversion of a package, provided as a string `name`, is handled by the method `core._convert_single`. It first checks whether it is dealing with a GitHub package, by calling the `GitHubProvider.package_exists(name)` method. After deciding on the right provider, it uses it to obtain a list of all availabe package versions. For each version, the `pyproject.toml` contents are loaded and parsed, resulting in a `core.PyProject` object.
This list of `PyProject`s is then passed to `core.SpackPyPkg.build_from_pyprojects`. There, first the newest version of the package/pyprojects is used for converting the general metadata. This metadata includes

- the package name
- description
- homepage
- authors'/maintainers' names and emails, as comments (Spacks `maintainers` field uses GitHub usernames)
- the license (licenses which are only provided as a file/path are ignored, since Spack requires specifiying the SPDX identifier and not a license file)

For each pyproject, its version is converted from the `packaging` format to Spack, and stored together with its source distribution checksum (if one exists).

### Dependency conversion

> Note: this section discusses conversion of python package dependencies. For non-python dependencies, see [Python extensions](#python-extensions).

In the last step, the dependencies are converted to Spack. The challenges here are on the one hand the conversion of individual packaging dependencies and requirements to their semantically equivalent Spack version, e.g. in terms of version ranges, and on the other hand combining all dependencies from many versions of the same package into one.

We first convert the individual dependencies of each pyproject. This includes all dependencies listed under the following pyproject.toml keys:

- `build-system.requires`
- `project.dependencies`
- `project.optional-dependencies`, the extras here are used to define the variants of the spack package
- `project.requires-python` for a dependency on specific python versions

Each individual packaging requirement/dependency is generally converted to a Spack dependency consisting of a main dependency `Spec` and a when-`Spec` (technically it is converted to a list of Spack dependencies, because a single packaging requirement can sometimes require multiple Spack dependencies. E.g. `some_pkg ; platform_system != 'windows'` would be converted to one Spack dependency for each platform that is not `windows`). The main dependency Spec captures the package dependency itself, i.e. package name, versions, and extras/variants. The problem here is that the semantics of python packaging version specifiers are not identical to Spack version specifiers (one example would be: `pkg <= 4.2` is **not** the same as `pkg@:4.2`, the one on the left does not include version `4.2.1`, the one on the right does). Thus in order to map accepted version ranges between the two, we first compute the subset of all available package versions that match/are included in the python packaging specifier. Given the list of all package versions and the subset of matching versions, we then compute the equivalent, condensed Spack specifier (more details on this in the comments in the `conversion_tools.py` module).
The when-Spec captures conditions under which the dependency applies, e.g. only for specific platforms, specific python versions, if a specific extra/variant is built in case of optional dependencies, etc. Thus the when-Spec generally only contains constraints for optional dependencies or requirements that include a [marker](https://packaging.pypa.io/en/latest/markers.html). For each dependency, we also remember whether it is a build dependency (from `bild-system.requires`, will be `type="build"` in Spack) or a runtime dependency (all others, will be `type=("build", "run")` in Spack).

We then store each individual Spack dependency (i.e. pair of main dependency Spec and when-Spec) together with the current version of the original package/version of the `pyproject.toml` from which this dependency originates in a hash table mapping unique Spack dependencies to lists of versions (all versions of the package we're currently converting that have this unique dependency). Next, we condense this list of associated versions of the original package for each unique dependency, and add it to the when-Spec. This means that the Spack dependency now only applies when the package itself has a version matching this version list, which is exactly what we want.

In the last step, we check for dependency conflicts which would make the dependencies of the package unsatisfiable. A dependency conflict is any pair of dependencies `dep-Spec1, when-Spec1` and `dep-Spec2, when-Spec2` such that has intersecting when-Specs but non-intersecting dependency Specs. This would mean that it is possible that both dependencies apply at the same time (the intersection of the when-Specs) but the dependencies themselves are not at the same time satisfiable (the dependency Specs are disjunct). An example would be the following pair: `dep-Spec1, when-Spec1 = (Spec("py-black@:3.2"), Spec("@12.0:15 platform=linux")` and `dep-Spec2, when-Spec2 = (Spec("py-black@4:"), Spec("@14:18 platform=linux")`. If we are installing a version between `14` and `15` on a `linux` system, then both when-Specs match and the dependencies apply. Then we would have one dependency on `py-black` with version less or equal to `3.2`, and one dependency on `py-black` with version greater or equal to `4`, which are not satisfiable both at the same time. If such an error occurs, the user is notified and a corresponding comment is added to the `package.py` file.

When the `package.py` file is written, the Spack dependencies are formatted as `depends_on("<dep-Spec>", when="<when-Spec>")` in the section with the correct dependency type `default_args` (e.g. under `with default_args(type="build"):` for all build dependencies).

### Error handling

Most (recoverable) errors that occur at any point during the conversion process, e.g. parsing errors of individual dependencies or conversion errors from packaging to Spack of individual dependencies, are stored and added to the final `SpackPyPkg` object. The idea is that whenever possible, individual errors should not crash the program or prevent the conversion from completing. These stored errors are then added to the `package.py` file as comments.

### Python extensions

> Work in progress...

We are currently working on supporting python extensions (python packages including/providing bindings for compiled code like C++), starting with the [scikit-build-core](https://scikit-build-core.readthedocs.io/en/latest/) backend and pybind11.

Build processes for such packages can be very involved and complex and are generally not fully automatable. Our goal is thus simply to provide the user with hints and suggestions where possible. But we still require them to review and "fine-tune" the `package.py` file manually. Since scikit-build-core is a wrapper around cmake, we initially just plan to try to extract any sort of version constraints, external dependencies, flags, etc. found in `CMakeLists.txt`, add them to the `package.py` as comments, and let the user implement the details.

### Package naming conventions

In order to find/name the Spack package corresponding to a python package from PyPI or GitHub, we follow the general Spack convention that the python package `my-package` will be called `py-my-package` in Spack.
