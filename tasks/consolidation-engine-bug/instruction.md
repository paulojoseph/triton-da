Our group-consolidation engine lives under `/app`: the entry point `consolidate.py` plus the `congraph`, `fxtrans`, `icelim` and `invprofit` modules. Running `python3 /app/consolidate.py` reads the CSV files in `/app/data/` and writes the consolidated result to `/app/output.json`.

The engine has a defect. For the sample dataset in `/app/data/`, its output disagrees with the known-correct result recorded in `/app/expected_sample.json`. Find the defect and fix it so the engine produces correct consolidated figures.

A few things to keep in mind:

- The consolidation rules the engine is *meant* to implement are described in the module docstrings. Some of them are deliberately unusual for this group (how the imbalance sign is taken, how one-sided documents are eliminated, how the imbalance total is aggregated, which rate applies to which leg). That intended behaviour is correct — preserve it. Only the genuine defect should change.
- It is a code defect, not a data problem. Do not edit the CSV files or `expected_sample.json`; fixing the symptom by special-casing the sample will not work.
- The fix will be checked by re-running your `consolidate.py` on other datasets, so it needs to address the underlying cause rather than the one number that happens to be wrong on the sample.

When you are done, `python3 /app/consolidate.py` should reproduce `/app/expected_sample.json` for the sample data, and remain correct on other inputs of the same shape.
