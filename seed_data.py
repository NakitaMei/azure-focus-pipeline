"""
seed_data.py — Portfolio Project 1, Stage 3 (Layer 3: synthetic enrichment)

The mirror image of loader.py:
    loader.py    READS data Azure already produced.
    seed_data.py WRITES data that never existed, because a $20 sandbox will never
                 buy a reservation, issue a correction, charge tax or sell a token.

Every row this script produces is flagged x_Synthetic = true. Real and engineered
data never blur — see the Stage 3 working notes, decision D4.

CHUNK 0 — the scaffold
    Paths, sanitised identity constants (D1), grounded constants, the verified
    FOCUS v1.2 column set (D2), the typed pyarrow schema, new_row() with its
    exact-spelling typo guard, and the writer + metadata sidecar.

CHUNK 1 — the reservation lifecycle fixture  (section 6b)
    The double-count trap, made demonstrable: one purchase row, 31 committed-usage
    rows and 21 unused-commitment rows, with term-closure arithmetic that ties to
    the cent. 53 rows.

CHUNK 2 — the charge family fixture  (section 6c)
    Tax, Credit, Adjustment and both faces of ChargeClass. The rows that belong to
    no resource and break naive allocation. 5 rows.

CHUNK 3 — the pricing family fixture  (section 6d)
    Whole-block pricing, virtual currency, a second billing currency, spot pricing
    and a marketplace charge. Needs columns that do not exist at 1.0r2. 7 rows.

CHUNK 4 — account, resource, SKU, location and timeframe  (section 6e)
    SkuPriceDetails across two SKUs, the nameless resource, a mid-period rename,
    capacity reservation vs commitment discount, the upfront purchase, the month
    boundary and invoicing latency. 11 rows.

CHUNK 5 — the pre-1.2 legacy era  (section 6f)
    A 2024-era 1.0 export in its OWN file with its OWN 51-column schema. The only
    data on which the build-spec §7 coalesce() fallbacks actually fire. 10 rows.

CHUNK 6 — negative fixtures  (section 6g)
    14 deliberately broken rows, one rule each, in data/negative/ and NEVER
    merged. Proof that the Stage 4 checks can actually fail. 14 rows.

CHUNK 7 — the writer
    One folder per layer, each holding a Parquet and an AZURE-SHAPED
    manifest.json. loader.py runs on all three unchanged. sha256 per file,
    proving the generator is deterministic.

Run:  python3 seed_data.py          (or  python3 src/seed_data.py)

No pandas, no numpy — pyarrow only. pyarrow lets us declare column types exactly,
which is the whole point: the real export types costs as DECIMAL(38,18) and
timestamps as naive TIMESTAMP, and anything else fails to merge with it.
Deterministic by design: no randomness anywhere, so re-running produces the same
bytes. That is what "fully reproducible" in the build spec actually requires.
"""

import hashlib
import json
import os
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP

import pyarrow as pa               # builds typed tables in memory
import pyarrow.parquet as pq       # writes those tables out as Parquet


# =============================================================================
# 1. PATHS — computed from this file, so the script runs from any directory
# =============================================================================
# Stage 2 lesson (working notes, "current working directory"): a bare filename is
# relative to wherever the terminal happens to be standing. __file__ is the path
# of THIS script, so deriving everything from it removes the problem entirely.

HERE = os.path.dirname(os.path.abspath(__file__))
# If the script lives in src/, the project root is one level up. If it sits beside
# loader.py at the project root, HERE already IS the project root.
PROJECT_ROOT = os.path.dirname(HERE) if os.path.basename(HERE) == "src" else HERE

# Each layer gets its OWN FOLDER containing a Parquet and a manifest.json —
# the same shape Azure delivers an export run in. That is not decoration: it
# means loader.py can be pointed at any of these folders and run UNCHANGED,
# because it finds the manifest keys and the *.snappy.parquet glob it expects.
# One loader, three sources.
DATA_DIR = os.path.join(PROJECT_ROOT, "data")

LAYERS = {
    "v1.2": {
        "folder":   os.path.join(DATA_DIR, "synthetic", "v1.2"),
        "parquet":  "focus_synthetic_v1.2.snappy.parquet",
        "export":   "synthetic-layer3-v1.2",
        "version":  "1.2",
        "runId":    "s3-v12-0000-0000-000000000001",
        "layer":    "Layer 3 - synthetic enrichment",
    },
    "pre-1.2": {
        "folder":   os.path.join(DATA_DIR, "synthetic", "pre-1.2"),
        "parquet":  "focus_synthetic_pre1.2.snappy.parquet",
        "export":   "synthetic-layer2-legacy",
        "version":  "1.0",
        "runId":    "s3-l2-0000-0000-000000000002",
        "layer":    "Layer 2 - legacy era",
    },
    "negative": {
        "folder":   os.path.join(DATA_DIR, "negative"),
        "parquet":  "focus_negative_fixtures.snappy.parquet",
        "export":   "negative-fixtures",
        "version":  "1.2",
        "runId":    "s3-neg-0000-0000-00000000003",
        "layer":    "Negative fixtures - harness testing only",
    },
}


# =============================================================================
# 2. SANITISED IDENTITY — decision D1
# =============================================================================
# Finding F6: the real export carries personal data. The account holder's name
# appears in FIVE columns (BillingAccountName, x_BillingAccountName,
# x_BillingProfileName, x_CustomerName, x_InvoiceSectionName) and real GUIDs sit
# in six more (BillingAccountId, x_BillingAccountId, x_BillingProfileId,
# x_InvoiceSectionId, x_SkuOrderId, SubAccountId — and inside every ResourceId).
#
# These stand-ins are defined HERE, in chunk 0, for one reason: the synthetic rows
# and the sanitised real rows must use the SAME identifiers, or joins between the
# two halves break. Same input -> same output, every run.

SUBSCRIPTION_ID     = "00000000-0000-0000-0000-000000000001"
BILLING_ACCOUNT_GUID = "00000000-0000-0000-0000-000000000002"

BILLING_ACCOUNT_ID   = f"/providers/Microsoft.Billing/billingAccounts/{BILLING_ACCOUNT_GUID}"
BILLING_ACCOUNT_NAME = "Portfolio Sandbox Account"
BILLING_ACCOUNT_TYPE = "Billing Profile"      # real value, not identifying

SUB_ACCOUNT_ID       = f"/subscriptions/{SUBSCRIPTION_ID}"
SUB_ACCOUNT_NAME     = "Azure subscription 1"  # real value, not identifying
SUB_ACCOUNT_TYPE     = "Subscription"

RESOURCE_GROUP       = "rg-p1-sandbox"


# =============================================================================
# 3. GROUNDED CONSTANTS — lifted from the real 31 July 2026 export (118 rows)
# =============================================================================
# The synthetic layer is grounded in what the real data actually says, so the two
# halves sit together plausibly. Every value below was read off the export, not
# invented. Source: Stage 2 findings F1 and F5, re-verified 2 August 2026.

CURRENCY        = "USD"          # single currency in the real data
REGION_ID       = "southafricanorth"
REGION_NAME     = "South Africa North"

PROVIDER_NAME       = "Microsoft"
PUBLISHER_NAME      = "Microsoft"
INVOICE_ISSUER_NAME = "Microsoft"

# The four real services, as (ServiceName, ServiceCategory).
# ServiceCategory values are constrained by the spec — these four are allowed values.
SERVICES = {
    "vm":      ("Virtual Machines",  "Compute"),
    "storage": ("Storage Accounts",  "Storage"),
    "network": ("Virtual Network",   "Networking"),
    "web":     ("Azure App Service", "Web"),
}

# The real billing period: 1 July -> 1 August 2026 (half-open; the end is exclusive).
BILLING_PERIOD_START = datetime(2026, 7,  1)
BILLING_PERIOD_END   = datetime(2026, 8,  1)

# Real charge rows only cover 22-31 July, because that is when the resources were
# created. Synthetic fixtures fill the rest of the picture.
REAL_DATA_FIRST_DAY = datetime(2026, 7, 22)

# Finding F7: Azure block-prices storage transactions in units of 10,000 and emits
# FRACTIONAL blocks (191 consumed -> PricingQuantity 0.0191). The build spec assumes
# WHOLE blocks. Both are legitimate; the synthetic fixture supplies the whole-block
# contrast so the Stage 5 waste query must handle each.
BLOCK_SIZE_10K = 10_000

# Provenance defaults (decisions D2 and D4)
SCHEMA_ERA_DEFAULT = "1.2"       # synthetic rows are generated at v1.2
SCHEMA_ERA_LEGACY  = "pre-1.2"   # the chunk 5 legacy-era fixture set
SCHEMA_ERA_REAL    = "1.0r2"     # what the real Azure export is; set by the loader


# =============================================================================
# 4. THE FOCUS v1.2 COLUMN SET — verified, not remembered
# =============================================================================
# Every column below was confirmed on 2 August 2026 by fetching its definition file
# at spec tag v1.2 using the build spec's §9 raw-file method:
#
#   https://raw.githubusercontent.com/FinOps-Open-Cost-and-Usage-Spec/FOCUS_Spec
#          /v1.2/specification/columns/<column>.md
#
# "Data type" and "Allows nulls" below are the spec's own declared values, read
# from those files. Nullable=False means the spec says this column MUST NOT be null.
#
# Filename note worth remembering: the repo names files by DISPLAY NAME while the
# Column ID is what you emit. ProviderName lives in provider.md, PublisherName in
# publisher.md, InvoiceIssuerName in invoiceissuer.md. Emit the Column ID.
#
# Format: (Column ID, spec data type, nullable per spec)

COLUMNS_V12 = [
    ("AvailabilityZone",                   "String",    True),
    ("BilledCost",                         "Decimal",   False),
    ("BillingAccountId",                   "String",    False),
    ("BillingAccountName",                 "String",    True),
    ("BillingAccountType",                 "String",    False),
    ("BillingCurrency",                    "String",    False),
    ("BillingPeriodEnd",                   "Date/Time", False),
    ("BillingPeriodStart",                 "Date/Time", False),
    ("CapacityReservationId",              "String",    True),
    ("CapacityReservationStatus",          "String",    True),
    ("ChargeCategory",                     "String",    False),
    ("ChargeClass",                        "String",    True),
    ("ChargeDescription",                  "String",    True),
    ("ChargeFrequency",                    "String",    False),
    ("ChargePeriodEnd",                    "Date/Time", False),
    ("ChargePeriodStart",                  "Date/Time", False),
    ("CommitmentDiscountCategory",         "String",    True),
    ("CommitmentDiscountId",               "String",    True),
    ("CommitmentDiscountName",             "String",    True),
    ("CommitmentDiscountQuantity",         "Decimal",   True),
    ("CommitmentDiscountStatus",           "String",    True),
    ("CommitmentDiscountType",             "String",    True),
    ("CommitmentDiscountUnit",             "String",    True),
    ("ConsumedQuantity",                   "Decimal",   True),
    ("ConsumedUnit",                       "String",    True),
    ("ContractedCost",                     "Decimal",   False),
    ("ContractedUnitPrice",                "Decimal",   True),
    ("EffectiveCost",                      "Decimal",   False),
    ("InvoiceId",                          "String",    True),
    ("InvoiceIssuerName",                  "String",    False),
    ("ListCost",                           "Decimal",   False),
    ("ListUnitPrice",                      "Decimal",   True),
    ("PricingCategory",                    "String",    True),
    ("PricingCurrency",                    "String",    True),
    ("PricingCurrencyContractedUnitPrice", "Decimal",   True),
    ("PricingCurrencyEffectiveCost",       "Decimal",   True),
    ("PricingCurrencyListUnitPrice",       "Decimal",   True),
    ("PricingQuantity",                    "Decimal",   True),
    ("PricingUnit",                        "String",    True),
    ("ProviderName",                       "String",    False),
    ("PublisherName",                      "String",    False),
    ("RegionId",                           "String",    True),
    ("RegionName",                         "String",    True),
    ("ResourceId",                         "String",    True),
    ("ResourceName",                       "String",    True),
    ("ResourceType",                       "String",    True),
    ("ServiceCategory",                    "String",    False),
    ("ServiceName",                        "String",    False),
    ("ServiceSubcategory",                 "String",    False),   # <- not nullable: the empty-string trap
    ("SkuId",                              "String",    True),
    ("SkuMeter",                           "String",    True),
    ("SkuPriceDetails",                    "JSON",      True),
    ("SkuPriceId",                         "String",    True),
    ("SubAccountId",                       "String",    True),
    ("SubAccountName",                     "String",    True),
    ("SubAccountType",                     "String",    True),
    ("Tags",                               "JSON",      True),
]

# Azure x_ columns carried into the synthetic rows so that showback and the
# block-pricing query behave identically across the real and synthetic halves.
# Three, not all 52 — decision D2.
COLUMNS_X_CARRIED = [
    ("x_ResourceGroupName",   "String",  True),
    ("x_PricingBlockSize",    "Decimal", True),
    ("x_SkuMeterName",        "String",  True),
    ("x_BillingExchangeRate", "Decimal", True),   # real Azure column (chunk 3)
]

# x_ columns invented for fixtures that have no FOCUS home yet. The x_ prefix is
# the specification's own extension mechanism, so these remain conformant.
# x_TokenCount / x_TokenModel anticipate FOCUS v1.5's AI work (build spec A4).
#
# x_CommitmentEligible anticipates v1.4's eligibility semantics (Amendment A4)
# and exists so Stage 6's coverage analysis measures coverage of COVERABLE
# spend rather than of all spend. Three-valued, and the null matters:
#   True   a Usage row a commitment discount could cover under this dataset's
#          documented rule: compute (Virtual Machines service) that is not
#          spot. Committed usage is trivially True - it IS covered.
#   False  a Usage row no commitment could cover here: storage, network,
#          tokens, marketplace, App Service, and spot (Dynamic) compute.
#          A deliberate simplification - real Azure sells reservations for
#          some of these - and the simplification is the disclosure.
#   None   the concept does not apply: non-usage rows (Purchase, Tax, Credit,
#          Adjustment) and Unused-commitment rows, which carry no resource
#          demand and belong to utilisation, not coverage. Also every row of
#          an era that predates the flag (pre-1.2 legacy, real 1.0r2) - the
#          coverage query must say so, not silently treat null as False.
COLUMNS_X_FIXTURE = [
    ("x_TokenCount",          "Decimal", True),
    ("x_TokenModel",          "String",  True),
    ("x_CommitmentEligible",  "Boolean", True),
]

# Provenance columns — decision D4. x_FixtureId is ours: it records which fixture
# function produced each row, which makes the chunk 8 self-test readable.
COLUMNS_PROVENANCE = [
    ("x_Synthetic",  "Boolean", False),
    ("x_SchemaEra",  "String",  False),
    ("x_FixtureId",  "String",  False),
]

ALL_COLUMN_SPECS = (COLUMNS_V12 + COLUMNS_X_CARRIED
                    + COLUMNS_X_FIXTURE + COLUMNS_PROVENANCE)
ALL_COLUMNS      = [name for name, _, _ in ALL_COLUMN_SPECS]
NOT_NULLABLE     = [name for name, _, nullable in ALL_COLUMN_SPECS if not nullable]


# =============================================================================
# 5. THE TYPED SCHEMA — spec data type -> pyarrow type
# =============================================================================
# Reading a file lets you inherit its types. Writing one means choosing them, and
# the choice has to match the real export or the two halves will not merge:
#   Decimal   -> decimal128(38, 18)   exactly as Azure ships costs and quantities
#   Date/Time -> timestamp('us')      NAIVE, with UTC semantics, as Azure ships them
#   String    -> string
#   JSON      -> string               providers emit tags as a serialised JSON STRING
#   Boolean   -> bool_
#
# On the naive timestamp: FOCUS requires ISO 8601 with a terminal Z. In Parquet the
# "Z" lives in the convention rather than in the bytes — Azure's own export stores
# naive timestamps understood as UTC, and matching that is what keeps the union clean.
# Anything written to CSV (the Layer C files, chunk 10) DOES carry the literal Z.

