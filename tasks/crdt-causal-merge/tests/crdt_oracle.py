"""Independent reference + hidden-instance generator for crdt-causal-merge.

`merge` computes the converged document from an edit set using causal relations
only (so it is order-independent). `make_instance` synthesizes a concurrent edit
history the agent never sees, returning per-replica logs plus the expected
output. `shuffle_deliveries` re-delivers the SAME edit multiset under different
file partitions and orderings, which the verifier uses to demand byte-identical
output from the agent's program.
"""
import json
import random


# --------------------------------------------------------------- oracle
def deps_of(line):
    d = set()
    r0 = line["replica"]
    for s in range(1, line["seq"]):
        d.add((r0, s))
    for r_str, val in line["vv"].items():
        r = int(r_str)
        for s in range(1, val + 1):
            d.add((r, s))
    return d


def _applied_set(ops):
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


def merge_ops(ops):
    applied, deps = _applied_set(ops)
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
    best = None
    for k in applied:
        op = ops[k]["op"]
        if op["op"] == "reg_set":
            cand = (ops[k]["ts"], ops[k]["replica"], op["value"])
            if best is None or (cand[0], cand[1]) > (best[0], best[1]):
                best = cand
    register = ({"value": None, "winner": None} if best is None
                else {"value": best[2], "winner": [best[0], best[1]]})
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


def merge_logs(logs):
    """logs: dict replica_id -> list of lines (the same edit may repeat)."""
    ops = {}
    for _owner, lines in logs.items():
        for line in lines:
            key = (line["replica"], line["seq"])
            if key not in ops:
                ops[key] = line
    return merge_ops(ops)


# --------------------------------------------------------------- generator
def _gen_history(rng, replicas, steps):
    ids = list(range(1, replicas + 1))
    vv = {i: {j: 0 for j in ids} for i in ids}
    own = {i: 0 for i in ids}
    allops = {}
    ts_counter = [0]
    tag_alpha = ["x", "y", "z", "w"]
    elem_counter = [0]

    def seen_inserts(i):
        return [line["op"]["id"] for (r, s), line in allops.items()
                if s <= vv[i][r] and line["op"]["op"] == "seq_insert"]

    for _ in range(steps):
        if rng.random() < 0.35 and any(vv[i] != vv[j] for i in ids for j in ids):
            i, j = rng.sample(ids, 2)
            for r in ids:
                vv[i][r] = max(vv[i][r], vv[j][r])
            continue
        i = rng.choice(ids)
        own[i] += 1
        seq = own[i]
        snap = {str(r): vv[i][r] for r in ids if vv[i][r] > 0}
        snap[str(i)] = seq - 1
        if snap[str(i)] == 0:
            del snap[str(i)]
        kind = rng.choice(["set_add", "set_remove", "reg_set",
                           "seq_insert", "seq_insert", "seq_delete"])
        seen = seen_inserts(i)
        if kind == "seq_delete" and not seen:
            kind = "seq_insert"
        if kind == "set_add":
            op = {"op": "set_add", "elem": rng.choice(tag_alpha)}
        elif kind == "set_remove":
            op = {"op": "set_remove", "elem": rng.choice(tag_alpha)}
        elif kind == "reg_set":
            op = {"op": "reg_set", "value": "v%d" % rng.randint(0, 999)}
        elif kind == "seq_insert":
            elem_counter[0] += 1
            eid = "e%d-%d" % (i, elem_counter[0])
            after = rng.choice(seen) if (seen and rng.random() < 0.7) else None
            op = {"op": "seq_insert", "id": eid, "after": after,
                  "value": "n%d" % elem_counter[0]}
        else:
            op = {"op": "seq_delete", "id": rng.choice(seen)}
        ts_counter[0] += 1
        line = {"replica": i, "seq": seq, "vv": snap, "ts": ts_counter[0], "op": op}
        allops[(i, seq)] = line
        vv[i][i] = seq
    return ids, vv, allops


def make_instance(name, seed, replicas=4, steps=70, orphan=True):
    """Return (logs, expected). logs: replica_id -> list of lines."""
    rng = random.Random(seed)
    ids, vv, allops = _gen_history(rng, replicas, steps)
    logs = {}
    for i in ids:
        hist = [allops[(r, s)] for (r, s) in allops if s <= vv[i][r]]
        rng.shuffle(hist)
        logs[i] = hist
    seen_keys = set()
    for i in ids:
        for ln in logs[i]:
            seen_keys.add((ln["replica"], ln["seq"]))
    for (r, s), line in allops.items():
        if (r, s) not in seen_keys:
            logs[r].append(line)
    if orphan:
        # an edit whose dependencies never arrive: must be excluded from output
        orphan_line = {"replica": 99, "seq": 5, "vv": {"99": 4}, "ts": 10 ** 9,
                       "op": {"op": "reg_set", "value": "ORPHAN_MUST_NOT_WIN"}}
        logs[ids[0]].append(orphan_line)
    expected = merge_logs(logs)
    return logs, expected


def shuffle_deliveries(logs, k, seed):
    """k alternative deliveries of the same edit multiset across the same files."""
    rng = random.Random(seed)
    ids = list(logs.keys())
    pool = {}
    for _i, lines in logs.items():
        for ln in lines:
            pool[(ln["replica"], ln["seq"])] = ln
    alllines = list(pool.values())
    variants = []
    for _ in range(k):
        files = {i: [] for i in ids}
        for ln in alllines:
            targets = [i for i in ids if rng.random() < 0.5] or [rng.choice(ids)]
            for t in targets:
                files[t].append(ln)
        for i in ids:
            rng.shuffle(files[i])
        variants.append(files)
    return variants


def write_logs(directory, logs):
    import os
    os.makedirs(directory, exist_ok=True)
    for existing in os.listdir(directory):
        if existing.endswith(".log"):
            os.remove(os.path.join(directory, existing))
    for rid, lines in logs.items():
        with open(os.path.join(directory, "%d.log" % rid), "w") as f:
            for ln in lines:
                f.write(json.dumps(ln) + "\n")
