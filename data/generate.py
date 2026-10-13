"""Generate the synthetic demo dataset: hospital bills, policy documents, and an answer key.

Every person, hospital, insurer and policy number here is fictional. Each PDF carries a
"SYNTHETIC - FOR DEMO" watermark.

Planted issues (see data/samples/expected.json for the machine-readable answer key):

  BILL-001  Suraksha Gold   appendectomy  duplicate CBC, Ceftriaxone qty x rate error,
                                          upcoded anaesthesia, wrong 20% co-pay,
                                          admission kit wrongly deducted (policy covers it)
  BILL-002  Suraksha Gold   cataract      eye-drops qty x rate error, gross total does not
                                          add up, sub-limit applied at 35k instead of 40k
  BILL-003  CareFirst Silver knee repl.   room billed 6 days for a 5-night stay, physio
                                          entered twice the same day, MRI priced far above
                                          benchmark, sub-limit applied at 1L instead of 1.5L
  BILL-004  CareFirst Silver dengue       CLEAN - every charge and deduction is correct

Run:  python data/generate.py
"""

from __future__ import annotations

import json
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

ROOT = Path(__file__).resolve().parent
OUT_BILLS = ROOT / "samples" / "bills"
OUT_POLICIES = ROOT / "samples" / "policies"

STYLES = getSampleStyleSheet()
H1 = ParagraphStyle("h1", parent=STYLES["Heading1"], fontSize=15, spaceAfter=2)
H2 = ParagraphStyle("h2", parent=STYLES["Heading2"], fontSize=11.5, spaceBefore=8, spaceAfter=3)
BODY = ParagraphStyle("body", parent=STYLES["BodyText"], fontSize=9.2, leading=12.5)
SMALL = ParagraphStyle("small", parent=BODY, fontSize=8, textColor=colors.grey)
CELL = ParagraphStyle("cell", parent=BODY, fontSize=8.3, leading=10)


def rs(amount: float) -> str:
    """Indian digit grouping: 122530 -> '1,22,530'."""
    neg = amount < 0
    whole = f"{abs(amount):.2f}"
    integer, frac = whole.split(".")
    if len(integer) > 3:
        head, tail = integer[:-3], integer[-3:]
        groups = []
        while len(head) > 2:
            groups.insert(0, head[-2:])
            head = head[:-2]
        if head:
            groups.insert(0, head)
        integer = ",".join(groups + [tail])
    text = integer if frac == "00" else f"{integer}.{frac}"
    return f"-{text}" if neg else text


def watermark(canvas, doc):
    canvas.saveState()
    canvas.setFont("Helvetica-Bold", 46)
    canvas.setFillColor(colors.Color(0.85, 0.1, 0.1, alpha=0.08))
    canvas.translate(A4[0] / 2, A4[1] / 2)
    canvas.rotate(35)
    canvas.drawCentredString(0, 0, "SYNTHETIC - FOR DEMO")
    canvas.restoreState()
    canvas.setFont("Helvetica", 7.5)
    canvas.setFillColor(colors.grey)
    canvas.drawString(15 * mm, 10 * mm, "Synthetic document generated for the ClaimShield AI demo. All names are fictional.")
    canvas.drawRightString(A4[0] - 15 * mm, 10 * mm, f"Page {doc.page}")


GRID = TableStyle(
    [
        ("GRID", (0, 0), (-1, -1), 0.4, colors.grey),
        ("FONT", (0, 0), (-1, -1), "Helvetica", 8.3),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]
)


# --------------------------------------------------------------------------------------
# Policies
# --------------------------------------------------------------------------------------

