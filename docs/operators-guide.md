# Open Collective Intelligence: the operator's guide

This guide is for the person who runs the site. It covers the everyday jobs, the few emails that need you, and what to do when something stops. You do not need to write any code to follow it.

## What the site is

The site is a closed test of a shared record. A small group of people write short statements about issues they care about. A reading service suggests the issue, the claim, any evidence and any solution in each statement. The writer checks and corrects that, then posts it. Every post joins one record that everyone taking part can read.

The site lives in three places, all in your name:

* **GitHub** keeps the code.
* **Render** runs the website and gives it its address.
* **Neo4j Aura** keeps the record itself, like a notebook.

A fourth company, **DeepSeek**, runs the reading service. You pay it a few cents as statements are read.

## Letting someone in

Everyone taking part has their own account and their own password. Nobody can sign themselves up: someone already taking part enters them. That way every account can be traced to the person who vouched for it, and each person has one account.

### Entering a person

Only enter someone who has already agreed to take part.

1. Sign in and click **Enter a person** at the top of the page.
2. Fill in their name, email address and country, and their postal code if you have it (it is optional), and choose how you know them: family, neighbor, friend, work, school, health or organization.
3. Tick **This person has agreed to be entered**, then press **Enter and send the invitation**.

The site emails them from your Gmail address. The email thanks them for taking part, says who entered them and holds a link to accept. The link works once, for 14 days. Invitations sometimes land in the spam or junk folder, so the page reminds whoever enters someone to tell them to look there.

Under the form you see everyone you have entered and whether they have joined. If the email did not go, or the link has expired, press **Send the invitation again**. A fresh link goes out and the earlier one stops working. If an email address was mistyped, press **Withdraw** and enter the person again. Withdraw only works for someone who has not accepted yet.

Everyone who joins can enter other people in the same way, and you can see every account in the back room.

### Accepting an invitation

The new person opens the link and sees who entered them and the details that were entered. They can correct their own name, country and postal code; the postal code is optional. How they know the person who entered them stays as it was entered. They choose a password of at least 10 characters. Their phone or browser may offer a strong password and remember it, which is the easiest way. Then they are signed in.

If the link has expired, they can ask for a new one, or use **Forgot your password?** on the sign in page with the address they were entered with. That sends them a fresh invitation.

### Signing in and passwords

People sign in with their email address and password, and stay signed in on that phone or computer for thirty days.

* **Forgot your password?** on the sign in page emails a link to choose a new password. The link works once, for one hour. The page says the same thing whatever address is typed, so it never tells a stranger who is taking part.
* **Your account**, at the top of the page, is where people sign out (right under the heading), change their name, country and postal code at any time, and change their password. Posts they already made keep the name they were posted with. Changing the password signs them out on every other phone or computer.
* **Change your email**, also on Your account, takes the new address and the current password. The site sends a link to the new address and a short note to the old one; nothing changes until the link is opened, within 24 hours. Until then the person signs in with their old address. An address that belongs to another account, now or before, is never used, and the page says the same thing either way. Every earlier address stays on the account's record with the date it stopped being used, and the back room lists them under People, so each address can only ever point at one person. This part is switched on in Render, under Environment, as `EMAIL_CHANGE_ENABLED` set to true; until then Your account has no Change your email form.
* **My Statements**, at the foot of Your account, lists everything that person has posted, newest first, including posts made anonymously, with **Edit** and **Delete** beside each. Only they see this list. Fifty show at first, and **Show more** brings the next fifty.

No password is ever sent by email, and nobody, you included, can see anyone's password.

### People from the test weeks

People who took part with the passphrase keep their earlier posts, approvals and oppositions, under the names they typed then. To take part again they need an account: enter them like anyone else. Their earlier posts stay as they are and are not moved to the new account.

## Changing the sentence at the top

The sentence at the top of the page and the site name live in Render, not in the code.

1. Sign in to Render and open your service.
2. Click **Environment**.
3. To change the sentence at the top of the page, edit `SITE_SENTENCE`. The site name is `SITE_NAME`.
4. Click **Save**. Render restarts the site. This takes a few minutes.

