# 04. The 0.1 interface, screen by screen

> **Revised 5 September 2026 after REVIEW.md.** Changed: the gate names DeepSeek (M16); the sentence and site name come from environment variables (M15); anonymous clears the name and stores none (M7); a row of the most discussed issue chips sits above the text box (C7); the limit is 4,000 characters (m11); a cancel link during reading (m10); Post is gated on an empty card (M17); the feed shows sixty posts, no paging (table); the sort is labelled "Most people" and top-level rows show inclusive counts (m9, C7); evidence links carry `noopener` (M17); admin uses basic auth and shows the last reading-service error (table, M5); the "posting as" header line is cut (table); error and asleep page copy added (m2, C4).

> **Extended 4 October 2026 for Phase 1 (People and positions, SOW 0.2).** Added: sign in, entering a person, the invitation and password emails, accepting, password pages, your account, approve and oppose buttons, editing and deleting your own posts, search, tidying and the list of changes, and back room additions. See "Phase 1: people and positions" at the end. With `ACCOUNTS_ENABLED` unset the screens above are unchanged, except search on the Issues page, which works behind the passphrase too.

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

**The card.** Appears under the text box. Heading **client-facing**: "Here is what we found". When a name was too long and was shortened, a note under the heading reads, **client-facing**: "A long name was shortened to 300 characters. You can edit it." Then, in this order, each section editable:

* **Issue.** One text input with autocomplete from existing issue names, and below it a select "Part of" listing top-level issues, shorter first: names already on this form, then, when the page was opened for an issue, that issue's family, then all issues. The choices are grouped under **client-facing** headings: "On this form", "About <issue name>", "All issues". The empty choice reads, **client-facing**: "none, this is a new top level issue", or "none, this is already a top level issue" when the name matches an existing top level issue. A small badge beside the input says "existing" when the name matches a node already in the graph, "new" otherwise. Most posts have one issue; a "+ another issue" link adds a second row, and the card will not post with more than three. When the page was not opened from an issue chip or link (no "Already on record" panel above), a line under the issue rows reads, **client-facing**: "To add a sub-issue, write it here and choose the issue it is part of."
* **Solutions.** Zero or more rows. Each row: name input with autocomplete, a "for issue" select (defaults to the first issue) grouped the same shorter-first way ("On this form", "About <issue name>", "All issues"; empty choice **client-facing**: "Choose an issue"), and three radio buttons: "no position", "I approve this", "I oppose this". The model pre-selects a position only when the text states one. "+ add a solution" link.
* **Evidence.** Zero or more rows. Each row: name input with autocomplete, a link input (optional), a select "supports / refutes", and a select "about" listing the issues and solutions in the card plus existing nodes, grouped **client-facing**: "On this form", "About <issue name>", "All issues", "Solutions", "Evidence" (empty choice **client-facing**: "Choose what this is about"). "+ add evidence" link.
* **What this will add.** A read-only list of sentences generated live from the fields, in John's format, for example:

  > John Kintree claims Drug dealing problem
  > John Kintree proposes Decriminalize drug sales
  > Drug dealing problem has proposed Decriminalize drug sales

  Anonymous posts read "Anonymous claims …". A row is removed by clearing its name or pressing its "remove from this form" button, and the sentence list updates.
* **Buttons.** "Post" (primary; disabled while any solution lacks an issue, any evidence lacks a target, or both the text box and the card are empty) and "Discard". With a filled card and an empty text box the card's own sentences are posted as the statement, and this line appears at the top of the card, **client-facing**: "No statement written. The lines under "What this will add" will be posted as your statement." The "post it as a plain statement anyway" link needs text, so it is disabled while the box is empty.
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

The artifact he likes most ("The Commons") does persist a shared record between viewers through Claude's artifact storage, and it calls a model. What it cannot do is live outside claude.ai, hold a real graph, rank issues, or be owned and moved. The difference is ownership and the Issues view, not whether it shares.

## Phase 1: people and positions

Added 4 October 2026 at Gate 0 of Phase 1. With `ACCOUNTS_ENABLED` set, sign in replaces the passphrase, and every screen above needs a signed-in member. The look does not change: same palette and type, one column, 44 px touch targets, and every screen holds at 360 px. Everything in a quote is **client-facing**; John may replace any of it. `{name}` and similar mark values filled in by the site. The emails go from John Kintree <jkintree@gmail.com>, as plain text.

### Header

Signed in, the header links read "Write", "Issues", "Enter a person" and "Your account", and wrap onto a second line on a narrow phone. The sign in, accept and password pages show the site name only.

### Sign in (`/sign-in`)

Replaces Screen 1. The two paragraphs about the shared record and the reading service stay exactly as they read on the live passphrase page.

