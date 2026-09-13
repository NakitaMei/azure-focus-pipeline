# Stage 4 — Working Notes (Conformance Harness)

**Project:** Azure Cost Management → FOCUS Pipeline (Portfolio Project 1)
**Stage:** 4 — spec-derived conformance harness · **Status: in progress**
**Started:** 15 August 2026
**Input:** `focus_unified` (204 rows × 114 columns, three eras), `data/negative/`
(14 planted violations), the three Layer C CSVs
**Findings continue the Stage 3 numbering.** F6–F22 are in `STAGE3_WORKING_NOTES.md`;
Stage 4 opens at F23.

---

## 1. What Stage 4 is

Stage 3 built the data. Stage 4 builds the thing that judges it — and the point
of the exercise is not "does my data pass." It is that **the harness's rules must
be traceable to sentences in the specification**, at a stated version tag, rather
than typed in from memory or lifted from a course.

Three requirements shape every design decision, all inherited from Stage 3
findings:

- **Two severities.** MUST breaks are failures, SHOULD breaks are warnings.
  One severity makes a harness either too noisy to use or too permissive to
  trust (F2 refined).
- **Era awareness.** `focus_unified` holds three schema eras in one table. A rule
  about a column introduced at 1.2 cannot be applied to a 1.0-era row.
- **Scope.** A MUST with an unstated scope, implemented literally, fails every
  real dataset it is pointed at — confidently (F10).

The measure of success is not a clean report. It is **14 of 14 planted violations
caught in `data/negative/`**. A harness that has only ever seen valid data has
never been proven to detect anything.

---

## 2. The two pieces, in plain language

### `spec_source.py` — the specification, as data

It goes and gets the FOCUS specification, keeps a local copy, and turns each
column's markdown file into a structured record: what the column requires, how
strongly, whether it may be null, what values it permits, and which version
introduced it.

Everything downstream reads the JSON this produces. **Nothing else in Stage 4
touches the network.** That means the harness runs offline, runs identically on
any machine, and — the part that matters for a public repo — the exact
specification text behind every check is committed where a reader can audit it.

### `validate.py` — the machine that runs rules

It defines what a check *is*: an identifier, a function, and **a citation**. A
check without a citation refuses to register. That is a one-line guard, and it is
the structural difference between a conformance harness and a pile of opinions.

Around that sits the scaffolding: which rows a check may look at (the era gate),
which datasets it may touch (the binding rules), and how results are scored.

### The seven parts of `validate.py`

1. **Version ordering** — FOCUS versions do not sort as text (`1.0-preview`
   precedes `1.0`), so the order is declared once and every comparison goes
   through it.
2. **What a check is** — `SpecRef`, `Check`, `Violation`, and a registry that
   rejects uncited rules.
3. **Horizons** — the version window in which each check is expressible at all.
4. **Datasets** — discovery, and reporting what is *missing* as loudly as what
   is found.
5. **The era gate** — in two modes, which turned out to be the whole game (F27).
6. **The first check family** — allowed values, built entirely from the spec.
7. **Running and reporting** — including the negative-proof table.

---

## 3. Glossary — Stage 4 additions

| Term | Meaning here |
|---|---|
| **RFC 2119** | The IETF convention FOCUS adopts for requirement keywords. Only the ALL-CAPS forms are normative — a lowercase "must" in prose is not a requirement. |
| **Normative** | Text that states a requirement. Distinguished from descriptive prose and from the Content Constraints table, which is metadata about the column. |
| **Feature level** | The spec's own presence classification: Mandatory, Conditional, Recommended. Distinct from nullability — presence is about the column, nullability about the value. |
| **Schema era** | Which FOCUS version a row was emitted under. Carried in `x_SchemaEra`. Three values in this project: `1.0r2`, `1.2`, `pre-1.2`. |
| **Era ceiling** | The newest FOCUS version whose columns a row of a given era may contain. A ceiling, not a label — see F27. |
| **Horizon** | The version window in which a check can be written at all: from the latest INTRODUCED among its columns, to the earliest REMOVED. |
| **Binding** | Which datasets a check may run against. Enforced in code, not by comment. |
| **Dataclass** | A Python record type. Writes its own constructor and a readable printout; `asdict()` turns it into JSON-ready dictionaries. |
| **Glob** | Filename pattern matching (`*.parquet`). Used instead of a manifest read where no manifest exists. |

---

## 4. Findings

### F23 — the spec file name is not the Column ID, and the failure looks like F22

At v1.2 three files are not named after the column they define:

| File | Column ID |
|---|---|
| `provider.md` | `ProviderName` |
| `publisher.md` | `PublisherName` |
| `invoiceissuer.md` | `InvoiceIssuerName` |

A path builder doing `column.lower() + ".md"` returns **404** on exactly these
three. And a 404 is indistinguishable from *"this column was removed"* — which is
what F22 is about.

**Left unhandled, the `REMOVED` map reports `ProviderName` as removed at v1.2.**
That is false, it is the same three columns F22 already touches, and it would look
entirely plausible in a report.

The fix is small and the principle is not: **the Column ID is read from inside
each file, never inferred from the file name**, and `REMOVED` is computed from
Column IDs. Recorded because the *class* of error recurs — an identifier that is
usually derivable, until it isn't, with a failure mode that mimics a real finding.

### F24 — F10 has a sibling in the same file, and it is worse

`effectivecost.md` at v1.2 states a second unscoped invariant:

> The sum of EffectiveCost where ChargeCategory is "Usage" MUST equal the sum of
> EffectiveCost where ChargeCategory is "Usage" and CommitmentDiscountStatus is
> "Used", plus the sum of EffectiveCost where ChargeCategory is "Usage" and
> CommitmentDiscountStatus is "Unused".

Read globally, this requires **every** Usage row to carry a non-null
`CommitmentDiscountStatus`. On-demand usage never does — and the spec itself
requires that status to be null when `CommitmentDiscountId` is null. So the
invariant contradicts a sibling column's nullability rule unless it is read as
commitment-scoped.

Same failure mode as F10, same file, and the same fix: scope the assertion to a
commitment. Chunk 4 implements both together.

**It strengthens the community issue considerably.** One unscoped invariant is an
oversight. Two adjacent ones in the same file is a pattern, and the issue can be
written as "this file needs a scoping clause" rather than "I think this one line
is wrong."

### F25 — the allowed-values table has three shapes, and the wrong one reads silently

| Column | Table header |
|---|---|
| `ChargeCategory` | `Value \| Description` |
| `ServiceCategory` | `Service Category \| Description` |
| `ServiceSubcategory` | `Service Category \| Service Subcategory \| Description` |

A first-column reader is correct on two of these and wrong on the third: on
`ServiceSubcategory` the first column is the **parent category**, so it returns 82
repetitions of the 19 category names and not one actual subcategory. The list
looks full. It is entirely wrong.

The parser picks the column whose header matches the column's Display Name. That
also hands the §2.10.2 parent-map check its pairs for free, with no second pass
and no hand-typed constant.

**The general lesson, and it is the Stage 3 pattern recurring:** a structure that
is consistent across most instances is not a structure you have verified. Two out
of three files agreeing is how a wrong reader gets shipped.

### F26 — the empty-string sweep has nowhere conformant to point on the real layer

`build_unified.py` declares `SANITISED_DIR = data/raw-sanitised` at line 37 **and
never writes to it.** The sanitised real rows exist only as an in-memory DuckDB
view inside that script.

That collides with handover guardrail 1. The sweep must bind to a per-layer view,
and on Layer 1 there are three candidates:

| Location | Problem |
|---|---|
| `data/raw/` | Holds the 1,406 empty strings, but is unsanitised (F6) and can never be committed. A published harness cannot read it. |
| `data/unified/` | D3 normalised `''` → NULL. The sweep reports zero and looks like a pass. **The exact foot-gun the guardrail names.** |
| `data/raw-sanitised/` | The right answer. Does not exist on disk. |

**Not yet resolved — it changes a signed-off Stage 3 deliverable.** The fix is a
few lines in `build_unified.py` to write the sanitised layer out with an
Azure-shaped manifest beside it. Must be settled before chunk 7.

Worth noting *how* this surfaced: the chunk 2 loader reports missing datasets as
loudly as found ones. Had it silently skipped absent folders, this would have been
discovered in chunk 7 as a sweep returning zero — which is indistinguishable from
a pass.

### F27 — the declared version is a floor, not a description

**Found by running the era gate and reading its scope notes.**

Azure's real export declares FOCUS **1.0r2** in its manifest. It populates
`BillingAccountType` and `SubAccountType` — both **introduced at v1.2** — on all
118 real rows. Values are `"Billing Profile"` and `"Subscription"`: real Azure
values, not artefacts of the merge. Scanned exhaustively across all 114 columns;
exactly these two.

This is **not a conformance failure.** Nothing forbids a provider from shipping
ahead of the version it declares, and over-delivering is the good direction to err
in. It is reported as INFO.

**What it breaks is an assumption the harness naturally makes.** A gate keyed
purely on the declared version would skip those two columns on 118 rows and report
a clean pass on data it never examined.

So "era-aware" turns out to mean two different things:

| Mode | Applies to | Gated? |
|---|---|---|
| `ERA_REQUIREMENT` | Rules that **require** something — presence, non-nullness, cascades | **Yes.** You cannot require a column that did not exist yet. Applying the rule anyway fails good data. |
| `ERA_VALUE` | Rules that **constrain a value that is present** | **No.** If a value is in the row it must be valid, whatever version the row claims. |

**This is the mirror image of F10, and the more dangerous of the two.** F10 fails
good data loudly — you notice. F27 passes unchecked data silently — you do not.
Every check from chunk 3 onward must declare its mode, and the default is
`ERA_REQUIREMENT` so that forgetting produces the loud failure rather than the
quiet one.

A `META-declaration-drift` check reports the condition on every dataset, so the
gap between what a provider declares and what it ships is measured rather than
assumed.

### Corrections to Stage 3 findings

- **F22 — the repo layout changes at v1.3, not v1.4.** Verified by HTTP status
  across all five tags: `specification/columns/` returns 200 at v1.0–v1.2 and 404
  at v1.3–v1.4. The removal of `ProviderName`/`PublisherName` is correctly dated
  at v1.4; the *path* restructure is one release earlier. A version-aware path
  builder that switches at 1.4 fails on every v1.3 lookup.
- **F22 — the successor is stated in the spec, not only the changelog.**
  `serviceprovidername.md` records its own Introduced field as *"1.3 Introduced as
  a replacement for ProviderName"*. So the successor map is derivable. No column
  file names a successor for `PublisherName`; the harness reports that gap rather
  than inferring one.
- **F12 — now bounded, not merely observed.** With the spec as data, all 57
  columns were scanned for "normative says MUST NOT be null, table says Allows
  nulls: True". **Exactly two:** `PricingCurrency` and
  `PricingCurrencyEffectiveCost`. That upgrades the community issue from "I found
  two" to "there are two, and here is the scan."

### Two Stage 3 open items closed

- **The v1.2 column list is exhaustive at 57.** Counted from the directory, not
  sampled. The GitHub contents API still rate-limits anonymous callers — the same
  wall Stage 3 hit — but the tag archive does not, and it carries the listing.
- **Stage 3's hand-built maps are independently confirmed.** `seed_data.py`'s
  `INTRODUCED`: 57 columns compared, **57 agree**. `self_test.py`'s `ALLOWED`: all
  seven enum columns match. Its `SERVICE_SUBCATEGORIES`: 19 categories, 82 pairs,
  exact match. Two maps built by different methods agreeing is worth more than
  either alone.

---

## 5. Decision register

### D10 — spec transport: the tag archive, not 57 individual raw fetches

Build spec §9 specifies per-column raw-file fetches. **The principle is kept —
raw files, never rendered documentation.** Only the transport changes: one archive
download per tag.

Two reasons. One request instead of 57, avoiding the rate limit that blocked the
Stage 3 attempt to confirm the column list. And a per-file fetch can only confirm
files you already knew to ask for — it structurally cannot prove a list is
*complete*. The archive carries the directory, so it can.

`raw_url()` still emits the exact §9 URL for every column, so every claim stays
hand-checkable and citable in the conformance report.

**Status: pending Nakita's confirmation** — it modifies a documented method.

### D11 — severity is read off the spec text, never assigned by hand

Each check cites a requirement sentence and inherits that sentence's RFC 2119
severity. At v1.2 the corpus is 349 FAIL-level statements, 30 WARN, 30 INFO.

The alternative — a human deciding which checks are failures — is how a harness
drifts from the spec while still looking rigorous. This makes the two-tier
structure (F2 refined) *structural from the start* rather than a retrofit, which
is what the Stage 4 brief asked for.

Corollary: a check citing one MUST and one SHOULD is a FAIL check. If a rule needs
to report at both levels it becomes two checks. No averaging.

### D12 — the era gate has two modes, defaulting to the strict one

Per F27. `ERA_REQUIREMENT` is the default so that forgetting to think about mode
produces the loud failure (a rule misapplied to an old row) rather than the quiet
one (a populated column never examined).

### D13 — a check cannot register without a spec citation

`register()` raises on an empty `refs` list. One line. It makes "every rule traces
to the specification" a property of the code rather than a claim in the README.

---

## 6. Build plan — the chunk sequence

| # | Chunk | Deliverable | Status |
|---|---|---|---|
| 1 | Spec source layer | `spec_source.py`, `docs/spec/*.json` | **complete** |
| 2 | Harness skeleton | `validate.py` — registry, severities, era gate, binding | **complete** |
| 3 | Structural checks | presence vs nullability, cascades, parent map | next |
| 4 | Metric validations | price × quantity, cost relationships, F10/F24 scoping | |
| 5 | Cross-column | commitment, capacity reservation, correction period rule | |
| 6 | Layer C / §2.14 | three-way reconciliation, contiguity, eligibility | |
| 7 | SHOULD tier | empty-string sweep (per-layer only), placeholders, KPIs | blocked on F26 |
| 8 | Negative proof | 14/14 + `conformance-report.md` | |
| 9 | Version-diff script | build spec §9 / Amendment A5.2 step 1 | |
| 10 | Official Validator | comparison table | |

