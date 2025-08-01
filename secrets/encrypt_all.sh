#!/bin/bash

# Ensure the script exits if any command returns a non-zero status
set -e

# Get the directory of the script
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Loop through all .env files in the script directory
for file in ${SCRIPT_DIR}/decoded/*.env; do
  file_base="$(basename "${file}" .env)"
  sops encrypt --age=age1kqmpnwma8rlnvgkg7n0tfz7k4urpgaadm28uwuu6l9m0skg7rawq6apsup "${file}" --output "${file_base}.enc.env"
done

# Usage
# ./encrypt_all.sh