POLICIES = {
    "POLICY-GOLD": {
        "file": "suraksha_health_gold.pdf",
        "insurer": "Bharat Shield General Insurance Ltd. (fictional)",
        "plan": "Suraksha Health Gold",
        "policy_number": "SHG-2026-004417",
        "schedule": [
            ("Policy Number", "SHG-2026-004417"),
            ("Plan", "Suraksha Health Gold - Individual"),
            ("Sum Insured", "Rs. 5,00,000 per policy year"),
            ("Policy Period", "01-Apr-2026 to 31-Mar-2027"),
            ("Insured Persons", "Rohan Mehta; Sushila Rao (fictional)"),
            ("TPA", "MediAssist Claims Services (fictional)"),
        ],
        "sections": [
            ("Section 1 - Cover", [
                ("1.1", "Sum Insured", "The Sum Insured under this policy is Rs. 5,00,000 per policy year. All admissible claims in a policy year are payable up to the Sum Insured."),
                ("1.2", "In-patient Hospitalisation", "The Company will pay Medical Expenses for In-patient Care incurred by the Insured Person for hospitalisation of at least 24 consecutive hours, or for listed Day Care Procedures, for an illness or injury contracted during the policy period."),
            ]),
            ("Section 2 - Definitions", [
                ("2.1", "Medically Necessary Treatment", "Treatment that is required for the medical management of the illness or injury suffered by the Insured Person, does not exceed the level of care necessary to provide safe, adequate and appropriate medical care, and is prescribed by a Medical Practitioner."),
                ("2.2", "Reasonable and Customary Charges", "Charges for services or supplies which are the standard charges for the specific provider and consistent with the prevailing charges in the geographical area for identical or similar services, taking into account the nature of the illness or injury involved."),
                ("2.3", "Expenses Actually Incurred", "Only expenses actually incurred by the Insured Person for services actually rendered are payable. Duplicate entries, and amounts arising from arithmetical errors in the hospital bill, are not expenses actually incurred."),
            ]),
            ("Section 3 - Limits and Benefits", [
                ("3.1", "Room Rent and ICU Charges", "Room rent for a normal room is payable up to 1% of the Sum Insured per day, i.e. Rs. 5,000 per day. ICU charges are payable up to 2% of the Sum Insured per day, i.e. Rs. 10,000 per day. If the Insured Person opts for a room with higher rent, only the excess room rent is non-payable; no proportionate deduction is applied to other charges."),
                ("3.2", "Co-payment", "No co-payment applies to claims for treatment taken at a Network Hospital. A co-payment of 20% of the admissible claim amount applies to treatment taken at a Non-Network Hospital. An additional co-payment of 10% applies where the Insured Person is aged 61 years or above at the time of admission."),
                ("3.3", "Sub-limits", "The following sub-limits apply per policy year and are applied before any co-payment: (a) Cataract surgery: Rs. 40,000 per eye. (b) Treatment of kidney stones: Rs. 60,000 per claim."),
                ("3.4", "Consumables Benefit", "Notwithstanding the list of non-payable items in Annexure II, non-medical items and consumables (including admission kits, gloves, masks and similar items) incurred during a covered hospitalisation are payable under this policy."),
            ]),
            ("Section 4 - Exclusions", [
                ("4.1", "Cosmetic Treatment", "Expenses for cosmetic or aesthetic treatment of any description are not payable, unless required as part of reconstruction following an accident, burn or cancer."),
                ("4.2", "Vision and Hearing Aids", "Cost of spectacles, contact lenses and hearing aids is not payable. Intraocular lenses implanted during a covered cataract surgery are payable."),
                ("4.3", "Dental Treatment", "Dental treatment is not payable unless it requires hospitalisation following an accident."),
                ("4.4", "Personal Comfort Items", "Personal comfort and convenience items, including attendant food, television charges, telephone charges and toiletries, are not payable."),
            ]),
            ("Section 5 - Claims", [
                ("5.1", "Cashless Claims", "Cashless facility is available at Network Hospitals subject to pre-authorisation by the TPA. The final settlement will be made on the itemised final hospital bill."),
                ("5.2", "Grievances", "If the Insured Person is not satisfied with a claim decision, a written grievance may be filed with the Company's Grievance Redressal Officer within 30 days of the decision. Unresolved grievances may be escalated to the Insurance Ombudsman."),
            ]),
        ],
    },
    "POLICY-SILVER": {
        "file": "carefirst_family_silver.pdf",
        "insurer": "Navodaya Assurance Company Ltd. (fictional)",
        "plan": "CareFirst Family Floater Silver",
        "policy_number": "CFS-2026-118230",
        "schedule": [
            ("Policy Number", "CFS-2026-118230"),
            ("Plan", "CareFirst Family Floater Silver"),
            ("Sum Insured", "Rs. 3,00,000 per policy year (floater)"),
            ("Policy Period", "15-Jan-2026 to 14-Jan-2027"),
            ("Insured Persons", "Farhan Qureshi; Kavya Iyer (fictional)"),
            ("TPA", "HealthBridge TPA (fictional)"),
        ],
        "sections": [
            ("Section 1 - Cover", [
                ("1.1", "Sum Insured", "The Sum Insured under this policy is Rs. 3,00,000 per policy year, available on a floater basis to all Insured Persons."),
                ("1.2", "In-patient Hospitalisation", "The Company will pay Medical Expenses for In-patient Care incurred for hospitalisation of at least 24 consecutive hours, or for listed Day Care Procedures."),
            ]),
            ("Section 2 - Definitions", [
                ("2.1", "Reasonable and Customary Charges", "Charges for services or supplies which are the standard charges for the specific provider and consistent with the prevailing charges in the geographical area for identical or similar services."),
                ("2.2", "Expenses Actually Incurred", "Only expenses actually incurred by the Insured Person for services actually rendered are payable. Duplicate entries, and amounts arising from arithmetical errors in the hospital bill, are not expenses actually incurred."),
            ]),
            ("Section 3 - Limits and Benefits", [
                ("3.1", "Room Rent and ICU Charges", "Room rent for a normal room is payable up to Rs. 3,000 per day. ICU charges are payable up to Rs. 6,000 per day. If the Insured Person opts for a room with higher rent, only the excess room rent is non-payable."),
                ("3.2", "Co-payment", "A co-payment of 20% of the admissible claim amount applies to every claim, at Network and Non-Network Hospitals alike. The co-payment is applied after sub-limits."),
                ("3.3", "Sub-limits", "The following sub-limits apply per policy year and are applied before any co-payment: (a) Total knee replacement: Rs. 1,50,000 per knee. (b) Cataract surgery: Rs. 25,000 per eye."),
                ("3.4", "Non-Medical Items", "Items listed in Annexure II (non-medical items and consumables such as admission kits, gloves and masks) are not payable."),
            ]),
            ("Section 4 - Exclusions", [
                ("4.1", "Cosmetic Treatment", "Expenses for cosmetic or aesthetic treatment of any description are not payable."),
                ("4.2", "Personal Comfort Items", "Personal comfort and convenience items, including attendant food, television charges, telephone charges and toiletries, are not payable."),
                ("4.3", "Dental Treatment", "Dental treatment is not payable unless it requires hospitalisation following an accident."),
            ]),
            ("Section 5 - Claims", [
                ("5.1", "Claim Settlement", "Claims are settled on the itemised final hospital bill. The TPA will communicate the reason for every deduction."),
                ("5.2", "Grievances", "A written grievance may be filed with the Company's Grievance Cell within 30 days of the claim decision. Unresolved grievances may be escalated to the Insurance Ombudsman."),
            ]),
        ],
    },
}