TYPE_MAP = {
    "Decimal":   pa.decimal128(38, 18),
    "Date/Time": pa.timestamp("us"),
    "String":    pa.string(),
    "JSON":      pa.string(),
    "Boolean":   pa.bool_(),
}

SCHEMA = pa.schema([
    pa.field(name, TYPE_MAP[spec_type], nullable=nullable)
    for name, spec_type, nullable in ALL_COLUMN_SPECS
])



# --- Which FOCUS version introduced each column -----------------------------
# Verified 13 August 2026 by reading the "Introduced (version)" section of every
# column file at spec tag v1.2. This map is not documentation — it is EXECUTABLE:
# the pre-1.2 legacy schema below is derived from it, so the availability matrix
# and the data can never drift apart.
#
# The shape of the FOCUS version gap, in one table:
#     0.5          20 columns
#     1.0-preview  15 columns
#     1.0           8 columns   <- Azure's real export stops here (1.0r2)
#     1.1           7 columns
#     1.2           7 columns
# 14 of 57 columns — a quarter of the specification — are structurally
# unavailable to a provider still emitting 1.0.

INTRODUCED = {
    "AvailabilityZone": "0.5", "BilledCost": "0.5", "BillingAccountId": "0.5",
    "BillingAccountName": "0.5", "BillingCurrency": "0.5", "BillingPeriodEnd": "0.5",
    "BillingPeriodStart": "0.5", "ChargeCategory": "0.5", "ChargePeriodEnd": "0.5",
    "ChargePeriodStart": "0.5", "EffectiveCost": "0.5", "InvoiceIssuerName": "0.5",
    "ProviderName": "0.5", "PublisherName": "0.5", "ResourceId": "0.5",
    "ResourceName": "0.5", "ServiceCategory": "0.5", "ServiceName": "0.5",
    "SubAccountId": "0.5", "SubAccountName": "0.5",

    "ChargeDescription": "1.0-preview", "ChargeFrequency": "1.0-preview",
    "CommitmentDiscountCategory": "1.0-preview", "CommitmentDiscountId": "1.0-preview",
    "CommitmentDiscountName": "1.0-preview", "CommitmentDiscountType": "1.0-preview",
    "ListCost": "1.0-preview", "ListUnitPrice": "1.0-preview",
    "PricingCategory": "1.0-preview", "PricingQuantity": "1.0-preview",
    "PricingUnit": "1.0-preview", "ResourceType": "1.0-preview", "SkuId": "1.0-preview",
    "SkuPriceId": "1.0-preview", "Tags": "1.0-preview",

    "ChargeClass": "1.0", "CommitmentDiscountStatus": "1.0", "ConsumedQuantity": "1.0",
    "ConsumedUnit": "1.0", "ContractedCost": "1.0", "ContractedUnitPrice": "1.0",
    "RegionId": "1.0", "RegionName": "1.0",

    "CapacityReservationId": "1.1", "CapacityReservationStatus": "1.1",
    "CommitmentDiscountQuantity": "1.1", "CommitmentDiscountUnit": "1.1",
    "ServiceSubcategory": "1.1", "SkuMeter": "1.1", "SkuPriceDetails": "1.1",

    "BillingAccountType": "1.2", "InvoiceId": "1.2", "PricingCurrency": "1.2",
    "PricingCurrencyContractedUnitPrice": "1.2", "PricingCurrencyEffectiveCost": "1.2",
    "PricingCurrencyListUnitPrice": "1.2", "SubAccountType": "1.2",
}

# Everything available at 1.0 and earlier — i.e. what a pre-1.2 provider could emit.
PRE12_VERSIONS = {"0.5", "1.0-preview", "1.0"}

COLUMNS_PRE12_ROOT = [(name, spec_type, nullable)
                      for name, spec_type, nullable in COLUMNS_V12
                      if INTRODUCED[name] in PRE12_VERSIONS]

# The x_ columns a 1.0-era Azure export uses to carry what the root columns cannot.
# These are EXACTLY the build-spec §7 fallback sources, and that is not a
# coincidence: the loader's fallback map exists because these four root columns
# were introduced after the version Azure emits.
#     SkuMeter        (1.1) <- x_SkuMeterName
#     SkuPriceDetails (1.1) <- x_SkuDetails
#     PricingCurrency (1.2) <- x_PricingCurrency
#     InvoiceId       (1.2) <- x_InvoiceId
COLUMNS_PRE12_X = [
    ("x_SkuMeterName",      "String", True),
    ("x_SkuDetails",        "JSON",   True),
    ("x_PricingCurrency",   "String", True),
    ("x_InvoiceId",         "String", True),
    ("x_ResourceGroupName", "String", True),
]

PRE12_COLUMN_SPECS = COLUMNS_PRE12_ROOT + COLUMNS_PRE12_X + COLUMNS_PROVENANCE
PRE12_COLUMNS      = [name for name, _, _ in PRE12_COLUMN_SPECS]

SCHEMA_PRE12 = pa.schema([
    pa.field(name, TYPE_MAP[spec_type], nullable=nullable)
    for name, spec_type, nullable in PRE12_COLUMN_SPECS
])



# --- The negative-test schema -----------------------------------------------
# A THIRD file, holding rows that are deliberately WRONG. It exists so the Stage 4
# harness can be tested: a harness that passes everything it is given proves
# nothing. These rows must each fail, and each carries a note saying how.
#
# Every column here is nullable, because several violations ARE a missing value
# in a column the spec says must be present. The negative file cannot be strict —
# that is the point of keeping it separate from the two clean files.
COLUMNS_NEGATIVE_ANNOTATION = [
    ("x_ExpectedViolation", "String", True),   # what a harness should flag
    ("x_ViolatedRule",      "String", True),   # which spec file states the rule
]

NEGATIVE_COLUMN_SPECS = ([(name, spec_type, True)              # <- all nullable
                          for name, spec_type, _ in ALL_COLUMN_SPECS]
                         + COLUMNS_NEGATIVE_ANNOTATION)
NEGATIVE_COLUMNS = [name for name, _, _ in NEGATIVE_COLUMN_SPECS]

SCHEMA_NEGATIVE = pa.schema([
    pa.field(name, TYPE_MAP[spec_type], nullable=True)
    for name, spec_type, _ in NEGATIVE_COLUMN_SPECS
])

SCHEMA_ERA_NEGATIVE = "negative"



# --- The negative-fixture schema (chunk 6) ----------------------------------
# Deliberately PERMISSIVE: every column nullable. This is not sloppiness — to
# write a row that violates "MUST NOT be null", the file format has to allow the
# null in the first place. A strict schema physically cannot hold a test case for
# its own strictness. See finding F18.
#
# Two extra columns label what each row is FOR, so the Stage 4 harness can assert
# "check X must flag row Y" rather than merely "something failed somewhere".
COLUMNS_NEGATIVE_LABELS = [
    ("x_ExpectedViolation", "String", True),
    ("x_ViolationDetail",   "String", True),
]

NEGATIVE_COLUMN_SPECS = ([(name, spec_type, True)                # force nullable
                          for name, spec_type, _ in ALL_COLUMN_SPECS]
                         + COLUMNS_NEGATIVE_LABELS)
NEGATIVE_COLUMNS = [name for name, _, _ in NEGATIVE_COLUMN_SPECS]

SCHEMA_NEGATIVE = pa.schema([
    pa.field(name, TYPE_MAP[spec_type], nullable=nullable)
    for name, spec_type, nullable in NEGATIVE_COLUMN_SPECS
])


# =============================================================================
# 6. HELPERS
# =============================================================================

_EIGHTEEN_PLACES = Decimal(1).scaleb(-18)     # 0.000000000000000001


def money(value):
    """Turn a number into a Decimal with exactly 18 decimal places.

    Money must never be a float. 0.1 + 0.2 is 0.30000000000000004 in float
    arithmetic, and a reconciliation that has to tie to the cent cannot survive
    that. Decimal is exact. The scale of 18 matches Azure's DECIMAL(38,18).
    """
    if value is None:
        return None
    return Decimal(str(value)).quantize(_EIGHTEEN_PLACES, rounding=ROUND_HALF_UP)


def json_string(obj):
    """Serialise a dict to a JSON string, the way providers actually emit Tags.

    sort_keys=True is deliberate. Finding F8: the real export emits the SAME four
    tags in TWO different key orders, so GROUP BY Tags splits one resource across
    two buckets. Sorting keys makes the synthetic half self-consistent; the real
    half keeps its inconsistency, because that inconsistency is the finding.
    """
    if obj is None:
        return None
    return json.dumps(obj, sort_keys=True, separators=(",", ":"))


def _did_you_mean(name):
    """Suggest the closest real column name for a misspelling."""
    lowered = name.lower()
    near = [c for c in ALL_COLUMNS if c.lower() == lowered]           # case only
    if not near:
        near = [c for c in ALL_COLUMNS if lowered in c.lower() or c.lower() in lowered]
    return near[:4]


def new_row(fixture_id, era=SCHEMA_ERA_DEFAULT, **values):
    """Build one complete FOCUS row.

    Give it the handful of fields the fixture cares about; every other column comes
    back as a true None (Python None -> Parquet null, never "" and never "N/A" —
    build spec §4.2 cross-cutting).

    THE TYPO GUARD is the important part. Misspell a column name and this raises
    immediately, naming the near matches, instead of quietly inventing a column
    that nothing will ever read. This is build spec §8's exact-spelling rule
    enforced at write time — the MemorySize/MemoryGB trap, caught here rather than
    by a query that returns nothing, forever, silently.
    """
    columns = {SCHEMA_ERA_LEGACY: PRE12_COLUMNS,
               SCHEMA_ERA_NEGATIVE: NEGATIVE_COLUMNS}.get(era, ALL_COLUMNS)
    unknown = [k for k in values if k not in columns]
    if unknown:
        hints = "; ".join(f"{u} -> did you mean {_did_you_mean(u)}?" for u in unknown)
        raise KeyError(f"Unknown column name(s) in fixture '{fixture_id}' "
                       f"at era {era}: {hints}")

    row = {column: None for column in columns}
    row.update(values)

    # --- conformance defaults (finding F12) --------------------------------
    # PricingCurrency and PricingCurrencyEffectiveCost both carry the normative
    # rule "MUST NOT be null" while their own Content Constraints tables say
    # "Allows nulls: True" — an internal contradiction in FOCUS v1.2. Azure
    # settles it in practice: it populates x_PricingCurrency on every real row,
    # equal to BillingCurrency. We follow the normative reading and populate on
    # every row, so the dataset is conformant under BOTH readings of the spec.
    #
    # These defaults only fire when a fixture has not set the value itself, so
    # the EUR fixture (where pricing and billing currencies genuinely differ)
    # passes through untouched.
    if era == SCHEMA_ERA_NEGATIVE:
        # No defaults, no corrections. The whole value of this file is that
        # every value is exactly what the fixture wrote — including the wrong
        # ones. Filling anything in here would repair the very defect under test.
        row["x_Synthetic"] = True
        row["x_SchemaEra"] = values.get("x_SchemaEra") or SCHEMA_ERA_NEGATIVE
        row["x_FixtureId"] = fixture_id
        return row

    if era == SCHEMA_ERA_LEGACY:
        # The pricing-currency columns were introduced at 1.2 and simply do not
        # exist here, so the F12 defaults must not fire. Conformance is
        # era-conditional; see finding F17.
        row["x_Synthetic"] = True
        row["x_SchemaEra"] = SCHEMA_ERA_LEGACY
        row["x_FixtureId"] = fixture_id
        return row

    if row["PricingCurrency"] is None:
        row["PricingCurrency"] = row["BillingCurrency"]
    if row["PricingCurrencyEffectiveCost"] is None and row["EffectiveCost"] is not None:
        row["PricingCurrencyEffectiveCost"] = row["EffectiveCost"]
    if row["PricingCurrencyListUnitPrice"] is None and row["ListUnitPrice"] is not None:
        row["PricingCurrencyListUnitPrice"] = row["ListUnitPrice"]
    if (row["PricingCurrencyContractedUnitPrice"] is None
            and row["ContractedUnitPrice"] is not None):
        row["PricingCurrencyContractedUnitPrice"] = row["ContractedUnitPrice"]

    # Provenance is applied here so no fixture can forget it (decision D4).
    row["x_Synthetic"] = True
    row["x_SchemaEra"] = values.get("x_SchemaEra") or era
    row["x_FixtureId"] = fixture_id
    return row


def write_parquet(rows, path, schema=SCHEMA, column_names=None):
    """Write rows to Parquet using a DECLARED schema (never an inferred one)."""
    column_names = column_names or ALL_COLUMNS
    columns = {c: [row[c] for row in rows] for c in column_names}
    table = pa.Table.from_pydict(columns, schema=schema)
    pq.write_table(table, path, compression="snappy")
    return table


def content_checksum(rows, column_names):
    """A checksum of the DATA, independent of how Parquet encoded it.

    Finding F20: the file's own sha256 changes between pyarrow versions, because
    Parquet has latitude in how it encodes and compresses. Same rows in, different
    bytes out. So a byte hash cannot support the reproducibility claim across
    environments — it only proves determinism within one.

    This hashes the values themselves, in a fixed column order, so it is stable
    anywhere the generator produces the same data. That is the number a reviewer
    should compare.
    """
    digest = hashlib.sha256()
    for row in rows:
        for name in column_names:              # fixed order, not dict order
            digest.update(f"{name}={row[name]!r}\x1f".encode())
        digest.update(b"\x1e")
    return digest.hexdigest()


def write_manifest(layer_key, rows, parquet_path, extra=None):
    """Write an Azure-shaped manifest.json beside the Parquet.

    The top-level keys deliberately mirror Azure's own export manifest —
    manifestVersion, byteCount, blobCount, dataRowCount, exportConfig,
    deliveryConfig, runInfo, blobs — so that loader.py, written in Stage 2
    against a real Azure manifest, reads these without a single change.

    Everything under "generator" is our own addition. Azure ignores keys it does
    not know and so does the loader, which is why extending a format this way is
    safe.
    """
    layer = LAYERS[layer_key]
    size = os.path.getsize(parquet_path)

    # TWO checksums, because they answer different questions (finding F20):
    #   fileSha256    — the bytes on disk. Stable on ONE machine with ONE pyarrow
    #                   version. Proves the write is repeatable here.
    #   contentSha256 — the data itself. Stable ANYWHERE. Proves the generator
    #                   produces the same dataset regardless of environment.
    # A reviewer comparing reproducibility should use contentSha256; fileSha256
    # is for detecting a file that changed after it was written.
    with open(parquet_path, "rb") as f:
        file_checksum = hashlib.sha256(f.read()).hexdigest()

    fixtures = {}
    for row in rows:
        fixtures[row["x_FixtureId"]] = fixtures.get(row["x_FixtureId"], 0) + 1

    manifest = {
        # --- Azure-shaped: what loader.py reads ---------------------------
        "manifestVersion": "2024-04-01",
        "byteCount":       size,
        "blobCount":       1,
        "dataRowCount":    len(rows),
        "exportConfig": {
            "exportName":  layer["export"],
            "dataVersion": layer["version"],
            "type":        "FocusCost",
            "timeFrame":   "MonthToDate",
            "granularity": "Daily",
        },
        "deliveryConfig": {
            "fileFormat":      "Parquet",
            "compressionMode": "Snappy",
            "partitionData":   False,
        },
        "runInfo": {
            "executionType": "Generated",
            "runId":         layer["runId"],
        },
        "blobs": [{
            "blobName":     layer["parquet"],
            "byteCount":    size,
            "dataRowCount": len(rows),
        }],

        # --- our own additions: ignored by the loader ---------------------
        "generator": {
            "script":        "seed_data.py",
            "layer":         layer["layer"],
            "synthetic":     True,
            "generatedAt":   datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "deterministic":  True,
            "fileSha256":     file_checksum,
            "contentSha256":  content_checksum(rows, list(rows[0]) if rows else []),
            "pyarrowVersion": pa.__version__,
            "columnCount":   len(rows[0]) if rows else 0,
            "fixtureCounts": fixtures,
            "groundedAgainst": {
                "export":       "focus-export-p1-sandbox-focus-cost",
                "runId":        "534c40a5-5207-406a-a372-6f8308b56aaa",
                "focusVersion": SCHEMA_ERA_REAL,
                "rows":         118,
            },
        },
    }
    if extra:
        manifest["generator"].update(extra)

    with open(os.path.join(layer["folder"], "manifest.json"), "w") as f:
        json.dump(manifest, f, indent=2)
    return manifest


