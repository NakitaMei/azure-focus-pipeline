"""
export_for_looker.py — runs every query in queries.sql and writes each
result to exports/ as a CSV, ready for Looker Studio.

Why this exists: Looker Studio cannot read a Parquet file on this Mac.
It CAN read uploaded CSVs or Google Sheets. This script materialises
each query's result as exports/query_<id>_<name>.csv. Workflow:

    python3 run_queries.py          # eyeball the results first
    python3 export_for_looker.py    # write the CSVs
    -> upload the CSVs to Looker Studio (or paste into Google Sheets,
       one tab per file) and build the dashboard on top.

Reuses the splitter and naming logic from run_queries.py — one parser,
one behaviour, no drift.
"""

import re
from pathlib import Path

import duckdb

from run_queries import SQL_FILE, name_for, split_statements

EXPORT_DIR = Path(__file__).parent / "exports"


def slug(title: str) -> str:
    """'QUERY 1a. CONSUMPTION SHOWBACK — "what…"' -> 'query_1a_consumption_showback'"""
    head = title.split("—")[0]
    head = re.sub(r"[^A-Za-z0-9]+", "_", head).strip("_").lower()
    return head


def main() -> None:
    EXPORT_DIR.mkdir(exist_ok=True)
    pairs = split_statements(SQL_FILE.read_text(encoding="utf-8"))
    con = duckdb.connect()

    written = []
    for i, (comment, statement) in enumerate(pairs, start=1):
        if statement.split()[0].upper() in ("CREATE", "SET", "INSTALL", "LOAD"):
            con.execute(statement)
            continue
        title = name_for(comment, f"statement_{i}")
        out = EXPORT_DIR / f"{slug(title)}.csv"
        con.execute(statement).df().to_csv(out, index=False)
        written.append(out.name)

    print(f"Wrote {len(written)} files to {EXPORT_DIR}/:")
    for name in written:
        print(f"  {name}")
    print("\nNext: upload these to Looker Studio (Create -> Data source ->")
    print("File upload), or paste into a Google Sheet, one tab per file.")


if __name__ == "__main__":
    main()
