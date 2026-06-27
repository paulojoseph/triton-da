Build the intercompany elimination engine for our group consolidation. Write `/app/consolidate.py` so that running `python3 /app/consolidate.py` reads the CSV files under `/app/data/` and writes `/app/output.json`. The reporting (group) currency is USD. Use only the Python standard library. All money amounts in the output are USD rounded to 2 decimals using round-half-up.

Inputs under `/app/data/`:
- `entities.csv` — columns `entity_id, functional_ccy, parent_id, ownership_pct`. The top reporting parent has an empty `parent_id` and empty `ownership_pct`. Every other entity is a subsidiary whose `parent_id` is another `entity_id`; `ownership_pct` (a decimal in [0,1]) is the fraction of that subsidiary owned directly by its parent. A subsidiary's parent may itself be a subsidiary, so ownership can run through several tiers up to the top parent.
- `fx_rates.csv` — columns `ccy, closing_rate, average_rate`. A rate is USD per 1 unit of `ccy` (e.g. `EUR,1.10,1.08` means 1 EUR = 1.10 USD at closing, 1.08 USD on average). USD is present with both rates `1.0`.
- `ic_transactions.csv` — one row per LEG: `doc_id, entity_id, leg_type, amount, currency`. `amount` is in the leg's `currency` (the booking entity's functional currency). `leg_type` is one of `AR, AP, REVENUE, EXPENSE, DIV_INCOME, DIV_PAID`. The two legs of one intercompany transaction share a `doc_id`. A document has at most one A-side leg (`AR`, `REVENUE`, or `DIV_INCOME`) and at most one B-side leg (`AP`, `EXPENSE`, or `DIV_PAID`); the two legs of a document are always the matching pair within one category (AR↔AP, REVENUE↔EXPENSE, or DIV_INCOME↔DIV_PAID). Some documents have only one leg.
- `profit_in_inventory.csv` — columns `seller_id, buyer_id, unrealized_profit, currency`. Unrealized profit (in `currency`) still held in group inventory from an intercompany sale.

## Translating each leg to USD

Translate every leg amount to USD as `amount × rate`, then round half-up to 2 decimals. The rate depends on the leg type:
- `AR`, `AP`, `DIV_INCOME`, `DIV_PAID` use the **closing** rate.
- `REVENUE`, `EXPENSE` use the **average** rate.

## Per-document elimination

For each `doc_id`, let `usd_a` be its A-side leg in USD and `usd_b` be its B-side leg in USD; a missing leg counts as `0.00`. Then:
- `eliminated_usd = min(usd_a, usd_b)`.
- `imbalance_usd = usd_a − usd_b` (signed; A-side minus B-side).
- `classification`:
  - `one_sided` if exactly one of the two legs is present;
  - otherwise (both legs present) let `diff = |usd_a − usd_b|` and `tolerance = max(1.00, 0.005 × max(usd_a, usd_b))`, and classify as `matched` if `diff == 0`, `within_tolerance` if `0 < diff ≤ tolerance`, or `out_of_tolerance` if `diff > tolerance`. The classification never changes how `eliminated_usd`/`imbalance_usd` are computed.

A document's category is `ar_ap` (AR/AP legs), `rev_exp` (REVENUE/EXPENSE legs), or `div` (DIV_INCOME/DIV_PAID legs).

## Profit in inventory and non-controlling interest

For each row of `profit_in_inventory.csv`, translate `unrealized_profit` to USD at the **average** rate (round half-up to 2 decimals); the full amount is eliminated. Split off the non-controlling-interest (NCI) portion by direction of the sale:
- **Upstream** (the `seller_id` is a subsidiary): `nci = unrealized_profit_usd × (1 − g)`, round half-up to 2 decimals, where `g` is the group's effective ownership of the seller — the product of `ownership_pct` along the chain of parents from the seller up to the top reporting parent. For a subsidiary held directly by the top parent, `g` is just its own `ownership_pct`; for one held through another subsidiary, `g` is the product of every link in the chain.
- **Downstream** (the `seller_id` is the top reporting parent): `nci = 0.00`.

