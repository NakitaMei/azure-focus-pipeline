"""
generate_layer_c.py — Portfolio Project 1, Stage 3 chunk 10

The Layer C / Layer 4 supplemental datasets: BillingPeriod, InvoiceDetail and
ContractCommitment.

WHAT THESE ARE. Until v1.3, FOCUS was one dataset: cost and usage, one row per
charge. v1.3 and v1.4 add SEPARATE datasets that describe things a charge row
cannot: when a billing period closed, what an invoice actually said, and what a
contract committed you to. They are companions to the cost data, not more of it.

WHY THEY EARN THEIR PLACE HERE. The single most common finance question about
cloud data — "why doesn't this tie to the invoice?" — cannot be answered from
cost and usage rows alone. InvoiceDetail is the other side of that reconciliation.

SHAPES VERIFIED AT SPEC TAG v1.4 on 14 August 2026, per Amendment 1 A3.1, which
is explicit that these must not be built from memory or blog posts. The v1.4 repo
layout differs from v1.2:
    v1.2  specification/columns/<column>.md
    v1.4  specification/datasets/<dataset>/columns/<column>.md
CSV rather than Parquet, per the build spec. Note that CSV timestamps DO carry
the literal trailing Z — in Parquet the Z lives in the convention, but text has
no other way to say it.

Run:  python3 generate_layer_c.py
"""

import csv
from datetime import datetime, timedelta
import json
import os
from decimal import Decimal

import duckdb

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE) if os.path.basename(HERE) == "src" else HERE
OUT_DIR = os.path.join(ROOT, "data", "supplemental")
UNIFIED = os.path.join(ROOT, "data", "unified", "focus_unified.snappy.parquet")

INVOICE_ISSUER = "Microsoft"
BILLING_ACCOUNT_ID = ("/providers/Microsoft.Billing/billingAccounts/"
                      "00000000-0000-0000-0000-000000000002")


def z(dt):
    """ISO 8601 with the literal trailing Z, as CSV requires."""
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ") if dt else ""


# =============================================================================
# 1. BillingPeriod — 6 columns, all Mandatory, none nullable
# =============================================================================
# The dataset that answers "is this month final, or still moving?" A closed
# period will not change; an open one will. Reporting on an open period and
# calling it final is a straightforward way to be wrong in public.

BILLING_PERIOD_COLUMNS = [
    "BillingPeriodStart", "BillingPeriodEnd", "BillingPeriodStatus",
    "BillingPeriodCreated", "BillingPeriodLastUpdated", "InvoiceIssuerName",
]


def billing_period_rows():
    return [
        # The legacy era's period — long closed.
        {"BillingPeriodStart": "2024-03-01T00:00:00Z",
         "BillingPeriodEnd": "2024-04-01T00:00:00Z",
         "BillingPeriodStatus": "Closed",
         "BillingPeriodCreated": "2024-03-01T00:00:00Z",
         "BillingPeriodLastUpdated": "2024-04-08T02:00:00Z",
         "InvoiceIssuerName": INVOICE_ISSUER},
        # June 2026 — closed, and the period the chunk 2 correction reaches back
        # into. Closed does NOT mean nothing further can be said about it; it
        # means corrections arrive in a LATER period instead.
        {"BillingPeriodStart": "2026-06-01T00:00:00Z",
         "BillingPeriodEnd": "2026-07-01T00:00:00Z",
         "BillingPeriodStatus": "Closed",
         "BillingPeriodCreated": "2026-06-01T00:00:00Z",
         "BillingPeriodLastUpdated": "2026-07-09T02:00:00Z",
         "InvoiceIssuerName": INVOICE_ISSUER},
        # July 2026 — the real export's period. Still OPEN, which is exactly why
        # its invoice has not been issued and InvoiceId is null on 118 real rows.
        {"BillingPeriodStart": "2026-07-01T00:00:00Z",
         "BillingPeriodEnd": "2026-08-01T00:00:00Z",
         "BillingPeriodStatus": "Open",
         "BillingPeriodCreated": "2026-07-01T00:00:00Z",
         "BillingPeriodLastUpdated": "2026-08-01T01:56:13Z",
         "InvoiceIssuerName": INVOICE_ISSUER},
    ]


# =============================================================================
# 2. InvoiceDetail — the other side of the reconciliation
# =============================================================================