---

## 7. Build log

### Chunk 1 — the specification source layer · 15 August 2026 · **runs clean, exit 0**

`spec_source.py`, standard library only — no new `requirements.txt` entries.

Fetches five tags (v1.0–v1.4), caches them under `spec_cache/`, parses every
column file, and writes:

- `docs/spec/spec_v1.2.json` — 57 columns with normative statements, severity,
  feature level, nullability, allowed values, parent/child rows, §9 raw URL
- `docs/spec/lifecycle.json` — `INTRODUCED` (67 columns across all tags) and
  `REMOVED`

Results: 57 columns at v1.2, exhaustive. Column counts per tag: 43 / 50 / 57 / 65
/ 65. `REMOVED` computed as `ProviderName` and `PublisherName` at v1.4, with
`ServiceProviderName` derived as the stated successor. Severity corpus: 349 / 30 /
30. Feature level: 21 Mandatory, 32 Conditional, 4 Recommended.

Findings raised: **F23**, **F25**. Corrections: F22 layout date, F22 successors,
F12 bounded. Open items closed: exhaustive column list, both hand-built map
cross-checks.

Two parser traps worth carrying: heading casing is inconsistent (30 files say
"Content Constraints", 25 say "Content constraints"), and two v1.2 files are CRLF
— skip the carriage-return strip and `chargeclass.md` and `subaccountname.md`
silently parse as having no Introduced version. Both are handled; both would have
been invisible.

One field needed structured parsing rather than a raw read:
`serviceprovidername.md` puts narrative in its Introduced field
(`"1.3 Introduced as a replacement for ProviderName"`). Taken whole it invents a
version key. Split into a token plus a note, it becomes the succession map.

Verified end to end from an empty state: `rm -rf spec_cache docs/spec` then a
clean run, exit 0. Second run reads from cache.

### Chunk 2 — the harness skeleton · 15 August 2026 · **runs clean, 10 checks, 2/14**

`validate.py`. Three run modes: default (clean data), `--negative` (the proving
set), `--list` (checks and horizons).

Registered: `META-declaration-drift` plus nine allowed-values checks, all nine
built from `spec_v1.2.json` with **no constant typed by hand**. Stage 3's
hardcoded `ALLOWED` dict was correct — chunk 1 confirmed it — but correct and
sourced are different properties, and only one survives a spec revision
unattended.

Against `focus_unified`: 0 FAIL, 0 WARN, 2 INFO (both F27 drift).
Against `data/negative/`: **2 of 14 caught** — `INVALID_ENUM_VALUE` and
`INVALID_CHARGECLASS_VALUE`.

**2/14 is the honest number for a skeleton with one check family**, and it is
recorded here precisely because it is low. A harness reporting 14/14 at this point
would be lying, and this number is what makes chunks 3–7 measurable.

The negative fixtures annotate themselves — every row carries
`x_ExpectedViolation` — so the count is computed from the data, never tallied by
hand. That was a good Stage 3 decision and it pays off here.

Findings raised: **F26**, **F27**. Decisions: **D11**, **D12**, **D13**.

Design difference from Stage 3 worth naming: in `self_test.py` a whole folder was
one era, so the era gate sat at the top of the run. `focus_unified` holds three
eras in one table, so **the gate moves from the folder to the row**. Every scope
decision moved down a level with it.

---

## 8. Open items

- [ ] **F26 — resolve where the real-layer empty-string sweep points.** Blocks
      chunk 7. Requires editing `build_unified.py`, a signed-off Stage 3
      deliverable. Nakita's call.
- [ ] Confirm **D10** (tag archive as spec transport) — it modifies build spec §9.
- [ ] Layer C column counts: the CSVs are 6 / 18 / 27 (billing_period /
      invoice_detail / contract_commitment); v1.4 specifies 6 / 22 / 30. Billing
      period matches exactly. Account for the 4 and 3 missing in chunk 6 — likely
      Conditional columns, but *likely* is not verified.
- [ ] Add `spec_cache/` to `.gitignore`.
- [ ] Carry **F24** into the F10 community issue — write it as "this file needs a
      scoping clause", covering both invariants.
- [ ] Chunk 3 must source `ServiceCategory`/`ServiceSubcategory` pairs from
      `allowed_value_rows` rather than the hand-built map, closing the last
      hardcoded constant in the value layer.

---

## 9. Chunk 2a — the F26 amendment · 15 August 2026 · **approved and applied**

`build_unified.py` now writes the per-layer sanitised view it had only declared.

**What changed.** A new `write_sanitised_layer()` function, called from the main
run, writing `data/raw-sanitised/<pull folder>/` with a Parquet file and an
Azure-shaped `manifest.json` beside it — the same shape `seed_data.py` writes for
the synthetic layers, so `loader.py` reads it unchanged. One subfolder per export
pull, mirroring `data/raw/`, because a second pull is a second export of the same
layer and flattening them would merge two months into one view and lose which
rows came from where.

**Scope correction on the estimate.** This was described as "four lines". The
logic is about ten; with the manifest and the reasoning comments it is closer to
fifty. Recorded because an estimate given and then quietly exceeded is how scope
creep enters a signed-off deliverable unnoticed.

**The safety property.** The write sits on the clean branch of the existing
residual-identifier check, which runs against the OUTPUT rows independently of
the sanitising rules. A surviving identifier therefore means **nothing is
written at all**, rather than something unpublishable being written and caught
later. Decision D6's publication gate, applied to a file instead of a repository.

**The property the folder exists for is now counted, not assumed.** The function
counts empty strings in what it wrote and prints the number. Azure's real export
holds ~1,406 of them (F2 refined — a SHOULD NOT, so a warning); they must survive
into this file or the chunk 7 sweep runs against a clean copy and reports a pass
on a defect that is really there. `sanitise_value()` returns early on empty
strings so preservation is *expected*, but expected is not verified — and
unverified expectation is precisely what produced F26.

**Testing limit, stated plainly.** The new path was exercised here against a
stand-in export built from the 1.0r2 rows of `focus_unified`. That proves the
mechanics — read, verify, gate, write, manifest, discover — and it proved the
gate by refusing to write on a first attempt where the fixture tripped the
residual check. It does **not** prove empty-string preservation, because those
rows had already been through D3. **Only the real `data/raw/` can prove that, and
the number to look for on Nakita's run is 1,406.** If it prints 0, something
upstream normalised the data before it reached the writer and chunk 7 is still
blocked.

**Consequential change to `validate.py`.** Discovery now finds parquets in a
folder *or* in its immediate subfolders, and names each one `real:<pull folder>`.
Layers with one file are unaffected.

**F26 status: resolved pending confirmation on real data.**

---

## 10. Chunk 3 — structural checks · 15 August 2026 · **80 checks, 7/14, one real defect found**

New file `rules.py`: the specification's requirement sentences, parsed into
executable conditions. `validate.py` registers what it produces.

### The decision: parse, do not transcribe

There are 85 nullability statements at v1.2. Hand-writing 85 assertions is a
morning's work and yields a harness that is correct on the morning it is written.
Each assertion is then a place a transcription error can hide, and a transcribed
rule looks exactly like an invented one. The keepsake's near-miss on assertion
2.4.4 — the truncated sentence that dropped `AND ChargeCategory is "Usage"` —
is that failure, and it survived review for that reason.

So the sentences are parsed, and **what cannot be parsed is reported, never
dropped**. A parser that silently skips what it does not understand is worse
than a hand list, because the gap becomes invisible.

| Class | Count |
|---|---:|
| Implemented | 68 |
| Not machine-checkable — condition the row does not carry | 15 |
| Not machine-checkable — semantic conjunct (pruning rule) | 2 |
| **Total nullability statements at v1.2** | **85** |

**The 17 refusals are the valuable number.** They are conditions like *"when a
charge is related to a resource"* — true or false in the world, unknowable from
the row. They are not gaps in this harness; they are gaps in what any harness
can do. Naming them with reasons is worth more than a coverage percentage, and
it is a claim the official Validator cannot make at all, since it does not
evaluate conditional requirements in the first place.

### The pruning rule — narrowing is safe, broadening is not

Some conditions mix a checkable term with a semantic one. They are not equally
usable, and the difference is a matter of logic rather than taste:

- `MUST be null when (ResourceId is null OR the resource has no display name)` —
  either branch alone is sufficient. Dropping the semantic branch **narrows when
  the rule fires**. It never fires wrongly. Implemented.
- `MUST NOT be null when (ResourceId is not null AND the resource has a display
  name)` — both must hold. Dropping the semantic conjunct **broadens** the rule
  into demanding a name for every identified resource. A conformant nameless
  resource would fail. Refused.

**You may narrow when a rule applies. You may never broaden it.** That is finding
F10's lesson stated as a general rule.

**Applied blind to the spec text, it reproduced Amendment 1 A7.2 exactly** —
assertion 1 implemented, assertion 3 refused, for the stated reason. A correction
derived by hand in July, arrived at independently by the parser in August. That
is the strongest available evidence that the parser is reading the specification
the way a careful human does.

### F28 — a MUST whose scope is stated in a line the parser threw away

**Found by running it: 47 failures on known-good data.**

`CommitmentDiscountQuantity MUST NOT be null when ChargeClass is not "Correction"`
read flat demands a commitment quantity on every non-correction row in the
dataset. In the source it is nested:

```
* CommitmentDiscountQuantity nullability is defined as follows:
  * When ChargeCategory is "Usage" or "Purchase" and CommitmentDiscountId is not
    null, ... adheres to the following additional requirements:
      * CommitmentDiscountQuantity MUST NOT be null when ChargeClass is not "Correction".
  * CommitmentDiscountQuantity MUST be null in all other cases.
```

The scope is in the parent bullet. Chunk 1 kept only bullets carrying an ALL-CAPS
keyword — and the parent has none, because it states scope rather than a
requirement. So the rule lost its context and failed 47 conformant rows.

**This is F10 arriving from the opposite direction.** F10 is a MUST whose scope
the spec never states. F28 is a MUST whose scope the spec states clearly, in a
line the reader discards. Both produce the same output: a confident, wrong
failure. **Scope is the hard part of turning a MUST into an assertion, whether or
not the specification hands it to you.**

Chunk 1 amended: all 77 non-normative bullets are now retained with
`severity: None` and their indentation, so `rules.py` can rebuild the ancestor
chain and conjoin the scope back on. The 349/30/30 normative counts are
unchanged.

**A second gain, unlooked for.** `MUST be null in all other cases` was refused in
the first pass as not independently parseable. With the nesting restored it
becomes precise — "all other cases" is the negation of its sibling's scope — and
implementable. Refusals fell from 18 to 17.

### F29 — a real conformance defect in our own seed data

After scope inheritance, one failure survived on `focus_unified`, and it is
genuine. Row 175, fixture `charge_family`:

| Column | Value |
|---|---|
| ChargeDescription | Rebate: July 2026 bandwidth metering adjustment |
| ChargeCategory | Usage |
| ChargeClass | *null* |
| SkuId | DZH318Z0BNZ4 |
| **SkuPriceId** | ***null*** |

`SkuPriceId MUST NOT be null when ChargeCategory is "Usage" or "Purchase" and
ChargeClass is not "Correction"`. The row is also internally inconsistent: SkuId
is set and SkuPriceId is not.

Its four siblings all escape correctly — Adjustment, Credit and Tax are outside
the Usage/Purchase scope, and the correction row carries ChargeClass
"Correction". Exactly one row is wrong.

**Fifteen hand-written self-tests passed this row.** The parsed harness caught it
on its first substantive run, because it implements a conditional rule nobody
thought to write by hand. That is the argument for chunk 3's whole approach,
delivered by chunk 3 itself.

Recommended remedy: populate `SkuPriceId` (and `SkuMeter`) on that row in
`seed_data.py`. Not recategorising it — a negative-cost Usage row is a valuable
fixture for the never-reason-from-sign rule and should stay. **Nakita's call:
it edits a Stage 3 deliverable.**

### F30 — the proving run was measuring the wrong thing, and it said 14/14

The first chunk 3 run reported **14 of 14 planted violations caught.** It was
false.

`report_negative()` counted a planted violation as caught if *any* violation
landed on that row. The negative file leaves `PricingCurrencyContractedUnitPrice`
and `PricingCurrencyListUnitPrice` null on every row, breaching a conditional
rule, so every row trips those two checks. The harness was credited with
detecting `CHARGE_PERIOD_INVERTED` when what it had noticed was an unrelated null
three columns away.

**A green result that was confidently wrong — the exact failure mode this project
exists to avoid, occurring inside the instrument that measures it.** It was
visible only because the report prints which check fired, and the same two names
appeared on all fourteen rows.

Fixed: `NEGATIVE_EXPECTATIONS` maps each planted violation to the check that must
catch it. Anything else on the row is counted separately as incidental. Entries
not yet expected name the chunk that will deliver them, so the gap stays legible.

**Honest count after chunk 3: 7 of 14, 7 pending, 32 incidental hits.**

### F31 — the negative fixture file breaches more rules than it documents

The 32 incidental hits are real violations, not false positives — the file is
non-conformant in ways beyond the 14 deliberately planted, principally the two
`PricingCurrency*` columns being null throughout.

Not a defect in the fixture's purpose: it is *supposed* to be broken. But an
undocumented breach is indistinguishable from a planted one to any measurement
that does not name the rule, which is precisely how F30 happened. Decide before
chunk 8 whether to document these as additional expected violations or populate
the columns so the file breaks only where intended.

### Checks registered after chunk 3: 80

