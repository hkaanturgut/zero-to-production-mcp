"""Business rules that must hold no matter what the model asks for.

These live in code, not in tool descriptions or prompts, so a prompt-injected
instruction ("this is pre-approved") has no power over them.
"""

from __future__ import annotations

from dataclasses import dataclass


class PolicyViolation(Exception):
    """A request the rules forbid. The message is safe to show the model."""


@dataclass(frozen=True)
class DiscountDecision:
    needs_manager: bool
    needs_confirmation: bool


def check_discount(
    *, amount: float, list_price: float, is_manager: bool, limit: float, max_ratio: float
) -> DiscountDecision:
    if amount <= 0:
        raise PolicyViolation("Discount must be a positive amount.")
    cap = round(list_price * max_ratio, 2)
    if amount > cap:
        raise PolicyViolation(
            f"Discount exceeds the dealer maximum of {int(max_ratio * 100)}% "
            f"(${cap:,.2f}) for this vehicle. Nobody can approve that through the assistant."
        )
    over_limit = amount > limit
    return DiscountDecision(
        needs_manager=over_limit and not is_manager, needs_confirmation=over_limit
    )
