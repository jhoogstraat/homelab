#!/bin/bash

# Ensure the script exits if any command returns a non-zero status
set -e

# Get the directory of the script
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

mkdir -p "${SCRIPT_DIR}/decoded"

# Loop through all .env files in the script directory
for file in ${SCRIPT_DIR}/*.enc.env; do
  decoded_filename="$(basename "${file}" .enc.env)"
  sops decrypt "${file}" --output "${SCRIPT_DIR}/decoded/${decoded_filename}.env"
done

# Usage
# SOPS_AGE_KEY=AGE-SECRET-KEY-... ./decrypt_all.sh
