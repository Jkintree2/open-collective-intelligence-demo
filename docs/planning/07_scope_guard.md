# 07. Scope guard

One page. Read it before saying yes to anything.

## The sentence

When John asks for something not on the "in" list:

> That goes on the list for after the demo.

Warmly, then add it to the list below and move on. If he writes "it seems like it could be included with no extra effort", the answer is the same sentence plus a price at 150 USD per hour, in writing, before any work. The APPROVES and OPPOSES addendum was the one goodwill exception and it said so at the time.

## In (version 0.1)

* A public URL behind one shared passphrase, no accounts.
* One page: a sentence, an optional name and an anonymous checkbox, a text box, browser dictation, an editable card that shows what was found, a Post button, a feed of posts showing the structure pulled from each.
* Extraction by a pay-per-use model in John's DeepSeek account, behind an adapter that is three environment variables.
* The card works with the model absent. Posting an empty card stores the text as a plain statement.
* Neo4j Aura in John's account with his schema: Person, Issue, Evidence, Solution; CLAIM, SUBMIT, PROPOSE, HAVE_PROPOSED, SUPPORTS, REFUTES, APPROVE, OPPOSE; sub-issues via PART_OF; anonymous flag on edges; optional link on evidence; timestamps.
* Autocomplete against existing names on every card field; existing names passed to the model so posts about the same thing land on the same node.
* Issues view ranked by distinct people with three sorts (most people, most recent, most evidence), top-level issues ranked on their whole family; issue detail with solutions, raw approve and oppose counts, evidence for and against, and the posts that touched the issue.
* Seed: the world government issue, five sub-issues, fourteen statements (five in John's own words), real citations, approved by John.
* Admin page: reload seed, reset to seed, download a copy, delete a post.
* Code in a GitHub repository under John's account, MIT, with automatic deploys; hosting, database and model key all in accounts John holds.
* Operator's guide in plain language, one hour walkthrough call, one revision round.

## Out (say the sentence)

From the SOW's "not included" list: individual user accounts and tester invitations, vector search and embeddings, trust or credibility weighting, sentiment and trend analysis, geographic or jurisdiction filtering, multilingual retrieval or non-English input, IPFS, ingestion of PDFs, Wikipedia pages or video, personhood validation, on-device models.

From the addendum: approve and oppose buttons, one stance per person per solution, changing or withdrawing a stance, ranking solutions by net support, sentiment over time.

From the kickoff: threaded replies, reactions, editing or deleting one's own post, verifiable evidence or source quality, a custom domain, a graph visualisation, the Cypher merge statement preview (priced at 600 USD), DECIDE and assemblies.

Anything that needs a second model call per post (summaries, fact checks, suggested rebuttals, translation).

## After the demo (living list)

Started at kickoff. Everything John raises that is outside the list above goes here with the date. Send it to him with each recap so nothing is lost and he can see it growing.

| Date | Item | Raised by | Note |
|---|---|---|---|
| 3 Sep | Threaded replies or reactions on posts | kickoff | The shared nodes are the conversation in 0.1 |
| 3 Sep | Verifiable evidence and source quality | kickoff | Evidence is text plus a link in 0.1 |
| 3 Sep | Individual accounts and invitations | kickoff, R3, R4 | Priced: 450 USD |
| 4 Sep | Approve and oppose buttons, one stance per person, stance over time | addendum 01 | To be priced after he has used the demo; needs accounts first |
| 4 Sep | Approving a document (his "APPROVES UDHR") | addendum 01 | Documents are Evidence in this schema; approving evidence is a different idea from approving a solution |
| 5 Sep | Editable Cypher merge preview | R9, R10 | Priced: 600 USD |
| 5 Sep | Merging two nodes that mean the same thing | planning | Entity resolution beyond names |
| 5 Sep | Deleting or editing one's own post | planning | Admin can delete in 0.1 |
| 5 Sep | Non-English input | planning | The demo says English only |
| 5 Sep | Second revision round | SOW | Priced: 300 USD |
| 5 Sep | A graph picture (his artifact's Map tab) | planning | Not in the SOW; ask before building |
| 5 Sep | Feed paging beyond the sixty most recent posts | review | Sixty is plenty for a closed test |
| 5 Sep | Restoring a downloaded copy from the admin page | review | In 0.1 a developer runs `scripts/restore.py`; the guide says so |

## What to watch for

He will send content, not feature requests, and that is welcome. Content goes in the seed or in the feed, never into new code.

He reads carefully. If a request is actually a wording change (the sentence at the top, a label, a verb), it is in scope and takes ten minutes; do it and say so.

If a request is small and would take under half an hour and he has not asked for anything else that week, it is Eston's call, but it still goes in the table with "done as goodwill" so the precedent is visible.
