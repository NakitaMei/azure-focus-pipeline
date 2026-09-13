"""
spec_source.py — Portfolio Project 1, Stage 4 chunk 1

THE SPECIFICATION, AS DATA.

Every assertion the Stage 4 harness makes must trace back to a sentence in the
FOCUS specification at a stated tag. A harness whose rules were typed in from
memory is an opinion with a pass/fail printout attached. This module is the
thing that goes and gets the specification, keeps a local copy, and turns each
column's markdown file into a structured record the checks can read.

Nothing downstream of this file touches the network. validate.py reads the JSON
this script writes. That matters for three reasons: the harness runs offline, it
runs identically on every machine, and the exact specification text behind every
check is committed to the repo where a reader can audit it.

WHY A TARBALL AND NOT 57 SEPARATE FETCHES
Build spec section 9 specifies the raw-file method:

    raw.githubusercontent.com/.../<TAG>/specification/columns/<column>.md

That method is right about the important thing — raw files, never rendered
documentation, because rendering truncates and accordions hide (assertion 2.4.4
was nearly built wrong from truncated text). This module keeps that principle and
changes only the transport: it downloads the whole tag as one archive.

Two reasons.
  1. One request instead of 57. The GitHub contents API rate-limits anonymous
     callers, which is what blocked the Stage 3 attempt to confirm the v1.2
     column list was exhaustive. The archive endpoint does not.
  2. A per-file fetch can only confirm files you already know to ask for. It
     cannot tell you the list is COMPLETE. The archive can, because it carries
     the directory. That is how the Stage 3 open item closes: 57 files at v1.2,
     counted, not assumed.

raw_url() below still emits the exact section 9 URL for any column, so every
claim stays hand-checkable and citable in the docs.

THREE THINGS THE SPEC REPO DOES THAT A NAIVE READER GETS WRONG
  1. The file name is NOT always the lowercased Column ID. At v1.2:
         provider.md      -> ProviderName
         publisher.md     -> PublisherName
         invoiceissuer.md -> InvoiceIssuerName
     A path builder doing column.lower() + ".md" 404s on exactly these three —
     and a 404 is indistinguishable from "this column was removed", which is
     what finding F22 is about. Left unhandled, the REMOVED map would report
     ProviderName as removed at v1.2. False, and entirely plausible-looking.
     So the Column ID is read from inside each file, never inferred.

  2. The repo layout changes at v1.3, not v1.4.
         v1.0, v1.1, v1.2   specification/columns/
         v1.3, v1.4         specification/datasets/<dataset>/columns/
     Verified across all five tags by HTTP status. F22 recorded the change at
     v1.4; it is one release earlier.

  3. Heading casing and line endings are inconsistent between files
     ("Content Constraints" and "Content constraints"; two files are CRLF).
     The parser is case-insensitive and normalises line endings before it does
     anything else. Skip the CR strip and two files silently parse as having no
     Introduced version.

Run:  python3 spec_source.py
Writes: spec_cache/<tag>/    the extracted specification (gitignored)
        docs/spec/spec_<tag>.json      one record per column
        docs/spec/lifecycle.json       INTRODUCED and REMOVED maps
Exit code 0 on success.

Standard library only — no new entries in requirements.txt.
"""

import io
import json
import os
import re
import sys
import tarfile
import urllib.request
from dataclasses import dataclass, field, asdict

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE) if os.path.basename(HERE) == "src" else HERE

CACHE = os.path.join(ROOT, "spec_cache")
OUT = os.path.join(ROOT, "docs", "spec")

REPO = "FinOps-Open-Cost-and-Usage-Spec/FOCUS_Spec"
ARCHIVE = "https://codeload.github.com/{repo}/tar.gz/refs/tags/{tag}"
RAW = "https://raw.githubusercontent.com/{repo}/{tag}/{path}"

# The tags this project reasons across. v1.2 is the conformance target; the
# others exist so the lifecycle maps can be computed rather than asserted.
TAGS = ["v1.0", "v1.1", "v1.2", "v1.3", "v1.4"]
TARGET_TAG = "v1.2"

# Layout changed at v1.3. Anything at or after it is dataset-scoped.
DATASET_LAYOUT_FROM = "v1.3"

