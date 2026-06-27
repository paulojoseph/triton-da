"""Deterministic generator of messy, multi-source bank/ledger data plus the
golden reconciliation. Used only by the verifier (never shipped in the image),
so the agent never sees the answers and must recover them from the files.

The same three bank formats and one ERP ledger format are reused for every
generated entity; only the values change with the seed, mirroring how the same
systems export every subsidiary's books.
"""
import os
import csv
import random
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP

CENT = Decimal("0.01")
MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
          "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def rc(x):
    return Decimal(x).quantize(CENT, rounding=ROUND_HALF_UP)


# --------------------------------------------------------------------------- #
# FX table: USD per one unit of currency, weekdays only (so weekend value dates
# must fall back to the most recent earlier listed date).
# --------------------------------------------------------------------------- #
def build_fx(rng, start, days):
    table = {}
    bases = {"USD": Decimal("1"), "EUR": Decimal("1.0850"),
             "GBP": Decimal("1.2700"), "CHF": Decimal("1.1200")}
    for ccy, base in bases.items():
        series = {}
        rate = base
        for i in range(days):
            d = start + timedelta(days=i)
            if d.weekday() >= 5:        # skip Sat/Sun
                continue
            if ccy != "USD":
                rate = (rate + Decimal(rng.randint(-40, 40)) / Decimal("10000"))
                rate = max(Decimal("0.50"), rate)
            series[d] = (Decimal("1") if ccy == "USD" else rate.quantize(Decimal("0.0001")))
        table[ccy] = series
    return table


def fx_rate(table, ccy, d):
    series = table[ccy]
    if d in series:
        return series[d]
    best = None
    for dd in sorted(series):
        if dd <= d:
            best = dd
        else:
            break
    return series[best]


# --------------------------------------------------------------------------- #
# Spec reconciliation (the golden). Operates on already-parsed rows.
# row = {"id": int, "d": date, "amt": Decimal (signed, account/ccy units, money
#        IN positive), "ccy": str, "ref": str}
# --------------------------------------------------------------------------- #
def _usd(table, row):
    return rc(row["amt"] * fx_rate(table, row["ccy"], row["d"]))


def reconcile_account(bank_rows, ledger_rows, table):
    # collapse imported duplicates (same value date, amount, ref); keep lowest id
    seen = {}
    for r in sorted(bank_rows, key=lambda r: r["id"]):
        key = (r["d"], r["amt"], r["ccy"], r["ref"])
        if key not in seen:
            seen[key] = r
    bank = sorted(seen.values(), key=lambda r: r["id"])

    bank_usd = {r["id"]: _usd(table, r) for r in bank}
    led_usd = {r["id"]: _usd(table, r) for r in ledger_rows}
    bank_by_id = {r["id"]: r for r in bank}
    led_by_id = {r["id"]: r for r in ledger_rows}

    used = set()
    matched = []
    for b in bank:
        cands = []
        for lr in ledger_rows:
            if lr["id"] in used:
                continue
            if lr["ccy"] != b["ccy"] or lr["amt"] != b["amt"]:
                continue
            gap = abs((lr["d"] - b["d"]).days)
            if gap <= 5:
                cands.append((gap, lr["id"]))
        if cands:
            cands.sort()
            lid = cands[0][1]
            used.add(lid)
            matched.append([b["id"], lid])
    matched.sort(key=lambda p: p[0])

    matched_bank = {p[0] for p in matched}
    unmatched_bank = sorted(r["id"] for r in bank if r["id"] not in matched_bank)
    unmatched_ledger = sorted(r["id"] for r in ledger_rows if r["id"] not in used)

    bank_close = rc(sum((bank_usd[r["id"]] for r in bank), Decimal("0")))
    ledger_close = rc(sum((led_usd[r["id"]] for r in ledger_rows), Decimal("0")))
    return {
        "matched": matched,
        "unmatched_bank": unmatched_bank,
        "unmatched_ledger": unmatched_ledger,
        "bank_close_usd": float(bank_close),
        "ledger_close_usd": float(ledger_close),
        "residual_usd": float(rc(bank_close - ledger_close)),
    }


