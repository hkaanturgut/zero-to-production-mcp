"""Minimise personal data in anything the model can see."""

from __future__ import annotations


def mask_phone(phone: str | None) -> str | None:
    if not phone:
        return None
    return f"***-***-{phone[-4:]}"


def mask_email(email: str | None) -> str | None:
    if not email or "@" not in email:
        return None
    local, domain = email.split("@", 1)
    return f"{local[:1]}***@{domain}"


def mask_lead(lead: dict) -> dict:
    """The only lead shape a tool may return."""
    return {
        "lead_id": lead["lead_id"],
        "name": f"{lead['first_name']} {lead['last_name'][:1]}.",
        "phone": mask_phone(lead.get("phone")),
        "email": mask_email(lead.get("email")),
        "interested_in": lead.get("stock_number"),
        # Free text written by customers or staff. Returned as quoted data so
        # the client and model can tell it apart from instructions.
        "note": {"untrusted_text": lead["note"]} if lead.get("note") else None,
    }