def build_policy(spec: dict) -> Path:
    path = OUT_POLICIES / spec["file"]
    doc = SimpleDocTemplate(str(path), pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm, topMargin=16 * mm, bottomMargin=18 * mm,
                            title=spec["plan"], author=spec["insurer"])
    story = [
        Paragraph(spec["insurer"], H1),
        Paragraph(f"{spec['plan']} - Policy Wordings", H2),
        Spacer(1, 4),
        Paragraph("Policy Schedule", H2),
    ]
    sched = Table([[k, v] for k, v in spec["schedule"]], colWidths=[45 * mm, 125 * mm])
    sched.setStyle(GRID)
    story += [sched, Spacer(1, 6)]
    for title, clauses in spec["sections"]:
        story.append(Paragraph(title, H2))
        for cid, ctitle, text in clauses:
            story.append(Paragraph(f"<b>{cid} {ctitle}.</b> {text}", BODY))
            story.append(Spacer(1, 3))
    doc.build(story, onFirstPage=watermark, onLaterPages=watermark)
    return path


# --------------------------------------------------------------------------------------
# Bills
# --------------------------------------------------------------------------------------

# Each line: (date, code, description, dept, qty, rate, printed_amount or None for qty*rate)
BILLS = {
    "BILL-001": {
        "file": "bill_001_sunrise_appendectomy.pdf",
        "policy": "POLICY-GOLD",
        "hospital": "Sunrise Multispeciality Hospital",
        "address": "Plot 14, Baner Road, Pune 411045 (fictional)",
        "header": {
            "Bill No": "SMH/IP/26/08812", "Bill Date": "2026-08-06",
            "Patient Name": "Rohan Mehta", "Age / Sex": "34 / M",
            "UHID": "SMH-0098812", "Policy No": "SHG-2026-004417",
            "Insurer / TPA": "Bharat Shield / MediAssist", "Network Hospital": "Yes",
            "Admission": "2026-08-03", "Discharge": "2026-08-06",
            "Diagnosis": "Acute appendicitis", "Procedure": "Laparoscopic appendectomy",
        },
        "lines": [
            ("2026-08-03", "RM-TWN", "Room charges - Twin sharing", "Room", 3, 4200, None),
            ("2026-08-03", "CON-SPL", "Specialist consultation (General Surgery)", "Consultation", 3, 1500, None),
            ("2026-08-03", "LAB-CBC", "Complete blood count (CBC)", "Laboratory", 1, 450, None),
            ("2026-08-03", "LAB-CBC", "Complete blood count (CBC)", "Laboratory", 1, 450, None),
            ("2026-08-03", "RAD-USG", "USG abdomen", "Radiology", 1, 1800, None),
            ("2026-08-04", "OT-LAP-APP", "Laparoscopic appendectomy - surgeon fee", "Surgery", 1, 55000, None),
            ("2026-08-04", "OT-CHG", "Operation theatre charges", "Operation Theatre", 1, 18000, None),
            ("2026-08-04", "ANS-GA-4", "Anaesthesia - General, complex (Grade IV)", "Anaesthesia", 1, 22000, None),
            ("2026-08-04", "PH-CEF1G", "Inj. Ceftriaxone 1g", "Pharmacy", 6, 180, 1800),
            ("2026-08-04", "PH-PCM-IV", "Inj. Paracetamol 1g IV", "Pharmacy", 4, 120, None),
            ("2026-08-04", "CS-KIT", "Surgical consumables kit", "Consumables", 1, 3200, None),
            ("2026-08-03", "NM-ADM", "Admission kit", "Non-Medical", 1, 650, None),
            ("2026-08-05", "NM-ATF", "Attendant food", "Non-Medical", 3, 300, None),
            ("2026-08-05", "LAB-CRP", "C-reactive protein (CRP)", "Laboratory", 1, 700, None),
        ],
        "gross_override": None,
        "deductions": [
            ("Non-payable items", "Admission kit; Attendant food", "NONPAY"),
            ("Co-payment", "20% of admissible amount", ("COPAY", 20)),
        ],
    },
    "BILL-002": {
        "file": "bill_002_netra_cataract.pdf",
        "policy": "POLICY-GOLD",
        "hospital": "Netra Eye Care Centre",
        "address": "College Road, Nashik 422005 (fictional)",
        "header": {
            "Bill No": "NEC/DC/26/03317", "Bill Date": "2026-07-21",
            "Patient Name": "Sushila Rao", "Age / Sex": "58 / F",
            "UHID": "NEC-0033170", "Policy No": "SHG-2026-004417",
            "Insurer / TPA": "Bharat Shield / MediAssist", "Network Hospital": "Yes",
            "Admission": "2026-07-21", "Discharge": "2026-07-21",
            "Diagnosis": "Senile cataract, right eye", "Procedure": "Cataract surgery (phacoemulsification with IOL), right eye",
        },
        "lines": [
            ("2026-07-21", "RM-DAY", "Day care bed charges", "Room", 1, 2500, None),
            ("2026-07-21", "CON-OPH", "Ophthalmologist consultation", "Consultation", 1, 1200, None),
            ("2026-07-21", "OPH-ASCAN", "A-scan biometry", "Radiology", 1, 1500, None),
            ("2026-07-21", "SUR-PHACO", "Phacoemulsification - surgeon fee", "Surgery", 1, 22000, None),
            ("2026-07-21", "IMP-IOL", "Foldable IOL (monofocal)", "Implant", 1, 12000, None),
            ("2026-07-21", "OT-CHG", "Operation theatre charges", "Operation Theatre", 1, 6500, None),
            ("2026-07-21", "PH-EYEDROP", "Post-operative eye drops pack", "Pharmacy", 2, 450, 1350),
            ("2026-07-21", "CS-SURG", "Surgical consumables", "Consumables", 1, 1800, None),
        ],
        "gross_override": 49850,  # printed lines sum to 48,850
        "deductions": [
            ("Sub-limit", "Cataract sub-limit applied at Rs. 35,000", ("CAP", 35000)),
        ],
    },
    "BILL-003": {
        "file": "bill_003_lotus_knee_replacement.pdf",
        "policy": "POLICY-SILVER",
        "hospital": "Lotus Orthopaedic Hospital",
        "address": "AB Road, Vijay Nagar, Indore 452010 (fictional)",
        "header": {
            "Bill No": "LOH/IP/26/11904", "Bill Date": "2026-09-06",
            "Patient Name": "Farhan Qureshi", "Age / Sex": "63 / M",
            "UHID": "LOH-0119040", "Policy No": "CFS-2026-118230",
            "Insurer / TPA": "Navodaya / HealthBridge", "Network Hospital": "Yes",
            "Admission": "2026-09-01", "Discharge": "2026-09-06",
            "Diagnosis": "Primary osteoarthritis, left knee", "Procedure": "Total knee replacement, left",
        },
        "lines": [
            ("2026-09-01", "RM-SEMI", "Room charges - Semi-private", "Room", 6, 2800, None),
            ("2026-09-01", "CON-ORT", "Orthopaedic consultation", "Consultation", 5, 1000, None),
            ("2026-09-01", "RAD-MRI-KNEE", "MRI knee (plain)", "Radiology", 1, 14500, None),
            ("2026-09-01", "LAB-PNL", "Pre-operative lab panel", "Laboratory", 1, 2200, None),
            ("2026-09-02", "SUR-TKR", "Total knee replacement - surgeon fee", "Surgery", 1, 85000, None),
            ("2026-09-02", "IMP-KNEE", "Knee implant (cemented)", "Implant", 1, 65000, None),
            ("2026-09-02", "OT-CHG", "Operation theatre charges", "Operation Theatre", 1, 25000, None),
            ("2026-09-02", "ANS-GA-2", "Anaesthesia - General (Grade II)", "Anaesthesia", 1, 10000, None),
            ("2026-09-02", "PH-MISC", "Pharmacy - medicines and IV fluids", "Pharmacy", 1, 7400, None),
            ("2026-09-02", "NM-PPE", "Gloves and masks pack", "Non-Medical", 1, 1200, None),
            ("2026-09-04", "PHY-SESS", "Physiotherapy session", "Physiotherapy", 1, 800, None),
            ("2026-09-04", "PHY-SESS", "Physiotherapy session", "Physiotherapy", 1, 800, None),
            ("2026-09-05", "PHY-SESS", "Physiotherapy session", "Physiotherapy", 1, 800, None),
        ],
        "gross_override": None,
        "deductions": [
            ("Non-payable items", "Gloves and masks pack", "NONPAY"),
            ("Sub-limit", "Knee replacement sub-limit applied at Rs. 1,00,000", ("CAP", 100000)),
            ("Co-payment", "20% of admissible amount", ("COPAY", 20)),
        ],
    },
    "BILL-004": {
        "file": "bill_004_sanjeevani_dengue_clean.pdf",
        "policy": "POLICY-SILVER",
        "hospital": "Sanjeevani Hospital",
        "address": "Dharampeth, Nagpur 440010 (fictional)",
        "header": {
            "Bill No": "SJH/IP/26/07751", "Bill Date": "2026-09-13",
            "Patient Name": "Kavya Iyer", "Age / Sex": "29 / F",
            "UHID": "SJH-0077510", "Policy No": "CFS-2026-118230",
            "Insurer / TPA": "Navodaya / HealthBridge", "Network Hospital": "Yes",
            "Admission": "2026-09-10", "Discharge": "2026-09-13",
            "Diagnosis": "Dengue fever without warning signs", "Procedure": "Medical management (no surgery)",
        },
        "lines": [
            ("2026-09-10", "RM-GEN", "Room charges - General ward", "Room", 3, 1800, None),
            ("2026-09-10", "CON-PHY", "Physician consultation", "Consultation", 3, 800, None),
            ("2026-09-10", "LAB-CBC", "Complete blood count (CBC)", "Laboratory", 1, 450, None),
            ("2026-09-11", "LAB-CBC", "Complete blood count (CBC)", "Laboratory", 1, 450, None),
            ("2026-09-12", "LAB-CBC", "Complete blood count (CBC)", "Laboratory", 1, 450, None),
            ("2026-09-10", "LAB-NS1", "Dengue NS1 antigen", "Laboratory", 1, 900, None),
            ("2026-09-10", "PH-PCM-IV", "Inj. Paracetamol 1g IV", "Pharmacy", 3, 120, None),
            ("2026-09-10", "PH-IVNS", "IV fluid - Normal saline 500 ml", "Pharmacy", 6, 95, None),
            ("2026-09-11", "PH-MISC", "Pharmacy - oral medicines", "Pharmacy", 1, 1850, None),
            ("2026-09-10", "NM-ADM", "Admission kit", "Non-Medical", 1, 650, None),
        ],
        "gross_override": None,
        "deductions": [
            ("Non-payable items", "Admission kit", "NONPAY"),
            ("Co-payment", "20% of admissible amount", ("COPAY", 20)),
        ],
    },
}


