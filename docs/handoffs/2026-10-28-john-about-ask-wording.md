# Handoff, 28 October 2026: John's requests after switching Phase 3 on

John's two emails of 28 October ("Turning on Phase 3" and "Turning on Phase 3, system prompt") ask for three things. Phase 3 is switched on in Render (Ask and About are in the live menu).

## Shipped

**PR 42** (merge `bc8216a`): About keeps John's own wording and shows the whole menu.

* John edited `about.html` on main himself (3adfef8, fe80d90: "shared database", "form", "language model"). Those commits deployed but failed four tests in `tests/test_about.py`. PR 42 keeps his words, finishes the three spots still saying reading service, card and record, changes the line shown with no key to "No language model is set up…", and brings `04_interface.md` and the tests in line. CLAUDE.md rule 5 now allows "language model" on About only.
* About opens without signing in, so `require_access` never looked for the member and the menu dropped Enter a person, My statements and My account. `routes_about.about` now calls `current_member(request)` first.

**Ask uses the guiding documents** (the PR that carries this note, branch `ask-guiding-documents`; not merged when written). John asked "what does the UDHR say about privacy" and whether a global carbon tax is consistent with Earth Charter 7d; Ask said the record holds nothing. Causes in `app/ask.py`: rule 1 ("Use only the record"), `guard()` dropping any paragraph without a post, and the empty short cut before the call. Now the purpose, the Declaration and the Charter are sources D1 to D3 (`ask.DOCUMENTS`, from `principles.DOCUMENTS`), cited only when the question or an earlier one names a document, an article or a principle (`ask.names_document`); a paragraph citing one needs no post, but every quotation in it must be word for word in that document or the digest; such a question reaches the model even with an empty digest. Source line "Guiding document: {name}.", linked to `/about#udhr` (and `#purpose`, `#earth-charter`) while About is on. Rule 10: for "does X fit article Y", quote it, say where the solution's words meet it and where not, give the record's views, leave the verdict to the reader. Cases A15 to A17 in `tests/ask_cases.json`; live run of 28 October answered all three as intended.

## Left to do

1. **"Database" for record and "form" for card, site wide.** About is done. The rest: templates, `app/static/*.js` strings, client-facing constants in `app/*.py` (for example `ask.EMPTY`), the Ask rules' word for what it reads, "Ask the record" titles, `04_interface.md`, `docs/operators-guide.md`, the tests and the `tests/fixtures/pages_before_phase3/` pages. Copy only: file, class and function names (`card.js`, `.card`, `CardPayload`) stay.

## Open decisions for John

* "Language model" beyond About: the rest of the site still says "reading service".
* For "is X consistent with article Y", Ask now quotes the article, sets the solution's words and the record's views beside it and leaves the verdict to the reader (rule 2: never one verdict). If John wants a yes or no, that is a change to rules 2 and 10 in `app/ask.py`.
* The new copy (the Ask page lead, the issue box line, the About paragraph on answers, the "Guiding document:" source line) awaits John's yes.
* John's edits on GitHub go live at once with no tests run; a PR, or sending the words, keeps main green.
