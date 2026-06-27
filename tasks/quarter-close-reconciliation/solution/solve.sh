#!/bin/bash
# Reference solution: install the reconciliation program and run it.
set -e
cp "$(dirname "$0")/solve.py" /app/reconcile.py
python3 /app/reconcile.py
