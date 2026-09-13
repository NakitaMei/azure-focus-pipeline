"""
build_unified.py — Portfolio Project 1, Stage 3 chunk 9

Builds `focus_unified`: the real Azure export and both synthetic layers in ONE
view, every row flagged for what it is.

Three jobs, in order:

  1. SANITISE the real export (decision D1, finding F6). The raw export carries
     the account holder's name in five columns and real tenancy GUIDs in six
     more. This runs on every pull, so the protection is a CONTROL rather than a
     habit someone has to remember.

  2. MERGE real + v1.2 synthetic + pre-1.2 legacy. Not the negative fixtures —
     those are deliberately broken and are excluded by name (decision from
     chunk 6).

  3. NORMALISE empty strings to NULL at this boundary only (decision D3), and
     PUBLISH the count. Normalisation that is counted is documentation;
     normalisation that is silent is data laundering.

Run:  python3 build_unified.py
"""

import hashlib
import json
import os
import re
import sys

import duckdb

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE) if os.path.basename(HERE) == "src" else HERE

RAW_DIR        = os.path.join(ROOT, "data", "raw")
SANITISED_DIR  = os.path.join(ROOT, "data", "raw-sanitised")
SYNTHETIC_V12  = os.path.join(ROOT, "data", "synthetic", "v1.2")
SYNTHETIC_PRE  = os.path.join(ROOT, "data", "synthetic", "pre-1.2")
UNIFIED_DIR    = os.path.join(ROOT, "data", "unified")


# =============================================================================
# 1. SANITISATION  (decision D1)
# =============================================================================
# THE DESIGN CONSTRAINT THAT SHAPES EVERYTHING HERE:
# this script is committed to a public repository. So it must NOT contain the
# real name or the real GUIDs — a lookup table mapping "real value" -> "fake
# value" would publish exactly what it is meant to hide.
#
# Therefore sanitisation works BY RULE, never by lookup:
#   - name-bearing columns are overwritten wholesale, without inspecting them
#   - GUIDs are replaced with a pseudonym DERIVED from the original by hashing
#
# Hashing gives stability without storage: the same input always produces the
# same pseudonym, so joins and GROUP BYs still work across the whole dataset and
# across future pulls — but the mapping exists nowhere, not even here.

SALT = "project-1-azure-focus"          # makes the pseudonyms specific to this project
# The salt is the project's ORIGINAL working name and is deliberately unchanged
# after the repository was renamed: every pseudonym in data/raw-sanitised/,
# data/unified/ and data/stage7/ is derived from it, so changing it would
# re-key all of them and break every cross-reference in the notes.

# Overwritten without being read. Content is irrelevant; these columns carry a
# person's name by definition, so there is nothing to inspect or preserve.
NAME_COLUMNS = {
    "BillingAccountName":   "Portfolio Sandbox Account",
    "x_BillingAccountName": "Portfolio Sandbox Account",
    "x_BillingProfileName": "Portfolio Sandbox Profile",
    "x_CustomerName":       "Portfolio Sandbox Customer",
    "x_InvoiceSectionName": "Portfolio Sandbox Section",
}

# EVERY string column is scanned for identifiers, not a chosen list of them.
#
# The first version of this script sanitised only six named "tenancy" columns
# and deliberately spared x_SkuDetails and x_SkuMeterId, reasoning that those
# hold Azure's PUBLIC meter catalogue GUIDs — the same for every customer, so
# identifying a product rather than a person.
#
# The independent verification below caught two leaks (finding F21):
#   - x_SkuDetails holds BOTH catalogue GUIDs AND the subscription GUID
#   - the billing profile code appears inside BillingAccountId as well as in
#     its own column
#
# Column-by-column judgement was the mistake. It required knowing, for all 96
# columns, exactly what each may contain — and being right every time, for every
# future export. Scanning everything requires knowing nothing.
#
# The accepted cost: x_SkuMeterId's public catalogue GUIDs are pseudonymised
# too, so those rows can no longer be joined to Azure's public pricing data.
# That is a real analytical loss and a cheap price. In a control protecting
# personal data, a rule that is simple to verify beats a rule that is clever.

