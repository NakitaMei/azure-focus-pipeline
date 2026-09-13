"""
run_queries.py — runs every query in queries.sql and prints the results.

Stage 5 helper, version 2. Changes from v1:
  1. NAMED HEADERS — each result is titled from the comment above the
     query (e.g. "QUERY 1a. CONSUMPTION SHOWBACK") instead of a bare
     sequence number.
  2. A PROPER STATEMENT SPLITTER — v1 split the file on every semicolon,
     which breaks the moment a semicolon appears inside a quoted string
     or a comment. v2 walks the file character by character and only
     treats ';' as "end of statement" when it is outside both.

Run from the VS Code terminal:
    source .venv/bin/activate    (if the prompt doesn't show (.venv))
    python3 run_queries.py
"""

import re
import sys
from pathlib import Path

import duckdb
import pandas as pd

pd.set_option("display.max_rows", None)
pd.set_option("display.max_columns", None)
pd.set_option("display.width", None)

SQL_FILE = Path(__file__).parent / "queries.sql"


def split_statements(text):
    """Split SQL text into statements, respecting strings and comments.

    Returns a list of (comment_text_before, statement_sql) pairs.
    Rules of the walk:
      * inside '...' single quotes, ';' is just a character ('' = escaped quote)
      * from '--' to end of line is a comment; ';' inside it is just text
      * everywhere else, ';' ends the current statement
    """
    pairs = []
    comment_chars = []      # comments seen since the last statement ended
    stmt_chars = []         # the statement being accumulated
    i, n = 0, len(text)
    in_string = False
    while i < n:
        ch = text[i]
        if in_string:
            stmt_chars.append(ch)
            if ch == "'":
                if i + 1 < n and text[i + 1] == "'":   # '' = escaped quote
                    stmt_chars.append("'")
                    i += 1
                else:
                    in_string = False
        elif ch == "'":
            in_string = True
            stmt_chars.append(ch)
        elif ch == "-" and i + 1 < n and text[i + 1] == "-":
            end = text.find("\n", i)
            end = n if end == -1 else end
            comment_chars.append(text[i:end])
            i = end
            continue
        elif ch == ";":
            sql = "".join(stmt_chars).strip()
            if sql:
                pairs.append(("\n".join(comment_chars), sql))
            comment_chars, stmt_chars = [], []
        else:
            stmt_chars.append(ch)
        i += 1
    sql = "".join(stmt_chars).strip()
    if sql:
        pairs.append(("\n".join(comment_chars), sql))
    return pairs


def name_for(comment_text, fallback):
    """Pick a display name from the comment block above a statement."""
    lines = [ln.strip().lstrip("-").strip() for ln in comment_text.splitlines()]
    lines = [ln for ln in lines if ln and not set(ln) <= set("=-")]
    numbered = [ln for ln in lines if re.match(r"^\d+[a-z]?\.\s+\S", ln)]
    if numbered:
        return "QUERY " + numbered[-1]
    titled = [ln for ln in lines if ln.upper().startswith("QUERY")]
    if titled:
        return titled[-1]
    return fallback


def main():
    if not SQL_FILE.exists():
        sys.exit(f"Cannot find {SQL_FILE} — put queries.sql next to this script.")

    pairs = split_statements(SQL_FILE.read_text(encoding="utf-8"))
    con = duckdb.connect()

    for i, (comment, statement) in enumerate(pairs, start=1):
        first_word = statement.split()[0].upper()
        if first_word in ("CREATE", "SET", "INSTALL", "LOAD"):
            con.execute(statement)
            print(f"[setup ran OK] {statement.splitlines()[0][:70]}...")
            continue

        title = name_for(comment, f"Statement {i}")
        print()
        print("=" * 72)
        print(title[:72])
        print("=" * 72)
        result = con.execute(statement).df()
        print("(no rows returned)" if result.empty else result.to_string(index=False))

    print()
    print("Done — compare with the expected results in STAGE5_WORKING_NOTES.md.")


if __name__ == "__main__":
    main()