# --------------------------------------------------------------------------- #
# Data generation
# --------------------------------------------------------------------------- #
ACCOUNTS = [
    ("NORDIC-EUR-01", "EUR", "eubank"),
    ("LONDON-GBP-02", "GBP", "ukbank"),
    ("DELTA-USD-03", "USD", "usbank"),
]


def _money(rng):
    return (Decimal(rng.randint(50, 90000)) + Decimal(rng.randint(0, 99)) / 100)


def generate(seed):
    rng = random.Random(seed)
    start = date(2026, 1, 5)
    table = build_fx(rng, start - timedelta(days=10), 130)
    entity = {"accounts": [], "fx": table}

    for account_id, ccy, fmt in ACCOUNTS:
        bank_rows, ledger_rows = [], []
        bid = rng.randint(1, 9)        # ids start at different bases per file
        lid = rng.randint(1, 9)
        ref_n = 1000 + rng.randint(0, 500)

        def next_ref():
            nonlocal ref_n
            ref_n += rng.randint(1, 7)
            return f"REF{ref_n}"

        n_pairs = rng.randint(9, 13)
        for _ in range(n_pairs):
            d = start + timedelta(days=rng.randint(0, 90))
            sign = 1 if rng.random() < 0.55 else -1
            amt = (sign * _money(rng)).quantize(CENT)
            ref = next_ref()
            bank_rows.append({"id": bid, "d": d, "amt": amt, "ccy": ccy, "ref": ref})
            bid += 1
            ld = d + timedelta(days=rng.randint(0, 4))      # within 5-day window
            ledger_rows.append({"id": lid, "d": ld, "amt": amt, "ccy": ccy, "ref": ref})
            lid += 1

        # a couple of foreign-currency ledger postings booked at the wrong rate
        for _ in range(rng.randint(1, 2)):
            d = start + timedelta(days=rng.randint(0, 90))
            fccy = rng.choice([c for c in ("EUR", "GBP", "CHF") if c != ccy])
            amt = (_money(rng)).quantize(CENT)
            ref = next_ref()
            bank_rows.append({"id": bid, "d": d, "amt": amt, "ccy": ccy, "ref": ref})
            bid += 1
            # ledger booked the foreign amount at a stale rate -> USD won't tie
            ledger_rows.append({"id": lid, "d": d, "amt": (amt * Decimal("1.03")).quantize(CENT),
                                "ccy": fccy, "ref": ref})
            lid += 1

        # bank-only charges (unmatched_bank)
        for _ in range(rng.randint(2, 3)):
            d = start + timedelta(days=rng.randint(0, 90))
            amt = (-(Decimal(rng.randint(3, 60)) + Decimal(rng.randint(0, 99)) / 100)).quantize(CENT)
            bank_rows.append({"id": bid, "d": d, "amt": amt, "ccy": ccy, "ref": next_ref()})
            bid += 1

        # deposits in transit (unmatched_ledger)
        for _ in range(rng.randint(2, 3)):
            d = start + timedelta(days=rng.randint(80, 95))
            amt = (_money(rng)).quantize(CENT)
            ledger_rows.append({"id": lid, "d": d, "amt": amt, "ccy": ccy, "ref": next_ref()})
            lid += 1

        # a genuine posting error (ledger amount off by a lot -> unmatched both sides)
        d = start + timedelta(days=rng.randint(0, 90))
        amt = _money(rng).quantize(CENT)
        ref = next_ref()
        bank_rows.append({"id": bid, "d": d, "amt": amt, "ccy": ccy, "ref": ref})
        bid += 1
        ledger_rows.append({"id": lid, "d": d, "amt": (amt + Decimal("100.00")).quantize(CENT),
                            "ccy": ccy, "ref": ref})
        lid += 1

        # imported duplicates: repeat a couple of bank lines verbatim (new id)
        for src in rng.sample(bank_rows, k=min(2, len(bank_rows))):
            bank_rows.append({"id": bid, "d": src["d"], "amt": src["amt"],
                              "ccy": src["ccy"], "ref": src["ref"]})
            bid += 1

        rng.shuffle(bank_rows)
        rng.shuffle(ledger_rows)
        entity["accounts"].append({
            "account_id": account_id, "ccy": ccy, "fmt": fmt,
            "bank_rows": bank_rows, "ledger_rows": ledger_rows,
        })
    return entity


