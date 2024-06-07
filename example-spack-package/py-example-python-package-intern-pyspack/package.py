# Copyright 2013-2024 Lawrence Livermore National Security, LLC and other
# Spack Project Developers. See the top-level COPYRIGHT file for details.
#
# SPDX-License-Identifier: (Apache-2.0 OR MIT)

# ----------------------------------------------------------------------------
# If you submit this package back to Spack as a pull request,
# please first remove this boilerplate and all FIXME comments.
#
# This is a template package file for Spack.  We've put "FIXME"
# next to all the things you'll want to change. Once you've handled
# them, you can save this file and test your package like this:
#
#     spack install py-example-python-package-intern-pyspack
#
# You can edit this file again by typing:
#
#     spack edit py-example-python-package-intern-pyspack
#
# See the Spack documentation for more information on packaging.
# ----------------------------------------------------------------------------

from spack.package import *


class PyExamplePythonPackageInternPyspack(PythonPackage):
    """ Example python package. """

    pypi = "example_python_package_intern_pyspack/example_python_package_intern_pyspack-0.1.3.tar.gz"

    maintainers("davhofer")

    license("MIT", checked_by="davhofer")

    version("0.1.3", sha256="edc0077ed40e5f11eb6a9821f66283d0dbd1c446c9752bf53a9e0d633e297117")

    # Build dependencies
    depends_on("py-flit-core", type="build")

    # Package dependencies
    # None