1 declaration drift · 9 allowed values · 1 presence · 1 service parent map ·
1 ResourceName-duplicates-ResourceId (WARN) · 67 nullability

`focus_unified`: 1 FAIL (F29, real), 0 WARN, 2 INFO.

---

## 11. F32 — a SHOULD NOT breach manufacturing 354 phantom MUST breaches

**Found on Nakita's run, not in development.** The sandbox has no real Azure
layer, so this could only appear against `data/raw-sanitised/`. Chunk 2a is what
made it visible: before the per-layer view existed, these rows were only ever
seen through `focus_unified`, where D3 had already normalised the problem away.

### What happened

`real:31 July 2026` reported **354 MUST violations**, all from three checks:

| Check | Rows |
|---|---:|
| `NULL-CommitmentDiscountCategory-notnull` | 118 |
| `NULL-CommitmentDiscountStatus-notnull` | 118 |
| `NULL-CommitmentDiscountType-notnull` | 118 |

118 × 3 = 354. Exact.

### Why

`CommitmentDiscountId` holds `''` on all 118 real rows — one of the 13 columns in
the empty-string report. **`''` is not null.** So `CommitmentDiscountId is not
null` evaluates true on every row, and three cascade rules demand a commitment
category, status and type on rows that have no commitment discount at all.

Not one of the 354 is real. Every one names a rule that is not the rule that is
broken.

### Why it matters beyond this project

F2 refined established that Azure's empty strings breach a **SHOULD NOT**, not a
MUST — a recommendation, so a warning. That is correct, and on its own it makes
the defect sound cosmetic.

**It is not cosmetic. It manufactured 354 phantom MUST failures three columns
away.** The damage from a placeholder is not to the column that holds it; it is
to every rule downstream that reasons about nullness. That is a far stronger
argument for fixing empty strings than tidiness, and it is quantified on real
provider data.

It is also the third appearance of the same underlying pattern:

| Finding | Failure |
|---|---|
| F10 | a MUST whose scope the spec never states → fails good data |
| F28 | a MUST whose scope the spec states in a discarded line → fails good data |
| F30 | a proof that credits the row rather than the rule → passes bad data |
| **F32** | **a defect that fires rules it did not break → misattributes real data** |

All four are the same class: **a confident result attributed to the wrong rule.**

### The fix — both facts preserved, neither hidden

Nullability conditions now read `''` as null, because that is what the provider
means. But the suppression is **counted and printed**, per check:

```
EMPTY-STRING SUPPRESSION (finding F32): 354 findings
  NULL-CommitmentDiscountCategory-notnull14    118
  NULL-CommitmentDiscountStatus-notnull19      118
  NULL-CommitmentDiscountType-notnull21        118
```

Silently suppressing them would be the F30 mistake in reverse — a clean report
concealing something real. The placeholder itself remains a SHOULD NOT and is
reported by the empty-string sweep in chunk 7, which is bound to exactly this
per-layer view.

Both readings are evaluated on every row: strict (only `None` is null) and
lenient (`''` too). A row that fires strict but not lenient is a
placeholder-caused finding, and that difference is the number reported.

### Result after the fix

`real:31 July 2026`: **0 FAIL, 0 WARN, 2 INFO, 354 suppressed and itemised.**
`focus_unified` and the negative count are unchanged: 1 FAIL (F29), 7 of 14.

### Note for the case study

This is the strongest single passage of evidence the project has produced so far.
A real provider export, a recommendation-level defect, and a measured
consequence: 1,406 placeholders in 13 columns causing 354 false conformance
failures in a harness that reads the specification correctly. The three-line
version — **the empty strings are not the problem; what they do to every rule
that reasons about nullness is the problem** — belongs in the write-up.

---

## 12. F29 and F31 resolved · 15 August 2026 · **all clean layers 0 FAIL, 0 incidental**

Both edits are in `seed_data.py`. Verified by running the full chain end to end:
`seed_data.py` → `self_test.py` → `build_unified.py` → `validate.py`.

### F29 — the rebate row

`SkuPriceId="DZH318Z0BNZ4/00CV"` added to the `charge_family` rebate row, matching
the `SkuId/00CV` pattern the rest of the v1.2 layer uses. `SkuMeter` added at the
same time.

**Correction to the earlier note:** only `SkuPriceId` was actually required.
`SkuMeter SHOULD NOT be null when SkuId is not null` is a **SHOULD**, so a
warning, and `SkuPriceDetails MAY be null when SkuPriceId is not null` means
populating `SkuPriceId` forces nothing further. `SkuMeter` was set anyway, because
a known SHOULD deviation sitting in the CLEAN layer gives the WARN tier a
permanent non-zero floor, and a floor is where a real regression hides.

**Not** recategorised as Adjustment: a negative-cost `Usage` row is the fixture
that proves never-reason-from-sign, and row 0 already covers Adjustment.

### F31 — the negative fixture's undocumented breaches

Measured before deciding. The 32 incidental hits were three separate problems
wanting three different answers:

| Group | Hits | Cause | Resolution |
|---|---:|---|---|
| 1 | 24 | `PricingCurrencyContractedUnitPrice` and `PricingCurrencyListUnitPrice` absent from the baseline, so null on every row | populated in `valid()` |
| 2 | 6 | the Tax row broke **seven** rules, not one | reduced to one fault |
| 3 | 2 | `ConsumedQuantity` populated on a non-Usage row, twice | nulled on both |

**Recommendation reversed on group 2, and worth recording why.** The initial
advice was to document the Tax row as a seven-rule test rather than fix it — it
tests more that way. Reading the fixture's own module docstring settled it:

> Each row is otherwise entirely valid. One fault per row, isolated, so a failure
> points at one rule rather than a fog of them.

The row was a Tax row built from a Usage template, and it broke the file's stated
contract. **A fixture's design principle outranks an opportunistic gain in
coverage**, because the principle is what makes every row diagnostic. If the other
six Tax nulling rules deserve testing, they deserve their own rows.

Nulling the anchors meant nulling their dependents too — `PricingUnit` follows
`PricingQuantity`, `ConsumedUnit` follows `ConsumedQuantity`, `SkuMeter` follows
`SkuId` — or the edit would simply have planted a different fault in place of the
old one.

**Group 3 row 2 is finding F32 in miniature.** `ChargeCategory="Consumption"` is
an invalid enum, and `ConsumedQuantity MUST be null when ChargeCategory is not
"Usage"` — so the planted defect *cascaded* into a second violation naming a rule
that was not the one broken. The same shape as the empty strings firing three
commitment cascades: **one defect firing rules it did not break.** Row 6's
`ConsumedQuantity` was a genuinely separate second fault, not a cascade.

### Result

| Target | FAIL | WARN | INFO |
|---|---:|---:|---:|
| `real:31 July 2026` | 0 | 0 | 2 (+354 suppressed, F32) |
| `synthetic-v1.2` | 0 | 0 | 0 |
| `synthetic-legacy` | 0 | 0 | 1 |
| `unified` | 0 | 0 | 2 |

Negative proof: **7 of 14 caught, 7 pending, 0 incidental.**

Stage 3's `self_test.py` still passes 14/14 — the edits did not disturb it.

**Zero incidental is now a usable regression signal.** Any future non-zero means
either a fixture regression or a check firing somewhere unexpected. Left at 32 it
would have been a number nobody read, which is how F30 happened.

### Gap noted while resolving F29 — the WARN tier is nearly empty

The nullability parser only takes MUST-level statements, so "85 nullability
statements" means 85 **MUST-level** ones. Three SHOULD-level nullability rules
exist at v1.2 and none are implemented:

- `ChargeDescription SHOULD NOT be null` — implementable
- `SkuMeter SHOULD NOT be null when SkuId is not null` — implementable
- `CapacityReservationId SHOULD NOT be null when a charge is related to a
  capacity reservation` — semantic, would be refused anyway

Added to chunk 7's scope. **Today's `0 WARN` on every target partly reflects
checks not yet written rather than clean data**, and the report must not be read
as though it meant otherwise until chunk 7 lands.

---

## 13. D14 — a module handshake between `validate.py` and `rules.py`

**Prompted by a real failure on Nakita's machine.** `AttributeError: module 'rules'
has no attribute 'is_null'`, raised 550 lines into a run, after the harness had
already printed its header, its dataset discovery and a target banner.

Cause: `rules.is_null` was added by the F32 patch, `rules.py` was not among the
files listed for replacement in the following message, and the two drifted out of
step. A handover error, not a code defect.

**Why it is worth a decision rather than an apology.** The two files are a matched
pair, edited together and shipped separately, so they *will* drift again. And the
symptom of drift is the worst kind: a Python-level error deep inside a check,
which reads like a bug in the harness. Someone debugging it starts by suspecting
the logic, not the file copy. The run looks partly successful right up to the
traceback, which makes it worse.

`rules.py` now carries `RULES_VERSION`, and `validate.py` checks it at import:

```
rules.py is out of date: this validate.py needs RULES_VERSION >= 2, found 1.
Replace rules.py with the version shipped alongside this file.
If you have already replaced it, delete __pycache__/ and re-run — a stale
.pyc can shadow the new source.
```

Fails at startup, in words, naming the file and the remedy — including the stale
bytecode case, which produces the identical symptom after the correct file has
been copied and is more confusing still.

**The general principle, and it is the same one the harness applies to data:**
an error should name the thing that is actually wrong. F30 credited the wrong
rule, F32 blamed the wrong column, and this blamed the wrong file. A harness that
insists on correct attribution in its findings should hold itself to it in its
own failures.

---

## 14. Chunk 4 — metric validations · 89 checks, 9/14, 0 incidental

Three families, all derived from spec sentences rather than transcribed:
non-negativity, price × quantity, and the two commitment aggregates.

New expectations mapped: `NEGATIVE_UNIT_PRICE` → `METRIC-nonneg-ListUnitPrice`,
`UNIT_PRICE_COST_MISMATCH` → `METRIC-product-ContractedCost`. **9 of 14 caught,
5 pending, 0 incidental.** Stage 3's `self_test.py` still passes 14/14.

### D15 — the tolerance is a harness policy and is declared as one

`numeric_format.md` says it outright: *the specification does not require a
specific level of precision for numeric values*, and precision is for the
provider to define and publish.

So the epsilon in a price × quantity check is **our judgement, not a
requirement**. `TOLERANCE = Decimal("0.000001")`, inherited from Stage 3's
`self_test.py` so the two agree, and stated in the module header rather than
buried at a call site. A harness that silently picks an epsilon is asserting a
rule the specification does not contain — which is the same failure as inventing
a MUST, just quieter.

### F34 — F10 and F24 are adjacent sentences with different evaluability

Both invariants read global and are commitment-scoped. Scoping is necessary for
both. **It is sufficient for only one of them**, and that only became visible
once the checks were run against data.

**F24 — the Used/Unused split — is a PARTITION IDENTITY.** Once scoped to a
commitment, every Usage row must carry a status of Used or Unused, so the parts
must sum to the whole *regardless of how much of the term the dataset covers*. A
one-day slice of a three-year reservation satisfies it exactly. It stays a
**FAIL**, and it fires nowhere in our data — which is the correct result and
confirms the identity holds.

**F10 — closure against the purchase — additionally presupposes that the dataset
spans the commitment's entire term.** Our own data contains the counterexample: a
three-year reservation purchased on 31 July, in a July export. 2,628.00
purchased against 2.40 consumed. Nothing is non-conformant; the export is one
month long.

Whether a dataset covers a commitment's term **cannot be established from the
rows** — the term is not in the data. So this is a MUST whose precondition is
unknowable, and it is reported as a **WARN** with the delta, on the same
principle as the ResourceName duplicate rule (A7.2.4). Downgrading a MUST is
normally exactly what this harness refuses to do; it is defensible only because
the alternative is asserting a rule whose precondition cannot be evaluated, and
because the downgrade is printed rather than hidden.

**For the community issue:** `effectivecost.md` does not need one scoping clause.
It needs two different ones, and the second invariant needs a statement about
term coverage that the first does not. That is a more precise and more useful
issue than "this line is wrong."

### F33 — commitment closure is broken by identifier reuse

`focus_unified` shows commitment `res-basv2-1yr-001` out by **exactly 0.10** at
eighteen decimal places. Not rounding.

`reservation_lifecycle` balances perfectly on its own:

| | |
|---|---|
| Purchase | 0.10 × 24 × 31 = **74.40** |
| Usage, Used, 31 rows | 61.80 |
| Usage, Unused, 21 rows | 12.60 |
| Used + Unused | **74.40** — exact |

The extra 0.10 is **one row from the `legacy_era` fixture that reuses the same
`CommitmentDiscountId`**. A commitment's closure was broken by a row from an
unrelated part of the dataset that happened to share an identifier.

**This is not a fixture curiosity — it is the production hazard.** Commitment IDs
genuinely appear across accounts, subscriptions and billing scopes, and any
commitment-level analysis that groups on the ID alone will silently absorb rows
it did not intend. The amount here is 0.10 on 74.40. At enterprise scale it is
whatever the neighbouring rows happen to be, and the total still looks plausible.

**The per-layer views make the mechanism visible in a way the merged view cannot.**
Run against `synthetic-legacy` alone, the check reports that commitment as having
0.10 of usage and **no purchase at all** — because the purchase row lives in a
different layer. Run against `focus_unified`, the two merge and the discrepancy
shrinks to 0.10. Same data, two framings, and the per-layer framing is the one
that names the cause. Further vindication of the chunk 2a decision.

**Open — Nakita's call.** Either give `legacy_era` its own `CommitmentDiscountId`
(cleanest, and preserves one-fault-per-fixture), or keep the collision
deliberately and document it as a demonstration case, since it is a genuinely
good illustration of the hazard. **Recommendation: give it its own ID and build
the collision as a named negative fixture instead**, so the demonstration is
labelled rather than accidental.

### Chunk 4 in one line for the case study

The harness now implements a conditional metric rule the reference Validator does
not express at all, declares its own tolerance as policy rather than smuggling it
in as fact, and distinguishes two adjacent invariants in the same specification
file by whether their preconditions are knowable from the data.

---

## 15. Chunk 4a — F33 resolved · legacy_era gets its own commitment identity

`legacy_era_family()` now uses `LEGACY_RESERVATION_ID`
(`res-basv2-legacy-2023`) instead of borrowing `RESERVATION_ID`. The purchase row
for it is deliberately **not** in the dataset: bought in 2023, before this export
window, which is the ordinary case for legacy data.

**Result:** `res-basv2-1yr-001` closes at **74.40 against 74.40, exact**, and
drops out of the warnings entirely. `self_test.py` still 14/14; negative proof
unchanged at 9 of 14, 0 incidental.

### The check learned to distinguish two situations that are not the same

Making the fix exposed a defect in the message. After the fix, the legacy
commitment has usage and **no purchase row at all** — a different thing from
"purchase present, amounts differ", and the old code reported both as an
imbalance.

| Situation | What it means | Message |
|---|---|---|
| No Purchase row in scope | The purchase falls outside the export window. Nothing about the numbers is in doubt. | *"closure is not evaluable — not an imbalance"* |
| Purchase present, amounts differ | Either partial term coverage, or a genuine failure to close. The rows cannot tell these apart. | *"out by X; may mean the dataset does not span the term"* |

Collapsing them reports *"out by -74.40"* for a commitment whose purchase simply
is not present — **a number that sends someone looking for a discrepancy that
does not exist.** The same misattribution failure as F30 and F32, in the
harness's own output rather than in its rule selection.

**The warning count did not fall — it stayed at two.** That is the right outcome
and worth stating plainly: the goal was never a smaller number. It was that each
remaining warning names a real and distinct thing. One is partial term coverage,
one is a purchase outside the window, and a reader can now act on either.

### Deferred to chunk 5 — the named collision fixture

The ID fix removes the accident. The **demonstration** is still worth having, but
it does not fit the negative file: that file's contract is one fault per **row**,
and a collision is inherently multi-row — the fault lives in the relationship
between a purchase and a usage row, not in either one. The expectation map also
assumes one planted violation maps to one row index, and `self_test.py` asserts
14/14, so a fifteenth entry ripples into a Stage 3 deliverable.

It wants its own fixture set (`data/negative-aggregate/` or similar) and a
decision about how aggregate faults are expressed. Designed properly in chunk 5
alongside the other aggregate work, not bolted on here.

### Also flagged for chunk 5 — a commitment term check

The collision was chronologically impossible: usage dated 14 March 2024 against a
one-year reservation purchased 1 July 2026. **A check that a commitment's usage
rows fall within its term would have caught F33 independently of the identifier**,
and it catches real-world commitment misattribution, which is worth demonstrating.

---

## 16. Chunk 5 — format and cross-column · 93 checks, 13/14, 0 incidental

Four new families: cross-column value rules, ISO 4217 currency, charge period
ordering, and `SkuPriceDetails` keys and value types. Four planted violations
newly caught. **13 of 14, 0 incidental.** `self_test.py` still 14/14.

`spec_source.py` was amended and must be re-run — see the new field below.

### Chunk 1 amended again — the `###` tables