def golden(entity):
    return {a["account_id"]: reconcile_account(a["bank_rows"], a["ledger_rows"], entity["fx"])
            for a in entity["accounts"]}


# --------------------------------------------------------------------------- #
# Messy serialisers (write what the agent actually parses)
# --------------------------------------------------------------------------- #
def _fmt_eu_amount(amt):           # 1.234,56  /  -1.234,56
    neg = amt < 0
    s = f"{abs(amt):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return ("-" + s) if neg else s


def _fmt_paren_amount(amt):        # 1,234.56  /  (1,234.56)
    s = f"{abs(amt):,.2f}"
    return f"({s})" if amt < 0 else s


def _eu_date(d):
    return f"{d.day:02d} {MONTHS[d.month - 1]} {d.year}"


def _write_bank(path, fmt, rows):
    if fmt == "eubank":
        with open(path, "w", newline="") as f:
            w = csv.writer(f, delimiter=";")
            w.writerow(["LineNo", "ValueDate", "Reference", "Amount", "Ccy"])
            for r in rows:
                w.writerow([r["id"], _eu_date(r["d"]), r["ref"], _fmt_eu_amount(r["amt"]), r["ccy"]])
    elif fmt == "ukbank":
        with open(path, "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["id", "date", "description", "amount", "currency", "ref"])
            for r in rows:
                w.writerow([r["id"], r["d"].isoformat(), "PAYMENT",
                            _fmt_paren_amount(r["amt"]), r["ccy"], r["ref"]])
    else:  # usbank, pipe-delimited, YYYY/MM/DD
        with open(path, "w", newline="") as f:
            f.write("TxnId|ValueDate|Amount|CUR|Ref\n")
            for r in rows:
                f.write(f"{r['id']}|{r['d'].year}/{r['d'].month:02d}/{r['d'].day:02d}|"
                        f"{r['amt']:.2f}|{r['ccy']}|{r['ref']}\n")


def _write_ledger(path, account_id, rows):
    # ERP export: minor units + DR/CR; DR increases the cash asset (money in).
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["EntryId", "Account", "PostDate", "DocRef", "AmountMinor", "DrCr", "Currency"])
        for r in rows:
            minor = int((abs(r["amt"]) * 100).to_integral_value())
            drcr = "DR" if r["amt"] >= 0 else "CR"
            w.writerow([r["id"], account_id, f"{r['d'].year}{r['d'].month:02d}{r['d'].day:02d}",
                        r["ref"], minor, drcr, r["ccy"]])


def write_sources(entity, root):
    src = os.path.join(root, "sources")
    os.makedirs(src, exist_ok=True)
    for a in entity["accounts"]:
        adir = os.path.join(src, a["account_id"])
        os.makedirs(adir, exist_ok=True)
        _write_bank(os.path.join(adir, "statement.csv" if a["fmt"] != "usbank" else "statement.txt"),
                    a["fmt"], a["bank_rows"])
        _write_ledger(os.path.join(adir, "ledger.csv"), a["account_id"], a["ledger_rows"])
    # fx rates
    with open(os.path.join(root, "fx_rates.csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["currency", "date", "rate"])
        for ccy in sorted(entity["fx"]):
            for d in sorted(entity["fx"][ccy]):
                w.writerow([ccy, d.isoformat(), f"{entity['fx'][ccy][d]}"])