def settle(spec: dict) -> dict:
    """Reproduce what the (fictional) TPA did, including its planted mistakes."""
    lines = [(*ln[:6], ln[6] if ln[6] is not None else ln[4] * ln[5]) for ln in spec["lines"]]
    gross = spec["gross_override"] if spec["gross_override"] is not None else sum(ln[6] for ln in lines)
    rows, nonpay, cap, copay_pct = [], 0.0, None, 0.0
    for label, basis, kind in spec["deductions"]:
        if kind == "NONPAY":
            names = [n.strip().lower() for n in basis.split(";")]
            nonpay = sum(ln[6] for ln in lines if any(n in ln[2].lower() for n in names))
        elif kind[0] == "CAP":
            cap = kind[1]
        elif kind[0] == "COPAY":
            copay_pct = kind[1]
    admissible = gross - nonpay
    capped = min(admissible, cap) if cap is not None else admissible
    copay = round(capped * copay_pct / 100, 2)
    approved = round(capped - copay, 2)
    for label, basis, kind in spec["deductions"]:
        if kind == "NONPAY":
            rows.append((label, basis, nonpay))
        elif kind[0] == "CAP":
            rows.append((label, basis, admissible - capped))
        elif kind[0] == "COPAY":
            rows.append((label, basis, copay))
    return {"lines": lines, "gross": gross, "deductions": rows, "approved": approved, "patient": round(gross - approved, 2)}


