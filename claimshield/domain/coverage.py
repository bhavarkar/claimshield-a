"""Policy entitlement engine.

Two questions, answered with the same formula:
  1. What should the insurer have paid on this bill, according to the policy? (`entitlement`)
  2. What parameters did the insurer actually use? (`infer_insurer`, read back from the
     itemised deductions printed on the settlement)

Coverage findings come from walking from the insurer's parameters to the policy's, one
component at a time (non-payables, room rent, sub-limit, co-payment). Each step's change in
payable is that finding's impact, so the impacts add up exactly to the total shortfall rather
than double-counting interacting components (a wrong sub-limit also shrinks the co-pay base).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field, replace
from typing import Callable, Optional

from ..money import inr, parse_amount
from ..models import Bill, Entitlement, Finding, FindingType, PolicyCitation, PolicyTerms
from .policy_terms import match_sub_limit


@dataclass(frozen=True)
class Params:
    non_payable: float
    room_excess: float
    cap: Optional[float]
    copay_pct: float


def payable(gross: float, p: Params, sum_insured: Optional[float]) -> float:
    admissible = max(gross - p.non_payable - p.room_excess, 0.0)
    after = min(admissible, p.cap) if p.cap is not None else admissible
    pay = round(after * (1 - p.copay_pct / 100), 2)
    return min(pay, sum_insured) if sum_insured else pay


def expected_copay_pct(bill: Bill, terms: PolicyTerms) -> float:
    pct = terms.copay_network_pct if bill.network_hospital else terms.copay_non_network_pct
    if terms.senior_age and bill.patient_age is not None and bill.patient_age >= terms.senior_age:
        pct += terms.copay_senior_pct
    return pct


def non_payable_lines(bill: Bill, terms: PolicyTerms) -> list[int]:
    out = []
    for li in bill.line_items:
        if li.category == "PERSONAL" and terms.personal_items_excluded:
            out.append(li.line_no)
        elif li.category == "NON_MEDICAL" and not terms.non_medical_covered:
            out.append(li.line_no)
    return out


def entitlement(bill: Bill, terms: PolicyTerms, line_corrections: dict[int, float] | None = None,
                gross_correction: float = 0.0) -> Entitlement:
    """Policy entitlement on the bill, optionally after removing disputed amounts.
    `line_corrections` maps line_no -> amount removed from that line; `gross_correction` is the
    total removed from the gross (line corrections plus any total-level error)."""
    corr = line_corrections or {}
    amounts = {li.line_no: max(li.amount - corr.get(li.line_no, 0.0), 0.0) for li in bill.line_items}
    gross = round(bill.stated_gross_total - gross_correction, 2)

    np_lines = non_payable_lines(bill, terms)
    non_pay = sum(amounts[n] for n in np_lines)

    room_excess = 0.0
    for li in bill.line_items:
        limit = terms.icu_rent_limit if li.category == "ICU" else terms.room_rent_limit if li.category == "ROOM" else None
        if limit and li.unit_price > limit:
            days = amounts[li.line_no] / li.unit_price if li.unit_price else 0
            room_excess += (li.unit_price - limit) * days

    sl = match_sub_limit(terms, bill.procedure)
    pct = expected_copay_pct(bill, terms)
    p = Params(non_payable=non_pay, room_excess=room_excess, cap=sl.amount if sl else None, copay_pct=pct)
    admissible = max(gross - non_pay - room_excess, 0.0)
    after = min(admissible, p.cap) if p.cap is not None else admissible
    insurer = payable(gross, p, terms.sum_insured)
    return Entitlement(
        gross=gross, non_payable=round(non_pay, 2), non_payable_lines=np_lines, room_excess=round(room_excess, 2),
        admissible=round(admissible, 2), sub_limit_applied=p.cap, after_sub_limit=round(after, 2),
        copay_pct=pct, copay=round(after * pct / 100, 2), insurer_payable=insurer, patient_payable=round(gross - insurer, 2),
    )


@dataclass
class InsurerView:
    params: Params
    non_payable_names: list[str] = field(default_factory=list)
    non_payable_lines: list[int] = field(default_factory=list)
    deduction_text: dict[str, str] = field(default_factory=dict)
    reproduced: float = 0.0


def infer_insurer(bill: Bill) -> InsurerView:
    non_pay = room = 0.0
    cap: Optional[float] = None
    pct = 0.0
    names: list[str] = []
    text: dict[str, str] = {}
    for d in bill.deductions:
        label = f"{d.label} {d.basis}".lower()
        shown = f"{d.label}: {d.basis} ({inr(d.amount)})"
        if "co-pay" in label or "copay" in label or "co pay" in label:
            if m := re.search(r"(\d+(?:\.\d+)?)\s*%", d.basis):
                pct = float(m.group(1))
            text["copay"] = shown
        elif "sub-limit" in label or "sublimit" in label or "sub limit" in label or "capped" in label:
            if m := re.search(r"(?:Rs\.?|₹|INR)\s*([\d,]+(?:\.\d+)?)", d.basis):
                cap = parse_amount(m.group(1))
            text["sub_limit"] = shown
        elif "room" in label:
            room += d.amount
            text["room_rent"] = shown
        elif "non-payable" in label or "non payable" in label or "not payable" in label or "excluded" in label:
            non_pay += d.amount
            names += [n.strip().lower() for n in re.split(r"[;,]", d.basis) if n.strip()]
            text["non_medical"] = shown
    np_lines = [li.line_no for li in bill.line_items if any(n and n in li.description.lower() for n in names)]
    p = Params(non_payable=non_pay, room_excess=room, cap=cap, copay_pct=pct)
    return InsurerView(params=p, non_payable_names=names, non_payable_lines=np_lines, deduction_text=text,
                       reproduced=payable(bill.stated_gross_total, p, None))


Cite = Callable[[str], Optional[PolicyCitation]]


def coverage_findings(bill: Bill, terms: PolicyTerms, cite: Cite, next_id: Callable[[], str]) -> tuple[list[Finding], list[str]]:
    """Walk insurer params -> policy params, adopting a policy value only where it favours the
    policyholder. Returns (findings, notes)."""
    ins = infer_insurer(bill)
    pol = entitlement(bill, terms)
    gross, si = bill.stated_gross_total, terms.sum_insured
    findings: list[Finding] = []
    notes: list[str] = []

    if abs(ins.reproduced - bill.insurer_approved) > 1:
        notes.append(
            f"The insurer's approved amount ({inr(bill.insurer_approved)}) could not be fully reproduced from the "
            f"deductions printed on the bill ({inr(ins.reproduced)})."
        )

    current = ins.params
    base = payable(gross, current, si)

    def step(new: Params) -> float:
        nonlocal current, base
        new_pay = payable(gross, new, si)
        delta = round(new_pay - base, 2)
        if delta > 0.5:
            current, base = new, new_pay
            return delta
        return 0.0

    # 1. Items deducted as non-payable that the policy pays for.
    wrongly = [n for n in ins.non_payable_lines if n not in pol.non_payable_lines]
    if wrongly:
        amt = sum(li.amount for li in bill.line_items if li.line_no in wrongly)
        impact = step(replace(current, non_payable=max(current.non_payable - amt, 0.0)))
        if impact:
            items = ", ".join(f"line {li.line_no} {li.description} ({inr(li.amount)})" for li in bill.line_items if li.line_no in wrongly)
            c = cite("non_medical")
            findings.append(Finding(
                finding_id=next_id(), type=FindingType.COVERAGE_MISMATCH, topic="non_medical",
                title="Covered item deducted as non-payable",
                bill_lines=wrongly,
                bill_evidence=f"{ins.deduction_text.get('non_medical', 'Non-payable deduction')}; includes {items}",
                policy=c,
                explanation=(f"The insurer treated {items} as non-payable, but "
                             f"{('policy ' + c.clause_id + ' (' + c.title + ')') if c else 'the policy'} makes these items payable "
                             f"during a covered hospitalisation."),
                confidence="High", impact=impact, counterparty="insurer", detected_by="audit_agent", method="policy rule replay",
            ))

    # 2. Room rent excess deducted beyond what the room-rent limit allows.
    if current.room_excess > pol.room_excess + 0.5:
        impact = step(replace(current, room_excess=pol.room_excess))
        if impact:
            findings.append(Finding(
                finding_id=next_id(), type=FindingType.COVERAGE_MISMATCH, topic="room_rent",
                title="Room-rent deduction exceeds the policy limit",
                bill_lines=[li.line_no for li in bill.line_items if li.category in ("ROOM", "ICU")],
                bill_evidence=ins.deduction_text.get("room_rent", "Room rent deduction"),
                policy=cite("room_rent"),
                explanation=(f"The insurer deducted {inr(ins.params.room_excess)} as excess room rent; under the policy's "
                             f"room-rent limit the excess is {inr(pol.room_excess)}."),
                confidence="High", impact=impact, counterparty="insurer", detected_by="audit_agent", method="policy rule replay",
            ))

    # 3. Sub-limit applied lower than the policy's, or applied where none exists.
    if current.cap is not None and (pol.sub_limit_applied is None or current.cap < pol.sub_limit_applied - 0.5):
        applied = current.cap
        impact = step(replace(current, cap=pol.sub_limit_applied))
        if impact:
            right = inr(pol.sub_limit_applied) if pol.sub_limit_applied is not None else "no sub-limit"
            findings.append(Finding(
                finding_id=next_id(), type=FindingType.COVERAGE_MISMATCH, topic="sub_limit",
                title="Sub-limit applied below the policy amount",
                bill_lines=[], bill_evidence=ins.deduction_text.get("sub_limit", "Sub-limit deduction"),
                policy=cite("sub_limit"),
                explanation=(f"The insurer capped this claim ({bill.procedure}) at {inr(applied)}. "
                             f"The policy's sub-limit for this procedure is {right}."),
                confidence="High", impact=impact, counterparty="insurer", detected_by="audit_agent", method="policy rule replay",
            ))

    # 4. Co-payment percentage different from the policy's.
    if current.copay_pct > pol.copay_pct + 0.01:
        impact = step(replace(current, copay_pct=pol.copay_pct))
        if impact:
            why = []
            why.append("network" if bill.network_hospital else "non-network")
            if bill.patient_age is not None:
                why.append(f"patient aged {bill.patient_age}")
            findings.append(Finding(
                finding_id=next_id(), type=FindingType.COVERAGE_MISMATCH, topic="copay",
                title="Co-payment applied that the policy doesn't require" if pol.copay_pct == 0 else "Co-payment rate higher than the policy's",
                bill_lines=[], bill_evidence=ins.deduction_text.get("copay", "Co-payment deduction"),
                policy=cite("copay"),
                explanation=(f"The insurer deducted a {ins.params.copay_pct:g}% co-payment. For this claim "
                             f"({', '.join(why)}) the policy's co-payment is {pol.copay_pct:g}%."),
                confidence="High", impact=impact, counterparty="insurer", detected_by="audit_agent", method="policy rule replay",
            ))

    # Anything the deductions don't explain.
    gap = round(ins.reproduced - bill.insurer_approved, 2)
    if gap > 1:
        findings.append(Finding(
            finding_id=next_id(), type=FindingType.COVERAGE_MISMATCH, topic="unexplained",
            title="Insurer paid less than its own stated deductions imply",
            bill_lines=[], bill_evidence=f"Approved {inr(bill.insurer_approved)} vs {inr(ins.reproduced)} implied by the itemised deductions",
            policy=cite("grievance"),
            explanation="Part of the shortfall isn't explained by any deduction on the settlement. Ask the insurer for the reason.",
            confidence="Worth reviewing", impact=gap, counterparty="insurer", detected_by="audit_agent", method="settlement reconciliation",
        ))
    return findings, notes
