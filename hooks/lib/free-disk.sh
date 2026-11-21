#!/usr/bin/env bash
# Kept as a short name; the logic is in free-disk.py next to it.
exec python3 "$(cd "$(dirname "$0")" && pwd)/free-disk.py" "$@"