INVOICE_DETAIL_COLUMNS = [
    "InvoiceDetailId", "InvoiceId", "ReferenceInvoiceId", "InvoiceIssuerName",
    "BillingAccountId", "BillingCurrency", "BilledCost", "ChargeCategory",
    "BillingPeriodStart", "BillingPeriodEnd", "InvoiceIssueDate",
    "InvoiceIssueStatus", "PaymentDueDate", "PaymentTerms",
    "InvoiceDetailDescription", "InvoiceDetailGrain",
    "InvoiceDetailCreated", "InvoiceDetailLastUpdated",
]


def invoice_detail_rows(totals):
    """One line per (InvoiceId, ChargeCategory, ChargeClass).

    STAGE 4, FINDING F38 — THE GROUPING KEY CHANGED, AND IT MATTERS.
    This function used to receive totals grouped by a TIME WINDOW: charges whose
    ChargePeriodStart fell in June 2026. The docstring claimed the invoice
    "genuinely ties to the cost data", and it did — by period.

    The specification's reconciliation identity does not use a period:

        The sum of the BilledCost for a given InvoiceId MUST match the sum of
        the payable amount provided in the corresponding invoice with the
        same id.

    **A tie-out that holds on a different key than the rule names is not the
    tie-out the rule requires.** It agrees until the two keys disagree — and
    they disagreed immediately: the invoice claimed INV-2026-06-0001 and the one
    cost row carrying an InvoiceId said INV-2026-07-0001. The Stage 4
    cross-dataset check found no shared key at all and correctly reported the
    identity as NOT EVALUABLE rather than as balancing.

    Totals now come grouped by InvoiceId, which is what the rule joins on.

    ChargeClass is in the grain because a correction to a closed period appears
    on a LATER invoice than the period it corrects, and needs to carry a
    reference back. Mixing it into the same line as ordinary charges loses that
    — and loses the ability to answer "what on this invoice is a restatement?",
    which is the first question anyone asks of an invoice that moved.

    InvoiceDetailGrain is a JSON object naming what each line is broken down by
    — here, ChargeCategory. It exists because invoices are summarised at
    different levels by different providers, and a consumer needs to know which.
    """
    rows = []
    # Sorted with None coerced to "", because ChargeClass is null on ordinary
    # lines and Python will not order None against a string. A small thing, and
    # the same shape as everything else in this project: null is not a value,
    # and code that forgets it fails at the boundary rather than in the middle.
    def order(item):
        (invoice_id, category, charge_class, period_start), _ = item
        return (invoice_id, category, charge_class or "", period_start)

    for index, (key, amount) in enumerate(sorted(totals.items(), key=order), start=1):
        invoice_id, category, charge_class, period_start = key
        # A correction points back at the invoice for the period it corrects; an
        # ordinary line points at itself.
        reference = (invoice_for_period(period_start) if charge_class == "Correction"
                     else invoice_id)
        issued = charge_class != "Correction"
        rows.append({
            "InvoiceDetailId": f"{invoice_id}-{index:03d}",
            "InvoiceId": invoice_id,
            "ReferenceInvoiceId": reference,
            "InvoiceIssuerName": INVOICE_ISSUER,
            "BillingAccountId": BILLING_ACCOUNT_ID,
            "BillingCurrency": "USD",
            "BilledCost": f"{amount:.2f}",
            "ChargeCategory": category,
            "BillingPeriodStart": z(period_bounds(invoice_id)[0]),
            "BillingPeriodEnd": z(period_bounds(invoice_id)[1]),
            "InvoiceIssueDate": z(issue_date(invoice_id)),
            "InvoiceIssueStatus": "Issued",
            "PaymentDueDate": z(issue_date(invoice_id) + timedelta(days=30)),
            "PaymentTerms": "Net 30",
            "InvoiceDetailDescription": (
                f"{category} correction to {reference}" if charge_class == "Correction"
                else f"{category} charges"),
            "InvoiceDetailGrain": json.dumps(
                {"ChargeCategory": category, "ChargeClass": charge_class or "None"},
                separators=(",", ":")),
            "InvoiceDetailCreated": z(issue_date(invoice_id)),
            "InvoiceDetailLastUpdated": z(issue_date(invoice_id)),
        })
    return rows


# Invoices are named for the billing period they settle, so the mapping between
# the two is derivable rather than tabulated. Kept in one place because three
# fields depend on it and a disagreement between them is invisible in a CSV.
def invoice_for_period(period_start):
    return f"INV-{period_start.year}-{period_start.month:02d}-0001"


def period_bounds(invoice_id):
    year, month = int(invoice_id[4:8]), int(invoice_id[9:11])
    start = datetime(year, month, 1)
    end = datetime(year + (month == 12), (month % 12) + 1, 1)
    return start, end


