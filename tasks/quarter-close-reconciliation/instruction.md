We're closing the books for the quarter and the cash accounts won't reconcile. Under `/app/sources/` you'll find, for each bank account, the bank's own statement lines next to the entries our accounting system posted against that account. They came out of different systems and nobody normalised them: dates, number formats, currencies and debit/credit conventions all differ between the two sides, a couple of statement files were imported twice, and plenty of items don't line up — bank charges we never booked, deposits still in transit, foreign-currency postings booked at a different rate, and a few genuine posting mistakes. Every statement line and ledger entry carries its own integer id from the source file.

Reconcile each account the way a group accountant would and write the result to `/app/reconciliation.json`. Treat money coming into the account as positive and money leaving it as negative on both sides. A bank line and a ledger entry settle each other when they are in the same currency, their amounts are equal, and their value dates are at most five calendar days apart. Match one-to-one and greedily: take the bank lines in ascending id order and settle each with the not-yet-used ledger entry that fits it, preferring the smallest date gap and then the lowest ledger entry id. Before matching, collapse imported duplicates — a statement line repeated with the same value date, amount and bank reference — into one, keeping the lowest id. For the closing balances, convert every line to USD with the rate in `/app/fx_rates.csv` for its value date — or the most recent earlier date listed when that day isn't (weekends, holidays) — round each converted line to the cent, and sum them per side.

Write `/app/reconcile.py` so that `python3 /app/reconcile.py` rebuilds `/app/reconciliation.json` from whatever currently sits under `/app/sources/` — we run the same close on the other entities, so it must work from the files, not from anything hard-coded.

`/app/reconciliation.json` is a JSON object keyed by `account_id` (the string the source files use). Each value is an object with exactly these keys:

- `matched`: list of `[bank_line_id, ledger_entry_id]` integer pairs, ordered by ascending `bank_line_id`.
- `unmatched_bank`: ascending list of the `bank_line_id` integers with no settling ledger entry.
- `unmatched_ledger`: ascending list of the `ledger_entry_id` integers with no settling bank line.
- `bank_close_usd`: the bank side's closing balance, rounded to 2 decimals.
- `ledger_close_usd`: the ledger side's closing balance, rounded to 2 decimals.
- `residual_usd`: `bank_close_usd − ledger_close_usd`, rounded to 2 decimals.
