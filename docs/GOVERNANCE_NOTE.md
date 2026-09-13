# Governing AI spend: what one afternoon of real token cost taught

*A note for the people who sign the budget.*

Most guidance on controlling AI spend assumes there is already a lot of it.
This note comes from the other end. It describes what one person learned
from spending twenty-eight cents on a real AI workload, in a sandbox with
one user, over one afternoon and one follow-up week. The lesson is that
every control that matters at a million dollars a month was already
load-bearing at twenty-eight cents, and that all four of them are decisions
a budget holder can make, not settings an engineer has to find.

**The first control is quota.** Before a single request was sent, the model
had already been chosen, and not by us. The catalogue's retirement schedule
had removed the model the plan named, and every interactive deployment type
came with a default quota of zero, so the only model that could be deployed
was the one that came with capacity attached. Quota, in other words, is not
an obstacle to adopting AI. It is the earliest and cheapest cost decision an
organisation makes, and it is usually made by whoever hits the wall first
and files a request in frustration. It should instead be made deliberately,
by a named budget holder, with the same care as a spending authority,
because that is what it is.

**The second is the buying mode.** The workload was run in batch mode, which
halved the price per token in exchange for a promise of results within
twenty-four hours. The halving was verified from what Microsoft actually
billed, not read off a price list, and the twenty-four-hour promise was kept
in under ten minutes, twice. A batch deployment also carries a limit on how
many tokens may be queued at once. Ours was set at two million of an allowed
fifty million. That limit is the only budget that exists today in the
currency AI is actually priced in, and it should be set the way a spending
limit is set, by someone who will answer for it. Work that can wait should
default to batch. Work that cannot should have to say why.

**The third is placement.** A quick-start wizard put the AI resource in a
resource group that Azure creates for its own network monitoring, outside
the group the project governs, and gave it the platform's own tags instead
of ours. The spend was real. It reconciled to the cent. And it was invisible
to the showback that tells each team what it consumed. This was shadow AI
on the first day, in a sandbox with a single user, and every team in a large
organisation has the same wizard. The allocation queries caught it after the
fact, because surfacing spend that nobody tagged is what allocation is for.
A policy that restricts where AI resources may be created, and requires the
organisation's tags at creation, would have prevented it before the first
request. At scale this is the untagged bucket, and nothing downstream of it
can be trusted until it shrinks.

**The fourth is credentials.** The API key for the deployment was exposed
three times in one working week: pasted into a chat, captured in a
screenshot, and pasted again. This happened despite a design that keeps
secrets out of files and in the environment, which is a reminder that a
credential's most common route into the open is a person being helpful.
Each exposure was logged. The publication checker that runs before anything
in this repository goes public screens for the class. And the response is
recorded as a fact rather than an intention: Key 1 was regenerated on
7 September 2026, after three logged exposures, before anything was
published.

Quota, buying mode, placement, credentials. None of them needed scale to
surface, none of them needed a data scientist to control, and all four
belong on the same page as the budget.
