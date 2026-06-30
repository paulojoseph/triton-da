"""Reference solution for crdt-causal-merge.

Reads every /app/data/replicas/*.log, replays the edits under causal delivery,
and writes the converged document to /app/result.json. The converged state is
computed from the applied edit set via causal relations only, so it does not
depend on the order logs are read or edits are applied.
"""
import glob
import json
import os

REPLICA_DIR = "/app/data/replicas"
RESULT = "/app/result.json"


def deps_of(line):
    """Causal dependencies of an edit: own per-replica prefix plus vv entries."""
    d = set()
    r0 = line["replica"]
    for s in range(1, line["seq"]):
        d.add((r0, s))
    for r_str, val in line["vv"].items():
        r = int(r_str)
        for s in range(1, val + 1):
            d.add((r, s))
    return d


def applied_set(ops):
    keys = set(ops)
    deps = {k: deps_of(line) for k, line in ops.items()}
    ok = {k: deps[k].issubset(keys) for k in ops}
    changed = True
    while changed:
        changed = False
        for k in ops:
            if ok[k] and any(not ok.get(d, False) for d in deps[k]):
                ok[k] = False
                changed = True
    return {k for k, v in ok.items() if v}, deps


def merge(ops):
    applied, deps = applied_set(ops)

    # OR-Set, add-wins (observed-remove)
    adds, removes = {}, {}
    for k in applied:
        op = ops[k]["op"]
        if op["op"] == "set_add":
            adds.setdefault(op["elem"], []).append(k)
        elif op["op"] == "set_remove":
            removes.setdefault(op["elem"], []).append(k)
    tags = set()
    for tag, addk in adds.items():
        rem = removes.get(tag, [])
        for a in addk:
            if not any(a in deps[r] for r in rem):
                tags.add(tag)
                break

    # LWW register: largest ts, tie to larger replica
    best = None
    for k in applied:
        op = ops[k]["op"]
        if op["op"] == "reg_set":
            cand = (ops[k]["ts"], ops[k]["replica"], op["value"])
            if best is None or (cand[0], cand[1]) > (best[0], best[1]):
                best = cand
    register = ({"value": None, "winner": None} if best is None
                else {"value": best[2], "winner": [best[0], best[1]]})

    # RGA ordered list
    children, deleted = {}, set()
    for k in applied:
        op = ops[k]["op"]
        if op["op"] == "seq_insert":
            children.setdefault(op["after"], []).append(op)
        elif op["op"] == "seq_delete":
            deleted.add(op["id"])
    for anchor in children:
        children[anchor].sort(key=lambda ins: ins["id"], reverse=True)
    sequence = []
    stack = list(reversed(children.get(None, [])))
    while stack:
        node = stack.pop()
        if node["id"] not in deleted:
            sequence.append(node["value"])
        for child in reversed(children.get(node["id"], [])):
            stack.append(child)

    return {"set": sorted(tags), "register": register,
            "sequence": sequence, "applied": len(applied)}


def load_ops():
    ops = {}
    for path in sorted(glob.glob(os.path.join(REPLICA_DIR, "*.log"))):
        with open(path) as f:
            for raw in f:
                raw = raw.strip()
                if not raw:
                    continue
                line = json.loads(raw)
                key = (line["replica"], line["seq"])
                if key not in ops:
                    ops[key] = line
    return ops


def main():
    ops = load_ops()
    result = merge(ops)
    with open(RESULT, "w") as f:
        json.dump(result, f)


if __name__ == "__main__":
    main()