def write_layer(layer_key, rows, schema, column_names, extra=None):
    """Write one layer: its folder, its Parquet, and its manifest."""
    layer = LAYERS[layer_key]
    os.makedirs(layer["folder"], exist_ok=True)
    parquet_path = os.path.join(layer["folder"], layer["parquet"])
    table = write_parquet(rows, parquet_path, schema=schema,
                          column_names=column_names)
    manifest = write_manifest(layer_key, rows, parquet_path, extra)
    return parquet_path, table, manifest


# =============================================================================
# 6b. FIXTURE — RESERVATION LIFECYCLE  (chunk 1)
# =============================================================================

RESERVATION_ID   = "/providers/Microsoft.Capacity/reservationOrders/res-basv2-1yr-001"
RESERVATION_NAME = "Basv2 1-year reserved capacity"
RESERVED_VM_ID   = f"{SUB_ACCOUNT_ID}/resourceGroups/{RESOURCE_GROUP}/providers/Microsoft.Compute/virtualMachines/vm-web-01"

COMMITTED_RATE = Decimal("0.10")
ON_DEMAND_RATE = Decimal("0.15")
COMMITTED_HOURS_PER_DAY = 24
JULY_DAYS = 31
FULL_USE_DAYS = 10
PARTIAL_USE_HOURS = 18

RESERVATION_TAGS = json_string({
    "team": "platform", "environment": "production",
    "cost-centre": "cc-1001", "application": "web-api",
})

def reservation_lifecycle():
    fixture = "reservation_lifecycle"
    rows = []
    total_hours = COMMITTED_HOURS_PER_DAY * JULY_DAYS
    purchase_cost = COMMITTED_RATE * total_hours

    def period(day):
        return datetime(2026, 7, day), datetime(2026, 7, day + 1) if day < 31 else datetime(2026, 8, 1)

    base = dict(
        BillingAccountId=BILLING_ACCOUNT_ID, BillingAccountName=BILLING_ACCOUNT_NAME,
        BillingAccountType=BILLING_ACCOUNT_TYPE, SubAccountId=SUB_ACCOUNT_ID,
        SubAccountName=SUB_ACCOUNT_NAME, SubAccountType=SUB_ACCOUNT_TYPE,
        BillingCurrency=CURRENCY, BillingPeriodStart=BILLING_PERIOD_START,
        BillingPeriodEnd=BILLING_PERIOD_END, ProviderName=PROVIDER_NAME,
        PublisherName=PUBLISHER_NAME, InvoiceIssuerName=INVOICE_ISSUER_NAME,
        ServiceName=SERVICES["vm"][0], ServiceCategory=SERVICES["vm"][1],
        ServiceSubcategory="Virtual Machines", RegionId=REGION_ID, RegionName=REGION_NAME,
        SkuId="DZH318Z0BQ35", SkuPriceId="DZH318Z0BQ35/00CV",
        SkuMeter="Basv2 Series", x_SkuMeterName="B2ats v2",
        CommitmentDiscountId=RESERVATION_ID, CommitmentDiscountName=RESERVATION_NAME,
        CommitmentDiscountType="Reserved Instance", CommitmentDiscountCategory="Usage",
        CommitmentDiscountUnit="Hours",
    )

    s, e = period(1)
    rows.append(new_row(fixture, **base,
        ChargeCategory="Purchase", ChargeFrequency="Recurring", ChargeClass=None,
        ChargeDescription="Purchase of Basv2 1-year reserved capacity, monthly billing",
        ChargePeriodStart=s, ChargePeriodEnd=e,
        BilledCost=money(purchase_cost), EffectiveCost=money(0),
        ListCost=money(purchase_cost), ContractedCost=money(purchase_cost),
        PricingCategory="Standard",
        ListUnitPrice=money(COMMITTED_RATE), ContractedUnitPrice=money(COMMITTED_RATE),
        PricingQuantity=money(total_hours), PricingUnit="Hours",
        CommitmentDiscountQuantity=money(total_hours),
        CommitmentDiscountStatus=None,
    ))

    for day in range(1, JULY_DAYS + 1):
        s, e = period(day)
        used_hours = COMMITTED_HOURS_PER_DAY if day <= FULL_USE_DAYS else PARTIAL_USE_HOURS
        unused_hours = COMMITTED_HOURS_PER_DAY - used_hours

        rows.append(new_row(fixture, **base,
            ChargeCategory="Usage", ChargeFrequency="Usage-Based", ChargeClass=None,
            ChargeDescription="Basv2 Series compute, covered by reserved capacity",
            ChargePeriodStart=s, ChargePeriodEnd=e,
            BilledCost=money(0), EffectiveCost=money(COMMITTED_RATE * used_hours),
            ListCost=money(ON_DEMAND_RATE * used_hours),
            ContractedCost=money(ON_DEMAND_RATE * used_hours),
            PricingCategory="Committed",
            ListUnitPrice=money(ON_DEMAND_RATE), ContractedUnitPrice=money(ON_DEMAND_RATE),
            ConsumedQuantity=money(used_hours), ConsumedUnit="Hours",
            PricingQuantity=money(used_hours), PricingUnit="Hours",
            CommitmentDiscountStatus="Used", CommitmentDiscountQuantity=money(used_hours),
            x_CommitmentEligible=True,
            ResourceId=RESERVED_VM_ID, ResourceName="vm-web-01",
            ResourceType="Microsoft.Compute/virtualMachines",
            x_ResourceGroupName=RESOURCE_GROUP, Tags=RESERVATION_TAGS,
        ))

        if unused_hours:
            rows.append(new_row(fixture, **base,
                ChargeCategory="Usage", ChargeFrequency="Usage-Based", ChargeClass=None,
                ChargeDescription="Unused reserved capacity, Basv2 1-year reservation",
                ChargePeriodStart=s, ChargePeriodEnd=e,
                BilledCost=money(0), EffectiveCost=money(COMMITTED_RATE * unused_hours),
                ListCost=money(COMMITTED_RATE * unused_hours),
                ContractedCost=money(COMMITTED_RATE * unused_hours),
                PricingCategory="Committed",
                ListUnitPrice=money(COMMITTED_RATE), ContractedUnitPrice=money(COMMITTED_RATE),
                ConsumedQuantity=None, ConsumedUnit=None,
                PricingQuantity=money(unused_hours), PricingUnit="Hours",
                CommitmentDiscountStatus="Unused",
                CommitmentDiscountQuantity=money(unused_hours),
                ResourceId=None, ResourceName=None, ResourceType=None,
                x_ResourceGroupName=None, Tags=None,
            ))
    return rows



# =============================================================================
# 6c. FIXTURE — CHARGE FAMILY: tax, credit, adjustment, corrections  (chunk 2)
# =============================================================================
# Chunk 1 produced ChargeCategory "Usage" and "Purchase". This chunk adds the
# remaining three — Tax, Credit, Adjustment — plus the two faces of ChargeClass.
#
# These are the rows that break naive allocation. Most of them belong to no
# resource at all, so they cannot be charged back to any team, and a showback that
# silently drops them will not reconcile to the invoice.

VAT_RATE = Decimal("0.15")          # South African VAT, the real rate for this account

def charge_family():
    fixture = "charge_family"
    rows = []

    # Shared account-level identity. Note what is NOT here: no ServiceName, no
    # ResourceId, no SkuId — those differ per row and several MUST be null.
    base = dict(
        BillingAccountId=BILLING_ACCOUNT_ID, BillingAccountName=BILLING_ACCOUNT_NAME,
        BillingAccountType=BILLING_ACCOUNT_TYPE, SubAccountId=SUB_ACCOUNT_ID,
        SubAccountName=SUB_ACCOUNT_NAME, SubAccountType=SUB_ACCOUNT_TYPE,
        BillingCurrency=CURRENCY, BillingPeriodStart=BILLING_PERIOD_START,
        BillingPeriodEnd=BILLING_PERIOD_END, ProviderName=PROVIDER_NAME,
        PublisherName=PUBLISHER_NAME, InvoiceIssuerName=INVOICE_ISSUER_NAME,
    )

    def flat_cost(amount):
        """Tax, credit and adjustment rows carry the same figure in all four
        cost columns: there is no list price to discount from and no commitment
        to amortise. Spelling it out once keeps the intent obvious."""
        return dict(BilledCost=money(amount), EffectiveCost=money(amount),
                    ListCost=money(amount), ContractedCost=money(amount))

    # --- 1. TAX -------------------------------------------------------------
    # Spec MUSTs for Tax rows (tax is the most heavily constrained category):
    #   PricingCategory  MUST be null when ChargeCategory is "Tax"
    #   SkuId            MUST be null when ChargeCategory is "Tax"
    #   PricingQuantity  MUST be null when ChargeCategory is "Tax"
    #   ConsumedQuantity MUST be null when ChargeCategory is not "Usage"
    #   EffectiveCost    MUST be calculated from the EffectiveCost of the related
    #                    charges (not from their BilledCost)
    tax_base = COMMITTED_RATE * COMMITTED_HOURS_PER_DAY * JULY_DAYS      # 74.40
    rows.append(new_row(fixture, **base,
        ChargeCategory="Tax", ChargeFrequency="One-Time", ChargeClass=None,
        ChargeDescription="VAT at 15% on July 2026 charges",
        ChargePeriodStart=datetime(2026, 7, 31), ChargePeriodEnd=datetime(2026, 8, 1),
        ServiceName="Tax", ServiceCategory="Other", ServiceSubcategory="Other (Other)",
        **flat_cost(tax_base * VAT_RATE),
        PricingCategory=None, SkuId=None, PricingQuantity=None, PricingUnit=None,
        ConsumedQuantity=None, ConsumedUnit=None,
        ResourceId=None, ResourceName=None, ResourceType=None, Tags=None,
    ))

    # --- 2. CREDIT ----------------------------------------------------------
    # Spec: EffectiveCost of a charge unrelated to other charges (e.g. Credit)
    # MUST match BilledCost. Negative, because a credit reduces what is owed.
    rows.append(new_row(fixture, **base,
        ChargeCategory="Credit", ChargeFrequency="One-Time", ChargeClass=None,
        ChargeDescription="Azure promotional credit applied, July 2026",
        ChargePeriodStart=datetime(2026, 7, 31), ChargePeriodEnd=datetime(2026, 8, 1),
        ServiceName="Azure Credit", ServiceCategory="Other",
        ServiceSubcategory="Other (Other)",
        **flat_cost("-25.00"),
        PricingCategory=None, SkuId=None, PricingQuantity=None,
        ConsumedQuantity=None, ConsumedUnit=None,
        ResourceId=None, ResourceName=None, ResourceType=None, Tags=None,
    ))

    # --- 3. ADJUSTMENT — deliberately ALLOCATABLE ---------------------------
    # The contrast row. Tax and credit belong to nobody; this SLA service credit
    # belongs to a specific VM, so it CAN be charged back. "Reconciling items are
    # unallocatable" is a habit, not a rule — the test is whether ResourceId is null.
    rows.append(new_row(fixture, **base,
        ChargeCategory="Adjustment", ChargeFrequency="One-Time", ChargeClass=None,
        ChargeDescription="SLA service credit, Virtual Machines availability breach",
        ChargePeriodStart=datetime(2026, 7, 31), ChargePeriodEnd=datetime(2026, 8, 1),
        ServiceName=SERVICES["vm"][0], ServiceCategory=SERVICES["vm"][1],
        ServiceSubcategory="Virtual Machines",
        RegionId=REGION_ID, RegionName=REGION_NAME,
        **flat_cost("-3.72"),
        PricingCategory=None, SkuId=None, PricingQuantity=None,
        ConsumedQuantity=None, ConsumedUnit=None,
        ResourceId=RESERVED_VM_ID, ResourceName="vm-web-01",
        ResourceType="Microsoft.Compute/virtualMachines",
        x_ResourceGroupName=RESOURCE_GROUP, Tags=RESERVATION_TAGS,
    ))

    # --- 4. CORRECTION to a PREVIOUSLY INVOICED period ----------------------
    # ChargeClass MUST NOT be null here, and MUST be "Correction".
    # Note the dates: BillingPeriod is JULY (when the correction lands) while
    # ChargePeriod is JUNE (what is being corrected). That mismatch is the whole
    # analytical hazard — a June-dated row arriving in a July file, after June
    # was reported and closed.
    # Note also how BARE this row is. The spec relaxes SkuId, PricingQuantity,
    # ConsumedQuantity and PricingCategory for corrections ("MUST NOT be null
    # when ChargeClass is not 'Correction'"), so corrections legitimately arrive
    # as money with almost no supporting detail.
    rows.append(new_row(fixture, **base,
        ChargeCategory="Usage", ChargeFrequency="Usage-Based", ChargeClass="Correction",
        ChargeDescription="Correction: June 2026 storage over-billing",
        ChargePeriodStart=datetime(2026, 6, 14), ChargePeriodEnd=datetime(2026, 6, 15),
        # STAGE 4, FINDING F38. This row carried no InvoiceId, and neither did
        # 202 of the other 203 rows, so the specification's invoice
        # reconciliation identity had nothing to join on:
        #
        #     The sum of the BilledCost for a given InvoiceId MUST match the sum
        #     of the payable amount provided in the corresponding invoice with
        #     the same id.
        #
        # generate_layer_c.py grounded its invoice on a TIME WINDOW instead —
        # charges whose ChargePeriodStart fell in June — and its docstring
        # claimed the invoice "genuinely ties to the cost data". It does tie. On
        # a different key than the rule uses. That agrees right up until the two
        # keys disagree, and only pointing a check at it showed the difference.
        #
        # WHICH invoice matters, and it is not June's. ChargeClass is
        # "Correction", which per the spec means a correction to a PREVIOUSLY
        # INVOICED billing period — so June was already issued and this cannot
        # appear on it. A correction to a closed period lands on the next
        # invoice, carrying a reference back. Hence July, and generate_layer_c.py
        # now groups by InvoiceId and sets ReferenceInvoiceId to the period being
        # corrected.
        InvoiceId="INV-2026-07-0001",
        ServiceName=SERVICES["storage"][0], ServiceCategory=SERVICES["storage"][1],
        ServiceSubcategory="Object Storage",
        RegionId=REGION_ID, RegionName=REGION_NAME,
        **flat_cost("-1.85"),
        x_CommitmentEligible=False,
        PricingCategory=None, SkuId=None, PricingQuantity=None,
        ConsumedQuantity=None, ConsumedUnit=None,
        ResourceId=f"{SUB_ACCOUNT_ID}/resourceGroups/{RESOURCE_GROUP}"
                   "/providers/Microsoft.Storage/storageAccounts/stp1sandbox",
        ResourceName="stp1sandbox", ResourceType="Microsoft.Storage/storageAccounts",
        x_ResourceGroupName=RESOURCE_GROUP, Tags=RESERVATION_TAGS,
    ))

    # --- 5. CORRECTION WITHIN the current period — ChargeClass MUST be NULL --
    # Same economic event, different timing, opposite flag. The spec: ChargeClass
    # MUST be null "when it represents a correction within the current billing
    # period". Correcting July inside July is just an ordinary negative row.
    # Filtering on ChargeClass='Correction' will NOT find this one.
    rows.append(new_row(fixture, **base,
        ChargeCategory="Usage", ChargeFrequency="Usage-Based", ChargeClass=None,
        ChargeDescription="Rebate: July 2026 bandwidth metering adjustment",
        ChargePeriodStart=datetime(2026, 7, 18), ChargePeriodEnd=datetime(2026, 7, 19),
        ServiceName=SERVICES["network"][0], ServiceCategory=SERVICES["network"][1],
        ServiceSubcategory="Network Connectivity",
        RegionId=REGION_ID, RegionName=REGION_NAME,
        **flat_cost("-0.42"),
        PricingCategory="Standard", SkuId="DZH318Z0BNZ4",
        # STAGE 4, FINDING F29. SkuPriceId was missing here and the row was
        # non-conformant: the spec requires it whenever ChargeCategory is
        # "Usage" or "Purchase" and ChargeClass is not "Correction", which this
        # row satisfies — it is a Usage row and its ChargeClass is deliberately
        # null. SkuId was set and SkuPriceId was not, so the row was also
        # internally inconsistent.
        #
        # None of the fifteen Stage 3 self-tests caught it, because none of them
        # implemented that conditional rule. The Stage 4 harness caught it on its
        # first substantive run, from the specification sentence rather than from
        # a hand-written assertion. That is the argument for parsing the spec,
        # made by the thing it found.
        #
        # SkuMeter is added at the same time. It is only a SHOULD NOT be null
        # when SkuId is not null — a warning, not a failure — but leaving a known
        # SHOULD deviation in the CLEAN layer would give the WARN tier a
        # permanent non-zero floor, and a floor is where a real regression hides.
        SkuPriceId="DZH318Z0BNZ4/00CV", SkuMeter="Bandwidth Inter-Region",
        x_CommitmentEligible=False,
        PricingQuantity=money("-2.8"), PricingUnit="GB",
        ConsumedQuantity=money("-2.8"), ConsumedUnit="GB",
        ListUnitPrice=money("0.15"), ContractedUnitPrice=money("0.15"),
        ResourceId=None, ResourceName=None, ResourceType=None, Tags=None,
    ))

    return rows



