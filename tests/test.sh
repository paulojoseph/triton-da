#!/bin/bash
# Pinar rigidamente as versoes para garantir reproducibilidade absoluta ao longo do tempo
python3 -m pip install --no-cache-dir --break-system-packages psutil==6.1.1 pytest==8.3.4
python3 -m pytest /tests/test_outputs.py "$@"
if [ $? -eq 0 ]; then
    mkdir -p /logs/verifier
    echo "1" > /logs/verifier/reward.txt
else
    mkdir -p /logs/verifier
    echo "0" > /logs/verifier/reward.txt
fi