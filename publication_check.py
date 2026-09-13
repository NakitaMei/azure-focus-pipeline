"""
publication_check.py — Portfolio Project 1

THE LAST THING THAT RUNS BEFORE ANYTHING GOES PUBLIC.

Stage 3 decision D6 held the repository closed until the sanitiser was built and
verified, and `build_unified.py` proves that `data/raw-sanitised/` carries zero
residual identifiers. That is a strong guarantee about **one file**.

This checks everything else. Three things it verifies, none of which the
sanitiser covers:

  1. **Excluded paths are actually absent** from what would be committed —
     `data/raw/`, `spec_cache/`, the chunk 10 workaround folder, saved-download
     duplicates.
  2. **Committed text carries no identifier-shaped strings.** The conformance
     report is GENERATED, and its violation messages embed values: a nullability
     failure prints `ResourceId = '/subscriptions/…'`. Today the real layer's
     only failures are empty-string ones, whose messages carry column names and
     nothing else — so the report is clean **by luck of which rule is broken**,
     not by design. Different data breaks a different rule.
  3. **Files that MUST be present are present.** `docs/spec/*.json` is easy to
     gitignore by accident alongside `spec_cache/`, since both are "the
     specification". Without it every citation in the conformance report is
     unverifiable and the traceability claim cannot be checked by a reader.
     **An omission is a publication defect too**, not only an exposure.

WHAT THIS DOES NOT COVER, AND CANNOT
Screenshots. Terminal output carries the machine hostname and username in the
prompt line — the same class of exposure as `data/raw/`, arriving through a
different door — and no text scan reads a PNG. That one stays manual, and this
script says so at the end rather than letting a green run imply otherwise.

Run:  python3 publication_check.py
Exit code 0 when clean, 1 otherwise.
Standard library only.
"""

import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE) if os.path.basename(HERE) == "src" else HERE


# =============================================================================
# 1. PATHS THAT MUST NOT BE PUBLISHED
# =============================================================================
# Present on disk is fine — gitignored is the point. This reports them so the
# check is a reminder to confirm `.gitignore` covers them, not an assertion that
# they have been deleted.

MUST_BE_IGNORED = [
    ("data/raw",            "unsanitised export — personal data (finding F6)"),
    ("spec_cache",          "19 MB copy of a public document"),
    ("focus_validator",     "chunk 10 currency-file workaround"),
    ("__pycache__",         "a stale .pyc shadows corrected source (D14)"),
    (".venv",               "the local virtual environment"),
]

# Saved downloads that duplicate generated files. The generated copies under
# docs/ are authoritative; these shadow them and go stale silently.
STRAY_DUPLICATES = [
    "spec_v1.2.json", "lifecycle.json", "conformance-report.md",
    "focus_unified.snappy.xlsx", ".gitignore.additions",
]

MUST_BE_PRESENT = [
    "docs/spec/spec_v1.2.json",
    "docs/spec/lifecycle.json",
    "docs/conformance-report.md",
    "README.md",
]


# =============================================================================
# 2. THE REAL CHECK — DID ANYTHING FROM THE ACTUAL EXPORT LEAK?
# =============================================================================
# THE FIRST VERSION OF THIS SCRIPT SCANNED FOR IDENTIFIER SHAPES AND REPORTED
# TWENTY-SIX PROBLEMS, OF WHICH TWENTY-FOUR WERE FALSE.
#
# All-zeros GUIDs. `{SUBSCRIPTION_ID}` placeholders. The synthetic fixture's own
# run id. Its own regular expressions. Every one deliberately committed and
# harmless — and a check that cries wolf twenty-four times is one nobody runs
# twice. That is finding F30 arriving inside the tool built to prevent leaks: a
# signal that fires on the wrong thing is worse than no signal, because it
# teaches you to ignore it.
#
# The question is not "does this look like an identifier". It is **"is this one
# of MY identifiers"** — and that question has an exact answer, because
# `data/raw/` is on disk and the real values are in it.
#
# So the blocking check reads the raw export purely to build a deny-list, scans
# publishable text for those exact strings, and **never prints a value it
# found** — printing it would put the identifier in the terminal scrollback and
# then in a screenshot. It reports the file and the count.
#
# The shape scan survives as a second, advisory tier: useful on prose, which can
# leak something the raw export never contained, but reported for review rather
# than as a block.


