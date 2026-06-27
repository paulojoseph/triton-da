#!/bin/bash
# Reference solution: install the consolidation engine and run it.
set -e
cp "$(dirname "$0")/solve.py" /app/consolidate.py
python3 /app/consolidate.py