# The four v1.4 datasets. At v1.0-v1.2 only cost_and_usage exists, and it is
# not addressed by name — its columns sit directly under specification/columns/.
DATASETS = ["cost_and_usage", "billing_period", "invoice_detail", "contract_commitment"]


# =============================================================================
# RFC 2119 — THE SEVERITY OF A RULE IS IN THE RULE'S OWN TEXT
# =============================================================================
# FOCUS adopts RFC 2119, and only the ALL-CAPS forms are normative. "must" in
# lowercase is prose. This is the F2-refinement made mechanical: rather than a
# human deciding which checks are failures and which are warnings, the severity
# is read off the keyword in the sentence the check came from.
#
#   MUST / MUST NOT / SHALL / REQUIRED       -> FAIL   (non-conformant)
#   SHOULD / SHOULD NOT / RECOMMENDED        -> WARN   (conformant, not advised)
#   MAY / OPTIONAL                           -> INFO   (permission, never a check)
#
# Order matters in the pattern: "MUST NOT" has to be tried before "MUST", or
# every negative requirement is misread as a positive one.

RFC2119 = re.compile(
    r"\b(MUST NOT|SHALL NOT|SHOULD NOT|MUST|SHALL|SHOULD|REQUIRED|RECOMMENDED|MAY|OPTIONAL)\b"
)

SEVERITY_OF = {
    "MUST": "FAIL", "MUST NOT": "FAIL", "SHALL": "FAIL", "SHALL NOT": "FAIL",
    "REQUIRED": "FAIL",
    "SHOULD": "WARN", "SHOULD NOT": "WARN", "RECOMMENDED": "WARN",
    "MAY": "INFO", "OPTIONAL": "INFO",
}


def severity_of(sentence):
    """Strongest keyword in a sentence wins. FAIL beats WARN beats INFO.

    A sentence can carry more than one keyword ("MUST be null when X, and MAY
    be null when Y"). Taking the strongest is the safe reading: it means a
    requirement is never quietly downgraded to a suggestion.
    """
    found = [SEVERITY_OF[m] for m in RFC2119.findall(sentence)]
    for level in ("FAIL", "WARN", "INFO"):
        if level in found:
            return level
    return None


# =============================================================================
# THE PARSED SHAPE OF ONE COLUMN
# =============================================================================
# A dataclass is Python's way of saying "this is a record with these fields".
# It writes __init__ and a readable __repr__ for you, and asdict() turns it
# into a plain dictionary ready for json.dump. Nothing clever — just a struct
# with a name, so the later chunks read column.allows_nulls rather than
# column["content_constraints"]["Allows nulls"] and hope the key is spelled
# the way this file spelled it.

@dataclass
class ColumnSpec:
    column_id: str                       # ProviderName - read from the file
    file_name: str                       # provider.md  - NOT inferable from above
    tag: str                             # v1.2
    dataset: str                         # cost_and_usage
    display_name: str = ""
    feature_level: str = ""              # Mandatory | Conditional | Optional
    allows_nulls: str = ""               # True | False
    data_type: str = ""
    value_format: str = ""
    column_type: str = ""                # Dimension | Metric
    introduced: str = ""                 # 0.5 | 1.0-preview | 1.0 | 1.1 | 1.2
    introduced_note: str = ""            # succession text, where the spec gives it
    allowed_values: list = field(default_factory=list)
    allowed_value_header: list = field(default_factory=list)
    allowed_value_rows: list = field(default_factory=list)   # full table, for parent maps
    subsection_tables: dict = field(default_factory=dict)    # "### " tables, e.g. SkuPriceDetails keys
    requirements: list = field(default_factory=list)   # {text, severity}
    raw_url: str = ""

    @property
    def musts(self):
        return [r for r in self.requirements if r["severity"] == "FAIL"]

    @property
    def shoulds(self):
        return [r for r in self.requirements if r["severity"] == "WARN"]


# =============================================================================
# FETCH AND CACHE
# =============================================================================

