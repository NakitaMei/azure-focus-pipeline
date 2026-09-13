"""
self_test.py — Portfolio Project 1, Stage 3 chunk 8

The generator checking its own output.

TWO THINGS MAKE THIS MORE THAN A FORMALITY.

1. It reads the files BACK FROM DISK rather than inspecting the rows in memory.
   Testing the in-memory rows would only prove the fixtures were built correctly;
   reading the written Parquet also proves the WRITE worked — the types survived,
   the nullability survived, nothing was silently coerced on the way out.

2. It is checked against data known to be BROKEN. Every check runs twice: over the
   clean layers, where it must stay silent, and over data/negative/, where each of
   the 14 planted violations must be caught. A harness that has only ever seen
   valid data has never been proven to detect anything (findings F16, F19).

SEVERITY follows RFC 2119, which FOCUS adopts:
    FAIL  - a MUST or MUST NOT was broken. Non-conformant.
    WARN  - a SHOULD or SHOULD NOT was broken. Conformant, but not recommended.
            Azure's real export sits here (finding F2 refined).
    PASS  - checked and clean.
Collapsing these into one severity makes a harness either too noisy to use or too
permissive to trust.

Run:  python3 self_test.py
Exit code is 0 when no MUST is broken, 1 otherwise — so CI can use it later.
"""

import json
import os
import sys
from decimal import Decimal

import duckdb
import pyarrow.parquet as pq

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE) if os.path.basename(HERE) == "src" else HERE

CLEAN_LAYERS = [
    ("v1.2",    os.path.join(ROOT, "data", "synthetic", "v1.2")),
    ("pre-1.2", os.path.join(ROOT, "data", "synthetic", "pre-1.2")),
]
NEGATIVE_LAYER = os.path.join(ROOT, "data", "negative")


# =============================================================================
# ALLOWED VALUES — read from the specification at tag v1.2, not from memory
# =============================================================================
# Finding F13: chunk 0's typo guard validates column NAMES. Nothing validated
# column VALUES, and a wrong enum value is more dangerous than a wrong column
# name because it survives into the data and looks entirely plausible in a report.

ALLOWED = {
    "ChargeCategory": {"Usage", "Purchase", "Tax", "Credit", "Adjustment"},
    "ChargeClass": {"Correction"},
    "ChargeFrequency": {"One-Time", "Recurring", "Usage-Based"},
    "PricingCategory": {"Standard", "Dynamic", "Committed", "Other"},
    "CommitmentDiscountStatus": {"Used", "Unused"},
    "CommitmentDiscountCategory": {"Spend", "Usage"},
    "CapacityReservationStatus": {"Used", "Unused"},
}

# The 13 FOCUS-defined SkuPriceDetails property keys. Anything else MUST carry
# the x_ prefix. This is build spec section 8's MemorySize/MemoryGB trap.
SKU_PRICE_PROPERTIES = {
    "CoreCount", "DiskMaxIops", "DiskSpace", "DiskType", "GpuCount",
    "InstanceType", "InstanceSeries", "MemorySize", "NetworkMaxIops",
    "NetworkMaxThroughput", "OperatingSystem", "Redundancy", "StorageClass",
}

