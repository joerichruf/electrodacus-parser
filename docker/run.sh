#!/bin/bash
set -e

usage() {
    cat <<EOF
Usage: $0 [convert|hexdump] [file] [extra-args...]

  Wraps electrodacus-parser via docker-compose. Mounts ../data at /data
  read-only. Defaults to: convert /data/sample_raw_bits.txt

Examples:
  $0
  $0 convert mycapture.txt
  $0 convert mycapture.txt --include-errors
  $0 hexdump mycapture.txt
EOF
}

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
    usage
    exit 0
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

CMD="${1:-convert}"
FILE="${2:-sample_raw_bits.txt}"

cd "$SCRIPT_DIR"

# Prevent Git Bash from converting absolute container paths.
export MSYS_NO_PATHCONV=1

docker-compose run --rm parser "$CMD" "/data/$FILE" "${@:3}"