def ensure_tag(tag, quiet=False):
    """Download and extract one spec tag, unless it is already on disk.

    Returns the path to the extracted specification/ folder.

    The archive is streamed straight into tarfile from memory — it is ~250KB,
    so there is no reason to write the .tar.gz down and read it back.
    """
    dest = os.path.join(CACHE, tag)
    marker = os.path.join(dest, "specification")
    if os.path.isdir(marker):
        if not quiet:
            print(f"  {tag}  cached")
        return marker

    url = ARCHIVE.format(repo=REPO, tag=tag)
    if not quiet:
        print(f"  {tag}  fetching {url}")
    with urllib.request.urlopen(url, timeout=60) as resp:
        blob = resp.read()

    os.makedirs(dest, exist_ok=True)
    with tarfile.open(fileobj=io.BytesIO(blob), mode="r:gz") as tar:
        # The archive has one top-level folder (FOCUS_Spec-1.2/). strip it so
        # every tag extracts to the same shape.
        members = []
        for m in tar.getmembers():
            parts = m.name.split("/", 1)
            if len(parts) == 2 and parts[1]:
                m.name = parts[1]
                members.append(m)
        tar.extractall(dest, members=members)

    if not quiet:
        print(f"        extracted to {os.path.relpath(dest, ROOT)}")
    return marker


def uses_dataset_layout(tag):
    """True for tags at or after the v1.3 restructure.

    Compared as (major, minor) integers rather than as strings, because "v1.10"
    would sort before "v1.3" as text. Not a problem today; a trap later.
    """
    def key(t):
        major, minor = t.lstrip("v").split(".")[:2]
        return (int(major), int(minor))
    return key(tag) >= key(DATASET_LAYOUT_FROM)


def columns_path(tag, dataset="cost_and_usage"):
    """Where this tag keeps its column definitions. Version-aware, per F22."""
    if uses_dataset_layout(tag):
        return os.path.join("specification", "datasets", dataset, "columns")
    if dataset != "cost_and_usage":
        return None          # the other three datasets do not exist before v1.3
    return os.path.join("specification", "columns")


def raw_url(tag, file_name, dataset="cost_and_usage"):
    """The exact build-spec section 9 URL for one column file.

    Not used to fetch anything. It exists so every claim in the conformance
    report can carry the address a reader can paste into a browser and check.
    """
    rel = columns_path(tag, dataset)
    if rel is None:
        return None
    return RAW.format(repo=REPO, tag=tag, path=f"{rel}/{file_name}".replace("\\", "/"))


# =============================================================================
# PARSE ONE COLUMN FILE
# =============================================================================

def _sections(text):
    """Split a column file on its '## ' headings.

    Returns {lowercased heading: body text}. Lowercased because the spec is not
    consistent: 30 files say "Content Constraints" and 25 say "Content
    constraints", and one says "Display name".
    """
    out = {}
    current = "_preamble"
    buf = []
    for line in text.split("\n"):
        if line.startswith("## "):
            out[current] = "\n".join(buf).strip()
            current = line[3:].strip().lower()
            buf = []
        else:
            buf.append(line)
    out[current] = "\n".join(buf).strip()
    return out


def _subsection_tables(text):
    """Markdown tables that live under a '### ' heading, keyed by heading.

    ADDED FOR CHUNK 5. The FOCUS-defined SkuPriceDetails property list — the
    thirteen keys, their data types and units — sits under
    '### FOCUS-Defined Properties', a level-THREE heading. `_sections` splits on
    '## ' only, so the table was inside the Content Constraints body and no
    field exposed it.

    That list is not decoration. `Property key MUST begin with "x_" unless it is
    a FOCUS-defined property` cannot be checked at all without knowing which
    properties are FOCUS-defined, and the standing trap this project keeps
    returning to is exactly a key that LOOKS defined and is not: the course
    taught `MemoryGB`; the specification says `MemorySize`. A query on the first
    returns nothing, forever, silently.

    So the list is read from the specification rather than typed in — same
    principle as everywhere else, applied to a table one heading level deeper.
    """
    out = {}
    current, buf = None, []

    def flush():
        if current is None:
            return
        header, rows = [], []
        for line in buf:
            line = line.strip()
            if not line.startswith("|"):
                continue
            cells = [c.strip() for c in line.strip("|").split("|")]
            if all(set(c) <= set(":- ") for c in cells if c):
                continue
            if not header:
                header = cells
            else:
                rows.append(cells)
        if header:
            out[current.lower()] = {"header": header, "rows": rows}

    for line in text.split("\n"):
        if line.startswith("### "):
            flush()
            current, buf = line[4:].strip(), []
        elif line.startswith("## "):
            flush()
            current, buf = None, []
        elif current is not None:
            buf.append(line)
    flush()
    return out


