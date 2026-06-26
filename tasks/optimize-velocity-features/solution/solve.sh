#!/bin/bash
# Reference solution: install the optimized engine and run it.
set -e
cp "$(dirname "$0")/solve.py" /app/engine.py
python3 /app/engine.py
