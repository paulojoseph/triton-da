#!/bin/bash
# Reference solution: replace the broken pipeline entry point with a correct,
# bounded-memory streaming implementation, then run it to produce /app/output.json.
set -e
cp "$(dirname "$0")/solve.py" /app/tracer/main.py
python3 /app/tracer/main.py