SERVICE_SUBCATEGORIES = {
    "AI and Machine Learning": [
        "AI Platforms",
        "Bots",
        "Generative AI",
        "Machine Learning",
        "Natural Language Processing",
        "Other (AI and Machine Learning)",
    ],
    "Analytics": [
        "Analytics Platforms",
        "Business Intelligence",
        "Data Processing",
        "Search",
        "Streaming Analytics",
        "Other (Analytics)",
    ],
    "Business Applications": [
        "Productivity and Collaboration",
        "Other (Business Applications)",
    ],
    "Compute": [
        "Containers",
        "End User Computing",
        "Quantum Compute",
        "Serverless Compute",
        "Virtual Machines",
        "Other (Compute)",
    ],
    "Databases": [
        "Caching",
        "Data Warehouses",
        "Ledger Databases",
        "NoSQL Databases",
        "Relational Databases",
        "Time Series Databases",
        "Other (Databases)",
    ],
    "Developer Tools": [
        "Developer Platforms",
        "Continuous Integration and Deployment",
        "Development Environments",
        "Source Code Management",
        "Quality Assurance",
        "Other (Developer Tools)",
    ],
    "Identity": [
        "Identity and Access Management",
        "Other (Identity)",
    ],
    "Integration": [
        "API Management",
        "Messaging",
        "Workflow Orchestration",
        "Other (Integration)",
    ],
    "Internet of Things": [
        "IoT Analytics",
        "IoT Platforms",
        "Other (Internet of Things)",
    ],
    "Management and Governance": [
        "Architecture",
        "Compliance",
        "Cost Management",
        "Data Governance",
        "Disaster Recovery",
        "Endpoint Management",
        "Observability",
        "Support",
        "Other (Management and Governance)",
    ],
    "Media": [
        "Content Creation",
        "Gaming",
        "Media Streaming",
        "Mixed Reality",
        "Other (Media)",
    ],
    "Migration": [
        "Data Migration",
        "Resource Migration",
        "Other (Migration)",
    ],
    "Mobile": [
        "Other (Mobile)",
    ],
    "Multicloud": [
        "Multicloud Integration",
        "Other (Multicloud)",
    ],
    "Networking": [
        "Application Networking",
        "Content Delivery",
        "Network Connectivity",
        "Network Infrastructure",
        "Network Routing",
        "Network Security",
        "Other (Networking)",
    ],
    "Other": [
        "Other (Other)",
    ],
    "Security": [
        "Secret Management",
        "Security Posture Management",
        "Threat Detection and Response",
        "Other (Security)",
    ],
    "Storage": [
        "Backup Storage",
        "Block Storage",
        "File Storage",
        "Object Storage",
        "Storage Platforms",
        "Other (Storage)",
    ],
    "Web": [
        "Application Platforms",
        "Other (Web)",
    ],
}

# The columns FOCUS v1.2 declares not-nullable, and the version that introduced
# each of the 14 columns absent before 1.2. Both mirror seed_data.py, which is
# deliberate: the harness must not import the generator's own beliefs about the
# spec, or it would only be testing that the generator agrees with itself.
MANDATORY_V12 = [
    "BilledCost", "BillingAccountId", "BillingAccountType", "BillingCurrency",
    "BillingPeriodEnd", "BillingPeriodStart", "ChargeCategory", "ChargeFrequency",
    "ChargePeriodEnd", "ChargePeriodStart", "ContractedCost", "EffectiveCost",
    "InvoiceIssuerName", "ListCost", "ProviderName", "PublisherName",
    "ServiceCategory", "ServiceName", "ServiceSubcategory",
]
POST_1_0_COLUMNS = {
    "BillingAccountType", "CapacityReservationId", "CapacityReservationStatus",
    "CommitmentDiscountQuantity", "CommitmentDiscountUnit", "InvoiceId",
    "PricingCurrency", "PricingCurrencyContractedUnitPrice",
    "PricingCurrencyEffectiveCost", "PricingCurrencyListUnitPrice",
    "ServiceSubcategory", "SkuMeter", "SkuPriceDetails", "SubAccountType",
}


# =============================================================================
# RESULT COLLECTION
# =============================================================================

class Results:
    """Collects findings so the summary is computed, never narrated (F14)."""

    def __init__(self):
        self.findings = []          # (check_id, severity, layer, message)

    def record(self, check_id, severity, layer, message):
        self.findings.append((check_id, severity, layer, message))

    def fails(self):
        return [f for f in self.findings if f[1] == "FAIL"]

    def warns(self):
        return [f for f in self.findings if f[1] == "WARN"]

    def caught_ids(self):
        return {f[0] for f in self.findings}


def load(folder):
    """Read a layer back from disk: its manifest, its rows, its arrow schema."""
    with open(os.path.join(folder, "manifest.json")) as f:
        manifest = json.load(f)
    path = os.path.join(folder, manifest["blobs"][0]["blobName"])
    con = duckdb.connect()
    con.execute(f"CREATE VIEW t AS SELECT * FROM read_parquet('{path}')")
    columns = [r[0] for r in con.execute("DESCRIBE t").fetchall()]
    rows = [dict(zip(columns, r)) for r in con.execute("SELECT * FROM t").fetchall()]
    return manifest, rows, columns, pq.ParquetFile(path).schema_arrow


# =============================================================================
# THE CHECKS
# =============================================================================
# Each check takes (rows, columns, arrow_schema, era, layer, results) and records
# findings. Every check is ERA-AWARE: a rule about a column introduced at 1.2
# cannot meaningfully be applied to a 1.0-era row (finding F17).

