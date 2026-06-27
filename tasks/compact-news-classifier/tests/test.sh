#!/bin/bash
# Offline-safe verifier: the model is graded with the in-image scikit-learn /
# numpy / scipy stack, so no network access and no pytest install are needed at
# verify time. The checks live in /tests/test_outputs.py.
python3 - <<'PY'
import sys
sys.path.insert(0, "/tests")
import test_outputs as t

failed = []
for name in ("test_model_size", "test_accuracy"):
    try:
        getattr(t, name)()
        print(f"{name}: PASS")
    except Exception as e:
        print(f"{name}: FAIL: {e}")
        failed.append(name)
sys.exit(1 if failed else 0)
PY
rc=$?
mkdir -p /logs/verifier
if [ $rc -eq 0 ]; then
    echo "1" > /logs/verifier/reward.txt
else
    echo "0" > /logs/verifier/reward.txt
fi
