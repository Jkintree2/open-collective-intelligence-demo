# 04. The 0.1 interface, screen by screen

> **Revised 5 September 2026 after REVIEW.md.** Changed: the gate names DeepSeek (M16); the sentence and site name come from environment variables (M15); anonymous clears the name and stores none (M7); a row of the most discussed issue chips sits above the text box (C7); the limit is 4,000 characters (m11); a cancel link during reading (m10); Post is gated on an empty card (M17); the feed shows sixty posts, no paging (table); the sort is labelled "Most people" and top-level rows show inclusive counts (m9, C7); evidence links carry `noopener` (M17); admin uses basic auth and shows the last reading-service error (table, M5); the "posting as" header line is cut (table); error and asleep page copy added (m2, C4).

> **Extended 4 October 2026 for Phase 1 (People and positions, SOW 0.2).** Added: sign in, entering a person, the invitation and password emails, accepting, password pages, your account, approve and oppose buttons, editing and deleting your own posts, search, tidying and the list of changes, and back room additions. See "Phase 1: people and positions" at the end. With `ACCOUNTS_ENABLED` unset the screens above are unchanged, except search on the Issues page, which works behind the passphrase too.

> **Extended 26 October 2026 for Phase 3 (Talking to the record).** Added: drafts for Ask the record, follow-up questions on the card, a place on each post, issues near me and the About page, all for John's yes on 28 October. See "Phase 3: talking to the record" at the end. Each shows only with its switch set.

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
> An invitation-only test of a shared database of issues, solutions, and evidence that people are claiming, proposing, submitting.
>
> Everything written here is merged into a free instance of the Neo4j Aura graph database that other testers can read. It is not a private conversation. Use it for things you are happy to say in public.
>
> A language model run by an outside company, DeepSeek, reads what you write when you enter statements. In the future, we would like to provide the option of using a small language model that runs on personal computers such as smartphones.
>
> Passphrase: [ input ]   [ Enter ]

On a wrong passphrase, same page with: "That passphrase did not match. Check the message from John and try again." A one-second delay before the form re-enables. On success, a cookie for thirty days and a redirect to the page the tester asked for.

If the server has no passphrase configured it refuses to start and logs why, so the demo can never be accidentally open.

## Screen 2: write and feed (`/`)

Top to bottom:

**The sentence.** One line in the serif face under the site name, read from `SITE_SENTENCE` so John can change it on Render's Environment tab without touching code. John supplies it (see `QUESTIONS.md`). Default draft, **client-facing**:

> Write what you think about an issue that matters to you. We will pull out the issue, your claim, any evidence and any solution, show you what we found, and add it to a record everyone here shares.

**Name row.** Label "Your name", text input, placeholder "optional". Beside it a checkbox "Post anonymously". Ticking it clears and greys the name field, and the post is stored with no name at all. The name is remembered in a cookie only when a post is made under it, and prefilled next time; anonymous is never remembered, it is a choice per post.

**Issues people are writing about.** Removed from the write page in the Phase 1 revision round (John and Beth, 17 and 18 October 2026). Testers see what others write about in the recent statements below the form and on the Issues page.

**Already on record.** When the page is opened from an issue chip or link (`/?issue=<key>`), a panel appears between the sentence and the text box, showing what the record already holds for that issue, so a tester adds to it instead of repeating it. It is absent when there is no `issue` in the address or the issue is unknown. All **client-facing**:

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

