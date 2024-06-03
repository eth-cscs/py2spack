# CSCS Internship: Automating Spack Package Generation for Python Packages 

## Description [¶](https://www.hpc-ch.org/internships-at-cscs-the-swiss-national-supercomputing-centre-2024/)

Spack is an open-source package management tool designed for supercomputing and high-performance computing (HPC) environments. It simplifies the installation and management of software and dependencies, allowing users to build and customize software stacks for their specific computing needs. A Spack package contains a set of instructions and metadata that define the dependencies and how to build and install a specific software package or library. Although Python packages already include the essential dependency metadata, Spack does not currently utilize this information, resulting in a manual and error-prone process when creating Spack packages from them. This challenge is further aggrevated when dealing with transitive dependencies that also lack their Spack counterpart.

### Project Goals
We are looking for a motivated individual to intern with us and contribute to Spack’s development by extending its capabilities to automatically generate Spack packages for Python dependencies. The intern will work on the following objectives:

* Develop a Python Tool: Create a Python tool that can extract dependency metadata from Python packages and use it to generate Spack package recipes.
* Handle Direct and Transitive Dependencies: Extend the tool’s functionality to generate Spack package recipes for both direct and transitive dependencies of a Python package.
* Version Flexibility: Enhance the tool to generate a single Spack recipe from multiple versions of a Python package, offering users and Spack’s concretizer the flexibility to choose the most suitable package version.
* Integration with Spack: Integrate the developed tool into the Spack codebase and extend the ‘spack create’ command to utilize this tool for generating Spack package recipes.

### Qualifications and Skills

* Good Python programming.
* Basic knowledge of package management concepts and Python packaging.
* Familiarity with Spack and HPC environments is a plus but not mandatory.

--------------------------------------

## Useful reference documentation

## Python
- The Python Language Reference. The import system: https://docs.python.org/3/reference/import.html
- Level Up Your Python: https://henryiii.github.io/level-up-your-python/notebooks/0%20Intro.html

### Python packaging
- Python Packaging Authority: https://www.pypa.io/en/latest/
- Python Enhancement Proposals » PEP Index » Packaging PEPs: https://peps.python.org/topic/packaging/
- Python Packaging User Guide: https://packaging.python.org/en/latest/
- pyOpenSci - Python Packaging Tools: https://www.pyopensci.org/python-package-guide/package-structure-code/python-package-build-tools.html
- The Python Package Index (PyPI): https://pypi.org/
- PyPI Stats. Analytics for PyPI packages: https://pypistats.org/

### Python packaging tooling
- Python build frontends:
    - [pip](https://pip.pypa.io/en/stable/)
    - [build](https://github.com/pypa/build) (minimal build frontend)
    - [uv](https://github.com/astral-sh/uv)
- Python build backends:
    - [setuptools](https://setuptools.pypa.io/en/latest/)
    - [flit](https://flit.pypa.io/en/stable/)
    - [scikit-build](https://scikit-build.readthedocs.io/en/latest/) (for CMake-based projects)
    - [scikit-build-core](https://scikit-build-core.readthedocs.io/en/latest/#) (for CMake-based projects)
- Python project managers with build backends:
    - [hatch/hatchling](https://hatch.pypa.io/latest/)
    - [pdm](https://pdm-project.org/en/latest/)
    - [poetry](https://python-poetry.org/)
- pyproject-hooks (low-level tools to deal with build backend hooks) [[github](https://github.com/pypa/pyproject-hooks)][[docs](https://pyproject-hooks.readthedocs.io/en/latest/)]

### Python packaging history
- [Python Packaging in 2020](https://dx13.co.uk/articles/2020/01/02/python-packaging-in-2020/). _A comprehensive introduction to the evolution of Python packaging towards the basis of current design based on PEP 517 & PEP 518._
- [Python Packaging: Hate, hate, hate everywhere](https://lucumr.pocoo.org/2012/6/22/hate-hate-hate-everywhere/). _More historical info and context._
- [A Curriculum for Python Packaging ](https://inventwithpython.com/blog/2018/10/22/a-curriculum-for-python-packaging/). _Collection of links to interesting documents and presentations._


## Spack
- [Spack](https://spack.io/)
- [Tutorial: Spack 101](https://spack-tutorial.readthedocs.io/en/latest/)
- [Spack Packaging Guide](https://spack.readthedocs.io/en/latest/packaging_guide.html)
- [pypi-to-spack-package](https://github.com/spack/pypi-to-spack-package) tool from spack developers (by Harmen Stoppels, [haampie](https://github.com/haampie))

## Roadmap

### Week 1: 03.05 - 07.05
- Refresh knowledge of Python language, import system and virtual environment. Ideas:
    - Python language documentation
    - Level Up Your Python notebooks
    - `virtualenv`, `venv`, `uv`, `pipx`, ...
- Get to know the Python packaging system (only pure Python packages)
    - Read documentation
    - Create a new Python distribution package from scratch using build backends (e.g. flit, setuptools, ...)
    - Optionally, upload it to TestPyPI and install it from there
- Get to know the basics of Spack
    - Read documentation
    - Write manually a very simple Spack package
    - Write manually a Spack package reproducing the Python package created earlier
- Investigate and play around with ideas on how to automatize the translation process from Python packages definitions (`pyproject.toml`) to Spack packages `package.py`)
    - [pypi-to-spack-package](https://github.com/spack/pypi-to-spack-package) tool already does this in the simple cases.




