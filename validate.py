"""
validate.py — Portfolio Project 1, Stage 4 chunk 2

THE HARNESS SKELETON.

Chunk 1 turned the specification into data. This is the machine that runs rules
against the datasets: what a check IS, which rows it is allowed to look at,
which datasets it is allowed to touch, and how its result is scored.

Almost no rules are registered yet — one family, so the wiring can be proven to
carry current from a sentence in the spec all the way to a caught violation in
data/negative/. Chunks 3 to 7 add the rest.

FOUR THINGS THIS FILE EXISTS TO GET RIGHT
-----------------------------------------

1. SEVERITY COMES FROM THE SPEC, NOT FROM A HUMAN.
   Every check cites a requirement sentence parsed in chunk 1, and takes that
   sentence's RFC 2119 severity. MUST -> FAIL, SHOULD -> WARN. Nobody sits down
   and decides which checks are important. That is the F2 refinement built in
   from the start rather than retrofitted, and it is why a check cannot be
   registered without a citation.

2. ERA IS A PROPERTY OF THE ROW, NOT OF THE FOLDER.
   In Stage 3's self_test.py a whole folder was one era, so the era gate sat at
   the top of the run. focus_unified holds THREE eras in one table, so the gate
   moves down to the row. A rule about PricingCurrency, introduced at 1.2,
   cannot be applied to a 1.0r2 row: the column did not exist to be wrong.
   Applying it anyway produces confident, wrong failures on 128 of your 204 rows.

3. A CHECK KNOWS THE VERSION RANGE IN WHICH IT CAN BE EXPRESSED AT ALL.
   Finding F22: ProviderName and PublisherName were REMOVED at v1.4. So checks
   have two horizons, not one — the earliest tag where every column they read
   exists, and the earliest tag where one of those columns is gone. The second
   horizon is what the INTRODUCED map alone cannot give you, and it is why
   chunk 1 computes REMOVED.

4. BINDING IS ENFORCED IN CODE, NOT BY CONVENTION.
   Handover guardrail 1: the empty-string sweep binds to the per-layer views,
   NEVER to focus_unified, because decision D3 normalises '' to NULL there and
   the sweep would "prove" Azure is clean. A comment saying so is not a control.
   A check declares its binding, and a check bound per-layer is never even
   HANDED the unified rows.

Run:  python3 validate.py                 validate everything discoverable
      python3 validate.py --negative      the proving run only
      python3 validate.py --list          registered checks and their horizons

Exit code 0 when no MUST is broken on the clean data, 1 otherwise.
Reads docs/spec/*.json from chunk 1. Never touches the network.
"""

import argparse
import glob
import json
import os
import re
import sys
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal

import duckdb

import rules

# --- module handshake --------------------------------------------------------
# validate.py and rules.py are a matched pair. If only one gets replaced, the
# failure lands deep inside a check as an AttributeError, which looks like a
# defect in the harness instead of a file that was not copied across. Checked
# here, once, in words.
REQUIRED_RULES_VERSION = 4
_have = getattr(rules, "RULES_VERSION", 0)
if _have < REQUIRED_RULES_VERSION:
    raise SystemExit(
        f"\nrules.py is out of date: this validate.py needs RULES_VERSION "
        f">= {REQUIRED_RULES_VERSION}, found {_have or 'none'}.\n"
        f"Replace rules.py with the version shipped alongside this file.\n"
        f"If you have already replaced it, delete __pycache__/ and re-run — a "
        f"stale .pyc can shadow the new source.\n")

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE) if os.path.basename(HERE) == "src" else HERE

SPEC_DIR = os.path.join(ROOT, "docs", "spec")
DATA = os.path.join(ROOT, "data")


# =============================================================================
# 1. VERSION ORDERING
# =============================================================================
# FOCUS versions are not numbers and they do not sort as text: "1.0-preview"
# comes BEFORE "1.0", and "1.10" would sort before "1.3" alphabetically. So the
# order is declared once, explicitly, and every comparison goes through it.

VERSION_ORDER = ["0.5", "1.0-preview", "1.0", "1.0r2", "1.1", "1.2", "1.3", "1.4"]


def vkey(version):
    """Position of a version in the release order. Unknown versions sort last."""
    if version in VERSION_ORDER:
        return VERSION_ORDER.index(version)
    return len(VERSION_ORDER)


# The x_SchemaEra values that appear in the data, mapped to the FOCUS version
# whose columns those rows may contain.
#
#   1.0r2    Azure's real export. Azure labels it FOCUS 1.0 revision 2.
#   pre-1.2  the simulated legacy layer (Amendment 1 A2). seed_data.py builds it
#            from columns introduced at 1.0 and earlier, so 1.0 is its ceiling.
#   1.2      the synthetic enrichment layer.
#
# Read this as a CEILING, not a label: a row of era 1.0r2 may contain any column
# introduced at or before 1.0, and may not contain any introduced after.
ERA_CEILING = {
    "1.0r2":   "1.0",
    "pre-1.2": "1.0",
    "1.2":     "1.2",
}


def era_supports(era, column, lifecycle):
    """Could a row of this era legitimately carry this column?

    False for two different reasons, and the harness should not confuse them:
      - the column had not been introduced yet   (era is older than INTRODUCED)
      - the column had already been removed      (era is at or after REMOVED)
    Both mean "do not apply this rule to this row". Only the second is F22.
    """
    ceiling = ERA_CEILING.get(era)
    if ceiling is None:
        return False
    introduced = lifecycle["introduced"].get(column)
    if introduced is None:
        return False
    if vkey(introduced) > vkey(ceiling):
        return False
    removed = lifecycle["removed"].get(column)          # e.g. "v1.4"
    if removed and vkey(ceiling) >= vkey(removed.lstrip("v")):
        return False
    return True


# =============================================================================
# 2. WHAT A CHECK IS
# =============================================================================

FAIL, WARN, INFO = "FAIL", "WARN", "INFO"

# Binding: which datasets a check is permitted to run against.
#   ANY         no restriction
#   PER_LAYER   per-layer views only. NEVER focus_unified. This is guardrail 1:
#               D3 normalises '' to NULL in the unified view, so a sweep run
#               there reports zero and looks like a pass.
#   UNIFIED     cross-layer only — checks that need rows from more than one era
#               in the same table to mean anything.
# Era mode: what "era-aware" actually means for a given rule. It turns out to
# mean two different things, and collapsing them produces a silent false
# negative. See finding F27.
#
#   ERA_REQUIREMENT   the rule REQUIRES something — presence, non-nullness, a
#                     cascade. Gate it by the row's declared era: you cannot
#                     require a column that did not exist yet. Applying such a
#                     rule to an older row fails good data.
#   ERA_VALUE         the rule constrains a VALUE that is present. Do not gate
#                     it. If a value is sitting in the row, it must be valid
#                     regardless of what version the row claims to be — because
#                     the declared version is a FLOOR, not a description.
ERA_REQUIREMENT, ERA_VALUE = "ERA_REQUIREMENT", "ERA_VALUE"

ANY, PER_LAYER, UNIFIED = "ANY", "PER_LAYER", "UNIFIED"

# RAW_VALUES — targets whose string values are exactly as the producer wrote
# them. Introduced in chunk 7, and it is a REFINEMENT of PER_LAYER rather than a
# synonym.
#
# The handover guardrail says the empty-string sweep binds to the per-layer
# views and never to focus_unified. The REASON is decision D3: the unified view
# normalises '' to NULL, so a sweep there returns zero and reads as a pass. The
# constraint is therefore about the TRANSFORMATION APPLIED, not about which
# folder a file sits in.
#
# Taken literally as "layers only", it excludes the negative fixtures — which are
# never merged and never normalised, and which carry the one planted
# EMPTY_STRING_PLACEHOLDER the sweep exists to catch. The literal reading would
# have left it permanently uncaught by the only check written to find it.
#
# Excluded, each for a stated reason:
#   unified       decision D3 normalises '' to NULL
#   supplemental  decision D17 reads '' as NULL, because CSV has no null
RAW_VALUES = "RAW_VALUES"


@dataclass
class SpecRef:
    """Where a rule came from. A check cannot be registered without one."""
    column: str
    text: str                 # the requirement sentence, as parsed at the tag
    severity: str             # FAIL or WARN, from the RFC 2119 keyword in text
    url: str                  # the build spec section 9 raw URL
    tag: str = "v1.2"
    # DERIVED means the rule follows from the specification but is not stated in
    # it — a conclusion drawn from two sentences read together. Tracked because
    # this harness's whole claim is that its rules trace to the specification,
    # and a derived rule filed quietly among quoted ones devalues every quoted
    # one beside it. Reported under its own heading, never mixed in.
    derived: bool = False

    def short(self, width=96):
        return self.text if len(self.text) <= width else self.text[:width - 1] + "…"


@dataclass
class Check:
    id: str
    title: str
    fn: object                       # (ctx) -> list of Violation
    refs: list = field(default_factory=list)     # SpecRef, at least one
    columns: tuple = ()              # columns read — drives the era gate
    binding: str = ANY
    era_mode: str = ERA_REQUIREMENT
    # Which FOCUS dataset this check belongs to. Layer C is a different dataset
    # at a different VERSION — cost_and_usage at v1.2, the supplemental three at
    # v1.4 — so a check must never be pointed at a table it was not written for.
    # Column names collide across datasets (BillingCurrency, InvoiceIssuerName),
    # so without this a cost_and_usage rule would happily run against an invoice
    # and produce a confident, meaningless result.
    dataset: str = "cost_and_usage"

    @property
    def is_derived(self):
        return any(r.derived for r in self.refs)

    @property
    def severity(self):
        """The strongest severity among the requirements this check implements.

        A check citing one MUST and one SHOULD is a FAIL check: it can fail. If
        a rule needs to report at both levels it should be two checks, and the
        code says so rather than averaging.
        """
        levels = {r.severity for r in self.refs}
        return FAIL if FAIL in levels else (WARN if WARN in levels else INFO)


@dataclass
class Violation:
    check_id: str
    severity: str
    target: str
    message: str
    row_index: int = -1
    expected_id: str = ""            # x_ExpectedViolation, on negative rows only


REGISTRY = []

# Cross-dataset checks are a different shape: they need MORE THAN ONE target at
# once, so they cannot run inside the per-target loop. Kept in their own registry
# and run after it, with every discovered dataset in hand.
#
# This is what Layer C is FOR. The supplemental datasets exist precisely to hold
# facts the cost rows cannot carry — what an invoice totalled, when a commitment
# term runs from and to — and a rule spanning them is unimplementable from
# cost_and_usage alone. Chunk 4 had to downgrade finding F10 for exactly that
# reason; this registry is where that downgrade gets reversed.
CROSS_REGISTRY = []


def register_cross(check):
    CROSS_REGISTRY.append(check)
    return check


def register(check):
    if not check.refs:
        raise ValueError(
            f"{check.id}: refuses to register without a spec citation. "
            "A rule with no source is an opinion."
        )
    # Checks are GENERATED by matching sentence patterns, so two patterns can
    # match one sentence and register it twice. That happened between the
    # allowed-values fallback and the chunk 5 value-condition parser: one defect
    # reported under two names, which inflates counts and splits attribution —
    # the same failure as F30, arriving from the registry instead of the report.
    #
    # Cheap to detect, so detected rather than trusted.
    for existing in REGISTRY:
        # SCOPED TO THE DATASET. Several columns — InvoiceIssuerName,
        # BillingCurrency, BillingAccountId — are defined in more than one FOCUS
        # dataset with identical wording. Two checks citing the same sentence for
        # two DIFFERENT tables are not duplicates; they are one rule applied
        # twice, which is exactly right.
        #
        # The guard found this by refusing to register, which is the behaviour
        # wanted from a guard whose own rule is imprecise: it stopped rather than
        # guessing.
        if existing.dataset != check.dataset:
            continue
        shared = {r.text for r in existing.refs} & {r.text for r in check.refs}
        if shared:
            raise ValueError(
                f"{check.id} and {existing.id} both implement the same "
                f"requirement sentence:\n    {sorted(shared)[0][:110]}\n"
                f"One sentence, one check. Remove whichever states it less "
                f"completely."
            )
    REGISTRY.append(check)
    return check


# =============================================================================
# 3. THE HORIZONS
# =============================================================================

def horizons(check, lifecycle):
    """The version window in which a check can be expressed at all.

    FROM: the latest INTRODUCED among the columns it reads. A check reading
          PricingCurrency (1.2) and ChargeCategory (0.5) is expressible from 1.2.
    TO:   the earliest REMOVED among them, exclusive. Usually open-ended.

    This is what F22 asked for, and it is not decoration. A harness that only
    tracks additions will carry a check on ProviderName into a v1.4 migration
    and discover the problem when the query fails to parse. Carrying the removal
    map means the harness can say, before anything runs, WHICH of its checks a
    version upgrade would delete.
    """
    intro = "0.5"
    for col in check.columns:
        got = lifecycle["introduced"].get(col)
        if got and vkey(got) > vkey(intro):
            intro = got
    gone = None
    for col in check.columns:
        got = lifecycle["removed"].get(col)
        if got and (gone is None or vkey(got.lstrip("v")) < vkey(gone.lstrip("v"))):
            gone = got
    return intro, gone


# =============================================================================
# 4. DATASETS
# =============================================================================

@dataclass
class Target:
    name: str
    path: str
    kind: str                # "layer", "unified", "negative", "supplemental"
    dataset: str = "cost_and_usage"
    rows: list = field(default_factory=list)
    columns: list = field(default_factory=list)

    @property
    def is_unified(self):
        return self.kind == "unified"


def _parquets_in(folder):
    """Parquet files in a folder, or in its immediate subfolders.

    Two shapes exist. The synthetic layers, the unified view and the negative
    fixtures each hold one parquet directly. data/raw-sanitised/ holds ONE
    SUBFOLDER PER EXPORT PULL, mirroring data/raw/ — because a second pull is a
    second export of the same layer, and flattening them would silently merge
    two months into one view and lose which rows came from where.

    Returns [(label_suffix, path)]. The suffix is empty for the flat case.
    """
    if not os.path.isdir(folder):
        return []
    direct = sorted(glob.glob(os.path.join(folder, "*.parquet")))
    if direct:
        return [("", direct[0])]
    out = []
    for entry in sorted(os.listdir(folder)):
        sub = os.path.join(folder, entry)
        if not os.path.isdir(sub):
            continue
        found = sorted(glob.glob(os.path.join(sub, "*.parquet")))
        if found:
            out.append((entry, found[0]))
    return out


# Where each dataset lives, and what it is for. Order matters only for output.
#
# data/raw/ is deliberately ABSENT from this list. It holds unsanitised personal
# data (finding F6, guardrail 5) and must never be read by a script whose output
# is published. The per-layer real view the empty-string sweep needs is
# data/raw-sanitised/ — see the note in the discovery output.
TARGET_SPECS = [
    ("real",             os.path.join(DATA, "raw-sanitised"),        "layer"),
    ("synthetic-v1.2",   os.path.join(DATA, "synthetic", "v1.2"),    "layer"),
    ("synthetic-legacy", os.path.join(DATA, "synthetic", "pre-1.2"), "layer"),
    ("unified",          os.path.join(DATA, "unified"),              "unified"),
    ("negative",         os.path.join(DATA, "negative"),             "negative"),
]


