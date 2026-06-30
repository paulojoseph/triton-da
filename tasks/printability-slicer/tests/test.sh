#!/bin/bash
# Pin verifier-only deps (pytest). Prefer uv; fall back to a system-wide pip install.
uv pip install --system pytest==8.3.4 2>/dev/null \
  || python3 -m pip install --no-cache-dir --break-system-packages pytest==8.3.4
python3 -m pytest /tests/test_outputs.py -rA "$@"
rc=$?
mkdir -p /logs/verifier
if [ $rc -eq 0 ]; then
    echo "1" > /logs/verifier/reward.txt
else
    echo "0" > /logs/verifier/reward.txt
fi
exit $rc