**Text box.** Label **client-facing**: "Write or dictate your statement in the box." (John's wording, 17 October 2026), with the Dictate button on the same line. The box is empty, with no example text, and the cursor is in it when the write page opens (not on the edit page). Four rows, grows with content, hard limit 4,000 characters with a counter that appears after 3,500.

**Buttons.** "Dictate" with a microphone glyph, beside the label (hidden when the browser has no speech recognition). With an account, the "Post anonymously" box and its line sit between the text box and "Read my statement". "Read my statement" is the primary button, disabled until the box has text. There is no button to skip the reading: when the reading service is slow or down, the card opens empty to fill in by hand.

**Dictation.** Press Dictate, the button turns red and reads "Listening… press to stop". Recognised text is appended to the box as it arrives. Press again to stop. The tester edits the text as normal before pressing Read my statement. Nothing is sent anywhere until they do.

**Reading state.** The button reads "Reading…" and the box locks, with a link "Stop and fill it in myself" shown from the first second (it abandons the request and opens the empty card). After eight seconds a line appears below: "Still reading. This can take up to half a minute." After twenty-five seconds the request is abandoned and the card opens empty with the message below.

**The card.** Appears under the text box. Heading **client-facing**: "Here is what we found". When a name was too long and was shortened, a note under the heading reads, **client-facing**: "A long name was shortened to 300 characters. You can edit it." Then, in this order, each section editable:

* **Issue.** One text input with autocomplete from existing issue names, and below it a select "Part of" listing top-level issues, shorter first: names already on this form, then, when the page was opened for an issue, that issue's family, then all issues. The choices are grouped under **client-facing** headings: "On this form", "About <issue name>", "All issues". The empty choice reads, **client-facing**: "none, this is a new top level issue", or "none, this is already a top level issue" when the name matches an existing top level issue. A small badge beside the input says "existing" when the name matches a node already in the graph, "new" otherwise. Since 24 October 2026 (John's email of that day) a line under the row also says so, **client-facing**: "This issue is already in the record." Most posts have one issue; a "+ another issue" link adds a second row, and the card will not post with more than three. When the page was not opened from an issue chip or link (no "Already on record" panel above), a line under the issue rows reads, **client-facing**: "To add a sub-issue, write it here and choose the issue it is part of."
* **Solutions.** Zero or more rows. Each row: name input with autocomplete, a "for issue" select (defaults to the first issue) grouped the same shorter-first way ("On this form", "About <issue name>", "All issues"; empty choice **client-facing**: "Choose an issue"), and three radio buttons: "no position", "I approve this", "I oppose this". The model pre-selects a position only when the text states one. "+ add a solution" link.
* **Evidence.** Zero or more rows. Each row: name input with autocomplete, a link input (optional), a select "supports / refutes", and a select "claim about" (John, 23 October 2026; "about" before) listing the issues and solutions in the card plus existing nodes, grouped **client-facing**: "On this form", "About <issue name>", "All issues", "Solutions", "Evidence" (empty choice **client-facing**: "Choose what this is about"). "+ add evidence" link. The badge beside the name reads "existing" when the name is already in the record, and since 24 October 2026 also when the link is: the same link counts as the same evidence (the scheme, a leading www., a trailing slash, the fragment and utm_ parameters do not count; the rest of the address does), so a row whose link the record already holds takes that piece of evidence's name and shows one line under the row, **client-facing**: "This evidence is already in the record." The writer may still change the name; a name already in the record then decides as before, and any other name still joins the evidence the link belongs to.
* **What this will add.** A read-only list of sentences generated live from the fields, in John's format, for example:

  > John Kintree claims Drug dealing problem
  > John Kintree proposes solution Decriminalize drug sales
  > Drug dealing problem has proposed Decriminalize drug sales
  > John Kintree submits evidence Hansen paper on accelerated global warming
  > Hansen paper on accelerated global warming supports issue of Drug dealing problem

  Since 23 October 2026 (John's email of that day) the verbs are "proposes solution", "submits evidence" and "supports issue of" / "solution of" / "evidence of" (likewise refutes); the feed's sentences under a post read the same way. When the issue is already in the record its line reads "{name} claims about existing issue {issue}" (John, 24 October 2026; from 23 to 24 October the line was left out whenever the card added anything else). Anonymous posts read "Anonymous claims …". A row is removed by clearing its name or pressing its "remove from this form" button, and the sentence list updates.
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

Signed in, the header links read "Write", "Issues", "Enter a person", "My statements" and "My account" (John, 22 October 2026: "My" instead of "Your", and My statements as its own menu item), and wrap onto a second line on a narrow phone. The sign in, accept and password pages show the site name only.

### Sign in (`/sign-in`)

Replaces Screen 1. The two paragraphs about the shared record and the reading service stay exactly as they read on the live passphrase page.

> **{SITE_NAME}**
>
> An invitation-only test of a shared database of issues, solutions, and evidence that people are claiming, proposing, and submitting.
>
> *(the two paragraphs from the passphrase page)*
>
> Email: [ input ]
> Password: [ input ]
> [ Sign in ]
>
> Forgot your password?
>
> New here? Someone already taking part must enter you, and you get an email from John Kintree with a link to choose your password.

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

The "Your name" field goes; posts are credited to the account's name. The "Post anonymously" box moves to just above "Read my statement", with a line under it:

> Your name is not shown to others. The record still knows the post is yours, so you can edit or delete it later.

The card's footnote is unchanged ("credited to {name}" or "listed as Anonymous").

### Enter a person (`/people`)

> **Enter a person**
>
> Enter someone who has already agreed to take part. We will email them from John Kintree's address with a link to accept and choose their own password. They will see your name as the person who entered them.
>
> Invitations sometimes land in the spam or junk folder. Please ask the person to look there if it has not arrived within a few minutes.
>
> Name: [ input ]
> Email: [ input ]
> Country: [ input ]
> Postal code (optional): [ input ]
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
> Thank you for agreeing to take part in {SITE_NAME}, an invitation-only test of a shared database of issues, solutions, and evidence that people are claiming, proposing, and submitting.
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
> Postal code (optional): [ {postal code} ]
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

### My account (`/account`)

Called "Your account" until 22 October 2026, when John asked for "My" on the menu and in the page's headings and buttons.

> **My account**
> [ Sign out ]
>
> {name} · {email}
> Entered by {inviter} ({relationship}) on {4 October 2026}.
>
> **My details**
> Name: [ {name} ]
> Country: [ {country} ]
> Postal code (optional): [ {postal code} ]
> Posts you have already made keep the name they were posted with.
> [ Save my details ]
>
> **Change my password**
> Email: {email}
> Current password: [ input ]
> New password: [ input ]
> Type it again: [ input ]
> [ Change password ]

> That is not your current password.

> Your password is changed. You are signed out everywhere else.

> Your details are saved.

> Please fill in your name and country.

The email on this page, on accepting and on choosing a new password is plain text, not a box, so it does not look as if it could be changed there (John, 17 October 2026). Not client-facing: it stays a read-only username field so a phone's password manager saves the password under it. Changing the email is its own form below (X2, in the Phase 2 section).

The postal code is optional everywhere: entering a person, accepting and My account (John, 18 October 2026: the site does not check postal codes). Everyone can change their own name, country and postal code at any time (revision round, promised 8 October 2026).

John's account leaves out the "Entered by" line. "Sign out" sits right under the heading (John, 17 October 2026).

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

Edit opens the write page with the statement and the card filled from the post as the record holds it now (an issue renamed or merged since shows under its new name). "Read my statement" is hidden while editing, and the page leaves out the sentence at the top (John, 16 October 2026). Without JavaScript the page shows the statement and a "Save changes" button, which saves the new words with the post's card as it is. The card's heading reads "Edit your post", its buttons "Save changes" and "Cancel", and a line at the top says:

> Saving replaces what this post added. Removing a position here does not withdraw it; use the buttons on the issue page.

The "Post anonymously" box starts at the post's own choice and can be changed at any time, either way (John, 16 October 2026). Saving shows the post under the new choice from then on.

Note for the builder: while editing, the reading buttons and the "post it as a plain statement anyway" button are hidden; the card is the edit.

A row with a link the post already holds a reading for shows that reading (Phase 2); what else the page mentions is not kept with the post, so the page is read again quietly and "The page also mentions" appears under the stored reading when it arrives. The stored reading and the writer's supports or refutes stand whatever the fresh reading says; a page that cannot be opened now adds nothing. With the flag on but no reading service, nothing is asked (Beth's note of 22 October 2026, that the list did not show when she added a link while editing; added 24 October 2026).

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
> Merge this issue with: [ Choose an issue / every other issue ] [ Merge ]
> Start from the issue you want to keep.

