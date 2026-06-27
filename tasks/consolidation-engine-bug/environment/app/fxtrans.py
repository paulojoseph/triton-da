"""Currency translation to the reporting currency (USD).

House rules (intentional, do not change):
  * Monetary legs -- AR, AP, DIV_INCOME, DIV_PAID -- are translated at the
    CLOSING rate.
  * Result legs -- REVENUE, EXPENSE -- are translated at the AVERAGE rate.
  * Profit-in-inventory amounts are translated at the AVERAGE rate.
  * Every translated amount is rounded to cents using round-half-up.
A rate is USD per one unit of the foreign currency; USD itself is 1.0/1.0.
"""
from decimal import Decimal, ROUND_HALF_UP

CLOSING_TYPES = frozenset({"AR", "AP", "DIV_INCOME", "DIV_PAID"})


def round_cents(value):
    """Round a Decimal to two places, half away from zero (round-half-up)."""
    return Decimal(value).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


class Translator:
    """Translates leg amounts into USD using closing/average rates by leg type."""

    def __init__(self, fx_rows):
        self._closing = {}
        self._average = {}
        for row in fx_rows:
            ccy = row["ccy"]
            self._closing[ccy] = Decimal(row["closing_rate"])
            self._average[ccy] = Decimal(row["average_rate"])

    def _rate(self, ccy, leg_type):
        table = self._closing if leg_type in CLOSING_TYPES else self._average
        return table[ccy]

    def to_usd(self, amount, ccy, leg_type):
        return round_cents(Decimal(str(amount)) * self._rate(ccy, leg_type))