def check_schema_nullability(rows, columns, schema, era, layer, r):
    """F11: the file itself must enforce not-nullable, not just the viewer."""
    if era != "1.2":
        return
    for name in MANDATORY_V12:
        if name not in columns:
            r.record("SCHEMA_MISSING_MANDATORY", "FAIL", layer,
                     f"{name} absent from the file")
            continue
        if schema.field(name).nullable:
            r.record("SCHEMA_NULLABLE_MANDATORY", "FAIL", layer,
                     f"{name} is written as optional but the spec says "
                     f"MUST NOT be null")


def check_mandatory_not_null(rows, columns, schema, era, layer, r):
    for name in MANDATORY_V12:
        if name not in columns:
            continue                      # absent by era, handled above
        bad = sum(1 for row in rows if row[name] is None)
        if bad:
            r.record("NULL_IN_MANDATORY_COLUMN", "FAIL", layer,
                     f"{name} is null on {bad} row(s); spec: MUST NOT be null")


def check_allowed_values(rows, columns, schema, era, layer, r):
    """F13: validate VALUES, not just column names."""
    for name, allowed in ALLOWED.items():
        if name not in columns:
            continue
        seen = {row[name] for row in rows if row[name] is not None}
        for value in sorted(seen - allowed):
            count = sum(1 for row in rows if row[name] == value)
            check = ("INVALID_CHARGECLASS_VALUE" if name == "ChargeClass"
                     else "INVALID_ENUM_VALUE")
            r.record(check, "FAIL", layer,
                     f"{name} = {value!r} on {count} row(s); not an allowed value")


def check_service_pairing(rows, columns, schema, era, layer, r):
    """ServiceSubcategory MUST have one and only one parent ServiceCategory."""
    if "ServiceSubcategory" not in columns:
        return
    for row in rows:
        category, subcategory = row["ServiceCategory"], row["ServiceSubcategory"]
        if not subcategory:
            continue
        valid = SERVICE_SUBCATEGORIES.get(category, [])
        if subcategory not in valid:
            r.record("SERVICE_PAIRING_INVALID", "FAIL", layer,
                     f"{subcategory!r} is not a subcategory of {category!r}")


def check_empty_strings(rows, columns, schema, era, layer, r):
    """StringHandling: empty strings SHOULD NOT be used -> WARN, not FAIL.

    Finding F2 refined. Azure's real export does exactly this on 1,406 values.
    It departs from a recommendation; it does not break a MUST.
    """
    for name in columns:
        if not isinstance(next((row[name] for row in rows
                                if row[name] is not None), None), str):
            continue
        bad = sum(1 for row in rows
                  if isinstance(row[name], str) and row[name].strip() == "")
        if bad:
            r.record("EMPTY_STRING_PLACEHOLDER", "WARN", layer,
                     f"{name} holds an empty string on {bad} row(s); "
                     f"StringHandling: SHOULD NOT be used")


def check_cascades(rows, columns, schema, era, layer, r):
    """A satellite column MUST be null when its anchor is null."""
    cascades = {
        "ResourceId":            ["ResourceName", "ResourceType"],
        "CommitmentDiscountId":  ["CommitmentDiscountStatus",
                                  "CommitmentDiscountCategory",
                                  "CommitmentDiscountType"],
        "SubAccountId":          ["SubAccountName", "SubAccountType"],
        "CapacityReservationId": ["CapacityReservationStatus"],
        "SkuPriceId":            ["SkuPriceDetails"],
    }
    for anchor, satellites in cascades.items():
        if anchor not in columns:
            continue
        for satellite in satellites:
            if satellite not in columns:
                continue
            bad = sum(1 for row in rows
                      if row[anchor] is None and row[satellite] is not None)
            if bad:
                check = ("ORPHAN_COMMITMENT_STATUS"
                         if satellite == "CommitmentDiscountStatus"
                         else "ORPHAN_CAPACITY_RESERVATION_STATUS"
                         if satellite == "CapacityReservationStatus"
                         else "SATELLITE_WITHOUT_ANCHOR")
                r.record(check, "FAIL", layer,
                         f"{satellite} is populated on {bad} row(s) where "
                         f"{anchor} is null")