SUPPLEMENTAL_FILES = {
    "billing_period":      "billing_period.csv",
    "invoice_detail":      "invoice_detail.csv",
    "contract_commitment": "contract_commitment.csv",
}


def _read_supplemental(dataset, path):
    """Load one Layer C CSV.

    D17 — IN A CSV, AN EMPTY FIELD IS READ AS NULL.
    CSV has no null: an absent value and an empty string are the same six
    characters of nothing. That is the opposite of the parquet layers, where ''
    and NULL are genuinely different and conflating them is finding F32.
    Both readings are right for their format, and the difference is recorded here
    rather than left for someone to discover from an inconsistent result.
    """
    import csv as _csv
    with open(path, newline="") as f:
        rows = list(_csv.DictReader(f))
    for row in rows:
        for key, value in list(row.items()):
            if value == "":
                row[key] = None
    columns = list(rows[0].keys()) if rows else []
    return rows, columns


def discover():
    """Which datasets are actually on disk. Found and missing both reported.

    Deliberately a glob rather than a manifest read. Every layer folder carries
    an Azure-shaped manifest.json, but data/unified/ does NOT — Stage 3 chunk 9
    writes focus_unified.snappy.parquet straight out of DuckDB with nothing
    beside it. A loader insisting on a manifest would silently skip the single
    most important dataset in the project.
    """
    found, missing = [], []
    con = duckdb.connect()
    for name, folder, kind in TARGET_SPECS:
        entries = _parquets_in(folder)
        if not entries:
            missing.append((name, folder, kind))
            continue
        for suffix, path in entries:
            label = f"{name}:{suffix}" if suffix else name
            con.execute(f"CREATE OR REPLACE VIEW t AS SELECT * FROM read_parquet('{path}')")
            cols = [r[0] for r in con.execute("DESCRIBE t").fetchall()]
            rows = [dict(zip(cols, r)) for r in con.execute("SELECT * FROM t").fetchall()]
            found.append(Target(label, path, kind, rows=rows, columns=cols))

    # Layer C — the supplemental datasets, at v1.4.
    for dataset, filename in sorted(SUPPLEMENTAL_FILES.items()):
        path = os.path.join(DATA, "supplemental", filename)
        if not os.path.exists(path):
            missing.append((f"layerC:{dataset}", path, "supplemental"))
            continue
        rows, cols = _read_supplemental(dataset, path)
        found.append(Target(f"layerC:{dataset}", path, "supplemental",
                            dataset=dataset, rows=rows, columns=cols))
    return found, missing


# =============================================================================
# 5. THE RUN CONTEXT AND THE ERA GATE
# =============================================================================

@dataclass
class CrossContext:
    """Every discovered dataset, keyed for cross-dataset rules."""
    targets: list
    spec: dict
    lifecycle: dict
    check: object = None

    def by_dataset(self, dataset):
        return [t for t in self.targets if t.dataset == dataset]

    def cost_target(self, prefer="unified"):
        """The cost_and_usage table to reconcile against.

        Prefers the merged view: an invoice or a commitment spans layers, and
        reconciling against one layer would report a shortfall that is really a
        missing layer — the same misattribution as F33's per-layer purchase.
        """
        cost = [t for t in self.targets if t.dataset == "cost_and_usage"]
        for t in cost:
            if t.kind == prefer:
                return t
        return cost[0] if cost else None


@dataclass
class Context:
    target: Target
    spec: dict
    lifecycle: dict
    check: Check
    suppressed: list = field(default_factory=list)

    def rows_in_scope(self):
        """(index, row) pairs this check is allowed to look at.

        VALUE-MODE checks see every row. If a value is present it must be valid,
        whatever version the row declares. This is finding F27: Azure's export
        declares FOCUS 1.0r2 and populates BillingAccountType and SubAccountType
        — both introduced at v1.2 — on all 118 real rows. A gate keyed purely on
        the declared version would skip those columns and report a clean pass on
        data it never looked at.

        REQUIREMENT-MODE checks are gated, and a row falls out for one of two
        reasons that must not be conflated:
          - the column had not been introduced at that era. Nothing to violate.
          - the column had already been REMOVED at that era. Same outcome,
            different cause; this one is F22 and deserves its own reporting once
            data at v1.4 exists.

        A row with no x_SchemaEra is treated as in scope. Every row here carries
        one, but a harness that silently skips unlabelled rows is a harness that
        can be made to pass by deleting a column.
        """
        if self.check.era_mode == ERA_VALUE:
            return list(enumerate(self.target.rows))
        out = []
        for i, row in enumerate(self.target.rows):
            era = row.get("x_SchemaEra")
            if era is None:
                out.append((i, row))
                continue
            if all(era_supports(era, c, self.lifecycle) for c in self.check.columns):
                out.append((i, row))
        return out

    def skipped_by_era(self):
        return len(self.target.rows) - len(self.rows_in_scope())


# =============================================================================
# 6. THE FIRST CHECK FAMILY — ALLOWED VALUES
# =============================================================================
# Registered here to prove the wiring carries current end to end: a sentence
# parsed from the spec in chunk 1 becomes a severity, an era gate, a horizon,
# and a caught violation in data/negative/ — with no constant typed by hand.
#
# Stage 3's self_test.py had this as a hardcoded ALLOWED dict. That dict was
# CORRECT — chunk 1 confirmed all seven columns against the spec — but correct
# and sourced are different properties, and only one of them survives a spec
# revision unattended.

ENUM_COLUMNS = [
    "ChargeCategory", "ChargeClass", "ChargeFrequency", "PricingCategory",
    "CommitmentDiscountCategory", "CommitmentDiscountStatus",
    "CapacityReservationStatus", "ServiceCategory",
    # ServiceSubcategory is deliberately absent. Its "allowed values" are not a
    # flat list — they are (Category, Subcategory) PAIRS (finding F25), so "one
    # of the allowed values" means a valid pair, not a recognised name.
    # SVC-parent-map implements that sentence completely; a separate flat check
    # implemented the same sentence less completely, and the registry guard
    # rejected the pair.
]


def make_allowed_values_check(column, spec):
    """Build one allowed-values check from the spec entry for a column."""
    entry = spec[column]
    allowed = set(entry["allowed_values"])

    # Find the requirement sentence that states the constraint, so the check
    # cites the actual rule rather than a rule we assume is there.
    ref_text, ref_sev = "", FAIL
    for req in entry["requirements"]:
        if "allowed values" in req["text"].lower():
            ref_text, ref_sev = req["text"], req["severity"]
            break
    if not ref_text:
        # ChargeClass states its constraint as 'MUST be "Correction" when
        # ChargeClass is not null' rather than as 'one of the allowed values'.
        #
        # An earlier version fell back to any MUST containing a quoted literal,
        # which worked — and then chunk 5's value-condition parser matched the
        # SAME sentence and registered a second check for it. One defect,
        # reported twice, under two names.
        #
        # The fallback is removed rather than the new check: XCOL implements the
        # sentence as written, including its condition, where the fallback only
        # approximated it. Coverage is unchanged and the attribution is single.
        return None

    def fn(ctx):
        out = []
        for i, row in ctx.rows_in_scope():
            value = row.get(column)
            if value is None or value == "":
                continue                       # nullability is a separate check
            if value not in allowed:
                out.append(Violation(
                    ctx.check.id, ref_sev, ctx.target.name,
                    f"{column} = {value!r} is not an allowed value "
                    f"({len(allowed)} permitted at v1.2)",
                    row_index=i,
                    expected_id=row.get("x_ExpectedViolation", "") or "",
                ))
        return out

    return Check(
        id=f"AV-{column}",
        title=f"{column} restricted to its v1.2 allowed values",
        fn=fn,
        refs=[SpecRef(column, ref_text, ref_sev, entry["raw_url"])],
        columns=(column,),
        binding=ANY,
        # A value constraint, not a requirement: an allowed-values rule says
        # nothing about whether the column must be there, only that whatever is
        # there must be one of these. So it is not era-gated (F27).
        era_mode=ERA_VALUE,
    )


def make_declaration_drift_check(lifecycle):
    """Does a row carry a column from a later version than it declares?

    Finding F27. Azure's real export declares FOCUS 1.0r2 in its manifest and
    populates BillingAccountType and SubAccountType — both introduced at v1.2 —
    on all 118 rows.

    This is NOT a conformance failure. Nothing in the specification forbids a
    provider from shipping ahead of the version it declares, and emitting more
    of the standard than promised is the good direction to err in. It is
    reported as INFO.

    It matters because it falsifies an assumption a harness naturally makes:
    that the declared version describes the dataset. It does not — it is a
    FLOOR. Any rule gated purely on the declaration will skip columns that are
    present and populated, and report a clean pass on data it never examined.
    That is the quiet failure mode, and it is the mirror image of F10: F10 fails
    good data loudly, this passes unchecked data silently.
    """
    def fn(ctx):
        out = []
        seen = {}
        for i, row in enumerate(ctx.target.rows):
            era = row.get("x_SchemaEra")
            ceiling = ERA_CEILING.get(era)
            if ceiling is None:
                continue
            for col in ctx.target.columns:
                if row.get(col) is None:
                    continue
                introduced = lifecycle["introduced"].get(col)
                if introduced and vkey(introduced) > vkey(ceiling):
                    seen.setdefault((era, col, introduced), 0)
                    seen[(era, col, introduced)] += 1
        for (era, col, introduced), n in sorted(seen.items()):
            out.append(Violation(
                ctx.check.id, INFO, ctx.target.name,
                f"era {era} declares a {ceiling_of(era)} ceiling but {col} "
                f"(introduced {introduced}) is populated on {n} rows",
            ))
        return out

    return Check(
        id="META-declaration-drift",
        title="Columns populated ahead of the row's declared schema era",
        fn=fn,
        refs=[SpecRef(
            "SchemaMetadata",
            "A FOCUS dataset MAY include columns beyond those required at the "
            "declared version; the declared version is a floor. (Observed "
            "behaviour, reported as INFO — see finding F27.)",
            INFO,
            "https://raw.githubusercontent.com/FinOps-Open-Cost-and-Usage-Spec/"
            "FOCUS_Spec/v1.2/specification/supported_features/schema_metadata.md",
        )],
        columns=(),
        binding=ANY,
        era_mode=ERA_VALUE,
    )


def ceiling_of(era):
    return ERA_CEILING.get(era, "?")


# =============================================================================
# 6b. STRUCTURAL CHECKS — chunk 3, generated from parsed spec sentences
# =============================================================================

def make_nullability_check(rule, index):
    """One check per parsed nullability sentence.

    Two shapes. Unconditional (`X MUST NOT be null.`) tests every row in scope.
    Conditional tests only the rows where the condition holds — which is the
    conditional-requirement class the official FOCUS Validator cannot express at
    all, and the reason a hand-written harness is worth building.
    """
    column = rule["column"]
    condition = rule["condition"]
    must_be_null = rule["must_be_null"]
    severity = rule.get("severity", FAIL)

    def fn(ctx):
        out = []
        suppressed = 0
        for i, row in ctx.rows_in_scope():
            # Evaluated twice on purpose. STRICT reads only None as null — the
            # literal reading. LENIENT also reads '' as null — what the provider
            # meant (F32). A row that fires strict but not lenient is a finding
            # CAUSED BY the empty-string placeholder rather than by the rule the
            # check names, so it is counted rather than reported. Suppressing it
            # silently would be the F30 mistake in reverse.
            if condition is not None:
                lenient = rules.evaluate(condition, row, empty_is_null=True)
                strict = rules.evaluate(condition, row, empty_is_null=False)
                if not lenient:
                    if strict:
                        suppressed += 1
                    continue

            value = row.get(column)
            blank = rules.is_null(value)
            if must_be_null and not blank:
                out.append(Violation(
                    ctx.check.id, severity, ctx.target.name,
                    f"{column} = {value!r} but MUST be null"
                    + (f" when {rules.describe(condition)}" if condition else ""),
                    row_index=i, expected_id=row.get("x_ExpectedViolation", "") or ""))
            elif not must_be_null and blank:
                if value == "":
                    # The value is present but is a placeholder. That is the
                    # empty-string defect again, not a missing value, and the
                    # empty-string check owns it.
                    suppressed += 1
                    continue
                out.append(Violation(
                    ctx.check.id, severity, ctx.target.name,
                    f"{column} is null but MUST NOT be null"
                    + (f" when {rules.describe(condition)}" if condition else ""),
                    row_index=i, expected_id=row.get("x_ExpectedViolation", "") or ""))

        if suppressed:
            ctx.suppressed.append((ctx.check.id, suppressed))
        return out

    referenced = (column,) + tuple(rules.columns_in(condition) if condition else ())
    kind = ("null" if must_be_null else "notnull") + ("" if severity == FAIL else "-should")
    return Check(
        id=f"NULL-{column}-{kind}{index}",
        title=f"{column} nullability" + (" (conditional)" if condition else ""),
        fn=fn,
        refs=[SpecRef(column, rule["text"], severity, rule["url"])],
        columns=tuple(dict.fromkeys(referenced)),
        binding=ANY,
        # A nullability rule REQUIRES something, so it is era-gated: a column
        # that did not exist cannot be required to hold a value (F27).
        era_mode=ERA_REQUIREMENT,
    )


def make_presence_check(spec, lifecycle):
    """Mandatory columns must be IN the dataset. Not the same as being non-null.

    Build spec section 2's third differentiator: presence (Feature Level) and
    nullability (Null Handling) answer different questions, and reporting them
    together lets a broken dataset pass. A dataset missing ServiceCategory
    entirely and one with a null ServiceCategory are different defects.

    Era-aware, and it has to be: all 21 v1.2 Mandatory columns happen to predate
    1.0 so they apply to every layer here, but a v1.3 mandatory column must not
    be demanded of a 1.0r2 export.
    """
    mandatory, conditional = rules.presence_expectations(spec, lifecycle)

    def fn(ctx):
        out = []
        eras = {row.get("x_SchemaEra") for row in ctx.target.rows}
        eras.discard(None)
        for cid, introduced in mandatory:
            for era in sorted(eras):
                ceiling = ERA_CEILING.get(era)
                if ceiling is None or vkey(introduced) > vkey(ceiling):
                    continue
                if cid not in ctx.target.columns:
                    out.append(Violation(
                        ctx.check.id, FAIL, ctx.target.name,
                        f"{cid} is Mandatory at v1.2 (introduced {introduced}) and "
                        f"absent from a dataset containing {era} rows"))
        # Conditional columns are reported, never asserted — their condition is
        # prose, the same class the nullability parser refuses.
        absent = [c for c, _ in conditional if c not in ctx.target.columns]
        if absent:
            out.append(Violation(
                ctx.check.id, INFO, ctx.target.name,
                f"{len(absent)} Conditional columns absent — not a defect without "
                f"knowing whether the condition holds: {', '.join(sorted(absent)[:6])}"
                + (" ..." if len(absent) > 6 else "")))
        return out

    return Check(
        id="PRESENCE-mandatory",
        title="Mandatory columns present in the dataset",
        fn=fn,
        refs=[SpecRef(
            "FeatureLevel",
            "Columns with Feature level 'Mandatory' MUST be present in a FOCUS "
            "dataset. Presence is distinct from nullability.",
            FAIL,
            "https://raw.githubusercontent.com/FinOps-Open-Cost-and-Usage-Spec/"
            "FOCUS_Spec/v1.2/specification/attributes/column_handling.md")],
        columns=(),
        binding=ANY,
        era_mode=ERA_VALUE,
    )