def real_identifiers():
    """Every identifier-shaped string present in the unsanitised export.

    Read only to build a deny-list. Nothing from here is ever printed.

    If `data/raw/` is absent — on a machine that only has the sanitised copy —
    this returns None, and the blocking check reports that it could not run.
    **A check that cannot run must say so**, not pass quietly; a silent skip is
    indistinguishable from a clean result, which is the F42 failure.
    """
    raw = os.path.join(ROOT, "data", "raw")
    if not os.path.isdir(raw):
        return None
    found = set()
    shapes = [
        r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}",
        r"[\w.+-]+@[\w-]+\.[\w.]{2,}",
        r"\b[\w-]+\.onmicrosoft\.com\b",
    ]
    for dirpath, _, filenames in os.walk(raw):
        for name in filenames:
            path = os.path.join(dirpath, name)
            try:
                with open(path, "rb") as f:
                    blob = f.read()
            except OSError:
                continue
            text = blob.decode("utf-8", errors="ignore")
            for shape in shapes:
                for match in re.findall(shape, text):
                    if not SYNTHETIC.match(match):
                        found.add(match)
    return found


# Values that LOOK like identifiers and are deliberately published: all-zeros
# placeholders, template braces, and the documented synthetic fixture run id.
# Kept deliberately small — a long allowlist is how a real value gets waved
# through.
SYNTHETIC = re.compile(
    r"^(0{8}-0{4}-0{4}-0{4}-0{12}"
    r"|\{[A-Z_]+\}"
    r"|534c40a5-5207-406a-a372-6f8308b56aaa)$"
)


# =============================================================================
# 2b. IDENTIFIER SHAPES — ADVISORY TIER
# =============================================================================
# Shapes, not a list of known values. A list can only find what you already knew
# to look for, which is the same distinction as "verified" versus "exhaustive"
# that this project has now hit four times.

PATTERNS = {
    "GUID":                 r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
                            r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12}",
    "Azure subscription":   r"/subscriptions/[^\s\"'`)\]]+",
    "Azure billing scope":  r"/providers/Microsoft\.Billing/[^\s\"'`)\]]+",
    "email address":        r"[\w.+-]+@[\w-]+\.[\w.]{2,}",
    "tenant domain":        r"\b[\w-]+\.onmicrosoft\.com\b",
}

# Text extensions worth scanning. Parquet and CSV under data/ are covered by the
# sanitiser's own residual-identifier scan, which is stricter than this one.
SCAN_EXTENSIONS = {".md", ".py", ".json", ".txt", ".yml", ".yaml", ".sql", ".csv", ".log"}

# The spec extract legitimately contains github.com URLs and spec prose. It is a
# copy of a public document, so identifier shapes there are not exposures.
SCAN_SKIP = {"docs/spec"}


def walk_publishable():
    """Every file that would be committed, given the exclusions above."""
    ignored = {p for p, _ in MUST_BE_IGNORED} | {".git", ".venv", "data/raw"}
    for dirpath, dirnames, filenames in os.walk(ROOT):
        rel_dir = os.path.relpath(dirpath, ROOT)
        if any(rel_dir == i or rel_dir.startswith(i + os.sep) for i in ignored):
            dirnames[:] = []
            continue
        dirnames[:] = [d for d in dirnames
                       if os.path.join(rel_dir, d).lstrip("./") not in ignored
                       and d not in (".git", ".venv", "__pycache__")]
        for name in filenames:
            yield os.path.join(dirpath, name)


