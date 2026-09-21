# 04. The 0.1 interface, screen by screen

> **Revised 5 September 2026 after REVIEW.md.** Changed: the gate names DeepSeek (M16); the sentence and site name come from environment variables (M15); anonymous clears the name and stores none (M7); a row of the most discussed issue chips sits above the text box (C7); the limit is 4,000 characters (m11); a cancel link during reading (m10); Post is gated on an empty card (M17); the feed shows sixty posts, no paging (table); the sort is labelled "Most people" and top-level rows show inclusive counts (m9, C7); evidence links carry `noopener` (M17); admin uses basic auth and shows the last reading-service error (table, M5); the "posting as" header line is cut (table); error and asleep page copy added (m2, C4).

Five screens, one CSS file, one JavaScript file. Look taken from John's two Claude prototypes: the paper palette and serif statements of the second ("The Commons"), the sidebar-free single column and the plain-sentence relationships of both. Anything marked **client-facing** is copy John will read; it avoids dashes and machine phrasing, and John may replace any of it.

## Look

From the artifact John likes most, verbatim values:

* Background paper `#F3EFE3`, secondary paper `#EAE3D2`, ink `#241F1A`, soft ink `#6B6252`, rule lines `#D8CFB8`, accent green `#4C7A6F` (hover `#375A52`), input background `#FDFCF8`.
* Node colours for chips and dots: Person `#3B5BA0`, Issue `#B8863B`, Evidence `#4C7A6F`, Solution `#A6473C`.
* Title and quoted statements in a serif system stack (`"Iowan Old Style", "Palatino Linotype", Georgia, serif`); everything else in the system sans stack. No web fonts, no icon library.
* One centred column, max width 640 px, 16 px gutter, 44 px minimum touch targets, inputs 40 px tall. Mobile first; the layout must hold at 360 px.
* No sidebar, no tabs. Navigation is two links in a small header: "Write" and "Issues" (the Issues link appears in Session 2). The header shows the site name from `SITE_NAME`.

## Screen 1: the passphrase gate (`/enter`)

Shown for any URL when the passphrase cookie is missing or stale. One card, centred.

**client-facing**

> **Open Collective Intelligence**
>
> A closed test of a shared record of what people are claiming, proposing and citing.
>
> Everything written here is merged into a shared record that other testers can read. It is not a private conversation. Use it for things you are happy to say in public.
>
> A reading service run by an outside company, DeepSeek, reads what you write to fill in the form. Do not write anything you would not want a company to store.
>
> Passphrase: [ input ]   [ Enter ]

On a wrong passphrase, same page with: "That passphrase did not match. Check the message from John and try again." A one-second delay before the form re-enables. On success, a cookie for thirty days and a redirect to the page the tester asked for.

If the server has no passphrase configured it refuses to start and logs why, so the demo can never be accidentally open.

## Screen 2: write and feed (`/`)

Top to bottom:

**The sentence.** One line in the serif face under the site name, read from `SITE_SENTENCE` so John can change it on Render's Environment tab without touching code. John supplies it (see `QUESTIONS.md`). Default draft, **client-facing**:

> Write what you think about an issue that matters to you. We will pull out the issue, your claim, any evidence and any solution, show you what we found, and add it to a record everyone here shares.

**Name row.** Label "Your name", text input, placeholder "optional". Beside it a checkbox "Post anonymously". Ticking it clears and greys the name field, and the post is stored with no name at all. The name is remembered in a cookie only when a post is made under it, and prefilled next time; anonymous is never remembered, it is a choice per post.

**Issues people are writing about.** One line of up to five chips, the most discussed issues, each linking to its page (Session 2) and, from Session 3, pre-filling the card's issue row so a tester adds to a conversation instead of starting a new one. Label **client-facing**: "People are writing about:".

**Already on record.** When the page is opened from an issue chip or link (`/?issue=<key>`), a panel appears between the chips row and the text box, showing what the record already holds for that issue, so a tester adds to it instead of repeating it. It is absent when there is no `issue` in the address or the issue is unknown. All **client-facing**:

> Already on record for <issue name>
> Part of <parent issue name>
> Sub-issues
> Proposed solutions
> approved by <n> · opposed by <n>
> Your position
> no position
> I approve this
> I oppose this
> No solutions proposed yet.
> Evidence
> No evidence attached to the issue itself yet.
> Open the full page for this issue
> To add a sub-issue, write it as an issue below and choose this issue under "Part of".