# =============================================================================
# 6d. FIXTURE — PRICING FAMILY  (chunk 3)
# =============================================================================
# Four scenarios the sandbox will never produce, all of which need columns that
# do not exist in Azure's real 1.0r2 export. This is decision D2 paying off:
# PricingCurrency, PricingCurrencyEffectiveCost and the rest are only available
# because the synthetic layer is generated at v1.2.

# A second billing account, billed in euros. The exchange rate is fixed for the
# billing period, mirroring Azure's own x_BillingExchangeRateDate behaviour.
BILLING_ACCOUNT_ID_EUR   = "/providers/Microsoft.Billing/billingAccounts/00000000-0000-0000-0000-000000000003"
BILLING_ACCOUNT_NAME_EUR = "Portfolio Sandbox Account (EU)"
SUB_ACCOUNT_ID_EUR       = "/subscriptions/00000000-0000-0000-0000-000000000004"
USD_TO_EUR               = Decimal("0.92")

# A virtual currency: prices published in credits, invoiced in dollars.
CREDITS_PER_USD = Decimal("100")


def pricing_family():
    fixture = "pricing_family"
    rows = []

    base = dict(
        BillingAccountId=BILLING_ACCOUNT_ID, BillingAccountName=BILLING_ACCOUNT_NAME,
        BillingAccountType=BILLING_ACCOUNT_TYPE, SubAccountId=SUB_ACCOUNT_ID,
        SubAccountName=SUB_ACCOUNT_NAME, SubAccountType=SUB_ACCOUNT_TYPE,
        BillingCurrency=CURRENCY, BillingPeriodStart=BILLING_PERIOD_START,
        BillingPeriodEnd=BILLING_PERIOD_END, ProviderName=PROVIDER_NAME,
        PublisherName=PUBLISHER_NAME, InvoiceIssuerName=INVOICE_ISSUER_NAME,
        RegionId=REGION_ID, RegionName=REGION_NAME,
        ChargeClass=None, x_ResourceGroupName=RESOURCE_GROUP, Tags=RESERVATION_TAGS,
    )

    # --- 1. WHOLE-BLOCK PRICING — the contrast case for finding F7 ----------
    # Azure's real export block-prices in units of 10,000 and emits FRACTIONAL
    # blocks: 191 transactions -> PricingQuantity 0.0191. This fixture models the
    # OTHER legitimate behaviour, WHOLE blocks: 500 transactions inside a 1,000
    # block -> PricingQuantity 1. You consume half a block and pay for all of it.
    #
    # Why it matters: ConsumedQuantity and PricingQuantity answer different
    # questions. Divide cost by the wrong one and the unit economics are wrong.
    # A waste query must handle both shapes — which is exactly why having the
    # real fractional case AND this synthetic whole-block case is stronger than
    # having either alone.
    storage_id = (f"{SUB_ACCOUNT_ID}/resourceGroups/{RESOURCE_GROUP}"
                  "/providers/Microsoft.Storage/storageAccounts/stp1sandbox")
    for day, consumed in ((20, 500), (21, 1500)):
        blocks = (consumed + 999) // 1000          # round UP to whole blocks
        rows.append(new_row(fixture, **base,
            ChargeCategory="Usage", ChargeFrequency="Usage-Based",
            ChargeDescription="Storage write operations, billed per 1K block",
            ChargePeriodStart=datetime(2026, 7, day),
            ChargePeriodEnd=datetime(2026, 7, day + 1),
            ServiceName=SERVICES["storage"][0], ServiceCategory=SERVICES["storage"][1],
            ServiceSubcategory="Object Storage",
            BilledCost=money(Decimal("0.05") * blocks),
            EffectiveCost=money(Decimal("0.05") * blocks),
            ListCost=money(Decimal("0.05") * blocks),
            ContractedCost=money(Decimal("0.05") * blocks),
            PricingCategory="Standard",
            ListUnitPrice=money("0.05"), ContractedUnitPrice=money("0.05"),
            ConsumedQuantity=money(consumed), ConsumedUnit="Operations",
            PricingQuantity=money(blocks), PricingUnit="1K Operations",
            x_PricingBlockSize=money(1000),
            x_CommitmentEligible=False,
            SkuId="DZH318Z0BQ4M", SkuPriceId="DZH318Z0BQ4M/002T",
            SkuMeter="Write Operations", x_SkuMeterName="Write Operations",
            ResourceId=storage_id, ResourceName="stp1sandbox",
            ResourceType="Microsoft.Storage/storageAccounts",
        ))

    # --- 2. VIRTUAL CURRENCY — priced in credits, billed in dollars ---------
    # PricingCurrency is a NATIONAL **or VIRTUAL** currency. Here the provider
    # publishes prices in credits and invoices in USD at 100 credits = $1.
    # Three columns exist only to carry this, and NONE of them exist at 1.0r2:
    #   PricingCurrency, PricingCurrencyEffectiveCost, PricingCurrencyListUnitPrice
    # The trap: summing PricingCurrencyEffectiveCost across a mixed dataset adds
    # credits to dollars. Only BillingCurrency amounts are ever safe to total.
    tokens = 1_500_000
    credits_per_million = Decimal("200")
    credits = credits_per_million * Decimal(tokens) / Decimal(1_000_000)
    rows.append(new_row(fixture, **base,
        ChargeCategory="Usage", ChargeFrequency="Usage-Based",
        ChargeDescription="Generative AI inference, 1M-token pricing",
        ChargePeriodStart=datetime(2026, 7, 22), ChargePeriodEnd=datetime(2026, 7, 23),
        ServiceName="Azure OpenAI Service",
        ServiceCategory="AI and Machine Learning", ServiceSubcategory="Generative AI",
        BilledCost=money(credits / CREDITS_PER_USD),
        EffectiveCost=money(credits / CREDITS_PER_USD),
        ListCost=money(credits / CREDITS_PER_USD),
        ContractedCost=money(credits / CREDITS_PER_USD),
        PricingCategory="Standard",
        ListUnitPrice=money(credits_per_million / CREDITS_PER_USD),
        ContractedUnitPrice=money(credits_per_million / CREDITS_PER_USD),
        PricingCurrency="AI Credits",
        PricingCurrencyEffectiveCost=money(credits),
        PricingCurrencyListUnitPrice=money(credits_per_million),
        PricingCurrencyContractedUnitPrice=money(credits_per_million),
        ConsumedQuantity=money(tokens), ConsumedUnit="Tokens",
        PricingQuantity=money("1.5"), PricingUnit="1M Tokens",
        x_TokenCount=money(tokens), x_TokenModel="gpt-4o-mini",
        x_CommitmentEligible=False,
        SkuId="DZH318Z0CFXG", SkuPriceId="DZH318Z0CFXG/00KJ",
        SkuMeter="Input Tokens", x_SkuMeterName="gpt-4o-mini Input Tokens",
        ResourceId=f"{SUB_ACCOUNT_ID}/resourceGroups/{RESOURCE_GROUP}"
                   "/providers/Microsoft.CognitiveServices/accounts/aoai-p1-sandbox",
        ResourceName="aoai-p1-sandbox",
        ResourceType="Microsoft.CognitiveServices/accounts",
    ))

    # --- 3. SECOND BILLING CURRENCY — the same VM, invoiced in euros --------
    # A second billing account settles in EUR while Microsoft still prices in USD.
    # BillingCurrency EUR, PricingCurrency USD, exchange rate fixed for the period.
    #
    # THE TRAP: SUM(EffectiveCost) across this dataset now adds euros to dollars
    # and returns a number that means nothing. Any total must either filter to one
    # BillingCurrency or convert first. This is the single most common multi-
    # currency reporting error, and it produces a plausible-looking figure.
    eur_base = dict(base)
    eur_base.update(
        BillingAccountId=BILLING_ACCOUNT_ID_EUR,
        BillingAccountName=BILLING_ACCOUNT_NAME_EUR,
        SubAccountId=SUB_ACCOUNT_ID_EUR, SubAccountName="Azure subscription 2 (EU)",
        BillingCurrency="EUR", RegionId="westeurope", RegionName="West Europe",
    )
    for day in (23, 24):
        usd_cost = Decimal("0.15") * 24
        rows.append(new_row(fixture, **eur_base,
            ChargeCategory="Usage", ChargeFrequency="Usage-Based",
            ChargeDescription="Basv2 Series compute, EU billing account",
            ChargePeriodStart=datetime(2026, 7, day),
            ChargePeriodEnd=datetime(2026, 7, day + 1),
            ServiceName=SERVICES["vm"][0], ServiceCategory=SERVICES["vm"][1],
            ServiceSubcategory="Virtual Machines",
            BilledCost=money(usd_cost * USD_TO_EUR),
            EffectiveCost=money(usd_cost * USD_TO_EUR),
            ListCost=money(usd_cost * USD_TO_EUR),
            ContractedCost=money(usd_cost * USD_TO_EUR),
            PricingCategory="Standard",
            ListUnitPrice=money(Decimal("0.15") * USD_TO_EUR),
            ContractedUnitPrice=money(Decimal("0.15") * USD_TO_EUR),
            PricingCurrency="USD",
            PricingCurrencyEffectiveCost=money(usd_cost),
            PricingCurrencyListUnitPrice=money("0.15"),
            PricingCurrencyContractedUnitPrice=money("0.15"),
            x_BillingExchangeRate=money(USD_TO_EUR),
            x_CommitmentEligible=True,
            ConsumedQuantity=money(24), ConsumedUnit="Hours",
            PricingQuantity=money(24), PricingUnit="Hours",
            SkuId="DZH318Z0BQ35", SkuPriceId="DZH318Z0BQ35/00CV",
            SkuMeter="Basv2 Series", x_SkuMeterName="B2ats v2",
            ResourceId=f"{SUB_ACCOUNT_ID_EUR}/resourceGroups/{RESOURCE_GROUP}"
                       "/providers/Microsoft.Compute/virtualMachines/vm-web-eu-01",
            ResourceName="vm-web-eu-01",
            ResourceType="Microsoft.Compute/virtualMachines",
        ))

    # --- 4. DYNAMIC PRICING — a spot VM -------------------------------------
    # PricingCategory MUST be "Dynamic" when the provider can change the unit
    # price without notice. Spot capacity is the classic case: deeply discounted
    # against list, and interruptible. Note ListUnitPrice stays at the on-demand
    # rate while ContractedUnitPrice is what was actually charged — so the
    # List-minus-Contracted savings ladder picks this up automatically.
    rows.append(new_row(fixture, **base,
        ChargeCategory="Usage", ChargeFrequency="Usage-Based",
        ChargeDescription="Basv2 Series spot compute, interruptible",
        ChargePeriodStart=datetime(2026, 7, 25), ChargePeriodEnd=datetime(2026, 7, 26),
        ServiceName=SERVICES["vm"][0], ServiceCategory=SERVICES["vm"][1],
        ServiceSubcategory="Virtual Machines",
        BilledCost=money(Decimal("0.045") * 24), EffectiveCost=money(Decimal("0.045") * 24),
        ListCost=money(Decimal("0.15") * 24), ContractedCost=money(Decimal("0.045") * 24),
        PricingCategory="Dynamic",
        ListUnitPrice=money("0.15"), ContractedUnitPrice=money("0.045"),
        ConsumedQuantity=money(24), ConsumedUnit="Hours",
        PricingQuantity=money(24), PricingUnit="Hours",
        x_CommitmentEligible=False,
        SkuId="DZH318Z0BQ35", SkuPriceId="DZH318Z0BQ35/00SP",
        SkuMeter="Basv2 Series Spot", x_SkuMeterName="B2ats v2 Spot",
        ResourceId=f"{SUB_ACCOUNT_ID}/resourceGroups/{RESOURCE_GROUP}"
                   "/providers/Microsoft.Compute/virtualMachines/vm-batch-spot-01",
        ResourceName="vm-batch-spot-01",
        ResourceType="Microsoft.Compute/virtualMachines",
    ))

    # --- 5. MARKETPLACE — BilledCost 0 does NOT mean free -------------------
    # Spec: "BilledCost MUST be 0 for charges where payments are received by a
    # third party (e.g., marketplace transactions)." Microsoft is the provider,
    # but a different company publishes and gets paid, so Microsoft's invoice
    # shows nothing.
    #
    # THE TRAP: a report built on BilledCost shows this workload costing nothing.
    # It is not free — EffectiveCost is $18.00. PublisherName differs from
    # ProviderName, which is how these rows are found.
    market_base = {k: v for k, v in base.items() if k != "PublisherName"}
    rows.append(new_row(fixture, **market_base,
        ChargeCategory="Usage", ChargeFrequency="Recurring",
        ChargeDescription="Third-party security appliance licence, monthly",
        ChargePeriodStart=datetime(2026, 7, 26), ChargePeriodEnd=datetime(2026, 7, 27),
        ServiceName="Marketplace Security Appliance",
        ServiceCategory="Security", ServiceSubcategory="Threat Detection and Response",
        PublisherName="Fortifex Security Ltd",
        BilledCost=money(0), EffectiveCost=money("18.00"),
        ListCost=money("18.00"), ContractedCost=money("18.00"),
        PricingCategory="Other",
        ListUnitPrice=money("18.00"), ContractedUnitPrice=money("18.00"),
        ConsumedQuantity=money(1), ConsumedUnit="Licences",
        PricingQuantity=money(1), PricingUnit="Licences",
        x_CommitmentEligible=False,
        SkuId="fortifex-appliance-std", SkuPriceId="fortifex-appliance-std/monthly",
        SkuMeter="Standard Licence", x_SkuMeterName="Fortifex Standard",
        ResourceId=f"{SUB_ACCOUNT_ID}/resourceGroups/{RESOURCE_GROUP}"
                   "/providers/Fortifex.Security/appliances/fx-appliance-01",
        ResourceName="fx-appliance-01",
        ResourceType="Fortifex.Security/appliances",
    ))

    return rows



# =============================================================================
# 6e. FIXTURE — ACCOUNT, RESOURCE, SKU, LOCATION, TIMEFRAME  (chunk 4)
# =============================================================================
# The remaining build-spec §4.2 families. Mostly about IDENTITY and TIME: what a
# thing is called versus what it is, and where a charge sits on the calendar.

CAPACITY_RESERVATION_ID = ("/subscriptions/00000000-0000-0000-0000-000000000001"
                           "/providers/Microsoft.Compute/capacityReservationGroups"
                           "/crg-p1-sandbox/capacityReservations/cr-basv2-01")

UPFRONT_RESERVATION_ID = ("/providers/Microsoft.Capacity/reservationOrders"
                          "/res-basv2-3yr-upfront-001")


