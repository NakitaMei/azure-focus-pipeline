"""
rules.py — Portfolio Project 1, Stage 4 chunk 3

THE STRUCTURAL RULES, DERIVED FROM THE SPECIFICATION'S OWN SENTENCES.

Chunk 2 built the harness. This builds the first substantial body of rules to run
in it — and it builds them by READING the specification's requirement sentences,
not by transcribing them into a table.

WHY PARSE INSTEAD OF TRANSCRIBE
There are 85 nullability statements at v1.2. Hand-writing 85 assertions is a
morning's work and produces a harness that is correct on the morning it is
written. Every one of those assertions is then a place where a transcription
error can hide, and there is no way to tell a transcribed rule from an invented
one by reading the code. The keepsake's near-miss on assertion 2.4.4 — the
truncated sentence that dropped `AND ChargeCategory is "Usage"` — is exactly this
failure, and it survived review because a hand-written assertion looks the same
whether or not it matches its source.

So the sentences are parsed. What cannot be parsed is REPORTED, never dropped.
A parser that silently skips what it does not understand is worse than a hand
list, because the gap is invisible.

THE COVERAGE, MEASURED
    20  unconditional        X MUST NOT be null.
    46  column-conditioned   X MUST be null when Y is null. (and richer forms)
    18  semantically gated   condition the data does not carry — see below
     1  needs sibling context
    --
    85  total

The 18 are the interesting number. They are conditions like "when a charge is
related to a resource" or "when the resource has an assigned display name" —
true or false in the world, and unknowable from the row. **They are not gaps in
the harness. They are gaps in what any harness can do**, and naming them with
reasons is worth more than a coverage percentage.

THE PRUNING RULE — WHY A PARTIALLY-SEMANTIC CONDITION IS SOMETIMES USABLE
Consider the ResourceName rules at v1.2:

    ResourceName MUST be null when ResourceId is null OR when the resource
        does not have an assigned display name.
    ResourceName MUST NOT be null when ResourceId is not null AND the
        resource has an assigned display name.

Both mix a checkable term with a semantic one. They are NOT equally usable:

  - In the first, the two branches are joined by OR, and either one alone is
    sufficient to require null. Dropping the semantic branch narrows WHEN the
    rule fires. It never fires wrongly. **Safe, and implemented.**
  - In the second they are joined by AND, and both must hold. Dropping the
    semantic conjunct makes the rule fire more often than the spec says —
    demanding a name for every identified resource. A conformant nameless
    resource would fail. **Unsafe, and not implemented.**

The general principle: **you may narrow when a rule applies; you may never
broaden it.** Dropping a disjunct from an OR is a narrowing. Dropping a conjunct
from an AND is a broadening. This is finding F10's lesson stated as a rule —
scope is the thing to get right, and getting it wrong produces confident,
wrong failures.

Applied blind to the specification text, that pruning rule reproduces Amendment 1
section A7.2 exactly: assertion 1 (ResourceId null implies ResourceName null)
implemented, assertion 3 (do NOT assert the reverse) refused. A correction
derived by hand in July, arrived at independently by the parser.

Imported by validate.py. Reads only the chunk 1 JSON. No network, no data.
"""

import json
import re

# Bumped whenever validate.py starts depending on something new here. The two
# files are edited together and shipped separately, so they can drift out of
# step on the receiving machine — and when they do, the symptom is an
# AttributeError raised hundreds of lines into a run, which reads like a bug in
# the harness rather than a stale file. validate.py checks this at startup.
RULES_VERSION = 4      # 4 = chunk 7, SHOULD-level nullability rules carry their severity

# =============================================================================
# 1. NORMALISING A REQUIREMENT SENTENCE
# =============================================================================

def normalise(text):
    """Strip markdown so a sentence can be matched against a grammar.

    Two things get in the way. Cross-references are markdown links —
    `[BillingAccountId](#billingaccountid)` — and glossary terms are wrapped in
    asterisks — `*charge*`. Both are presentation, not meaning.
    """
    text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", text)
    text = text.replace("*", "")
    return re.sub(r"\s+", " ", text).strip().rstrip(".")


