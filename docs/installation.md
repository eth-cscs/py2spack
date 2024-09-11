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