def account_resource_sku_family():
    fixture = "account_resource_sku"
    rows = []

    base = dict(
        BillingAccountId=BILLING_ACCOUNT_ID, BillingAccountName=BILLING_ACCOUNT_NAME,
        BillingAccountType=BILLING_ACCOUNT_TYPE, SubAccountId=SUB_ACCOUNT_ID,
        SubAccountType=SUB_ACCOUNT_TYPE,
        BillingCurrency=CURRENCY, BillingPeriodStart=BILLING_PERIOD_START,
        BillingPeriodEnd=BILLING_PERIOD_END, ProviderName=PROVIDER_NAME,
        PublisherName=PUBLISHER_NAME, InvoiceIssuerName=INVOICE_ISSUER_NAME,
        RegionId=REGION_ID, RegionName=REGION_NAME, ChargeClass=None,
        ChargeCategory="Usage", ChargeFrequency="Usage-Based",
        PricingCategory="Standard",
    )

    def cost(amount):
        return dict(BilledCost=money(amount), EffectiveCost=money(amount),
                    ListCost=money(amount), ContractedCost=money(amount))

    # --- 1. SkuPriceDetails, part 1 of 2 — the COMPUTE properties -----------
    # The build spec asks for a "13-key SkuPriceDetails JSON". The specification
    # forbids exactly that in one row: "SkuPriceDetails MUST NOT include
    # properties that are not applicable to the corresponding SkuPriceId."
    # No single SKU has all 13 — a VM has no StorageClass, a disk has no
    # CoreCount. So the 13 FOCUS-defined properties are covered across TWO rows,
    # each carrying only what applies to it. See finding F15.
    #
    # Three spec rules on display here:
    #   - keys use PascalCase and MUST match the spec's exact spelling
    #     (MemorySize, never MemoryGB — build spec §8's standing trap)
    #   - provider-defined keys MUST begin with "x_"
    #   - numeric values MUST be per a single PricingUnit
    rows.append(new_row(fixture, **base,
        ChargeDescription="Basv2 Series compute, full SKU price detail",
        ChargePeriodStart=datetime(2026, 7, 27), ChargePeriodEnd=datetime(2026, 7, 28),
        ServiceName=SERVICES["vm"][0], ServiceCategory=SERVICES["vm"][1],
        ServiceSubcategory="Virtual Machines",
        SubAccountName=SUB_ACCOUNT_NAME,
        **cost(Decimal("0.15") * 24),
        ListUnitPrice=money("0.15"), ContractedUnitPrice=money("0.15"),
        ConsumedQuantity=money(24), ConsumedUnit="Hours",
        PricingQuantity=money(24), PricingUnit="Hours",
        SkuId="DZH318Z0BQ35", SkuPriceId="DZH318Z0BQ35/00CV",
        SkuMeter="Basv2 Series", x_SkuMeterName="B2ats v2",
        SkuPriceDetails=json_string({
            "CoreCount": 2,
            "DiskSpace": 32,
            "DiskType": "SSD",
            "GpuCount": 0,
            "InstanceSeries": "Basv2",
            "InstanceType": "B2ats_v2",
            "MemorySize": 1,
            "NetworkMaxIops": 4000,
            "NetworkMaxThroughput": 6250,
            "OperatingSystem": "Linux",
            "x_AcceleratedNetworking": False,
        }),
        AvailabilityZone="southafricanorth-az1",
        x_CommitmentEligible=True,
        ResourceId=RESERVED_VM_ID, ResourceName="vm-web-01",
        ResourceType="Microsoft.Compute/virtualMachines",
        x_ResourceGroupName=RESOURCE_GROUP, Tags=RESERVATION_TAGS,
    ))

    # --- 2. SkuPriceDetails, part 2 of 2 — the STORAGE properties -----------
    rows.append(new_row(fixture, **base,
        ChargeDescription="Premium SSD managed disk, provisioned capacity",
        ChargePeriodStart=datetime(2026, 7, 27), ChargePeriodEnd=datetime(2026, 7, 28),
        ServiceName=SERVICES["storage"][0], ServiceCategory=SERVICES["storage"][1],
        ServiceSubcategory="Block Storage",
        SubAccountName=SUB_ACCOUNT_NAME,
        **cost("0.62"),
        ListUnitPrice=money("0.02"), ContractedUnitPrice=money("0.02"),
        # GiB, not GB. A gibibyte is 2^30 bytes; a gigabyte is 10^9. They differ
        # by about 7%, which is a real reconciliation gap at scale.
        ConsumedQuantity=money(31), ConsumedUnit="GiB",
        PricingQuantity=money(31), PricingUnit="GiB",
        SkuId="DZH318Z0BP04", SkuPriceId="DZH318Z0BP04/00P1",
        SkuMeter="Premium SSD Managed Disks", x_SkuMeterName="P4 LRS Disk",
        SkuPriceDetails=json_string({
            "DiskMaxIops": 120,
            "DiskSpace": 32,
            "DiskType": "SSD",
            "Redundancy": "Local",
            "StorageClass": "Premium",
        }),
        x_CommitmentEligible=False,
        ResourceId=f"{SUB_ACCOUNT_ID}/resourceGroups/{RESOURCE_GROUP}"
                   "/providers/Microsoft.Compute/disks/vm-web-01-osdisk",
        ResourceName="vm-web-01-osdisk", ResourceType="Microsoft.Compute/disks",
        x_ResourceGroupName=RESOURCE_GROUP, Tags=RESERVATION_TAGS,
    ))

    # --- 3. THE NAMELESS RESOURCE — conformant, not a defect ---------------
    # Amendment A7.2. "ResourceName MUST be null when ResourceId is null OR WHEN
    # THE RESOURCE DOES NOT HAVE AN ASSIGNED DISPLAY NAME." System-generated
    # resources often have no display name at all.
    #
    # Note the direction. loader.py's cascade check flags a satellite filled
    # while its anchor is null. This is the OPPOSITE: anchor filled, satellite
    # null — and it is entirely legal. A null in a satellite column is not
    # evidence of anything on its own.
    rows.append(new_row(fixture, **base,
        ChargeDescription="System-managed network interface, hourly",
        ChargePeriodStart=datetime(2026, 7, 28), ChargePeriodEnd=datetime(2026, 7, 29),
        ServiceName=SERVICES["network"][0], ServiceCategory=SERVICES["network"][1],
        ServiceSubcategory="Network Infrastructure",
        SubAccountName=SUB_ACCOUNT_NAME,
        **cost("0.05"),
        ListUnitPrice=money("0.05"), ContractedUnitPrice=money("0.05"),
        ConsumedQuantity=money(1), ConsumedUnit="Units",
        PricingQuantity=money(1), PricingUnit="Units",
        x_CommitmentEligible=False,
        SkuId="DZH318Z0BNZ4", SkuPriceId="DZH318Z0BNZ4/00NI",
        SkuMeter="Network Interface", x_SkuMeterName="NIC Hours",
        ResourceId=f"{SUB_ACCOUNT_ID}/resourceGroups/{RESOURCE_GROUP}"
                   "/providers/Microsoft.Network/networkInterfaces"
                   "/nic-a41f9c02-7b3e-4d18-9f6a-2c8e5b1d0447",
        ResourceName=None,                      # <- conformant null
        ResourceType="Microsoft.Network/networkInterfaces",
        x_ResourceGroupName=RESOURCE_GROUP, Tags=None,
    ))

    # --- 4. THE RENAME — same thing, two names, plus mixed-case group ------
    # On 29 July the subscription and the VM were both renamed. The IDs did not
    # change; the names did.
    #
    # GROUP BY SubAccountName splits one subscription into two. GROUP BY
    # SubAccountId does not. Names are labels and they drift; IDs are identity.
    # Always group by the Id column and carry the name along for display.
    #
    # The second row also uses RG-P1-SANDBOX in upper case, which is the
    # deliberate version of finding F9 — already present in the real export.
    for day, sub_name, res_name, rg in (
        (29, SUB_ACCOUNT_NAME,        "vm-web-01", RESOURCE_GROUP),
        (30, "Production Subscription", "vm-web-prod-01", RESOURCE_GROUP.upper()),
    ):
        rows.append(new_row(fixture, **base,
            ChargeDescription="Basv2 Series compute, hourly",
            ChargePeriodStart=datetime(2026, 7, day),
            ChargePeriodEnd=datetime(2026, 7, day + 1),
            ServiceName=SERVICES["vm"][0], ServiceCategory=SERVICES["vm"][1],
            ServiceSubcategory="Virtual Machines",
            SubAccountName=sub_name,
            **cost(Decimal("0.15") * 24),
            ListUnitPrice=money("0.15"), ContractedUnitPrice=money("0.15"),
            ConsumedQuantity=money(24), ConsumedUnit="Hours",
            PricingQuantity=money(24), PricingUnit="Hours",
            SkuId="DZH318Z0BQ35", SkuPriceId="DZH318Z0BQ35/00CV",
            SkuMeter="Basv2 Series", x_SkuMeterName="B2ats v2",
            x_CommitmentEligible=True,
            ResourceId=RESERVED_VM_ID,          # <- unchanged across the rename
            ResourceName=res_name,
            ResourceType="Microsoft.Compute/virtualMachines",
            x_ResourceGroupName=rg, Tags=RESERVATION_TAGS,
        ))

    # --- 5. CAPACITY RESERVATION — the cross-family check ------------------
    # Deferred from Stage 2 because 1.0r2 carries no capacity-reservation columns
    # at all, so it was never testable on real data.
    #
    # A capacity reservation and a commitment discount are DIFFERENT THINGS that
    # can apply to the same charge: the capacity reservation guarantees the
    # hardware is there, the commitment discount reduces the price. Both sets of
    # columns populate together. Confusing the two double-counts the saving.
    cr_base = {k: v for k, v in base.items() if k != "PricingCategory"}
    for status, hours, resource in (("Used", 20, RESERVED_VM_ID), ("Unused", 4, None)):
        rows.append(new_row(fixture, **cr_base,
            ChargeDescription=f"Basv2 capacity reservation, {status.lower()} portion",
            # STAGE 4, FINDING F39. These rows were dated 30-31 July, one day
            # BEFORE the 3-year reservation they draw against begins. The
            # purchase row below sits at 31 July and the Layer C contract term
            # runs 2026-07-31 to 2029-07-31, so 2.40 of EffectiveCost was booked
            # against a commitment that had not started.
            #
            # Not visible by reading: the cost dataset does not carry a
            # commitment term, so nothing here contradicted anything here. It
            # took the chunk 6b cross-dataset check, comparing these dates to
            # ContractCommitmentPeriodStart in contract_commitment, to find it —
            # and it surfaced as ZERO overlap rather than as a small one, which
            # is a different condition and not a rounding artefact.
            #
            # The purchase date is the correct one, so the usage moves.
            ChargePeriodStart=datetime(2026, 7, 31), ChargePeriodEnd=datetime(2026, 8, 1),
            ServiceName=SERVICES["vm"][0], ServiceCategory=SERVICES["vm"][1],
            ServiceSubcategory="Virtual Machines",
            SubAccountName=SUB_ACCOUNT_NAME, PricingCategory="Committed",
            # BilledCost MUST be 0: this capacity was paid for at purchase.
            # Billing it again here would charge twice for the same hours — the
            # exact error the chunk 1 fixture exists to demonstrate. Caught by
            # the reconciliation assertion, not by review (finding F16).
            BilledCost=money(0),
            EffectiveCost=money(COMMITTED_RATE * hours),
            ListCost=money(Decimal("0.15") * hours),
            ContractedCost=money(COMMITTED_RATE * hours),
            ListUnitPrice=money("0.15"), ContractedUnitPrice=money(COMMITTED_RATE),
            ConsumedQuantity=money(hours) if status == "Used" else None,
            ConsumedUnit="Hours" if status == "Used" else None,
            PricingQuantity=money(hours), PricingUnit="Hours",
            CapacityReservationId=CAPACITY_RESERVATION_ID,
            CapacityReservationStatus=status,
            # Drawn against the 3-year UPFRONT reservation, not chunk 1's monthly
            # one. Using chunk 1's would over-draw it: 744 hours were purchased
            # for July and 744 are already consumed there.
            CommitmentDiscountId=UPFRONT_RESERVATION_ID,
            CommitmentDiscountName="Basv2 3-year reserved capacity, all upfront",
            CommitmentDiscountType="Reserved Instance",
            CommitmentDiscountCategory="Usage",
            CommitmentDiscountStatus=status,
            CommitmentDiscountQuantity=money(hours),
            CommitmentDiscountUnit="Hours",
            x_CommitmentEligible=True if status == "Used" else None,
            SkuId="DZH318Z0BQ35", SkuPriceId="DZH318Z0BQ35/00CV",
            SkuMeter="Basv2 Series", x_SkuMeterName="B2ats v2",
            ResourceId=resource,
            ResourceName="vm-web-01" if resource else None,
            ResourceType="Microsoft.Compute/virtualMachines" if resource else None,
            x_ResourceGroupName=RESOURCE_GROUP if resource else None,
            Tags=RESERVATION_TAGS if resource else None,
        ))

    # --- 6. THE ONE-TIME UPFRONT PURCHASE — deferred from chunk 1 ----------
    # Chunk 1 modelled a RECURRING monthly reservation so the term closes inside
    # the dataset. This is the other shape: a 3-year reservation paid entirely
    # upfront, ChargeFrequency "One-Time".
    #
    # It deliberately does NOT close here. $2,628 buys 26,280 hours across three
    # years; July can only amortise its own slice. That is why chunk 1 used the
    # recurring form for the closure assertion — and it is the honest reason the
    # spec's invariant needs a scope (finding F10).
    purchase_base = {k: v for k, v in base.items()
                     if k not in ("ChargeCategory", "ChargeFrequency")}
    rows.append(new_row(fixture, **purchase_base,
        ChargeCategory="Purchase", ChargeFrequency="One-Time",
        ChargeDescription="Purchase of Basv2 3-year reserved capacity, all upfront",
        ChargePeriodStart=datetime(2026, 7, 31), ChargePeriodEnd=datetime(2026, 8, 1),
        ServiceName=SERVICES["vm"][0], ServiceCategory=SERVICES["vm"][1],
        ServiceSubcategory="Virtual Machines",
        SubAccountName=SUB_ACCOUNT_NAME,
        BilledCost=money("2628.00"), EffectiveCost=money(0),
        ListCost=money("2628.00"), ContractedCost=money("2628.00"),
        ListUnitPrice=money("0.10"), ContractedUnitPrice=money("0.10"),
        PricingQuantity=money(26280), PricingUnit="Hours",
        CommitmentDiscountId=UPFRONT_RESERVATION_ID,
        CommitmentDiscountName="Basv2 3-year reserved capacity, all upfront",
        CommitmentDiscountType="Reserved Instance",
        CommitmentDiscountCategory="Usage",
        CommitmentDiscountQuantity=money(26280), CommitmentDiscountUnit="Hours",
        SkuId="DZH318Z0BQ35", SkuPriceId="DZH318Z0BQ35/00CV",
        SkuMeter="Basv2 Series", x_SkuMeterName="B2ats v2",
        ResourceId=None, ResourceName=None, ResourceType=None, Tags=None,
    ))

    # --- 7. THE MONTH BOUNDARY — half-open intervals ------------------------
    # ChargePeriodStart is the INCLUSIVE start; ChargePeriodEnd is the EXCLUSIVE
    # end. This row covers the whole of 31 July, so its end is 1 August 00:00 —
    # a timestamp in AUGUST on a row that belongs entirely to JULY.
    #
    # THE TRAP: "WHERE ChargePeriodEnd BETWEEN 1 July AND 31 July" silently drops
    # this row. "BETWEEN 1 July AND 1 August" on a September file double-counts.
    # Correct form is always >= start AND < end.
    rows.append(new_row(fixture, **base,
        ChargeDescription="Storage capacity, final day of billing period",
        ChargePeriodStart=datetime(2026, 7, 31),
        ChargePeriodEnd=datetime(2026, 8, 1),          # <- exclusive, in August
        ServiceName=SERVICES["storage"][0], ServiceCategory=SERVICES["storage"][1],
        ServiceSubcategory="Object Storage",
        SubAccountName=SUB_ACCOUNT_NAME,
        **cost("0.31"),
        ListUnitPrice=money("0.01"), ContractedUnitPrice=money("0.01"),
        ConsumedQuantity=money(31), ConsumedUnit="GiB",
        PricingQuantity=money(31), PricingUnit="GiB",
        x_CommitmentEligible=False,
        SkuId="DZH318Z0BQ4M", SkuPriceId="DZH318Z0BQ4M/002T",
        SkuMeter="Hot LRS Data Stored", x_SkuMeterName="Hot LRS Data Stored",
        ResourceId=f"{SUB_ACCOUNT_ID}/resourceGroups/{RESOURCE_GROUP}"
                   "/providers/Microsoft.Storage/storageAccounts/stp1sandbox",
        ResourceName="stp1sandbox", ResourceType="Microsoft.Storage/storageAccounts",
        x_ResourceGroupName=RESOURCE_GROUP, Tags=RESERVATION_TAGS,
    ))

    # --- 8. INVOICING LATENCY — invoiced vs not yet invoiced ----------------
    # Two identical charges, days apart. The earlier one has an InvoiceId; the
    # later one does not, because the invoice has not been cut yet.
    #
    # A null InvoiceId means "not yet on an invoice" — it is NOT missing data.
    # (Straight from the keepsake's null-as-information table.) The consequence
    # for reporting: an invoice-anchored report and a charge-period report will
    # legitimately disagree at month end, and the gap is timing, not error.
    for day, invoice in ((28, "INV-2026-07-0001"), (31, None)):
        rows.append(new_row(fixture, **base,
            ChargeDescription="App Service plan, hourly",
            ChargePeriodStart=datetime(2026, 7, day),
            ChargePeriodEnd=datetime(2026, 7, day + 1) if day < 31
                            else datetime(2026, 8, 1),
            ServiceName=SERVICES["web"][0], ServiceCategory=SERVICES["web"][1],
            ServiceSubcategory="Application Platforms",
            SubAccountName=SUB_ACCOUNT_NAME,
            **cost("0.24"),
            ListUnitPrice=money("0.01"), ContractedUnitPrice=money("0.01"),
            ConsumedQuantity=money(24), ConsumedUnit="Hours",
            PricingQuantity=money(24), PricingUnit="Hours",
            InvoiceId=invoice,
            x_CommitmentEligible=False,
            SkuId="DZH318Z0CD3N", SkuPriceId="DZH318Z0CD3N/00B1",
            SkuMeter="App Service Plan", x_SkuMeterName="B1 App Service Hours",
            ResourceId=f"{SUB_ACCOUNT_ID}/resourceGroups/{RESOURCE_GROUP}"
                       "/providers/Microsoft.Web/serverFarms/asp-p1-sandbox",
            ResourceName="asp-p1-sandbox", ResourceType="Microsoft.Web/serverFarms",
            x_ResourceGroupName=RESOURCE_GROUP, Tags=RESERVATION_TAGS,
        ))

    return rows