def name_lookup(spec):
    """Map every way the spec refers to a column onto its Column ID.

    Necessary because the spec is not consistent. `commitmentdiscountstatus.md`
    writes its cross-reference as "Charge Category" — the DISPLAY name, with a
    space — where every other file writes "ChargeCategory". A parser keyed only
    on Column IDs fails to resolve it, and the sentence it fails on is assertion
    2.4.4: the one the keepsake records as nearly built wrong.
    """
    out = {cid: cid for cid in spec}
    for cid, entry in spec.items():
        display = entry.get("display_name")
        if display:
            out[display] = cid
    return out


# =============================================================================
# 2. CONDITIONS
# =============================================================================
# Phrases that describe the world rather than the row. A condition containing
# one of these cannot be evaluated from data at any level of effort — the fact
# it turns on is simply not in the dataset.

SEMANTIC_MARKERS = [
    "is related to", "is not related to", "does not have", "has an assigned",
    "can be assigned", "provider supports", "does not represent", "represents",
    "is operated in", "specific to", "associated with", "not associated",
]

SEMANTIC = {"kind": "semantic"}


def parse_clause(clause, names):
    """One atomic condition: `X is null`, `X is not "A"`, `X is "A" or "B"`."""
    clause = clause.strip()
    clause = re.sub(r"^when ", "", clause).strip().rstrip(",")

    if any(marker in clause for marker in SEMANTIC_MARKERS):
        return dict(SEMANTIC, text=clause)

    match = re.match(r"^(.+?) is (not )?null$", clause)
    if match and match.group(1).strip() in names:
        kind = "not_null" if match.group(2) else "null"
        return {"kind": kind, "column": names[match.group(1).strip()]}

    match = re.match(r'^(.+?) is (not )?("[^"]+"(?: or "[^"]+")*)$', clause)
    if match and match.group(1).strip() in names:
        values = re.findall(r'"([^"]+)"', match.group(3))
        return {"kind": "ne" if match.group(2) else "eq",
                "column": names[match.group(1).strip()], "values": values}

    return None


def parse_condition(text, names):
    """A condition tree, or None if the grammar does not cover the sentence.

    Precedence follows the English: top-level OR is written ", or when ...", and
    AND binds tighter. `ChargeCategory is "Usage" or "Purchase" and ChargeClass
    is not "Correction"` therefore reads as (Category in {Usage, Purchase}) AND
    (Class != Correction) — the value list belongs to one clause and must be
    consumed before splitting on "and".
    """
    terms = [t for t in re.split(r",? or when ", text) if t.strip()]
    branches = []
    for term in terms:
        # Split on "and", tolerating the Oxford comma. The nullability
        # sentences write "A and B"; the metric sentences write "A, B, and C".
        # Same conjunction, different punctuation, and a splitter that only
        # knows the first form silently fails to parse the second.
        # Split on "and", tolerating the Oxford comma AND bare comma series.
        # The nullability sentences write "A and B"; the metric sentences write
        # "A, B, and C". Same conjunction, different punctuation, and a splitter
        # that knows only the first form silently fails to parse the second —
        # silently, which is the part that matters.
        conjuncts = [parse_clause(c, names)
                     for c in re.split(r",\s*(?:and\s+)?|\s+and\s+", term) if c.strip()]
        if any(c is None for c in conjuncts):
            return None
        branches.append({"kind": "and", "terms": conjuncts}
                        if len(conjuncts) > 1 else conjuncts[0])
    return {"kind": "or", "terms": branches} if len(branches) > 1 else branches[0]


def prune(node, in_or):
    """Remove semantic leaves, or refuse to.

    Returns (pruned_node_or_None, was_pruned). See the module docstring: pruning
    a disjunct NARROWS when the rule fires and is safe; pruning a conjunct
    BROADENS it and is not.
    """
    if node["kind"] == "semantic":
        return (None, True) if in_or else (None, False)

    if node["kind"] == "or":
        kept, pruned_any = [], False
        for term in node["terms"]:
            got, ok = prune(term, in_or=True)
            if got is None:
                pruned_any = True
                if not ok:
                    return None, False
            else:
                kept.append(got)
        if not kept:
            return None, True
        node = kept[0] if len(kept) == 1 else {"kind": "or", "terms": kept}
        return node, pruned_any

    if node["kind"] == "not":
        got, ok = prune(node["term"], in_or=False)
        return (None, False) if got is None else (negate(got), False)

    if node["kind"] == "and":
        kept = []
        for term in node["terms"]:
            got, ok = prune(term, in_or=False)
            if got is None:
                return None, False          # a conjunct cannot be dropped
            kept.append(got)
        return ({"kind": "and", "terms": kept} if len(kept) > 1 else kept[0]), False

    return node, False


