#!/bin/bash
# Reference solution: install the causal-merge program and run it.
set -e
cp "$(dirname "$0")/solve.py" /app/merge.py
python3 /app/merge.py