> **{SITE_NAME}**
>
> A closed test of a shared record of what people are claiming, proposing and citing.
>
> *(the two paragraphs from the passphrase page)*
>
> Email: [ input ]
> Password: [ input ]
> [ Sign in ]
>
> Forgot your password?
>
> New here? Someone already taking part enters you, and you get an email from John Kintree with a link to choose your password.

Messages:

> That email and password did not match. Check them and try again.

> Too many tries. Please wait a minute and try again.

> You are signed out.

When a page finds the member signed out (the card, a preview, Post, an Approve or Oppose button):

> Please sign in again.

Any form posted from another site is refused with:

> Please reload the page and try again.

The same "did not match" line answers a wrong password, an unknown email, an invitation not yet accepted and an account that is switched off, so the page never says who is taking part.

### Writing with an account

The "Your name" field goes; posts are credited to the account's name. The "Post anonymously" box stays, with a line under it:

> Your name is not shown to others. The record still knows the post is yours, so you can edit or delete it later.

The card's footnote is unchanged ("credited to {name}" or "listed as Anonymous").

### Enter a person (`/people`)

> **Enter a person**
>
> Enter someone who has already agreed to take part. We will email them from John Kintree's address with a link to accept and choose their own password. They will see your name as the person who entered them.
>
> Name: [ input ]
> Email: [ input ]
> Country: [ input ]
> Postal code: [ input ]
> How do you know them? [ Choose one / Family / Neighbor / Friend / Work / School / Health / Organization ]
> [ ] This person has agreed to be entered
> [ Enter and send the invitation ]

Messages:

> Please fill in every field.

> Please enter only someone who has agreed, and tick the box to say so.

> That email address does not look complete. Please check it.

> Someone with that email address has already been entered.

> {name} is entered. The invitation is on its way to {email}. The link works for 14 days.

> {name} is entered, but the invitation email did not go. Please try again in a minute.
> [ Send the invitation again ]

When the form is sent twice in a row (a double tap), the second answer promises nothing, since the first email may not have gone; the list below shows the truth:

> {name} is entered. If the invitation does not arrive, use Send the invitation again in the list below.

> Too many tries. Please wait a minute and try again.

When "Send the invitation again" has reached the same address too often in the last hour (the same limit as "Forgot your password?"):

> Too many emails to that address in the last hour. Please try again later.

Below the form, the people this member has entered, newest first:

> **People you have entered**
>
> {name} · {relationship} · entered {4 October}
> joined {6 October}
> *or* invited, not accepted yet [ Send the invitation again ] [ Withdraw ]
> *or* invitation expired [ Send the invitation again ] [ Withdraw ]
> *or* switched off
>
> If an email address was mistyped, withdraw the entry and enter the person again.

> You have not entered anyone yet.

Withdraw asks first:

> Withdraw the entry for {name}? Their link stops working and the details you entered are removed.
> [ Withdraw ] [ Keep it ]

After either button:

> A new invitation is on its way to {email}. The earlier link no longer works.

> The entry for {name} is withdrawn.

### The invitation email

> **Subject:** Your invitation to {SITE_NAME}
>
> Hello {name},
>
> Thank you for agreeing to take part in {SITE_NAME}, a closed test of a shared record of what people are claiming, proposing and citing.
>
> Entered by: {inviter}
> How you know each other: {relationship}
>
> To accept and choose your own password, open this link:
> {SITE_URL}/accept/{link}
>
> The link works once, for 14 days. If it has expired, ask {inviter} to send a new one. If you were not expecting this email, you can ignore it.
>
> If you have a question, reply to this email.
>
> John Kintree

Note for the builder: `{relationship}` starts with a capital letter when it stands alone after a label.

John's own first email has no "Entered by" lines. `make_admin.py` makes his account and sends nothing; the email goes when he first uses "Forgot your password?" on the site, since his account is not yet accepted (the same goes for any invitation sent again to his account before he accepts):

> **Subject:** Choose your password for {SITE_NAME}
>
> Hello {name},
>
> Your account on {SITE_NAME} is ready. To choose your password, open this link:
> {SITE_URL}/accept/{link}
>
> The link works once, for 14 days.

### Accepting (`/accept/{link}`)

> **Welcome to {SITE_NAME}**
>
> {inviter} entered you. Please check your details and choose a password.
>
> Name: [ {name} ]
> Email: {email}
> Country: [ {country} ]
> Postal code: [ {postal code} ]
> How you know {inviter}: {relationship}
>
> Choose a password: [ input ]
> At least 10 characters. Your browser may offer a strong password and remember it for you.
> Type it again: [ input ]
>
> *(the two paragraphs from the passphrase page)*
>
> [ Accept and sign in ]

