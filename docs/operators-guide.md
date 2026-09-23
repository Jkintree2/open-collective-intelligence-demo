# Open Collective Intelligence: the operator's guide

This guide is for the person who runs the site. It covers the everyday jobs, the few emails that need you, and what to do when something stops. You do not need to write any code to follow it.

## What the site is

The site is a closed test of a shared record. A small group of people write short statements about issues they care about. A reading service suggests the issue, the claim, any evidence and any solution in each statement. The writer checks and corrects that, then posts it. Every post joins one record that everyone with the passphrase can read.

The site lives in three places, all in your name:

* **GitHub** keeps the code.
* **Render** runs the website and gives it its address.
* **Neo4j Aura** keeps the record itself, like a notebook.

A fourth company, **DeepSeek**, runs the reading service. You pay it a few cents as statements are read.

## Letting someone in

Anyone who wants to use the site needs the passphrase. Send it to them yourself, by email or in person. They type it once and their browser remembers it for thirty days.

Only give it to people you are happy to have in the test. The passphrase is the only lock on the front door.

## Changing the passphrase or the sentence at the top

Both live in Render, not in the code.

1. Sign in to Render and open your service.
2. Click **Environment**.
3. To change the passphrase, edit `DEMO_PASSPHRASE`. To change the sentence at the top of the page, edit `SITE_SENTENCE`. The site name is `SITE_NAME`.
4. Click **Save**. Render restarts the site. This takes a few minutes.

After a passphrase change, everyone has to type the new one, including you. Tell your testers before you change it.

## The back room

The back room is where you look after the record. Add `/admin` to the end of the site address. Your browser asks for a username and a password. Type any username. The password is your back room password (see the next section). Keep that password to yourself.

The page shows how many records and connections there are, the last problem the reading service reported, and the latest fifty posts. The problem line clears itself when the site restarts.

**Download a copy** saves the whole record to your computer as one file. Do this often, and always before a reset. Keep the file somewhere private, because it holds everything people wrote.

**Reload seed** adds back any of the starting statements that are missing. It does not remove anything.

**Reset to seed** clears the whole record and puts back only the starting statements. Download a copy first. You have to type RESET to confirm.

**Delete** next to a post removes that statement and the claims, citations, proposals and evidence links it created. An issue, solution or piece of evidence goes too, but only when that post touched it, it is not a starting item, and nothing else is linked to it. People and starting items always stay. Links between solutions and issues, approvals, oppositions and the way issues sit inside each other also stay, even when they began with the deleted post.

A developer can put a downloaded copy back into an empty record. There is no button for that yet.

## Where the back room password is

Render made the password for you when the site was set up. To see it:

1. Sign in to Render and open your service.
2. Click **Environment**.
3. Find `ADMIN_TOKEN` and click the eye icon to show it.

You can copy it into your password manager. If you ever change it in Render, the old one stops working after the site restarts.

## Adding a starting statement

There is no separate list to edit. To add a statement you want everyone to see, post it on the site under your own name, like any tester.

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

Two kinds of email need action. Always sign in by typing the company's address into your browser yourself, rather than clicking a link in the email. That way a fake email cannot trick you.

* **From Neo4j, about a paused instance or a planned deletion.** Wake the instance as described above.
* **From UptimeRobot, saying the site is down.** Open the site yourself. If it loads after about thirty seconds, it was only asleep and you can ignore the alert. If it shows the "asleep" page, wake the record. If it shows an error for more than ten minutes, contact whoever helps you with the site.

Emails that need nothing from you: receipts from DeepSeek, notices from Render that the site was deployed, newsletters from any of the four companies, and a later UptimeRobot email saying the site is up again.

## When reading stops

If "Read my statement" stops filling in the form, testers can still fill it in by hand and post. Nothing is lost. To get reading working again:

1. **Check your DeepSeek balance first.** Sign in to the DeepSeek platform. If the balance is at or near zero, add a few dollars.
2. **Then look at the reading service line in the back room.** It shows the last problem DeepSeek reported. A problem with the key or the balance shows there.
3. If you made a new DeepSeek key, put it in Render under Environment as `LLM_API_KEY` and save.

## Before you widen the circle

The site was built for a small, trusted group. Before you give the passphrase to many more people, keep these points in mind:

* It is a closed test. The passphrase is the only lock.
* DeepSeek, an outside company, reads every statement that goes through "Read my statement". People should not write anything they would not want a company to store.
* Names are not checked. Anyone can post under any name, including yours.
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
3. Ask whoever helps you with the site to put your last downloaded copy into the new, empty instance. They need the file and about ten minutes.
4. If you have no copy, open the back room and press **Reload seed** to start again from the starting statements.

## Dictation

If your browser offers Dictate, press it and speak. The button says "Listening… press to stop". Press it again to stop, then check and edit the text before reading or posting it. If Dictate is missing or does not work, type the statement instead.

## A few things testers may notice

The site asks each person to wait twenty seconds between posts, so nobody can flood the record. A tester who posts twice quickly sees a short message asking them to wait a moment.

A tester can leave the text box empty, fill in the issue, claim, evidence or solution by hand, and post that. The lines shown under "What this will add" become the statement.

Names for issues, claims, evidence and solutions can be up to three hundred characters. A long one wraps onto more lines rather than being cut off. If a tester's long name was shortened to fit, the form says so and they can edit it.

## Who to ask

For the accounts, passwords and the passphrase, you are in charge. For anything that means changing how the site works, or putting a copy back, ask a developer. The list of things planned for later came with this guide. Hand it to whoever helps you, so nobody starts from scratch.
