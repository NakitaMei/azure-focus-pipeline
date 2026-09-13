"""
loader.py — Portfolio Project 1, Stage 2
Chunk 1: read the manifest.
Chunk 2: load the Parquet into DuckDB.
Chunk 3: apply the §7 fallbacks, schema-aware, to build the 'focus' view.
"""

import json          # Python's built-in tool for reading JSON files
import duckdb        # the DuckDB engine, as a Python library
import sys, glob, os   # accept a pull folder + find the parquet by pattern

# --- 1. Open and read the manifest ------------------------------------------
pull_folder = sys.argv[1] if len(sys.argv) > 1 else "."
print(f"Reading pull folder: {pull_folder}\n")
with open(os.path.join(pull_folder, "manifest.json")) as f:
    manifest = json.load(f)

# --- 2. Reach into the manifest for the fields Stage 2 cares about -----------
export_config = manifest["exportConfig"]
run_info      = manifest["runInfo"]

focus_version = export_config["dataVersion"]
export_name   = export_config["exportName"]
run_id        = run_info["runId"]
row_count     = manifest["dataRowCount"]

# --- 3. Print what we found -------------------------------------------------
print("Manifest read successfully.")
print(f"  Export name   : {export_name}")
print(f"  FOCUS version : {focus_version}")
print(f"  Run ID        : {run_id}")
print(f"  Data rows     : {row_count}")

# --- 4. Load the Parquet into DuckDB ----------------------------------------
con = duckdb.connect()
matches = glob.glob(os.path.join(pull_folder, "*.snappy.parquet"))
if not matches:
    sys.exit(f"No .snappy.parquet found in {pull_folder}")
parquet_file = matches[0]
con.execute(f"CREATE VIEW raw AS SELECT * FROM read_parquet('{parquet_file}')")

# --- 5. Confirm it loaded ---------------------------------------------------
rows = con.execute("SELECT count(*) FROM raw").fetchone()[0]
cols = len(con.execute("DESCRIBE raw").fetchall())
print()
print("Parquet loaded into DuckDB.")
print(f"  Columns in file : {cols}")
print(f"  Rows in file    : {rows}")

# --- 6. Which columns does this export actually have? -----------------------
# DESCRIBE lists every column; we keep the names in a list (file order).
existing = [row[0] for row in con.execute("DESCRIBE raw").fetchall()]

# --- 7. The §7 fallback map: canonical FOCUS column  <-  Azure x_ column -----
fallbacks = {
    "SkuMeter":        "x_SkuMeterName",
    "SkuPriceDetails": "x_SkuDetails",
    "PricingCurrency": "x_PricingCurrency",
    "InvoiceId":       "x_InvoiceId",
}

# --- 8. Build the canonical view, SCHEMA-AWARE ------------------------------
# For each canonical target, decide how to resolve it from what's present.
resolved_parts = []
print()
print("Applying §7 fallbacks (schema-aware):")
for canonical, x_col in fallbacks.items():
    root_here = canonical in existing
    x_here    = x_col in existing
    if root_here and x_here:
        resolved_parts.append(f'coalesce("{canonical}", "{x_col}") AS "{canonical}"')
        print(f'  {canonical:<16} coalesce(root, {x_col})   [both present]')
    elif x_here:                        # root absent — the 1.0r2 reality
        resolved_parts.append(f'"{x_col}" AS "{canonical}"')
        print(f'  {canonical:<16} rename {x_col}   [root absent at {focus_version}]')
    elif root_here:
        resolved_parts.append(f'"{canonical}"')
        print(f'  {canonical:<16} root only   [no x_ needed]')
    else:
        resolved_parts.append(f'CAST(NULL AS VARCHAR) AS "{canonical}"')
        print(f'  {canonical:<16} neither present -> NULL')

# Keep every original column too (nothing lost), except the canonical names
# themselves — we just built better versions of those above.
passthrough = [f'"{c}"' for c in existing if c not in fallbacks]

# Assemble and create the canonical view 'focus'.
select_sql = ", ".join(passthrough + resolved_parts)
con.execute(f"CREATE VIEW focus AS SELECT {select_sql} FROM raw")

focus_cols = len(con.execute("DESCRIBE focus").fetchall())
print()
print(f"Canonical view 'focus' created: {focus_cols} columns "
      f"({len(existing)} original + {len(resolved_parts)} resolved).")
# --- 9. Profiling -----------------------------------------------------------
focus_rows = con.execute("SELECT count(*) FROM focus").fetchone()[0]
print()
print("=" * 60)
print("PROFILING")
print("=" * 60)
print(f"Rows in 'focus': {focus_rows}")

if focus_rows == 0:
    print()
    print("** 0 rows — expected, not a fault. **")
    print("Free-tier resources sit at US$0.00, so Azure emits no charge rows")
    print("yet (8-24h lag). Schema is valid; the value-level profile below is")
    print("empty by construction. Re-pull in 1-2 days and re-run unchanged.")