The FOCUS-defined `SkuPriceDetails` property list sits under
`### FOCUS-Defined Properties`, a level-THREE heading. `_sections` splits on
`## ` only, so the table was buried in the Content Constraints body and no field
exposed it.

That list is not optional detail: *"Property key MUST begin with the string 'x_'
unless it is a FOCUS-defined property"* cannot be checked at all without knowing
which properties are FOCUS-defined. And the standing trap here is precisely a key
that looks defined and is not — the course taught `MemoryGB`, the specification
says `MemorySize`, and a query on the first returns nothing forever and reports
it as an absence rather than an error.

New `subsection_tables` field. **13 properties parsed at v1.2, `MemoryGB` absent
— F15 confirmed independently from the specification.**

### D16 — DERIVED checks are labelled and reported separately

`PERIOD-ordering` is the harness's first rule that does **not** quote a
specification sentence.

Searching v1.2 for any statement ordering `ChargePeriodStart` and
`ChargePeriodEnd` returns nothing. Searching **v1.4 returns nothing either.**
Three releases on, the specification still nowhere requires a charge period's end
to follow its start.

What it does say is that one is the *inclusive start bound* and the other the
*exclusive end bound* of "the effective period of the charge". A period whose
exclusive end precedes its inclusive start contains no time, so it cannot be the
effective period of anything. The conclusion holds — but it follows from two
sentences read together, not from a sentence.

An inverted period is obviously wrong and a validator that misses it is not worth
running, so the check is implemented. But `SpecRef` now carries `derived=True`,
and the run reports the split: **92 checks cite a specification sentence, 1 is
derived.** Because this harness's entire claim is that its rules trace to the
specification, and **a derived rule filed quietly among quoted ones devalues
every quoted one beside it.**

**Third candidate community issue**, and the cleanest of them: no explicit
ordering requirement between `ChargePeriodStart` and `ChargePeriodEnd` at any
version through v1.4. The kind of gap everyone assumes is covered precisely
because it is too obvious to write down.

### F35 — the ISO 4217 check applies to BillingCurrency and NOT to PricingCurrency

`CurrencyFormat` makes the rule conditional: three-letter alphabetic **when the
value is presented in national currency**, `StringHandling` when it is virtual
currency (credits, tokens). The row does not say which it is.

For `BillingCurrency` the condition is settled by the column's own rule —
*BillingCurrency MUST be expressed in national currency* — so ISO applies
unconditionally and a bad code is a hard failure.

**`PricingCurrency` carries no such statement.** A provider pricing in credits or
tokens is conformant, and nothing in the row distinguishes that from a malformed
code. Asserting ISO on `PricingCurrency` would broaden a conditional rule into an
unconditional one — chunk 3's pruning rule in a different guise — and it would
fail conformant data.

A naive validator applies one currency check to every currency column. The
negative fixture sets **both** columns to `"US Dollars"`, so a naive
implementation would have looked correct here and been wrong in general.

The check is also on the **shape** (three uppercase letters), not membership of
the ISO code list. Currencies are added and withdrawn; a harness carrying a stale
copy of the list would reject valid data. Shape catches `"US Dollars"`, `"usd"`
and `"US$"` — the errors that actually occur — without asserting a list this
project has no authority to maintain.

### F36 — generated checks can implement the same sentence twice

Chunk 5's value-condition parser matched `ChargeClass MUST be "Correction" when
ChargeClass is not null` — a sentence the allowed-values fallback was **already**
using, because `ChargeClass` states its constraint that way rather than as "one
of the allowed values". One defect, reported under two names, inflating counts
and splitting attribution.

**This is F30 again, arriving from the registry instead of the report.** When
checks are generated by matching sentence patterns rather than written by hand,
two patterns matching one sentence is a structural hazard, not an accident.

`register()` now rejects any check citing a requirement sentence already cited.
The fallback was removed rather than the new check, since `XCOL` implements the
sentence as written, including its condition, where the fallback only
approximated it.

**The guard found a second collision on its first run** — one I had not noticed:
`SVC-parent-map` and `AV-ServiceSubcategory` both cited *ServiceSubcategory MUST
be one of the allowed values*. And that pair was more interesting, because they
were **not duplicates**: one tested membership of a flat name list, the other the
(Category, Subcategory) pairing. Since the allowed values ARE pairs (F25), "one
of the allowed values" means a valid pair — so the parent-map check states the
sentence completely and the flat check only partially.

Merged into one, with a fallback: when `ServiceCategory` is null or unrecognised
the pair cannot be evaluated, so the subcategory NAME is checked instead.
**Without that fallback, nulling `ServiceCategory` would switch off subcategory
validation entirely, and a dataset could be made to pass by deleting a value.**

### Still open, carried to chunk 6/7

- `EMPTY_STRING_PLACEHOLDER` — the last planted violation, due with the chunk 7
  SHOULD tier and the per-layer empty-string sweep.
- The named multi-row collision fixture (deferred from chunk 4a) — needs its own
  fixture set and a decision on how aggregate faults are expressed.
- A commitment term check — would have caught F33 independently of the
  identifier. Note that it would be **DERIVED**, like `PERIOD-ordering`: no
  specification sentence requires usage to fall within its commitment's term.

---

## 17. Chunk 6a — Layer C loaded and structurally validated · 96 checks

Seven targets now: four cost_and_usage plus the three supplemental datasets.
`spec_source.py` amended again and must be re-run.

**Result: 1 MUST failure, and it is real.** Negative proof unchanged at 13 of 14.

### One project, two specification versions

The supplemental datasets **do not exist before v1.3**. There is no earlier
version to target. So Layer C is validated at **v1.4** while cost_and_usage is
validated at **v1.2** — one repository, two datasets, two versions of one
specification, each checked against the version it actually belongs to.

That is the version-lag thesis stated as a fact about our own artifact rather
than as an observation about providers, and it is the strongest form of the
argument: **the gap is not a provider failing, it is a structural property of a
specification that ships datasets at different maturities.**

### The generators were reused, not rewritten

Layer C's presence, allowed-values and nullability checks are the **same
generator functions** used on cost_and_usage, pointed at a different spec index
and tagged with a different dataset.

**A whole new dataset cost a spec index and a dataset tag — not a new body of
hand-written assertions.** That is the return on chunk 3's decision to parse the
specification rather than transcribe it, and it only became visible when a second
dataset arrived.

`Check` and `Target` now carry a `dataset`, and a check is never handed a table
it was not written for. Not fussiness: `BillingCurrency` and `InvoiceIssuerName`
exist in three of the four datasets with different rules, so without the scope a
cost_and_usage rule would run against an invoice and produce a confident,
meaningless result.

### D17 — in a CSV, an empty field is read as NULL

CSV has no null. An absent value and an empty string are the same nothing.

**That is the exact opposite of the parquet layers**, where `''` and NULL are
genuinely different and conflating them is finding F32. Both readings are correct
for their format. Recorded here rather than left for someone to discover from an
inconsistent result between two targets in the same run.

### F37 — contract_commitment is missing a Mandatory column, and it is the F22 column

Measured against v1.4, not assumed:

| Dataset | CSV | Spec | Mandatory present | Verdict |
|---|---:|---:|---|---|
| billing_period | 6 | 6 | 6/6 | complete |
| invoice_detail | 18 | 22 | 18/18 | complete — the 4 absent are all Conditional |
| contract_commitment | 27 | 30 | **26/27** | **`ServiceProviderName` missing** |

**The generator's rule was evidently "build every Mandatory column", and it got
two of three datasets exactly right.** The Conditional absences are not defects:
`PaymentCurrency*` applies only where payment and billing currency differ,
`PurchaseOrderNumber` only where the provider supports POs. The harness reports
them as INFO for that reason.

The one real miss is `ServiceProviderName` — **the v1.3 replacement for
`ProviderName`, which is finding F22.** The generator was almost certainly
working from a v1.2 mental model, where the provider column is called
`ProviderName`; that name does not exist in a dataset that starts at v1.3, and
the successor was not on its list.

**F22 predicted this class of error and it happened anyway, in our own code, one
stage later.** Knowing that a column was renamed is not the same as having a
process that catches its absence — which is the argument for a harness over a
finding.

**Open — Nakita's call.** `generate_layer_c.py` needs `ServiceProviderName` added
to the contract_commitment column set. I do not have that script (only its
output), so I cannot write or test the patch. Value: `Microsoft`, matching
`InvoiceIssuerName` in the same rows.

### Also fixed in chunk 1 — allowed values moved at v1.3

Up to v1.2 the allowed-values table sits inside the Content Constraints body.
From v1.3 the supplemental datasets give it its own `## Allowed Values` heading.
Reading only the first location returns an **empty** list for every v1.4 dataset
column — and an empty allowed list reads as *unconstrained*, so every value would
have passed.

Same shape as F25: a structure consistent until it isn't, failing silently
instead of loudly. Third time this class of trap has appeared in the spec parser.

### Chunk 6b — still to come

- Invoice reconciliation: `sum(BilledCost)` per `InvoiceId` in cost_and_usage
  against `invoice_detail.BilledCost`. A spec MUST.
- **The F10 upgrade.** `contract_commitment` carries `ContractCommitmentPeriodStart`
  and `ContractCommitmentPeriodEnd` — **the commitment term**, which chunk 4 had
  to treat as unknowable. With Layer C present it is knowable, so the closure
  invariant moves from WARN to a decidable check. That is a substantial result:
  the invariant is unverifiable from cost_and_usage alone and verifiable with the
  supplemental dataset, which is an argument for the multi-dataset specification
  rather than merely a note about ours.
- Billing period overlap and status rules.

---

## 18. F37 revised, and F38 raised — after reading `generate_layer_c.py`

The generator arrived after chunk 6a was written. It changes F37's explanation
materially, and it surfaces a second finding that reshapes chunk 6b.

### F37 revised — the knowledge was in the file; the column was not

Chunk 6a guessed that the generator "was working from a v1.2 mental model." That
guess was **wrong**, and the truth is more useful.

`generate_layer_c.py` documents the rename itself, at length, in a prominent
closing block: F22, ProviderName and PublisherName removed at v1.4, successors
named — **`ServiceProviderName` among them.** The author knew. The column was
still missing.

Two causes, and both generalise:

**1. One finding, two datasets, two different tenses.** The F22 note treats the
rename as a *future* risk to the cost dataset: *"Nothing to fix today: the data
is v1.2 and correctly declares itself so."* True of cost_and_usage. False of
contract_commitment — which does not exist before v1.3 and can therefore only
ever be built at v1.3+ naming, where `ServiceProviderName` is not a successor to
plan for but **the current column name**. The present-tense case went unnoticed
twenty lines above the paragraph describing it.