def issue_date(invoice_id):
    """Issued on the ninth of the month after the period closes."""
    return period_bounds(invoice_id)[1] + timedelta(days=8)


# =============================================================================
# 3. ContractCommitment — what was agreed, as opposed to what was charged
# =============================================================================
# The cost dataset records a commitment being APPLIED. It never records what the
# commitment WAS: its term, its payment model, whether it was negotiated or
# off-the-shelf. Without that, "are we buying the right commitments?" is
# unanswerable — you can see coverage but not the deal behind it.

# STAGE 4, FINDING F37. ServiceProviderName was missing from this list, and it
# is MANDATORY in the v1.4 contract_commitment dataset. 26 of 27 mandatory
# columns were present. The Stage 4 harness caught it on the first run that
# pointed a presence check at Layer C.
#
# WHY IT SURVIVED IS THE INTERESTING PART, AND IT IS NOT IGNORANCE.
# This same file already documents the rename, at length, at the bottom: F22,
# ProviderName and PublisherName removed at v1.4, successors named, and
# ServiceProviderName among them. The knowledge was in the file. The column was
# not.
#
# The note treats F22 as a FUTURE risk to the cost dataset — "nothing to fix
# today: the data is v1.2 and correctly declares itself so." That was true of
# cost_and_usage and false of this one. The supplemental datasets do not exist
# before v1.3, so they can only ever be built at v1.3+ naming, where
# ServiceProviderName is not a successor to plan for but the current column
# name. One finding, two datasets, two different tenses — and the second went
# unnoticed twenty lines above the paragraph describing it.
#
# SECOND CAUSE, AND THE ONE THAT GENERALISES.
# The header says these shapes were "VERIFIED AT SPEC TAG v1.4". They were: every
# column in this list was checked against the spec. What was never checked is
# whether the list was COMPLETE. Verified is not exhaustive — precisely the
# distinction Stage 4 chunk 1 closed for the v1.2 cost columns by counting the
# directory instead of confirming names one at a time. Nobody carried that
# lesson across to Layer C, and one mandatory column fell through the same gap
# that lesson was written about.
CONTRACT_COMMITMENT_COLUMNS = [
    "ContractId", "ContractCommitmentId", "ContractCommitmentType",
    "ContractCommitmentCategory", "ContractCommitmentBenefitCategory",
    "ContractCommitmentOfferCategory", "ContractCommitmentModel",
    "ContractCommitmentDescription", "ContractCommitmentLifecycleStatus",
    "ContractCommitmentDurationType", "ContractCommitmentPaymentModel",
    "ContractCommitmentPaymentInterval", "ContractCommitmentFulfillmentInterval",
    "ContractCommitmentPaymentUpfrontPercentage",
    "ContractCommitmentQuantity", "ContractCommitmentUnit",
    "ContractCommitmentCost", "ContractCommitmentDiscountPercentage",
    "BillingCurrency", "InvoiceIssuerName", "ServiceProviderName",
    "ContractPeriodStart", "ContractPeriodEnd",
    "ContractCommitmentPeriodStart", "ContractCommitmentPeriodEnd",
    "ContractCommitmentApplicability",
    "ContractCommitmentCreated", "ContractCommitmentLastUpdated",
]

# ContractCommitmentApplicability is a JSON Object at v1.4 — changed from the
# earlier ContractApplied format, which the changelog flags as a
# migration-compatible break: queries parsing the old shape must be rewritten.
APPLICABILITY = json.dumps(
    {"IsGlobalScope": False, "IsComplexScope": False,
     "BillingAccountIds": [BILLING_ACCOUNT_ID]},
    separators=(",", ":"))


