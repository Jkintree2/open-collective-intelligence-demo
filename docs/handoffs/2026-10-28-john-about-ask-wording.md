# Handoff, 28 October 2026: John's requests after switching Phase 3 on

John's two emails of 28 October ("Turning on Phase 3" and "Turning on Phase 3, system prompt") ask for three things. Phase 3 is switched on in Render (Ask and About are in the live menu).

## Shipped

**PR 42** (merge `bc8216a`): About keeps John's own wording and shows the whole menu.

* John edited `about.html` on main himself (3adfef8, fe80d90: "shared database", "form", "language model"). Those commits deployed but failed four tests in `tests/test_about.py`. PR 42 keeps his words, finishes the three spots still saying reading service, card and record, changes the line shown with no key to "No language model is set up…", and brings `04_interface.md` and the tests in line. CLAUDE.md rule 5 now allows "language model" on About only.
* About opens without signing in, so `require_access` never looked for the member and the menu dropped Enter a person, My statements and My account. `routes_about.about` now calls `current_member(request)` first.

**PR 43** (merge `c5e3e87`, deploy success, smoke 25 of 25; live, "What does the UDHR say about privacy?" quotes Article 12): **Ask uses the guiding documents.** John asked "what does the UDHR say about privacy" and whether a global carbon tax is consistent with Earth Charter 7d; Ask said the record holds nothing. Causes in `app/ask.py`: rule 1 ("Use only the record"), `guard()` dropping any paragraph without a post, and the empty short cut before the call. Now the purpose, the Declaration and the Charter are sources D1 to D3 (`ask.DOCUMENTS`, from `principles.DOCUMENTS`), cited only when the question or an earlier one names a document, an article or a principle (`ask.names_document`); a paragraph citing one needs no post, but every quotation in it must be word for word in that document or the digest; such a question reaches the model even with an empty digest. Source line "Guiding document: {name}.", linked to `/about#udhr` (and `#purpose`, `#earth-charter`) while About is on. Rule 10: for "does X fit article Y", quote it, say where the solution's words meet it and where not, give the record's views, leave the verdict to the reader. Cases A15 to A17 in `tests/ask_cases.json`; live run of 28 October answered all three as intended.

**PR 44** (merge `e79db14`, deploy success, smoke 25 of 25): **site-wide wording.** Every page, page script and message a tester or John reads now says "database" where it said "record" (about 20 strings, the operator's guide, README, `04_interface.md`, the site sentence default in `config.py`, `.env.example` and `render.yaml`). Ask answers say "the database" too (rule 12, and `ask._clean` turns "the record" into "the database"). `tests/test_wording.py` keeps "the record" off every page and page script string. Left as they are: "your account's record" on the change of email page (an account's own record, not the shared one), John's "keeps the records" on About, back room error lines about single records ("Malformed record fields."), and "Ask the record" as the part's name in docs and code. "Card" was already gone from visible copy outside About; code names (`card.js`, `.card`, `CardPayload`) keep it.

Read back live: the write page's sentence says "a database everyone here shares" (no Render dashboard change was needed), `/ask` says "Ask the database", the form says "Added to the database".

## Render: a leftover Blueprint (resolved)

After PR 44 Render emailed "deploy failed" and "Blueprint Sync Failed". Not John's site: a Blueprint left in the builder's own Render workspace from before the move to John's account still watched `render.yaml`. PR 44 was the first change to that file since 14 September, so it synced, created a new service with none of the secret settings, and that service exited with "DEMO_PASSPHRASE is not set". Both were deleted the same day and read back in the dashboard (no Blueprints left). John's service (`srv-daqn2rek1f9s73codb9g`, deploys by Jkintree2 in GitHub's deployment list) was never affected. If a deploy by another account shows up in that list again, look for a Blueprint in that account.

## Open decisions for John

Nothing is left to build from John's 28 October emails; these wait on his answers.

**Reply sent 28 October, 12:03 UTC**, on the "Turning on Phase 3" thread (it also answers his separate "Turning on Phase 3, system prompt" mail). It tells John all three fixes are live and asks him two questions: should Ask give a yes or no for "is X consistent with article Y", and should the rest of the site say "language model" instead of "reading service". It also asks him to send wording changes rather than edit on GitHub. Next session: read his answer on that thread before changing `app/ask.py` or the copy.

* "Language model" beyond About: the rest of the site still says "reading service".
* For "is X consistent with article Y", Ask now quotes the article, sets the solution's words and the record's views beside it and leaves the verdict to the reader (rule 2: never one verdict). If John wants a yes or no, that is a change to rules 2 and 10 in `app/ask.py`.
* The new copy (the Ask page lead, the issue box line, the About paragraph on answers, the "Guiding document:" source line) awaits John's yes.
* John's edits on GitHub go live at once with no tests run; a PR, or sending the words, keeps main green.
