#!/bin/bash
# Reference solution: train the compact classifier and save /app/model.pkl.
set -e
python3 "$(dirname "$0")/solve.py"