For John's own account the heading is "Choose your password" and the "entered you" and "How you know" lines are left out. Messages:

> Please fill in your name.

> Please use at least 10 characters for your password.

> The two passwords are not the same.

After accepting, the write page opens with:

> Welcome, {name}. You are signed in.

When the link cannot be used, one page with one of these:

> This invitation has expired. Please ask {inviter} to send a new one.
> [ Ask for a new link ]

The button opens "Forgot your password?", which sends a person not yet accepted their invitation again (D4). John's own first link has no inviter; when it expires it shows "This link has expired. You can ask for a new one." with "Forgot your password?".

> This link has expired. You can ask for a new one.
> [ Forgot your password? ]

> This link no longer works. It may have been used already, or a newer one sent. If you have chosen a password, sign in. If not, use the most recent email, or ask the person who entered you to send the invitation again.
> [ Sign in ]

> You are signed in as {name}. This link is for someone else.
> [ Sign out and continue ]

### Forgot your password (`/forgot-password`)

> **Forgot your password**
>
> Enter the email address you were invited with, and we will send you a link to choose a password.
>
> Email: [ input ]
> [ Send the link ]
>
> Sign in

Afterwards, whatever was typed (the "Sign in" link stays under it):

> If that address belongs to someone taking part, an email with a link is on its way.

Someone who was entered but has not accepted yet gets the invitation email again, with a fresh link, instead of the password email. Nobody else gets anything.

> Too many tries. Please wait a minute and try again.

### The password email

> **Subject:** Choose a new password for {SITE_NAME}
>
> Hello {name},
>
> Someone asked for a new password for your account on {SITE_NAME}. If it was you, open this link to choose one:
> {SITE_URL}/reset/{link}
>
> The link works once, for one hour. Your current password keeps working until you choose a new one.
>
> If it was not you, you can ignore this email.
>
> John Kintree

### Choose a new password (`/reset/{link}`)

> **Choose a new password**
>
> Email: {email}
> New password: [ input ]
> Type it again: [ input ]
> [ Save the new password ]

Then the write page opens with:

> Your new password is saved. You are signed out everywhere else.

The same length and "not the same" messages as accepting, and the same page when the link cannot be used.

### Your account (`/account`)

> **Your account**
>
> {name} · {email}
> Entered by {inviter} ({relationship}) on {4 October 2026}.
>
> **Change your password**
> Email: {email}
> Current password: [ input ]
> New password: [ input ]
> Type it again: [ input ]
> [ Change password ]
>
> [ Sign out ]

> That is not your current password.

> Your password is changed. You are signed out everywhere else.

John's account leaves out the "Entered by" line.

### Approve and oppose on the issue page

Under "Proposed solutions", one line:

> Listed by approvals minus oppositions.

Each solution keeps its counts line ("proposed by 2 · approved by 3 · opposed by 1") and gains two buttons, "Approve" and "Oppose". The one the member holds is highlighted, with a line under the buttons:

> You approve this. Press Approve again to withdraw.

> You oppose this. Press Oppose again to withdraw.

Pressing the other button switches. The counts update in place; without JavaScript the buttons are forms and the page reloads at the same solution. On failure, under the buttons (without JavaScript too, after the page reloads at the solution):

> Your position was not saved. Please try again.

With `ACCOUNTS_ENABLED` unset there are no buttons and no "Listed by" line, and the solutions keep today's order, so the issue page reads exactly as before.

The "Already on record" panel above the write box keeps its three choices, which add a row to the card as before; a choice made there survives "Read my statement" (GitHub issue 8).

### Your own posts

On a member's own posts, after the byline: "Edit" and "Delete". An edited post's byline reads "{name} · 2 hours ago · edited".

Delete asks first:

> Delete this post? What it claimed, proposed and cited goes, unless something else still uses it. Approvals and oppositions stay; you can change them on the issue page.
> [ Delete ] [ Keep it ]

> Your post is deleted.

Edit opens the write page with the statement and the card filled from the post as the record holds it now (an issue renamed or merged since shows under its new name). "Read my statement" and "Skip the reading" are hidden while editing. Without JavaScript the page shows the statement and a "Save changes" button, which saves the new words with the post's card as it is. The card's heading reads "Edit your post", its buttons "Save changes" and "Cancel", and a line at the top says:

> Saving replaces what this post added. It keeps the name or Anonymous it was first posted with. Removing a position here does not withdraw it; use the buttons on the issue page.

Note for the builder: while editing, the reading buttons and the "post it as a plain statement anyway" button are hidden; the card is the edit.

> Your post is updated.

