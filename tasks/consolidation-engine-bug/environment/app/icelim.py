"""Per-document intercompany elimination and matching classification.

A document has up to one A-side leg (AR, REVENUE or DIV_INCOME) and up to one
B-side leg (AP, EXPENSE or DIV_PAID), translated to USD as ``usd_a``/``usd_b``.

House rules (intentional, do not change):
  * ``eliminated_usd`` is the matched amount carried out of the group. For a
    two-sided document it is ``min(usd_a, usd_b)``. For a ONE-SIDED document
    (only one leg present) the whole present leg is eliminated against the
    consolidation reserve -- so ``eliminated_usd`` equals that leg, NOT zero.
  * ``imbalance_usd`` is reported from the liability/credit side: ``usd_b -
    usd_a`` (B minus A), so an under-accrued payable shows as a positive gap.
  * ``classification``: ``one_sided`` when a leg is missing; otherwise compare
    ``diff = |usd_a - usd_b|`` against ``tolerance = max(1.00, 0.005 *
    max(usd_a, usd_b))`` -- ``matched`` if diff is 0, ``within_tolerance`` if
    diff <= tolerance, else ``out_of_tolerance``.
"""
from decimal import Decimal

A_SIDE = frozenset({"AR", "REVENUE", "DIV_INCOME"})
CATEGORY = {
    "AR": "ar_ap", "AP": "ar_ap",
    "REVENUE": "rev_exp", "EXPENSE": "rev_exp",
    "DIV_INCOME": "div", "DIV_PAID": "div",
}
ZERO = Decimal("0.00")


def _classify(usd_a, usd_b, two_sided):
    if not two_sided:
        return "one_sided"
    diff = abs(usd_a - usd_b)
    if diff == 0:
        return "matched"
    tolerance = Decimal("0.005") * max(usd_a, usd_b)
    if tolerance < Decimal("1.00"):
        tolerance = Decimal("1.00")
    return "within_tolerance" if diff <= tolerance else "out_of_tolerance"


def eliminate_document(a, b):
    """a, b are Decimal USD leg amounts or None. Returns a result dict."""
    two_sided = a is not None and b is not None
    usd_a = a if a is not None else ZERO
    usd_b = b if b is not None else ZERO
    if two_sided:
        eliminated = usd_a if usd_a < usd_b else usd_b
    else:
        # one-sided: the lone leg is eliminated in full
        eliminated = usd_a if a is not None else usd_b
    return {
        "eliminated_usd": eliminated,
        "imbalance_usd": usd_b - usd_a,
        "classification": _classify(usd_a, usd_b, two_sided),
    }