def build_bill(bill_id: str, spec: dict) -> tuple[Path, dict]:
    s = settle(spec)
    path = OUT_BILLS / spec["file"]
    doc = SimpleDocTemplate(str(path), pagesize=A4, leftMargin=14 * mm, rightMargin=14 * mm, topMargin=14 * mm, bottomMargin=18 * mm,
                            title=f"{spec['hospital']} - Final Bill", author=spec["hospital"])
    story = [
        Paragraph(spec["hospital"], H1),
        Paragraph(spec["address"], SMALL),
        Paragraph("IN-PATIENT FINAL BILL (ITEMISED)", H2),
    ]
    items = list(spec["header"].items())
    header_rows = [[items[i][0], Paragraph(items[i][1], CELL), items[i + 1][0], Paragraph(items[i + 1][1], CELL)]
                   for i in range(0, len(items), 2)]
    ht = Table(header_rows, colWidths=[28 * mm, 62 * mm, 28 * mm, 64 * mm])
    ht.setStyle(GRID)
    ht.setStyle(TableStyle([("FONT", (0, 0), (0, -1), "Helvetica-Bold", 8.3), ("FONT", (2, 0), (2, -1), "Helvetica-Bold", 8.3)]))
    story += [ht, Spacer(1, 8), Paragraph("Itemised Charges", H2)]

    rows = [["#", "Date", "Code", "Description", "Dept", "Qty", "Rate (Rs.)", "Amount (Rs.)"]]
    for i, (d, code, desc, dept, qty, rate, amt) in enumerate(s["lines"], start=1):
        rows.append([str(i), d, code, Paragraph(desc, CELL), Paragraph(dept, CELL), str(qty), rs(rate), rs(amt)])
    lt = Table(rows, colWidths=[7 * mm, 19 * mm, 23 * mm, 55 * mm, 29 * mm, 9 * mm, 19 * mm, 21 * mm], repeatRows=1)
    lt.setStyle(GRID)
    lt.setStyle(TableStyle([("FONT", (0, 0), (-1, 0), "Helvetica-Bold", 8.3), ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#eef2f7")),
                            ("ALIGN", (5, 1), (-1, -1), "RIGHT")]))
    story += [lt, Spacer(1, 8), Paragraph("Insurance Settlement (Cashless)", H2)]

    drows = [["Deduction", "Basis", "Amount (Rs.)"]] + [[l, Paragraph(b, CELL), rs(a)] for l, b, a in s["deductions"]]
    dt = Table(drows, colWidths=[40 * mm, 100 * mm, 42 * mm])
    dt.setStyle(GRID)
    dt.setStyle(TableStyle([("FONT", (0, 0), (-1, 0), "Helvetica-Bold", 8.3), ("ALIGN", (2, 1), (2, -1), "RIGHT")]))
    story += [dt, Spacer(1, 6)]

    srows = [["Gross Total", rs(s["gross"])], ["Insurer Approved Amount", rs(s["approved"])], ["Patient Payable", rs(s["patient"])]]
    st = Table(srows, colWidths=[140 * mm, 42 * mm])
    st.setStyle(GRID)
    st.setStyle(TableStyle([("FONT", (0, 0), (-1, -1), "Helvetica-Bold", 9), ("ALIGN", (1, 0), (1, -1), "RIGHT")]))
    story += [st, Spacer(1, 10), Paragraph("This is a computer-generated bill. E. &amp; O.E.", SMALL)]
    doc.build(story, onFirstPage=watermark, onLaterPages=watermark)
    return path, s


