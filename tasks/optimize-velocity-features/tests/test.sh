#!/bin/bash
# Pin verifier-only dependencies for reproducibility (the agent doesn't need them).
python3 -m pip install --no-cache-dir --break-system-packages pytest==8.3.4
python3 -m pytest /tests/test_outputs.py "$@"
if [ $? -eq 0 ]; then
    mkdir -p /logs/verifier
    echo "1" > /logs/verifier/reward.txt
else
    mkdir -p /logs/verifier
    echo "0" > /logs/verifier/reward.txt
fi
