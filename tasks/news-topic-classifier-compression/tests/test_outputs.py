"""Verifier for news-topic-classifier-compression.

Checks the agent's /app/model.pkl on a held-out test set the agent never sees:
the artifact must be at most 1 MiB AND reach >= 0.68 accuracy. The model is
loaded with a restricted unpickler that only admits numpy/scipy/scikit-learn
classes, so a hand-crafted pickle cannot execute code (read the hidden labels,
tamper with the reward, etc.); only the texts are handed to the model and the
labels stay with the verifier.
"""
import io
import os
import json
import pickle

MODEL = "/app/model.pkl"
TEST = os.path.join(os.path.dirname(__file__), "test.jsonl")
SIZE_LIMIT = 1048576          # 1 MiB
ACC_BAR = 0.68

_ALLOWED_TOP = {"numpy", "scipy", "sklearn"}
_SAFE = {("collections", "OrderedDict"), ("builtins", "range"),
         ("builtins", "complex"), ("builtins", "set"),
         ("builtins", "frozenset"), ("builtins", "bytearray")}


class _RestrictedUnpickler(pickle.Unpickler):
    def find_class(self, module, name):
        if module.split(".")[0] in _ALLOWED_TOP:
            return super().find_class(module, name)
        if (module, name) in _SAFE:
            return super().find_class(module, name)
        raise pickle.UnpicklingError(f"disallowed class while loading model: {module}.{name}")


def _load_test():
    texts, labels = [], []
    with open(TEST) as f:
        for line in f:
            o = json.loads(line)
            texts.append(o["text"])
            labels.append(int(o["label"]))
    return texts, labels


def test_model_size():
    """The saved model artifact must be at most 1 MiB."""
    assert os.path.exists(MODEL), "/app/model.pkl was not produced."
    size = os.path.getsize(MODEL)
    assert size <= SIZE_LIMIT, f"model.pkl is {size} bytes, over the {SIZE_LIMIT}-byte (1 MiB) limit."


def test_accuracy():
    """The model must reach at least 0.68 accuracy on the held-out test set."""
    texts, labels = _load_test()
    with open(MODEL, "rb") as f:
        model = _RestrictedUnpickler(f).load()
    preds = model.predict(texts)
    preds = list(preds)
    assert len(preds) == len(labels), f"model returned {len(preds)} predictions for {len(labels)} inputs."
    correct = sum(1 for p, y in zip(preds, labels) if int(p) == y)
    acc = correct / len(labels)
    assert acc >= ACC_BAR, f"accuracy {acc:.4f} is below the required {ACC_BAR}."
