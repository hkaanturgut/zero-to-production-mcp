"""All-in pricing, computed in code so the model never does money math.

Ontario's all-in price rule (OMVIC): the advertised price must include every
fee the dealer intends to collect; only HST and licensing may be excluded, and
the quote must say so. Money uses Decimal, rounded to cents.
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

HST_RATE = Decimal("0.13")
CENT = Decimal("0.01")


def money(value: float | int | str | Decimal) -> Decimal:
    return Decimal(str(value)).quantize(CENT, rounding=ROUND_HALF_UP)


def all_in_quote(list_price: float, fees: list[dict], discount: float = 0.0) -> dict:
    price = money(list_price)
    disc = money(discount)
    if disc < 0 or disc > price:
        raise ValueError("discount out of range")
    fee_lines = [{"label": f["label"], "amount": float(money(f["amount"]))} for f in fees]
    fee_total = sum((money(f["amount"]) for f in fees), Decimal("0"))
    all_in = price - disc + fee_total
    hst = (all_in * HST_RATE).quantize(CENT, rounding=ROUND_HALF_UP)
    return {
        "vehicle_price": float(price),
        "discount": float(disc),
        "fees": fee_lines,
        "all_in_price": float(all_in),
        "hst_estimate": float(hst),
        "total_with_hst": float(all_in + hst),
        "disclosure": "All-in price includes all dealer fees. HST and licensing are extra.",
    }