def check_conditional_nulls(rows, columns, schema, era, layer, r):
    """The 'MUST be null when...' rules that carry real analytical weight."""
    for row in rows:
        if row.get("ChargeCategory") == "Tax":
            for name in ("PricingCategory", "SkuId", "PricingQuantity",
                         "ListUnitPrice", "ContractedUnitPrice"):
                if name in columns and row[name] is not None:
                    r.record("TAX_WITH_PRICING_CATEGORY", "FAIL", layer,
                             f"{name} is populated on a Tax row; "
                             f"spec: MUST be null when ChargeCategory is 'Tax'")

        if (row.get("ChargeCategory") == "Purchase"
                and row.get("ChargeFrequency") == "Usage-Based"):
            r.record("PURCHASE_WITH_USAGE_BASED_FREQUENCY", "FAIL", layer,
                     "ChargeFrequency MUST NOT be 'Usage-Based' when "
                     "ChargeCategory is 'Purchase'")

        if ("ConsumedQuantity" in columns
                and row.get("ChargeCategory") not in ("Usage", None)
                and row["ConsumedQuantity"] is not None):
            r.record("CONSUMED_QUANTITY_ON_NON_USAGE", "FAIL", layer,
                     "ConsumedQuantity MUST be null when ChargeCategory "
                     "is not 'Usage'")


def check_non_negative_prices(rows, columns, schema, era, layer, r):
    for name in ("ListUnitPrice", "ContractedUnitPrice",
                 "PricingCurrencyListUnitPrice",
                 "PricingCurrencyContractedUnitPrice"):
        if name not in columns:
            continue
        bad = sum(1 for row in rows
                  if row[name] is not None and row[name] < 0)
        if bad:
            r.record("NEGATIVE_UNIT_PRICE", "FAIL", layer,
                     f"{name} is negative on {bad} row(s); "
                     f"spec: MUST be a non-negative decimal value")


def check_price_times_quantity(rows, columns, schema, era, layer, r):
    """PricingQuantity x unit price MUST match the corresponding cost.

    Exempt when ChargeClass is 'Correction' — the spec relaxes this, which is
    why corrections cannot be analysed by unit economics at all.
    """
    pairs = [("ListUnitPrice", "ListCost"),
             ("ContractedUnitPrice", "ContractedCost")]
    for price_col, cost_col in pairs:
        if price_col not in columns or cost_col not in columns:
            continue
        for row in rows:
            if row.get("ChargeClass") == "Correction":
                continue
            price, cost, qty = row[price_col], row[cost_col], row.get("PricingQuantity")
            if price is None or cost is None or qty is None:
                continue
            if abs(price * qty - cost) > Decimal("0.000001"):
                r.record("UNIT_PRICE_COST_MISMATCH", "FAIL", layer,
                         f"{price_col} {price} x PricingQuantity {qty} "
                         f"!= {cost_col} {cost}")


def check_sku_price_details(rows, columns, schema, era, layer, r):
    """F15 + build spec section 8: exact key spelling, or an x_ prefix."""
    if "SkuPriceDetails" not in columns:
        return
    for row in rows:
        blob = row["SkuPriceDetails"]
        if not blob:
            continue
        try:
            properties = json.loads(blob)
        except (ValueError, TypeError):
            r.record("SKU_PRICE_DETAILS_BAD_KEYS", "FAIL", layer,
                     "SkuPriceDetails is not valid JSON")
            continue
        for key in properties:
            if key in SKU_PRICE_PROPERTIES or key.startswith("x_"):
                continue
            near = [p for p in SKU_PRICE_PROPERTIES
                    if p.lower().startswith(key.lower()[:6])]
            hint = f" (did you mean {near[0]}?)" if near else ""
            r.record("SKU_PRICE_DETAILS_BAD_KEYS", "FAIL", layer,
                     f"SkuPriceDetails key {key!r} is neither FOCUS-defined nor "
                     f"x_-prefixed{hint}")


def check_currency_format(rows, columns, schema, era, layer, r):
    """CurrencyFormat: three-letter ISO 4217 for national currency.

    A virtual currency (credits, tokens) is exempt and follows StringHandling
    instead — so a longer value is only a violation when it looks like a
    mangled national currency code rather than a deliberate virtual one.
    """
    virtual = {"AI Credits"}
    for name in ("BillingCurrency", "PricingCurrency"):
        if name not in columns:
            continue
        for value in {row[name] for row in rows if row[name]}:
            if value in virtual:
                continue
            if len(value) != 3 or not value.isalpha() or not value.isupper():
                r.record("CURRENCY_NOT_ISO_4217", "FAIL", layer,
                         f"{name} = {value!r}; CurrencyFormat requires a "
                         f"three-letter ISO 4217 code for national currency")