def _first_line(body):
    """First non-blank line of a section body."""
    for line in body.split("\n"):
        if line.strip():
            return line.strip()
    return ""


def _introduced(body):
    """Version token and, where present, the succession note beside it.

    Most files put a bare version here ("1.2"). One does not. At v1.3,
    serviceprovidername.md reads:

        1.3 Introduced as a replacement for [ProviderName](#providername)

    Taken whole, that string becomes a key in the INTRODUCED map and the map
    grows a version that does not exist. Taken as a leading token plus a note,
    it becomes something better than clean data: the spec's own machine-readable
    record of WHICH column replaced the one F22 says was removed. Successors are
    documented in the spec, not only in the changelog.

    Returns (version, note).
    """
    line = _first_line(body)
    if not line:
        return "", ""
    m = re.match(r"^(\d+\.\d+(?:[-.]\w+)?)\s*(.*)$", line)
    if not m:
        return line, ""
    version, rest = m.group(1), m.group(2).strip()
    rest = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", rest)     # unwrap md links
    return version, rest


def _constraints_table(body):
    """Read the Content Constraints two-column markdown table into a dict.

    Markdown tables here look like:
        | Constraint    | Value     |
        | :------------ | :-------- |
        | Feature level | Mandatory |
    The header row and the :---: separator row are both discarded.
    """
    out = {}
    for line in body.split("\n"):
        line = line.strip()
        if not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if len(cells) < 2:
            continue
        key, value = cells[0], cells[1]
        if not key or set(key) <= set(":- "):        # separator row
            continue
        if key.lower() == "constraint":              # header row
            continue
        out[key.lower()] = value
    return out


def _allowed_values_table(body):
    """The 'Allowed values:' table as (header cells, data rows).

    Three different header shapes appear at v1.2 and a first-column-only reader
    gets one of them badly wrong:

        ChargeCategory      | Value           | Description |
        ServiceCategory     | Service Category| Description |
        ServiceSubcategory  | Service Category| Service Subcategory | Description |

    On ServiceSubcategory the first column is the PARENT category, so reading
    column 0 yields 83 repetitions of the 19 category names and not one actual
    subcategory. Silently. The list would look full and be entirely wrong.

    Keeping the whole table also hands chunk 3 the parent/child pairs for the
    section 2.10.2 map (ServiceSubcategory 'Virtual Machines' under anything but
    'Compute' is a hard fail) without a second pass or a hand-typed constant.
    """
    marker = body.lower().find("allowed values")
    if marker < 0:
        return [], []
    header, rows = [], []
    for line in body[marker:].split("\n")[1:]:
        line = line.strip()
        if not line.startswith("|"):
            if rows or header:
                break                                    # table has ended
            continue
        cells = [c.strip().strip("*_` ") for c in line.strip("|").split("|")]
        if all(set(c) <= set(":- ") for c in cells if c):  # the :--- separator
            continue
        if not header:
            header = cells
            continue
        rows.append(cells)
    return header, rows


def _pick_value_column(header, display_name):
    """Which column of the allowed-values table holds this column's own values.

    Preference order: a header cell matching the column's Display Name, then a
    header cell literally called "Value", then column 0. Matching on the display
    name is what keeps ServiceSubcategory off its parent column.
    """
    lowered = [h.lower() for h in header]
    if display_name and display_name.lower() in lowered:
        return lowered.index(display_name.lower())
    if "value" in lowered:
        return lowered.index("value")
    return 0