# Ground truth for the end-to-end tests: finding type -> bill line numbers involved.
EXPECTED = {
    "BILL-001": {
        "policy": "POLICY-GOLD",
        "findings": [
            {"type": "DUPLICATE_CHARGE", "lines": [3, 4], "confidence": "High"},
            {"type": "ARITHMETIC_ERROR", "lines": [9], "confidence": "High"},
            {"type": "UPCODING_SIGNAL", "lines": [8], "confidence": "Worth reviewing"},
            {"type": "COVERAGE_MISMATCH", "lines": [12], "confidence": "High", "topic": "non_medical"},
            {"type": "COVERAGE_MISMATCH", "lines": [], "confidence": "High", "topic": "copay"},
        ],
    },
    "BILL-002": {
        "policy": "POLICY-GOLD",
        "findings": [
            {"type": "ARITHMETIC_ERROR", "lines": [7], "confidence": "High"},
            {"type": "TOTAL_MISMATCH", "lines": [], "confidence": "High"},
            {"type": "COVERAGE_MISMATCH", "lines": [], "confidence": "High", "topic": "sub_limit"},
        ],
    },
    "BILL-003": {
        "policy": "POLICY-SILVER",
        "findings": [
            {"type": "QUANTITY_MISMATCH", "lines": [1], "confidence": "High"},
            {"type": "DUPLICATE_CHARGE", "lines": [11, 12], "confidence": "Worth reviewing"},
            {"type": "PRICE_OUTLIER", "lines": [3], "confidence": "Worth reviewing"},
            {"type": "COVERAGE_MISMATCH", "lines": [], "confidence": "High", "topic": "sub_limit"},
        ],
    },
    "BILL-004": {"policy": "POLICY-SILVER", "findings": []},
}


