"""
sanitise_stage7.py — Portfolio Project 1, Stage 8

Writes data/stage7/ — the committed, sanitised copies of the Stage 7 real
exports (August and September 2026, 1.0r2 and 1.2-preview) that
sql/stage7_queries.sql reads.

Why a separate script and not build_unified.py: build_unified.py's job is the
VALIDATED real layer (data/raw-sanitised/), which validate.py discovers folder
by folder. The Stage 7 exports are reconciled in SQL, not validated, and must
not widen the conformance report — so they get their own folder, outside the
validator's search path, produced by the SAME sanitising rules imported from
build_unified.py rather than a second set.

What it does, per file in data/raw/stage7/*.parquet:
  1. reads every row, applies build_unified.sanitise_value to EVERY string
     column (GUID and billing-code shapes replaced with stable pseudonyms —
     including inside JSON blobs such as x_SkuDetails);
  2. writes the result to data/stage7/<same name>;
  3. verifies: no identifier-shaped string from the RAW file survives in the
     sanitised file. Compares exact values; never prints one. Refuses to keep
     an output that fails.

Manifests are deliberately NOT copied: they carry the subscription and
billing-account ids in plain text and nothing in the repository reads them.

Run from the repo root:  python3 sanitise_stage7.py
Exit 0 when every file verifies, 1 otherwise.
"""

import glob
import os
import re
import sys

import duckdb
import pyarrow as pa
import pyarrow.parquet as pq

import build_unified as BU   # the project's own sanitising rules

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE) if os.path.basename(HERE) == "src" else HERE
RAW = os.path.join(ROOT, "data", "raw", "stage7")
OUT = os.path.join(ROOT, "data", "stage7")

SHAPES = [
    re.compile(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"),
    re.compile(r"\b[A-Z0-9]{4}-[A-Z0-9]{4}-[A-Z0-9]{3}-[A-Z0-9]{3}\b"),
    re.compile(r"[\w.+-]+@[\w-]+\.[\w.]{2,}"),
]


def identifier_shaped(text):
    found = set()
    for shape in SHAPES:
        found.update(shape.findall(text))
    return found


def sanitise_file(src, dst):
    table = pq.read_table(src)
    columns = {}
    raw_text_parts = []
    for name in table.column_names:
        col = table.column(name)
        if pa.types.is_string(col.type) or pa.types.is_large_string(col.type):
            values = col.to_pylist()
            raw_text_parts.extend(v for v in values if isinstance(v, str))
            columns[name] = pa.array([BU.sanitise_value(v) for v in values],
                                     type=col.type)
        else:
            columns[name] = col
    out = pa.table(columns)
    pq.write_table(out, dst, compression="snappy")

    # ---- verification: nothing identifier-shaped from RAW survives -------
    raw_ids = identifier_shaped("\n".join(raw_text_parts))
    out_text = "\n".join(
        v for name in out.column_names
        for v in out.column(name).to_pylist()
        if isinstance(v, str)
    )
    survivors = sum(1 for value in raw_ids if value in out_text)
    return table.num_rows, len(table.column_names), len(raw_ids), survivors


def main():
    if not os.path.isdir(RAW):
        print(f"nothing to do: {os.path.relpath(RAW, ROOT)} is absent "
              "(a machine holding only the sanitised copies)")
        return 0
    os.makedirs(OUT, exist_ok=True)
    files = sorted(glob.glob(os.path.join(RAW, "*.parquet")))
    if not files:
        print("no parquet files under data/raw/stage7/")
        return 1
    failed = 0
    print("sanitise_stage7.py — Stage 7 real exports → data/stage7/")
    print("=" * 72)
    for src in files:
        name = os.path.basename(src)
        dst = os.path.join(OUT, name)
        rows, cols, n_ids, survivors = sanitise_file(src, dst)
        if survivors:
            os.remove(dst)
            failed += 1
            print(f"  FAIL  {name}: {survivors} of {n_ids} raw identifiers "
                  f"survived — output deleted, value not printed")
        else:
            print(f"  ok    {name}: {rows} rows × {cols} cols; "
                  f"{n_ids} distinct raw identifiers checked, 0 residual")
    print("=" * 72)
    if failed:
        print(f"NOT CLEAN — {failed} file(s) failed verification")
        return 1
    print("clean — data/stage7/ written; manifests deliberately not copied")
    return 0


if __name__ == "__main__":
    sys.exit(main())
