"""
version_diff.py — Portfolio Project 1, Stage 4 chunk 9

WHAT CHANGED BETWEEN TWO VERSIONS OF THE SPECIFICATION, AND WHAT IT DOES TO US.

Build spec section 9 and Amendment 1 A5.2 both call for this: a way to answer
"what breaks if we move from v1.2 to v1.4" without reading two hundred markdown
files by hand.

It has two halves, and the second is the one worth having.

  1. THE DIFF. Columns added and removed, feature levels and nullability
     changed, requirement sentences added and withdrawn. Anyone with two copies
     of the specification could produce this.

  2. THE IMPACT ON THIS HARNESS. Which of the registered checks do not survive
     the move, and why. **That half is only possible because every check cites
     the sentence it came from.** A harness whose rules were transcribed by hand
     cannot answer it at all — it has nothing to compare against the new text,
     and the only way to find out what broke is to run it and read the failures.

Run:  python3 version_diff.py                v1.2 -> v1.4 (this project's case)
      python3 version_diff.py v1.1 v1.2      any pair of tags
      python3 version_diff.py --no-impact    the diff alone

Reads the cached specification. Fetches a tag if it is not already local.
"""

import argparse
import sys

import rules
import spec_source as S


def _norm_set(column):
    """Normative sentences for one column, normalised for comparison.

    Normalised because markdown link syntax and glossary asterisks change
    between releases without the requirement changing. Comparing raw text
    reports edits to formatting as edits to the rules, and a diff that cries
    wolf on punctuation is one nobody reads twice.
    """
    return {rules.normalise(r["text"]) for r in column.requirements if r["severity"]}


def diff(from_tag, to_tag, dataset="cost_and_usage"):
    a = S.index_tag(from_tag, dataset, quiet=True)
    b = S.index_tag(to_tag, dataset, quiet=True)

    added = sorted(set(b) - set(a))
    removed = sorted(set(a) - set(b))
    common = sorted(set(a) & set(b))

    successors = {}
    for cid in b:
        note = b[cid].introduced_note
        for gone in removed:
            if note and gone in note:
                successors.setdefault(gone, []).append(cid)

    changes = []
    for cid in common:
        before, after = a[cid], b[cid]
        entry = {"column": cid}
        if before.feature_level != after.feature_level:
            entry["feature_level"] = (before.feature_level, after.feature_level)
        if before.allows_nulls != after.allows_nulls:
            entry["allows_nulls"] = (before.allows_nulls, after.allows_nulls)
        if set(before.allowed_values) != set(after.allowed_values):
            entry["values_added"] = sorted(set(after.allowed_values)
                                           - set(before.allowed_values))
            entry["values_removed"] = sorted(set(before.allowed_values)
                                             - set(after.allowed_values))
        sa, sb = _norm_set(before), _norm_set(after)
        if sa != sb:
            entry["rules_added"] = sorted(sb - sa)
            entry["rules_removed"] = sorted(sa - sb)
        if len(entry) > 1:
            changes.append(entry)

    return a, b, added, removed, successors, changes


def impact(a, b, to_tag):
    """Which registered checks do not survive the move, and why.

    Three ways a check can fail to survive, and they are not equally bad:

      GONE      a column it reads was removed. The check cannot be expressed at
                the new version at all — it fails to parse rather than returning
                a wrong answer, which is the safe failure and the reason finding
                F22 asked for a REMOVED map.

      RESTATED  the sentence it cites no longer appears. The rule may have been
                withdrawn, or merely rewritten. **The harness cannot tell those
                apart and does not guess** — it reports the citation as stale and
                leaves the reading to a human, because silently re-binding a
                check to a similar-looking sentence is how a harness starts
                enforcing something the specification does not say.

      RELAXED   a MUST became a SHOULD, or a not-nullable column became
                nullable. The check still runs and would now be too strict.

    Importing validate.py here is deliberate: the impact is computed against the
    checks that ACTUALLY RUN, not against a list of what they are believed to be.
    """
    import validate as V

    spec, lifecycle = V.load_spec()
    V.build_registry(spec, lifecycle)

    gone, restated, relaxed = [], [], []
    for check in V.REGISTRY:
        if check.dataset != "cost_and_usage":
            continue
        missing = [c for c in check.columns if c in a and c not in b]
        if missing:
            gone.append((check, missing))
            continue
        for ref in check.refs:
            if ref.derived or ref.column not in b:
                continue
            if rules.normalise(ref.text) not in _norm_set(b[ref.column]):
                restated.append((check, ref))
                break
        else:
            for ref in check.refs:
                if ref.column not in a or ref.column not in b:
                    continue
                if (a[ref.column].allows_nulls == "False"
                        and b[ref.column].allows_nulls == "True"):
                    relaxed.append((check, ref, "column became nullable"))
                    break
    return gone, restated, relaxed


