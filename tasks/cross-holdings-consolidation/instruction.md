Compute the group's effective interest and the non-controlling interest (NCI) for a corporate group whose ownership includes reciprocal (cross) holdings. Write `/app/consolidate.py` so that running `python3 /app/consolidate.py` reads the CSV files under `/app/data/` and writes `/app/output.json`. Use only the Python standard library. Money amounts in the output are USD rounded to 2 decimals using round-half-up.

Inputs under `/app/data/`:
- `entities.csv` — columns `entity_id, equity, is_parent`. `equity` is the entity's standalone book equity in USD (an integer or decimal). Exactly one row has `is_parent` set to `1`: that is the top reporting parent `P`; every other row has `is_parent` empty.
- `ownership.csv` — columns `owner_id, owned_id, fraction`. Each row says that `owner_id` directly owns `fraction` (a decimal in (0, 1]) of `owned_id`. This is a general directed graph: an entity can be owned by several owners, ownership can run through many tiers, and it can be **reciprocal** — an entity may be owned (directly or indirectly) by an entity that it itself owns, forming a cycle. Some owners may be outside the group (an `owner_id` that never appears as an `entity_id`); their share is simply held outside the group. The parent `P` is owned only from outside the group.

## Effective interest

The group's effective interest `g(e)` in an entity `e` is the proportion of `e` ultimately attributable to the top parent `P` through every direct and indirect holding, reciprocal holdings included. It is defined by:

- `g(P) = 1`, and
- for every other entity `e`, `g(e) = Σ fraction(o, e) · g(o)` summed over every owner `o` of `e` that belongs to the group (owners outside the group contribute nothing).

When the ownership graph has no cycles this is just the sum over ownership paths from `P`. When it has cycles the two definitions above still pin a single set of values `g(e)` — they are a system of simultaneous equations, not a one-pass walk down the tree.

## Non-controlling interest

For each entity `e`, the non-controlling interest in its equity is `nci(e) = (1 − g(e)) · equity(e)`, rounded half-up to cents. (`nci(P) = 0`.)

## Output

Write `/app/output.json` as one JSON object with exactly these keys:
- `effective_interest`: an object mapping every `entity_id` to its `g(e)` (a number; `P` maps to `1.0`).
- `nci`: an object mapping every `entity_id` to its `nci(e)` in USD.
- `nci_total`: the sum of the per-entity `nci(e)` values.

## Worked examples

1. **No cycles.** `P` owns 0.80 of `A`; `A` owns 0.50 of `B`; nothing else. Then `g(A) = 0.80`, `g(B) = 0.80 · 0.50 = 0.40`. With `equity(A) = 50000`, `nci(A) = (1 − 0.80) · 50000 = 10000.00`.

2. **Reciprocal holding (the sample data).** Entities `P` (equity 100000, parent), `A` (50000), `B` (30000), `C` (20000); ownership `P→A 0.80`, `P→B 0.60`, `A→C 0.50`, `C→A 0.20`, `B→C 0.30`. Because `A` owns `C` (through `A→C`) while `C` owns part of `A` (`C→A`), `A` and `C` form a cycle, so the values solve together:
   - `g(B) = 0.60`,
   - `g(A) = 0.80 + 0.20 · g(C)` and `g(C) = 0.50 · g(A) + 0.30 · g(B)`, which give `g(A) = 0.928889…` and `g(C) = 0.644444…` (not the one-pass `g(A) = 0.80`, `g(C) = 0.58`).
   - `nci(A) = (1 − 0.928889…) · 50000 = 3555.56`, `nci(B) = 12000.00`, `nci(C) = 7111.11`, `nci(P) = 0.00`, so `nci_total = 22666.67`.

Report `effective_interest` to full precision (do not pre-round it); only the `nci` figures are rounded to cents.