def check_charge_period(rows, columns, schema, era, layer, r):
    for row in rows:
        start, end = row.get("ChargePeriodStart"), row.get("ChargePeriodEnd")
        if start is None or end is None:
            continue
        if end <= start:
            r.record("CHARGE_PERIOD_INVERTED", "FAIL", layer,
                     f"ChargePeriodEnd {end} does not follow "
                     f"ChargePeriodStart {start}")


def check_pricing_currency_populated(rows, columns, schema, era, layer, r):
    """Decision D7 guardrail (from finding F12).

    The spec contradicts itself: normative text says MUST NOT be null, the
    Content Constraints table says nulls are allowed. We satisfy both by
    populating every row. This asserts that outcome INDEPENDENTLY, so the
    guarantee does not rest on the generator's default having fired.
    """
    if era != "1.2":
        return                      # introduced at 1.2; absent before
    for name in ("PricingCurrency", "PricingCurrencyEffectiveCost"):
        if name not in columns:
            r.record("PRICING_CURRENCY_ABSENT", "FAIL", layer,
                     f"{name} missing from a v1.2 layer")
            continue
        bad = sum(1 for row in rows if row[name] is None)
        if bad:
            r.record("PRICING_CURRENCY_NULL", "FAIL", layer,
                     f"{name} is null on {bad} row(s); D7 requires it populated")


def check_era_columns(rows, columns, schema, era, layer, r):
    """A pre-1.2 layer MUST NOT carry columns that did not exist before 1.2."""
    if era != "pre-1.2":
        return
    present = POST_1_0_COLUMNS & set(columns)
    if present:
        r.record("ERA_COLUMN_ANACHRONISM", "FAIL", layer,
                 f"pre-1.2 layer carries post-1.0 columns: {sorted(present)}")


def check_provenance(rows, columns, schema, era, layer, r):
    """Decision D4: every synthetic row flagged, always."""
    for name in ("x_Synthetic", "x_SchemaEra", "x_FixtureId"):
        bad = sum(1 for row in rows if row.get(name) in (None, ""))
        if bad:
            r.record("PROVENANCE_MISSING", "FAIL", layer,
                     f"{name} is missing on {bad} row(s)")
    unflagged = sum(1 for row in rows if row.get("x_Synthetic") is not True)
    if unflagged:
        r.record("PROVENANCE_NOT_SYNTHETIC", "FAIL", layer,
                 f"{unflagged} row(s) not flagged x_Synthetic = true")


CHECKS = [
    check_schema_nullability, check_mandatory_not_null, check_allowed_values,
    check_service_pairing, check_empty_strings, check_cascades,
    check_conditional_nulls, check_non_negative_prices,
    check_price_times_quantity, check_sku_price_details,
    check_currency_format, check_charge_period,
    check_pricing_currency_populated, check_era_columns, check_provenance,
]


# =============================================================================
# RECONCILIATION — the identity from finding F14, with the F16 overlap term
# =============================================================================

def check_reconciliation(rows, layer, r):
    """EffectiveCost - BilledCost must be fully explained, per currency.

    Two causes, plus the overlap term flagged as a known limit in F14:
        third-party charges  - BilledCost MUST be 0, EffectiveCost is not
        commitment timing    - purchase billed in one period, amortised across
                               others; nets to zero once a term closes
    A row that is BOTH would have been double-counted by the original identity.
    That is now subtracted explicitly rather than assumed away.
    """
    for currency in sorted({row["BillingCurrency"] for row in rows
                            if row.get("BillingCurrency")}):
        book = [row for row in rows if row["BillingCurrency"] == currency]
        billed = sum(row["BilledCost"] for row in book
                     if row["BilledCost"] is not None)
        effective = sum(row["EffectiveCost"] for row in book
                        if row["EffectiveCost"] is not None)

        third_party = sum(row["EffectiveCost"] for row in book
                          if row.get("PublisherName") != row.get("ProviderName")
                          and row["EffectiveCost"] is not None)
        amortised = sum(row["EffectiveCost"] for row in book
                        if row.get("ChargeCategory") == "Usage"
                        and row.get("CommitmentDiscountId") is not None
                        and row["EffectiveCost"] is not None)
        purchased = sum(row["BilledCost"] for row in book
                        if row.get("ChargeCategory") == "Purchase"
                        and row["BilledCost"] is not None)
        # The overlap: rows counted in BOTH terms above.
        overlap = sum(row["EffectiveCost"] for row in book
                      if row.get("PublisherName") != row.get("ProviderName")
                      and row.get("ChargeCategory") == "Usage"
                      and row.get("CommitmentDiscountId") is not None
                      and row["EffectiveCost"] is not None)

        explained = third_party + (amortised - purchased) - overlap
        gap = effective - billed
        if gap != explained:
            r.record("RECONCILIATION_UNEXPLAINED", "FAIL", layer,
                     f"{currency}: EffectiveCost - BilledCost = {gap:.2f} but "
                     f"only {explained:.2f} is explained "
                     f"(unexplained {gap - explained:.2f})")


