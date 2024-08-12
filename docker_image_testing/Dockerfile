FROM python:3.12

# Install system dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    build-essential \
    git \
    && rm -rf /var/lib/apt/lists/*


# Set the working directory
WORKDIR /app

# Clone the Spack repository to /app/spack and set up the environment
RUN git clone --depth=100 --branch=releases/v0.22 https://github.com/spack/spack.git && \
    /bin/bash -c "source /app/spack/share/spack/setup-env.sh"

# Set environment variable for Spack paths
ENV PYTHONPATH="/app/spack/lib/spack/external/_vendoring:/app/spack/lib/spack/external:/app/spack/lib/spack"

ENV SPACK_ROOT="/app/spack"

# Adjust working directory 
WORKDIR /app/py2spack
