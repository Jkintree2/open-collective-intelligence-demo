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
| 14 Sep | Server-side speech to text for better dictation (browser engine quality is the limit) | Dictation email | Web Speech API is the 0.1 dictation; repeated words on Android is a bug for Session 5 |
| 14 Sep | Platform answers questions from the knowledge graph | Conversational email | Needs a retrieval and answer path, a second model call |
| 14 Sep | Tools: calculator, calendar, Wikidata, Wikipedia, fact-checking sites | Conversational email | |
| 14 Sep | Platform describes itself: model, software, host, hardware, energy, and the sources of each answer | Conversational email | A static About page is the cheap part |
| 14 Sep | Platform asks who, when, where, why and how for each issue, evidence and solution | Conversational email | The card already asks about the what |
| 15 Sep | One-click approve and oppose buttons on the issue page | Sentiment on solutions | Only meaningful once each person is counted once; needs accounts |
| 15 Sep | Location on each post, issues filtered by place | Sentiment clarification | SOW "not included": geographic filtering |
| 15 Sep | Working through reasons for opposition and amendments towards consensus | Sentiment clarification | A process, not a field |
| 15 Sep | Solutions of the current issue listed on the write-about card with the three stance choices | Sentiment on solutions | Done as goodwill in the 0.1 revision round (promised 16 Sep); done 21 Sep |
| 15 Sep | Delay between repeated posts from one source (anti-flood) | Security email | Done as goodwill in the 0.1 revision round (promised 16 Sep); done 21 Sep |
| 16 Sep | Fetch the page behind an evidence link, verify it says what the poster claims, extract further entities from it | Links to evidence | Document ingestion plus a second model pass per link; biggest 0.2 candidate |
| 16 Sep | Confidence level for the trustworthiness of each linked source | Links to evidence | Method needs discussion with John first |
| 16 Sep | Reader told which issue the tester is writing about; card lists grouped (this card, this issue's family, the rest); summary of the issue above the write-about form | Fix emails | Done as goodwill in the 0.1 revision round (promised 17 Sep); done 21 Sep. The new-parent-on-same-card case and issue-name link styling are bugs, not goodwill |
| 21 Sep | Keyword search on the Issues page | Session 5 feedback | Priced separately after the handover |
| 21 Sep | Moving an issue under another, renaming, or merging two issues that mean the same thing | Session 5 feedback | A childless top-level issue can already gain a parent through the card; anything else is tree editing, priced separately after the handover |
| 21 Sep | Deleting an issue with its evidence and solutions from the site | Session 5 feedback | Not wanted: deletion stays in the back room, per post |

## What to watch for

He will send content, not feature requests, and that is welcome. Content goes in the seed or in the feed, never into new code.

He reads carefully. If a request is actually a wording change (the sentence at the top, a label, a verb), it is in scope and takes ten minutes; do it and say so.

If a request is small and would take under half an hour and he has not asked for anything else that week, it is Eston's call, but it still goes in the table with "done as goodwill" so the precedent is visible.