**2. Verified is not exhaustive.** The header states the shapes were *"VERIFIED
AT SPEC TAG v1.4"*, and they were — every column in the list was checked against
the spec. What was never checked is whether the **list** was complete.

That is precisely the distinction Stage 4 chunk 1 closed for the v1.2 cost
columns, by counting the directory instead of confirming names one at a time.
**Nobody carried the lesson across to Layer C, and a mandatory column fell
through the exact gap that lesson was written about.**

**The generalisable point, and it is the best argument the project has for
building the harness at all:** documenting a breaking change did not prevent the
defect it describes. Knowledge in a comment is not a control. A presence check
that counts against the spec is.

**Resolved.** `ServiceProviderName` added to `CONTRACT_COMMITMENT_COLUMNS` and to
both rows, value `Microsoft`, matching `InvoiceIssuerName`. Regenerated: 28
columns, **27/27 Mandatory**, all seven targets 0 FAIL.

### F38 — the invoice reconciliation identity does not join, and cannot on real data

The spec MUST is explicit:

> The sum of the BilledCost for a given InvoiceId MUST match the sum of the
> payable amount provided in the corresponding invoice with the same id.

The key is **InvoiceId**. On this project's data:

| | |
|---|---|
| InvoiceIds in `invoice_detail` | `INV-2026-06-0001` |
| InvoiceIds in `cost_and_usage` | `INV-2026-07-0001` |
| **Shared** | **none** |
| Cost rows carrying no InvoiceId | 203 of 204 |
| …of which the real Azure layer | **118 of 118** |

**The two datasets cannot be joined on the key the rule names.**

*In the synthetic layer* this is a fixture defect with a clear cause. The
generator grounds the invoice on a TIME WINDOW — `ChargePeriodStart` within June
2026 — not on InvoiceId. Its docstring claims *"the invoice genuinely ties to the
cost data"*, and it does tie: by period, not by the key the reconciliation
identity uses. **A tie-out that holds on a different key than the rule specifies
is not the tie-out the rule requires**, and only pointing a check at it revealed
the difference.

*In the real layer this is not fixable at all.* Azure populates `InvoiceId` on
**none** of the 118 rows — it was one of the thirteen empty-string columns from
finding F32. So the specification's invoice reconciliation MUST is
**structurally unevaluable against a real Azure export**, and the reason is the
same empty-string defect that manufactured 354 phantom failures in chunk 3.

That is a substantial result, and it connects three findings into one story:
**F32 (empty strings) → no usable InvoiceId → F38 (the invoice tie-out cannot be
performed).** The recommendation-level defect does not merely cause noise; it
disables a mandatory reconciliation. It is also the concrete mechanism behind the
well-known industry observation that provider invoices and cost exports rarely
agree exactly.

**Open — Nakita's call, before chunk 6b:**

| Option | Effect |
|---|---|
| Populate `InvoiceId` on the June rows in `seed_data.py` | The identity becomes evaluable on the synthetic layer and the check has something to prove itself against |
| Re-point the invoice at `INV-2026-07-0001` | Smaller edit, but the July period is Open and not yet invoiced — less realistic |
| Leave it and report | The check registers, finds no shared key, and reports "not evaluable" with the reason |

**Recommendation: the first.** A correction row reaching back into a closed
period is exactly the case where `InvoiceId` and `ReferenceInvoiceId` earn their
keep, and `invoice_detail` already carries both. It also gives chunk 6b's
reconciliation check a positive case to pass, not only a gap to report — and the
real layer will still, correctly, report the identity as unevaluable.

---

## 19. Chunk 6b — cross-dataset rules · **finding F10 reversed**

Three checks spanning cost_and_usage and Layer C, in a new `CROSS_REGISTRY` that
runs after the per-target loop with every dataset in hand. Per-target results and
the negative proof are unchanged: 13 of 14, 0 incidental, exit 0.

### F10 asserted, not warned — the headline

Chunk 4 downgraded the closure invariant to a warning because it carries an
unstated precondition — the dataset must span the commitment's whole term — and
**the term is not in the cost dataset.**

`contract_commitment` carries `ContractCommitmentPeriodStart` and
`ContractCommitmentPeriodEnd`. The term is in Layer C. So the precondition became
testable and the check now decides:

| Commitment | Coverage | Outcome |
|---|---|---|
| `res-basv2-1yr-001` | term **fully covered** | closure **asserted** and holds exactly at 74.40 |
| `res-basv2-3yr-upfront-001` | usage outside the term | misattribution — see F39 |
| `res-basv2-legacy-2023` | no contract record | term unknown, stays not evaluable |

**One honest shrug became three decidable outcomes.**

**This is an argument for the multi-dataset specification, not a note about our
data.** The invariant is unverifiable from cost_and_usage alone and verifiable
with contract_commitment — which is exactly why the supplemental datasets were
added at v1.3, demonstrated rather than asserted.

It also sharpens the community issue. The recommendation is no longer *"this
sentence needs a scope clause"* but: **scope it to a commitment, and state that
it presupposes full-term coverage — a precondition only the contract_commitment
dataset can establish.** That is a proposal, not a complaint.

### F39 — usage booked against a commitment that had not begun

The three-year reservation, in our own data:

| | |
|---|---|
| Layer C term | 2026-07-31 → 2029-07-31 |
| Usage rows | 2026-07-30 → 2026-07-31 |
| Purchase row | 2026-07-31 → 2026-08-01 |

**The usage precedes the term entirely.** 2.40 of EffectiveCost is attributed to
a commitment that had not started. The purchase row is correctly dated; the two
usage rows are a day early.

Found by arithmetic rather than by looking: the coverage calculation returned
zero overlap, and zero is not a small number here — it is a different condition.
Reporting it as *"0 of 1096 days covered"* would have buried misattribution under
something that reads like rounding, so it reports separately.

**This is the commitment-term check deferred in chunk 4a, arriving on its own.**
It is also the check that would have caught F33 independently of the identifier
collision — the legacy row was dated two years before the reservation it claimed.
DERIVED: no specification sentence requires usage to fall within its commitment's
term, so it warns rather than fails.

**Open — Nakita's call.** Either move the two 3-year usage rows to 2026-07-31 in
`seed_data.py`, or move the Layer C term start to 2026-07-30. The purchase row
sits at 07-31 and the reservation is described as bought on 31 July, so **moving
the usage rows is the consistent fix.** Doing so should convert this warning into
a partial-coverage observation — 1 day of 1096, correctly not evaluable.

### F38 confirmed by the check that was written to test it

`XDS-invoice-reconciliation` joins on `InvoiceId` and on nothing else, because
that is the key the specification names. Result:

- The June invoice totals −1.85 and **no cost row carries its InvoiceId** —
  reported as *not evaluable*, explicitly distinguished from balancing.
- **203 of 204 cost rows carry no InvoiceId at all**, so the identity is outside
  reach for effectively the whole dataset.

A reconciliation with nothing to reconcile is not a clean reconciliation, and the
check says so rather than passing silently.

### D18 — cross-dataset checks reconcile against the merged view

`cost_target()` prefers `unified`. An invoice or a commitment spans layers, and
reconciling against a single layer reports a shortfall that is really a missing
layer — the same misattribution as F33's per-layer purchase row. The per-layer
views remain the right target for provider-behaviour checks such as the
empty-string sweep; they are the wrong target for anything that must see the
whole picture. **Binding is not one rule for all checks: it depends on whether
the check asks about a provider's behaviour or about a total.**

### Billing periods

`XDS-billing-period` reports nothing, which is the correct result: no overlaps,
one Open period, and every cost row falls inside a declared period. DERIVED — the
specification defines the bounds but never states that periods must not overlap.

---

## 20. F38 and F39 resolved · cross-dataset section clean

Both fixes applied and the full chain re-run. **All seven targets 0 FAIL,
cross-dataset 0 FAIL 0 WARN, negative 13 of 14 with 0 incidental, exit 0.**
`self_test.py` still 14/14.

### F39 — the 3-year usage rows moved into the term

`ChargePeriodStart` 2026-07-30 → **2026-07-31**, matching the purchase row and
the Layer C contract term. The warning became the correct observation:

> dataset covers **1 of 1096 days** of the term 2026-07-31 to 2029-07-31, so
> closure is NOT EVALUABLE. Usage 2.40 against a 2628.00 purchase is a short
> export, not a shortfall.

**One day of coverage is the right answer**; zero was misattribution wearing a
rounding-error costume.

Worth noting how it was found: the cost dataset carries no commitment term, so
nothing in it contradicted anything else in it. It took comparing two datasets to
see it. **A single-dataset validator cannot find this class of error at all** —
which is the argument for chunk 6b in one sentence.

### F38 — the invoice now joins on the key the rule names

Two edits, because the fault was in both files.

**`seed_data.py`:** the June correction row now carries
`InvoiceId="INV-2026-07-0001"`. **Which invoice matters and it is not June's.**
`ChargeClass` is "Correction", which per the specification means a correction to
a *previously invoiced* billing period — so June was already issued and this
cannot appear on it. A correction to a closed period lands on the next invoice
and carries a reference back.

**`generate_layer_c.py`:** the invoice is now grouped by
`(InvoiceId, ChargeCategory, ChargeClass)` taken from the cost data, instead of
by a June date window. Rows with no `InvoiceId` are **excluded** rather than
swept into a period bucket — a charge that names no invoice is not on one, and
pretending otherwise is exactly how the old grouping produced an invoice nothing
could join to.

`ChargeClass` is in the grain because a correction appears on a later invoice
than the period it corrects and must carry a reference back. Folding it into the
ordinary line loses the ability to answer *"what on this invoice is a
restatement?"* — the first question anyone asks of an invoice that moved.

Result — two lines, reconciling on the specified key:

| InvoiceId | Category | BilledCost | ReferenceInvoiceId | Description |
|---|---|---:|---|---|
| INV-2026-07-0001 | Usage | 0.24 | INV-2026-07-0001 | Usage charges |
| INV-2026-07-0001 | Usage | −1.85 | **INV-2026-06-0001** | Usage correction to INV-2026-06-0001 |

The harness now reports **1 invoice reconciled on the key the spec names**, and
separately that **202 of 204 rows carry no InvoiceId and are outside invoice
reconciliation entirely.**

**That second number is the finding, and it should stay visible.** It is not a
defect to fix. Azure populates `InvoiceId` on none of its 118 real rows, so on
real provider data the identity is unevaluable for the whole export. The
synthetic layer now proves the check works; the real layer shows why it usually
cannot be used. Both facts are worth more than either.

Derivable mappings (`invoice_for_period`, `period_bounds`, `issue_date`) were
factored into one place, because three fields depend on them and a disagreement
between them is invisible in a CSV.

---

## 21. Chunk 7 — the SHOULD tier · **14 of 14** · 100 checks

The negative proof is closed. Every planted violation is caught by the check that
names its rule, with **0 incidental hits**.

```
14 of 14 caught by the check that names the rule.
 0 awaiting a later chunk.
 0 incidental hits
```

### F40 — the empty strings are a MUST violation, not a SHOULD deviation

**This corrects finding F2 refined, which has been carried through the whole of
Stage 4 and shaped its central design decision.**

The specification states the rule twice, at two severities:

| Source | Text | Severity |
|---|---|---|
| `string_handling.md` | Empty strings and strings consisting solely of spaces **SHOULD NOT** be used in not-nullable string columns. | WARN |
| `null_handling.md` | Columns **MUST NOT** use empty strings or placeholder values … to represent a null or not having a value, **regardless of whether the column allows nulls or not**. | FAIL |

F2 refined cited StringHandling and concluded the defect was a recommendation.
NullHandling is stricter, unconditional on nullability, and squarely on point: an
empty string in `CommitmentDiscountId` on a row with no commitment discount **is**
an empty string used to represent not having a value. That is the MUST NOT,
verbatim.

**The scope that decides the split** is one line of preamble in
`null_handling.md`: *"All columns defined in the FOCUS specification MUST follow
the null handling requirements listed below. Custom columns SHOULD also follow
the same formatting requirements."*

So severity depends on **whose column it is**:

| | Columns | Values | Severity |
|---|---|---:|---|
| FOCUS-defined | `CommitmentDiscountId`, `CommitmentDiscountName` | **236** | **FAIL** |
| Custom `x_` | eleven | **1,170** | WARN |
| | | **1,406** | |

One defect, two verdicts, and the boundary is a single sentence of preamble. **No
validator that treats empty strings as one phenomenon can produce this answer.**

**Azure's real export is therefore non-conformant at MUST level** — a materially
stronger claim than Stage 4 has been making for six chunks, and one that changes
the headline of the case study. The 236 failures are real and the harness reports
them; the F32 suppression text has been corrected to match.

*Why it took until chunk 7:* F2 was settled in Stage 3 from the column-attribute
files, and `null_handling.md` was never read against it. Chunk 7 read it because
the SHOULD tier needed its source text. **A conclusion drawn from the first
applicable rule found is not a conclusion about the specification** — the same
lesson as F28's discarded parent bullet, and the fourth time in Stage 4 that
reading one level further changed an answer.

### D19 — the binding is RAW_VALUES, not PER_LAYER

The guardrail says the sweep binds to the per-layer views and never to
`focus_unified`. The **reason** is decision D3: the unified view normalises `''`
to NULL, so a sweep there returns zero and reads as a pass. The constraint is
about the **transformation applied**, not about which folder a file sits in.

Read literally as "layers only", it excludes the negative fixtures — which are
never merged, never normalised, and carry the one planted
`EMPTY_STRING_PLACEHOLDER` the sweep exists to catch. **The literal reading would
have left it permanently uncaught by the only check written to find it**, and the
proving run would have reported MISSED forever with every component behaving
exactly as specified.

Excluded now, each for a stated reason: `unified` (D3 normalises), `supplemental`
(D17 reads `''` as NULL from CSV, because CSV has no null).