The passphrase from the test weeks, `DEMO_PASSPHRASE`, no longer lets anyone in. Leave it where it is. If accounts ever had to be switched off in a hurry, changing `ACCOUNTS_ENABLED` to false in the same place brings the passphrase page back, and nothing in the record is lost. Then tell whoever helps you with the site.

## The back room

The back room is where you look after the record. Add `/admin` to the end of the site address. Your browser asks for a username and a password. Type any username. The password is your back room password (see "Where the back room password is"). It is not the password of your own account. Keep both to yourself.

The page shows how many records and connections there are, the last problem the reading service reported, the last email that could not be sent, everyone with an account, and the latest fifty posts. The two problem lines clear themselves when the site restarts.

**Download a copy** saves the whole record to your computer as one file. Do this often, and always before a reset. Keep the file somewhere private, because it holds everything people wrote.

**Reload seed** adds back any of the starting statements that are missing. It does not remove anything.

**Reset to seed** clears every post and puts back only the starting statements. Accounts, and who entered whom, stay, so nobody is locked out. The list of changes to the issues is cleared too. Download a copy first. You have to type RESET to confirm.

**Delete** next to a post removes that statement and the claims, citations, proposals and evidence links it created. An issue, solution or piece of evidence goes too, but only when that post touched it, it is not a starting item, and nothing else is linked to it. People and starting items always stay. Links between solutions and issues, approvals, oppositions and the way issues sit inside each other also stay, even when they began with the deleted post.

A developer can put a downloaded copy back into an empty record. There is no button for that yet. A copy never holds passwords, so after a copy is put back everyone chooses a new password with **Forgot your password?**.

### People

