"""Elimination of unrealised profit in inventory (PIP) and the NCI carve-out.

For each profit-in-inventory row the unrealised profit is translated to USD at
the average rate and eliminated in full. The non-controlling-interest portion
depends on the direction of the sale:

House rules (intentional, do not change):
  * Downstream sale -- the seller is the top reporting parent: ``nci = 0``.
  * Upstream sale -- the seller is a subsidiary: ``nci = profit_usd * (1 - g)``
    where ``g`` is the group's EFFECTIVE interest in the seller (the chain
    product from ``congraph``), rounded half-up to cents.
"""
from decimal import Decimal

from fxtrans import round_cents


def eliminate_pip(rows, translator, graph, effective):
    """rows: profit_in_inventory dicts. effective: {entity_id -> Decimal g}
    for the consolidated set. Returns (pip_total, nci_total)."""
    pip_total = Decimal("0.00")
    nci_total = Decimal("0.00")
    for row in rows:
        usd = translator.to_usd(row["unrealized_profit"], row["currency"], "REVENUE")
        pip_total += usd
        seller = row["seller_id"]
        if graph.is_top_parent(seller):
            nci_total += Decimal("0.00")
            continue
        g = effective.get(seller)
        if g is None:
            # seller outside the consolidated set: use its direct interest
            g = graph.direct_interest(seller)
        nci_total += round_cents(usd * (Decimal("1") - g))
    return pip_total, nci_total