### F41 — grouped reporting made the count wrong and broke the proof

The sweep first reported one violation per column: *"CommitmentDiscountId: 118
rows"*. Readable, and wrong twice.

It made the MUST count read **2** where **236 values** breach the rule — the
count in a conformance report should be the count of breaches, not the count of
places they cluster. And it attached each finding to no row at all, so the
proving run could not match the planted violation to the check that caught it:
**the check fired, the fixture reported MISSED, and both were behaving
correctly.**

Flooding is a display problem and is now solved where display happens — the
report rolls a check up to one line past a handful of violations. Counts stay
exact; the screen stays readable.

### The WARN tier is no longer nearly empty

`rules.py` v4 takes SHOULD-level nullability statements as well as MUSTs. The
corpus is **88 nullability statements, 70 implemented, 18 not machine-checkable**
— up from 85/68/17, the difference being `ChargeDescription SHOULD NOT be null`
and `SkuMeter SHOULD NOT be null when SkuId is not null`.

Recorded because the earlier `0 WARN` on every target partly reflected checks
that had not been written rather than clean data, and a report should not be
readable as the second when it means the first.

### Exit code 1 — and that is correct

`validate.py` now exits **1**, because a MUST is broken on the real Azure layer.
It is not a regression and must not be "fixed": the harness has found a genuine
conformance failure in real provider data, which is what it was built to do. The
synthetic layers, the unified view and all three Layer C datasets remain at 0
FAIL.

---

## 22. Chunk 8 — the conformance report

`validate.py --report` writes `docs/conformance-report.md`. 174 lines, every
figure taken from the run that produced it.

### D20 — the report is generated, never written by hand

A report typed out separately is accurate on the day it is typed and drifts from
the code the first time either changes — and nothing in the file tells a reader
which day that was. Generating it means the report cannot disagree with the
harness, and a reader can regenerate it and get the same file.

`--report` also runs the **negative** target, which the normal run excludes.
**A conformance report that omits the evidence its instrument works is an
assertion, not a report.**

### Sections, and why each is there

| Section | Purpose |
|---|---|
| Header | Both spec versions, the method, and the exact commands to reproduce |
| Verdict | One row per dataset — 236 FAIL on the real layer, 0 everywhere else |
| **Does the harness detect anything?** | The 14 of 14 table, placed before the results |
| What was checked | 100 checks by family; 99 cited, 1 derived |
| **What the harness cannot check, and why** | All 18 refusals, each with its reason |
| Findings | Each grouped by check, **quoting the requirement and linking the raw file** |
| Cross-dataset | The three Layer C rules, including F10 asserted |
| Limitations | Six explicit statements of what a green result does not mean |

**The proof section sits above the results deliberately.** A reader deciding
whether to believe a conformance claim needs to know the instrument was tested
before they read what it found, not after.

**Every finding quotes its requirement and links the raw specification file at
the pinned tag.** A reader who doubts a finding can check it in one click without
taking the harness's word for anything — which is the whole point of deriving
rules from the specification rather than transcribing them.

### The two sections that make it worth reading

**"What the harness cannot check, and why"** lists all 18 refused conditional
requirements with reasons — conditions like *"when a charge is related to a
resource"*, which turn on facts the row does not carry. Not gaps in this harness;
gaps in what any harness can do. **The reference FOCUS Validator cannot make this
statement at all, because it does not evaluate conditional requirements**, so it
has no way to distinguish "checked and passed" from "never checked".

**"Limitations"** states in six lines what a green result does not mean: the
tolerance is our policy and not a requirement; Conditional absence is not a
defect; era gating differs for requirements and values; the sweep never runs
against the merged view; two invariants presuppose term coverage.

A conformance report listing only what passed invites the reading that everything
else was checked and found clean. **It was not, and saying so is the difference
between a report and a marketing document.**

### Still to come

- **Chunk 8b** — repository assembly: `src/`, `docs/`, the redacted
  `screenshots/` bundle, `README.md`, `.gitignore` entry for `spec_cache/`.
- **Chunk 9** — the version-diff script (build spec §9, Amendment A5.2 step 1).
- **Chunk 10** — comparison against the official FOCUS Validator.
- **Closing session** — interview language, held over at Nakita's request since
  the chunk 1 explanation.

---

## 23. Chunk 8b — publication assembly

### `README.md`

Written. It is the artifact a reader meets first, so it leads with what the
harness **found** rather than with how it is built: 236 MUST failures and 1,170
SHOULD deviations in a real Azure export, and one specification-mandated
reconciliation that cannot be performed on Azure data at all.

Three deliberate choices:

**It states the problem before the solution.** Most FOCUS validation code encodes
what its author believes the specification says, and *you cannot tell from reading
the code whether that belief is right*. Everything else in the README follows from
removing that step.

**The 18 unimplemented rules are presented as a result, not an omission.** They
turn on conditions the data does not carry, they are listed with reasons, and the
reference Validator cannot make the distinction at all. A reader who skims will
still see that number framed correctly.

**There is an "Honest scope" section.** It says this is a sandbox export, that
several findings are defects in the project's own synthetic data, and that the
three candidate community issues have not yet been raised. **A portfolio piece
that only lists strengths is read as marketing; one that bounds its own claims is
read as work.** The line worth keeping: the harness catching our own defects, after
they passed a hand-written fifteen-check self-test, *is* the evidence that it
works.

### `.gitignore`

Two additions, in `.gitignore.additions` for review before merging:

- `spec_cache/` — 19 MB, and a copy of a public document rather than this
  project's work. **`docs/spec/*.json` is committed** (220 KB): that is the parsed
  extract every check cites, and committing it is what makes a finding
  re-checkable against the exact text it was derived from.
- `__pycache__/`, `*.pyc` — a stale `.pyc` can shadow a corrected source and
  produce the D14 symptom, an `AttributeError` that reads like a harness defect.

### `requirements.txt` — no change needed

Checked by parsing the imports of all seven scripts rather than by memory. The
only third-party imports across the whole pipeline are **duckdb** and **pyarrow**,
both already required. `spec_source.py` and `rules.py` are standard library only.

### Moving the scripts into `src/`

Every script resolves its root by checking whether it sits in a directory called
`src`, so the move needs no code change:

```bash
mkdir -p src && git mv *.py src/
python3 src/validate.py --report      # verify before committing
```

Verified working from `src/` throughout Stage 4 development.

### Remaining before publication

- [ ] Move scripts to `src/`, merge `.gitignore.additions`
- [ ] Add the redacted `screenshots/` bundle — **only Nakita can produce these**
- [ ] Final `validate.py --report` on the assembled tree, and commit the report
      that run produces
- [ ] Confirm `data/raw/` is absent from `git status` before the first push

---

## 24. Filing layout — the target repository shape

**Assembly is deferred to the GitHub step at the end of the project.** Nothing is
being moved now; working files stay where they are on Drive. This section records
the target so the move is mechanical when the time comes, and so nothing is
decided in a hurry on the day of publication.

### Target tree

```
azure-focus-pipeline/
├── README.md
├── requirements.txt
├── .gitignore
│
├── src/                             every script, one job each
│   ├── spec_source.py               fetch + parse the specification (chunk 1)
│   ├── rules.py                     requirement-sentence parser (chunk 3)
│   ├── validate.py                  the harness (chunks 2–8)
│   ├── seed_data.py                 synthetic fixtures
│   ├── self_test.py                 generator self-test
│   ├── build_unified.py             sanitise + merge
│   ├── generate_layer_c.py          supplemental datasets
│   ├── check_files.py               written-output verification
│   └── loader.py                    Stage 2 schema-aware loader
│
├── docs/
│   ├── conformance-report.md        GENERATED — regenerate before committing
│   ├── STAGE2_WORKING_NOTES.md
│   ├── STAGE3_WORKING_NOTES.md
│   ├── STAGE3_HANDOVER.md
│   ├── STAGE4_WORKING_NOTES.md      this file
│   └── spec/                        the parsed specification — COMMITTED
│       ├── spec_v1.2.json
│       ├── spec_v1.4_billing_period.json
│       ├── spec_v1.4_contract_commitment.json
│       ├── spec_v1.4_invoice_detail.json
│       └── lifecycle.json
│
├── data/
│   ├── raw/                         NEVER COMMITTED — unsanitised
│   ├── raw-sanitised/<pull>/        sanitised per-layer view + manifest
│   ├── synthetic/v1.2/
│   ├── synthetic/pre-1.2/
│   ├── negative/                    the 14 planted violations
│   ├── unified/                     focus_unified.snappy.parquet
│   └── supplemental/                the three Layer C CSVs
│
├── screenshots/                     redacted run output
└── spec_cache/                      GITIGNORED — 19 MB, extracted spec
```

### What is committed, and why

| Path | Commit? | Reason |
|---|---|---|
| `src/`, `README.md`, `requirements.txt` | yes | the work |
| `docs/*.md` | yes | the reasoning is the portfolio, not just the code |
| **`docs/spec/*.json`** | **yes — 220 KB** | the parsed extract every check cites. Committing it is what lets a reader re-check a finding against the exact text it was derived from. Without it the citations are unverifiable. |
| `data/synthetic/`, `data/negative/`, `data/unified/`, `data/supplemental/` | yes | small, synthetic or sanitised, and the harness is not reproducible without them |
| `data/raw-sanitised/` | yes | written **only** after an independent scan reports zero residual identifiers |
| **`data/raw/`** | **never** | unsanitised personal data (F6, guardrail 5). Confirm absent from `git status` before the first push. |
| `spec_cache/` | no — 19 MB | a copy of a public document, not this project's work. Regenerated by one command. |
| `__pycache__/`, `*.pyc` | no | a stale `.pyc` reproduces the D14 symptom |

### Three judgement calls to make before the repository goes public

**1. The course-derived documents.** `Nakita_FOCUS_Analyst_Module6_Keepsake.docx`
and `Nakita_FOCUS_Analyst_Portfolio_Build_Spec.docx` are working documents built
while studying paid FinOps Foundation material, and the keepsake in particular
follows the course structure closely. **They are not in the tree above.**
Recommendation: keep them on Drive as personal study artefacts and do not publish
them. Nothing in the repository depends on them — every rule the harness applies
cites the public specification, not the course.

**2. `Project_1_Master_v3` and `Portfolio_Build_Spec_Amendment_1`.** These are your
own analysis and safe to publish, but they read as internal planning documents
rather than as a public artifact. Recommendation: fold the parts a reader needs
into the README and the working notes, and keep the originals on Drive.

**3. Screenshot redaction.** Terminal output includes the machine hostname and
username in the prompt line. Crop or blur before committing — it is the same
class of leak as `data/raw/`, arriving through a different door.

### Assembly checklist for the GitHub session

- [ ] `mkdir -p src && git mv *.py src/`
- [ ] Merge `.gitignore.additions` into `.gitignore`, delete the additions file
- [ ] `python3 src/validate.py --report` from the new location — verify it runs
      and commit **that** report, not an earlier one
- [ ] Add the redacted `screenshots/` bundle
- [ ] `git status` — confirm `data/raw/` and `spec_cache/` are both absent
- [ ] Confirm `docs/spec/*.json` **is** staged (it is easy to gitignore by
      accident alongside `spec_cache/`, and the citations become unverifiable
      without it)
- [ ] First push

### One property to preserve through the move

Every script resolves its root by checking whether it sits in a directory called
`src`, so the move needs no code change — but that is a property worth
**re-verifying rather than trusting** after the move. Run the full chain once from
the new location before committing anything. It has been developed and tested from
`src/` throughout Stage 4, so it should be uneventful.

---

## 25. Chunk 9 — the version-diff script · **two of three community issues already fixed upstream**

`version_diff.py`. Build spec §9 and Amendment A5.2 step 1, delivered.

```
python3 src/version_diff.py              # v1.2 -> v1.4, this project's case
python3 src/version_diff.py v1.1 v1.2    # any pair of tags
python3 src/version_diff.py --no-impact  # the diff alone
```

### F42 — building it immediately found a silent parser failure

**At v1.4 the requirement bullets moved out of the preamble into an explicit
`## Requirements` section.** `spec_source.py` read only the preamble, so it parsed
**zero** normative statements for every v1.4 column.

That had already bitten, unnoticed, three chunks earlier. Chunk 6a generated
nullability and allowed-value checks for the three supplemental datasets — all of
which are v1.4 — and every generator returned nothing, because there were no
sentences to generate from. **Layer C was being validated for column presence
only.** The run reported `Layer C (v1.4) | 3 checks` and nothing was wrong enough
to notice.

**An empty rule list looks exactly like a clean dataset.** This is the fourth
structural change the spec repo has made across versions, and the second to fail
silently rather than loudly:

| Change | At | Failure mode |
|---|---|---|
| `columns/` → `datasets/*/columns/` | v1.3 | loud (404) |
| Allowed values → own `## Allowed Values` section | v1.3 | **silent** (empty list = unconstrained) |
| `### FOCUS-Defined Properties` level-3 tables | v1.2 | loud (field absent) |
| Requirements → own `## Requirements` section | v1.4 | **silent** (no rules generated) |

Fixed. **300 normative statements recovered** across Layer C — 26, 130 and 144 —
and the harness went from **100 checks to 166**. v1.2 parsing is unchanged at
349/30/30, verified.

Layer C still reports 0 FAIL now that it is genuinely being checked, and the
negative proof holds at 14 of 14 with 0 incidental.

**The tool built to detect specification drift detected drift in the parser that
reads the specification.** Which is the argument for building it, delivered by
building it.

### The duplicate guard was scoped to the dataset