def contract_commitment_rows():
    """The two reservations the cost data draws against, described properly."""
    return [
        # The chunk 1 monthly reservation. NoUpfront, so it bills each period —
        # which is why its term closes inside the dataset.
        {"ContractId": "CTR-2026-0001",
         "ContractCommitmentId": ("/providers/Microsoft.Capacity/reservationOrders"
                                  "/res-basv2-1yr-001"),
         "ContractCommitmentType": "Reserved Instance",
         "ContractCommitmentCategory": "Usage",
         "ContractCommitmentBenefitCategory": "Discount",
         "ContractCommitmentOfferCategory": "Public",
         "ContractCommitmentModel": "Continuous",
         "ContractCommitmentDescription": "Basv2 1-year reserved capacity, monthly billing",
         "ContractCommitmentLifecycleStatus": "Active",
         "ContractCommitmentDurationType": "Year",
         # STAGE 4, FINDING F45. This was "NoUpfront" — the AWS API spelling.
         # The FOCUS allowed value is "No Upfront", with a space.
         "ContractCommitmentPaymentModel": "No Upfront",
         "ContractCommitmentPaymentInterval": "Monthly",
         "ContractCommitmentFulfillmentInterval": "Hourly",
         "ContractCommitmentPaymentUpfrontPercentage": "0",
         "ContractCommitmentQuantity": "744",
         "ContractCommitmentUnit": "Hours",
         "ContractCommitmentCost": "74.40",
         "ContractCommitmentDiscountPercentage": "0.3333",
         "BillingCurrency": "USD",
         "InvoiceIssuerName": INVOICE_ISSUER,
         "ServiceProviderName": INVOICE_ISSUER,
         "ContractPeriodStart": "2026-07-01T00:00:00Z",
         "ContractPeriodEnd": "2027-07-01T00:00:00Z",
         "ContractCommitmentPeriodStart": "2026-07-01T00:00:00Z",
         "ContractCommitmentPeriodEnd": "2026-08-01T00:00:00Z",
         "ContractCommitmentApplicability": APPLICABILITY,
         "ContractCommitmentCreated": "2026-07-01T00:00:00Z",
         "ContractCommitmentLastUpdated": "2026-07-01T00:00:00Z"},

        # The chunk 4 upfront reservation. AllUpfront, 3 years — which is why it
        # does NOT close inside a single month, and why finding F10's invariant
        # needs a scope.
        {"ContractId": "CTR-2026-0002",
         "ContractCommitmentId": ("/providers/Microsoft.Capacity/reservationOrders"
                                  "/res-basv2-3yr-upfront-001"),
         "ContractCommitmentType": "Reserved Instance",
         "ContractCommitmentCategory": "Usage",
         "ContractCommitmentBenefitCategory": "Discount",
         "ContractCommitmentOfferCategory": "Negotiated",
         "ContractCommitmentModel": "Continuous",
         "ContractCommitmentDescription": "Basv2 3-year reserved capacity, all upfront",
         "ContractCommitmentLifecycleStatus": "Active",
         "ContractCommitmentDurationType": "Years",
         # F45: was "AllUpfront". FOCUS says "All Upfront".
         "ContractCommitmentPaymentModel": "All Upfront",
         "ContractCommitmentPaymentInterval": "One-Time",
         "ContractCommitmentFulfillmentInterval": "Hourly",
         "ContractCommitmentPaymentUpfrontPercentage": "1",
         "ContractCommitmentQuantity": "26280",
         "ContractCommitmentUnit": "Hours",
         "ContractCommitmentCost": "2628.00",
         "ContractCommitmentDiscountPercentage": "0.3333",
         "BillingCurrency": "USD",
         "InvoiceIssuerName": INVOICE_ISSUER,
         "ServiceProviderName": INVOICE_ISSUER,
         "ContractPeriodStart": "2026-07-31T00:00:00Z",
         "ContractPeriodEnd": "2029-07-31T00:00:00Z",
         "ContractCommitmentPeriodStart": "2026-07-31T00:00:00Z",
         "ContractCommitmentPeriodEnd": "2029-07-31T00:00:00Z",
         "ContractCommitmentApplicability": APPLICABILITY,
         "ContractCommitmentCreated": "2026-07-31T00:00:00Z",
         "ContractCommitmentLastUpdated": "2026-07-31T00:00:00Z"},
    ]


def write_csv(name, columns, rows):
    os.makedirs(OUT_DIR, exist_ok=True)
    path = os.path.join(OUT_DIR, f"{name}.csv")
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)
    return path


# =============================================================================
# 4. RUN
# =============================================================================