Each proposed solution carries the same three position choices as a card row. Choosing "I approve this" or "I oppose this" opens the card and adds that solution as a row, already tied to this issue and with the position set, so the tester can post it. Choosing "no position" again removes the row.

When the choice cannot be taken the panel puts the solution back to "no position" and says why, in the card's message line when the card is open and in the line under the buttons otherwise. **Client-facing**:

> The form already holds five solutions. Remove one from the form to add this.
> Please wait for the reading to finish, then choose a position.

**Text box.** Label **client-facing**: "A claim, a piece of evidence, or a proposed solution". Four rows, grows with content, hard limit 4,000 characters with a counter that appears after 3,500. Placeholder **client-facing**: "For example: The problem of drug dealing could be reduced by decriminalizing the sale of those drugs."

**Buttons.** "Dictate" with a microphone glyph (hidden when the browser has no speech recognition). "Read my statement" as the primary button, disabled until the box has text. A third, quieter link: "Skip the reading and fill in the form myself", which opens an empty card and works with an empty box. Under the buttons, **client-facing**: "You can leave the box empty, fill in the form yourself, and post that."

**Dictation.** Press Dictate, the button turns red and reads "Listening… press to stop". Recognised text is appended to the box as it arrives. Press again to stop. The tester edits the text as normal before pressing Read my statement. Nothing is sent anywhere until they do.

**Reading state.** The button reads "Reading…" and the box locks, with a link "Stop and fill it in myself" shown from the first second (it abandons the request and opens the empty card). After eight seconds a line appears below: "Still reading. This can take up to half a minute." After twenty-five seconds the request is abandoned and the card opens empty with the message below.

**The card.** Appears under the text box. Heading **client-facing**: "Here is what we found". Then, in this order, each section editable:

* **Issue.** One text input with autocomplete from existing issue names, and below it a select "Part of" listing top-level issues plus "none, this is a new top-level issue". A small badge beside the input says "existing" when the name matches a node already in the graph, "new" otherwise. Most posts have one issue; a "+ another issue" link adds a second row, and the card will not post with more than three. When the page was not opened from an issue chip or link (no "Already on record" panel above), a line under the issue rows reads, **client-facing**: "To add a sub-issue, write it here and choose the issue it is part of."
* **Solutions.** Zero or more rows. Each row: name input with autocomplete, a "for issue" select (defaults to the first issue), and three radio buttons: "no position", "I approve this", "I oppose this". The model pre-selects a position only when the text states one. "+ add a solution" link.
* **Evidence.** Zero or more rows. Each row: name input with autocomplete, a link input (optional), a select "supports / refutes", and a select "about" listing the issues and solutions in the card plus existing nodes. "+ add evidence" link.
* **What this will add.** A read-only list of sentences generated live from the fields, in John's format, for example:

  > John Kintree claims Drug dealing problem
  > John Kintree proposes Decriminalize drug sales
  > Drug dealing problem has proposed Decriminalize drug sales

  Anonymous posts read "Anonymous claims …". A row is removed by clearing its name or pressing its "remove from this form" button, and the sentence list updates.
* **Buttons.** "Post" (primary; disabled while any solution lacks an issue, any evidence lacks a target, or both the text box and the card are empty) and "Discard". With a filled card and an empty text box the card's own sentences are posted as the statement, and this line appears at the top of the card, **client-facing**: "No statement written. The lines under \"What this will add\" will be posted as your statement." The "post it as a plain statement anyway" link needs text, so it is disabled while the box is empty.
* **Footnote** **client-facing**: "Posting adds this to the shared record, credited to John Kintree." or "… listed as Anonymous."

**When the model found nothing.** The card opens with all sections empty and this line at the top, **client-facing**: "We could not find an issue, a claim, evidence or a solution in that. If you meant to make one, fill in the form below, or change the text and read it again." The Post button is disabled until the tester types into a field or clicks a second link, "post it as a plain statement anyway", which posts the text into the feed with no structure. Greetings and tests then stay out of the feed unless someone means it.

**When the model is slow or down.** Same empty card, **client-facing**: "The reading service is not answering right now. You can fill in the form by hand, or try again in a minute." A "Try again" link re-sends the same text.

**When the model returns something wrong.** The tester edits or removes it. That is the whole design; there is no second model call to fix the first.

**When the text is too long or not English.** Before any model call, over 4,000 characters: "That is longer than this demo can read at once. Please shorten it to a few paragraphs." If the model reports the text is not mostly English: "This demo reads English only for now."