def negate(node):
    """Logical NOT. Needed for the spec's 'in all other cases' construction."""
    return {"kind": "not", "term": node}


def columns_in(node):
    if node["kind"] == "not":
        return columns_in(node["term"])
    if node["kind"] in ("and", "or"):
        out = []
        for term in node["terms"]:
            out.extend(columns_in(term))
        return out
    return [node["column"]] if "column" in node else []


def is_null(value, empty_is_null=True):
    """Null, for the purpose of evaluating a nullability condition.

    FINDING F32. Azure's real export writes '' where it means NULL in 13
    columns, 1,406 values in all. FOCUS StringHandling makes that a SHOULD NOT
    — a recommendation, not a requirement — so on its own it is a warning.

    Its CONSEQUENCE is not a warning. `CommitmentDiscountId` holds '' on all 118
    real rows, and '' is not null, so `CommitmentDiscountId is not null` is true
    everywhere and three cascade rules demand a category, status and type on
    rows that have no commitment. 118 x 3 = 354 MUST failures, none of them
    real, every one attributed to the wrong rule.

    So for evaluating nullability, '' counts as null: it is what the provider
    meant. The placeholder itself is still reported, as a warning, by the
    empty-string check — and the number of findings suppressed by this reading
    is counted and printed, so nothing is quietly disappeared.

    **A SHOULD NOT breach manufacturing hundreds of phantom MUST breaches is the
    real argument for fixing empty strings.** Not tidiness — the damage is done
    downstream, to anyone consuming the data.
    """
    if value is None:
        return True
    return empty_is_null and isinstance(value, str) and value == ""


def evaluate(node, row, empty_is_null=True):
    """Is this condition true of this row?"""
    kind = node["kind"]
    if kind == "not":
        return not evaluate(node["term"], row, empty_is_null)
    if kind == "and":
        return all(evaluate(t, row, empty_is_null) for t in node["terms"])
    if kind == "or":
        return any(evaluate(t, row, empty_is_null) for t in node["terms"])
    value = row.get(node["column"])
    if kind == "null":
        return is_null(value, empty_is_null)
    if kind == "not_null":
        return not is_null(value, empty_is_null)
    if kind == "eq":
        return value in node["values"]
    if kind == "ne":
        return value not in node["values"]
    return False


def describe(node):
    kind = node["kind"]
    if kind == "not":
        return f"not ({describe(node['term'])})"
    if kind == "and":
        return " and ".join(describe(t) for t in node["terms"])
    if kind == "or":
        return "(" + " or ".join(describe(t) for t in node["terms"]) + ")"
    if kind == "null":
        return f"{node['column']} is null"
    if kind == "not_null":
        return f"{node['column']} is not null"
    if kind == "eq":
        return f"{node['column']} in {node['values']}"
    if kind == "ne":
        return f"{node['column']} not in {node['values']}"
    return "?"


def ancestor_scope(requirements, index, names):
    """The conditions a bullet inherits from the bullets it is nested under.

    FINDING F28. The specification nests its nullability rules, and the scope
    lives in the parent:

        * CommitmentDiscountQuantity nullability is defined as follows:
          * When ChargeCategory is "Usage" or "Purchase" and CommitmentDiscountId
            is not null, ... adheres to the following additional requirements:
            * CommitmentDiscountQuantity MUST NOT be null when ChargeClass is
              not "Correction".

    Flattened, that MUST demands a commitment quantity on EVERY non-correction
    row. Scoped, it applies only to commitment rows. The difference on this
    project's own data is 47 false failures.

    This is finding F10's lesson arriving from the opposite direction. F10 was a
    MUST whose scope the spec never states. F28 is a MUST whose scope the spec
    states clearly — in a line the parser threw away. Both produce the same
    thing: a confident, wrong failure. **Scope is the hard part of turning a
    MUST into an assertion, whether the spec gives it to you or not.**

    Returns (conditions, unparsed_ancestors).
    """
    depth = requirements[index]["indent"]
    chain = []
    for j in range(index - 1, -1, -1):
        if requirements[j]["indent"] < depth:
            chain.append(requirements[j])
            depth = requirements[j]["indent"]
            if depth == 0:
                break

    conditions, unparsed = [], []
    for ancestor in chain:
        text = normalise(ancestor["text"])
        # "When <condition>, X adheres to the following additional requirements:"
        # and the bare "When <condition>:" form.
        match = re.match(r"^When (.+?),? [A-Za-z]+ adheres to the following.*$", text)
        if not match:
            match = re.match(r"^When (.+?):?$", text)
        if not match:
            continue                      # e.g. "X nullability is defined as follows:"
        parsed = parse_condition(match.group(1), names)
        if parsed is None:
            unparsed.append(text)
        else:
            conditions.append(parsed)
    return conditions, unparsed


