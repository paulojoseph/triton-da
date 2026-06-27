#!/bin/bash
# Reference solution: install the consolidation program and run it.
set -e
cp "$(dirname "$0")/solve.py" /app/consolidate.py
python3 /app/consolidate.py