def _requirements(preamble, column_id):
    """Every bullet line from the preamble, with its severity and its depth.

    NORMATIVE bullets carry an ALL-CAPS RFC 2119 keyword. Lowercase "must" in
    prose is not a requirement, and treating it as one invents rules the spec
    never stated.

    NON-NORMATIVE bullets are kept too, with severity None — because they carry
    SCOPE. The spec nests its nullability rules:

        * CommitmentDiscountQuantity nullability is defined as follows:
          * When ChargeCategory is "Usage" or "Purchase" and CommitmentDiscountId
            is not null, ... adheres to the following additional requirements:
            * CommitmentDiscountQuantity MUST NOT be null when ChargeClass is
              not "Correction".

    Read flat, that MUST demands a commitment quantity on every non-correction
    row in the dataset. Read with its parent, it applies only to commitment
    rows. The parent has no capitalised keyword, so an earlier version of this
    function discarded it — and the rule then failed 47 conformant rows.

    Hence `indent`: the leading whitespace, which is what lets rules.py rebuild
    the ancestor chain and conjoin the scope back on. Finding F28.
    """
    out = []
    for line in preamble.split("\n"):
        stripped = line.strip()
        if not (stripped.startswith("* ") or stripped.startswith("- ")):
            continue
        text = stripped[2:].strip()
        # Strip the spec's glossary link syntax: [*billing period*](#glossary:...)
        clean = re.sub(r"\[\*?([^\]]*?)\*?\]\(#glossary:[^)]*\)", r"\1", text)
        clean = re.sub(r"\s+", " ", clean).strip()
        out.append({
            "text": clean,
            "severity": severity_of(text),      # None when not normative
            "indent": len(line) - len(line.lstrip()),
        })
    return out


def parse_column_file(path, tag, dataset):
    """One markdown file in, one ColumnSpec out."""
    with open(path, "rb") as f:
        raw = f.read()
    # Normalise line endings FIRST. Two v1.2 files are CRLF, and a trailing \r
    # makes a blank line look non-blank — which silently empties the Introduced
    # version on chargeclass.md and subaccountname.md.
    text = raw.decode("utf-8-sig").replace("\r\n", "\n").replace("\r", "\n")

    secs = _sections(text)
    file_name = os.path.basename(path)

    column_id = _first_line(secs.get("column id", ""))
    if not column_id:
        # No Column ID heading means this is not a column definition file.
        return None

    constraints = _constraints_table(
        secs.get("content constraints", "") or secs.get("content constraint", "")
    )
    # Where allowed values live moved at v1.3. Up to v1.2 the table sits inside
    # the Content Constraints body; from v1.3 the supplemental datasets give it
    # its own '## Allowed Values' heading. Reading only the first location
    # returns an EMPTY list for every v1.4 dataset column — and an empty allowed
    # list reads as "unconstrained", so the checks would quietly pass anything.
    #
    # Same shape of trap as F25: a structure that is consistent until it isn't,
    # failing silently rather than loudly.
    body_for_values = "\n".join(filter(None, [
        secs.get("content constraints", "") or secs.get("content constraint", ""),
        secs.get("allowed values", ""),
    ]))

    introduced, introduced_note = _introduced(secs.get("introduced (version)", ""))

    display_name = _first_line(secs.get("display name", "")) or _first_line(secs.get("display name ", ""))
    av_header, av_rows = _allowed_values_table(body_for_values)
    value_col = _pick_value_column(av_header, display_name)
    allowed = []
    for row in av_rows:
        if value_col < len(row) and row[value_col] and row[value_col] not in allowed:
            allowed.append(row[value_col])

    return ColumnSpec(
        column_id=column_id,
        file_name=file_name,
        tag=tag,
        dataset=dataset,
        display_name=display_name,
        feature_level=constraints.get("feature level", ""),
        allows_nulls=constraints.get("allows nulls", ""),
        data_type=constraints.get("data type", ""),
        value_format=constraints.get("value format", ""),
        column_type=constraints.get("column type", ""),
        introduced=introduced,
        introduced_note=introduced_note,
        allowed_values=allowed,
        allowed_value_header=av_header,
        allowed_value_rows=av_rows,
        subsection_tables=_subsection_tables(text),
        # WHERE REQUIREMENTS LIVE MOVED AT v1.4 — FOUND BY CHUNK 9.
        #
        # Up to v1.3 the normative bullets sit in the preamble, above the first
        # '## ' heading. At v1.4 they were given an explicit '## Requirements'
        # section. Reading only the preamble returns ZERO requirements for every
        # v1.4 column — and zero requirements produces zero checks, silently.
        #
        # It had already bitten: chunk 6a generated nullability and allowed-value
        # checks for the three supplemental datasets, all of which are v1.4, and
        # every generator returned nothing. Layer C was being validated for
        # column PRESENCE only. The run reported "Layer C (v1.4) | 3 checks" and
        # nothing was wrong enough to notice.
        #
        # **An empty rule list looks exactly like a clean dataset.** This is the
        # fourth structural change the spec repo has made across versions, and
        # the second to fail silently rather than loudly.
        requirements=(_requirements(secs.get("_preamble", ""), column_id)
                      + _requirements(secs.get("requirements", ""), column_id)),
        raw_url=raw_url(tag, file_name, dataset),
    )