Restoring Layer C's rules made `register()` refuse: `InvoiceIssuerName MUST NOT
be null` is stated identically in two v1.4 datasets. Not a duplicate — one rule
applied to two different tables, which is correct. The guard now compares only
within a dataset.

Worth noting the guard **stopped rather than guessed**, which is the behaviour
wanted from a control whose own rule turns out to be imprecise.

### The half that matters: impact on this harness

The diff itself is unremarkable — anyone with two copies of the specification
could produce it. The second half cannot be produced without a spec-derived
harness:

| | |
|---|---|
| **Cannot be expressed at v1.4** — column removed | 2 (`ProviderName`, `PublisherName`) |
| **Citation stale** — the sentence no longer appears | 5 |
| **Now too strict** — a column became nullable | 0 |

A stale citation means the rule was withdrawn **or** rewritten, and **the harness
cannot tell those apart and does not guess.** Silently re-binding a check to a
similar-looking sentence is how a harness starts enforcing something the
specification does not say.

**A harness built from transcribed rules cannot answer this question at all.** It
has nothing to compare against the new text; the only way to discover what a
version upgrade broke is to run it and read the failures.

### F43 — two of the three candidate community issues are already fixed

The stale citations were the finding. Following them:

**F12 — the nullability contradiction: FIXED at v1.4.** `PricingCurrency` and
`PricingCurrencyEffectiveCost` changed `Allows nulls` from `True` to `False`,
resolving the contradiction with their own "MUST NOT be null" text. Both, exactly
the two columns the chunk 1 exhaustive scan identified.

**F10 and F24 — the unscoped invariants: FIXED at v1.4, and fixed the way we
derived.** The v1.2 text read:

> The sum of EffectiveCost where ChargeCategory is "Usage" MUST equal the sum of
> BilledCost where ChargeCategory is "Purchase".

The v1.4 text reads:

> The sum of EffectiveCost across all **related covering and covered charges**
> MUST equal the sum of BilledCost across the same set of charges, **within the
> charge period of the covering charges** …

Both corrections this project reached independently:

| Our finding | The v1.4 fix |
|---|---|
| F10 — scope it to a commitment | "across all related covering and covered charges" |
| F34 / chunk 6b — it presupposes full-term coverage | "within the charge period of the covering charges" |

And a companion **MAY** was added covering exactly the case chunk 6b reports as
*not evaluable*: the sums may differ when covered and covering charges span
multiple billing periods.

**The FinOps Foundation independently made both corrections we derived from first
principles, and we did not know until the diff tool was pointed at it.** That is
the strongest available evidence that the analysis was right — stronger than
raising the issue would have been, and it means the issue must **not** be raised,
because it is stale.

**PERIOD-ordering — STILL OPEN at v1.4.** `ChargePeriodStart` is still only "the
inclusive start bound" and `ChargePeriodEnd` "the exclusive end bound". Nothing
anywhere requires the end to follow the start. **This is the one live candidate
issue**, and it is now the only one.

### What this changes for the write-up

The community-issue section shrinks from three candidates to one, and gains
something better: **a record of two analyses that were independently confirmed by
the standards body.** "We found this and raised it" is a contribution. "We derived
this correction and the Foundation shipped the same correction" is evidence the
method works.

It also produces a rule worth keeping: **run the diff before raising anything
upstream.** Two of three issues here were already fixed, and raising a stale issue
against a specification you claim to have read carefully is a poor first
impression to make on a community you are trying to join.

---

## 26. Chunk 10 — comparison against the official FOCUS Validator

Run, not assumed. `focus-validator` **2.2.1**, model `1.2.0.1`, targeting FOCUS
v1.2 — the same version this harness targets.

```bash
pip install focus-validator
mkdir -p focus_validator/rules && cp "$(python3 -c 'import focus_validator,os;print(os.path.dirname(focus_validator.__file__))')/rules/currency_codes.csv" focus_validator/rules/
focus-validator --data-file data/unified/focus_unified.snappy.parquet \
                --data-format parquet --validate-version 1.2 \
                --block-download --output-type console