# The columns of the canonical view (file order)
focus_columns = [row[0] for row in con.execute("DESCRIBE focus").fetchall()]

# --- 9a. Null profile: how many nulls in each column ------------------------
print()
print("Null profile (columns with at least one null):")
if focus_rows == 0:
    print("  (0 rows — deferred to re-pull.)")
else:
    any_nulls = False
    for c in focus_columns:
        n = con.execute(f'SELECT count(*) - count("{c}") FROM focus').fetchone()[0]
        if n > 0:
            any_nulls = True
            print(f"  {c:<28} {n:>6}  ({n / focus_rows * 100:4.0f}%)")
    if not any_nulls:
        print("  (no nulls in any column.)")

# --- 9b. Category inventory: distinct values of every *Category column -------
print()
print("Category inventory (distinct values per Category column):")
category_columns = [c for c in focus_columns if c.endswith("Category")]
for c in category_columns:
    if focus_rows == 0:
        print(f"  {c:<28} (0 rows — deferred)")
    else:
        vals = con.execute(
            f'SELECT "{c}", count(*) FROM focus GROUP BY 1 ORDER BY 2 DESC'
        ).fetchall()
        shown = ", ".join(f"{v}×{n}" for v, n in vals[:8])
        print(f"  {c:<28} {len(vals)} distinct: {shown}")

# --- 9c. Currency inventory -------------------------------------------------
print()
print("Currency inventory:")
for c in ["BillingCurrency", "PricingCurrency"]:
    if c in focus_columns:
        if focus_rows == 0:
            print(f"  {c:<20} (0 rows — deferred)")
        else:
            vals = con.execute(f'SELECT DISTINCT "{c}" FROM focus ORDER BY 1').fetchall()
            print(f"  {c:<20} {[v[0] for v in vals]}")
            # --- 10. Null interpretation (keepsake Module 6: "null is information") ------
print()
print("=" * 60)
print("NULL INTERPRETATION")
print("=" * 60)

# 10a. Semantic nulls — a null here is MEANINGFUL, not a defect (keepsake L6-L10).
null_meaning = {
    "ChargeClass":          "not a prior-period correction",
    "InvoiceId":            "not yet on an invoice",
    "CommitmentDiscountId": "nothing to do with a commitment",
    "RegionId":             "charge isn't geographically scoped",
    "ResourceId":           "not tied to a resource",
}
print()
print("Semantic nulls — conformant by design (no action):")
for col, meaning in null_meaning.items():
    if col in focus_columns:
        if focus_rows == 0:
            print(f"  {col:<22} deferred — will mean: {meaning}")
        else:
            n = con.execute(f'SELECT count(*) - count("{col}") FROM focus').fetchone()[0]
            print(f"  {col:<22} {n} null = {meaning}")

# 10b. Anchor -> satellite cascade: if the anchor is null, its satellites MUST be
#      null too. A satellite filled while its anchor is null is a defect.
cascade = {
    "RegionId":             ["RegionName"],
    "ResourceId":           ["ResourceName", "ResourceType"],
    "CommitmentDiscountId": ["CommitmentDiscountStatus"],
    "SubAccountId":         ["SubAccountName", "SubAccountType"],
}
print()
print("Anchor -> satellite cascade (defect test):")
if focus_rows == 0:
    print("  (0 rows — checks wired; no findings yet. On real rows each flags a")
    print("   satellite that is NON-NULL while its anchor IS NULL.)")
else:
    found = False
    for anchor, satellites in cascade.items():
        if anchor not in focus_columns:
            continue
        for sat in satellites:
            if sat not in focus_columns:
                continue
            bad = con.execute(
                f'SELECT count(*) FROM focus WHERE "{anchor}" IS NULL AND "{sat}" IS NOT NULL'
            ).fetchone()[0]
            if bad:
                found = True
                print(f"  INVESTIGATE: {sat} filled on {bad} row(s) where {anchor} is null.")
    if not found:
        print("  OK: every satellite follows its anchor. Cascade conformant.")

# 10c. Placeholder abuse: an empty string / "N/A" used instead of a real NULL.
placeholders = ["", "N/A", "n/a", "NA", "null", "NULL", "None", "-"]
print()
print("Placeholder-instead-of-null check:")
if focus_rows == 0:
    print("  (0 rows — deferred.)")
else:
    ph_list = ", ".join(f"'{p}'" for p in placeholders)
    found = False
    string_cols = [r[0] for r in con.execute(
        "SELECT column_name, column_type FROM (DESCRIBE focus)").fetchall()
        if str(r[1]).upper() in ("VARCHAR", "STRING")]
    for c in string_cols:
        bad = con.execute(f'SELECT count(*) FROM focus WHERE "{c}" IN ({ph_list})').fetchone()[0]
        if bad:
            found = True
            print(f"  INVESTIGATE: {c} holds a placeholder on {bad} row(s) (should be NULL).")
    if not found:
        print("  OK: no empty-string / placeholder-for-null found.")
