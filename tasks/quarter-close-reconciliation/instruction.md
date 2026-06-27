We're closing the books for the quarter and the cash accounts won't reconcile. Under `/app/sources/` you'll find, for each of our bank accounts, the bank's own statement lines next to the entries our accounting system posted against that account. They came out of different systems and nobody normalised them: dates, number formats, currencies and debit/credit conventions all differ between the two sides, a few statement files were imported twice, and plenty of items simply don't line up — bank charges we never booked, deposits still in transit, foreign-currency postings recorded at a different rate, and a handful of genuine posting mistakes.

Reconcile each account the way a group accountant would and write the result to `/app/reconciliation.json`. For every account, pair each bank statement line with the single ledger entry that settles it, list whatever is left unmatched on each side, and report each side's closing balance and the difference that remains. Work in USD throughout; `/app/fx_rates.csv` holds the daily rates (USD per unit of currency, by value date). A bank line and a ledger entry settle each other when their USD amounts, rounded to the cent, are equal and their value dates are at most five calendar days apart; matching is one-to-one. When more than one candidate fits a line, take the smallest date gap, then the lowest ledger entry id, and never reuse a line in two pairs. Imported duplicates (a statement line repeated with the same account, value date, amount and bank reference) count once.

Write `/app/reconcile.py` so that `python3 /app/reconcile.py` rebuilds `/app/reconciliation.json` from whatever currently sits under `/app/sources/` — we run the same close on the other entities, so it has to work from the files, not from anything hard-coded.

`/app/reconciliation.json` is a JSON object keyed by `account_id` (the string used in the source files). Each value is an object with exactly these keys:

- `matched`: a list of `[bank_line_id, ledger_entry_id]` pairs (the ids the source files give each line), ordered by `bank_line_id`.
- `unmatched_bank`: a sorted list of `bank_line_id` with no settling ledger entry.
- `unmatched_ledger`: a sorted list of `ledger_entry_id` with no settling bank line.
- `bank_close_usd`: the account's closing bank balance — the sum of its bank statement lines in USD, rounded to 2 decimals.
- `ledger_close_usd`: the sum of the account's ledger entries in USD, rounded to 2 decimals.
- `residual_usd`: `bank_close_usd − ledger_close_usd`, rounded to 2 decimals.
