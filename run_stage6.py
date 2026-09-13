"""
run_stage6.py - runs stage6_reconciliation.sql (or any .sql passed as arg 1).

Exists because run_queries.py runs queries.sql regardless of arguments.
Strips -- comments before splitting on ';' (a semicolon inside a comment is
exactly the class of bug that broke run_queries v1), labels each result with
the Q-header it sits under, and prints full frames.

Run:  python3 run_stage6.py
      python3 run_stage6.py some_other_file.sql
"""

import re
import sys

import duckdb
import pandas as pd

pd.set_option("display.width", 200)
pd.set_option("display.max_columns", 50)

path = sys.argv[1] if len(sys.argv) > 1 else "stage6_reconciliation.sql"
raw = open(path).read()

# Capture the Q-titles before stripping comments, keyed by character offset.
titles = [(m.start(), m.group(1).strip())
          for m in re.finditer(r"^--\s*([QC]\d+\s*·.*)$", raw, re.MULTILINE)]

def title_for(offset):
    current = ""
    for pos, t in titles:
        if pos <= offset:
            current = t
        else:
            break
    return current

# Strip comments but keep character positions roughly aligned by replacing
# each comment with spaces of the same length (so offsets stay meaningful).
stripped = re.sub(r"--[^\n]*", lambda m: " " * len(m.group(0)), raw)

def split_statements(text):
    """Split on ';' but never inside a single-quoted string ('' escapes ok)."""
    parts, buf, in_str = [], [], False
    for ch in text:
        if ch == "'":
            in_str = not in_str
        if ch == ";" and not in_str:
            parts.append("".join(buf)); buf = []
        else:
            buf.append(ch)
    parts.append("".join(buf))
    return parts

con = duckdb.connect()
pos = 0
for chunk in split_statements(stripped):
    stmt = chunk.strip()
    # label on the first non-space character of the statement itself,
    # so the Q-header comment (blanked to spaces) sits BEFORE it
    offset = pos + (len(chunk) - len(chunk.lstrip()))
    pos += len(chunk) + 1
    if not stmt:
        continue
    if stmt.upper().startswith("CREATE"):
        con.execute(stmt)
        continue
    label = title_for(offset)
    result = con.execute(stmt)
    try:
        df = result.df()
    except Exception:
        continue
    if df.shape[1] == 0:
        continue
    print("=" * 78)
    print(label or f"(statement at offset {offset})")
    print("=" * 78)
    if df.empty:
        print("(no rows - for the orphan check, empty IS the pass)")
    else:
        print(df.to_string(index=False))
    print()
