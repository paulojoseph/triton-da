#!/usr/bin/env python3
"""Reference quarter-close reconciliation.

Parses the heterogeneous bank statements and ERP ledger exports under
/app/sources, converts every line to USD via /app/fx_rates.csv, collapses
imported duplicate statement lines, and one-to-one greedily matches bank lines
to settling ledger entries.
"""
import csv
import json
import os
from datetime import date
from decimal import Decimal, ROUND_HALF_UP

ROOT = "/app"
SOURCES = os.path.join(ROOT, "sources")
CENT = Decimal("0.01")
MONTHS = {m: i + 1 for i, m in enumerate(
    ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
     "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"])}


def rc(x):
    return Decimal(x).quantize(CENT, rounding=ROUND_HALF_UP)


# ----- FX -----
def load_fx(path):
    table = {}
    with open(path, newline="") as f:
        for row in csv.DictReader(f):
            table.setdefault(row["currency"], {})[date.fromisoformat(row["date"])] = Decimal(row["rate"])
    return table


def fx_rate(table, ccy, d):
    if ccy not in table:
        return Decimal("1")
    series = table[ccy]
    if d in series:
        return series[d]
    best = None
    for dd in sorted(series):
        if dd <= d:
            best = dd
        else:
            break
    return series[best] if best is not None else Decimal("1")


# ----- date / amount parsing -----
def parse_date(s):
    s = s.strip()
    if " " in s:                                   # DD Mon YYYY
        dd, mon, yy = s.split()
        return date(int(yy), MONTHS[mon[:3].title()], int(dd))
    if "-" in s:                                   # YYYY-MM-DD
        return date.fromisoformat(s)
    if "/" in s:                                   # YYYY/MM/DD
        y, m, d = s.split("/")
        return date(int(y), int(m), int(d))
    return date(int(s[:4]), int(s[4:6]), int(s[6:8]))  # YYYYMMDD


def parse_eu(s):
    s = s.strip()
    neg = s.startswith("-")
    s = s.lstrip("-").replace(".", "").replace(",", ".")
    return -Decimal(s) if neg else Decimal(s)


def parse_paren(s):
    s = s.strip()
    neg = s.startswith("(")
    s = s.strip("()").replace(",", "")
    return -Decimal(s) if neg else Decimal(s)


def parse_plain(s):
    s = s.strip().replace(",", "")
    return Decimal(s)


# ----- source parsing -----
def parse_bank(adir):
    for name in os.listdir(adir):
        if not name.startswith("statement"):
            continue
        path = os.path.join(adir, name)
        with open(path, newline="") as f:
            head = f.readline().strip()
        if head.startswith("LineNo"):              # eubank, ';'
            rows = []
            with open(path, newline="") as f:
                for r in csv.DictReader(f, delimiter=";"):
                    rows.append({"id": int(r["LineNo"]), "d": parse_date(r["ValueDate"]),
                                 "amt": parse_eu(r["Amount"]), "ccy": r["Ccy"].strip(),
                                 "ref": r["Reference"].strip()})
            return rows
        if head.startswith("id,date"):             # ukbank, ','
            rows = []
            with open(path, newline="") as f:
                for r in csv.DictReader(f):
                    rows.append({"id": int(r["id"]), "d": parse_date(r["date"]),
                                 "amt": parse_paren(r["amount"]), "ccy": r["currency"].strip(),
                                 "ref": r["ref"].strip()})
            return rows
        if head.startswith("TxnId"):               # usbank, '|'
            rows = []
            with open(path, newline="") as f:
                for r in csv.DictReader(f, delimiter="|"):
                    rows.append({"id": int(r["TxnId"]), "d": parse_date(r["ValueDate"]),
                                 "amt": parse_plain(r["Amount"]), "ccy": r["CUR"].strip(),
                                 "ref": r["Ref"].strip()})
            return rows
    return []


def parse_ledger(adir):
    rows = []
    with open(os.path.join(adir, "ledger.csv"), newline="") as f:
        for r in csv.DictReader(f):
            minor = Decimal(r["AmountMinor"].strip()) / 100
            amt = minor if r["DrCr"].strip().upper() == "DR" else -minor
            rows.append({"id": int(r["EntryId"]), "d": parse_date(r["PostDate"]),
                         "amt": amt, "ccy": r["Currency"].strip(), "ref": r["DocRef"].strip()})
    return rows


# ----- reconciliation -----
def usd(table, row):
    return rc(row["amt"] * fx_rate(table, row["ccy"], row["d"]))


def reconcile(bank_rows, ledger_rows, table):
    seen = {}
    for r in sorted(bank_rows, key=lambda r: r["id"]):
        key = (r["d"], r["amt"], r["ccy"], r["ref"])
        seen.setdefault(key, r)
    bank = sorted(seen.values(), key=lambda r: r["id"])

    bank_usd = {r["id"]: usd(table, r) for r in bank}
    led_usd = {r["id"]: usd(table, r) for r in ledger_rows}

    used = set()
    matched = []
    for b in bank:
        cands = []
        for lr in ledger_rows:
            if lr["id"] in used or lr["ccy"] != b["ccy"] or lr["amt"] != b["amt"]:
                continue
            gap = abs((lr["d"] - b["d"]).days)
            if gap <= 5:
                cands.append((gap, lr["id"]))
        if cands:
            cands.sort()
            used.add(cands[0][1])
            matched.append([b["id"], cands[0][1]])
    matched.sort(key=lambda p: p[0])

    mb = {p[0] for p in matched}
    bank_close = rc(sum((bank_usd[r["id"]] for r in bank), Decimal("0")))
    ledger_close = rc(sum((led_usd[r["id"]] for r in ledger_rows), Decimal("0")))
    return {
        "matched": matched,
        "unmatched_bank": sorted(r["id"] for r in bank if r["id"] not in mb),
        "unmatched_ledger": sorted(r["id"] for r in ledger_rows if r["id"] not in used),
        "bank_close_usd": float(bank_close),
        "ledger_close_usd": float(ledger_close),
        "residual_usd": float(rc(bank_close - ledger_close)),
    }


def main():
    table = load_fx(os.path.join(ROOT, "fx_rates.csv"))
    out = {}
    for account_id in sorted(os.listdir(SOURCES)):
        adir = os.path.join(SOURCES, account_id)
        if not os.path.isdir(adir):
            continue
        out[account_id] = reconcile(parse_bank(adir), parse_ledger(adir), table)
    with open(os.path.join(ROOT, "reconciliation.json"), "w") as f:
        json.dump(out, f, indent=2)


if __name__ == "__main__":
    main()