# =============================================================================
# 6f. FIXTURE — THE PRE-1.2 LEGACY ERA  (chunk 5)
# =============================================================================
# Layer 2. A 2024-era export from a provider emitting FOCUS 1.0, written to its
# OWN file with its OWN schema (51 columns, not 66) because that is how it
# actually arrives: you do not receive one file spanning two schema versions,
# you receive a 2024 file and a 2026 file and have to reconcile them.
#
# What makes this fixture worth having: it is the only data on which loader.py's
# build-spec §7 coalesce() fallbacks actually FIRE. The four fallbacks map to
# exactly the four root columns introduced after 1.0 — which is why they exist.
#
# Also hourly, not daily. Older exports were commonly hourly, and mixing
# granularities is its own reconciliation problem: a naive row count compares
# 24 legacy rows against 1 modern row for the same day and the same money.

# STAGE 4, FINDING F33. The legacy commitment row used to borrow RESERVATION_ID
# — the same constant the 2026 reservation_lifecycle fixture uses. Convenience,
# not intent: this fixture exists to show the 1.0 version gap, and the identity
# of the reservation is incidental to that.
#
# The consequence was not incidental. Grouping by CommitmentDiscountId put a
# 2024 usage row inside a 2026 commitment's scope, and the commitment's closure
# came out 0.10 over: 74.50 of usage against a 74.40 purchase.
# reservation_lifecycle balances EXACTLY on its own.
#
# It was also chronologically impossible — usage dated 14 March 2024 against a
# one-year reservation purchased 1 July 2026, two years later.
#
# **This is the production hazard, not a fixture curiosity.** Commitment IDs
# genuinely recur across accounts, subscriptions and billing scopes, and any
# commitment analysis that groups on the ID alone silently absorbs rows it did
# not intend. Here it is 0.10 on 74.40. At enterprise scale it is whatever the
# neighbouring rows happen to be, and the total still looks entirely plausible.
LEGACY_RESERVATION_ID   = "/providers/Microsoft.Capacity/reservationOrders/res-basv2-legacy-2023"
LEGACY_RESERVATION_NAME = "Basv2 1-year reserved capacity (2023 term)"

LEGACY_BILLING_PERIOD_START = datetime(2024, 3, 1)
LEGACY_BILLING_PERIOD_END   = datetime(2024, 4, 1)


def legacy_era_family():
    fixture = "legacy_era"
    rows = []

    base = dict(
        BillingAccountId=BILLING_ACCOUNT_ID, BillingAccountName=BILLING_ACCOUNT_NAME,
        SubAccountId=SUB_ACCOUNT_ID, SubAccountName=SUB_ACCOUNT_NAME,
        BillingCurrency=CURRENCY,
        BillingPeriodStart=LEGACY_BILLING_PERIOD_START,
        BillingPeriodEnd=LEGACY_BILLING_PERIOD_END,
        ProviderName=PROVIDER_NAME, PublisherName=PUBLISHER_NAME,
        InvoiceIssuerName=INVOICE_ISSUER_NAME,
        RegionId=REGION_ID, RegionName=REGION_NAME,
        ChargeCategory="Usage", ChargeFrequency="Usage-Based", ChargeClass=None,
        PricingCategory="Standard",
        # The §7 fallback sources. Root SkuMeter / SkuPriceDetails / PricingCurrency
        # / InvoiceId are ABSENT from this schema entirely — not null, absent.
        x_SkuMeterName="B2ats v2",
        x_PricingCurrency=CURRENCY,
        x_InvoiceId="INV-2024-03-0001",
        x_ResourceGroupName=RESOURCE_GROUP,
    )

    # --- Hourly compute, 08:00-15:59 on 14 March 2024 -----------------------
    for hour in range(8, 16):
        rows.append(new_row(fixture, era=SCHEMA_ERA_LEGACY, **base,
            ChargeDescription="Basv2 Series compute, hourly (legacy export)",
            ChargePeriodStart=datetime(2024, 3, 14, hour),
            ChargePeriodEnd=datetime(2024, 3, 14, hour + 1),
            ServiceName=SERVICES["vm"][0], ServiceCategory=SERVICES["vm"][1],
            # ServiceSubcategory does not exist at 1.0 — introduced at 1.1.
            BilledCost=money("0.15"), EffectiveCost=money("0.15"),
            ListCost=money("0.15"), ContractedCost=money("0.15"),
            ListUnitPrice=money("0.15"), ContractedUnitPrice=money("0.15"),
            ConsumedQuantity=money(1), ConsumedUnit="Hours",
            PricingQuantity=money(1), PricingUnit="Hours",
            SkuId="DZH318Z0BQ35", SkuPriceId="DZH318Z0BQ35/00CV",
            x_SkuDetails=json_string({"InstanceType": "B2ats_v2", "CoreCount": 2}),
            ResourceId=RESERVED_VM_ID, ResourceName="vm-web-01",
            ResourceType="Microsoft.Compute/virtualMachines",
            Tags=RESERVATION_TAGS,
        ))

    # --- Legacy storage, daily ---------------------------------------------
    storage_base = dict(base)
    storage_base.update(x_SkuMeterName="Hot LRS Data Stored")
    rows.append(new_row(fixture, era=SCHEMA_ERA_LEGACY, **storage_base,
        ChargeDescription="Blob storage capacity, daily (legacy export)",
        ChargePeriodStart=datetime(2024, 3, 14), ChargePeriodEnd=datetime(2024, 3, 15),
        ServiceName=SERVICES["storage"][0], ServiceCategory=SERVICES["storage"][1],
        BilledCost=money("0.24"), EffectiveCost=money("0.24"),
        ListCost=money("0.24"), ContractedCost=money("0.24"),
        ListUnitPrice=money("0.01"), ContractedUnitPrice=money("0.01"),
        ConsumedQuantity=money(24), ConsumedUnit="GiB",
        PricingQuantity=money(24), PricingUnit="GiB",
        SkuId="DZH318Z0BQ4M", SkuPriceId="DZH318Z0BQ4M/002T",
        x_SkuDetails=json_string({"StorageClass": "Hot", "Redundancy": "Local"}),
        ResourceId=f"{SUB_ACCOUNT_ID}/resourceGroups/{RESOURCE_GROUP}"
                   "/providers/Microsoft.Storage/storageAccounts/stp1sandbox",
        ResourceName="stp1sandbox", ResourceType="Microsoft.Storage/storageAccounts",
        Tags=RESERVATION_TAGS,
    ))

    # --- A legacy commitment row -------------------------------------------
    # CommitmentDiscountId and Status existed by 1.0, but Quantity and Unit did
    # NOT (both 1.1). So a 1.0 export can tell you a commitment was APPLIED but
    # not HOW MUCH of it was consumed. Utilisation is unanswerable at 1.0 —
    # a concrete, costly example of what the version gap actually denies you.
    commitment_base = dict(base)
    commitment_base.update(PricingCategory="Committed")
    rows.append(new_row(fixture, era=SCHEMA_ERA_LEGACY, **commitment_base,
        ChargeDescription="Basv2 compute covered by reservation (legacy export)",
        ChargePeriodStart=datetime(2024, 3, 14, 16), ChargePeriodEnd=datetime(2024, 3, 14, 17),
        ServiceName=SERVICES["vm"][0], ServiceCategory=SERVICES["vm"][1],
        BilledCost=money(0), EffectiveCost=money("0.10"),
        ListCost=money("0.15"), ContractedCost=money("0.10"),
        ListUnitPrice=money("0.15"), ContractedUnitPrice=money("0.10"),
        ConsumedQuantity=money(1), ConsumedUnit="Hours",
        PricingQuantity=money(1), PricingUnit="Hours",
        # F33: its own commitment, not the 2026 one. The purchase row for this
        # reservation is deliberately NOT in the dataset — it was bought in 2023,
        # before this export window. That is the ordinary case for legacy data,
        # and the harness reports it as such rather than as an imbalance.
        CommitmentDiscountId=LEGACY_RESERVATION_ID,
        CommitmentDiscountName=LEGACY_RESERVATION_NAME,
        CommitmentDiscountType="Reserved Instance",
        CommitmentDiscountCategory="Usage",
        CommitmentDiscountStatus="Used",
        # CommitmentDiscountQuantity / Unit absent at 1.0 — cannot be recorded.
        SkuId="DZH318Z0BQ35", SkuPriceId="DZH318Z0BQ35/00CV",
        x_SkuDetails=json_string({"InstanceType": "B2ats_v2", "CoreCount": 2}),
        ResourceId=RESERVED_VM_ID, ResourceName="vm-web-01",
        ResourceType="Microsoft.Compute/virtualMachines",
        Tags=RESERVATION_TAGS,
    ))

    return rows



# =============================================================================
# 6g. FIXTURE — NEGATIVE TESTS  (chunk 6)
# =============================================================================
# Rows that are DELIBERATELY WRONG, each breaking exactly one rule.
#
# Why this file has to exist: a conformance harness that only ever runs against
# valid data always passes, and a test that cannot fail proves nothing. These
# rows are the evidence that the Stage 4 checks actually detect anything.
#
# ** THIS FILE MUST NEVER BE MERGED INTO focus_unified. **
# It is written separately, flagged separately, and excluded by name. Every row
# carries x_ExpectedViolation naming the rule it breaks, so the harness can
# assert that a SPECIFIC check catches a SPECIFIC row — not merely that
# something, somewhere, failed.
#
# Each row is otherwise entirely valid. One fault per row, isolated, so a failure
# points at one rule rather than a fog of them.


def negative_row(violation, detail, **values):
    """Build a deliberately non-conformant row.

    Separate from new_row() on purpose: the conformance defaults in new_row()
    would quietly repair some of these violations, which is exactly what they are
    for and exactly what must not happen here.
    """
    row = {column: None for column in NEGATIVE_COLUMNS}
    row.update(values)
    row["x_Synthetic"] = True
    row["x_SchemaEra"] = SCHEMA_ERA_DEFAULT
    row["x_FixtureId"] = "negative"
    row["x_ExpectedViolation"] = violation
    row["x_ViolationDetail"] = detail
    return row