## Output

Write `/app/output.json` as one JSON object with exactly two keys:
- `documents`: an object mapping each `doc_id` to `{"eliminated_usd": ..., "imbalance_usd": ..., "classification": ...}`.
- `totals`: an object with exactly `eliminated_ar_ap_usd`, `eliminated_rev_exp_usd`, `eliminated_dividends_usd` (sums of `eliminated_usd` over the `ar_ap`, `rev_exp`, and `div` documents respectively), `ic_imbalance_usd` (the signed sum of every document's `imbalance_usd`), `pip_eliminated_usd` (total unrealized profit eliminated), and `pip_nci_usd` (total NCI portion).

## Worked examples (each pins one rule)

1. Closing-rate AR vs AP, within tolerance. Doc D1: `AR` 1000.00 EUR (closing 1.10) → `usd_a = 1100.00`; `AP` 1095.00 USD → `usd_b = 1095.00`. `eliminated_usd = 1095.00`, `imbalance_usd = +5.00`. `tolerance = max(1.00, 0.005×1100.00) = 5.50`, `diff = 5.00 ≤ 5.50` → `within_tolerance`. Counts in `eliminated_ar_ap_usd`.
2. Out of tolerance. Same as D1 but `AP` is 1080.00 USD → `usd_b = 1080.00`, `diff = 20.00 > 5.50` → `out_of_tolerance`; still `eliminated_usd = 1080.00`, `imbalance_usd = +20.00`.
3. Average-rate REVENUE vs EXPENSE. Doc D3: `REVENUE` 2000.00 EUR (average 1.08) → `usd_a = 2160.00`; `EXPENSE` 2200.00 USD → `usd_b = 2200.00`. `eliminated_usd = 2160.00`, `imbalance_usd = −40.00`. Counts in `eliminated_rev_exp_usd`.
4. One-sided. Doc D4: only an `AR` leg, 150000 JPY (closing 0.0068) → `usd_a = 1020.00`, `usd_b = 0.00`. `eliminated_usd = 0.00`, `imbalance_usd = +1020.00`, `classification = one_sided`.
5. Dividend. Doc D5: `DIV_INCOME` 500.00 USD → `usd_a = 500.00`; `DIV_PAID` 460.00 EUR (closing 1.10) → `usd_b = 506.00`. `eliminated_usd = 500.00`, `imbalance_usd = −6.00`. Counts in `eliminated_dividends_usd`, not in `eliminated_rev_exp_usd`.
6. Upstream profit in inventory, direct subsidiary. Seller is subsidiary `FR`, owned 0.80 directly by the top parent, so `g = 0.80`; `unrealized_profit` 1000.00 EUR (average 1.08) → 1080.00 USD eliminated; `nci = 1080.00 × (1 − 0.80) = 216.00`.
7. Downstream profit in inventory. Seller is the top parent `US`; `unrealized_profit` 500.00 USD → 500.00 USD eliminated; `nci = 0.00`.
8. Upstream profit from a lower-tier subsidiary. The top parent owns `FR` 0.80, and `FR` owns `FR2` 0.50, so the group's effective ownership of `FR2` is `g = 0.80 × 0.50 = 0.40`. Seller `FR2`, `unrealized_profit` 1000.00 EUR (average 1.08) → 1080.00 USD eliminated; `nci = 1080.00 × (1 − 0.40) = 648.00` (not `1080.00 × (1 − 0.50) = 540.00`). The chain can be deeper still — if `FR2` in turn owns `FR3` 0.90, then `g(FR3) = 0.80 × 0.50 × 0.90 = 0.36`.
9. Rounding ties go up. Doc D7: `AR` 8009 AUD (closing 1.125) → `8009 × 1.125 = 9010.125`, which rounds half-up to `usd_a = 9010.13` (not `9010.12`); `AP` 9010.13 USD → `usd_b = 9010.13`. So `eliminated_usd = 9010.13`, `imbalance_usd = 0.00`, `classification = matched`. (Plain `round()` in Python rounds halves to even and would wrongly give `9010.12`.)