> You can change only your own posts.

> That post is no longer here.

### Search on the Issues page

Above "Sort by":

> Search: [ input, placeholder "A word or two, for example: housing" ] [ Search ]

Results replace the list, in groups that have results, each item linking to its issue page; posts look as in the feed:

> **Results for {words}**
> Issues · Solutions · Evidence · Posts
> Show all issues

Every word must match, as written or as the start of a word, so a second word narrows the results.

> Nothing matches {words}. Try another word, or fewer words.

### Tidying an issue (John only)

At the foot of an issue page, seen only by an admin account:

> **Tidy this issue**
>
> New name: [ {name} ] [ Rename ]
>
> Make it part of: [ none, make it a top level issue / top level issues ] [ Move ]
> *or, when other issues are part of it:* Other issues are part of this one, so it stays at the top level.
>
> Merge another issue into this one: [ Choose an issue / every other issue ] [ Merge ]

Merge asks first:

> Merge {other} into {this}? Its claims, solutions, evidence and the issues that are part of it move here, and {other} is removed. This cannot be undone. It is recorded in the list of changes.
> [ Merge ] [ Cancel ]

Messages:

> Renamed.

> Moved.

> Merged. Everything about {other} is now here.

> Another issue already has that name. To join the two, use Merge.

> That name is too short.

> An issue cannot be part of itself.

> That issue is part of another issue, so nothing can be part of it.

> Choose a different issue to merge.

### Changes to the issues (`/changes`)

Linked at the foot of the Issues page as "Changes to the issues"; every member can read it.

> **Changes to the issues**
>
> Every move, rename and merge, newest first.
>
> {4 October 2026, 14:02 UTC} · {name} renamed {old name} to {new name}
> {date} · {name} moved {issue} under {parent}
> {date} · {name} made {issue} a top level issue
> {date} · {name} merged {other} into {issue}

> No changes yet.

### Back room additions

A "People" section listing every account:

> {name} · {email} · entered by {inviter} ({relationship}) on {date} · joined {date}
> *or* invited, not accepted yet *or* invitation expired *or* switched off
> *or, for John's own account:* first account

Buttons, as they apply: "Send the invitation again", "Send a password link", "Withdraw", "Switch off", "Switch on". Switch off asks first:

> Switch off {name}? They can no longer sign in. Their posts stay.

Withdraw asks first too, because in the back room John withdraws entries that other members made:

> Withdraw the entry for {name}? Their link stops working and the details entered for them are removed.
> [ Withdraw ]

Notices:

> Invitation sent again.

> Password link sent.

> Entry withdrawn.

> Switched off.

> Switched on.

> The email did not go. Please try again in a minute.

> Too many emails to that address in the last hour. Please try again later.

The line above appears when a back room email would pass the per address limit that "Forgot your password?" and "Send the invitation again" also use; the back room has no per minute limit, since only John can reach it. John's own row reads "{name} · {email} · first account" followed by its state, because nobody entered him; it offers neither Withdraw nor Switch off. Switch off is offered only to accounts that have joined; someone not yet accepted is withdrawn instead.

A "Sending email" line, like the reading service line:

> No problems recorded.

> The last email could not be sent, on {4 October 2026, 14:02 UTC}. If this keeps happening, Google needs John's permission again.

When the time of the failure is not known:

> The last email could not be sent. If this keeps happening, Google needs John's permission again.

"Reset to seed" now reads:

> This deletes every post and restores the seed statements. Accounts, and who entered whom, stay. Download a copy first if you want to keep the current record.

### Phone and browser details (not client-facing)

* Sign in: `type="email" autocomplete="username" autocapitalize="none" spellcheck="false"` and `autocomplete="current-password"`. Accept, reset and change password: the email is present as a read-only `autocomplete="username"` field, and both new password fields use `autocomplete="new-password" minlength="10"`, so the phone or browser offers a strong password and saves it under the right email.
* Enter a person: every field `autocomplete="off"`, so the browser does not fill in the member's own name, email or address for someone else. Email `type="email"`.
* Accept, reset, sign in and account pages send `Cache-Control: no-store` and `Referrer-Policy: same-origin`: a link's address never goes to another site, and the page's own forms still carry this site's `Origin` (under `no-referrer` a browser sends `Origin: null` with every form, which the same-site check must refuse). The link pages load nothing from another site.
* The request log writes `/accept/…` and `/reset/…` with the link cut out. A link never appears in a log at any level.
* Email links are built from `SITE_URL`, never from the request's host.
* New scripts and styles sit in `app/static/`, so the `?v=` hash from fe88bd4 covers them.
* Every form works without JavaScript; a mutation is a POST, refused unless it comes from this site.
