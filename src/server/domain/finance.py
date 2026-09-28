"""Loan payment estimates. Always an estimate, never an approval."""

from __future__ import annotations

from decimal import Decimal

from server.domain.pricing import money

# Illustrative demo rates by term (APR %). A real dealer gets these from lenders.
DEMO_APR = {
    36: Decimal("6.99"),
    48: Decimal("7.49"),
    60: Decimal("7.99"),
    72: Decimal("8.49"),
    84: Decimal("8.99"),
}
DISCLAIMER = (
    "Estimate only, on approved credit. Not an offer or approval of financing. "
    "Actual rate depends on the lender and credit review."
)


def estimate(total_with_hst: float, down_payment: float, term_months: int) -> dict:
    if term_months not in DEMO_APR:
        raise ValueError(f"term must be one of {sorted(DEMO_APR)}")
    principal = money(total_with_hst) - money(down_payment)
    if principal <= 0:
        raise ValueError("down payment covers the full price, no financing needed")
    apr = DEMO_APR[term_months]
    r = apr / Decimal(1200)
    n = term_months
    monthly = principal * r / (1 - (1 + r) ** -n)
    monthly = money(monthly)
    total_paid = monthly * n
    return {
        "financed_amount": float(principal),
        "term_months": n,
        "apr_percent": float(apr),
        "monthly_payment": float(monthly),
        "biweekly_payment": float(money(monthly * 12 / 26)),
        "total_interest": float(money(total_paid - principal)),
        "disclaimer": DISCLAIMER,
    }
