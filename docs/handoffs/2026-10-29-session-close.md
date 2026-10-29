# Handoff, 29 October 2026: session close after John's call

No code has changed since `bf06061` (PR 51). This closes the session that ran John's call of 28 October and shipped PRs 47 to 51. The technical state in `2026-10-28-v02-follow-ups-live.md` still holds.

## State

* Live site: Phase 3 complete, all four switches on (John set them on 28 October). `scripts.smoke` 25 of 25 after the last deploy.
* No open pull requests and nothing in progress.
* The branches of PRs 49 to 51 are deleted locally. The GitHub branches of PRs 47 to 51 are merged but not yet deleted.

## Next session, start here

1. `git fetch` and look at `main` for commits John made himself on GitHub.
2. Read the latest handoffs here, then the builder's private notes for John's emails, replies and the next scope of work.
3. Every merge to `main` deploys John's live site: tests green, local site opened, the builder's go, then `scripts.smoke` and a read-back of the live pages.

## Open

* No way for John to remove a listed question himself; the operator's guide says to ask whoever helps with the site.
* Duplicate solutions ("Global carbon tax by referendum" and "Carbon tax"): John can merge them with Tidy.
* John's ideas for the next phase (wiki-style editing of a proposed solution, a conversational interface by voice) are not yet agreed or scoped. Nothing to build until they are.
