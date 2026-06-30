#!/bin/bash
# Reference solution: install the exact-arithmetic slicer and run it.
set -e
cp "$(dirname "$0")/solve.py" /app/slice.py
python3 /app/slice.py