def sibling_scopes(requirements, index, names):
    """Scope conditions of the bullets alongside this one, for 'in all other cases'.

    `CommitmentDiscountQuantity MUST be null in all other cases` is meaningless
    alone — chunk 3's first pass refused it for exactly that reason. Read in
    place it is precise: "all other cases" is the negation of its sibling's
    scope. Restoring the nesting makes an unparseable sentence parseable.
    """
    depth = requirements[index]["indent"]
    parent = None
    for j in range(index - 1, -1, -1):
        if requirements[j]["indent"] < depth:
            parent = j
            break
    if parent is None:
        return []

    scopes = []
    for j in range(parent + 1, len(requirements)):
        if j == index:
            continue
        if requirements[j]["indent"] < depth:
            break
        if requirements[j]["indent"] != depth:
            continue
        text = normalise(requirements[j]["text"])
        match = re.match(r"^When (.+?),? [A-Za-z]+ adheres to the following.*$", text)
        if not match:
            match = re.match(r"^When (.+?):?$", text)
        if not match:
            continue
        parsed = parse_condition(match.group(1), names)
        if parsed is not None:
            scopes.append(parsed)
    return scopes


def conjoin(*conditions):
    """AND a set of conditions, dropping the Nones."""
    terms = [c for c in conditions if c is not None]
    if not terms:
        return None
    return terms[0] if len(terms) == 1 else {"kind": "and", "terms": terms}


# =============================================================================
# 3. EXTRACTING NULLABILITY RULES
# =============================================================================

NULL_RE = re.compile(r"\b(?:MUST|SHOULD) (NOT )?be null\b")