def index_tag(tag, dataset="cost_and_usage", quiet=False):
    """Every column definition at one tag, keyed by Column ID.

    The KEY is the Column ID read from inside the file. The file name is kept
    as a field. Those two differ for three columns at v1.2 and conflating them
    is the trap this whole module was written around.
    """
    spec_root = ensure_tag(tag, quiet=quiet)
    rel = columns_path(tag, dataset)
    if rel is None:
        return {}
    folder = os.path.join(os.path.dirname(spec_root), rel)
    if not os.path.isdir(folder):
        return {}

    out = {}
    for name in sorted(os.listdir(folder)):
        if not name.endswith(".md"):
            continue
        col = parse_column_file(os.path.join(folder, name), tag, dataset)
        if col is None:
            continue
        if col.column_id in out:
            raise ValueError(
                f"{tag}/{dataset}: two files claim Column ID {col.column_id}: "
                f"{out[col.column_id].file_name} and {col.file_name}"
            )
        out[col.column_id] = col
    return out


# =============================================================================
# LIFECYCLE — INTRODUCED AND REMOVED
# =============================================================================

def lifecycle(dataset="cost_and_usage", quiet=False):
    """When each column arrived, and when it went away.

    INTRODUCED is taken from the spec's own "Introduced (version)" field where
    the column states one, and falls back to first-tag-seen otherwise. Two v1.2
    files leave it blank in a way that only bites if you forget the CR strip;
    the fallback is there so a future blank cannot produce a missing key.

    REMOVED is finding F22's requirement, and it can only be COMPUTED — no file
    announces its own deletion. A column is removed at tag N if it is present at
    tag N-1 and absent at N. The presence test is on Column ID, never on file
    name, which is the whole reason parse_column_file reads the ID from inside.

    F22 in one line: ProviderName and PublisherName are present through v1.3 and
    gone at v1.4. A check written on them cannot be expressed at v1.4 at all.
    """
    per_tag = {}
    for tag in TAGS:
        per_tag[tag] = index_tag(tag, dataset, quiet=quiet)

    introduced, removed, present_in = {}, {}, {}
    for tag in TAGS:
        for cid, col in per_tag[tag].items():
            present_in.setdefault(cid, []).append(tag)
            if cid not in introduced:
                introduced[cid] = col.introduced or tag.lstrip("v")

    for cid, tags_present in present_in.items():
        for earlier, later in zip(TAGS, TAGS[1:]):
            if earlier in tags_present and later not in tags_present:
                removed[cid] = later
                break

    return introduced, removed, per_tag


# =============================================================================
# MAIN
# =============================================================================

SUPPLEMENTAL = ["billing_period", "invoice_detail", "contract_commitment"]
SUPPLEMENTAL_TAG = "v1.4"


def write_supplemental(quiet=False):
    """The three supplemental datasets, indexed at v1.4.

    They do not exist before v1.3 — there is no earlier version to target — so
    Layer C is validated at v1.4 while the cost and usage dataset is validated at
    v1.2. **Two datasets in one project, conformant to two different versions of
    the same specification**, which is the version-lag thesis stated as a fact
    about our own repository rather than as an observation about providers.
    """
    written = []
    for dataset in SUPPLEMENTAL:
        index = index_tag(SUPPLEMENTAL_TAG, dataset, quiet=quiet)
        if not index:
            continue
        path = os.path.join(OUT, f"spec_{SUPPLEMENTAL_TAG}_{dataset}.json")
        with open(path, "w") as f:
            json.dump({cid: asdict(c) for cid, c in sorted(index.items())}, f, indent=2)
        written.append((dataset, len(index), path))
    return written