def main():
    ap = argparse.ArgumentParser(description="FOCUS specification version diff")
    ap.add_argument("from_tag", nargs="?", default="v1.2")
    ap.add_argument("to_tag", nargs="?", default="v1.4")
    ap.add_argument("--dataset", default="cost_and_usage")
    ap.add_argument("--no-impact", action="store_true",
                    help="diff the specification only, skip the harness impact")
    args = ap.parse_args()

    print(f"FOCUS specification diff — {args.from_tag} to {args.to_tag} "
          f"({args.dataset})")
    print("=" * 74)

    a, b, added, removed, successors, changes = diff(
        args.from_tag, args.to_tag, args.dataset)
    print(f"\nColumns: {len(a)} at {args.from_tag}, {len(b)} at {args.to_tag}")

    print(f"\nADDED ({len(added)})")
    for cid in added:
        note = b[cid].introduced_note
        print(f"    {cid:<36} {b[cid].feature_level}"
              + (f"   [{note}]" if note else ""))
    if not added:
        print("    none")

    print(f"\nREMOVED ({len(removed)})")
    for cid in removed:
        succ = ", ".join(successors.get(cid, [])) or "no successor named in a column file"
        print(f"    {cid:<36} -> {succ}")
    if not removed:
        print("    none")

    level = [c for c in changes if "feature_level" in c]
    nulls = [c for c in changes if "allows_nulls" in c]
    values = [c for c in changes if "values_added" in c]
    ruleset = [c for c in changes if "rules_added" in c]

    print(f"\nFEATURE LEVEL CHANGED ({len(level)})")
    for c in level:
        print(f"    {c['column']:<36} {c['feature_level'][0]} -> {c['feature_level'][1]}")
    if not level:
        print("    none")

    print(f"\nNULLABILITY CHANGED ({len(nulls)})")
    for c in nulls:
        before, after = c["allows_nulls"]
        arrow = "tightened" if after == "False" else "RELAXED"
        print(f"    {c['column']:<36} allows nulls {before} -> {after}   ({arrow})")
    if not nulls:
        print("    none")

    print(f"\nALLOWED VALUES CHANGED ({len(values)})")
    for c in values:
        if c["values_added"]:
            print(f"    {c['column']:<36} + {', '.join(c['values_added'])}")
        if c["values_removed"]:
            print(f"    {c['column']:<36} - {', '.join(c['values_removed'])}")
    if not values:
        print("    none")

    total_added = sum(len(c["rules_added"]) for c in ruleset)
    total_removed = sum(len(c["rules_removed"]) for c in ruleset)
    print(f"\nREQUIREMENT TEXT CHANGED — {len(ruleset)} columns, "
          f"{total_added} statements added, {total_removed} withdrawn")
    for c in ruleset[:8]:
        print(f"    {c['column']}")
        for text in c["rules_removed"][:2]:
            print(f"        - {text[:88]}")
        for text in c["rules_added"][:2]:
            print(f"        + {text[:88]}")
    if len(ruleset) > 8:
        print(f"    ... and {len(ruleset) - 8} more columns")

    if args.no_impact:
        return 0

    print(f"\n{'=' * 74}")
    print(f"IMPACT ON THIS HARNESS — which checks survive a move to {args.to_tag}")
    print("=" * 74)
    gone, restated, relaxed = impact(a, b, args.to_tag)

    print(f"\nCANNOT BE EXPRESSED AT {args.to_tag} — column removed ({len(gone)})")
    for check, missing in gone:
        print(f"    {check.id:<44} needs {', '.join(missing)}")
    if not gone:
        print("    none")

    print(f"\nCITATION IS STALE — the sentence no longer appears ({len(restated)})")
    for check, ref in restated[:12]:
        print(f"    {check.id:<44} {ref.column}")
        print(f"        {rules.normalise(ref.text)[:82]}")
    if len(restated) > 12:
        print(f"    ... and {len(restated) - 12} more")
    if not restated:
        print("    none")
    if restated:
        print("\n  A stale citation means the rule was withdrawn OR rewritten, and")
        print("  the harness cannot tell those apart. It does not guess: silently")
        print("  re-binding a check to a similar-looking sentence is how a harness")
        print("  starts enforcing something the specification does not say.")

    print(f"\nNOW TOO STRICT — a column became nullable ({len(relaxed)})")
    for check, ref, why in relaxed:
        print(f"    {check.id:<44} {ref.column}: {why}")
    if not relaxed:
        print("    none")

    print(f"\n{'=' * 74}")
    print("This second half is only possible because every check cites the")
    print("sentence it came from. A harness built from transcribed rules has")
    print("nothing to compare against the new text — the only way to find out")
    print("what a version upgrade broke is to run it and read the failures.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
