## Overview

py2spack is a tool for automatically generating Spack package recipes based on existing Python packages, with the ability to handle direct and transitive dependencies and flexible versions.
Its main goal is to support users and developers in writing custom `package.py` recipes for existing packages (that could be installed via pip) and automate as much of this process as possible. Conversion for pure python packages should generally work out-of-the-box, meaning that the generated Spack package can be installed without further changes, **but it's always recommended to double-check the `package.py` files for errors or open FIXMEs.**

Conversion of python extensions, python bindings for compiled libraries, or any sort of python package that also includes compiled code like C++ is more complicated and in general not completely automatable. The objective there is to support the user as much as possible by providing hints and suggestions for external non-python dependencies, version constraints etc., but manual review of the generated `package.py` is **always required** (normal python dependencies should still be converted automatically and correctly).

In addition to managing the dependencies, py2spack also tries to detect and include metadata like maintainers, licenses, existing package versions and their checksums, extras/variants, etc.

See the [Conversion workflow](./workflow.md) section for more details on how py2spack and its package conversion works.

### Supported python build-backends

Any build-backend specifying its metadata and dependency using the standard pyproject.toml tables/keys, such as:

- hatchling
- flit/flit-core
- setuptools >= 61.0.0, with only a `pyproject.toml` file and no `setup.py` or `setup.cfg`

#### Complex/compiled builds:

- scikit-build-core: py2spack parses potential dependencies and version constraints for non-python dependencies from `CMakeLists.txt` and adds the converted dependencies to the generated package as comments. They are an approximation of the actual dependencies and serve as suggestions for the user to make conversion easier, but manual review is always required. For simple packages, uncommenting the generated suggestions can already be enough for successful conversion.
