#!/bin/bash
# Reference solution: install the exact polytope solver and run it.
set -e
cp "$(dirname "$0")/solve.py" /app/polytope.py
python3 /app/polytope.py