def make_service_parent_check(spec):
    """ServiceSubcategory must sit under its own ServiceCategory.

    The pairs come from the allowed-values table, whose first column is the
    parent (finding F25). 'Virtual Machines' under anything but 'Compute' is a
    hard fail — build spec section 2.10.2.
    """
    parents = rules.service_parent_map(spec)
    entry = spec["ServiceSubcategory"]
    text = next((r["text"] for r in entry["requirements"]
                 if "allowed values" in r["text"].lower()), "")

    # Every subcategory name, across all parents. Needed for the fallback below.
    all_subcategories = {sub for subs in parents.values() for sub in subs}

    def fn(ctx):
        out = []
        for i, row in ctx.rows_in_scope():
            category = row.get("ServiceCategory")
            subcategory = row.get("ServiceSubcategory")
            if not subcategory:
                continue

            permitted = parents.get(category) if category else None
            if permitted is not None:
                if subcategory not in permitted:
                    out.append(Violation(
                        ctx.check.id, FAIL, ctx.target.name,
                        f"ServiceSubcategory {subcategory!r} is not permitted "
                        f"under ServiceCategory {category!r}",
                        row_index=i,
                        expected_id=row.get("x_ExpectedViolation", "") or ""))
            elif subcategory not in all_subcategories:
                # The parent is null or unrecognised, so the pair cannot be
                # checked — but the name itself still can. Without this fallback,
                # nulling ServiceCategory would switch off subcategory validation
                # entirely, and a dataset could be made to pass by deleting a value.
                out.append(Violation(
                    ctx.check.id, FAIL, ctx.target.name,
                    f"ServiceSubcategory {subcategory!r} is not a recognised "
                    f"value (ServiceCategory is {category!r}, so the pair itself "
                    f"cannot be checked)",
                    row_index=i,
                    expected_id=row.get("x_ExpectedViolation", "") or ""))
        return out

    return Check(
        id="SVC-parent-map",
        title="ServiceSubcategory belongs to its ServiceCategory",
        fn=fn,
        refs=[SpecRef("ServiceSubcategory", text, FAIL, entry["raw_url"])],
        columns=("ServiceCategory", "ServiceSubcategory"),
        binding=ANY,
        era_mode=ERA_VALUE,
    )


def make_resource_name_duplicate_check(spec):
    """ResourceName repeating ResourceId — a warning with a count.

    The spec MUST is real but conditional on something unknowable: ResourceName
    MUST NOT duplicate ResourceId when the resource is not provisioned
    interactively or only has a system-generated id. Whether a resource was
    provisioned interactively is not in the row.

    So it is reported as a WARNING with counts rather than asserted as a failure
    — Amendment 1 A7.2 assertion 4. Downgrading a MUST is normally exactly what
    this harness refuses to do; it is defensible here only because the
    alternative is asserting a rule whose precondition cannot be evaluated, and
    the downgrade is stated in the output rather than hidden in the code.
    """
    entry = spec["ResourceName"]
    text = next((r["text"] for r in entry["requirements"]
                 if "duplicate" in r["text"].lower()), "")
    if not text:
        return None

    def fn(ctx):
        hits = []
        for i, row in ctx.rows_in_scope():
            rid, rname = row.get("ResourceId"), row.get("ResourceName")
            if rid and rname and rid == rname:
                hits.append(i)
        if hits:
            return [Violation(
                ctx.check.id, WARN, ctx.target.name,
                f"ResourceName duplicates ResourceId on {len(hits)} rows. The spec "
                f"MUST is conditional on provisioning method, which the row does not "
                f"carry — reported as a warning (Amendment A7.2.4)",
                row_index=hits[0])]
        return []

    return Check(
        id="WARN-ResourceName-duplicates-ResourceId",
        title="ResourceName repeating ResourceId",
        fn=fn,
        refs=[SpecRef("ResourceName", text, WARN, entry["raw_url"])],
        columns=("ResourceId", "ResourceName"),
        binding=ANY,
        era_mode=ERA_VALUE,
    )


# =============================================================================
# 6c. METRIC VALIDATIONS — chunk 4
# =============================================================================
# Three families, all derived from spec sentences rather than transcribed:
#   - non-negativity          "X MUST be a non-negative decimal value."
#   - price x quantity        "The product of X and Y MUST match the Z when ..."
#   - commitment aggregates   the two EffectiveCost invariants (F10, F24)
#
# TOLERANCE IS A HARNESS POLICY, NOT A SPECIFICATION REQUIREMENT.
# numeric_format.md says so in as many words: the specification does not require
# a specific level of precision, and precision is for the provider to define and
# publish. So any tolerance here is OUR judgement, and it is declared rather than
# buried — a harness that silently picks an epsilon is asserting a rule the spec
# does not contain. Inherited from Stage 3's self_test.py so the two agree.
TOLERANCE = Decimal("0.000001")

NONNEG_RE = re.compile(r"^(\w+) MUST be a non-negative decimal value$")
PRODUCT_RE = re.compile(
    r"^The product of (\w+) and (\w+) MUST match the (\w+) when (.+)$")


def make_nonnegative_checks(spec):
    """Every column the spec requires to be non-negative. Found, not listed."""
    out = []
    for cid, entry in sorted(spec.items()):
        for req in entry["requirements"]:
            if req["severity"] != FAIL:
                continue
            match = NONNEG_RE.match(rules.normalise(req["text"]))
            if not match or match.group(1) != cid:
                continue

            def fn(ctx, column=cid):
                found = []
                for i, row in ctx.rows_in_scope():
                    value = row.get(column)
                    if value is None or not isinstance(value, Decimal):
                        continue
                    if value < 0:
                        found.append(Violation(
                            ctx.check.id, FAIL, ctx.target.name,
                            f"{column} = {value} is negative; MUST be non-negative",
                            row_index=i,
                            expected_id=row.get("x_ExpectedViolation", "") or ""))
                return found

            out.append(Check(
                id=f"METRIC-nonneg-{cid}",
                title=f"{cid} is non-negative",
                fn=fn,
                refs=[SpecRef(cid, req["text"], FAIL, entry["raw_url"])],
                columns=(cid,),
                binding=ANY,
                # A value constraint: if a number is present it must not be
                # negative, whatever era the row declares (F27).
                era_mode=ERA_VALUE,
            ))
            break
    return out


def make_product_checks(spec):
    """price x quantity MUST match cost — with the spec's own scope attached.

    The same rule is stated in both the price column's file and the cost
    column's file, with slightly different `when` clauses: the cost file adds
    "and <price> is not null". Both are parsed; duplicates are dropped on the
    (price, quantity, cost) triple, keeping the one with the more complete
    scope, because the narrower condition can only ever fire on a subset.

    Corrections are exempt, and the spec is explicit about why — it states as a
    MAY that discrepancies between price, quantity and cost are permitted when
    ChargeClass is "Correction". **A corrected row cannot be analysed by unit
    economics at all**, which is worth knowing before building any price
    variance report on FOCUS data.
    """
    seen, out = {}, []
    for cid, entry in sorted(spec.items()):
        for req in entry["requirements"]:
            if req["severity"] != FAIL:
                continue
            match = PRODUCT_RE.match(rules.normalise(req["text"]))
            if not match:
                continue
            price, quantity, cost, when = match.groups()
            if not all(c in spec for c in (price, quantity, cost)):
                continue
            condition = rules.parse_condition(when, rules.name_lookup(spec))
            if condition is None:
                continue
            condition, _ = rules.prune(condition, in_or=False)
            if condition is None:
                continue
            key = (price, quantity, cost)
            terms = len(rules.columns_in(condition))
            if key in seen and seen[key][0] >= terms:
                continue
            seen[key] = (terms, condition, req, entry)

    for (price, quantity, cost), (_, condition, req, entry) in sorted(seen.items()):
        def fn(ctx, price=price, quantity=quantity, cost=cost, condition=condition):
            found = []
            for i, row in ctx.rows_in_scope():
                if not rules.evaluate(condition, row):
                    continue
                p, q, c = row.get(price), row.get(quantity), row.get(cost)
                if any(v is None or not isinstance(v, Decimal) for v in (p, q, c)):
                    continue
                delta = p * q - c
                if abs(delta) > TOLERANCE:
                    found.append(Violation(
                        ctx.check.id, FAIL, ctx.target.name,
                        f"{price} {p} x {quantity} {q} = {p * q}, but {cost} is {c} "
                        f"(out by {delta})",
                        row_index=i,
                        expected_id=row.get("x_ExpectedViolation", "") or ""))
            return found

        out.append(Check(
            id=f"METRIC-product-{cost}",
            title=f"{price} x {quantity} matches {cost}",
            fn=fn,
            refs=[SpecRef(cost, req["text"], FAIL, entry["raw_url"])],
            columns=(price, quantity, cost) + tuple(rules.columns_in(condition)),
            binding=ANY,
            era_mode=ERA_VALUE,
        ))
    return out


def _commitment_groups(ctx):
    """Rows grouped by (CommitmentDiscountId, BillingCurrency).

    Currency is in the key, not an afterthought: handover guardrail 4. The
    unified view holds USD and EUR, and summing across them produces a number
    that is wrong in a way nothing about it looks wrong.
    """
    groups = {}
    for i, row in ctx.rows_in_scope():
        cid = row.get("CommitmentDiscountId")
        if cid is None or cid == "":
            continue
        groups.setdefault((cid, row.get("BillingCurrency")), []).append((i, row))
    return groups


def make_commitment_closure_check(spec):
    """F10, scoped — and downgraded to a warning, for a reason worth stating.

    The spec:
        The sum of EffectiveCost where ChargeCategory is "Usage" MUST equal the
        sum of BilledCost where ChargeCategory is "Purchase".

    Read globally it fails every real dataset: on-demand usage has an
    EffectiveCost and no corresponding purchase. Scoping it to a commitment is
    the fix finding F10 identified, and it is necessary — but it is NOT
    sufficient, and that second half only became visible when the check was run.

    **The invariant also presupposes that the dataset spans the commitment's
    entire term.** A three-year reservation bought on 31 July, in a July export,
    shows the full purchase against one day of amortised usage. Our own data has
    exactly that case: 2,628.00 purchased, 2.40 consumed. Nothing is
    non-conformant. The export is simply one month long.

    Whether a dataset covers a commitment's term is not something the rows can
    establish — the term is not in the data. So this is a MUST whose precondition
    cannot be evaluated, and it is reported as a WARNING with the delta, on the
    same principle as the ResourceName duplicate rule (Amendment A7.2.4).

    Downgrading a MUST is normally exactly what this harness refuses to do. It is
    defensible here only because the alternative is asserting a rule whose
    precondition is unknowable — and the downgrade is printed in the output
    rather than hidden in the code.
    """
    entry = spec["EffectiveCost"]
    text = next((r["text"] for r in entry["requirements"]
                 if "sum of BilledCost" in r["text"]), "")
    if not text:
        return None

    def fn(ctx):
        found = []
        for (cid, currency), rows in sorted(_commitment_groups(ctx).items()):
            usage_rows = [r for _, r in rows if r.get("ChargeCategory") == "Usage"]
            purchase_rows = [r for _, r in rows if r.get("ChargeCategory") == "Purchase"]
            usage = sum((r.get("EffectiveCost") or Decimal(0) for r in usage_rows),
                        Decimal(0))
            purchase = sum((r.get("BilledCost") or Decimal(0) for r in purchase_rows),
                           Decimal(0))
            if not usage_rows and not purchase_rows:
                continue

            # TWO DIFFERENT SITUATIONS, AND THEY MUST NOT SHARE A MESSAGE.
            #
            #   no purchase row at all   the dataset does not contain the
            #                            purchase. Ordinary for a commitment
            #                            bought before the export window, and
            #                            nothing about the numbers is in doubt.
            #   purchase present, amounts differ
            #                            either the dataset covers only part of
            #                            the term, or the commitment genuinely
            #                            does not close. The rows cannot tell
            #                            these apart, which is why this is a
            #                            warning and not a failure.
            #
            # Collapsing them would report "out by -74.40" for a commitment whose
            # purchase simply is not here — a number that invites someone to go
            # looking for a 74.40 discrepancy that does not exist.
            if not purchase_rows:
                found.append(Violation(
                    ctx.check.id, WARN, ctx.target.name,
                    f"commitment {cid[-28:]} [{currency}]: {usage} of Usage "
                    f"EffectiveCost with NO Purchase row in this dataset. Closure "
                    f"is not evaluable — the purchase falls outside the export "
                    f"window. Not an imbalance",
                    row_index=rows[0][0]))
                continue

            delta = usage - purchase
            if abs(delta) > TOLERANCE:
                found.append(Violation(
                    ctx.check.id, WARN, ctx.target.name,
                    f"commitment {cid[-28:]} [{currency}]: Usage EffectiveCost "
                    f"{usage} vs Purchase BilledCost {purchase}, out by {delta}. "
                    f"Scoped per F10; a gap here may mean the dataset does not "
                    f"span the commitment term, which the rows cannot confirm",
                    row_index=rows[0][0]))
        return found

    return Check(
        id="COMMIT-closure-F10",
        title="EffectiveCost closes against Purchase BilledCost, per commitment",
        fn=fn,
        refs=[SpecRef("EffectiveCost", text, WARN, entry["raw_url"])],
        columns=("CommitmentDiscountId", "ChargeCategory", "EffectiveCost",
                 "BilledCost", "BillingCurrency"),
        binding=ANY,
        era_mode=ERA_REQUIREMENT,
    )