def negative_family():
    """Fourteen rows, fourteen distinct rule violations."""

    # A valid baseline. Each fixture below copies this and breaks ONE thing.
    def valid(**overrides):
        row = dict(
            BillingAccountId=BILLING_ACCOUNT_ID,
            BillingAccountName=BILLING_ACCOUNT_NAME,
            BillingAccountType=BILLING_ACCOUNT_TYPE,
            SubAccountId=SUB_ACCOUNT_ID, SubAccountName=SUB_ACCOUNT_NAME,
            SubAccountType=SUB_ACCOUNT_TYPE,
            BillingCurrency=CURRENCY, PricingCurrency=CURRENCY,
            BillingPeriodStart=BILLING_PERIOD_START,
            BillingPeriodEnd=BILLING_PERIOD_END,
            ProviderName=PROVIDER_NAME, PublisherName=PUBLISHER_NAME,
            InvoiceIssuerName=INVOICE_ISSUER_NAME,
            ChargeCategory="Usage", ChargeFrequency="Usage-Based", ChargeClass=None,
            ChargeDescription="Basv2 Series compute, hourly",
            ChargePeriodStart=datetime(2026, 7, 15),
            ChargePeriodEnd=datetime(2026, 7, 16),
            ServiceName=SERVICES["vm"][0], ServiceCategory=SERVICES["vm"][1],
            ServiceSubcategory="Virtual Machines",
            RegionId=REGION_ID, RegionName=REGION_NAME,
            BilledCost=money("3.60"), EffectiveCost=money("3.60"),
            ListCost=money("3.60"), ContractedCost=money("3.60"),
            PricingCurrencyEffectiveCost=money("3.60"),
            # STAGE 4, FINDING F31. These two were absent from the baseline, so
            # they were null on every row in the file — breaching "MUST NOT be
            # null when ChargeCategory is Usage or Purchase and ChargeClass is
            # not Correction" twelve times over, on top of the fourteen planted
            # faults.
            #
            # Harmless in itself: the file is meant to be broken. The damage was
            # to the MEASUREMENT. The first Stage 4 proving run reported 14 of 14
            # caught, because a row-level match credited the harness for spotting
            # an unrelated null three columns away (finding F30). An undocumented
            # breach is indistinguishable from a planted one to any measure that
            # does not name the rule.
            PricingCurrencyContractedUnitPrice=money("0.15"),
            PricingCurrencyListUnitPrice=money("0.15"),
            PricingCategory="Standard",
            ListUnitPrice=money("0.15"), ContractedUnitPrice=money("0.15"),
            ConsumedQuantity=money(24), ConsumedUnit="Hours",
            PricingQuantity=money(24), PricingUnit="Hours",
            SkuId="DZH318Z0BQ35", SkuPriceId="DZH318Z0BQ35/00CV",
            SkuMeter="Basv2 Series", x_SkuMeterName="B2ats v2",
            ResourceId=RESERVED_VM_ID, ResourceName="vm-web-01",
            ResourceType="Microsoft.Compute/virtualMachines",
            x_ResourceGroupName=RESOURCE_GROUP, Tags=RESERVATION_TAGS,
        )
        row.update(overrides)
        return row

    fixtures = [
        ("NULL_IN_MANDATORY_COLUMN",
         "ServiceCategory is null; spec: MUST NOT be null",
         dict(ServiceCategory=None)),

        ("EMPTY_STRING_PLACEHOLDER",
         "ServiceSubcategory is '' instead of a value; StringHandling: empty "
         "strings SHOULD NOT be used in not-nullable string columns. This is the "
         "real Azure defect from Stage 2 finding F2, reproduced deliberately.",
         dict(ServiceSubcategory="")),

        ("INVALID_ENUM_VALUE",
         "ChargeCategory 'Consumption' is not an allowed value "
         "(Usage/Purchase/Tax/Credit/Adjustment)",
         # STAGE 4, FINDING F31. ConsumedQuantity MUST be null when
         # ChargeCategory is not "Usage", and "Consumption" is not "Usage", so
         # the invalid enum was CASCADING into a second violation on the same
         # row. A real consequence, but not the planted one, and it made this row
         # test two things at once.
         #
         # The same shape as finding F32 in miniature: one defect firing rules it
         # did not break, and the rule it fires is not the rule that is wrong.
         dict(ChargeCategory="Consumption",
              ConsumedQuantity=None, ConsumedUnit=None)),

        ("INVALID_CHARGECLASS_VALUE",
         "ChargeClass 'Adjustment'; spec: MUST be 'Correction' when not null",
         dict(ChargeClass="Adjustment")),

        ("SATELLITE_WITHOUT_ANCHOR",
         "ResourceName populated while ResourceId is null; spec: ResourceName "
         "MUST be null when ResourceId is null",
         dict(ResourceId=None, ResourceType=None)),

        ("TAX_WITH_PRICING_CATEGORY",
         "Tax row carries PricingCategory; spec: MUST be null when "
         "ChargeCategory is 'Tax'",
         # STAGE 4, FINDING F31. This row previously broke SEVEN rules, not one.
         # A Tax row must null ContractedUnitPrice, ListUnitPrice, PricingQuantity,
         # SkuId, SkuPriceId and PricingCategory, and ConsumedQuantity must be
         # null whenever ChargeCategory is not "Usage" — and it inherited all of
         # them populated from the Usage baseline above.
         #
         # It was a Tax row built from a Usage template. Contrary to this
         # fixture's own stated contract: one fault per row, isolated, so a
         # failure points at one rule rather than a fog of them.
         #
         # Everything the Tax rules require to be null is now null, leaving
         # PricingCategory as the single planted fault. The dependent columns go
         # with their anchors — PricingUnit follows PricingQuantity, ConsumedUnit
         # follows ConsumedQuantity, SkuMeter follows SkuId — or nulling the
         # anchor would simply plant a different fault in place of the old one.
         dict(ChargeCategory="Tax", ChargeFrequency="One-Time",
              PricingCategory="Standard", ServiceName="Tax",
              ServiceCategory="Other", ServiceSubcategory="Other (Other)",
              ConsumedQuantity=None, ConsumedUnit=None,
              PricingQuantity=None, PricingUnit=None,
              ContractedUnitPrice=None, ListUnitPrice=None,
              PricingCurrencyContractedUnitPrice=None,
              PricingCurrencyListUnitPrice=None,
              SkuId=None, SkuPriceId=None, SkuMeter=None)),

        ("PURCHASE_WITH_USAGE_BASED_FREQUENCY",
         "spec: ChargeFrequency MUST NOT be 'Usage-Based' when ChargeCategory "
         "is 'Purchase'",
         # STAGE 4, FINDING F31. ConsumedQuantity MUST be null when
         # ChargeCategory is not "Usage". This is a Purchase row, so the
         # populated ConsumedQuantity inherited from the baseline was a second,
         # genuinely separate fault — not a consequence of the planted one.
         dict(ChargeCategory="Purchase", ChargeFrequency="Usage-Based",
              EffectiveCost=money(0),
              ConsumedQuantity=None, ConsumedUnit=None)),

        ("NEGATIVE_UNIT_PRICE",
         "ListUnitPrice -0.15; spec: MUST be a non-negative decimal value",
         # STAGE 4, CHUNK 4. ListCost moves with the price. Negating the unit
         # price alone broke a SECOND rule as a side effect — the product of
         # ListUnitPrice and PricingQuantity no longer matched ListCost — so the
         # row tested two things and only named one.
         #
         # A negative ListCost is perfectly legal: the spec requires unit PRICES
         # to be non-negative and says nothing of the sort about costs, which is
         # what makes credits and rebates expressible at all. So -3.60 keeps the
         # row internally consistent and leaves the negative unit price as the
         # single planted fault.
         #
         # Third instance of the same shape in this file, after the Tax row and
         # the invalid enum: one defect firing rules it did not break.
         dict(ListUnitPrice=money("-0.15"), ListCost=money("-3.60"))),

        ("UNIT_PRICE_COST_MISMATCH",
         "PricingQuantity 24 x ContractedUnitPrice 0.15 = 3.60, but "
         "ContractedCost says 9.99; spec: the product MUST match",
         dict(ContractedCost=money("9.99"))),

        ("ORPHAN_COMMITMENT_STATUS",
         "CommitmentDiscountStatus set while CommitmentDiscountId is null; "
         "spec: MUST be null when CommitmentDiscountId is null",
         dict(CommitmentDiscountStatus="Used")),

        ("ORPHAN_CAPACITY_RESERVATION_STATUS",
         "CapacityReservationStatus set while CapacityReservationId is null; "
         "spec: MUST be null when CapacityReservationId is null",
         dict(CapacityReservationStatus="Used")),

        ("SKU_PRICE_DETAILS_BAD_KEYS",
         "'MemoryGB' is not the FOCUS-defined key (MemorySize is), and "
         "'AcceleratedNetworking' is provider-defined but lacks the required "
         "x_ prefix. Build spec section 8's standing trap, as data.",
         dict(SkuPriceDetails=json_string({
             "MemoryGB": 1, "AcceleratedNetworking": False, "CoreCount": 2}))),

        ("CURRENCY_NOT_ISO_4217",
         "BillingCurrency 'US Dollars'; CurrencyFormat: MUST be a three-letter "
         "alphabetic ISO 4217 code for national currency",
         dict(BillingCurrency="US Dollars", PricingCurrency="US Dollars")),

        ("CHARGE_PERIOD_INVERTED",
         "ChargePeriodEnd precedes ChargePeriodStart; spec: start is the "
         "inclusive start bound and end the exclusive end bound",
         dict(ChargePeriodStart=datetime(2026, 7, 16),
              ChargePeriodEnd=datetime(2026, 7, 15))),
    ]

    return [negative_row(violation, detail, **valid(**overrides))
            for violation, detail, overrides in fixtures]


# =============================================================================
# 7. RUN
# =============================================================================

