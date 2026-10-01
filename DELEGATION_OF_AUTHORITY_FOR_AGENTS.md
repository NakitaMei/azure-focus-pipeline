# Delegation of authority for agents

*The employee test. A position note by Nakita Meiring, 1 October 2026.*

## The position

An AI agent that takes actions should be governed as an employee, not as a tool. A tool does what the person holding it decides. An agent decides for itself, within whatever room it has been given: it shuts down a machine, deletes a disk, buys a commitment. Once software is making decisions that spend or commit money, the first question is no longer "what does it cost to run?" but "what is it allowed to do, and did it stay inside that?"

I call this the employee test. If you would not let a new hire do something without a mandate, a limit and a review, an agent should not do it without them either.

## Why I am writing it down

The conversation about agents in FinOps runs quickly to what they can do and says little about the controls around them. A common answer to who should own an agent that works on cloud cost is the FinOps team alone. I disagree: governing an agent is shared work, as FinOps itself is, with finance, engineering, procurement and leadership (the personas, in the Framework's term) each holding a part.

The barriers to adopting agents are also not technical. What is missing is the paperwork. Finance has had that paperwork for a long time and calls it delegation of authority: the written rules for who may commit the organisation to what, and up to what amount. It carries over to an agent with very little translation.

## The four questions

Finance asks four questions of any employee who can commit the organisation's money. They are the same four for an agent.

1. **What is your mandate?** A written statement of what the agent is there to do, signed by a named person who answers for it.
2. **What may you do alone, and what needs a second signature?** Approval limits: what the agent may do by itself, what needs a human approver, and what it may never do.
3. **Where is the record?** A log of every action, written at the time, that the agent cannot edit.
4. **Does it reconcile?** A regular check that what was authorised, what was done and what was billed agree, with every difference explained.

An agent missing any one of these is an employee nobody is supervising.

None of this means a human in every step. A trusted employee handles routine work without asking each time, and an agent whose work is tested and trusted can do the same. Clearing out orphaned resources, the ones no longer attached to anything in use, is the example I hear most, and I agree with it where the amounts are small and the action can be undone. But that freedom is itself a delegation: someone decided what counts as routine, and the record and the reconciliation still apply. Beyond the routine, the second signature comes back.

## Value against the mandate

Most discussion of agent cost starts with tokens, the units of text a model is billed on. Token cost matters, and this repository reconciles real token spend to the bill. But nobody judges an employee by salary alone. We judge them by what they delivered against what they were asked to do. The same holds for an agent: without a mandate there is nothing to measure value against, and cost is the only number left.

## Scope, and what comes next

No agent runs in this repository. This is a position, not a finding, and it sits beside the [governance note](GOVERNANCE_NOTE.md), which covers the controls on AI spend. A fuller paper setting out the mechanism is underway.