**After Post.** The card and text box clear, a green line reads "Added to the record" for a few seconds, and the new post appears at the top of the feed without a page reload (the feed section is re-fetched).

**A second post too soon after the first from the same tester.** The post is refused, **client-facing**: "Please wait a moment before posting again." (C12)

**The feed.** Heading "Recent posts". The sixty most recent; paging is on the after list. Each post:

* First line: display name or "Anonymous", a dot, relative time ("2 hours ago"). Seed posts carry a small "seed" tag.
* The statement, in the serif face.
* Chips, one per distinct node the post touched, coloured by type, each an issue chip linking to that issue's page (solution and evidence chips link to the issue they belong to).
* A "show what was added" link that expands the sentence list for the post.

Empty feed **client-facing**: "Nothing here yet. Be the first to write something."

## Screen 3: Issues (`/issues`)

Heading "Issues". Under it a three-way control labelled "Sort" for assistive technology, with a visible **client-facing** label "Sort by" beside the choices: "Most people", "Most recent", "Most evidence". The chosen sort is in the URL (`?sort=people|recent|evidence`) so it can be linked.

Each top-level issue is a card: the name (a link), then one line of counts, then its sub-issues indented, each with its own count line. A top-level issue is ranked on its whole family, so a conversation with five sub-issues sits above a one-line post. Count line for a sub-issue or an issue without children: "3 people · 5 claims · 2 solutions · 4 pieces of evidence". For a top-level issue with sub-issues: "3 people · 13 claims in total · 1 claim on the issue itself · 4 solutions · 14 pieces of evidence". Numbers are plain; no bars, no percentages.

Empty state **client-facing**: "No issues yet. Write something on the front page and it will appear here."

## Screen 4: issue detail (`/issues/<key>`)

* Breadcrumb: "Issues › Need for world government › Security Council veto" when the issue is a sub-issue.
* Name as the page title. Under it: "Claimed by 3 people (5 claims)" and the names, anonymous ones shown as "Anonymous".
* "Sub-issues" list if any, each linking.
* "Proposed solutions". Each solution: name, then "proposed by 2 · approved by 3 · opposed by 1", then its evidence as two short lists, "Supported by" and "Refuted by", each item a name and, if present, a link that opens in a new tab with `rel="noopener noreferrer"`.
* "Evidence about this issue". Same two lists for evidence attached to the issue directly.
* "Posts about this issue". The feed component filtered to posts that touched this issue or, on a parent, any of its sub-issues.
* A "Write about this issue" button (Session 3) that returns to the front page with the issue and its parent prefilled in the card. Cheap and it gives the conversation a thread without building threads.

## Screen 5: admin (`/admin`)

Not linked from anywhere. Protected by HTTP basic auth (any username, the admin token as the password; the browser remembers it). Shows node and relationship counts, one line for the last reading-service error ("Reading service: insufficient balance since 3 October", or "none"), and three buttons:

* "Reload seed": re-runs the seed merge without deleting anything. Safe.
* "Reset to seed": deletes everything and reloads the seed, behind a confirm that requires typing RESET.
* "Download a copy": returns all nodes and relationships as one JSON file, for John to keep.

And a list of the last fifty posts with a "delete" link each (removes the post, the claim, submit, propose, supports and refutes edges it created, and any issue, solution or evidence that this post alone created; shared edges such as a solution's link to its issue stay).

## Copy rules for every screen

* John's node words only: issue, claim, evidence, solution, person. Never node, edge, graph, Cypher, model name, extraction, entity.
* The model is "the reading service" or just "we" in copy. It is never named.
* Sentences in the card use the display name, a lowercase verb, the node name, nothing else.
* No exclamation marks. No "oops". Errors say what happened and what to do next.
* Numbers are raw counts of people and posts. Nothing is a percentage, a score or a trend.

## Two more pages

**Error** (any unhandled failure), **client-facing**: "Something went wrong. Please try again in a minute."

**Asleep** (the database is paused), **client-facing**: "The record is asleep. John needs to press Play in the Neo4j console, and it wakes up in a few minutes." With the console link for John's benefit. The app keeps running while the database is paused; only this page is served.

## Note on John's artifact

The artifact he likes most ("The Commons") does persist a shared record between viewers through Claude's artifact storage, and it calls a model. What it cannot do is live outside claude.ai, hold a real graph, rank issues, or be owned and moved. The difference to describe to John, if it comes up, is ownership and the Issues view, not "it did not share". (Eston told him it has no shared backend on 2 September; John accepted it and moved on. No need to correct it unless he asks.)
