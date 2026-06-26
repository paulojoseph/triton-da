#!/bin/bash
# Install the verifier-only dependency (pytest). Prefer uv; fall back to a
# system-wide pip install if uv is unavailable. The agent never needs this.
uv pip install --system pytest==8.3.4 2>/dev/null \
  || python3 -m pip install --no-cache-dir --break-system-packages pytest==8.3.4
python3 -m pytest /tests/test_outputs.py "$@"
if [ $? -eq 0 ]; then
    mkdir -p /logs/verifier
    echo "1" > /logs/verifier/reward.txt
else
    mkdir -p /logs/verifier
    echo "0" > /logs/verifier/reward.txt
fi