def make_commitment_split_check(spec):
    """F24 — and unlike its sibling, this one IS a hard failure.

    The spec:
        The sum of EffectiveCost where ChargeCategory is "Usage" MUST equal the
        sum where Usage and CommitmentDiscountStatus is "Used", plus the sum
        where Usage and CommitmentDiscountStatus is "Unused".

    Read globally it is as broken as F10: it requires every Usage row in the
    dataset to carry a commitment status, and on-demand usage never does — the
    spec itself requires that status to be null when there is no commitment. So
    the same scoping fix applies.

    **But the two invariants are not equally evaluable, and that difference is
    the interesting part.** Once scoped to a commitment, this is a PARTITION
    IDENTITY: every Usage row in the group must be Used or Unused, so the parts
    must sum to the whole regardless of how much of the term the dataset covers.
    A one-day slice of a three-year reservation still satisfies it exactly.

    So F10 becomes a warning and F24 stays a failure — two adjacent sentences in
    the same file, one of which can be asserted and one of which cannot. That
    distinction is worth carrying into the community issue: the file does not
    need one scoping clause, it needs two different ones.
    """
    entry = spec["EffectiveCost"]
    text = next((r["text"] for r in entry["requirements"]
                 if "CommitmentDiscountStatus" in r["text"] and "sum of" in r["text"]), "")
    if not text:
        return None

    def fn(ctx):
        found = []
        for (cid, currency), rows in sorted(_commitment_groups(ctx).items()):
            usage = [r for _, r in rows if r.get("ChargeCategory") == "Usage"]
            total = sum((r.get("EffectiveCost") or Decimal(0) for r in usage), Decimal(0))
            parts = sum((r.get("EffectiveCost") or Decimal(0) for r in usage
                         if r.get("CommitmentDiscountStatus") in ("Used", "Unused")),
                        Decimal(0))
            if not usage:
                continue
            delta = total - parts
            if abs(delta) > TOLERANCE:
                unstated = [r for r in usage
                            if r.get("CommitmentDiscountStatus") not in ("Used", "Unused")]
                found.append(Violation(
                    ctx.check.id, FAIL, ctx.target.name,
                    f"commitment {cid[-28:]} [{currency}]: Usage EffectiveCost "
                    f"{total} but Used+Unused is {parts}, out by {delta}; "
                    f"{len(unstated)} Usage rows carry neither status",
                    row_index=rows[0][0]))
        return found

    return Check(
        id="COMMIT-split-F24",
        title="Used plus Unused partitions Usage EffectiveCost, per commitment",
        fn=fn,
        refs=[SpecRef("EffectiveCost", text, FAIL, entry["raw_url"])],
        columns=("CommitmentDiscountId", "ChargeCategory", "EffectiveCost",
                 "CommitmentDiscountStatus", "BillingCurrency"),
        binding=ANY,
        era_mode=ERA_REQUIREMENT,
    )


# =============================================================================
# 6d. FORMAT AND CROSS-COLUMN CHECKS — chunk 5
# =============================================================================

# ISO 4217 alphabetic codes are exactly three uppercase letters. The check is
# the SHAPE, not membership of the code list: the list changes (currencies are
# added and withdrawn), and a harness carrying a stale copy would reject valid
# data. Shape catches "US Dollars", "usd" and "US$" — the errors that actually
# occur — without asserting a list this project has no authority to maintain.
ISO4217_SHAPE = re.compile(r"^[A-Z]{3}$")

VALUE_RULE_RE = re.compile(r'^(\w+) MUST (NOT )?be "([^"]+)" when (.+)$')


def make_value_condition_checks(spec):
    """Cross-column value rules: X MUST [NOT] be "V" when <condition>.

    At v1.2 this shape catches `ChargeFrequency MUST NOT be "Usage-Based" when
    ChargeCategory is "Purchase"` — a rule about the relationship between two
    columns, where each column's value is individually legal. Both "Purchase"
    and "Usage-Based" are allowed values; the pair is not.

    **This is the class the reference Validator cannot express at all.** It
    checks columns one at a time against their own allowed-value lists, so a row
    that is valid column-by-column and invalid as a row passes it cleanly.
    """
    out = []
    for cid, entry in sorted(spec.items()):
        for req in entry["requirements"]:
            if req["severity"] != FAIL:
                continue
            match = VALUE_RULE_RE.match(rules.normalise(req["text"]))
            if not match:
                continue
            column, negated, value, when = match.groups()
            if column != cid:
                continue
            condition = rules.parse_condition(when, rules.name_lookup(spec))
            if condition is None:
                continue
            # Chunk 3's pruning rule applies here too, and forgetting it is how a
            # semantic leaf reached the evaluator and raised KeyError. A condition
            # that cannot be evaluated must be REFUSED, not evaluated badly.
            condition, _ = rules.prune(condition, in_or=False)
            if condition is None:
                continue

            def fn(ctx, column=column, value=value, forbidden=bool(negated),
                   condition=condition):
                found = []
                for i, row in ctx.rows_in_scope():
                    if not rules.evaluate(condition, row):
                        continue
                    actual = row.get(column)
                    if actual is None:
                        continue
                    if forbidden and actual == value:
                        found.append(Violation(
                            ctx.check.id, FAIL, ctx.target.name,
                            f"{column} = {actual!r} is forbidden when "
                            f"{rules.describe(condition)}",
                            row_index=i,
                            expected_id=row.get("x_ExpectedViolation", "") or ""))
                    elif not forbidden and actual != value:
                        found.append(Violation(
                            ctx.check.id, FAIL, ctx.target.name,
                            f"{column} = {actual!r} but MUST be {value!r} when "
                            f"{rules.describe(condition)}",
                            row_index=i,
                            expected_id=row.get("x_ExpectedViolation", "") or ""))
                return found

            out.append(Check(
                id=f"XCOL-{cid}-{value.replace(' ', '')}",
                title=f"{cid} constrained by another column's value",
                fn=fn,
                refs=[SpecRef(cid, req["text"], FAIL, entry["raw_url"])],
                columns=(cid,) + tuple(rules.columns_in(condition)),
                binding=ANY,
                era_mode=ERA_VALUE,
            ))
    return out


def make_currency_check(spec):
    """BillingCurrency must be a three-letter ISO 4217 code — and only it.

    CurrencyFormat makes the ISO rule CONDITIONAL: three-letter alphabetic when
    the value is national currency, StringHandling when it is virtual currency
    (credits, tokens). The row does not say which it is.

    For BillingCurrency the condition is settled by the column's own rule —
    *BillingCurrency MUST be expressed in national currency* — so the ISO
    requirement applies unconditionally and this is a hard failure.

    **PricingCurrency carries no such statement and is deliberately NOT checked
    here.** A provider pricing in credits or tokens is conformant, and the row
    gives no way to tell that from a malformed code. Asserting ISO on
    PricingCurrency would broaden a conditional rule into an unconditional one —
    the pruning rule from chunk 3, in a different guise, and it would fail
    conformant data.

    A naive validator applies the same currency check to both columns. That is
    the mistake this docstring exists to record.
    """
    entry = spec["BillingCurrency"]
    text = next((r["text"] for r in entry["requirements"]
                 if "national currency" in r["text"]), "")
    if not text:
        return None

    def fn(ctx):
        found = []
        for i, row in ctx.rows_in_scope():
            value = row.get("BillingCurrency")
            if value is None or value == "":
                continue
            if not ISO4217_SHAPE.match(str(value)):
                found.append(Violation(
                    ctx.check.id, FAIL, ctx.target.name,
                    f"BillingCurrency = {value!r} is not a three-letter ISO 4217 "
                    f"alphabetic code",
                    row_index=i,
                    expected_id=row.get("x_ExpectedViolation", "") or ""))
        return found

    return Check(
        id="FMT-ISO4217-BillingCurrency",
        title="BillingCurrency is a three-letter ISO 4217 code",
        fn=fn,
        refs=[SpecRef("BillingCurrency", text, FAIL, entry["raw_url"])],
        columns=("BillingCurrency",),
        binding=ANY,
        era_mode=ERA_VALUE,
    )


def make_charge_period_order_check(spec):
    """ChargePeriodEnd must not precede ChargePeriodStart.

    **DERIVED, NOT QUOTED — and that distinction is the point of this check.**

    Searching v1.2 for any statement ordering the two columns returns nothing.
    Searching v1.4 returns nothing either. Three releases on, the specification
    still nowhere says that a charge period's end must follow its start.

    What it does say is that ChargePeriodStart is the *inclusive start bound* and
    ChargePeriodEnd the *exclusive end bound* of "the effective period of the
    charge". A period whose exclusive end precedes its inclusive start contains
    no time at all, so it cannot be the effective period of anything. The
    conclusion follows — but it follows from two sentences read together, not
    from a sentence.

    So the check is registered as DERIVED. It appears under its own heading in
    `--list`, and the conformance report will separate it from the spec-cited
    checks, because this harness's entire claim is that its rules trace to the
    specification. **A derived rule that is quietly filed among quoted ones
    devalues every quoted one beside it.**

    Candidate FOCUS community issue, and a clean one: the specification has no
    explicit ordering requirement between ChargePeriodStart and ChargePeriodEnd,
    at any version through v1.4. It is the kind of gap everybody assumes is
    covered precisely because it is too obvious to write down.
    """
    entry = spec["ChargePeriodEnd"]
    text = next((r["text"] for r in entry["requirements"]
                 if "exclusive end bound" in r["text"]), "")

    def fn(ctx):
        found = []
        for i, row in ctx.rows_in_scope():
            start, end = row.get("ChargePeriodStart"), row.get("ChargePeriodEnd")
            if start is None or end is None:
                continue
            if end <= start:
                relation = "precedes" if end < start else "equals"
                found.append(Violation(
                    ctx.check.id, FAIL, ctx.target.name,
                    f"ChargePeriodEnd {end} {relation} ChargePeriodStart {start}; "
                    f"an exclusive end bound at or before an inclusive start "
                    f"bound describes no period at all",
                    row_index=i,
                    expected_id=row.get("x_ExpectedViolation", "") or ""))
        return found

    return Check(
        id="PERIOD-ordering",
        title="ChargePeriodEnd follows ChargePeriodStart",
        fn=fn,
        refs=[SpecRef("ChargePeriodEnd", text, FAIL, entry["raw_url"], derived=True)],
        columns=("ChargePeriodStart", "ChargePeriodEnd"),
        binding=ANY,
        era_mode=ERA_VALUE,
    )


def make_sku_price_details_checks(spec):
    """SkuPriceDetails property keys and value types, against the spec's table.

    Two MUSTs, both checkable, and both resting on the same thing: knowing which
    property keys are FOCUS-defined. That list is read from the specification's
    own table (13 properties at v1.2) rather than typed in — which matters more
    here than almost anywhere else in the project, because the standing trap is a
    key that looks defined and is not. The course taught `MemoryGB`. The
    specification says `MemorySize`. A query on the first returns nothing,
    forever, and reports it as an absence rather than an error.
    """
    entry = spec["SkuPriceDetails"]
    table = entry.get("subsection_tables", {}).get("focus-defined properties")
    if not table:
        return []

    defined = {}
    for row in table["rows"]:
        if len(row) >= 3 and row[0]:
            defined[row[0]] = row[2]

    prefix_text = next((r["text"] for r in entry["requirements"]
                        if 'MUST begin with the string "x_"' in r["text"]), "")
    type_text = next((r["text"] for r in entry["requirements"]
                      if "MUST be of the type specified" in r["text"]), "")
    out = []

    def parse_blob(value):
        if not value:
            return None
        try:
            return json.loads(value) if isinstance(value, str) else None
        except (ValueError, TypeError):
            return None

    if prefix_text:
        def key_fn(ctx):
            found = []
            for i, row in ctx.rows_in_scope():
                blob = parse_blob(row.get("SkuPriceDetails"))
                if not isinstance(blob, dict):
                    continue
                for key in blob:
                    if key in defined or key.startswith("x_"):
                        continue
                    near = [d for d in defined if d.lower()[:6] == key.lower()[:6]]
                    hint = f" (did you mean {near[0]}?)" if near else ""
                    found.append(Violation(
                        ctx.check.id, FAIL, ctx.target.name,
                        f"SkuPriceDetails key {key!r} is neither a FOCUS-defined "
                        f"property nor prefixed 'x_'{hint}",
                        row_index=i,
                        expected_id=row.get("x_ExpectedViolation", "") or ""))
            return found

        out.append(Check(
            id="SKU-key-prefix",
            title="SkuPriceDetails keys are FOCUS-defined or x_ prefixed",
            fn=key_fn,
            refs=[SpecRef("SkuPriceDetails", prefix_text, FAIL, entry["raw_url"])],
            columns=("SkuPriceDetails",),
            binding=ANY,
            era_mode=ERA_VALUE,
        ))

    if type_text:
        def type_fn(ctx):
            found = []
            for i, row in ctx.rows_in_scope():
                blob = parse_blob(row.get("SkuPriceDetails"))
                if not isinstance(blob, dict):
                    continue
                for key, value in blob.items():
                    expected = defined.get(key)
                    if expected is None or value is None:
                        continue
                    numeric = isinstance(value, (int, float)) and not isinstance(value, bool)
                    if expected == "Numeric" and not numeric:
                        found.append(Violation(
                            ctx.check.id, FAIL, ctx.target.name,
                            f"SkuPriceDetails {key!r} = {value!r} but the spec "
                            f"declares it Numeric",
                            row_index=i,
                            expected_id=row.get("x_ExpectedViolation", "") or ""))
                    elif expected == "String" and not isinstance(value, str):
                        found.append(Violation(
                            ctx.check.id, FAIL, ctx.target.name,
                            f"SkuPriceDetails {key!r} = {value!r} but the spec "
                            f"declares it String",
                            row_index=i,
                            expected_id=row.get("x_ExpectedViolation", "") or ""))
            return found

        out.append(Check(
            id="SKU-value-type",
            title="SkuPriceDetails values match their declared types",
            fn=type_fn,
            refs=[SpecRef("SkuPriceDetails", type_text, FAIL, entry["raw_url"])],
            columns=("SkuPriceDetails",),
            binding=ANY,
            era_mode=ERA_VALUE,
        ))
    return out


def make_layer_c_checks(dataset, spec):
    """Presence, allowed values and nullability for one supplemental dataset.

    The generators are the same ones used on cost_and_usage — the nullability
    sentence parser, the allowed-values reader — pointed at a different spec
    index. That reuse is the payoff for deriving rules from the specification
    rather than writing them: **a whole new dataset costs a spec index and a
    dataset tag, not a new body of hand-written assertions.**

    Layer C rows carry no x_SchemaEra, so the era gate passes them through. That
    is correct rather than lax: these datasets do not exist before v1.3, so there
    is no earlier era for a row of theirs to belong to.
    """
    checks = []

    mandatory = sorted(cid for cid, e in spec.items()
                       if (e.get("feature_level") or "").lower() == "mandatory")

    def presence_fn(ctx, mandatory=tuple(mandatory), dataset=dataset):
        out = []
        for cid in mandatory:
            if cid not in ctx.target.columns:
                out.append(Violation(
                    ctx.check.id, FAIL, ctx.target.name,
                    f"{cid} is Mandatory in the v1.4 {dataset} dataset and absent"))
        conditional = [c for c in spec
                       if (spec[c].get("feature_level") or "").lower() == "conditional"
                       and c not in ctx.target.columns]
        if conditional:
            out.append(Violation(
                ctx.check.id, INFO, ctx.target.name,
                f"{len(conditional)} Conditional columns absent — not a defect "
                f"without knowing whether the condition holds: "
                f"{', '.join(sorted(conditional))}"))
        return out

    checks.append(Check(
        id=f"LC-{dataset}-presence",
        title=f"{dataset}: Mandatory columns present",
        fn=presence_fn,
        refs=[SpecRef(
            dataset,
            f"Columns with Feature level 'Mandatory' MUST be present in a FOCUS "
            f"{dataset} dataset.", FAIL,
            "https://raw.githubusercontent.com/FinOps-Open-Cost-and-Usage-Spec/"
            "FOCUS_Spec/v1.4/specification/"
            f"datasets/{dataset}/columns/")],
        columns=(), binding=ANY, era_mode=ERA_VALUE, dataset=dataset,
    ))

    for cid, entry in sorted(spec.items()):
        if not entry.get("allowed_values"):
            continue
        permitted = set(entry["allowed_values"])
        text = next((r["text"] for r in entry["requirements"]
                     if "allowed values" in r["text"].lower()), "")
        if not text:
            continue
        severity = next((r["severity"] for r in entry["requirements"]
                         if "allowed values" in r["text"].lower()), FAIL)
        if severity not in (FAIL, WARN):
            continue

        def av_fn(ctx, column=cid, permitted=permitted, severity=severity):
            out = []
            for i, row in ctx.rows_in_scope():
                value = row.get(column)
                if value is None:
                    continue
                if value not in permitted:
                    out.append(Violation(
                        ctx.check.id, severity, ctx.target.name,
                        f"{column} = {value!r} is not an allowed value "
                        f"({len(permitted)} permitted at v1.4)", row_index=i))
            return out

        checks.append(Check(
            id=f"LC-{dataset}-AV-{cid}",
            title=f"{dataset}.{cid} allowed values",
            fn=av_fn,
            refs=[SpecRef(cid, text, severity, entry["raw_url"], tag="v1.4")],
            columns=(cid,), binding=ANY, era_mode=ERA_VALUE, dataset=dataset,
        ))

    for n, rule in enumerate(rules.nullability_rules(spec)[0]):
        check = make_nullability_check(rule, n)
        check.id = f"LC-{dataset}-{check.id}"
        check.dataset = dataset
        checks.append(check)

    return checks


