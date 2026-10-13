"""Turn retrieved policy clauses into structured PolicyTerms.

The rules here read the standard Indian retail health-policy wording (IRDAI-style phrasing for
room rent, co-payment, sub-limits and non-payable items). When Gemini is enabled the policy
agent asks Gemini first and uses these rules as the fallback and as a cross-check.
"""

from __future__ import annotations

import re

from ..money import parse_amount
from ..models import Clause, PolicyTerms, SubLimit

AMOUNT = r"Rs\.?\s*([\d,]+(?:\.\d+)?)"


def _num(pattern: str, text: str, flags: int = re.I) -> float | None:
    m = re.search(pattern, text, flags)
    return parse_amount(m.group(1)) if m else None


def extract_terms(clauses_by_topic: dict[str, Clause | None]) -> PolicyTerms:
    terms = PolicyTerms(extraction="rules")
    refs: dict[str, str] = {}

    if c := clauses_by_topic.get("sum_insured"):
        terms.sum_insured = _num(r"Sum Insured.{0,80}?" + AMOUNT, c.text)
        refs["sum_insured"] = c.clause_id

    if c := clauses_by_topic.get("room_rent"):
        # ".{0,120}?" rather than "[^.]*?": wordings like "1% of the Sum Insured per day, i.e. Rs. 5,000" contain periods.
        terms.room_rent_limit = _num(r"normal room.{0,120}?" + AMOUNT + r"\s*per day", c.text)
        terms.icu_rent_limit = _num(r"ICU.{0,120}?" + AMOUNT + r"\s*per day", c.text)
        refs["room_rent"] = c.clause_id

    if c := clauses_by_topic.get("copay"):
        t = c.text
        if m := re.search(r"(\d+(?:\.\d+)?)%[^.]*?applies to every claim", t, re.I):
            terms.copay_network_pct = terms.copay_non_network_pct = float(m.group(1))
        else:
            if re.search(r"No co-payment applies[^.]*Network Hospital", t, re.I):
                terms.copay_network_pct = 0.0
            elif m := re.search(r"(\d+(?:\.\d+)?)%[^.]*?(?<!Non-)Network Hospital", t, re.I):
                terms.copay_network_pct = float(m.group(1))
            if m := re.search(r"(\d+(?:\.\d+)?)%[^.]*?Non-Network Hospital", t, re.I):
                terms.copay_non_network_pct = float(m.group(1))
        if m := re.search(r"additional co-payment of (\d+(?:\.\d+)?)%[^.]*?aged (\d+) years", t, re.I):
            terms.copay_senior_pct = float(m.group(1))
            terms.senior_age = int(m.group(2))
        refs["copay"] = c.clause_id

    if c := clauses_by_topic.get("sub_limit"):
        for m in re.finditer(r"\([a-z]\)\s*([A-Za-z][A-Za-z \-]+?):\s*" + AMOUNT + r"\s*per (\w+)", c.text):
            terms.sub_limits.append(SubLimit(procedure=m.group(1).strip(), amount=parse_amount(m.group(2)), basis=m.group(3)))
        refs["sub_limit"] = c.clause_id

    if c := clauses_by_topic.get("non_medical"):
        t = c.text.lower()
        terms.non_medical_covered = bool(re.search(r"non-medical items[^.]*\bare payable", t)) and "not payable" not in t
        refs["non_medical"] = c.clause_id

    if c := clauses_by_topic.get("personal_items"):
        terms.personal_items_excluded = "not payable" in c.text.lower()
        refs["personal_items"] = c.clause_id

    for topic in ("actually_incurred", "reasonable_customary", "grievance"):
        if c := clauses_by_topic.get(topic):
            refs[topic] = c.clause_id

    terms.clause_refs = refs
    return terms


STOPWORDS = {"surgery", "treatment", "of", "the", "and", "for", "a", "an", "total"}


def match_sub_limit(terms: PolicyTerms, procedure: str) -> SubLimit | None:
    """A sub-limit applies when every significant word of its name appears in the bill's
    procedure, e.g. 'Total knee replacement' -> {knee, replacement}."""
    proc = procedure.lower()
    for sl in terms.sub_limits:
        tokens = [w for w in re.findall(r"[a-z]+", sl.procedure.lower()) if w not in STOPWORDS]
        if tokens and all(w in proc for w in tokens):
            return sl
    return None
