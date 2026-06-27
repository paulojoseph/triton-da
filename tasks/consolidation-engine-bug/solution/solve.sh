#!/bin/bash
# Reference fix: the defect is in congraph.consolidated_entities(), which builds
# the set of parent ids instead of the subsidiaries themselves, so leaf
# subsidiaries never get an effective interest and their NCI falls back to the
# direct rate. Replace that module with the corrected one and re-run.
set -e
cp "$(dirname "$0")/congraph.py" /app/congraph.py
python3 /app/consolidate.py