def main():
    print("publication_check.py — the last gate before anything goes public")
    print("=" * 72)
    problems, warnings = [], []

    # --- 1. exclusions ------------------------------------------------------
    print("\nPATHS THAT MUST BE GITIGNORED")
    gitignore = ""
    gi_path = os.path.join(ROOT, ".gitignore")
    if os.path.exists(gi_path):
        gitignore = open(gi_path).read()
    else:
        problems.append("no .gitignore at the project root")

    for path, why in MUST_BE_IGNORED:
        exists = os.path.exists(os.path.join(ROOT, path))
        covered = path.rstrip("/") in gitignore or path.rstrip("/") + "/" in gitignore
        if not exists:
            print(f"  ok       {path:<22} not present")
        elif covered:
            print(f"  ok       {path:<22} present and gitignored   ({why})")
        else:
            print(f"  PROBLEM  {path:<22} present and NOT in .gitignore   ({why})")
            problems.append(f"{path} is not gitignored — {why}")

    # --- 2. stray duplicates ------------------------------------------------
    print("\nSAVED DOWNLOADS THAT SHADOW GENERATED FILES")
    found_strays = [n for n in STRAY_DUPLICATES
                    if os.path.exists(os.path.join(ROOT, n))]
    for name in found_strays:
        print(f"  PROBLEM  {name}")
        problems.append(f"{name} at project root duplicates a generated file")
    if not found_strays:
        print("  ok       none at the project root")
    else:
        print("  These are saved downloads. The generated copies under docs/ are")
        print("  authoritative; committing a stale duplicate ships a wrong report.")

    # --- 3. required files --------------------------------------------------
    print("\nFILES THAT MUST BE COMMITTED")
    for rel in MUST_BE_PRESENT:
        if os.path.exists(os.path.join(ROOT, rel)):
            print(f"  ok       {rel}")
        else:
            print(f"  PROBLEM  {rel} is MISSING")
            problems.append(f"{rel} missing — required for the repository to make sense")
    if "docs/spec" in gitignore:
        print("  PROBLEM  docs/spec is gitignored")
        problems.append(
            "docs/spec is gitignored — that is the parsed specification every "
            "check cites. Without it no finding can be verified by a reader.")

    # --- 4a. THE BLOCKING CHECK: real identifiers from the actual export -----
    print("\nDID ANYTHING FROM THE REAL EXPORT LEAK?  (blocking)")
    deny = real_identifiers()
    if deny is None:
        print("  CANNOT RUN  data/raw/ is not present, so there is nothing to")
        print("              compare against. On a machine holding only the")
        print("              sanitised copy this check is not applicable — but a")
        print("              check that cannot run must say so rather than pass.")
        warnings.append("the real-identifier check could not run: data/raw/ absent")
    elif not deny:
        print("  ok          no identifiers found in data/raw/ to compare against")
    else:
        leaked = {}
        for path in walk_publishable():
            if os.path.splitext(path)[1].lower() not in SCAN_EXTENSIONS:
                continue
            rel = os.path.relpath(path, ROOT)
            try:
                text = open(path, encoding="utf-8", errors="replace").read()
            except OSError:
                continue
            hits = sum(1 for value in deny if value in text)
            if hits:
                leaked[rel] = hits
        # Deliberately reports the COUNT and never the value: printing it would
        # put the identifier into terminal scrollback, and from there into a
        # screenshot.
        for rel, n in sorted(leaked.items()):
            print(f"  PROBLEM     {rel}: {n} real identifier(s) — value not printed")
            problems.append(f"{rel} contains {n} identifier(s) from the real export")
        if not leaked:
            print(f"  ok          {len(deny)} real identifiers checked against every")
            print(f"              publishable file — none appear in any of them")

    # --- 4b. advisory shape scan --------------------------------------------
    print("\nIDENTIFIER-SHAPED STRINGS  (advisory — review, not a block)")
    scanned, advisory = 0, {}
    for path in walk_publishable():
        rel = os.path.relpath(path, ROOT)
        if os.path.splitext(path)[1].lower() not in SCAN_EXTENSIONS:
            continue
        if any(rel.startswith(s) for s in SCAN_SKIP):
            continue
        if os.path.basename(path) == "publication_check.py":
            continue                    # its own patterns are not a finding
        try:
            text = open(path, encoding="utf-8", errors="replace").read()
        except OSError:
            continue
        scanned += 1
        for label, pattern in PATTERNS.items():
            for match in re.findall(pattern, text):
                if SYNTHETIC.match(match) or "{" in match:
                    continue
                advisory.setdefault(rel, set()).add(label)
    for rel, labels in sorted(advisory.items()):
        print(f"  review      {rel}: {', '.join(sorted(labels))}")
    print(f"  {scanned} text files scanned. Shapes flagged here are usually")
    print("  synthetic fixture values, which is why this tier does not block —")
    print("  the blocking answer is 4a, which compares against the real export.")
    if not advisory:
        print("  ok          nothing to review")

    # --- 5. what this cannot check ------------------------------------------
    print("\nNOT COVERED BY THIS CHECK — MANUAL, EVERY TIME")
    print("  screenshots/   Terminal output carries the machine hostname and")
    print("                 username in the prompt line. Same class of exposure")
    print("                 as data/raw/, arriving through a different door, and")
    print("                 no text scan reads a PNG. Crop or blur before adding.")
    warnings.append("screenshots must be redacted by hand")

    print("\n" + "=" * 72)
    if problems:
        print(f"NOT READY TO PUBLISH — {len(problems)} problem(s):")
        for p in problems:
            print(f"  - {p}")
        return 1

    print("No problems found in what this script can check.")
    print()
    print("One property worth knowing, because it is stronger than any scan:")
    print("validate.py never reads data/raw/ — it is deliberately absent from")
    print("TARGET_SPECS, and only build_unified.py touches it, writing sanitised")
    print("output. So no publishable artefact is generated from unsanitised data,")
    print("BY CONSTRUCTION rather than by inspection. This check exists because")
    print("that holds only while nobody adds it, and says nothing about the")
    print("screenshots or anything written by hand.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