# Identifier shapes, replaced wherever they appear in any string column.
GUID_PATTERN = re.compile(
    r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
    r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12}")

# Azure billing profile / invoice section codes, e.g. ABCD-1E2F-GH3-IJK.
BILLING_CODE_PATTERN = re.compile(r"\b[A-Z0-9]{4}-[A-Z0-9]{4}-[A-Z0-9]{3}-[A-Z0-9]{3}\b")


def pseudonym_guid(original):
    """A stable fake GUID derived from a real one. Same in, same out, always."""
    digest = hashlib.sha256((SALT + original).encode()).hexdigest()
    return (f"{digest[0:8]}-{digest[8:12]}-{digest[12:16]}-"
            f"{digest[16:20]}-{digest[20:32]}")


def pseudonym_token(original, template="XXXX-XXXX-XXX-XXX"):
    """A stable fake identifier shaped like the original."""
    digest = hashlib.sha256((SALT + original).encode()).hexdigest().upper()
    out, i = [], 0
    for character in template:
        if character == "-":
            out.append("-")
        else:
            out.append(digest[i]); i += 1
    return "".join(out)


def sanitise_value(value):
    """Replace every identifier shape found anywhere in the string.

    Surrounding structure is preserved, so a ResourceId stays a readable path
    and resource group, type and name all still work.
    """
    if value is None or not isinstance(value, str) or not value:
        return value
    out = GUID_PATTERN.sub(lambda m: pseudonym_guid(m.group(0)), value)
    out = BILLING_CODE_PATTERN.sub(lambda m: pseudonym_token(m.group(0)), out)
    return out


def sanitise_export(folder, con, keep_original=False):
    """Read a real export folder, return sanitised rows + a report."""
    with open(os.path.join(folder, "manifest.json")) as f:
        manifest = json.load(f)

    parquet = os.path.join(folder, os.path.basename(
        manifest["blobs"][0]["blobName"]))
    if not os.path.exists(parquet):
        matches = [f for f in os.listdir(folder) if f.endswith(".snappy.parquet")]
        if not matches:
            return None, None, None
        parquet = os.path.join(folder, matches[0])

    con.execute(f"CREATE OR REPLACE VIEW raw AS "
                f"SELECT * FROM read_parquet('{parquet}')")
    columns = [r[0] for r in con.execute("DESCRIBE raw").fetchall()]
    rows = [dict(zip(columns, r))
            for r in con.execute("SELECT * FROM raw").fetchall()]

    original = [dict(row) for row in rows] if keep_original else None
    report = {"names": 0, "identifiers": 0, "columns_touched": set()}
    for row in rows:
        for column, replacement in NAME_COLUMNS.items():
            if column in row and row[column] is not None:
                row[column] = replacement
                report["names"] += 1
        # Every string column, no exceptions and no judgement calls.
        for column, value in row.items():
            if column in NAME_COLUMNS or not isinstance(value, str):
                continue
            new = sanitise_value(value)
            if new != value:
                row[column] = new
                report["identifiers"] += 1
                report["columns_touched"].add(column)

    report["original"] = original
    return manifest, rows, report


