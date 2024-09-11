"""A package for converting Python distribution packages to Spack package.py files."""

from __future__ import annotations


__all__ = ["SpackPyPkg", "convert_package"]
__version__ = "0.0.1"

from .core import SpackPyPkg, convert_package