# =============================================================================
# 6e. CROSS-DATASET CHECKS — chunk 6b
# =============================================================================

def _ts(value):
    """Parse a Layer C ISO 8601 timestamp. CSV gives strings; parquet gives
    datetimes. Returns a datetime or None."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).replace(tzinfo=None)
    except (ValueError, TypeError):
        return None


def _dec(value):
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except (ValueError, ArithmeticError):
        return None


def make_invoice_reconciliation_check(spec):
    """Sum of BilledCost per InvoiceId must match the invoice with that id.

    The specification names the key explicitly, and the key is InvoiceId:

        The sum of the BilledCost for a given InvoiceId MUST match the sum of
        the payable amount provided in the corresponding invoice with the
        same id.

    **The check therefore joins on InvoiceId and on nothing else.** That sounds
    obvious and is the whole finding: a tie-out that holds on some other key —
    a billing period, a date range — is not the tie-out this rule requires, and
    it will agree right up until the moment the two keys disagree.

    When no InvoiceId is shared between the datasets the identity is NOT
    EVALUABLE, and that is reported as such with the reason rather than as a
    pass. A reconciliation with nothing to reconcile is not a clean
    reconciliation (finding F38).

    On a real Azure export it is never evaluable: InvoiceId is empty on every
    row, one of the thirteen empty-string columns from finding F32. **A
    recommendation-level defect disabling a mandatory reconciliation** — and the
    concrete mechanism behind the familiar complaint that provider invoices and
    cost exports never quite agree.
    """
    entry = spec["BilledCost"]
    text = next((r["text"] for r in entry["requirements"]
                 if "sum of the payable amount" in r["text"]), "")
    if not text:
        return None

    def fn(ctx):
        out = []
        invoices = ctx.by_dataset("invoice_detail")
        cost = ctx.cost_target()
        if not invoices or cost is None:
            return out

        invoice_totals = {}
        for target in invoices:
            for row in target.rows:
                key = (row.get("InvoiceId"), row.get("BillingCurrency"))
                amount = _dec(row.get("BilledCost"))
                if key[0] and amount is not None:
                    invoice_totals[key] = invoice_totals.get(key, Decimal(0)) + amount

        cost_totals, unattributed = {}, 0
        for row in cost.rows:
            invoice_id = row.get("InvoiceId")
            amount = row.get("BilledCost")
            if not invoice_id:
                unattributed += 1
                continue
            key = (invoice_id, row.get("BillingCurrency"))
            cost_totals[key] = cost_totals.get(key, Decimal(0)) + (amount or Decimal(0))

        shared = set(invoice_totals) & set(cost_totals)
        for key in sorted(shared):
            delta = cost_totals[key] - invoice_totals[key]
            if abs(delta) > TOLERANCE:
                out.append(Violation(
                    "XDS-invoice-reconciliation", FAIL, "cross-dataset",
                    f"invoice {key[0]} [{key[1]}]: cost_and_usage sums to "
                    f"{cost_totals[key]}, invoice_detail says "
                    f"{invoice_totals[key]}, out by {delta}"))

        for key in sorted(set(invoice_totals) - set(cost_totals)):
            out.append(Violation(
                "XDS-invoice-reconciliation", WARN, "cross-dataset",
                f"invoice {key[0]} [{key[1]}] totals {invoice_totals[key]} but NO "
                f"cost row carries that InvoiceId — the identity is not evaluable "
                f"for this invoice, which is not the same as it balancing (F38)"))

        if unattributed:
            share = 100 * unattributed / max(1, len(cost.rows))
            out.append(Violation(
                "XDS-invoice-reconciliation", INFO, "cross-dataset",
                f"{unattributed} of {len(cost.rows)} cost rows ({share:.0f}%) carry "
                f"no InvoiceId and are outside invoice reconciliation entirely"))
        if shared:
            out.append(Violation(
                "XDS-invoice-reconciliation", INFO, "cross-dataset",
                f"{len(shared)} invoice(s) reconciled on the key the spec names"))
        return out

    return Check(
        id="XDS-invoice-reconciliation",
        title="BilledCost per InvoiceId matches invoice_detail",
        fn=fn,
        refs=[SpecRef("BilledCost", text, FAIL, entry["raw_url"])],
        columns=(), binding=ANY,
    )


def make_commitment_term_closure_check(spec):
    """FINDING F10, REVERSED — the closure invariant becomes decidable.

    Chunk 4 had to report this as a warning. Not because the rule was wrong, and
    not because the scoping fix was wrong, but because the invariant carries an
    unstated precondition — **the dataset must span the commitment's whole term**
    — and the term is not in the cost dataset. A three-year reservation bought on
    31 July shows its full purchase against one day of usage, and nothing in the
    rows says whether that is a shortfall or a short export.

    `contract_commitment` carries `ContractCommitmentPeriodStart` and
    `ContractCommitmentPeriodEnd`. **The term is in Layer C.** So with the
    supplemental dataset present the precondition is testable, and the check
    splits into two decidable outcomes instead of one honest shrug:

        term fully covered by the dataset  ->  closure MUST hold. FAIL if not.
        term only partly covered           ->  not evaluable, coverage reported.

    **This is an argument for the multi-dataset specification, not a note about
    our data.** The invariant is unverifiable from cost_and_usage alone and
    verifiable with contract_commitment — which is precisely why the supplemental
    datasets were added at v1.3, and a concrete demonstration of what they buy.

    It also sharpens the community issue. The recommendation is no longer "this
    sentence needs a scope clause" but: **scope it to a commitment, and state
    that it presupposes full-term coverage — a precondition only the
    contract_commitment dataset can establish.**
    """
    entry = spec["EffectiveCost"]
    text = next((r["text"] for r in entry["requirements"]
                 if "sum of BilledCost" in r["text"]), "")
    if not text:
        return None

    def fn(ctx):
        out = []
        commitments = ctx.by_dataset("contract_commitment")
        cost = ctx.cost_target()
        if not commitments or cost is None:
            return out

        terms = {}
        for target in commitments:
            for row in target.rows:
                cid = row.get("ContractCommitmentId")
                start = _ts(row.get("ContractCommitmentPeriodStart"))
                end = _ts(row.get("ContractCommitmentPeriodEnd"))
                if cid and start and end:
                    terms[cid] = (start, end, _dec(row.get("ContractCommitmentCost")),
                                  row.get("BillingCurrency"))

        groups = {}
        for row in cost.rows:
            cid = row.get("CommitmentDiscountId")
            if cid:
                groups.setdefault(cid, []).append(row)

        for cid, rows in sorted(groups.items()):
            if cid not in terms:
                out.append(Violation(
                    "XDS-commitment-closure", INFO, "cross-dataset",
                    f"commitment {cid[-28:]} has cost rows but no "
                    f"contract_commitment record — its term is unknown, so "
                    f"closure stays not evaluable"))
                continue

            start, end, contract_cost, currency = terms[cid]
            usage = [r for r in rows if r.get("ChargeCategory") == "Usage"]
            purchase = [r for r in rows if r.get("ChargeCategory") == "Purchase"]
            usage_total = sum((r.get("EffectiveCost") or Decimal(0) for r in usage),
                              Decimal(0))
            purchase_total = sum((r.get("BilledCost") or Decimal(0) for r in purchase),
                                 Decimal(0))

            covered_from = min((r.get("ChargePeriodStart") for r in usage
                                if r.get("ChargePeriodStart")), default=None)
            covered_to = max((r.get("ChargePeriodEnd") for r in usage
                              if r.get("ChargePeriodEnd")), default=None)
            if covered_from is None or covered_to is None:
                continue

            term_days = max((end - start).total_seconds() / 86400, 1)
            covered_days = max((min(covered_to, end)
                                - max(covered_from, start)).total_seconds() / 86400, 0)
            fraction = covered_days / term_days
            full_term = covered_from <= start and covered_to >= end

            if full_term:
                delta = usage_total - purchase_total
                if abs(delta) > TOLERANCE:
                    out.append(Violation(
                        "XDS-commitment-closure", FAIL, "cross-dataset",
                        f"commitment {cid[-28:]} [{currency}]: term "
                        f"{start:%Y-%m-%d} to {end:%Y-%m-%d} is FULLY covered by "
                        f"the dataset, so closure must hold — Usage EffectiveCost "
                        f"{usage_total} vs Purchase BilledCost {purchase_total}, "
                        f"out by {delta}"))
                else:
                    out.append(Violation(
                        "XDS-commitment-closure", INFO, "cross-dataset",
                        f"commitment {cid[-28:]} [{currency}]: term fully covered "
                        f"and closure holds exactly at {usage_total}. F10 asserted, "
                        f"not merely warned — the term came from Layer C"))
            elif covered_days <= 0:
                # DERIVED, and it is the deferred commitment-term check arriving
                # of its own accord. Usage attributed to a commitment but dated
                # wholly outside that commitment's term is not partial coverage —
                # it is misattribution, and reporting it as "0 days covered"
                # would bury the distinction under a rounding-looking number.
                #
                # No specification sentence requires usage to fall within its
                # commitment's term. As with PERIOD-ordering, the conclusion
                # follows from what the columns mean rather than from a rule, so
                # it is reported as an observation rather than a failure.
                #
                # This is also the check that would have caught finding F33
                # independently of the identifier collision: the legacy row was
                # dated two years before the reservation it claimed.
                out.append(Violation(
                    "XDS-commitment-closure", WARN, "cross-dataset",
                    f"commitment {cid[-28:]} [{currency}]: every usage row falls "
                    f"OUTSIDE the term {start:%Y-%m-%d} to {end:%Y-%m-%d} — usage "
                    f"runs {covered_from:%Y-%m-%d} to {covered_to:%Y-%m-%d}. Not "
                    f"partial coverage but misattribution: {usage_total} of "
                    f"EffectiveCost is booked against a commitment that had not "
                    f"begun"))
            else:
                out.append(Violation(
                    "XDS-commitment-closure", INFO, "cross-dataset",
                    # Days, not a percentage. One day of a three-year term
                    # rounds to "0.0%", which reads as no coverage at all when
                    # there is some — and the whole point of this line is that
                    # the gap is a measuring problem, not an absence.
                    f"commitment {cid[-28:]} [{currency}]: dataset covers "
                    f"{covered_days:.0f} of {term_days:.0f} days of the term "
                    f"{start:%Y-%m-%d} to {end:%Y-%m-%d}, "
                    f"so closure is NOT EVALUABLE. Usage {usage_total} against a "
                    f"{purchase_total} purchase is a short export, not a shortfall"))

            if contract_cost is not None and purchase_total and full_term:
                gap = purchase_total - contract_cost
                if abs(gap) > TOLERANCE:
                    out.append(Violation(
                        "XDS-commitment-closure", FAIL, "cross-dataset",
                        f"commitment {cid[-28:]}: Purchase BilledCost "
                        f"{purchase_total} disagrees with "
                        f"contract_commitment.ContractCommitmentCost "
                        f"{contract_cost}, out by {gap}"))
        return out

    return Check(
        id="XDS-commitment-closure",
        title="Commitment closure, decided against the term in Layer C",
        fn=fn,
        refs=[SpecRef("EffectiveCost", text, FAIL, entry["raw_url"])],
        columns=(), binding=ANY,
    )


def make_billing_period_check(spec):
    """Billing periods must not overlap, and cost rows must sit inside one.

    DERIVED. `BillingPeriodStart` is the inclusive start bound and
    `BillingPeriodEnd` the exclusive end bound of a billing period; two periods
    that overlap would put one charge in two of them, and the billing_period
    dataset exists to be the authority on which periods exist. But as with
    `PERIOD-ordering`, the specification never states the non-overlap
    requirement, so the check is labelled derived rather than quoted.
    """
    def fn(ctx):
        out = []
        periods = []
        for target in ctx.by_dataset("billing_period"):
            for row in target.rows:
                start, end = _ts(row.get("BillingPeriodStart")), _ts(row.get("BillingPeriodEnd"))
                if start and end:
                    periods.append((start, end, row.get("BillingPeriodStatus")))
        if not periods:
            return out

        periods.sort()
        for (s1, e1, _), (s2, e2, _) in zip(periods, periods[1:]):
            if s2 < e1:
                out.append(Violation(
                    "XDS-billing-period", FAIL, "cross-dataset",
                    f"billing periods overlap: {s1:%Y-%m-%d}..{e1:%Y-%m-%d} and "
                    f"{s2:%Y-%m-%d}..{e2:%Y-%m-%d}"))

        open_periods = [p for p in periods if str(p[2]).lower() == "open"]
        if len(open_periods) > 1:
            out.append(Violation(
                "XDS-billing-period", WARN, "cross-dataset",
                f"{len(open_periods)} billing periods are Open simultaneously"))

        cost = ctx.cost_target()
        if cost:
            outside = 0
            for row in cost.rows:
                start = row.get("ChargePeriodStart")
                if start is None:
                    continue
                if not any(s <= start < e for s, e, _ in periods):
                    outside += 1
            if outside:
                out.append(Violation(
                    "XDS-billing-period", INFO, "cross-dataset",
                    f"{outside} of {len(cost.rows)} cost rows fall outside every "
                    f"declared billing period — the billing_period dataset does "
                    f"not describe the whole cost dataset"))
        return out

    return Check(
        id="XDS-billing-period",
        title="Billing periods do not overlap and contain the cost rows",
        fn=fn,
        refs=[SpecRef(
            "BillingPeriodEnd",
            "BillingPeriodEnd MUST be the exclusive end bound of the billing "
            "period. (Non-overlap follows from the bounds; it is not stated.)",
            FAIL,
            "https://raw.githubusercontent.com/FinOps-Open-Cost-and-Usage-Spec/"
            "FOCUS_Spec/v1.4/specification/datasets/billing_period/columns/"
            "billingperiodend.md", tag="v1.4", derived=True)],
        columns=(), binding=ANY,
    )


# =============================================================================
# 6e-bis. STAGE 6 ALIGNMENT ASSERTIONS — Amendment A3.2 / A3.3, promoted
# =============================================================================
# Stage 6 ran these as queries (stage6_reconciliation.sql Q1-Q6, coverage
# Q7-Q11) and proved them once. A guarantee proven once is a screenshot; a
# guarantee that runs on every build is a property. This section is the
# promotion.
#
# Division of labour with chunk 6b, deliberate:
#   XDS-invoice-reconciliation already FAILs a per-invoice mismatch and WARNs
#   an invoice no cost row cites (F38's not-evaluable argument — untouched).
#   XDS-commitment-closure already decides closure where the term allows.
#   What was MISSING, and is added here: the cost-side orphan direction, the
#   period-PAIR match, correction cut-off discipline, and the eligibility
#   universe guard. All four cite Amendment 1 rather than a specification
#   sentence, so all four are DERIVED — the harness's own honesty mechanism
#   for rules that follow from the project's build spec rather than being
#   quoted from FOCUS. version_diff's impact half skips derived refs, which
#   is correct: an amendment citation cannot go stale against a FOCUS tag.

AMENDMENT_URL = "docs/Portfolio_Build_Spec_Amendment_1.docx"


def _civil_date(value):
    """The date AS WRITTEN, no timezone arithmetic anywhere (finding S7).

    billing_period.csv carries offset-aware timestamps (+02:00) while the
    cost data's period columns are naive. Any comparison that lets a session
    timezone interpret either side gives verdicts that depend on the
    analyst's machine: raw equality fails on SAST and passes on UTC, and
    even a cast-to-date shifts a day west of Greenwich. _ts() already keeps
    the civil clock (fromisoformat parses the offset, replace(tzinfo=None)
    drops it without converting), so .date() of that is the civil date the
    file states — identical in Cape Town, Berlin, Sydney and New York.
    """
    parsed = _ts(value)
    return parsed.date() if parsed else None


def make_invoice_orphan_check(spec):
    """A3.2 assertion 2, cost side: every InvoiceId a cost row carries must
    exist in invoice_detail.

    Chunk 6b covers the other direction (an invoice no cost row cites, WARN,
    F38). This is the harder failure: a cost row claiming membership of an
    invoice the invoice dataset has never heard of is not a timing gap, it
    is a broken reference — the supplemental dataset failing at the one
    thing it exists to be authoritative about.
    """
    def fn(ctx):
        out = []
        cost = ctx.cost_target()
        invoices = ctx.by_dataset("invoice_detail")
        if cost is None or not invoices:
            return out
        known = {row.get("InvoiceId")
                 for target in invoices for row in target.rows}
        known.discard(None)
        orphans = {}
        for row in cost.rows:
            invoice_id = row.get("InvoiceId")
            if invoice_id and invoice_id not in known:
                orphans[invoice_id] = orphans.get(invoice_id, 0) + 1
        for invoice_id in sorted(orphans):
            out.append(Violation(
                "XDS-invoice-orphan-cost-side", FAIL, "cross-dataset",
                f"{orphans[invoice_id]} cost row(s) carry InvoiceId "
                f"{invoice_id}, which does not exist in invoice_detail — a "
                f"reference to an invoice the authoritative dataset has "
                f"never heard of"))
        if not orphans and known:
            out.append(Violation(
                "XDS-invoice-orphan-cost-side", INFO, "cross-dataset",
                "every InvoiceId on a cost row exists in invoice_detail"))
        return out

    return Check(
        id="XDS-invoice-orphan-cost-side",
        title="Every cost-row InvoiceId exists in invoice_detail",
        fn=fn,
        refs=[SpecRef(
            "InvoiceId",
            "Amendment A3.2 assertion 2: orphan checks run in BOTH "
            "directions; a cost-row InvoiceId absent from invoice_detail is "
            "a hard failure. (Follows from the BilledCost reconciliation "
            "identity, which is unevaluable against a missing invoice.)",
            FAIL, AMENDMENT_URL, tag="v1.4", derived=True)],
        columns=(), binding=ANY,
    )


def make_period_pair_check(spec):
    """A3.2 assertion 3: every (BillingPeriodStart, BillingPeriodEnd) pair
    the cost data carries must exist as a row in billing_period.

    Chunk 6b's XDS-billing-period asserts the periods' internal geometry
    (no overlap) and reports charge-date containment. This asserts the
    JOIN: the pair itself, compared at civil-date grain per finding S7 —
    the first local run of the Stage 6 SQL failed on exactly this, with
    the same two files passing on a UTC machine and failing on a SAST one.
    """
    def fn(ctx):
        out = []
        cost = ctx.cost_target()
        declared = set()
        for target in ctx.by_dataset("billing_period"):
            for row in target.rows:
                pair = (_civil_date(row.get("BillingPeriodStart")),
                        _civil_date(row.get("BillingPeriodEnd")))
                if pair[0] and pair[1]:
                    declared.add(pair)
        if cost is None or not declared:
            return out
        missing = {}
        for row in cost.rows:
            pair = (_civil_date(row.get("BillingPeriodStart")),
                    _civil_date(row.get("BillingPeriodEnd")))
            if pair[0] and pair[1] and pair not in declared:
                missing[pair] = missing.get(pair, 0) + 1
        for pair in sorted(missing):
            out.append(Violation(
                "XDS-period-pair-match", FAIL, "cross-dataset",
                f"{missing[pair]} cost row(s) declare billing period "
                f"{pair[0]}..{pair[1]}, which has no row in billing_period "
                f"— the period authority does not know this period"))
        if not missing:
            out.append(Violation(
                "XDS-period-pair-match", INFO, "cross-dataset",
                f"every cost-row period pair exists in billing_period "
                f"({len(declared)} period(s) declared) — compared at "
                f"civil-date grain (S7)"))
        return out

    return Check(
        id="XDS-period-pair-match",
        title="Every cost-row billing-period pair exists in billing_period",
        fn=fn,
        refs=[SpecRef(
            "BillingPeriodStart",
            "Amendment A3.2 assertion 3: every BillingPeriodStart/End pair "
            "in Cost and Usage matches a billing_period row. Compared at "
            "civil-date grain — never through session-timezone conversion "
            "(Stage 6 finding S7).",
            FAIL, AMENDMENT_URL, tag="v1.4", derived=True)],
        columns=(), binding=ANY,
    )


def make_correction_discipline_check(spec):
    """Cut-off discipline: a ChargeClass='Correction' row restates a CLOSED
    billing period, and its invoice line says which one.

    The one row type permitted to speak about the past has to name the past
    it speaks about: its invoice_detail line carries a ReferenceInvoiceId
    different from its own InvoiceId, and the consumption date falls in a
    billing period whose status is Closed. A correction referencing an Open
    period is not a correction, it is a re-statement of the current period
    wearing the wrong flag — the accounting equivalent of backdating.
    """
    def fn(ctx):
        out = []
        cost = ctx.cost_target()
        if cost is None:
            return out
        corrections = [row for row in cost.rows
                       if row.get("ChargeClass") == "Correction"]
        if not corrections:
            return out

        invoice_refs = {}
        for target in ctx.by_dataset("invoice_detail"):
            for row in target.rows:
                invoice_refs.setdefault(row.get("InvoiceId"), set()).add(
                    row.get("ReferenceInvoiceId"))

        periods = []
        for target in ctx.by_dataset("billing_period"):
            for row in target.rows:
                start = _civil_date(row.get("BillingPeriodStart"))
                end = _civil_date(row.get("BillingPeriodEnd"))
                if start and end:
                    periods.append((start, end,
                                    str(row.get("BillingPeriodStatus"))))

        for row in corrections:
            invoice_id = row.get("InvoiceId")
            if not invoice_id:
                out.append(Violation(
                    "XDS-correction-discipline", WARN, "cross-dataset",
                    "a Correction row carries no InvoiceId — cut-off "
                    "discipline is not evaluable for it (which is not the "
                    "same as it being satisfied)"))
                continue
            refs_on_invoice = {r for r in invoice_refs.get(invoice_id, set())
                               if r and r != invoice_id}
            if invoice_refs and not refs_on_invoice:
                out.append(Violation(
                    "XDS-correction-discipline", FAIL, "cross-dataset",
                    f"Correction on invoice {invoice_id}: no line on that "
                    f"invoice carries a ReferenceInvoiceId naming the "
                    f"period being corrected"))
            consumed = _civil_date(row.get("ChargePeriodStart"))
            if consumed and periods:
                status = next((st for s, e, st in periods
                               if s <= consumed < e), None)
                if status is None:
                    out.append(Violation(
                        "XDS-correction-discipline", FAIL, "cross-dataset",
                        f"Correction consumption date {consumed} falls in "
                        f"no declared billing period"))
                elif status.lower() != "closed":
                    out.append(Violation(
                        "XDS-correction-discipline", FAIL, "cross-dataset",
                        f"Correction restates the period containing "
                        f"{consumed}, whose status is {status} — a "
                        f"correction must reference a Closed period"))
                else:
                    out.append(Violation(
                        "XDS-correction-discipline", INFO, "cross-dataset",
                        f"Correction restates a Closed period (consumption "
                        f"{consumed}) and its invoice names the reference "
                        f"— cut-off discipline holds"))
        return out

    return Check(
        id="XDS-correction-discipline",
        title="Corrections restate a Closed period and name it",
        fn=fn,
        refs=[SpecRef(
            "ChargeClass",
            "Amendment A3.2: a Correction row references a previously "
            "invoiced (Closed) billing period, and the invoice line "
            "carries ReferenceInvoiceId. (Follows from ChargeClass: "
            "'correction to a previously invoiced billing period'.)",
            FAIL, AMENDMENT_URL, tag="v1.4", derived=True)],
        columns=(), binding=ANY,
    )


def make_eligibility_universe_check(spec):
    """A3.3: the eligibility universe is fully explained, and coverage is
    reported against COVERABLE spend.

    x_CommitmentEligible is three-valued and the NULL carries meaning —
    but only two NULLs are legitimate: concept-not-applicable (non-usage,
    unused commitment) and era-predates-the-flag. A v1.2-era Usage row
    with demand and no verdict is bucket 6 of the Stage 6 disclosure
    query: unexplained, and unexplained is a failure. This also guards
    the regression this week's seed_data fix closed — if the flag stops
    being seeded, every v1.2 usage row lands here at once.

    The INFO line reports the two coverage figures side by side per
    currency: coverage of coverable vs the naive all-usage figure. Same
    numerator, two denominators, and the gap between them is the entire
    argument for eligibility-awareness.
    """
    def fn(ctx):
        out = []
        cost = ctx.cost_target()
        if cost is None:
            return out

        unexplained = 0
        per_currency = {}
        for row in cost.rows:
            if row.get("ChargeCategory") != "Usage":
                continue
            currency = row.get("BillingCurrency")
            flag = row.get("x_CommitmentEligible")
            unused = row.get("CommitmentDiscountStatus") == "Unused"
            era = row.get("x_SchemaEra")
            effective = _dec(row.get("EffectiveCost")) or Decimal(0)

            bucket = per_currency.setdefault(
                currency, {"covered": Decimal(0), "eligible": Decimal(0),
                           "demand": Decimal(0)})
            if not unused:
                bucket["demand"] += effective
            if flag is True:
                bucket["eligible"] += effective
                if row.get("PricingCategory") == "Committed":
                    bucket["covered"] += effective
            elif flag is None and era == "1.2" and not unused:
                unexplained += 1

        if unexplained:
            out.append(Violation(
                "XDS-eligibility-universe", FAIL, "cross-dataset",
                f"{unexplained} v1.2-era Usage row(s) have no "
                f"x_CommitmentEligible verdict and are not Unused — the "
                f"eligibility universe is not fully explained (Stage 6 "
                f"disclosure bucket 6, which must be empty)"))
        for currency in sorted(k for k in per_currency if k):
            b = per_currency[currency]
            if b["eligible"] > 0 and b["demand"] > 0:
                coverable = 100 * b["covered"] / b["eligible"]
                naive = 100 * b["covered"] / b["demand"]
                out.append(Violation(
                    "XDS-eligibility-universe", INFO, "cross-dataset",
                    f"[{currency}] coverage of coverable "
                    f"{coverable:.1f}% vs naive all-usage {naive:.1f}% — "
                    f"same numerator, two denominators; only the first "
                    f"respects eligibility"))
        return out

    return Check(
        id="XDS-eligibility-universe",
        title="Eligibility universe fully explained; coverage of coverable reported",
        fn=fn,
        refs=[SpecRef(
            "CommitmentDiscountId",
            "Amendment A3.3: coverage is measured against coverable spend, "
            "eligibility taken from the x_CommitmentEligible flag seeded in "
            "the data; rows without the flag are disclosed by era, never "
            "silently treated as ineligible.",
            FAIL, AMENDMENT_URL, tag="v1.4", derived=True)],
        columns=(), binding=ANY,
    )


# =============================================================================
# 6f. THE EMPTY-STRING SWEEP — chunk 7
# =============================================================================
# FINDING F40. THE SPECIFICATION STATES THIS RULE TWICE, AT TWO SEVERITIES, AND
# STAGE 3 CITED THE WEAKER ONE.
#
#   string_handling.md   "Empty strings and strings consisting solely of spaces
#                         SHOULD NOT be used in not-nullable string columns."
#
#   null_handling.md     "Columns MUST NOT use empty strings or placeholder
#                         values such as 0 for numeric columns or 'Not
#                         Applicable' for string columns to represent a null or
#                         not having a value, REGARDLESS OF WHETHER THE COLUMN
#                         ALLOWS NULLS OR NOT."
#
# Finding F2 refined concluded that Azure's 1,406 empty strings break a
# recommendation rather than a requirement, and that conclusion has been carried
# through the whole of Stage 4. It rests on StringHandling alone. NullHandling is
# stricter, unconditional on nullability, and squarely on point: an empty string
# in CommitmentDiscountId on a row with no commitment discount is an empty string
# used to represent not having a value. That is the MUST NOT, verbatim.
#
# THE SCOPE THAT DECIDES IT is in null_handling.md's opening line: "All columns
# defined in the FOCUS specification MUST follow the null handling requirements
# listed below. Custom columns SHOULD also follow the same formatting
# requirements."
#
# So the severity depends on WHOSE COLUMN IT IS:
#
#   CommitmentDiscountId, CommitmentDiscountName    FOCUS-defined  ->  236  FAIL
#   the eleven x_ columns                           custom         -> 1170  WARN
#
# One defect, two verdicts, and the boundary is a single sentence of preamble.
# Reporting all 1,406 at either severity would be wrong in one direction or the
# other, and no validator that treats empty strings as a single phenomenon can
# produce this answer.

def _is_blank_string(value):
    """Empty, or nothing but spaces. StringHandling names both cases explicitly,
    and the whitespace-only one is the harder to spot by eye — which is why the
    specification bothered to name it."""
    return isinstance(value, str) and value.strip() == ""


def make_empty_string_checks(spec):
    """Two checks, one phenomenon, severity decided by who defined the column."""
    focus_columns = set(spec)

    must_text = ("Columns MUST NOT use empty strings or placeholder values such as 0 "
                 "for numeric columns or \"Not Applicable\" for string columns to "
                 "represent a null or not having a value, regardless of whether the "
                 "column allows nulls or not.")
    should_text = ("Empty strings and strings consisting solely of spaces SHOULD NOT "
                   "be used in not-nullable string columns.")
    null_url = ("https://raw.githubusercontent.com/FinOps-Open-Cost-and-Usage-Spec/"
                "FOCUS_Spec/v1.2/specification/attributes/null_handling.md")
    string_url = ("https://raw.githubusercontent.com/FinOps-Open-Cost-and-Usage-Spec/"
                  "FOCUS_Spec/v1.2/specification/attributes/string_handling.md")

    def sweep(ctx, want_focus, severity):
        """One violation per offending VALUE, not per column.

        The first version grouped by column and reported "CommitmentDiscountId:
        118 rows". Readable, and wrong twice over.

        It made the MUST count read 2 when 236 values breach the rule — the
        count of a conformance report should be the count of breaches, not the
        count of places they cluster. And it attached each finding to no row at
        all, so the proving run could not match the planted
        EMPTY_STRING_PLACEHOLDER to the only check written to catch it: the check
        fired, the fixture reported MISSED, and both were behaving correctly.

        Flooding is a DISPLAY problem and is solved where display happens: the
        per-target report rolls a check up to one line once it exceeds a handful
        of violations. Counts stay honest; the screen stays readable.
        """
        out = []
        for i, row in ctx.rows_in_scope():
            for column, value in row.items():
                if not _is_blank_string(value):
                    continue
                if (column in focus_columns) != want_focus:
                    continue
                out.append(Violation(
                    ctx.check.id, severity, ctx.target.name,
                    f"{column} holds an empty string where the value is absent"
                    + ("" if want_focus else " (custom column — a SHOULD here, a "
                       "MUST for FOCUS-defined columns)"),
                    row_index=i,
                    expected_id=row.get("x_ExpectedViolation", "") or ""))
        return out

    return [
        Check(
            id="EMPTY-STRING-focus-columns",
            title="No empty strings standing in for null (FOCUS-defined columns)",
            fn=lambda ctx: sweep(ctx, want_focus=True, severity=FAIL),
            refs=[SpecRef("NullHandling", must_text, FAIL, null_url)],
            columns=(),
            # RAW_VALUES, not PER_LAYER. The guardrail is about the TRANSFORMATION
            # applied, not the folder a file sits in: focus_unified normalises ''
            # to NULL by decision D3, so a sweep there reports zero and looks like
            # a pass. The negative fixtures are never merged and never normalised,
            # so they must be swept — and a PER_LAYER binding would have excluded
            # them and left the planted EMPTY_STRING_PLACEHOLDER permanently
            # uncaught by the one check written to find it.
            binding=RAW_VALUES,
            era_mode=ERA_VALUE,
        ),
        Check(
            id="EMPTY-STRING-custom-columns",
            title="No empty strings standing in for null (custom x_ columns)",
            fn=lambda ctx: sweep(ctx, want_focus=False, severity=WARN),
            refs=[SpecRef("StringHandling", should_text, WARN, string_url)],
            columns=(), binding=RAW_VALUES, era_mode=ERA_VALUE,
        ),
    ]


def write_report(results, cross_violations, spec, lifecycle, refused,
                 caught, planted):
    """Generate docs/conformance-report.md from the run that just happened.

    GENERATED, NEVER WRITTEN BY HAND. A report typed out separately is accurate
    on the day it is typed and drifts from the code the first time either
    changes — and nothing in the file itself tells a reader which day that was.
    Every number below comes from the run that produced it.

    The section a reader should be steered to is LIMITATIONS. A conformance
    report that lists only what passed invites the reading that everything else
    was checked and found clean. **What this harness cannot check is a property
    of the specification and of the data, not an admission**, and it is the part
    a practitioner most needs before trusting a green result.
    """
    out = []
    w = out.append

    parsed_rules, _ = rules.nullability_rules(spec)
    derived = [c for c in REGISTRY if c.is_derived]
    cited = len(REGISTRY) - len(derived)

    w("# FOCUS Conformance Report")
    w("")
    w(f"**Generated:** {datetime.now():%d %B %Y} by `validate.py` "
      f"— every figure below comes from that run.  ")
    w("**Specification:** cost and usage at **v1.2**; the supplemental datasets "
      "at **v1.4**, since they do not exist before v1.3.  ")
    w("**Method:** rules are parsed from the specification's own requirement "
      "sentences at a pinned tag, not transcribed. Severity is taken from the "
      "RFC 2119 keyword in the sentence each check cites.")
    w("")
    w("Reproduce with:")
    w("")
    w("```")
    w("python3 spec_source.py       # fetch and parse the specification at 5 tags")
    w("python3 seed_data.py         # synthetic fixtures across three schema eras")
    w("python3 self_test.py         # generator self-test")
    w("python3 build_unified.py     # sanitise the real export, merge the layers")
    w("python3 generate_layer_c.py  # the v1.4 supplemental datasets")
    w("python3 validate.py --report # validate, and write this report")
    w("```")
    w("")

    # ---------------------------------------------------------------- verdict
    w("## Verdict")
    w("")
    w("| Dataset | Rows | MUST (FAIL) | SHOULD (WARN) | Observations |")
    w("|---|---:|---:|---:|---:|")
    for target, violations, _, _ in results:
        if target.kind == "negative":
            continue
        f = sum(1 for v in violations if v.severity == FAIL)
        n = sum(1 for v in violations if v.severity == WARN)
        i = sum(1 for v in violations if v.severity == INFO)
        w(f"| `{target.name}` | {len(target.rows)} | **{f}** | {n} | {i} |")
    cf = sum(1 for v in cross_violations if v.severity == FAIL)
    cw = sum(1 for v in cross_violations if v.severity == WARN)
    ci = sum(1 for v in cross_violations if v.severity == INFO)
    w(f"| cross-dataset | — | **{cf}** | {cw} | {ci} |")
    w("")

    # ------------------------------------------------------------- the proof
    w("## Does the harness detect anything?")
    w("")
    w(f"**{caught} of {planted} planted violations caught by the check that names "
      f"the rule.**")
    w("")
    w("A validator that has only ever seen valid data has never been shown to "
      "detect anything. `data/negative/` holds deliberately broken rows, one "
      "fault each, every row declaring what it breaks. A violation counts only "
      "when the check that fires is the check implementing the rule the row "
      "names — anything else is a hit on the right row for the wrong reason, "
      "which is how an earlier version of this report claimed full coverage it "
      "did not have.")
    w("")
    negative = [(t, v) for t, v, _, _ in results if t.kind == "negative"]
    if negative:
        target, violations = negative[0]
        w("| Planted violation | Caught by |")
        w("|---|---|")
        for i, row in enumerate(target.rows):
            eid = row.get("x_ExpectedViolation")
            if not eid:
                continue
            wanted = NEGATIVE_EXPECTATIONS.get(eid) or []
            hits = sorted({v.check_id for v in violations if v.row_index == i
                           and any(v.check_id.startswith(x) for x in wanted)})
            w(f"| `{eid}` | {', '.join(f'`{h}`' for h in hits) or '**not caught**'} |")
        w("")

    # ------------------------------------------------------------- inventory
    w("## What was checked")
    w("")
    w(f"**{len(REGISTRY)} checks.** {cited} cite a specification sentence; "
      f"{len(derived)} {'is' if len(derived) == 1 else 'are'} *derived* — "
      f"{'it follows' if len(derived) == 1 else 'they follow'} from the specification "
      f"without being stated in it, and {'is' if len(derived) == 1 else 'are'} labelled as such because a derived "
      f"rule filed quietly among quoted ones devalues every quoted one beside it.")
    w("")
    families = {}
    for check in REGISTRY:
        families[check.id.split("-")[0]] = families.get(check.id.split("-")[0], 0) + 1
    w("| Family | Checks |")
    w("|---|---:|")
    labels = {"AV": "Allowed values", "NULL": "Nullability (parsed)",
              "METRIC": "Metric validation", "XCOL": "Cross-column value rules",
              "SKU": "SkuPriceDetails keys and types", "FMT": "Value format",
              "PERIOD": "Charge period ordering *(derived)*",
              "EMPTY": "Empty strings standing in for null",
              "PRESENCE": "Mandatory column presence", "SVC": "Service taxonomy",
              "COMMIT": "Commitment aggregates", "LC": "Layer C (v1.4)",
              "META": "Schema observations", "WARN": "Advisory"}
    for prefix, n in sorted(families.items(), key=lambda kv: -kv[1]):
        w(f"| {labels.get(prefix, prefix)} | {n} |")
    w(f"| cross-dataset | {len(CROSS_REGISTRY)} |")
    w("")

    # ------------------------------------------------------------- coverage
    w("## What the harness cannot check, and why")
    w("")
    w(f"Of **{len(parsed_rules) + len(refused)}** nullability statements at "
      f"v1.2, **{len(parsed_rules)}** are implemented and **{len(refused)}** are "
      f"not machine-checkable.")
    w("")
    w("These are not gaps in this harness. They are conditions the row does not "
      "carry — facts about the world that no validator reading a dataset can "
      "evaluate. **Naming them, with reasons, is worth more than a coverage "
      "percentage**, and it is a claim the reference FOCUS Validator cannot make "
      "at all, because it does not evaluate conditional requirements.")
    w("")
    w("| Column | Requirement | Why not |")
    w("|---|---|---|")
    for item in refused:
        text = rules.normalise(item["text"])
        text = text if len(text) <= 96 else text[:95] + "…"
        w(f"| `{item['column']}` | {text} | {item['reason']} |")
    w("")

    # ------------------------------------------------------------- findings
    w("## Findings")
    w("")
    any_fail = False
    for target, violations, _, suppressed in results:
        if target.kind == "negative":
            continue
        fails = [v for v in violations if v.severity == FAIL]
        warns = [v for v in violations if v.severity == WARN]
        if not fails and not warns:
            continue
        any_fail = any_fail or bool(fails)
        w(f"### `{target.name}`")
        w("")
        by_check = {}
        for v in fails + warns:
            by_check.setdefault((v.severity, v.check_id), []).append(v)
        for (severity, check_id), group in sorted(by_check.items()):
            check = next((c for c in REGISTRY if c.id == check_id), None)
            citation = check.refs[0] if check and check.refs else None
            w(f"**{severity} — `{check_id}` — {len(group)} violation(s)**")
            w("")
            if citation:
                w(f"> {rules.normalise(citation.text)}")
                w(">")
                w(f"> — [{citation.column}, {citation.tag}]({citation.url})"
                  + ("  *(derived, not quoted)*" if citation.derived else ""))
                w("")
            w(f"{group[0].message}")
            w("")
        if suppressed:
            total = sum(n for _, n in suppressed)
            w(f"**{total} findings suppressed** on this dataset because the "
              f"column they depend on holds `''` rather than NULL. The rule they "
              f"name is not the rule that is broken; the placeholder itself is "
              f"reported above.")
            w("")

    if not any_fail:
        w("No MUST-level violations on any dataset.")
        w("")

    # ------------------------------------------------------ cross-dataset
    if cross_violations:
        w("## Cross-dataset")
        w("")
        w("Rules spanning cost and usage and the supplemental datasets. These "
          "cannot be expressed against a single table — the commitment term and "
          "the invoice total live in Layer C, which is why Layer C exists.")
        w("")
        for v in cross_violations:
            w(f"- **{v.severity}** `{v.check_id}` — {v.message}")
        w("")

    # ------------------------------------------------------- limitations
    w("## Limitations")
    w("")
    w("A conformance report listing only what passed invites the reading that "
      "everything else was checked and found clean. It was not.")
    w("")
    w(f"- **{len(refused)} conditional requirements are not machine-checkable** "
      f"and are listed above with reasons.")
    w("- **Numeric tolerance is a harness policy, not a specification "
      "requirement.** `numeric_format.md` states that the specification does not "
      "require a specific level of precision and leaves it to the provider. The "
      f"tolerance used here is `{TOLERANCE}`.")
    w("- **Presence and nullability are separate questions** and are reported "
      "separately. A Conditional column being absent is not a defect unless its "
      "condition holds, and whether it holds is usually not in the data.")
    w("- **Checks are era-aware at row level.** A rule about a column introduced "
      "later is not applied to earlier rows. Value constraints are not gated "
      "this way: a value that is present is checked regardless of the version a "
      "row declares, because the declared version is a floor rather than a "
      "description.")
    w("- **The empty-string sweep never runs against the merged view**, which "
      "normalises `''` to NULL. Run there it would report zero and read as a "
      "pass. It binds only to datasets holding values as the producer wrote them.")
    w("- **Two invariants presuppose full-term coverage of a commitment.** Where "
      "the supplemental dataset supplies the term, this is decided; where it "
      "does not, closure is reported as not evaluable rather than as balanced.")
    w("")

    path = os.path.join(ROOT, "docs", "conformance-report.md")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write("\n".join(out) + "\n")
    return path


def load_spec():
    index = os.path.join(SPEC_DIR, "spec_v1.2.json")
    life = os.path.join(SPEC_DIR, "lifecycle.json")
    if not (os.path.exists(index) and os.path.exists(life)):
        print("Specification index not found. Run chunk 1 first:")
        print("    python3 src/spec_source.py")
        sys.exit(2)
    with open(index) as f:
        spec = json.load(f)
    if spec and "subsection_tables" not in next(iter(spec.values())):
        print("docs/spec/spec_v1.2.json predates chunk 5 and lacks the "
              "'subsection_tables' field.\nRe-run the spec source layer first:")
        print("    python3 spec_source.py")
        sys.exit(2)
    with open(life) as f:
        lifecycle = json.load(f)
    return spec, lifecycle


def build_registry(spec, lifecycle):
    REGISTRY.clear()
    register(make_declaration_drift_check(lifecycle))

    # chunk 2 — value constraints
    for column in ENUM_COLUMNS:
        if column not in spec:
            continue
        check = make_allowed_values_check(column, spec)
        if check:
            register(check)

    # chunk 3 — structural
    register(make_presence_check(spec, lifecycle))
    register(make_service_parent_check(spec))
    duplicate = make_resource_name_duplicate_check(spec)
    if duplicate:
        register(duplicate)

    # chunk 4 — metrics
    for check in make_nonnegative_checks(spec):
        register(check)
    for check in make_product_checks(spec):
        register(check)
    for maker in (make_commitment_closure_check, make_commitment_split_check):
        check = maker(spec)
        if check:
            register(check)

    # chunk 5 — format and cross-column
    for check in make_value_condition_checks(spec):
        register(check)
    currency = make_currency_check(spec)
    if currency:
        register(currency)
    register(make_charge_period_order_check(spec))
    for check in make_sku_price_details_checks(spec):
        register(check)

    # chunk 6a — Layer C, at v1.4
    for dataset in sorted(SUPPLEMENTAL_FILES):
        path = os.path.join(SPEC_DIR, f"spec_v1.4_{dataset}.json")
        if not os.path.exists(path):
            continue
        with open(path) as f:
            for check in make_layer_c_checks(dataset, json.load(f)):
                register(check)

    # chunk 6b — cross-dataset
    CROSS_REGISTRY.clear()
    for maker in (make_invoice_reconciliation_check,
                  make_commitment_term_closure_check,
                  make_billing_period_check,
                  # Stage 6 alignment assertions (6e-bis) — Amendment A3.2/A3.3
                  make_invoice_orphan_check,
                  make_period_pair_check,
                  make_correction_discipline_check,
                  make_eligibility_universe_check):
        check = maker(spec)
        if check:
            register_cross(check)

    # chunk 7 — the SHOULD tier
    for check in make_empty_string_checks(spec):
        register(check)

    parsed, refused = rules.nullability_rules(spec)
    for n, rule in enumerate(parsed):
        register(make_nullability_check(rule, n))
    return refused


# =============================================================================
# 7. RUNNING
# =============================================================================

def run_target(target, spec, lifecycle):
    """Every registered check against one dataset. Returns (violations, notes)."""
    violations, notes, contexts = [], [], []
    for check in REGISTRY:
        # BINDING — enforced before the check is handed a single row.
        if check.binding == PER_LAYER and target.kind != "layer":
            notes.append((check.id, f"not run on {target.name}: bound to per-layer "
                                    "views (D3 normalises '' to NULL in unified)"))
            continue
        if check.binding == RAW_VALUES and target.kind in ("unified", "supplemental"):
            why = ("D3 normalises '' to NULL here" if target.kind == "unified"
                   else "D17 reads '' as NULL from CSV")
            notes.append((check.id, f"not run on {target.name}: {why}, so a sweep "
                                    f"would report zero and read as a pass"))
            continue
        if check.binding == UNIFIED and target.kind != "unified":
            notes.append((check.id, f"not run on {target.name}: needs the merged view"))
            continue

        if check.dataset != target.dataset:
            continue                      # different dataset; silently not applicable

        missing = [c for c in check.columns if c not in target.columns]
        if missing:
            notes.append((check.id, f"column absent from {target.name}: {', '.join(missing)}"))
            continue

        ctx = Context(target, spec, lifecycle, check)
        contexts.append(ctx)
        skipped = ctx.skipped_by_era()
        if skipped:
            notes.append((check.id, f"{skipped} of {len(target.rows)} rows out of era scope"))
        violations.extend(check.fn(ctx))
    suppressed = [item for c in contexts for item in c.suppressed]
    return violations, notes, suppressed


# =============================================================================
# THE NEGATIVE-PROOF EXPECTATION MAP
# =============================================================================
# FINDING F30. The first version of report_negative() counted a planted
# violation as caught if ANY violation landed on that row. It reported 14 of 14
# after chunk 3 — and it was wrong.
#
# The negative file leaves PricingCurrencyContractedUnitPrice and
# PricingCurrencyListUnitPrice null on every row, which is itself a breach of a
# v1.2 conditional rule. So every row trips those two checks, and a row-level
# match credited the harness with detecting CHARGE_PERIOD_INVERTED when what it
# had actually noticed was an unrelated null three columns away.
#
# A green result that is confidently wrong. Which is the failure mode this whole
# project is built to avoid, appearing in the instrument that measures it.
#
# So the proof is now specific: each planted violation names the check that must
# catch it. Anything else on the row is incidental and reported separately.
# Entries mapping to None are not yet expected — the chunk that delivers them is
# named, so the coverage gap stays visible instead of being papered over.
NEGATIVE_EXPECTATIONS = {
    "NULL_IN_MANDATORY_COLUMN":           ["NULL-ServiceCategory"],
    "SATELLITE_WITHOUT_ANCHOR":           ["NULL-ResourceName"],
    "ORPHAN_COMMITMENT_STATUS":           ["NULL-CommitmentDiscountStatus"],
    "ORPHAN_CAPACITY_RESERVATION_STATUS": ["NULL-CapacityReservationStatus"],
    "TAX_WITH_PRICING_CATEGORY":          ["NULL-PricingCategory"],
    "INVALID_ENUM_VALUE":                 ["AV-ChargeCategory"],
    "INVALID_CHARGECLASS_VALUE":          ["XCOL-ChargeClass"],
    # Still to come. The chunk that delivers each is named so the gap is legible.
    "EMPTY_STRING_PLACEHOLDER":            ["EMPTY-STRING"],
    "CURRENCY_NOT_ISO_4217":                 ["FMT-ISO4217-BillingCurrency"],
    "CHARGE_PERIOD_INVERTED":                ["PERIOD-ordering"],
    "NEGATIVE_UNIT_PRICE":                 ["METRIC-nonneg-ListUnitPrice"],
    "UNIT_PRICE_COST_MISMATCH":            ["METRIC-product-ContractedCost"],
    "SKU_PRICE_DETAILS_BAD_KEYS":            ["SKU-key-prefix"],
    "PURCHASE_WITH_USAGE_BASED_FREQUENCY":   ["XCOL-ChargeFrequency"],
}


def report_negative(violations, target):
    """The proving run: was each planted violation caught BY THE RIGHT CHECK?

    The fixtures annotate themselves — every row carries x_ExpectedViolation —
    so the count is computed from the data. But the annotation names a RULE, and
    a harness only earns the point if the rule it fired is that rule. See F30
    above for what happens otherwise.
    """
    expected = {}
    for i, row in enumerate(target.rows):
        eid = row.get("x_ExpectedViolation")
        if eid:
            expected.setdefault(eid, []).append(i)

    print(f"\n  Planted violations: {sum(len(v) for v in expected.values())}")
    print(f"  {'expected violation':<38} {'row':>4}  {'status':<12} caught by")
    print("  " + "-" * 82)

    caught, pending, incidental_total = 0, 0, 0
    for eid in sorted(expected):
        wanted = NEGATIVE_EXPECTATIONS.get(eid, [])
        for idx in expected[eid]:
            hits = sorted({v.check_id for v in violations if v.row_index == idx})
            if wanted is None:
                status, by = "not yet", "(due in a later chunk)"
                pending += 1
            elif not wanted:
                status, by = "UNMAPPED", "no expectation declared — add one"
            else:
                matched = [h for h in hits if any(h.startswith(w) for w in wanted)]
                if matched:
                    caught += 1
                    status, by = "CAUGHT", ", ".join(matched)
                else:
                    status, by = "MISSED", f"expected {'/'.join(wanted)}"
            incidental = [h for h in hits
                          if not (wanted and any(h.startswith(w) for w in wanted))]
            incidental_total += len(incidental)
            print(f"  {eid:<38} {idx:>4}  {status:<12} {by}")

    total = sum(len(v) for v in expected.values())
    print("  " + "-" * 82)
    print(f"  {caught} of {total} caught by the check that names the rule.")
    print(f"  {pending} awaiting a later chunk.")
    if incidental_total:
        print(f"  {incidental_total} incidental hits — real violations, but not the rule")
        print(f"    the row names. The fixture breaches conditional rules beyond the")
        print(f"    ones planted, so a row-level match would credit the harness for")
        print(f"    noticing those instead (findings F30, F31).")
    else:
        print(f"  0 incidental hits — every violation the harness raises on this file")
        print(f"    is one the row declares. One fault per row, as the fixture intends,")
        print(f"    so this number staying at zero is now a usable regression signal")
        print(f"    (finding F31 resolved).")
    return caught, total


def main():
    ap = argparse.ArgumentParser(description="FOCUS conformance harness (Stage 4)")
    ap.add_argument("--negative", action="store_true", help="run the proving set only")
    ap.add_argument("--list", action="store_true", help="list checks and horizons")
    ap.add_argument("--report", action="store_true",
                    help="also write docs/conformance-report.md")
    args = ap.parse_args()

    spec, lifecycle = load_spec()
    refused = build_registry(spec, lifecycle)

    print("validate.py — FOCUS conformance harness, Stage 4 chunk 7")
    print("=" * 74)
    print(f"Specification: v1.2, {len(spec)} columns, parsed by spec_source.py")
    print(f"Checks registered: {len(REGISTRY)}")
    parsed_rules, _ = rules.nullability_rules(spec)
    total = len(parsed_rules) + len(refused)
    print(f"Nullability statements at v1.2: {total} — "
          f"{len(parsed_rules)} implemented, {len(refused)} not machine-checkable")

    if args.list:
        print(f"\n{'check':<32} {'sev':<5} {'expressible':<16} spec")
        print("-" * 100)
        for c in REGISTRY:
            frm, to = horizons(c, lifecycle)
            window = f"{frm} onward" if not to else f"{frm} to {to} (excl)"
            print(f"{c.id:<32} {c.severity:<5} {window:<16} {c.refs[0].short(48)}")
        print("\nA check's window is computed from INTRODUCED and REMOVED, so the")
        print("harness can say which of its own checks a version upgrade deletes")
        print("before anything is run. That is finding F22 made operational.")
        return 0

    found, missing = discover()
    print(f"\nDatasets discovered:")
    for t in found:
        print(f"  {t.name:<18} {len(t.rows):>4} rows x {len(t.columns):>3} cols   "
              f"{os.path.relpath(t.path, ROOT)}")
    for name, folder, kind in missing:
        print(f"  {name:<18}    absent          {os.path.relpath(folder, ROOT)}/")

    if any(name == "real" for name, _, _ in missing):
        print("\n  NOTE — data/raw-sanitised/ is absent. build_unified.py declares it")
        print("  (line 37) but never writes it: the sanitised real rows exist only as")
        print("  an in-memory view inside that script. The chunk 7 empty-string sweep")
        print("  binds to per-layer views, so on the real layer it has nowhere")
        print("  conformant to point — data/raw/ is unsanitised and unpublishable,")
        print("  and data/unified/ has already normalised '' to NULL by D3.")
        print("  Resolve before chunk 7. It is a small addition to build_unified.py.")

    if not found:
        print("\nNo datasets found. Nothing to validate.")
        return 2

    exit_code = 0
    results = []
    caught = planted = 0
    for target in found:
        # --report needs every target INCLUDING the negative set, because the
        # proving run is part of the report: a conformance report that omits the
        # evidence its instrument works is an assertion, not a report.
        if not args.report:
            if args.negative and target.kind != "negative":
                continue
            if not args.negative and target.kind == "negative":
                continue

        print(f"\n{'=' * 74}")
        print(f"TARGET: {target.name}   ({target.kind})")
        print("=" * 74)

        eras = {}
        for row in target.rows:
            era = row.get("x_SchemaEra") or "(unlabelled)"
            eras[era] = eras.get(era, 0) + 1
        print("  eras present: " + ", ".join(f"{k} ({v})" for k, v in sorted(eras.items())))

        violations, notes, suppressed = run_target(target, spec, lifecycle)

        if notes:
            print(f"\n  Scope notes ({len(notes)}):")
            for cid, note in notes:
                print(f"    {cid:<32} {note}")

        if suppressed:
            total_sup = sum(n for _, n in suppressed)
            print(f"\n  EMPTY-STRING SUPPRESSION (finding F32): {total_sup} findings")
            for cid, n in sorted(suppressed, key=lambda x: -x[1]):
                print(f"    {cid:<44} {n}")
            print("    These fired only because a column holds '' where it means NULL.")
            print("    '' is not null, so cascade conditions read as satisfied and")
            print("    demand values on rows that have none. Reported here rather than")
            print("    as MUST failures, because the rule they name is not the rule")
            print("    that is broken. The placeholder itself is reported by the")
            print("    empty-string checks — as a MUST for FOCUS-defined columns")
            print("    and a SHOULD for custom ones (finding F40).")

        fails = [v for v in violations if v.severity == FAIL]
        warns = [v for v in violations if v.severity == WARN]
        infos = [v for v in violations if v.severity == INFO]

        results.append((target, violations, notes, suppressed))

        if target.kind == "negative":
            caught, planted = report_negative(violations, target)
        else:
            print(f"\n  MUST violations (FAIL): {len(fails)}")
            print(f"  SHOULD deviations (WARN): {len(warns)}")
            print(f"  Observations (INFO):      {len(infos)}")
            # Roll a check up once it exceeds a handful of hits. A conformance
            # report that prints 236 near-identical lines is one nobody reads to
            # the end, and the counts above are already exact.
            def show(violations, label):
                by_check = {}
                for v in violations:
                    by_check.setdefault(v.check_id, []).append(v)
                for check_id, group in sorted(by_check.items()):
                    if len(group) > 5:
                        columns = sorted({v.message.split(" holds")[0].split(" =")[0]
                                          for v in group})
                        detail = (f"across {len(columns)} columns: "
                                  f"{', '.join(columns[:6])}"
                                  + (" ..." if len(columns) > 6 else "")
                                  ) if len(columns) > 1 else group[0].message
                        print(f"    {label}  {check_id:<30} {len(group)} violations, "
                              f"{detail}")
                    else:
                        for v in group:
                            print(f"    {label}  row {v.row_index:>4}  "
                                  f"{v.check_id:<28} {v.message}")

            show(fails, "FAIL")
            show(warns, "WARN")
            for v in infos[:20]:
                print(f"    INFO  {v.check_id:<28} {v.message}")
            if fails:
                exit_code = 1

    print(f"\n{'=' * 74}")
    # --- cross-dataset phase -------------------------------------------------
    cross_violations, cross_ran = [], False
    if CROSS_REGISTRY and len(found) > 1:
        print(f"\n{'=' * 74}")
        print("CROSS-DATASET  (chunk 6b — rules spanning cost_and_usage and Layer C)")
        print("=" * 74)
        ctx = CrossContext(found, spec, lifecycle)
        cross_violations = []
        cross_ran = True
        for check in CROSS_REGISTRY:
            ctx.check = check
            cross_violations.extend(check.fn(ctx))
        cross_fail = [v for v in cross_violations if v.severity == FAIL]
        cross_warn = [v for v in cross_violations if v.severity == WARN]
        cross_info = [v for v in cross_violations if v.severity == INFO]
        print(f"\n  MUST violations (FAIL): {len(cross_fail)}")
        print(f"  SHOULD deviations (WARN): {len(cross_warn)}")
        print(f"  Observations (INFO):      {len(cross_info)}")
        for v in cross_fail + cross_warn + cross_info:
            print(f"    {v.severity:<5} {v.check_id:<26} {v.message}")
        if cross_fail:
            exit_code = 1

    derived = [c.id for c in REGISTRY if c.is_derived]
    if args.report:
        path = write_report(results, cross_violations, spec, lifecycle,
                            refused, caught, planted)
        print(f"\nConformance report written: {os.path.relpath(path, ROOT)}")

    print(f"Chunks 2-7 registered. {len(REGISTRY) - len(derived)} checks cite a")
    n = len(derived)
    print(f"specification sentence; {n} {'is' if n == 1 else 'are'} DERIVED — "
          f"{'it follows' if n == 1 else 'they follow'} from")
    print(f"the spec without being stated in it: {', '.join(derived) or 'none'}.")
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