```

*(The `mkdir` is a workaround: 2.2.1 looks for its currency list at a path
relative to the working directory rather than to the package.)*

### F44 — the standing assumption about the Validator was out of date, and had to go

Stage 3 and the FOCUS Analyst course notes both record that the reference
Validator does not evaluate conditional requirements. **That has been repeated
throughout Stage 4 as this harness's main differentiator, and for version 2.2.1
it is false.**

It ships **621 model rules** with AND/OR composites, 96 carrying explicit
applicability criteria, and it evaluated **578 checks** against
`focus_unified`. It caught `ChargeFrequency MUST NOT be "Usage-Based" when
ChargeCategory is "Purchase"` — a genuine cross-column conditional.

Corrected. The differentiator is real but it is **not** the one we had been
claiming, and repeating a stale claim in an interview against a tool the
interviewer may know better would have been considerably worse than finding this
now.

### What it actually does differently — three findings, all reproduced

**1. No era awareness.** Against `focus_unified` it reported **128 violations of
`ServiceSubcategory MUST NOT be null`.** Those are the 118 real 1.0r2 rows plus
the 10 pre-1.2 rows — and **`ServiceSubcategory` was introduced at v1.1.** The
column did not exist when those rows were emitted.

It validates a mixed-version dataset entirely against one version. This harness's
era gate skips exactly those 128 rows, and says so in its scope notes. **On a
dataset spanning three schema revisions, one tool reports 128 MUST failures and
the other reports none, and the second is right.**

**2. Semantic conditions are dropped rather than declined — and there is a proof.**

`InvoiceId` carries two complementary rules: MUST NOT be null when the charge is
associated with an invoice, MUST be null when it is not. Neither condition is in
the data. Against `focus_unified` the Validator reported:

| Rule | Violations |
|---|---:|
| `InvoiceId-C-005-C` — MUST NOT be null | 202 |
| `InvoiceId-C-004-C` — MUST be null | 2 |
| | **204** |

**204 is the row count.** The two rules are complements, so with their conditions
dropped every row must violate exactly one — and every row does. That is a proof
by construction that the conditions are not being evaluated: not an inference
from behaviour, an identity.

This harness **refuses** both sentences, by name, with the reason printed in the
conformance report. Chunk 3's pruning rule exists for precisely this: you may
narrow when a rule applies, never broaden it.

**3. Allowed-value checks are aggregate, not per row.** Established with a
controlled probe — the same file, one column changed:

| Probe | ChargeCategory | Result |
|---|---|---|
| negative fixtures as built | 1 of 14 rows invalid | **PASS** |
| same file, all rows changed | 14 of 14 invalid | FAIL, violations=14 |

One conformant value in a column masks any number of non-conformant ones. On
production data, where every enum column will contain some valid values, **enum
violations would essentially never be detected.**

This is a **false negative on a basic MUST in the reference implementation**, and
it is the strongest of the three candidate community issues — stronger than the
period-ordering gap, because it is a defect rather than an omission. Reproduction
is two files and one command.

### The headline: our principal finding is invisible to it

Against `data/raw-sanitised/` — the real Azure export:

| | Official Validator 2.2.1 | This harness |
|---|---|---|
| Checks executed | 578 | 166 |
| `ServiceSubcategory` null | **118 — false positive** (era) | skipped, out of era |
| `InvoiceId` null | **118 — false positive** (condition dropped) | refused, condition unknowable |
| `ServiceName` / `ServiceSubcategory` 1:1 | 6 — **genuine, and we miss it** | not implemented |
| **Empty strings standing in for null** | **0 — not detected** | **236 MUST + 1,170 SHOULD** |

**236 MUST-level violations of `null_handling.md` in a real provider export, and
the reference Validator reports none of them.** That is the project's central
result, and it now has a control.

### Two rules we do not implement, and should say so

The comparison runs both ways. The Validator caught two SHOULD-level rules this
harness does not:

- `ServiceName SHOULD have one and only one ServiceSubcategory` — a dataset-level
  consistency rule, and a good one.
- `PricingUnit SHOULD conform to UnitFormat requirements` — 3 violations on
  `focus_unified`.

Both are implementable and both are listed in the chunk 7 survey as deferred.
**Recorded rather than quietly omitted: a comparison that only reports where we
win is not a comparison.**

### The candidate community issues, final position

| Issue | Status |
|---|---|
| F12 — nullability contradiction | **fixed upstream at v1.4** (chunk 9) |
| F10 / F24 — unscoped invariants | **fixed upstream at v1.4**, as we derived (chunk 9) |
| Charge period ordering never stated | **open at v1.4** — a specification omission |
| **Validator allowed-values check is aggregate** | **open** — an implementation defect, reproducible in two commands |

Two retired, two live, and the two live ones are of different kinds: one for the
specification, one for the tooling.


---

## 27. F44 revised — the claim was not false, it was undated

The chunk 10 comparison ran against `focus-validator` **2.2.1** in a Python 3.12
environment. Attempting the same install in the project venv (Python 3.9) produced
version **1.0.0** and an `ImportError` — `overload` was removed from `multimethod`
at 2.0 and 1.0.0 still imports it.

Checked against PyPI rather than assumed:

| Version | requires_python |
|---|---|
| 1.0.0 | `>=3.9,<4.0` |
| 2.0.1 through 2.2.1 | **`>=3.12,<4.0`** |

So pip on Python 3.9 silently resolves to the last release from the 1.x line.

**This explains the stale claim rather than excusing it.** The FOCUS Analyst
course notes and the Stage 3 record both say the reference Validator does not
evaluate conditional requirements. **Against 1.0.0 that was very likely true when
it was written.** It is false against 2.2.1, which carries 621 model rules with
applicability criteria.

The claim was never wrong. **It was undated** — and an undated claim about a
moving artifact silently becomes a wrong one. Which is the same lesson as pinning
the specification to a tag, arriving from the tooling side.

**Reproduction requires a separate 3.12 environment.** Do not upgrade the project
venv; the pipeline works on 3.9 and nothing else needs 3.12.

```bash
python3.12 -m venv /tmp/fv && source /tmp/fv/bin/activate
pip install --upgrade pip && pip install focus-validator   # 2.2.1
```

Running 1.0.0 with `multimethod<2` pinned would "work" and would be worse than not
running it: it would confirm the stale claim with fresh-looking evidence.

### Housekeeping before publication

- `spec_v1.2.json`, `lifecycle.json`, `conformance-report.md` exist at project
  root **and** under `docs/`. The root copies are saved downloads; the
  authoritative ones are generated into `docs/`. Delete the root duplicates or
  stale copies will be committed.
- `focus_validator/` at project root is the currency-file workaround. Delete it
  after the comparison.
- `focus_unified.snappy.xlsx` is a local inspection convenience. Not for commit.

---

## 28. Stage 4 closing — presentation and interview material

`docs/STAGE4_PRESENTATION.md` written. Two parts:

**Part A — a presentation script.** A sixteen-minute walkthrough structured as
*problem, method, findings, control, meaning*, with the reasoning to say aloud at
each step and a cut order for shorter slots.

The one structural decision worth recording: **it is deliberately not
chronological.** Ten chunks in order is a build log, and a build log is only
interesting to the person who built it. The presentation opens with the
`MemoryGB` / `MemorySize` example — small, concrete, and it makes an audience want
the answer before any pipeline is described.

**Part B — interview preparation.** The 30-second and two-minute versions, and
prepared answers for the questions that will actually come: a time you were wrong
(the false 14 of 14), a time you disagreed with your own conclusion (F40), how you
handle ambiguity in a standard, the hardest bug (F42 — the one that produced no
error at all), and what you contributed back.

It also carries a short **things not to say** list. The first entry is the stale
Validator claim: it is version-bound and false for 2.2.1, and asserting it to
someone who knows the tool would undo the credibility everything else buys.

**Held over from the chunk 1 explanation at Nakita's request; now delivered.**

---

## 29. F45 — Layer C used the provider's spelling, not the specification's

**Found on Nakita's run, and it corrects a claim made in chunk 9.**

`layerC:contract_commitment` reported **2 MUST violations**:

```
ContractCommitmentPaymentModel = 'NoUpfront'  is not an allowed value (3 permitted at v1.4)
ContractCommitmentPaymentModel = 'AllUpfront' is not an allowed value (3 permitted at v1.4)
```

The FOCUS allowed values are **`No Upfront`, `Partial Upfront`, `All Upfront`** —
with spaces. `generate_layer_c.py` wrote `NoUpfront` and `AllUpfront`, which is
the **AWS API spelling**.

**This is the exact class of error FOCUS exists to eliminate: provider vocabulary
leaking into a dataset whose purpose is to be provider-neutral.** It is invisible
to a human reader — both strings look like the value they are meant to be — and
it is trivially visible to a check that reads the allowed list from the
specification.

It also could not have been found before chunk 9. The v1.4 requirement text was
in a section `spec_source.py` did not read, so no allowed-values check existed for
any Layer C column. **The defect was present from chunk 6a and undetectable until
chunk 9 restored the rules.**

Fixed in `generate_layer_c.py`. Regenerated: `layerC:contract_commitment` back to
0 FAIL, negative proof unchanged at 14 of 14 with 0 incidental.

### A correction to chunk 9's write-up

Chunk 9 stated: *"Layer C still reports 0 FAIL now that it is genuinely being
checked."* **That was wrong.** The run was inspected through a `grep` filter and
the claim was made from the filtered view rather than from the output.

**The same failure this project keeps finding, made in reporting rather than in
code: reading one level short.** F28 discarded the parent bullet. F40 read one
attribute file and not the other. F42 read the preamble and not the new section.
This read a filter and not the run.

Worth keeping in the write-up rather than quietly correcting, because the pattern
is the finding: **every one of those was caught by something downstream noticing a
number that did not fit, not by anyone re-reading more carefully.** That is an
argument for instruments over diligence.

### Environment note — the project venv's pip

The chunk 10 attempt upgraded pip inside the Python 3.9 project venv from 21.2.4
to 26.0.1 and left it broken: `No module named 'pip._vendor.rich.markup'`. pip
26.0.1 does declare 3.9 support, so this is an incomplete install rather than a
version mismatch.

```bash
source .venv/bin/activate
python3 -m ensurepip --upgrade
python3 -m pip uninstall -y focus-validator
```

Cosmetic: nothing in the pipeline imports pip or `focus-validator`, which is why
`validate.py` ran normally immediately afterwards.

---

## 30. Chunk 10 CORRECTED — reproduced on real hardware, and three numbers were wrong

The chunk 10 comparison was rerun by Nakita against `focus-validator` **2.2.1** on
Python 3.12. Two of the three datasets produced different results from the
sandbox, and **the sandbox was the one that was wrong.**

### Why my numbers were wrong: I tested against a reconstruction

The sandbox has no real `data/raw/`, so `data/raw-sanitised/` was rebuilt there
from `focus_unified` — the **114-column union**. Nakita's genuine export is
**99 columns**. Columns the union carried as null are, in the real file, simply
**absent**.

So my run reported *"ServiceSubcategory MUST NOT be null — 118 violations"* where
the real run reports *"Column 'ServiceSubcategory' RECOMMENDED to be present"*.
**Same defect, different symptom, and my number was an artefact of the stand-in.**

**This is the fourth time in Stage 4 that testing a reconstruction rather than the
thing itself produced a confident wrong answer**, and it is the one I should have
predicted, having written the other three up. The lesson is not "be careful": it
is that **a stand-in built by a different route than the original will differ in
ways that are invisible until something downstream disagrees.**

### The corrected comparison

**`focus_unified` (204 rows, three eras) — reproduced EXACTLY.**

| Finding | Sandbox | Nakita |
|---|---:|---:|
| `ServiceSubcategory MUST NOT be null` | 128 | **128** |
| `InvoiceId MUST NOT be null` | 202 | **202** |
| `InvoiceId MUST be null` | 2 | **2** |
| `PricingUnit SHOULD conform to UnitFormat` | 3 | **3** |
| `ServiceName SHOULD have one ServiceSubcategory` | 2 | **2** |

**202 + 2 = 204 = the row count.** The two InvoiceId rules are complements, so
with their conditions dropped every row must violate exactly one — and every row
does. The identity holds on real hardware.

**`data/raw-sanitised/` (the real Azure export, 99 columns) — CORRECTED.**

Not 118 null violations. Instead: `ServiceSubcategory` and `InvoiceId` reported
as **columns not present**, with the dependent MUST rules failing behind them.
The era blindness is identical — it demands a v1.1 column of a 1.0r2 export — but
the symptom is absence rather than nullity.

**Unchanged and still the headline: not one finding about empty strings.** The
harness reports **236 MUST + 1,170 SHOULD** on this exact file. The reference
validator reports none of them, and instead reports findings that are false.

**`data/negative/` (14 planted faults) — NEW, and the most useful of the three.**

| | |
|---|---|
| Planted faults **caught** | **4 of 14** — ServiceCategory null, BillingCurrency ISO 4217, ChargeClass value, ChargeFrequency/Purchase |
| Planted faults **missed** | 10, including the invalid enum |
| **False positives** | **14** — `InvoiceId MUST NOT be null` on every row |

Against **14 of 14 with 0 incidental** for this harness, on the same file.

### F46 — the allowed-values defect, confirmed on real data

```
ChargeCategory-C-003-M: PASS  (violations=0, OR passed — satisfied by
                               rules: [check_value#1, check_value#2, check_value#3])
```

Row 2 of that file holds `ChargeCategory = "Consumption"`, which is **not** an
allowed value. It passes because the OR is satisfied by the *other* rows' valid
values — the check is evaluated across the column, not per row.

**One conformant value masks any number of non-conformant ones.** On production
data, where every enum column contains valid values, enum violations would
essentially never be detected. A **false negative on a basic MUST in the reference
implementation**, reproducible in one command.

Confirmed earlier by a controlled probe — same file, all 14 rows invalid → FAIL,
one row invalid → PASS — and now independently on Nakita's machine.

### A correction in the Validator's favour

The presentation script said the reference tool "has no way to distinguish
checked-and-passed from never-checked". **That is too strong and must be
softened.** Its output is full of explicit declarations:

- `SKIPPED — validation is dynamic and cannot be pre-generated`
- `SKIPPED — not applicable to current dataset or configuration`
- `SKIPPED — marked as MAY/OPTIONAL and not enforced`

It *does* say what it declined and why, per rule. The distinction that survives is
narrower and still real: **it does not distinguish requirements that are
unknowable from the data**, which is what the 14 InvoiceId false positives are —
a condition it could not evaluate and asserted anyway rather than declining.

Recorded because overstating a competitor's limitation is the same error as F44,
and it would be found by anyone who ran the tool.

---

## 31. Outstanding actions — publication and community

Consolidated from across Stage 4 so nothing is carried only in prose. Two lists:
things to do before the repository is public, and things to raise upstream.

### 31.1 GitHub / publication checklist

**Structural** (target tree in §24):

- [ ] `mkdir -p src && git mv *.py src/` — nine scripts
- [ ] Merge `.gitignore.additions` into `.gitignore`, then delete it
- [ ] **Re-run the full chain from the new location before committing.** Every
      script resolves its root by checking whether it sits in a directory called
      `src`, so no code change is needed — but that is a property to
      **re-verify rather than trust**, which is the whole habit of this stage.
- [ ] `python3 src/validate.py --report` and commit **that** report, not an
      earlier one. It is generated; a stale copy is a wrong copy.
- [ ] **`python3 src/publication_check.py` — LAST, immediately before the first
      push.** See §32. Exit 0 is required. It does not cover screenshots, and
      says so on every run.

**Files that must NOT be committed:**

- [ ] `data/raw/` — unsanitised personal data (F6). **Confirm absent from
      `git status` before the first push.**
- [ ] `spec_cache/` — 19 MB, a copy of a public document
- [ ] `focus_unified.snappy.xlsx` — local inspection convenience
- [ ] `focus_validator/` — the chunk 10 currency-file workaround
- [ ] Root-level duplicates of `spec_v1.2.json`, `lifecycle.json` and
      `conformance-report.md` — these are saved downloads; the authoritative
      copies are generated into `docs/`

**Files that MUST be committed, and are easy to lose:**

- [ ] **`docs/spec/*.json`** (220 KB). Easy to gitignore by accident alongside
      `spec_cache/`, since both are "the specification". **Without it every
      citation in the conformance report is unverifiable**, and the traceability
      claim — the entire point of the project — cannot be checked by a reader.

**Screenshots:**

- [ ] Redact before committing. Terminal output carries the machine hostname and
      username in the prompt line — the same class of exposure as `data/raw/`,
      arriving through a different door.
- [ ] Suggested three: the chunk 1 spec-source output, the 14-of-14 proving run,
      and the real-layer 236/1,170 split.

**Judgement calls made and recorded:**

- Course-derived documents (`Module6_Keepsake`, `Portfolio_Build_Spec`) stay on
  Drive and are **not** published. Nothing in the repository depends on them —
  every rule cites the public specification, not the course, which is what makes
  that separation clean rather than awkward.
- `Project_1_Master_v3` and `Amendment_1` are your own work and safe to publish,
  but read as internal planning. Fold what a reader needs into the README and
  keep the originals on Drive.

### 31.2 Community issues — two live, two retired

**Run `version_diff.py` before raising anything.** Two of the original four
candidates were already fixed upstream, and raising a stale issue against a
specification you claim to have read carefully is a poor first impression to make
on a community you are trying to join. That check took one command.

**LIVE — specification omission.**

> **No requirement that `ChargePeriodEnd` follow `ChargePeriodStart`.**
> Verified absent at v1.2 **and at v1.4**. The specification defines
> `ChargePeriodStart` as the inclusive start bound and `ChargePeriodEnd` as the
> exclusive end bound of the effective period of a charge, but nowhere states the
> ordering between them. A period whose exclusive end precedes its inclusive start
> contains no time and cannot be the effective period of anything — the conclusion
> follows, but from two sentences read together rather than from a sentence.
>
> This project implements the check and **labels it DERIVED** for that reason: it
> is the harness's only rule that does not quote the specification.
>
> The kind of gap everyone assumes is covered precisely because it is too obvious
> to write down.

**LIVE — reference implementation defect.** *(the stronger of the two)*

> **`focus-validator` 2.2.1 evaluates allowed-value checks across the column
> rather than per row.** One conformant value masks any number of non-conformant
> ones.
>
> Reproduction, two commands and one edited column:
>
> | Probe | ChargeCategory | Result |
> |---|---|---|
> | negative fixtures as built | 1 of 14 rows invalid | **PASS** |
> | same file, all rows changed | 14 of 14 invalid | FAIL, violations=14 |
>
> ```
> ChargeCategory-C-003-M: PASS (violations=0, OR passed — satisfied by
>                               rules: [check_value#1, check_value#2, check_value#3])
> ```
>
> On production data, where every enum column contains some valid values, **enum
> violations would essentially never be detected.** A false negative on a basic
> MUST. Confirmed independently on two machines.

**RETIRED — already fixed upstream, do not raise:**

| Issue | Resolution |
|---|---|
| F12 — `PricingCurrency` and `PricingCurrencyEffectiveCost` normative text contradicts the constraints table on nullability | **Fixed at v1.4** — `Allows nulls` changed True → False on both, exactly the two columns the chunk 1 exhaustive scan identified |
| F10 / F24 — two unscoped `EffectiveCost` invariants | **Fixed at v1.4**, and fixed the way this project derived: scoped to *"related covering and covered charges"* and qualified *"within the charge period of the covering charges"*, with a companion MAY covering the partial-coverage case |

**The second retirement is worth more than raising it would have been.** The
FinOps Foundation independently made both corrections this project reached from
first principles — scope it to a commitment, and state that it presupposes
full-term coverage. That is not a contribution to claim; it is evidence the method
works, and it belongs in the case study rather than in an issue tracker.

### 31.3 Two rules this harness does not implement

Found by the chunk 10 comparison, both catchable by the reference validator and
both implementable here:

- [ ] `ServiceName SHOULD have one and only one ServiceSubcategory` — a
      dataset-level consistency rule, and a good one
- [ ] `PricingUnit SHOULD conform to UnitFormat requirements` — 3 violations on
      `focus_unified`

Recorded rather than quietly omitted. **A comparison that only reports where you
win is not a comparison**, and the conformance report's Limitations section is
worth less if these are absent from it.

---

## 32. The sanitisation gate — a control, not a checklist item

**Prompted by Nakita asking whether the notes carried a reminder to sanitise
everything before publishing. They carried part of one, and not the useful part.**

§24 and §31.1 held *negative* rules — do not commit `data/raw/`, redact the
screenshots. Both are about files you **exclude**. Nothing checked the files you
**include**.

That gap matters because `docs/conformance-report.md` is **generated**, and its
violation messages embed values:

```
ChargeCategory = 'Consumption' is not an allowed value
ResourceId = '...' but MUST be null when ...
```

Today the real layer's only failures are the empty-string ones, whose messages
carry column names and nothing else. **So the report is clean by luck of which
rule is broken, not by design.** Different data breaks a different rule and
prints a different value.

### The one strong property, worth stating because it beats any scan

`validate.py` **never reads `data/raw/`.** It is deliberately absent from
`TARGET_SPECS`; only `build_unified.py` touches it, and only to write sanitised
output. **So no publishable artefact is generated from unsanitised data, by
construction rather than by inspection.**

That is a better guarantee than a checklist. It holds only while nobody adds it,
and it says nothing about screenshots or anything written by hand — which is why
the gate below exists anyway.

### F47 — the first version of the gate cried wolf twenty-four times out of
twenty-six

Written as a shape scan — GUIDs, `/subscriptions/…`, email addresses — it
reported **26 problems, of which 24 were false**: all-zeros placeholders,
`{SUBSCRIPTION_ID}` templates, the documented synthetic fixture run id, and its
own regular expressions.

**A check that fires on the wrong thing is worse than no check**, because it
teaches you to skim past it. That is finding F30 arriving inside the tool built
to prevent leaks.

**The question was wrong.** Not *"does this look like an identifier"* but **"is
this one of MY identifiers"** — and that has an exact answer, because
`data/raw/` is on disk and the real values are in it.

### `publication_check.py`

Two tiers, and the split is the whole design:

**Blocking — exact match against the real export.** Reads `data/raw/` purely to
build a deny-list, scans every publishable file for those exact strings, and
**never prints a value it found.** Printing it would put the identifier into
terminal scrollback and from there into a screenshot — the leak the check exists
to prevent, committed by the check itself.

It reports the file and the count. If `data/raw/` is absent it says **CANNOT
RUN** rather than passing: a check that cannot run must say so, because a silent
skip is indistinguishable from a clean result. That is F42 — the empty rule list
that looked like a clean dataset — applied to a control.

**Advisory — shape scan, for review.** Useful on prose, which can leak something
the raw export never contained. Reported, never blocking.

It also verifies the two directions the checklist covers separately:

- paths that must be gitignored are gitignored
- **files that must be COMMITTED are present** — specifically `docs/spec/*.json`,
  which is easy to exclude by accident alongside `spec_cache/` since both are
  "the specification". **An omission is a publication defect too**: without it
  every citation in the conformance report is unverifiable and the traceability
  claim cannot be checked by a reader.

### What it cannot check, printed every run

**Screenshots.** Terminal output carries the machine hostname and username in the
prompt line — the same class of exposure as `data/raw/`, through a different
door — and no text scan reads a PNG. The script names this at the end of every
run, including clean ones, so a green result never implies the screenshots were
covered.

### Where it goes in the sequence

**Last, immediately before the first push**, after the `src/` move and the final
`validate.py --report`. Added to the §31.1 checklist.

Verified by running it against a deliberately broken tree — `data/raw/` present
and ungitignored, two saved-download duplicates at root, no `.gitignore` — and it
reported exactly those five and nothing else, exit 1.
