#!/bin/bash
set -e

# Get the directory where this script is located
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Default command
CMD="${1:-convert}"
FILE="${2:-sample_raw_bits.txt}"

cd "$SCRIPT_DIR"

# Use MSYS_NO_PATHCONV to prevent Git Bash from converting paths
export MSYS_NO_PATHCONV=1

# Run with docker-compose - mount is configured in docker-compose.yml
docker-compose run --rm parser "$CMD" "/data/$FILE" "${@:3}"
