"""Rupee formatting with Indian digit grouping."""

from __future__ import annotations


def group_indian(amount: float) -> str:
    neg = amount < 0
    integer, frac = f"{abs(amount):.2f}".split(".")
    if len(integer) > 3:
        head, tail = integer[:-3], integer[-3:]
        groups: list[str] = []
        while len(head) > 2:
            groups.insert(0, head[-2:])
            head = head[:-2]
        if head:
            groups.insert(0, head)
        integer = ",".join(groups + [tail])
    text = integer if frac == "00" else f"{integer}.{frac}"
    return f"-{text}" if neg else text


def inr(amount: float) -> str:
    """For the web UI and JSON: '₹1,22,530'."""
    return f"₹{group_indian(amount)}"


def rs(amount: float) -> str:
    """For PDFs (the base-14 PDF fonts have no ₹ glyph): 'Rs. 1,22,530'."""
    return f"Rs. {group_indian(amount)}"


def parse_amount(text: str) -> float:
    cleaned = (text or "").replace("Rs.", "").replace("₹", "").replace("INR", "").replace(",", "").strip()
    return float(cleaned) if cleaned else 0.0
