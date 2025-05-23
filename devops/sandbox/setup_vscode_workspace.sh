#!/bin/bash

# ========== VS CODE INTEGRATION ==========
echo "Creating symlinks for VS Code IntelliSense..."

mkdir -p "/var/tmp/metta"

# Link site-packages for IntelliSense support
if [ -n "$CONDA_PREFIX" ]; then
  SITE_PACKAGES_PATH="$CONDA_PREFIX/lib/python3.11/site-packages"
  SYMLINK_PATH="/var/tmp/metta/conda-site-packages"
  ln -sf "$SITE_PACKAGES_PATH" "$SYMLINK_PATH"
  echo "Symlink created: $SYMLINK_PATH -> $SITE_PACKAGES_PATH"
else
  echo "WARNING: CONDA_PREFIX is not set. Make sure you've activated your conda environment."
  echo "Run 'conda activate metta' before running this script."
fi