Merge asks first (wording from the revision round, R1: the issue whose page you are on is the one kept):

> Keep {this}. Move everything from {other} into it, then remove {other}. This cannot be undone. It is recorded in the list of changes.
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

> {name} · {email} · entered by {inviter} ({inviter's email}, {relationship}) on {date} · joined {date}
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

## Phase 2: evidence that checks itself

Added 20 October 2026, before any Phase 2 code. Everything here shows only when `EVIDENCE_CHECK_ENABLED` is set and the reading service is configured; otherwise the card is exactly the Phase 1 card. Everything in a quote is **client-facing**. John approved the card and source confidence wording as proposed in the source confidence note (20 October 2026, 14:16 UTC: "Please proceed with building the display as you described it"); the change of email copy (X2) has not been shown to him yet. No dashes, none of the forbidden words.

### On the card, under each evidence row with a link

Shown as soon as the card opens (for links found in the statement) or when the writer leaves the link field (for a link typed or changed by hand). One line, replaced by the result:

> Reading the page…

Then one of:

> The page seems to support this: "{quote}"

> The page seems to argue against this: "{quote}"

> The page does not clearly say either way.

> Could not open this page.

> This kind of link cannot be read yet.

Under "The page does not clearly say either way.", the reading's own one sentence on why, for example what the writer's words claim that the page does not say (added 22 October 2026 after Audrey Tang's test, a draft for John):

> The page says vTaiwan claims 80 percent led to government action, not that they became law.

When a page has not been read after ten seconds, one more line under "Reading the page…" until the result comes (22 October 2026, a draft for John):

> Still reading. A slow page can take up to a minute.

The page is read against what the writer says it shows (their own words about the evidence, or a sentence they copied from the page), with the issue or solution as the claim. Words that say about the same as the page, even in other words, count; words that go further than the page read as unclear (22 October 2026, after Audrey Tang's test; Phase 2 SOW item 1, "what the poster claims").

The last one of the five results is for PDFs, videos and other links that are not web pages. "Could not open this page." is also what shows when the reading itself fails (the site does not answer, or the request is refused), apart from the busy reader below, which has its own line. Under a result with a page, one line of what the page says about itself (the same words as source confidence, below, without the agreement part), for example:

> A news report from March 2024. Secondary source.

The supports or refutes choice on the row is set from the reading only while the writer has not touched it, and stays theirs to change. When the writer's choice and the reading differ, one more line:

> You chose differently from the reading. That is fine; others will see both.

**Suggestions.** When the page mentions issues, solutions or evidence not yet on the card, up to three of each appear under the row, unticked, under the heading:

> The page also mentions

Under the heading, one line of help (added 21 October 2026 after John asked what the tick boxes do; a draft for John):

> Tick any you want to add to your statement; you can edit it before you post. Evidence you tick keeps this page's link.

Each is one line with a tick box and its kind ("Issue: …", "Solution: …", "Evidence: …"). Ticking one adds it to the card as an ordinary row the writer can edit; unticking removes that row again. Evidence ticked this way takes the link of the page it was found on, about the same claim, so it stays tied to its source (John, 20 October 2026: "Keeping the evidence connected with the source is important"); the writer can change the link. Its row shows the reading of that page but does not list the page's suggestions again.

When too many links are read in a short time, the line under the link says, **client-facing**:

> Too many links read just now. Please wait a minute; you can still post.

Post is never held back by a reading still under way. A post sent before the reading came back is stored without it.

### Source confidence, on the issue page

Under each piece of evidence in "Supported by" and "Refuted by", one line in plain words, never a number or a colour scale. Four parts, in this order, each left out when it is not known:

> A {type} from {Month YYYY}. {Primary source | Secondary source}. {N other pieces of evidence here say the same; M disagree.}

For a reference work (an encyclopedia or dictionary page) the date is when the page was last updated, since such pages are kept up to date (when the page gives no such date, as on a long article read only in part, the date its server gives for the last change); Wikipedia's first date is when the article was started, which says nothing about what it says now. Types: "news report", "research paper", "government source", "reference work", "organisation's page", "blog post", "page". Without a date, the first sentence ends after the type and "Date not given." follows: "A news report. Date not given. Secondary source." Agreement counts only evidence on the same issue or solution. When the writer kept "supports" but the page was read as arguing against (or the other way round), one more line:

> The page was read as arguing against this.

or, under "Refuted by", when the page was read as supporting:

> The page was read as supporting this.

This line shows to everyone, as the note proposed.

When the date is more than five years before the day the page is shown, one more sentence follows the date (John, 20 October 2026: "Indicating the age of the resource is good"; five years was the note's example and he named no other number):

> More than five years old.

For example: "A news report from March 2018. More than five years old. Secondary source. Two other pieces of evidence here say the same; one disagrees." A date given only as a year counts from the end of that year, and a month and year from the end of that month. Nothing is said about age when the date is not given. The card's line under a link says the age the same way.

The agreement part, word for word, counted in words from one to ten and in figures above (added 20 October 2026, following the note's example):

> One other piece of evidence here says the same.

> Two other pieces of evidence here say the same.

> One other piece of evidence here disagrees.

> Two other pieces of evidence here disagree.

> One other piece of evidence here says the same; two disagree.

> Two other pieces of evidence here say the same; one disagrees.

When no other evidence is on the same issue or solution, the agreement part is left out. When a page was never read, its type, date and primary or secondary are left out and only the agreement part shows, if any. When several statements cite the same evidence for the same claim, the "read as arguing against" line shows when any one of their readings went the other way.

### Revision round: agrees, partly agrees, contradicts (added 22 October 2026)

From John's emails of 21 October ("agrees, partly agrees, contradicts", the statement and the page side by side, "No source given") and 22 October (personal experience). Behind `EVIDENCE_CHECK_ENABLED`, like all of Phase 2. The verdict words, "No source given.", "From my own experience" and "From personal experience." are John's, from the plan's copy list; the labels "You wrote:", "The statement says:", "The page says:" and "Names its sources." are drafts for John. All **client-facing**.

**On the card, under an evidence row with a link.** The three readings that rest on a sentence from the page replace "The page seems to support this" and "The page seems to argue against this". One word or two, then the writer's sentence and the page's sentence one under the other:

> Agrees

> Partly agrees

> Contradicts

> You wrote: "{the writer's own sentence about this evidence}"

> The page says: "{quote}"

"You wrote" is left out when the statement says nothing about the evidence of its own. Under "Partly agrees", the reading's one sentence on what the page does not say, as under "The page does not clearly say either way." today, for example:

> The page says 80 percent led to government action, not that they became law.

"The page does not clearly say either way.", "Could not open this page." and "This kind of link cannot be read yet." stay as they are. "Partly agrees" sets the row to supports while the writer has not chosen; "You chose differently from the reading." shows when the writer picks refutes against "Agrees" or "Partly agrees", or supports against "Contradicts".

**On the card, under an evidence row with no link.** One line, and one tick box:

> No source given.

> From my own experience

When the box is ticked, the line reads instead:

> From personal experience.

Nothing is read for such a row. The tick box goes away (and is cleared) when a link is typed; it comes back when the link is removed. The card asks the writer nothing more.

**The source line** (on the card and in source confidence) gains one sentence after primary or secondary, when the page names where its facts come from (R16):

> Names its sources.

For example: "A news report from March 2024. Secondary source. Names its sources." Nothing is said when it does not, or when it cannot be told.

**On the issue page, under each piece of evidence**, after the source confidence line, each statement's reading of the page that rests on a quote, one under another (each distinct one once):

> Agrees. The statement says: "{the writer's sentence}" The page says: "{quote}"

> Partly agrees. The statement says: "…" The page says: "…" {what the page does not say}

> Contradicts. The statement says: "…" The page says: "…"

"The statement says" is left out when the reading kept no sentence of the writer's. For a piece of evidence with no link, instead of a link:

> No source given.

or, when the statement that added it ticked "From my own experience":

> From personal experience.

The disagreement line follows the new words: under "Supported by", "The page was read as contradicting this."; under "Refuted by", "The page was read as agreeing with this." (or "The page was read as partly agreeing with this." when only a partly agrees reading went that way). A "Partly agrees" reading counts as agreeing everywhere, with what the page does not say shown under it.

### Revision round: PDFs (added 22 October 2026)

PDFs are read like pages, so "This kind of link cannot be read yet." now shows only for videos and other files that are not web pages or PDFs. A PDF's result is one of the same lines as a page's. A PDF that is only pictures of pages (a scanned document) has no text to read; under its link, **client-facing** (John's words, from the plan's copy list):

> This PDF has no text that can be read.

A PDF too large to read (over 15 MB) or too slow to open shows "Could not open this page.", as a page does. Only the first 40 pages of a long PDF are read, or as many as can be read in 25 seconds; a PDF of which not one page can be read in that time shows "Could not open this page."

An arXiv paper's link (`arxiv.org/abs/...`) reads the abstract page first; when the abstract does not settle it or only partly agrees, the full paper is read too, and its reading is shown when it rests on a sentence from the paper. Nothing new is said on the card while that happens ("Reading the page…" and, after ten seconds, "Still reading. A slow page can take up to a minute." as for any page). Its source line says it is a primary research paper, for example:

> A research paper from June 2017. More than five years old. Primary source.


### Revision round: YouTube videos (added 22 October 2026)

YouTube videos are read from their own captions, best effort (YouTube may refuse). "This kind of link cannot be read yet." stays for Vimeo, TikTok, YouTube channels and playlists, and other files. All **client-facing**. "Could not read this video's captions. Paste the transcript below and it will be read." is John's, from the plan's copy list; the rest are drafts for John.

**On the card, under a YouTube link.** While it is read:

> Reading the video…

Then one of the same results as a page. The video's sentence carries its time:

> The video says at 4:12: "{quote}"

When the captions cannot be read (the video has none, or YouTube refused):

> Could not read this video's captions. Paste the transcript below and it will be read.

with a box for the transcript (at most 60,000 characters) and a button:

> Read the transcript

While it is read: "Reading the transcript…". The result is one of the same lines, with:

> The transcript says: "{quote}"

(and "at 4:12" after "says" when the pasted transcript has its times, as YouTube's "Show transcript" gives them). The pasted text is never kept; only the reading is. A transcript too short to read shows the box again.

**The source line** for a video names the channel's kind: "news video", "organisation's video" or "video", with the upload date, for example "A news video from March 2024. Secondary source." After a reading from a pasted transcript one more sentence:

> Read from a transcript the writer pasted.

**On the issue page**, a video's reading says "The video says at 4:12:" instead of "The page says:", and a reading from a pasted transcript "The transcript says:" followed by "Read from a transcript the writer pasted."

### Revision round: the page's side and the writer's side (GitHub issue 29, added 26 October 2026)

**Awaiting John's yes.** Every quote below is a **client-facing** draft; he may replace any of it. Behind `EVIDENCE_CHECK_ENABLED`, like all of Phase 2. No dashes, none of the forbidden words.

John asked (issue 29) whether supports or refutes is about the statement or the source, and whether a post could be "refutes for the statement, and supports for the source". It now is. When the page is read as "Agrees" and the writer chose refutes, or as "Contradicts" and the writer chose supports, the post adds two pieces of evidence: the page, on the side it was read as taking, and the writer's own statement about it, with no link, on the writer's side. "Partly agrees", "The page does not clearly say either way." and a page that could not be opened stay as they are, one piece on the writer's side.

**On the card, under the row**, in place of "You chose differently from the reading. That is fine; others will see both." (which stays for "Partly agrees"):

> The page supports this and your statement refutes it, so both will be added, each on its own side. To add only the page, choose supports.

> The page refutes this and your statement supports it, so both will be added, each on its own side. To add only the page, choose refutes.

Choosing the page's side clears the line, and only the page is added.

**What this will add** lists both, each in John's format, the page's line first. The statement is named with the writer's own sentence about the page when the reading found one in the statement, and otherwise "Statement on {the page's name}". For John's example:

> John Kintree submits evidence En.wikipedia.org/wiki/Climate_change
> John Kintree submits evidence The rise in CO2 is minuscule
> En.wikipedia.org/wiki/Climate_change supports issue of Climate change
> The rise in CO2 is minuscule refutes issue of Climate change

The feed's sentences under the post read the same way.

**On the issue page** the page is listed under its side with its reading and source line as before, and the statement under the writer's side. It is not counted as another piece of evidence saying the same or disagreeing. Under it, in place of "No source given.":

> The writer's own words about {the page's name}, which was read as agreeing with this.

under "Refuted by", or under "Supported by":

> The writer's own words about {the page's name}, which was read as contradicting this.

**Editing the post.** The edit card shows one row again, the page on the writer's side with its reading and the line above; saving adds the same two pieces again, never a third.

### My statements (`/my-statements`; no-cost extra, John 17 October 2026)

First at the foot of Your account; since 22 October 2026 (Beth's request, John's yes) a page of its own, linked from the menu between "Enter a person" and "My account". **Client-facing**:

> **My statements**

Then the member's own posts, newest first, each as in the feed: byline, statement, what it added, and "Edit" and "Delete". Posts made anonymously are included and say "Anonymous" as in the feed; this page is seen only by its owner. At most 50 at first; with more, under the last one:

> [ Show more ]

which shows 50 more each time. With none yet:

> You have not posted anything yet.

### My account: Change my email (no-cost extra, John 17 October 2026)

Shown only with `EMAIL_CHANGE_ENABLED` set (not client-facing), which waits for John's yes on the wording below; unset, My account ends with "Change my password".

After "Change my password", **client-facing**:

> **Change my email**
> New email: [ input ]
> Current password: [ input ]
> [ Send a link to the new email ]

Then, at the top of My account, the same words whether or not the new address can be used (as on "Forgot your password?"):

> We have sent a link to {new email}. Open it to finish the change. If it does not arrive in a few minutes, please check your spam folder. Until then, sign in with {current email}.

Under the form, when it cannot go ahead:

> That is not your current password.

> Please enter an email address.

> That is already your email.

Nothing changes until the link is opened. A new address is not used when it belongs to another account, now or before (it then gets no email; the page says the same as above). Not client-facing: one account sends at most three change links a day, and one address gets at most three links an hour; past either, the page says the same as above and nothing is sent. Too many tries in a minute shows the sign in limit's "Too many tries. Please wait a minute and try again." Every earlier address stays on the account's record with the date it stopped being used, so an address never points at two people.

### The new email link

> **Subject:** Confirm your new email for {SITE_NAME}
>
> Hello {name},
>
> You asked to use this address for your account on {SITE_NAME}. To confirm, open this link:
> {SITE_URL}/email/{link}
>
> The link works once, for 24 hours. Until you open it, sign in with your old address.
>
> If it was not you, you can ignore this email.
>
> John Kintree

### The note to the old address

> **Subject:** Your email on {SITE_NAME} is being changed
>
> Hello {name},
>
> Someone signed in to your account on {SITE_NAME} asked to change its email to {new email}. Nothing changes until the link sent to that address is opened.
>
> If it was not you, please change your password and reply to this email.
>
> John Kintree

### Confirm your new email (`/email/{link}`)

> **Confirm your new email**
>
> From now on, sign in with {new email}. Your old address, {old email}, stays on your account's record as an earlier one.
> [ Confirm the new email ]

Then:

> Your email is changed. From now on, sign in with {new email}.
> [ My account ] (signed in) or [ Sign in ]

When the address was taken by another account meanwhile:

> That address is now used by another account. Your email has not changed.

An expired link:

> This link has expired. You can ask for a new one on My account.

A used or replaced link reads as for the other links ("This link no longer works...").

### Back room: earlier addresses

On each person's line in People, after the email, for each earlier one:

> earlier {address} until {20 October 2026}

### Not client-facing

The reading takes a few seconds per link; rows fill in as they arrive. A link is read once for the same claim and statement; the reading is kept for the life of the running site (up to 500 readings), so reading it again costs nothing until the site restarts. With the reading service unset, no line appears at all.

## Phase 3: talking to the record

Added 26 October 2026, before any Phase 3 code. Every quote below is a **client-facing** draft for John's yes on the call of 28 October 2026; he may replace any of it. Each part shows only with its switch set (not client-facing): `ASK_ENABLED`, `FOLLOW_UPS_ENABLED`, `PLACES_ENABLED`, `ABOUT_ENABLED`; unset, every screen is exactly as before. No dashes, none of the forbidden words. After this entry each workstream edits only its own subsection, and only after its case run: Ask the record (W2), Follow-up questions on the card (W3a), A place on the card (W3b), Places in the record (W4), About (W1).

### Header

Two menu items, each behind its switch: "Ask" after "Issues", for anyone who can read the record (passphrase or signed in), and "About" last, wherever the menu shows. The About page also opens without signing in (open question 9; default yes).

> Write · Issues · Ask · Enter a person · My statements · My account · About

### Ask the record (`/ask`, and a box on each issue page)

**On `/ask`,** for the whole record:

> **Ask the record**
>
> Ask a question in plain words. The answer is built only from what people have posted here, and names the posts it comes from.
>
> [ input, placeholder "For example: What do people say about the Security Council veto?" ]
> [ Ask ]

**On each issue page,** under the evidence and above the posts:

> **Ask about this issue**
>
> [ input, placeholder "For example: Why do people oppose these solutions?" ]
> [ Ask ]
>
> Answers come only from the posts about this issue and its sub-issues.

Under either box, small:

> Answers sum up what is in the record, including views that differ. They can be wrong, so open the posts to check. Your earlier questions on this page go with the next one, so you can follow up; nothing is kept after you leave.

**While it reads:**

> Reading the record… The first question after a quiet spell can take a minute.

After ten seconds, one more line until the answer comes:

> Still reading. A long issue can take up to a minute.

**The answer,** a few short paragraphs, each ending in its source numbers ([1] [3]), then:

> **Sources**
>
> 1. {name or Anonymous}, {date}: "{the first 200 characters of the post}…" On {issue name}

A source that is a solution or a piece of evidence (a count line cites these) reads, on an issue page and on the Ask page alike (added 26 October 2026 after the walk):

> 2. Solution: {solution name}. On {issue name}

> 3. Evidence: {evidence name}. On {issue name}

"On {issue name}" is left off when the evidence belongs to no issue. Each issue name links to its issue page. A count line reads, for example, "Approved by 5, opposed by 2, as of 30 October."

**When the record had more than one answer can read,** under the answer:

> There are more posts on this than one answer can read, so this answer may leave some out.

**When the record holds nothing on it,** or nothing in the answer could be tied to a post:

> The record does not say anything about this yet.

**When it cannot go ahead:**

> Please write a question.

> Please keep the question under 500 characters.

> You have asked 30 questions today. Please ask again tomorrow.

> The site has answered as many questions as it can today. Please ask again tomorrow.

> Asking needs the reading service, which is not set up.

> The question could not be answered just now. Please try again in a minute.

The last line is for a reply that is late, refused or unreadable; never an error page. Not client-facing: the browser waits 50 seconds, longer than the server's 40.

### Follow-up questions on the card

Under a **new** issue, solution or evidence row (never one already in the record), at most three on a card, once the card has opened:

> A question that would make this clearer:
> {question}
> [ input ]
> [ Add to my statement ] [ Skip ]
>
> Your answer is added to your statement, so everyone who reads the post sees it.

Under an evidence row with no link and no "From my own experience" tick, always this question (no reading needed):

> Where did you read or hear this?

"Add to my statement" adds one line to the statement, the question and then the answer ("When did this happen? In 2023."), and the box goes. The card is not read again. "Skip" removes the box. Post is never held back by a question, and nothing shows while questions are being thought of. Questions are in English, like the rest of the card.

### A place on the card

A "Place" row under the card's rows, before Post:

> Place: [ list, first choice "Not about one place", then countries A to Z ]
> Town or area, optional: [ input ]

For a named statement the country starts as the account's country; for an anonymous one both start empty, with:

> A town can tell others who wrote an anonymous statement. Add one only if you are happy with that.

When a town or area is typed with "Not about one place":

> Please choose the country for this town or area.

On the edit page the row shows the post's place and can be changed like the rest.

### Places in the record

**Under a post** that has a place, in the feed, on issue pages, in search and on My statements:

> In St. Louis, United States

> In Germany

**On the Issues page,** under search and above "Sort by":

> Near: [ list of countries ] [ Town or area, optional ] [ Show ]

It starts with the place of the member's last placed post, else the account's country. Results replace the list, sorted and counted as the full list:

> **Issues near {place}**
> Show all issues

With a town or area, near means posts placed in the same town or area; with a country only, posts placed in that country. When there are none:

> No statements have been placed in {place} yet. Show all issues

### About (`/about`)

> **About this site**
>
> **What it is for**
>
> {SITE_NAME} is a small test of a shared database. People write statements about issues they care about. The site reads each one into a short form of the issue, the evidence and the solutions it mentions; the writer checks and corrects the form; and it joins a database that everyone here can read, ask questions of, and build on.
>
> **How statements are read and questions are answered**
>
> A language model fills in the form from the statement. Nothing joins the database until the writer has checked the form and posted it.
>
> When you ask a question, the site gathers what the database holds about it: the issues, the solutions with how many people approve and oppose them and since when, the evidence and how its pages were read, and the posts themselves, newest first. The language model writes a short answer from that alone, and each part of the answer names the posts it comes from. A part that names no post is left out. Questions and answers are not kept.
>
> **The language model**
>
> {provider}, version {version}. It reads statements, answers questions and suggests follow-up questions, with the guiding principles below at the start of its instructions each time. When it checks the page behind an evidence link it is given no principles, so that each link stays quick and cheap to read.
>
> **What is sent to the language model**
>
> The statement being written and its form; the question and your earlier questions on the page; and what the database holds that an answer is built from: posts under the name they were posted with, or none when anonymous, and the names of issues, solutions and evidence. Never an email address, a password, or an account's country or postal code.
>
> **Software**
>
> The site is written in Python with FastAPI and keeps the records in a Neo4j database. Its code is open, under the MIT licence, in John Kintree's repository: {repository address}.
>
> **Where it runs**
>
> On Render's free plan, with the records in a free Neo4j Aura database. A free service sleeps after a quiet spell, so the first page or question after one can take up to a minute.
>
> **Guiding principles**
>
> The language model is given the Statement of purpose, and the full text of the Universal Declaration of Human Rights and the Earth Charter at the start of the system prompt, its instructions for reading statements, answering questions and asking follow-up questions. They guide it; they are not a test that posts must pass. It does not judge a post against them unless a question asks, and names an article or a principle only when the question or a post does. Each person still checks their own form.
>
> **Statement of purpose**
> {purpose, in full}
>
> **Universal Declaration of Human Rights**
> {the Declaration, in full}
>
> **The Earth Charter**
> {the Charter, in full}

The three documents are shown from the same files the instructions use, so the page and the instructions can never differ. `{provider}` and `{version}` come from `LLM_BASE_URL` and `LLM_MODEL` (DeepSeek, deepseek-v4-flash). Without `LLM_API_KEY` the language model paragraph reads:

> No language model is set up at the moment, so forms are filled in by hand and questions cannot be asked.

This page's words are John's own (his edits of 28 October): "database" for the record, "form" for the card and "language model" for the reading service, rule 5 notwithstanding. The rest of the site still says record, card and reading service until the wording is changed throughout.

`{repository address}` is John's repository, as the README names it; nothing personal to the builder (CLAUDE.md rule 8).
