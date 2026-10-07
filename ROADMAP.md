# Roadmap

Open Collective Intelligence is a conversational platform for digital democracy: people write statements about issues they care about, the platform sorts each one into issues, solutions and evidence, and everything joins one shared database that everyone can read. This page lists what has been built so far and the phases that come next. Each phase stands on its own.

## Built so far

### Version 0.1: the working prototype (September 2026)

| Release | Date | What it added |
|---|---|---|
| v0.1.0 | 7 Sep 2026 | The first live site: a passphrase protected page for writing a statement and reading the shared record |
| v0.1.1 | 7 Sep 2026 | Seeded example content, the Issues pages, and suggestions from the record while typing |
| v0.1.3 | 14 Sep 2026 | Reading: each statement is sorted into issues, claims, evidence and solutions on a card the writer checks before posting; optional dictation; a private back room with export and restore |
| v0.1.4 | 21 Sep 2026 | A revision round from the first week of testing |

At handover on 24 September 2026 the prototype moved to accounts held by John Kintree, with this repository deploying the live site automatically.

### Since version 0.1

* **28 September to 1 October 2026:** the platform's statement of purpose, followed by the full text of the Universal Declaration of Human Rights and the Earth Charter, added to the instructions the model reads ([app/extract.py](app/extract.py)).
* **2 October 2026:** approving a solution now records just the approval ([issue 4](https://github.com/Jkintree2/open-collective-intelligence-demo/issues/4)), and two fixes for posting and dictation on phones.

## Next phases towards prototype v0.2

### Phase 1: People and positions

Every tester gets their own sign-in, so a person is counted once and can stand behind what they post.

* Invitation only accounts: an existing member invites a new person, who accepts through a link and sets their own password, and every account can be traced to whoever invited it
* One click approve and oppose on the issue page: one stance per person, which they can change or withdraw, with solutions ranked by net support
* Edit or delete one's own post
* Keyword search on the Issues page
* Tidying the issue tree: move an issue under another, rename it, or merge two issues that mean the same thing, with a record of every change

### Phase 2: Evidence that checks itself

Evidence stops being just a link. The platform reads the page behind it and tells the person what it found before anything is saved.

* Read the page behind an evidence link and check whether it says what the poster claims (supports, refutes or unclear), and suggest the further issues, solutions and evidence it contains, for the person to accept or correct
* Source confidence: a simple, published method (type of source, date, primary or secondary, agreement with other sources), shown in words rather than scores

### Phase 3: Talking to the prototype

The platform starts to talk back: it answers questions from what people have posted and asks the questions a good moderator would.

* Ask the prototype a question in plain language, with answers that come only from what is posted and cite the posts they came from
* Follow up questions on the card: who, when, where, why and how for a new issue, piece of evidence or solution
* Guiding principles: rules that put the statement of purpose, the Universal Declaration of Human Rights and the Earth Charter to work when reading statements, answering questions and asking follow ups (the documents themselves are already in place)
* An About page describing the model, software and host, what each answer is built from, and the two guiding documents in full
* A place on each post and an "issues near me" filter

### Phase 4: Meeting people where they are (after prototype v0.2)

A connector for AI assistants (MCP), so people can read and post to the record through ChatGPT, Claude or similar assistants instead of the website. It builds on Phases 1 and 3, because an assistant acting for someone needs that person's account and a way to query the record.

### Later

* A consensus process (reasons for opposition, amendments, rounds), once its design has been discussed
* Tools for answering questions (calculator, Wikidata, fact checking sites), after Phase 3
* Server side speech to text, if phone dictation is still a problem

## Taking part

To test the prototype or suggest a change, open an issue in this repository or contact John Kintree. All code is released under the [MIT License](LICENSE).