if __name__ == "__main__":
    print("=" * 68)
    print("seed_data.py — chunks 0-7: fixtures, three layers, Azure-shaped manifests")
    print("=" * 68)

    print(f"\nProject root : {PROJECT_ROOT}")
    print(f"Data folder  : {DATA_DIR}")

    # --- the schema -------------------------------------------------------
    print("\nColumn set:")
    print(f"  FOCUS v1.2 columns (verified at tag v1.2) : {len(COLUMNS_V12)}")
    print(f"  Azure x_ columns carried across           : {len(COLUMNS_X_CARRIED)}")
    print(f"  x_ columns invented for fixtures          : {len(COLUMNS_X_FIXTURE)}")
    print(f"  Provenance columns                        : {len(COLUMNS_PROVENANCE)}")
    print(f"  TOTAL                                     : {len(ALL_COLUMNS)}")

    type_counts = {}
    for _, spec_type, _ in ALL_COLUMN_SPECS:
        type_counts[spec_type] = type_counts.get(spec_type, 0) + 1
    print("\nDeclared types:")
    for spec_type, count in sorted(type_counts.items()):
        print(f"  {spec_type:<10} x{count:<3} -> {TYPE_MAP[spec_type]}")

    print(f"\nNot-nullable per spec ({len(NOT_NULLABLE)} columns):")
    print("  " + ", ".join(NOT_NULLABLE))

    # --- the row factory --------------------------------------------------
    print("\n" + "-" * 68)
    print("Row factory check")
    print("-" * 68)

    demo = new_row(
        "chunk0_demo",
        ChargeCategory="Usage",
        ChargeFrequency="Usage-Based",
        ServiceName=SERVICES["vm"][0],
        ServiceCategory=SERVICES["vm"][1],
        ServiceSubcategory="Virtual Machines",
        BillingCurrency=CURRENCY,
        BilledCost=money("0.20747059"),
        EffectiveCost=money("0.20747059"),
        ListCost=money("0.20747059"),
        ContractedCost=money("0.20747059"),
        RegionId=REGION_ID,
        RegionName=REGION_NAME,
        Tags=json_string({"team": "platform", "environment": "production"}),
    )
    filled = [k for k, v in demo.items() if v is not None]
    print(f"  Row built with {len(demo)} columns; {len(filled)} filled, "
          f"{len(demo) - len(filled)} true nulls.")
    print(f"  x_Synthetic={demo['x_Synthetic']}  "
          f"x_SchemaEra={demo['x_SchemaEra']}  x_FixtureId={demo['x_FixtureId']}")
    print(f"  Tags -> {demo['Tags']}")
    print(f"  BilledCost -> {demo['BilledCost']}  (type: {type(demo['BilledCost']).__name__})")

    # The typo guard, demonstrated rather than asserted.
    try:
        new_row("chunk0_demo", SkuMeterName="Basv2 Series VM")   # deliberate error
        print("  TYPO GUARD FAILED — a bad column name was accepted.")
    except KeyError as err:
        print(f"  Typo guard works: {err}")

    # --- write the empty, fully-typed file ---------------------------------
    print("\n" + "-" * 68)
    print("Writing")
    print("-" * 68)
    rows = (reservation_lifecycle() + charge_family() + pricing_family()
            + account_resource_sku_family())
    legacy_rows   = legacy_era_family()
    negative_rows = negative_family()

    absent = sorted({n for n, _, _ in COLUMNS_V12} - set(PRE12_COLUMNS))

    v12_path, v12_table, _ = write_layer(
        "v1.2", rows, SCHEMA, ALL_COLUMNS)
    legacy_path, legacy_table, _ = write_layer(
        "pre-1.2", legacy_rows, SCHEMA_PRE12, PRE12_COLUMNS,
        extra={"columnsAbsentVsV12": absent})
    neg_path, neg_table, _ = write_layer(
        "negative", negative_rows, SCHEMA_NEGATIVE, NEGATIVE_COLUMNS,
        extra={"excludeFromUnifiedView": True,
               "violations": sorted({r["x_ExpectedViolation"]
                                     for r in negative_rows})})

    for path, table, note in ((v12_path,    v12_table,    "era 1.2"),
                              (legacy_path, legacy_table, "era pre-1.2"),
                              (neg_path,    neg_table,    "NEGATIVE — never merged")):
        print(f"  {os.path.relpath(path, PROJECT_ROOT)}")
        print(f"      Rows: {table.num_rows}   Columns: {table.num_columns}   ({note})")
        print(f"      manifest.json written alongside")

    print("\n  Each folder holds a Parquet and an Azure-shaped manifest.json, so")
    print("  loader.py can be pointed at any of them and run UNCHANGED:")
    for key in LAYERS:
        print(f"      python3 loader.py "
              f"{os.path.relpath(LAYERS[key]['folder'], PROJECT_ROOT)}")

    # --- prove the reservation fixture closes -------------------------------
    # SCOPE MATTERS. The spec states, without qualification:
    #   "The sum of EffectiveCost where ChargeCategory is 'Usage' MUST equal the
    #    sum of BilledCost where ChargeCategory is 'Purchase'."
    # Read globally that cannot hold — any dataset containing ordinary on-demand
    # usage, or a correction to a prior period, breaks it immediately (see the
    # Stage 3 notes, finding F10). The invariant is real but it is COMMITMENT-
    # SCOPED: it closes within one commitment's term. So the assertion filters to
    # the reservation fixture. Getting the scope wrong is how a conformance test
    # produces a confident, wrong FAIL.
    res = [r for r in rows if r["x_FixtureId"] == "reservation_lifecycle"]

    print("\n" + "-" * 68)
    print("Reservation lifecycle — term closure (commitment-scoped)")
    print("-" * 68)

    purchased = sum(r["BilledCost"] for r in res if r["ChargeCategory"] == "Purchase")
    amortised = sum(r["EffectiveCost"] for r in res if r["ChargeCategory"] == "Usage")
    used      = sum(r["EffectiveCost"] for r in res
                    if r["CommitmentDiscountStatus"] == "Used")
    unused    = sum(r["EffectiveCost"] for r in res
                    if r["CommitmentDiscountStatus"] == "Unused")
    list_cost = sum(r["ListCost"] for r in res if r["ChargeCategory"] == "Usage")

    print(f"  Purchased (BilledCost, Purchase rows)  : {purchased:>10.2f}")
    print(f"  Amortised (EffectiveCost, Usage rows)  : {amortised:>10.2f}")
    print(f"    of which Used                        : {used:>10.2f}")
    print(f"    of which Unused (waste)              : {unused:>10.2f}")
    print(f"  Utilisation                            : {used / amortised:>10.1%}")
    print(f"  Savings vs on-demand list              : "
          f"{list_cost - amortised:>10.2f}  ({1 - amortised / list_cost:.1%})")

    print("\n  Spec MUSTs (FOCUS v1.2, effectivecost.md), within commitment scope:")
    print(f"    sum(Usage EffectiveCost) == sum(Purchase BilledCost)   "
          f"{'PASS' if amortised == purchased else 'FAIL'}")
    print(f"    Used + Unused == all Usage EffectiveCost               "
          f"{'PASS' if used + unused == amortised else 'FAIL'}")

    print(f"\n  The trap: BilledCost + EffectiveCost = {purchased + amortised:.2f} "
          f"— the same {purchased:.2f} counted twice.")

    # --- the charge family: what reconciles, what allocates ------------------
    # CURRENCY-SCOPED, per finding F14. An earlier version totalled every row
    # regardless of BillingCurrency and printed a hardcoded claim that the two
    # cost columns agree. Both were wrong: the totals mixed EUR with USD, and the
    # claim stopped being true the moment a third-party row was added. The panel
    # now COMPUTES the relationship instead of asserting one.
    print("\n" + "-" * 68)
    print("Charge family — the reconciliation panel (per billing currency)")
    print("-" * 68)

    for currency in sorted({r["BillingCurrency"] for r in rows}):
        book = [r for r in rows if r["BillingCurrency"] == currency]
        print(f"\n  {currency} — {len(book)} rows")
        print(f"    {'Category':<12}{'Rows':>6}{'BilledCost':>14}{'EffectiveCost':>16}")
        for category in ["Usage", "Purchase", "Tax", "Credit", "Adjustment"]:
            group = [r for r in book if r["ChargeCategory"] == category]
            if group:
                print(f"    {category:<12}{len(group):>6}"
                      f"{sum(r['BilledCost'] for r in group):>14.2f}"
                      f"{sum(r['EffectiveCost'] for r in group):>16.2f}")
        billed    = sum(r["BilledCost"] for r in book)
        effective = sum(r["EffectiveCost"] for r in book)
        print(f"    {'TOTAL':<12}{len(book):>6}{billed:>14.2f}{effective:>16.2f}")

        # The two columns are NOT expected to agree. The gap is explainable, and
        # explaining it exactly is the actual reconciliation:
        #   1. third-party charges  — BilledCost MUST be 0, EffectiveCost is not
        #   2. commitment timing    — purchase billed in one period, amortised
        #                             across others; nets to zero once the term closes
        third_party = sum(r["EffectiveCost"] for r in book
                          if r["PublisherName"] != r["ProviderName"])
        amortised   = sum(r["EffectiveCost"] for r in book
                          if r["ChargeCategory"] == "Usage"
                          and r["CommitmentDiscountId"] is not None)
        purchased   = sum(r["BilledCost"] for r in book
                          if r["ChargeCategory"] == "Purchase")
        timing      = amortised - purchased
        gap         = effective - billed

        print(f"\n    EffectiveCost - BilledCost      {gap:>10.2f}")
        print(f"      third-party charges (billed 0){third_party:>12.2f}")
        print(f"      commitment timing difference {timing:>13.2f}")
        print(f"      explained                    {third_party + timing:>13.2f}"
              f"   {'PASS' if gap == third_party + timing else 'FAIL'}")

        allocatable   = [r for r in book if r["ResourceId"] is not None]
        unallocatable = [r for r in book if r["ResourceId"] is None]
        print(f"\n    Allocation on EffectiveCost:")
        print(f"      allocatable to a resource  {len(allocatable):>4} rows "
              f"{sum(r['EffectiveCost'] for r in allocatable):>10.2f}")
        print(f"      reconciling items          {len(unallocatable):>4} rows "
              f"{sum(r['EffectiveCost'] for r in unallocatable):>10.2f}")

    print("\n  The two cost columns are NOT interchangeable and do NOT agree.")
    print("  Every difference above is accounted for, which is what reconciliation")
    print("  means: not that the numbers match, but that the gap is explained.")

    print("\n  Corrections:")
    flagged = [r for r in rows if r["ChargeClass"] == "Correction"]
    for r in flagged:
        print(f"    ChargeClass='Correction'  charge period "
              f"{r['ChargePeriodStart']:%Y-%m-%d}  billing period "
              f"{r['BillingPeriodStart']:%Y-%m}  {r['EffectiveCost']:>8.2f}")
    print("    A June-dated row inside a July file. June was already reported.")
    unflagged = [r for r in rows if r["ChargeClass"] is None
                 and r["EffectiveCost"] < 0 and r["ChargeCategory"] == "Usage"]
    for r in unflagged:
        print(f"    ChargeClass=NULL          charge period "
              f"{r['ChargePeriodStart']:%Y-%m-%d}  billing period "
              f"{r['BillingPeriodStart']:%Y-%m}  {r['EffectiveCost']:>8.2f}")
    print("    Also a correction — but within the current period, so the spec")
    print("    requires ChargeClass to be NULL. Filtering on 'Correction' misses it.")

    # --- the pricing family: what cannot safely be summed -------------------
    print("\n" + "-" * 68)
    print("Pricing family — currency, blocks and third parties")
    print("-" * 68)

    print("\n  Currencies present:")
    seen = {}
    for r in rows:
        key = (r["BillingCurrency"], r["PricingCurrency"])
        seen[key] = seen.get(key, 0) + 1
    for (billing, pricing), count in sorted(seen.items()):
        note = "" if billing == pricing else "   <- differs"
        print(f"    billed {billing:<4} priced {pricing:<12}{count:>4} rows{note}")

    naive = sum(r["EffectiveCost"] for r in rows)
    usd   = sum(r["EffectiveCost"] for r in rows if r["BillingCurrency"] == "USD")
    eur   = sum(r["EffectiveCost"] for r in rows if r["BillingCurrency"] == "EUR")
    print(f"\n    SUM(EffectiveCost) over everything : {naive:>8.2f}  <- MEANINGLESS")
    print(f"    USD only                          : {usd:>8.2f}")
    print(f"    EUR only                          : {eur:>8.2f}")
    print("    The first figure adds euros to dollars and still looks plausible.")

    print("\n  Block pricing — consumed vs priced:")
    for r in rows:
        if r["x_PricingBlockSize"] is not None:
            print(f"    consumed {r['ConsumedQuantity']:>8.0f} {r['ConsumedUnit']:<12}"
                  f"priced {r['PricingQuantity']:>4.0f} {r['PricingUnit']:<14}"
                  f"block {r['x_PricingBlockSize']:>6.0f}")
    print("    Whole blocks: 500 operations still costs a full block. Azure's real")
    print("    export emits FRACTIONAL blocks instead (finding F7) — a waste query")
    print("    has to handle both.")

    print("\n  BilledCost = 0 does not mean free:")
    zero_billed = [r for r in rows if r["BilledCost"] == 0 and r["EffectiveCost"] > 0]
    third_party = [r for r in zero_billed if r["PublisherName"] != r["ProviderName"]]
    covered     = [r for r in zero_billed if r["CommitmentDiscountId"] is not None]
    print(f"    {len(zero_billed)} rows bill zero but cost something. TWO different causes:")
    print(f"      {len(covered):>3} covered by a commitment already paid for upfront")
    print(f"      {len(third_party):>3} paid to a third party (marketplace)")
    for r in third_party:
        print(f"          {r['ChargeDescription'][:40]:<42}"
              f"effective {r['EffectiveCost']:>6.2f}  publisher {r['PublisherName']}")
    print("    Same zero, different reasons — and only one of them is on the invoice.")
    print("    PublisherName differs from ProviderName: that is how marketplace is found.")

    # --- identity, time and the SKU detail ----------------------------------
    print("\n" + "-" * 68)
    print("Account, resource and SKU — identity is not the same as name")
    print("-" * 68)

    fam = [r for r in rows if r["x_FixtureId"] == "account_resource_sku"]

    # Rename: one Id, several names. Grouping by name fragments the truth.
    print("\n  The rename — one identity, more than one name:")
    for column_id, column_name in (("SubAccountId", "SubAccountName"),
                                   ("ResourceId", "ResourceName")):
        by_id = {}
        for r in fam:
            if r[column_id] and r[column_name]:
                by_id.setdefault(r[column_id], set()).add(r[column_name])
        for identity, names in by_id.items():
            if len(names) > 1:
                print(f"    {column_id:<14} ...{identity[-28:]}")
                print(f"      {column_name} seen as: {sorted(names)}")
    print("    GROUP BY the Id column; carry the name for display only.")
    print("    Grouping by name would report one VM as two, each at half the cost.")

    groups = {r["x_ResourceGroupName"] for r in fam if r["x_ResourceGroupName"]}
    print(f"\n  Resource group casing: {sorted(groups)}")
    print("    Two spellings of one group — deliberate here, and already real in")
    print("    the Azure export (finding F9). Normalise case before grouping.")

    # SkuPriceDetails: 13 FOCUS-defined properties, spread across applicable SKUs.
    focus_sku_properties = {
        "CoreCount", "DiskMaxIops", "DiskSpace", "DiskType", "GpuCount",
        "InstanceType", "InstanceSeries", "MemorySize", "NetworkMaxIops",
        "NetworkMaxThroughput", "OperatingSystem", "Redundancy", "StorageClass",
    }
    seen_properties, provider_keys = set(), set()
    for r in fam:
        if r["SkuPriceDetails"]:
            for key in json.loads(r["SkuPriceDetails"]):
                (provider_keys if key.startswith("x_") else seen_properties).add(key)
    print(f"\n  SkuPriceDetails coverage: {len(seen_properties)}/13 FOCUS-defined "
          f"properties, {len(provider_keys)} provider-defined (x_)")
    missing = focus_sku_properties - seen_properties
    unknown = seen_properties - focus_sku_properties
    print(f"    all 13 covered   {'PASS' if not missing else 'FAIL ' + str(missing)}")
    print(f"    no invented keys {'PASS' if not unknown else 'FAIL ' + str(unknown)}")
    print("    Spread across two SKUs on purpose: the spec forbids listing")
    print("    properties that do not apply to the SKU, so no single row has 13.")

    # Nulls that mean something, not nulls that are missing.
    nameless = [r for r in fam if r["ResourceId"] and not r["ResourceName"]]
    print(f"\n  Conformant nulls:")
    print(f"    {len(nameless)} row(s) with ResourceId but no ResourceName "
          f"— resource has no display name, which the spec allows.")
    uninvoiced = [r for r in fam if r["InvoiceId"] is None]
    invoiced   = [r for r in fam if r["InvoiceId"] is not None]
    print(f"    {len(uninvoiced)} row(s) with no InvoiceId, {len(invoiced)} with one "
          f"— 'not yet invoiced', not missing data.")

    # Half-open intervals across the month boundary.
    spillover = [r for r in rows if r["ChargePeriodEnd"] > datetime(2026, 8, 1)
                 or (r["ChargePeriodEnd"] == datetime(2026, 8, 1))]
    print(f"\n  Month boundary: {len(spillover)} row(s) end at 2026-08-01 00:00 "
          f"while belonging to July.")
    print("    ChargePeriodEnd is EXCLUSIVE. Filter with >= start AND < end;")
    print("    BETWEEN either drops these rows or double-counts them.")

    # --- the legacy era: the version gap, measured -------------------------
    print("\n" + "-" * 68)
    print("Legacy era (pre-1.2) — the FOCUS version gap, measured")
    print("-" * 68)

    absent = sorted({n for n, _, _ in COLUMNS_V12} - set(PRE12_COLUMNS))
    print(f"\n  Columns in the v1.2 file  : {len(ALL_COLUMNS)}")
    print(f"  Columns in the legacy file: {len(PRE12_COLUMNS)}")
    print(f"  FOCUS columns unavailable at 1.0: {len(absent)} of {len(COLUMNS_V12)} "
          f"({len(absent) / len(COLUMNS_V12):.0%} of the specification)")
    for name in absent:
        print(f"    {name:<36} introduced at {INTRODUCED[name]}")

    print("\n  The build-spec §7 fallbacks, and why they exist:")
    for root, x_column in (("SkuMeter", "x_SkuMeterName"),
                           ("SkuPriceDetails", "x_SkuDetails"),
                           ("PricingCurrency", "x_PricingCurrency"),
                           ("InvoiceId", "x_InvoiceId")):
        filled = sum(1 for r in legacy_rows if r.get(x_column) is not None)
        print(f"    {root:<16} absent (introduced {INTRODUCED[root]})"
              f" <- {x_column:<20} {filled}/{len(legacy_rows)} rows")
    print("    Every fallback target is a column introduced AFTER 1.0. The loader's")
    print("    coalesce() map is not arbitrary — it is the version gap, in code.")

    print("\n  What the gap actually costs you:")
    covered = [r for r in legacy_rows if r["CommitmentDiscountId"] is not None]
    print(f"    {len(covered)} legacy row(s) show a commitment was APPLIED"
          f" (CommitmentDiscountStatus).")
    print(f"    None can show HOW MUCH was consumed: CommitmentDiscountQuantity and")
    print(f"    CommitmentDiscountUnit were introduced at 1.1.")
    print("    Commitment utilisation is unanswerable at 1.0 — not hard, impossible.")

    grains = {(r["ChargePeriodEnd"] - r["ChargePeriodStart"]) for r in legacy_rows}
    print(f"\n  Granularity in the legacy file: "
          f"{sorted(str(g) for g in grains)}")
    print("    Hourly and daily rows together. Row counts are not comparable across")
    print("    eras; only money is.")

    # --- the negative fixtures: proof the checks can fail -------------------
    print("\n" + "-" * 68)
    print("Negative fixtures — one broken rule per row")
    print("-" * 68)
    print("\n  Written to data/negative/, NOT data/synthetic/. Never merged into")
    print("  focus_unified. A harness that only sees valid data always passes,")
    print("  and a test that cannot fail proves nothing.")

    print(f"\n  {len(negative_rows)} rows, {len(negative_rows)} distinct violations:")
    for r in negative_rows:
        print(f"    {r['x_ExpectedViolation']}")

    # Each row must break exactly ONE rule. Verify by diffing against the
    # baseline: a row differing in many columns would confound the harness.
    print("\n  One fault per row (isolated):")
    unique = len({r["x_ExpectedViolation"] for r in negative_rows})
    print(f"    distinct violation labels    {unique}/{len(negative_rows)}   "
          f"{'PASS' if unique == len(negative_rows) else 'FAIL'}")

    # And the violations must actually BE violations — spot-check the ones a
    # simple rule can confirm, so this panel is computed and not narrated (F14).
    checks = [
        ("NULL_IN_MANDATORY_COLUMN",
         lambda r: r["ServiceCategory"] is None),
        ("EMPTY_STRING_PLACEHOLDER",
         lambda r: r["ServiceSubcategory"] == ""),
        ("INVALID_ENUM_VALUE",
         lambda r: r["ChargeCategory"] not in
                   {"Usage", "Purchase", "Tax", "Credit", "Adjustment"}),
        ("INVALID_CHARGECLASS_VALUE",
         lambda r: r["ChargeClass"] not in (None, "Correction")),
        ("SATELLITE_WITHOUT_ANCHOR",
         lambda r: r["ResourceId"] is None and r["ResourceName"] is not None),
        ("TAX_WITH_PRICING_CATEGORY",
         lambda r: r["ChargeCategory"] == "Tax" and r["PricingCategory"] is not None),
        ("PURCHASE_WITH_USAGE_BASED_FREQUENCY",
         lambda r: r["ChargeCategory"] == "Purchase"
                   and r["ChargeFrequency"] == "Usage-Based"),
        ("NEGATIVE_UNIT_PRICE",
         lambda r: r["ListUnitPrice"] < 0),
        ("UNIT_PRICE_COST_MISMATCH",
         lambda r: r["PricingQuantity"] * r["ContractedUnitPrice"]
                   != r["ContractedCost"]),
        ("ORPHAN_COMMITMENT_STATUS",
         lambda r: r["CommitmentDiscountId"] is None
                   and r["CommitmentDiscountStatus"] is not None),
        ("ORPHAN_CAPACITY_RESERVATION_STATUS",
         lambda r: r["CapacityReservationId"] is None
                   and r["CapacityReservationStatus"] is not None),
        ("CURRENCY_NOT_ISO_4217",
         lambda r: len(r["BillingCurrency"]) != 3),
        ("CHARGE_PERIOD_INVERTED",
         lambda r: r["ChargePeriodEnd"] <= r["ChargePeriodStart"]),
    ]
    by_label = {r["x_ExpectedViolation"]: r for r in negative_rows}
    confirmed = 0
    for label, test in checks:
        row = by_label.get(label)
        ok = row is not None and test(row)
        confirmed += ok
        if not ok:
            print(f"    NOT ACTUALLY BROKEN: {label}")
    print(f"    violations confirmed present {confirmed}/{len(checks)}   "
          f"{'PASS' if confirmed == len(checks) else 'FAIL'}")
    print("    (SKU_PRICE_DETAILS_BAD_KEYS needs the spec key list; asserted in")
    print("     the chunk 8 self-test rather than duplicated here.)")

    # --- the writer: determinism and the manifest ---------------------------
    print("\n" + "-" * 68)
    print("Output — three layers, three manifests, reproducible")
    print("-" * 68)

    print("\n  Each layer folder mirrors an Azure export run: one Parquet plus a")
    print("  manifest.json carrying the same top-level keys Azure emits")
    print("  (manifestVersion, byteCount, dataRowCount, exportConfig, runInfo,")
    print("  blobs). Everything generator-specific sits under a 'generator' key,")
    print("  which the loader ignores — extending a format safely.")

    print(f"\n  {'layer':<10}{'rows':>6}{'cols':>6}{'bytes':>9}"
          f"  {'contentSha256':<14}{'fileSha256'}")
    for key, path, table, layer_rows in (
            ("v1.2",     v12_path,    v12_table,    rows),
            ("pre-1.2",  legacy_path, legacy_table, legacy_rows),
            ("negative", neg_path,    neg_table,    negative_rows)):
        with open(path, "rb") as f:
            file_digest = hashlib.sha256(f.read()).hexdigest()
        content_digest = content_checksum(layer_rows, list(layer_rows[0]))
        print(f"  {key:<10}{table.num_rows:>6}{table.num_columns:>6}"
              f"{os.path.getsize(path):>9}  {content_digest[:12]:<14}"
              f"{file_digest[:12]}")

    print(f"\n  pyarrow {pa.__version__}")
    print("  TWO checksums, because they answer different questions (finding F20):")
    print("    contentSha256  the DATA. Stable on any machine, any pyarrow version.")
    print("                   This is the reproducibility number.")
    print("    fileSha256     the BYTES. Stable only within one environment —")
    print("                   Parquet encodes differently between library versions.")
    print("  No randomness anywhere, so the same script always produces the same")
    print("  dataset. That is what makes the GENERATOR the artifact and the")
    print("  Parquet merely its output.")

    print("\nChunks 0-7 complete.")