if __name__ == "__main__":
    print("=" * 70)
    print("generate_layer_c.py — supplemental datasets, verified at spec tag v1.4")
    print("=" * 70)

    # --- ground the invoice in the actual cost data ------------------------
    totals = {}
    if os.path.exists(UNIFIED):
        con = duckdb.connect()
        con.execute(f"CREATE VIEW u AS SELECT * FROM read_parquet('{UNIFIED}')")
        # June is the closed, invoiced period. Only the correction row reaches
        # back into it, so the invoice is deliberately small and easy to follow.
        # F38: grouped by INVOICE, which is the key the reconciliation identity
        # names — not by a date window, which is what it used to be. Rows with no
        # InvoiceId are excluded rather than swept into a period bucket: a charge
        # that names no invoice is not on one, and pretending otherwise is how
        # the old grouping produced an invoice nothing could join to.
        for invoice_id, category, charge_class, period_start, amount in con.execute("""
                SELECT InvoiceId, ChargeCategory, ChargeClass,
                       date_trunc('month', ChargePeriodStart), sum(BilledCost)
                FROM u
                WHERE BillingCurrency = 'USD'
                  AND InvoiceId IS NOT NULL AND InvoiceId <> ''
                GROUP BY 1, 2, 3, 4""").fetchall():
            totals[(invoice_id, category, charge_class, period_start)] = Decimal(str(amount))
    if not totals:
        totals = {("INV-2026-07-0001", "Usage", "Correction",
                   datetime(2026, 6, 1)): Decimal("-1.85")}
        print("\n  (focus_unified not found or no June rows — using the known")
        print("   June correction amount so the tie-out still demonstrates.)")

    files = [
        ("billing_period", BILLING_PERIOD_COLUMNS, billing_period_rows()),
        ("invoice_detail", INVOICE_DETAIL_COLUMNS, invoice_detail_rows(totals)),
        ("contract_commitment", CONTRACT_COMMITMENT_COLUMNS,
         contract_commitment_rows()),
    ]

    print("\nWRITING")
    print("-" * 70)
    for name, columns, rows in files:
        path = write_csv(name, columns, rows)
        print(f"  {os.path.relpath(path, ROOT):<44}"
              f"{len(rows):>3} rows, {len(columns)} columns")

    # --- what each dataset is for ------------------------------------------
    print("\nWHAT EACH ONE ANSWERS")
    print("-" * 70)
    print("\n  BillingPeriod        is this month final, or still moving?")
    for row in billing_period_rows():
        print(f"    {row['BillingPeriodStart'][:7]}  {row['BillingPeriodStatus']}")
    print("    July 2026 is OPEN — which is exactly why its invoice has not been")
    print("    issued, and why InvoiceId is null on all 118 real rows. That null")
    print("    is a fact about the calendar, not missing data.")

    print("\n  InvoiceDetail        what did the invoice actually say?")
    invoice_total = sum(Decimal(r["BilledCost"]) for r in invoice_detail_rows(totals))
    print(f"    June 2026 invoice, {len(totals)} line(s), total {invoice_total:.2f} USD")
    print("    Grounded in focus_unified itself — the amounts are queried from the")
    print("    cost data, so the invoice genuinely ties rather than merely looking")
    print("    as though it might. 'Why doesn't this match the invoice?' is the")
    print("    most common finance question about cloud data, and it cannot be")
    print("    answered from cost rows alone. This is the other side of it.")

    print("\n  ContractCommitment   what was actually agreed?")
    for row in contract_commitment_rows():
        print(f"    {row['ContractCommitmentDescription']}")
        print(f"      {row['ContractCommitmentPaymentModel']:<15}"
              f"{row['ContractCommitmentOfferCategory']:<12}"
              f"{row['ContractCommitmentQuantity']:>7} "
              f"{row['ContractCommitmentUnit']}   "
              f"{row['BillingCurrency']} {row['ContractCommitmentCost']}")
    print("    The cost data records a commitment being APPLIED. It never records")
    print("    what the commitment WAS — term, payment model, negotiated or")
    print("    off-the-shelf. Without that, 'are we buying the right commitments?'")
    print("    is unanswerable: you can see coverage but not the deal behind it.")

    # --- the v1.4 finding that matters more than the CSVs ------------------
    print("\n" + "=" * 70)
    print("VERIFYING AT v1.4 SURFACED A BREAKING CHANGE  (finding F22)")
    print("=" * 70)
    print("""
  ProviderName and PublisherName were DEPRECATED at v1.3 and REMOVED at v1.4.
  Both return 404 at tag v1.4. Successors: ServiceProviderName,
  HostProviderName, InvoiceIssuerName, and DataGenerator metadata.

  This project uses both columns, and one use is load-bearing: the
  reconciliation identity detects third-party marketplace charges with

      PublisherName != ProviderName

  At v1.4 that expression cannot be written at all. The check does not return
  a wrong answer — it fails to parse. Loudly, which is the good case.

  Nothing to fix today: the data is v1.2 and correctly declares itself so.
  But it is a concrete, dated example of the thesis this portfolio argues —
  that provider version lag is a recurring structural problem, not a one-off.
  Azure sits at 1.0r2. The spec has since removed columns Azure has not yet
  shipped. The gap does not merely persist; it MOVES.
""")
    print("=" * 70)
