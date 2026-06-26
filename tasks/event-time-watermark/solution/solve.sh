#!/bin/bash
# Reference solution: install the correct streaming aggregator and run it.
set -e
cp "$(dirname "$0")/solve.py" /app/aggregator.py
python3 /app/aggregator.py
