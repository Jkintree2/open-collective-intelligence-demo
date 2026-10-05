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
2. Fill in their name, email address, country and postal code, and choose how you know them: family, neighbor, friend, work, school, health or organization.
3. Tick **This person has agreed to be entered**, then press **Enter and send the invitation**.

The site emails them from your Gmail address. The email thanks them for taking part, says who entered them and holds a link to accept. The link works once, for 14 days.

Under the form you see everyone you have entered and whether they have joined. If the email did not go, or the link has expired, press **Send the invitation again**. A fresh link goes out and the earlier one stops working. If an email address was mistyped, press **Withdraw** and enter the person again. Withdraw only works for someone who has not accepted yet.

Everyone who joins can enter other people in the same way, and you can see every account in the back room.

### Accepting an invitation

The new person opens the link and sees who entered them and the details that were entered. They can correct their own name, country and postal code. How they know the person who entered them stays as it was entered. They choose a password of at least 10 characters. Their phone or browser may offer a strong password and remember it, which is the easiest way. Then they are signed in.

If the link has expired, they can ask for a new one, or use **Forgot your password?** on the sign in page with the address they were entered with. That sends them a fresh invitation.

### Signing in and passwords

People sign in with their email address and password, and stay signed in on that phone or computer for thirty days.

* **Forgot your password?** on the sign in page emails a link to choose a new password. The link works once, for one hour. The page says the same thing whatever address is typed, so it never tells a stranger who is taking part.
* **Your account**, at the top of the page, is where people change their password. Changing it signs them out on every other phone or computer.

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

Every account is listed with its email address, who entered it and how they know each other, the date it was entered, and where it stands: joined, invited but not accepted yet, invitation expired, or switched off. Your own account says **first account**, because nobody entered you.

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
* **Merge** brings another issue into this one. Its claims, solutions, evidence and the issues that are part of it move here, and the other issue is removed. The page asks first, because a merge cannot be undone.

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
* **DeepSeek** costs a few cents for a busy week. You pay in advance by adding credit.
* **Neo4j Aura** is free. Never upgrade to Aura Professional for this site. It is far more than a test needs and it costs real money every month.
* **UptimeRobot** and **GitHub** are free.

## If the record is ever lost

If Aura deletes your instance, the site shows an error and your record is gone from Aura. The last copy you downloaded is what you can get back. This is why regular copies matter.

1. In the Aura console, create a new free instance. Download the credentials file straight away, because the password is shown only once.
2. In Render, under Environment, fill in `NEO4J_URI`, `NEO4J_PASSWORD` and `NEO4J_DATABASE` from that file. The database name is the instance id, a short code, not the word neo4j. Save.
3. Ask whoever helps you with the site to put your last downloaded copy into the new, empty instance. They need the file and about ten minutes. A copy holds no passwords, so afterwards everyone, you included, chooses a new password with **Forgot your password?**.
4. If you have no copy, the accounts are gone too. Ask whoever helps you to make your first account again, as on the setup call. Then open the back room, press **Reload seed** to start again from the starting statements, and enter people again.

## Dictation

If your browser offers Dictate, press it and speak. The button says "Listening… press to stop". Press it again to stop, then check and edit the text before reading or posting it. If Dictate is missing or does not work, type the statement instead.

## A few things testers may notice

The site asks each person to wait twenty seconds between posts, so nobody can flood the record. A tester who posts twice quickly sees a short message asking them to wait a moment.

A tester can leave the text box empty, fill in the issue, claim, evidence or solution by hand, and post that. The lines shown under "What this will add" become the statement.

Names for issues, claims, evidence and solutions can be up to three hundred characters. A long one wraps onto more lines rather than being cut off. If a tester's long name was shortened to fit, the form says so and they can edit it.

On an issue page, each solution has an **Approve** and an **Oppose** button. Each person holds one position on each solution: pressing the other button switches it, and pressing the same button again withdraws it. Solutions are listed by approvals minus oppositions.

People can **Edit** or **Delete** their own posts, and nobody else's. Editing a post changes only what that post says. To rename an issue, use **Tidy this issue** at the foot of the issue page. An edited post says "edited". Deleting a post removes what it claimed, proposed and cited, unless something else still uses it. Its approvals and oppositions stay; they are changed with the buttons on the issue page.

The Issues page has a search box. It finds issues, solutions, evidence and posts that hold every word typed, or words that start with it. Searching by meaning comes in a later phase.

## Who to ask

For accounts, entering people and the back room, you are in charge. For anything that means changing how the site works, or putting a copy back, ask a developer. The list of things planned for later came with this guide. Hand it to whoever helps you, so nobody starts from scratch.