def _sanitise_tree(value):
    """Apply sanitise_value to every string inside a nested dict/list."""
    if isinstance(value, dict):
        return {k: _sanitise_tree(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_sanitise_tree(v) for v in value]
    return sanitise_value(value)


def write_sanitised_layer(folder_name, manifest, rows, con):
    """Write the sanitised real rows out as a per-layer view of their own.

    ADDED IN STAGE 4 (chunk 2a, finding F26). Until now SANITISED_DIR was
    declared at the top of this file and never used: the sanitised rows existed
    only as an in-memory view inside this script, and vanished when it exited.

    That was fine for building focus_unified and wrong for everything after it.
    The Stage 4 empty-string sweep must bind to a PER-LAYER view, because
    decision D3 normalises '' -> NULL when focus_unified is built. Run the sweep
    on the unified view and it reports zero and looks like a pass. On the real
    layer that left three places to point it and none of them usable:

        data/raw/            has the 1,406 empty strings, but is unsanitised
                             (finding F6) and can never be committed
        data/unified/        D3 already normalised them away
        data/raw-sanitised/  the right answer — and it did not exist

    So this writes it: same rows, same sanitisation, same Azure-shaped manifest
    as every other layer folder, and safe to commit.

    THE SAFETY PROPERTY, AND IT IS THE POINT OF THE FUNCTION SIGNATURE:
    this is only ever called AFTER verify_sanitised has returned no problems.
    The verification runs against the OUTPUT rows, independently of the
    sanitising rules, and this write is downstream of that gate. A residual
    identifier therefore means nothing is written at all, rather than something
    unpublishable being written and then noticed later. Decision D6's publication
    gate, applied to a file instead of to a repository.
    """
    import pyarrow as pa
    import pyarrow.parquet as pq

    out_dir = os.path.join(SANITISED_DIR, folder_name)
    os.makedirs(out_dir, exist_ok=True)

    parquet_name = "focus_real_sanitised.snappy.parquet"
    parquet_path = os.path.join(out_dir, parquet_name)
    pq.write_table(pa.Table.from_pylist(rows), parquet_path, compression="snappy")

    size = os.path.getsize(parquet_path)

    # The manifest mirrors Azure's own shape, exactly as seed_data.py does for
    # the synthetic layers, so loader.py reads this folder with no change. The
    # export config is carried over from the REAL manifest rather than invented:
    # this is the same export, sanitised, and it must keep saying so — including
    # its dataVersion, which is what x_SchemaEra and every era gate depend on.
    out_manifest = {
        "manifestVersion": manifest.get("manifestVersion", "2024-04-01"),
        "byteCount":       size,
        "blobCount":       1,
        "dataRowCount":    len(rows),
        # Stage 8 finding F-S8-12: exportConfig.resourceId is an ARM path that
        # embeds the subscription id, and this manifest was being written with
        # it intact — the residual check below counts the PARQUET, not this
        # file. publication_check.py caught it. Every string in the carried-
        # over config now goes through the same sanitising rule as the data.
        "exportConfig":    _sanitise_tree(manifest.get("exportConfig", {})),
        "deliveryConfig": {
            "fileFormat":      "Parquet",
            "compressionMode": "Snappy",
            "partitionData":   False,
        },
        "runInfo": {
            "executionType": "Sanitised",
            "runId":         manifest.get("runInfo", {}).get("runId", ""),
        },
        "blobs": [{
            "blobName":     parquet_name,
            "byteCount":    size,
            "dataRowCount": len(rows),
        }],
        # Our own key. Azure ignores keys it does not know and so does the
        # loader, which is why extending a manifest this way is safe.
        "sanitisation": {
            "source":      f"data/raw/{folder_name}/",
            "method":      "rule-based; no lookup table exists (decision D1)",
            "salt":        SALT,
            "verified":    "0 residual identifiers, checked independently of "
                           "the sanitising rules",
            "publishable": True,
        },
    }
    with open(os.path.join(out_dir, "manifest.json"), "w") as f:
        json.dump(out_manifest, f, indent=2)

    # THE PROPERTY THIS FOLDER EXISTS FOR, COUNTED RATHER THAN ASSUMED.
    #
    # The whole reason to write a per-layer view is that it preserves the
    # provider's behaviour where focus_unified does not. Azure's real export
    # holds ~1,406 empty strings in not-nullable string columns (finding F2,
    # refined: a SHOULD NOT, so a warning and not a failure). Those must SURVIVE
    # into this file, or the chunk 7 sweep will run against a clean copy and
    # report a pass on a defect that is really there.
    #
    # sanitise_value returns early on an empty string, so preservation is
    # expected — but expected is not verified, and this is exactly the class of
    # assumption that produced F26 in the first place. So it is counted here and
    # printed, and a count of zero is a loud signal that something upstream
    # normalised the data before it reached this function.
    con.execute("CREATE OR REPLACE VIEW sanitised_check AS "
                f"SELECT * FROM read_parquet('{parquet_path}')")
    empties = 0
    for name, kind, *_ in con.execute("DESCRIBE sanitised_check").fetchall():
        if str(kind).upper() in ("VARCHAR", "STRING"):
            empties += con.execute(
                f'SELECT count(*) FROM sanitised_check WHERE "{name}" = \'\''
            ).fetchone()[0]

    return parquet_path, len(rows), empties


def verify_sanitised(original_rows, sanitised_rows):
    """Does anything identifying survive? Asked of the OUTPUT, not the code.

    The distinction matters and it is the whole point of this function. A check
    that confirms "my replacements ran" proves the code executed. It cannot
    prove the code was COMPLETE. This one takes every identifier present in the
    original and searches the sanitised output for it, anywhere, in any column.

    It found two leaks the first time it ran (finding F21) — both in places the
    rules had deliberately spared.
    """
    # Harvest every identifier the original contained.
    needles = set()
    for row in original_rows:
        for value in row.values():
            if not isinstance(value, str) or not value:
                continue
            needles.update(GUID_PATTERN.findall(value))
            needles.update(BILLING_CODE_PATTERN.findall(value))
    for row in original_rows:
        for column in NAME_COLUMNS:
            if isinstance(row.get(column), str) and row[column]:
                needles.add(row[column])

    leaks = []
    for row in sanitised_rows:
        for column, value in row.items():
            if not isinstance(value, str) or not value:
                continue
            for needle in needles:
                if needle in value:
                    leaks.append(f"{column} still contains an original identifier")
    return sorted(set(leaks)), len(needles)


# =============================================================================
# 2. THE UNIFIED VIEW  (decisions D2, D3)
# =============================================================================

def find_real_exports():
    """Every folder under data/raw/ that holds a manifest and a parquet."""
    if not os.path.isdir(RAW_DIR):
        return []
    found = []
    for entry in sorted(os.listdir(RAW_DIR)):
        folder = os.path.join(RAW_DIR, entry)
        if (os.path.isdir(folder)
                and os.path.exists(os.path.join(folder, "manifest.json"))):
            found.append(folder)
    return found


def empty_string_report(con, view):
    """Count empty strings per column BEFORE they are normalised (D3 guardrail).

    Finding F2, quantified. Publishing this count is what separates a documented
    normalisation from silent data laundering.
    """
    counts = {}
    for name, kind, *_ in con.execute(f"DESCRIBE {view}").fetchall():
        if str(kind).upper() not in ("VARCHAR", "STRING"):
            continue
        n = con.execute(
            f'SELECT count(*) FROM {view} WHERE "{name}" = \'\'').fetchone()[0]
        if n:
            counts[name] = n
    return counts


def build(con, sources):
    """UNION the layers, then normalise empty strings at this boundary only."""
    # UNION ALL BY NAME matches columns by NAME rather than position and fills
    # anything missing with NULL. That is what lets a 51-column legacy layer, a
    # 66-column v1.2 layer and a 96-column real export merge at all — decision
    # D8's cost, and it is one clause.
    union = "\nUNION ALL BY NAME\n".join(f"SELECT * FROM {name}"
                                         for name in sources)
    con.execute(f"CREATE OR REPLACE VIEW unified_raw AS {union}")

    before = empty_string_report(con, "unified_raw")

    # D3: normalise '' -> NULL HERE AND ONLY HERE. The raw and per-layer views
    # keep the provider's behaviour intact so the defect stays provable, and the
    # Stage 4 empty-string sweep must bind to those, never to this view.
    columns = con.execute("DESCRIBE unified_raw").fetchall()
    projections = []
    for name, kind, *_ in columns:
        if str(kind).upper() in ("VARCHAR", "STRING"):
            projections.append(f'nullif("{name}", \'\') AS "{name}"')
        else:
            projections.append(f'"{name}"')
    con.execute(f"CREATE OR REPLACE VIEW focus_unified AS "
                f"SELECT {', '.join(projections)} FROM unified_raw")
    return before


# =============================================================================
# 3. RUN
# =============================================================================

if __name__ == "__main__":
    print("=" * 70)
    print("build_unified.py — real + synthetic, sanitised and merged")
    print("=" * 70)

    con = duckdb.connect()
    sources, summary = [], []

    # --- the real layer, sanitised first ---------------------------------
    print("\nSANITISING THE REAL EXPORT  (decision D1, finding F6)")
    print("-" * 70)
    exports = find_real_exports()
    if not exports:
        print(f"  No exports found under {RAW_DIR}")
        print("  Expected: data/raw/<pull folder>/manifest.json + *.snappy.parquet")
    for folder in exports:
        # Keep an untouched copy purely so the verification has something to
        # compare against. It is never written anywhere.
        manifest, rows, report = sanitise_export(folder, con, keep_original=True)
        if rows is None:
            print(f"  {os.path.basename(folder):<20} no parquet found, skipped")
            continue
        if not rows:
            print(f"  {os.path.basename(folder):<20} 0 rows, skipped "
                  f"(expected for the 22 July pull)")
            continue

        problems, needle_count = verify_sanitised(report["original"], rows)
        version = manifest["exportConfig"]["dataVersion"]
        for row in rows:
            row["x_Synthetic"] = False
            row["x_SchemaEra"] = version
            row["x_FixtureId"] = "real_azure_export"

        name = f"real_{len(sources)}"
        con.register(name, __import__("pyarrow").Table.from_pylist(rows))
        sources.append(name)
        summary.append((os.path.basename(folder), version, len(rows),
                        len(rows[0])))

        print(f"  {os.path.basename(folder):<20} {len(rows):>4} rows, "
              f"FOCUS {version}")
        print(f"      name values overwritten   : {report['names']}")
        print(f"      identifiers pseudonymised : {report['identifiers']} "
              f"across {len(report['columns_touched'])} columns")
        print(f"      distinct identifiers found: {needle_count}")
        print(f"      RESIDUAL AFTER SANITISING : "
              f"{'NONE' if not problems else problems}")
        if problems:
            print("      ** A rule is incomplete. Do not publish. **")
        else:
            # F26 / chunk 2a: write the per-layer sanitised view, but ONLY on
            # the clean branch. If a residual identifier survived, nothing is
            # written — the file never exists to be committed by accident.
            written, n, empties = write_sanitised_layer(
                os.path.basename(folder), manifest, rows, con)
            print(f"      per-layer view written     : "
                  f"{os.path.relpath(written, ROOT)} ({n} rows)")
            print(f"      empty strings PRESERVED    : {empties} "
                  f"{'(the F2 defect, intact for the Stage 4 sweep)' if empties else '(none in this pull)'}")

    # --- the synthetic layers --------------------------------------------
    print("\nSYNTHETIC LAYERS")
    print("-" * 70)
    for label, folder in (("v1.2", SYNTHETIC_V12), ("pre-1.2", SYNTHETIC_PRE)):
        manifest_path = os.path.join(folder, "manifest.json")
        if not os.path.exists(manifest_path):
            print(f"  {label:<10} not found — run seed_data.py first")
            continue
        with open(manifest_path) as f:
            manifest = json.load(f)
        parquet = os.path.join(folder, manifest["blobs"][0]["blobName"])
        name = f"syn_{label.replace('.', '_').replace('-', '_')}"
        con.execute(f"CREATE OR REPLACE VIEW {name} AS "
                    f"SELECT * FROM read_parquet('{parquet}')")
        rows = con.execute(f"SELECT count(*) FROM {name}").fetchone()[0]
        cols = len(con.execute(f"DESCRIBE {name}").fetchall())
        sources.append(name)
        summary.append((label, manifest["exportConfig"]["dataVersion"],
                        rows, cols))
        print(f"  {label:<10} {rows:>4} rows, {cols} columns")

    print("\n  EXCLUDED: data/negative/ — deliberately broken rows, never merged.")

    if not sources:
        print("\nNothing to merge. Run seed_data.py first.")
        sys.exit(1)

    # --- merge ------------------------------------------------------------
    print("\nMERGING  (UNION ALL BY NAME)")
    print("-" * 70)
    before = build(con, sources)

    total = con.execute("SELECT count(*) FROM focus_unified").fetchone()[0]
    width = len(con.execute("DESCRIBE focus_unified").fetchall())

    print(f"\n  {'source':<22}{'FOCUS':>8}{'rows':>7}{'columns':>9}")
    for label, version, rows, cols in summary:
        print(f"  {label:<22}{version:>8}{rows:>7}{cols:>9}")
    print(f"  {'focus_unified':<22}{'mixed':>8}{total:>7}{width:>9}")
    print("\n  Column count exceeds every source: BY NAME keeps the union of all")
    print("  columns and fills the gaps with NULL. A row from a 51-column legacy")
    print("  layer simply has nothing to say about PricingCurrency.")

    # --- D3: what was normalised, stated plainly --------------------------
    print("\nEMPTY-STRING NORMALISATION  (decision D3, finding F2)")
    print("-" * 70)
    if before:
        coerced = sum(before.values())
        print(f"\n  {coerced} empty strings coerced to NULL across "
              f"{len(before)} column(s):")
        for name, count in sorted(before.items(), key=lambda kv: -kv[1]):
            print(f"    {name:<34}{count:>6}")
        print("\n  Applied at THIS boundary only. The per-layer views keep the")
        print("  provider's behaviour intact, so the defect stays provable and")
        print("  the Stage 4 empty-string sweep must bind to those, not to this.")
        print("  FOCUS StringHandling makes this a SHOULD NOT, not a MUST NOT —")
        print("  a departure from a recommendation, not a conformance failure.")
    else:
        print("\n  No empty strings found. (Expected 0 if the real export is")
        print("  absent — Azure's own rows are where they come from.)")

    # --- provenance: what is what -----------------------------------------
    print("\nPROVENANCE  (decisions D2, D4)")
    print("-" * 70)
    print(f"\n  {'x_SchemaEra':<12}{'synthetic':>11}{'rows':>7}   fixture")
    for era, synthetic, rows, fixture in con.execute(
            "SELECT x_SchemaEra, x_Synthetic, count(*), "
            "  string_agg(DISTINCT x_FixtureId, ', ') "
            "FROM focus_unified GROUP BY 1, 2 ORDER BY 1, 2").fetchall():
        print(f"  {str(era):<12}{str(synthetic):>11}{rows:>7}   {fixture[:44]}")
    print("\n  Every row declares its origin. Nothing can be mistaken for real")
    print("  data, and the FOCUS version each row was emitted under is never lost.")

    # --- write it out -----------------------------------------------------
    os.makedirs(UNIFIED_DIR, exist_ok=True)
    out = os.path.join(UNIFIED_DIR, "focus_unified.snappy.parquet")
    con.execute(f"COPY focus_unified TO '{out}' "
                f"(FORMAT PARQUET, COMPRESSION SNAPPY)")
    print(f"\n  Written: {os.path.relpath(out, ROOT)}")
    print(f"  {total} rows x {width} columns — the Stage 4 and Stage 5 input.")
