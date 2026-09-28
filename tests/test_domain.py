"""Pure business rules: fast, exhaustive unit tests."""

import pytest

from server.domain import finance, pricing
from server.domain.masking import mask_email, mask_lead, mask_phone
from server.domain.policy import PolicyViolation, check_discount

FEES = [{"label": "Admin", "amount": 499}, {"label": "OMVIC", "amount": 12.5}]


def test_all_in_quote_includes_every_fee():
    q = pricing.all_in_quote(20000, FEES, discount=500)
    assert q["all_in_price"] == 20011.50
    assert q["hst_estimate"] == 2601.50
    assert q["total_with_hst"] == 22613.00


def test_quote_rejects_negative_or_oversized_discount():
    with pytest.raises(ValueError):
        pricing.all_in_quote(1000, FEES, discount=-1)
    with pytest.raises(ValueError):
        pricing.all_in_quote(1000, FEES, discount=1001)


def test_money_rounding_is_half_up_to_cents():
    assert pricing.money(0.125) == pricing.money("0.13")


def test_payment_estimate_matches_amortization_formula():
    e = finance.estimate(30000, 0, 60)
    r = 7.99 / 1200
    expected = 30000 * r / (1 - (1 + r) ** -60)
    assert abs(e["monthly_payment"] - expected) < 0.01
    assert e["biweekly_payment"] == round(e["monthly_payment"] * 12 / 26, 2)


@pytest.mark.parametrize(("down", "term"), [(40000, 60), (0, 99)])
def test_payment_estimate_rejects_bad_inputs(down, term):
    with pytest.raises(ValueError):
        finance.estimate(30000, down, term)


@pytest.mark.parametrize(
    ("amount", "manager", "needs_manager", "needs_confirm"),
    [(500, False, False, False), (501, False, True, True), (900, True, False, True)],
)
def test_discount_policy(amount, manager, needs_manager, needs_confirm):
    d = check_discount(
        amount=amount, list_price=20000, is_manager=manager, limit=500, max_ratio=0.15
    )
    assert (d.needs_manager, d.needs_confirmation) == (needs_manager, needs_confirm)


@pytest.mark.parametrize("amount", [0, -5, 3001])
def test_discount_policy_hard_limits(amount):
    with pytest.raises(PolicyViolation):
        check_discount(amount=amount, list_price=20000, is_manager=True, limit=500, max_ratio=0.15)


def test_masking():
    assert mask_phone("416-555-0142") == "***-***-0142"
    assert mask_email("jane.doe@example.com") == "j***@example.com"
    lead = mask_lead(
        {
            "lead_id": "L-1",
            "first_name": "Jane",
            "last_name": "Doe",
            "phone": "416-555-0142",
            "email": None,
            "note": "hi",
        }
    )
    assert lead["name"] == "Jane D." and lead["note"] == {"untrusted_text": "hi"}