def nullability_rules(spec):
    """Every nullability statement at v1.2, parsed or explicitly refused.

    Returns (rules, refused). A rule is a dict with:
        column, must_be_null, condition (None = unconditional), partial, text
    A refusal carries the sentence and the reason it was not implemented, so the
    conformance report can list what the harness does NOT check, and why.
    """
    names = name_lookup(spec)
    rules, refused = [], []

    for cid, entry in sorted(spec.items()):
        reqs = entry["requirements"]
        for index, req in enumerate(reqs):
            # CHUNK 7: SHOULD-level nullability statements are rules too. Only
            # MUSTs were taken until now, which is why "85 nullability
            # statements" meant 85 MUST-level ones and the WARN tier sat almost
            # empty. A near-zero WARN column that reflects unwritten checks
            # rather than clean data invites exactly the wrong conclusion.
            if req["severity"] not in ("FAIL", "WARN"):
                continue                       # scope bullets and MAYs are not rules
            text = normalise(req["text"])
            if not NULL_RE.search(text):
                continue

            # F28: whatever this bullet is nested under scopes it.
            scopes, unparsed_scope = ancestor_scope(reqs, index, names)
            if unparsed_scope:
                refused.append({
                    "column": cid, "text": req["text"],
                    "reason": f"nested under a scope this parser cannot read: "
                              f"{unparsed_scope[0][:70]}",
                })
                continue
            inherited = conjoin(*scopes)

            match = re.match(rf"^{re.escape(cid)} (?:MUST|SHOULD) (NOT )?be null$", text)
            if match:
                rules.append({
                    "column": cid, "must_be_null": not match.group(1),
                    "condition": inherited, "partial": False,
                    "severity": req["severity"],
                    "text": req["text"], "url": entry["raw_url"],
                })
                continue

            # "in all other cases" = the negation of the sibling's scope. Only
            # recoverable once the nesting is restored (F28).
            if re.match(rf"^{re.escape(cid)} (?:MUST|SHOULD) (NOT )?be null in all other cases$", text):
                others = sibling_scopes(reqs, index, names)
                if not others:
                    refused.append({
                        "column": cid, "text": req["text"],
                        "reason": "'in all other cases' with no sibling scope to negate",
                    })
                    continue
                combined = others[0] if len(others) == 1 else {"kind": "or", "terms": others}
                rules.append({
                    "column": cid,
                    "must_be_null": not re.match(rf"^{re.escape(cid)} (?:MUST|SHOULD) NOT", text),
                    "condition": conjoin(inherited, negate(combined)),
                    "partial": False,
                    "severity": req["severity"],
                    "text": req["text"], "url": entry["raw_url"],
                })
                continue

            match = re.match(rf"^{re.escape(cid)} (?:MUST|SHOULD) (NOT )?be null when (.+)$", text)
            if not match:
                refused.append({
                    "column": cid, "text": req["text"],
                    "reason": "sentence depends on the statement before it "
                              "('in all other cases') — not independently parseable",
                })
                continue

            must_be_null = not match.group(1)
            tree = parse_condition(match.group(2), names)
            if tree is None:
                refused.append({
                    "column": cid, "text": req["text"],
                    "reason": "condition grammar not recognised",
                })
                continue

            pruned, was_pruned = prune(tree, in_or=False)
            if pruned is None:
                # Two distinct reasons, and the report should not blur them.
                # A bare semantic condition is unknowable full stop. A semantic
                # CONJUNCT is knowable in part, and refused on the pruning rule
                # rather than on ignorance.
                bare = tree.get("kind") == "semantic"
                refused.append({
                    "column": cid, "text": req["text"],
                    "reason": ("condition turns on a fact the row does not carry"
                               if bare else
                               "condition mixes a checkable term with a fact the row "
                               "does not carry, joined by AND — dropping the unknown "
                               "conjunct would broaden the rule and fail good data"),
                })
                continue

            rules.append({
                "column": cid, "must_be_null": must_be_null,
                "condition": conjoin(inherited, pruned), "partial": was_pruned,
                "severity": req["severity"],
                "text": req["text"], "url": entry["raw_url"],
            })

    return rules, refused


def presence_expectations(spec, lifecycle):
    """Which columns must simply BE THERE, and from which version.

    Presence and nullability are different questions and the build spec is
    emphatic that conflating them lets a broken dataset pass: is the column in
    the dataset (Feature Level) versus is the value in the row (Null Handling).
    A dataset missing ServiceCategory entirely and a dataset with a null
    ServiceCategory are different defects with different causes.

    Only Mandatory columns are asserted. Conditional columns are required only
    when their condition holds, and that condition is prose — the same class of
    unknowable the nullability parser refuses. Reported, not asserted.
    """
    mandatory, conditional = [], []
    for cid, entry in sorted(spec.items()):
        level = (entry.get("feature_level") or "").lower()
        introduced = lifecycle["introduced"].get(cid, "0.5")
        if level == "mandatory":
            mandatory.append((cid, introduced))
        elif level == "conditional":
            conditional.append((cid, introduced))
    return mandatory, conditional


def service_parent_map(spec):
    """Which ServiceSubcategory values belong under which ServiceCategory.

    Taken from the allowed-values table of servicesubcategory.md, whose first
    column is the parent. Chunk 1 keeps the whole table for this reason; the
    Stage 3 self-test carried the same map hand-typed, and the two agree.
    """
    entry = spec.get("ServiceSubcategory")
    if not entry:
        return {}
    out = {}
    for row in entry.get("allowed_value_rows", []):
        if len(row) >= 2 and row[0] and row[1]:
            out.setdefault(row[0], set()).add(row[1])
    return out


def coverage(spec):
    """A summary of what the harness derives, for the conformance report."""
    rules, refused = nullability_rules(spec)
    return {
        "nullability_total": len(rules) + len(refused),
        "implemented": len(rules),
        "partial": sum(1 for r in rules if r["partial"]),
        "refused": len(refused),
        "refusals": refused,
    }