Every account is listed with its email address, who entered it (with that person's email address, since two people can share a name) and how they know each other, the date it was entered, and where it stands: joined, invited but not accepted yet, invitation expired, or switched off. Your own account says **first account** in their place, because nobody entered you.

Next to each person are the buttons that fit:

* **Send the invitation again**, for someone who has not accepted. A fresh link goes out and the earlier one stops working.
* **Send a password link**, for someone who has joined and cannot get in. They get the same email as from "Forgot your password?".
* **Withdraw**, for someone who has not accepted. The page asks first. Their entry and their link are removed.
* **Switch off**, for someone who has joined. The page asks first. They can no longer sign in, and their posts, approvals and oppositions stay. **Switch on** lets them back in. Your own account cannot be switched off.

If one of these emails does not go, the page says so. Try again in a minute. One person can be sent only a few emails an hour, so nobody's inbox fills up by mistake.

### Sending email

The **Sending email** line reads "No problems recorded." while all is well. If it shows a date, the last email could not be sent. Try once more. If it keeps happening, Google has most likely withdrawn the permission to send from your Gmail. See "Sending email from your Gmail" below.

## Where the back room password is

Render made the password for you when the site was set up. To see it:

1. Sign in to Render and open your service.
2. Click **Environment**.
3. Find `ADMIN_TOKEN` and click the eye icon to show it.

You can copy it into your password manager. If you ever change it in Render, the old one stops working after the site restarts.

## Adding a starting statement

There is no separate list to edit. To add a statement you want everyone to see, post it on the site under your own name, like any tester.

## Tidying the issues

Only your account can tidy the list of issues. At the foot of each issue page you see **Tidy this issue**:

* **Rename** changes the issue's name. If another issue already has that name, the page suggests a merge instead.
* **Move** makes the issue part of a top level issue, or makes it a top level issue again. An issue that has issues of its own stays at the top level.
* **Merge** starts from the issue you want to keep. Open that issue's page and choose the other one under **Merge this issue with**. Everything from the other issue, its claims, solutions, evidence and the issues that are part of it, moves to the one you kept, and the other is removed. The page asks first, naming the issue it keeps, because a merge cannot be undone.

Every rename, move and merge is listed, newest first, on **Changes to the issues**, linked at the foot of the Issues page. Everyone taking part can read it, so tidying always happens in the open. After a merge, older posts show the issue they now belong to; their own words are not changed.

## The slow first visit

On the free plan, Render puts the site to sleep after about fifteen minutes with no visitors. The next visit wakes it up. That first page can take around thirty seconds to appear. After that it is quick again. Nothing is wrong, and nothing is lost.

If you want the site to answer at once every time, see "What costs money" below.

## When the page says the record is asleep

If the notebook at Neo4j Aura has nobody using it for three days, Aura pauses it. The site then shows a page that says the record is asleep.

To wake it:

1. Sign in to the Neo4j Aura console with your Google account.
2. Find your instance. It will say Paused.
3. Press the **Play** button.
4. Wait a few minutes, then reload the site.

**Never leave it paused for thirty days.** Aura deletes a free instance that has been paused that long, together with everything in it. If you get an email about a pause, wake the instance within a day or two.

## Emails that need you

A few kinds of email need action. Always sign in by typing the company's address into your browser yourself, rather than clicking a link in the email. That way a fake email cannot trick you.

* **From Neo4j, about a paused instance or a planned deletion.** Wake the instance as described above.
* **From UptimeRobot, saying the site is down.** Open the site yourself. If it loads after about thirty seconds, it was only asleep and you can ignore the alert. If it shows the "asleep" page, wake the record. If it shows an error for more than ten minutes, contact whoever helps you with the site.
* **From Google, saying an app can now send email for you, or that its access was removed.** One arrives right after the setup call; that one is expected. If one arrives at any other time and you did nothing, ask whoever helps you with the site.

Emails that need nothing from you: receipts from DeepSeek, notices from Render that the site was deployed, newsletters from any of the four companies, and a later UptimeRobot email saying the site is up again. Replies from people you entered are ordinary emails to you.

## When reading stops

If "Read my statement" stops filling in the form, testers can still fill it in by hand and post. Nothing is lost. To get reading working again:

1. **Check your DeepSeek balance first.** Sign in to the DeepSeek platform. If the balance is at or near zero, add a few dollars.
2. **Then look at the reading service line in the back room.** It shows the last problem DeepSeek reported. A problem with the key or the balance shows there.
3. If you made a new DeepSeek key, put it in Render under Environment as `LLM_API_KEY` and save.

## Sending email from your Gmail

Invitations and password links go out from your own Gmail address, so people can simply reply to you. Each one also appears in your Sent folder. The site can do this because you gave Google a permission once, on the setup call. That permission lets the site send email as you. It cannot read, change or delete anything in your mailbox. Gmail allows a few hundred emails a day, far more than the site needs.

The permission stops working if:

* you change your Google password, because Google then withdraws it for safety;
* you remove it yourself (see below);
* no email at all is sent for six months.

Nothing is lost when that happens, and the site keeps working, but invitations and password links stop going out. Anyone entering a person is told the invitation did not go, and the **Sending email** line in the back room shows a date. To put it right, ask whoever helps you with the site for a short call to give the permission again. It takes about ten minutes. Afterwards, press **Send the invitation again** for anyone still waiting.

To remove the permission yourself, for example when the test ends:

1. Go to myaccount.google.com and sign in.
2. Click **Security**, then open the list of apps that have access to your account ("Your connections to third-party apps and services").
3. Choose Open Collective Intelligence, the name given to the app on the setup call, and remove its access.

## Before you widen the circle

The site was built for a small, trusted group. Before you let many more people in, keep these points in mind:

* It is a closed test. Nobody gets in without an account, and every account is entered by someone already taking part, who vouches for them.
* DeepSeek, an outside company, reads every statement that goes through "Read my statement". People should not write anything they would not want a company to store.
* Each post is credited to the name on the account. Entering someone vouches for them, but names are not checked against anything, so the record cannot prove that every account is a different person.
* "Post anonymously" hides the name from other people, but the post still belongs to its account. The copies you download from the back room show whose post it is, so keep those copies private.
* The address ends in onrender.com. It works, but it is not your own web address yet.

## What costs money

Nothing, by default.

* **Render** is free. The Starter plan, about 7 US dollars a month, removes the slow first visit. You can change the plan on the service page in Render at any time.
* **DeepSeek** costs a few cents for a busy week. You pay in advance by adding credit. Reading the page behind a link costs about a tenth of a US cent each time, about one US dollar per thousand links; a link already read is not read again until the site restarts. When DeepSeek's own page reader is asked to try a page, that adds 75 US cents per thousand pages it manages to read.
* **Neo4j Aura** is free. Never upgrade to Aura Professional for this site. It is far more than a test needs and it costs real money every month.
* **UptimeRobot** and **GitHub** are free.

## If the record is ever lost

If Aura deletes your instance, the site shows an error and your record is gone from Aura. The last copy you downloaded is what you can get back. This is why regular copies matter.

1. In the Aura console, create a new free instance. Download the credentials file straight away, because the password is shown only once.
2. In Render, under Environment, fill in `NEO4J_URI`, `NEO4J_PASSWORD` and `NEO4J_DATABASE` from that file. The database name is the instance id, a short code, not the word neo4j. Save.
3. Ask whoever helps you with the site to put your last downloaded copy into the new, empty instance. They need the file and about ten minutes. A copy holds no passwords, so afterwards everyone, you included, chooses a new password with **Forgot your password?**.
4. If you have no copy, the accounts are gone too. Ask whoever helps you to make your first account again, as on the setup call. Then open the back room, press **Reload seed** to start again from the starting statements, and enter people again.

## When you add a link

A piece of evidence can carry a link to a web page. When the form opens, the site reads the page behind each link and says, under that link, what it found:

* "Agrees", "Partly agrees" or "Contradicts", followed by the writer's own sentence about the page ("You wrote") and the sentence from the page the reading rests on ("The page says"), one under the other;
* "The page does not clearly say either way", followed by one sentence on why;
* "Could not open this page";
* "This kind of link cannot be read yet".

The page is read against what the writer says it shows, not only against the issue or solution. A writer who copies or puts in their own words what the page says gets "Agrees". A writer who goes further than the page, for example "proves" where the page says "suggests", or "became law" where it says "led to government action", gets "Partly agrees", and one more sentence names what the page does not say. "Partly agrees" sets the form to supports, and counts as agreeing on the issue page. When the page backs none of what the writer says, the form says "does not clearly say either way". A slow page can take up to a minute; after ten seconds the form says "Still reading. A slow page can take up to a minute."

Under a page it could read, one more line says what kind of page it is, when it was written and whether it is a primary source, for example "A news report from March 2024. Secondary source." When the page names where its facts come from, such as the studies or data it relies on, the line ends with "Names its sources." The supports or refutes choice is set from the reading only while the writer has not touched it. **The writer always decides.** If they choose differently, the form says that is fine and that others will see both. Nothing is ever blocked or removed because of a reading, and Post never waits for one. The page may also mention other issues, solutions or evidence; up to three of each appear under **The page also mentions**, unticked, and ticking one adds it to the form.

Some pages cannot be read well:

* A page that is mostly menus and links, like the starting statements' United Nations document page, says "does not clearly say either way", because there is almost no text on it.
* Some news sites, Reuters among them, turn away anything that is not a person in a browser. Their pages say "Could not open this page". When that happens the site asks DeepSeek's own page reader to try instead, which sometimes works. To stop it asking, add `DEEPSEEK_FETCH` with the value `0` in Render under Environment and save; those pages then simply say "Could not open this page".
* Vimeo and TikTok videos, YouTube channels and playlists, and files that are neither web pages nor PDFs (Word documents, pictures), say "This kind of link cannot be read yet".
* A PDF that is only pictures of pages, as a scanned document is, says "This PDF has no text that can be read".

In each case the form works as before and the writer chooses supports or refutes themselves.

**PDFs** are read like pages: a report, a study or a government document behind a link is read for the sentence the writer's claim rests on, and its date is the one the PDF gives for itself. Only the first 40 pages are read, and a PDF over 15 MB says "Could not open this page", as a very slow one does. A link to a paper on arXiv (arxiv.org/abs/...) reads the paper's summary page first; when that does not settle it, or only partly agrees, the whole paper is read too, which can take a little longer. A summary leaves out detail, so the paper's own sentence is shown when it finds one. Such a paper is always described as a primary research paper.

**YouTube videos** are read from their own captions, the words YouTube shows under a video. While it reads, the form says "Reading the video…", and the result is one of the same lines as for a page. The video's sentence says where it is, for example "The video says at 4:12", so anyone can go to that moment. Under it, the line names what the channel is ("A news video", "An organisation's video" or "A video") and the day the video was put up. Reading captions is best effort: YouTube has no official way for another site to read them, and it often turns away sites run from large data centres, as this one is. When the captions cannot be read, the form says "Could not read this video's captions. Paste the transcript below and it will be read." with a box and a button, **Read the transcript**. On YouTube, the transcript is under the video's description, behind "Show transcript"; copying it with its times lets the form say where the sentence is. The pasted words are read exactly as a page is, and are never kept: only the reading is. Because such a reading rests on what the writer pasted, its line ends "Read from a transcript the writer pasted.", on the form and on the issue page, where its sentence reads "The transcript says".

A piece of evidence with no link says "No source given." under it, on the form and on the issue page. Under that line is a tick box, **From my own experience**. A writer who ticks it is saying the evidence is something they saw or lived through; the line then reads "From personal experience." instead, on the form and on the issue page. Nothing is read or checked for it, and the box goes away when a link is typed.

On the issue page, each piece of evidence then carries one line in plain words: the kind of page and its date, "More than five years old." when it is, primary or secondary, and how many other pieces of evidence on the same issue or solution say the same or disagree. For a reference work such as Wikipedia, the date is when the page was last updated. Anything not known is left out. Under that line, each statement's reading of the page is shown in the same words as on the form: "Agrees", "Partly agrees" or "Contradicts", then what the statement says and what the page says, side by side, and for "Partly agrees" what the page does not say. When the writer kept "supports" but the page was read as contradicting it, everyone sees "The page was read as contradicting this." (and under "Refuted by", "The page was read as agreeing with this."). Five years is easy to change; ask whoever helps you with the site.

Reading links is switched on in Render, under Environment, as `EVIDENCE_CHECK_ENABLED` set to true. To switch it off, set it to false and save. The form and the issue page then look as they did before, and nothing in the record is lost.

## Dictation

If your browser offers Dictate, press it and speak. The button says "Listening… press to stop". Press it again to stop, then check and edit the text before reading or posting it. If Dictate is missing or does not work, type the statement instead.

## A few things testers may notice

The site asks each person to wait twenty seconds between posts, so nobody can flood the record. A tester who posts twice quickly sees a short message asking them to wait a moment.

The Write page is kept simple: the introduction, the box for writing or dictating, **Post anonymously**, and **Read my statement**, with the recent statements below. **Read my statement** always opens the form: when the reading service is slow or down, the form opens empty and the tester fills it in by hand. Everything in the form can be changed before posting.

Names for issues, claims, evidence and solutions can be up to three hundred characters. A long one wraps onto more lines rather than being cut off. If a tester's long name was shortened to fit, the form says so and they can edit it.

On an issue page, each solution has an **Approve** and an **Oppose** button. Each person holds one position on each solution: pressing the other button switches it, and pressing the same button again withdraws it. Solutions are listed by approvals minus oppositions.

People can **Edit** or **Delete** their own posts, and nobody else's. Editing a post changes only what that post says. While editing, a person can switch the post between their name and Anonymous at any time, either way; people who saw it before may remember who wrote it. To rename an issue, use **Tidy this issue** at the foot of the issue page. An edited post says "edited". Deleting a post removes what it claimed, proposed and cited, unless something else still uses it. Its approvals and oppositions stay; they are changed with the buttons on the issue page.

The Issues page has a search box. It finds issues, solutions, evidence and posts that hold every word typed, or words that start with it. Searching by meaning comes in a later phase.

## Two checks after the October changes

Two things can only be seen from your side, in Render and in the back room. Neither is urgent.

1. **What the site could read.** Sign in to Render, open your service and choose **Logs**. Search for `"reader"`. A line with `"reader": "youtube"` says whether YouTube let the site read a video's captions: `ok` when it did, `refused` when it turned the site away and the writer was asked to paste the transcript. A line with `"reader": "deepseek"` is a page the site could not open itself, so DeepSeek's own page reader tried instead; if Wikipedia links show up there often, tell whoever helps you with the site.
2. **A copy of the record.** In the back room, press **Download a copy** once. It should save one file, as before. If it says there was a problem instead, tell whoever helps you with the site.

## Who to ask

For accounts, entering people and the back room, you are in charge. For anything that means changing how the site works, or putting a copy back, ask a developer. The list of things planned for later came with this guide. Hand it to whoever helps you, so nobody starts from scratch.