def main() -> None:
    OUT_BILLS.mkdir(parents=True, exist_ok=True)
    OUT_POLICIES.mkdir(parents=True, exist_ok=True)
    catalog = {"policies": {}, "bills": {}}
    for pid, spec in POLICIES.items():
        p = build_policy(spec)
        catalog["policies"][pid] = {"file": f"policies/{p.name}", "plan": spec["plan"], "insurer": spec["insurer"]}
        print(f"wrote {p.relative_to(ROOT)}")
    for bid, spec in BILLS.items():
        p, s = build_bill(bid, spec)
        catalog["bills"][bid] = {
            "file": f"bills/{p.name}", "policy": spec["policy"], "hospital": spec["hospital"],
            "procedure": spec["header"]["Procedure"], "patient": spec["header"]["Patient Name"],
            "gross": s["gross"], "insurer_approved": s["approved"], "patient_payable": s["patient"],
            "clean": not EXPECTED[bid]["findings"],
        }
        print(f"wrote {p.relative_to(ROOT)}  gross={rs(s['gross'])} approved={rs(s['approved'])} patient={rs(s['patient'])}")
    (ROOT / "samples" / "catalog.json").write_text(json.dumps(catalog, indent=2))
    (ROOT / "samples" / "expected.json").write_text(json.dumps(EXPECTED, indent=2))
    print("wrote samples/catalog.json, samples/expected.json")


if __name__ == "__main__":
    main()