# =============================================================================
# RUN
# =============================================================================

def run_layer(label, folder, results, reconcile=True, skip=()):
    manifest, rows, columns, schema = load(folder)
    era = manifest["generator"].get("schemaEra") or (
        "pre-1.2" if "pre-1.2" in label else "1.2")
    for check in CHECKS:
        if check.__name__ in skip:
            continue
        check(rows, columns, schema, era, label, results)
    if reconcile:
        check_reconciliation(rows, label, results)
    return manifest, rows


if __name__ == "__main__":
    print("=" * 70)
    print("self_test.py — conformance of the generated data")
    print("=" * 70)

    # --- 1. the clean layers: every check must stay silent ------------------
    clean = Results()
    print("\nCLEAN LAYERS — no MUST may be broken")
    print("-" * 70)
    total_rows = 0
    for label, folder in CLEAN_LAYERS:
        if not os.path.isdir(folder):
            print(f"  {label:<10} FOLDER MISSING — run seed_data.py first")
            continue
        manifest, rows = run_layer(label, folder, clean)
        total_rows += len(rows)
        print(f"  {label:<10} {len(rows):>4} rows, "
              f"{manifest['generator']['columnCount']} columns  checked")

    print(f"\n  {len(CHECKS)} checks over {total_rows} rows.")
    if clean.fails():
        print(f"\n  {len(clean.fails())} MUST violation(s):")
        for check_id, _, layer, message in clean.fails():
            print(f"    FAIL [{layer}] {check_id}: {message}")
    else:
        print("  MUST violations : 0   PASS")

    if clean.warns():
        print(f"\n  {len(clean.warns())} SHOULD departure(s) — conformant, not "
              f"recommended:")
        for check_id, _, layer, message in clean.warns():
            print(f"    WARN [{layer}] {check_id}: {message}")
    else:
        print("  SHOULD departures: 0")

    # --- 2. the negative layer: every planted violation must be CAUGHT ------
    print("\n\nNEGATIVE LAYER — every planted violation must be caught")
    print("-" * 70)
    negative = Results()
    if os.path.isdir(NEGATIVE_LAYER):
        # The negative file is deliberately permissive (finding F18): to hold a
        # violation of "MUST NOT be null" it has to allow nulls. Its schema
        # nullability and provenance are therefore not meaningful to check here,
        # and running those would bury the real findings in expected noise.
        manifest, rows = run_layer("negative", NEGATIVE_LAYER, negative,
                                   reconcile=False,
                                   skip=("check_schema_nullability",
                                         "check_provenance"))
        planted = sorted({row["x_ExpectedViolation"] for row in rows})
        caught = negative.caught_ids()

        print(f"\n  {len(planted)} violations planted, "
              f"{len(negative.findings)} findings raised.")
        print("  (More findings than violations is correct: one bad row can")
        print("   breach the same rule in several columns at once.)\n")
        missed = []
        for label in planted:
            hit = label in caught
            print(f"    {'caught ' if hit else 'MISSED '} {label}")
            if not hit:
                missed.append(label)

        print(f"\n  Detection: {len(planted) - len(missed)}/{len(planted)}   "
              f"{'PASS' if not missed else 'FAIL'}")
        if missed:
            print("  A planted violation nothing detects is a GAP IN THE HARNESS,")
            print("  not a problem with the fixture. Add the missing check.")
    else:
        print("  data/negative/ not found — run seed_data.py first")

    # --- 3. verdict ---------------------------------------------------------
    print("\n" + "=" * 70)
    ok = not clean.fails()
    print(f"  Clean layers conformant : {'YES' if ok else 'NO'}")
    print(f"  SHOULD departures       : {len(clean.warns())}")
    if os.path.isdir(NEGATIVE_LAYER):
        print(f"  Planted violations caught: {len(planted) - len(missed)}"
              f"/{len(planted)}")
    print("\n  A harness that has only seen valid data has never been proven to")
    print("  detect anything. This one has been shown 14 broken rows and found")
    print("  all 14 — which is what makes the zero above mean something.")
    print("=" * 70)
    sys.exit(0 if ok else 1)