def main():
    os.makedirs(OUT, exist_ok=True)

    print("FOCUS specification source layer — Stage 4 chunk 1")
    print("=" * 68)
    print("\nFetching tags (cached after the first run):")
    introduced, removed, per_tag = lifecycle("cost_and_usage")

    target = per_tag[TARGET_TAG]
    print(f"\nColumns at {TARGET_TAG}: {len(target)}")

    # The Stage 3 open item: is the v1.2 list exhaustive, or merely verified?
    # The archive carries the directory, so this is now a count, not a hope.
    print(f"  directory listing counted, not sampled — the list is exhaustive")

    # The trap, stated in the output so it cannot be forgotten.
    odd = [c for c in target.values()
           if c.file_name != c.column_id.lower() + ".md"]
    print(f"\nColumns whose FILE NAME is not lower(ColumnID) + '.md': {len(odd)}")
    for c in sorted(odd, key=lambda c: c.column_id):
        print(f"    {c.column_id:<20} lives in {c.file_name}")
    print("  A path builder that infers the file name 404s on these three.")
    print("  A 404 is indistinguishable from 'removed'. Hence REMOVED is")
    print("  computed from Column IDs, never from file names.")

    print(f"\nLayout by tag:")
    for tag in TAGS:
        print(f"    {tag}  {columns_path(tag)}   ({len(per_tag[tag])} columns)")

    print(f"\nINTRODUCED — {len(introduced)} columns across all tags")
    by_version = {}
    for cid, ver in introduced.items():
        by_version.setdefault(ver, []).append(cid)
    for ver in sorted(by_version):
        print(f"    {ver:<12} {len(by_version[ver]):>2} columns")

    print(f"\nREMOVED — {len(removed)} columns (finding F22)")
    # A removed column usually has a successor, and the spec records it in the
    # Introduced field of the replacement ("1.3 Introduced as a replacement
    # for ProviderName"). So the successor map is derivable, not folklore.
    successors = {}
    for tag in TAGS:
        for cid, col in per_tag[tag].items():
            if col.introduced_note:
                for gone in removed:
                    if gone in col.introduced_note:
                        successors.setdefault(gone, []).append(cid)
    for cid, tag in sorted(removed.items()):
        succ = ", ".join(sorted(set(successors.get(cid, [])))) or "not stated in a column file"
        print(f"    {cid:<20} removed at {tag}   -> replaced by {succ}")
    if not removed:
        print("    none")
    if removed:
        print("  A check written on a removed column cannot be expressed at that")
        print("  tag at all — it fails to parse rather than returning a wrong")
        print("  answer. That is the safe failure mode, and the reason F22 wants")
        print("  removal treated as a migration case and not an afterthought.")

    # Regression guard: the Stage 3 seed script carries a hand-typed INTRODUCED
    # map. Two maps built by different methods agreeing is worth more than
    # either alone; two disagreeing is a finding. Checked, never assumed.
    seed = os.path.join(HERE, "seed_data.py")
    if os.path.exists(seed):
        text = open(seed).read()
        start = text.find("INTRODUCED = {")
        if start >= 0:
            block = text[start:]
            block = block[:block.index("\n}") + 2]
            hand = eval(block.split("=", 1)[1])            # noqa: S307 - our own file
            shared = set(hand) & set(introduced)
            bad = {k: (hand[k], introduced[k]) for k in shared if hand[k] != introduced[k]}
            missing = sorted(set(hand) - set(introduced))
            print(f"\nCross-check against seed_data.py's hand-built INTRODUCED map:")
            print(f"    {len(shared)} columns compared, {len(shared) - len(bad)} agree")
            if bad:
                for k, (h, d) in sorted(bad.items()):
                    print(f"    MISMATCH  {k:<20} seed says {h}, spec says {d}")
            if missing:
                print(f"    in seed but not in any tag: {missing}")
            if not bad and not missing:
                print("    Stage 3's map is independently confirmed by the specification.")

    # Severity distribution — the two-tier structure, sourced from the spec text
    # rather than hand-assigned. This is the F2 refinement made mechanical.
    musts = sum(len(c.musts) for c in target.values())
    shoulds = sum(len(c.shoulds) for c in target.values())
    infos = sum(1 for c in target.values() for r in c.requirements
                if r["severity"] == "INFO")
    non_normative = sum(1 for c in target.values() for r in c.requirements
                        if r["severity"] is None)
    print(f"\nNormative statements at {TARGET_TAG}, by RFC 2119 keyword:")
    print(f"    MUST / MUST NOT / SHALL / REQUIRED   {musts:>4}   -> FAIL")
    print(f"    SHOULD / SHOULD NOT / RECOMMENDED    {shoulds:>4}   -> WARN")
    print(f"    MAY / OPTIONAL                       {infos:>4}   -> INFO")
    print("  Severity is read off the keyword in the sentence, not assigned by")
    print("  hand. That is the two-tier harness, sourced from the spec itself.")
    print(f"    non-normative bullets kept for SCOPE  {non_normative:>4}   (F28)")
    print("  Parent bullets carry no keyword but do carry scope. Discarding them")
    print("  strips a rule of its context and it then fails conformant data.")

    # Finding F12 was noticed on two columns. With the spec as data it can be
    # scanned exhaustively instead — which turns "we found two" into "there are
    # exactly two", a materially stronger claim for a community issue.
    print(f"\nSelf-contradictions at {TARGET_TAG} — normative text vs Content Constraints:")
    contradictions = []
    for cid, col in sorted(target.items()):
        says_not_null = any(
            re.search(rf"\b{re.escape(cid)}\b\s+MUST NOT be null\.?$", req["text"])
            for req in col.requirements
        )
        if says_not_null and col.allows_nulls.lower() == "true":
            contradictions.append(cid)
            print(f"    {cid:<34} 'MUST NOT be null'  vs  'Allows nulls: True'")
    if not contradictions:
        print("    none")
    else:
        print(f"  {len(contradictions)} of {len(target)} columns, scanned exhaustively.")
        print("  This is finding F12, now bounded rather than merely observed.")

    print(f"\nFeature level at {TARGET_TAG}:")
    levels = {}
    for c in target.values():
        levels[c.feature_level or "(none)"] = levels.get(c.feature_level or "(none)", 0) + 1
    for level, n in sorted(levels.items()):
        print(f"    {level:<14} {n:>2}")

    # Write the artifacts the rest of Stage 4 reads.
    index_path = os.path.join(OUT, f"spec_{TARGET_TAG}.json")
    with open(index_path, "w") as f:
        json.dump({cid: asdict(c) for cid, c in sorted(target.items())}, f, indent=2)

    lifecycle_path = os.path.join(OUT, "lifecycle.json")
    with open(lifecycle_path, "w") as f:
        json.dump({
            "tags": TAGS,
            "target_tag": TARGET_TAG,
            "introduced": dict(sorted(introduced.items())),
            "removed": dict(sorted(removed.items())),
            "columns_per_tag": {t: len(per_tag[t]) for t in TAGS},
        }, f, indent=2)

    print(f"\nSupplemental datasets at {SUPPLEMENTAL_TAG} (they do not exist before v1.3):")
    for dataset, n, path in write_supplemental(quiet=True):
        mandatory = sum(1 for c in index_tag(SUPPLEMENTAL_TAG, dataset, quiet=True).values()
                        if (c.feature_level or "").lower() == "mandatory")
        print(f"    {dataset:<22} {n:>2} columns, {mandatory} Mandatory")
    print("  Layer C is validated at v1.4 while cost_and_usage is validated at")
    print("  v1.2 — one project, two datasets, two versions of one specification.")

    print(f"\nWritten:")
    print(f"    {os.path.relpath(index_path, ROOT)}")
    print(f"    {os.path.relpath(lifecycle_path, ROOT)}")
    print(f"    {os.path.relpath(CACHE, ROOT)}/   (add to .gitignore)")
    print("\nNo network access is needed downstream. validate.py reads the JSON.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
