"""
check_files.py — a definitive count of what the generator actually wrote.

Reads the files on disk rather than trusting console output or a viewer.
Also re-computes each sha256 so you can confirm determinism yourself.

Run:  python3 check_files.py
"""

import datetime
import hashlib
import json
import os

import duckdb

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE) if os.path.basename(HERE) == "src" else HERE

LAYERS = [
    ("v1.2",     os.path.join(ROOT, "data", "synthetic", "v1.2")),
    ("pre-1.2",  os.path.join(ROOT, "data", "synthetic", "pre-1.2")),
    ("negative", os.path.join(ROOT, "data", "negative")),
]

con = duckdb.connect()

for label, folder in LAYERS:
    print(f"\n{'=' * 60}\n{label}\n{'=' * 60}")

    if not os.path.isdir(folder):
        print(f"  FOLDER NOT FOUND: {folder}")
        print("  (Re-run seed_data.py — chunk 7 changed the folder layout.)")
        continue

    manifest_path = os.path.join(folder, "manifest.json")
    if not os.path.exists(manifest_path):
        print(f"  manifest.json NOT FOUND in {folder}")
        continue
    with open(manifest_path) as f:
        manifest = json.load(f)

    parquet = os.path.join(folder, manifest["blobs"][0]["blobName"])
    if not os.path.exists(parquet):
        print(f"  Parquet named in the manifest is missing: {parquet}")
        continue

    rows = con.execute(f"SELECT count(*) FROM read_parquet('{parquet}')").fetchone()[0]
    columns = con.execute(
        f"DESCRIBE SELECT * FROM read_parquet('{parquet}')").fetchall()

    with open(parquet, "rb") as f:
        digest = hashlib.sha256(f.read()).hexdigest()

    stamp = datetime.datetime.fromtimestamp(
        os.path.getmtime(parquet)).strftime("%Y-%m-%d %H:%M:%S")

    print(f"  file          : {os.path.relpath(parquet, ROOT)}")
    print(f"  rows          : {rows}")
    print(f"  columns       : {len(columns)}")
    print(f"  last written  : {stamp}")
    print(f"  sha256        : {digest[:16]}...")

    # Cross-check the file against its own manifest — a mismatch means one of
    # them is stale.
    stated_rows = manifest["dataRowCount"]
    stated_hash = manifest["generator"]["fileSha256"]
    print(f"  manifest says : {stated_rows} rows   "
          f"{'MATCH' if stated_rows == rows else 'MISMATCH — one is stale'}")
    print(f"  fileSha256    : "
          f"{'agrees' if stated_hash == digest else 'DIFFERS — file changed after write'}")
    print(f"  contentSha256 : {manifest['generator']['contentSha256'][:16]}...")
    print(f"  pyarrow       : {manifest['generator'].get('pyarrowVersion', 'not recorded')}")

    eras = con.execute(
        f"SELECT DISTINCT x_SchemaEra FROM read_parquet('{parquet}')").fetchall()
    print(f"  x_SchemaEra   : {[e[0] for e in eras]}")

    for name, count in con.execute(
            f"SELECT x_FixtureId, count(*) FROM read_parquet('{parquet}') "
            f"GROUP BY 1 ORDER BY 2 DESC").fetchall():
        print(f"      {name:<26} {count:>4} rows")

print(f"\n{'=' * 60}")
print("Reproducibility (finding F20):")
print("  contentSha256 is the number to compare across machines — it hashes the")
print("  DATA and is stable regardless of pyarrow version.")
print("  fileSha256 hashes the BYTES and legitimately differs between pyarrow")
print("  versions, because Parquet encodes the same data more than one way.")
