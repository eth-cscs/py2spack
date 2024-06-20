# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- parse_pyproject.py: Initial version of a parser for pyproject.toml files with subsequent conversion to a Spack package.
- parse_pyproject.py: Added conversion of dependencies and markers using functionality from [pypi-to-spack-package](https://github.com/spack/pypi-to-spack-package).

### Removed
- old files and directories.