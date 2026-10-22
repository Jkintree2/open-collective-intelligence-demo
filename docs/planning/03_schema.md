# 03. Graph schema for 0.1

> **Revised 5 September 2026 after REVIEW.md.** Changed: `display_name` is null on anonymous posts (M7); name cleaning and key rules tightened (m6, m7, m8, M4); `PART_OF` guards for a parent that is a sub-issue and a child that already has a parent (M2, M3); Q1 computes `last_activity` over every edge and returns person keys so top-level rows rank on inclusive counts (C7, m4); Q6 includes children's posts (m5); Q8 is capped and uncached (M4, M20); Q11 keeps MERGEd edges and deletes orphaned non-seed nodes (M4, M9); the worked example follows the corrected case 1 (C6).

> **Extended 4 October 2026 for Phase 1 (People and positions, SOW 0.2).** Added: accounts on `Person`, the `ENTERED`, `MADE` and `CHANGED` relationships, the `Change` label, one stance per person, `Post.edited_at`, full-text indexes, and queries Q12 to Q33; Q1, Q4, Q7, Q10, the write path's stance statement and the export format are revised. See "Phase 1: people and positions" at the end. Everything in that section ships behind the `ACCOUNTS_ENABLED` setting except search.

Neo4j Aura Free, Neo4j 5 Cypher. John's README vocabulary plus only what the kickoff decisions require: sub-issues, an anonymous flag on relationships, a source link on Evidence, timestamps, and a Post node so every edge traces back to the text that produced it.

## Node labels

| Label | Properties | Notes |
|---|---|---|
| `Person` | `key` (unique), `name` (string or null), `anonymous` (bool), `created_at` | `key` is `name:<normalised name>` for a named tester, `anon:<uuid>` for an anonymous one. An anonymous Person has `name = null` and is displayed as "Anonymous". A browser gets one anonymous key, held in a cookie, so an anonymous tester's posts count as one person. |
| `Issue` | `key` (unique), `name`, `created_at`, `seed` (bool) | Top level or sub-issue. A sub-issue has exactly one outgoing `PART_OF`; the write path's guards keep it that way (first parent wins, and a sub-issue can never be a parent). |
| `Solution` | `key` (unique), `name`, `created_at`, `seed` | |
| `Evidence` | `key` (unique), `name`, `url` (string or null), `created_at`, `seed` | `name` is the citation as a short title ("2024 NOAA flooding survey"). `url` optional. Never fetched in 0.1 and Phase 1; from Phase 2, read once when a writer asks for a check (see "Phase 2: evidence that checks itself"). |
| `Post` | `id` (unique uuid), `text`, `created_at`, `anonymous`, `display_name` (null when `anonymous`; the name is never stored for an anonymous post), `seed`, `source` (`model`, `manual`, `seed`), `extraction_raw` (string, the model's JSON as returned, or null), `model`, `latency_ms` | The audit record. Every relationship created by a post carries `post_id`, so the feed, the "posts about this issue" list, and "it did something weird" debugging all start here. |

`key` for Issue, Solution and Evidence is the normalised name: Unicode NFKC, lowercase, non-alphanumerics collapsed to single spaces, trimmed, a leading "the", "a" or "an" removed only when it is followed by a space (so "A/B testing" keeps its A). A key shorter than two characters after normalisation is rejected, so "The" or "!!!" can never become a node. "The need for world government" and "Need for world government" share a key. The displayed `name` is whatever the first poster wrote, cleaned: newlines to spaces, trimmed, capped at 300 characters, the first character upper-cased only when it is lower-case and the second is not upper-case ("iPhone" and "eBay" survive), and a trailing `.,;:!?` removed.

## Relationship types

Names are John's README verbs exactly. Direction is always from the actor or source to the thing acted on.

| Type | From | To | Properties | Cardinality |
|---|---|---|---|---|
| `POSTED` | Person | Post | `created_at` | one per post |
| `CLAIM` | Person | Issue | `post_id`, `anonymous`, `created_at` | one per post that claims the issue (CREATE, not MERGE). "Claims" counts these; "people" counts distinct Person. |
| `SUBMIT` | Person | Evidence | `post_id`, `anonymous`, `created_at` | one per post |
| `PROPOSE` | Person | Solution | `post_id`, `anonymous`, `created_at` | one per post |
| `HAVE_PROPOSED` | Issue | Solution | `post_id`, `created_at` | MERGE: one per issue and solution pair. Records the first post that put the solution on the table for that issue. |
| `SUPPORTS` | Evidence | Issue, Solution or Evidence | `post_id`, `created_at` | one per post |
| `REFUTES` | Evidence | Issue, Solution or Evidence | `post_id`, `created_at` | one per post |
| `APPROVE` | Person | Solution | `post_id`, `anonymous`, `created_at`, `last_post_id` | MERGE: one per person and solution, so "approved by N" counts people, not posts. |
| `OPPOSE` | Person | Solution | same as APPROVE | MERGE, one per person and solution |
| `PART_OF` | Issue | Issue | `post_id`, `created_at` | MERGE. One level deep in 0.1: the parent must not itself have a `PART_OF`, and a child that already has a parent keeps it. Both guards are in the write path's WHERE clause; a requested parent that is itself a sub-issue is replaced by that sub-issue's parent in Python before the transaction. |

A person can hold both `APPROVE` and `OPPOSE` on the same solution if they posted both. The counts show both. Reconciling stances is the voting layer, out of scope (addendum 01). **Phase 1 replaces this rule:** one stance per person and solution from then on; pairs left from 0.1 stay until that person takes a new stance (see "Stances" in the Phase 1 section).

### DECIDE is out

John's README has "Assemblies and juries of people DECIDE on issues." It needs an Assembly or Jury node type, a membership model, a decision process and a record of outcomes. All of that is the voting and decision layer that the SOW puts under sentiment and trend analysis and the addendum explicitly leaves out of 0.1. Nothing in the demo would create or read it. Leaving the type out costs nothing; adding it empty would invite the question "where are the decisions?".

### Why a Post node

The SOW does not name it. It is the cheapest way to get four things the decisions require: a feed of raw text in order, the structure "pulled out of each post" as labels, the link from any node back to the posts that created it, and a place to keep the model's raw JSON for debugging. Without it, the feed would have to be reconstructed from edge timestamps.

## Constraints and indexes

Run once at startup (idempotent) and from the seed script.

```cypher
CREATE CONSTRAINT person_key   IF NOT EXISTS FOR (p:Person)   REQUIRE p.key IS UNIQUE;
CREATE CONSTRAINT issue_key    IF NOT EXISTS FOR (i:Issue)    REQUIRE i.key IS UNIQUE;
CREATE CONSTRAINT solution_key IF NOT EXISTS FOR (s:Solution) REQUIRE s.key IS UNIQUE;
CREATE CONSTRAINT evidence_key IF NOT EXISTS FOR (e:Evidence) REQUIRE e.key IS UNIQUE;
CREATE CONSTRAINT post_id      IF NOT EXISTS FOR (p:Post)     REQUIRE p.id IS UNIQUE;
CREATE INDEX post_created      IF NOT EXISTS FOR (p:Post)     ON (p.created_at);
```

No relationship property indexes in 0.1. The feed looks up edges by `post_id` for a page of thirty posts; at demo scale (hundreds of posts) that is milliseconds. Add `CREATE INDEX claim_post IF NOT EXISTS FOR ()-[r:CLAIM]-() ON (r.post_id)` and siblings only if the feed query exceeds 200 ms in the logs.

## The write path: merging one post

One write transaction (`session.execute_write`) running the statements below in order, all parameterised, from the validated card payload (`05_extraction.md`, "Card payload"). Names are normalised to keys in Python before the transaction. If anything fails the transaction rolls back and the tester sees "Nothing was added; please try again."

```cypher
// 1. Person
MERGE (p:Person {key: $person_key})
ON CREATE SET p.name = $name, p.anonymous = $anonymous, p.created_at = datetime()
ON MATCH  SET p.name = coalesce($name, p.name);

// 2. Post
MATCH (p:Person {key: $person_key})
CREATE (post:Post {
  id: $post_id, text: $text, created_at: datetime(),
  anonymous: $anonymous, display_name: $display_name, seed: false,
  source: $source, extraction_raw: $extraction_raw,
  model: $model, latency_ms: $latency_ms
})
CREATE (p)-[:POSTED {created_at: datetime()}]->(post);

// 3. For each issue in the payload
MERGE (i:Issue {key: $issue_key})
ON CREATE SET i.name = $issue_name, i.created_at = datetime(), i.seed = false
WITH i
MATCH (p:Person {key: $person_key})
CREATE (p)-[:CLAIM {post_id: $post_id, anonymous: $anonymous, created_at: datetime()}]->(i);

// 3b. If the issue names a parent (sub-issue). Python has already replaced a parent that is
//     itself a sub-issue with that sub-issue's parent. The parent must exist and be top level,
//     and the child must not already have a parent (first parent wins).
MATCH (child:Issue {key: $issue_key}), (parent:Issue {key: $parent_key})
WHERE child <> parent
  AND NOT (parent)-[:PART_OF]->(:Issue)
  AND NOT (child)-[:PART_OF]->(:Issue)
MERGE (child)-[r:PART_OF]->(parent)
ON CREATE SET r.post_id = $post_id, r.created_at = datetime();

// 4. For each solution in the payload (for_issue is required)
MERGE (s:Solution {key: $solution_key})
ON CREATE SET s.name = $solution_name, s.created_at = datetime(), s.seed = false
WITH s
MATCH (p:Person {key: $person_key}), (i:Issue {key: $for_issue_key})
CREATE (p)-[:PROPOSE {post_id: $post_id, anonymous: $anonymous, created_at: datetime()}]->(s)
MERGE (i)-[hp:HAVE_PROPOSED]->(s)
ON CREATE SET hp.post_id = $post_id, hp.created_at = datetime();

// 4b. Stance, only when the payload says approve or oppose ($stance_type is APPROVE or OPPOSE,
//     substituted in Python from a whitelist; relationship types cannot be parameters)
MATCH (p:Person {key: $person_key}), (s:Solution {key: $solution_key})
MERGE (p)-[r:APPROVE]->(s)
ON CREATE SET r.post_id = $post_id, r.anonymous = $anonymous, r.created_at = datetime()
ON MATCH  SET r.last_post_id = $post_id;

// 5. For each evidence item
MERGE (e:Evidence {key: $evidence_key})
ON CREATE SET e.name = $evidence_name, e.url = $url, e.created_at = datetime(), e.seed = false
ON MATCH  SET e.url = coalesce(e.url, $url)
WITH e
MATCH (p:Person {key: $person_key})
CREATE (p)-[:SUBMIT {post_id: $post_id, anonymous: $anonymous, created_at: datetime()}]->(e);

// 5b. Evidence stance toward its target. $target_label is Issue, Solution or Evidence and
//     $rel is SUPPORTS or REFUTES, both substituted from whitelists in Python.
MATCH (e:Evidence {key: $evidence_key}), (t:Issue {key: $target_key})
CREATE (e)-[:SUPPORTS {post_id: $post_id, created_at: datetime()}]->(t);
```

Rules applied in Python before the transaction:

* Every solution must name an issue from the same payload or an existing issue. If the model returned a solution with no issue, the card forces the tester to pick one before Post is enabled.
* Every evidence item must name a target from the payload or the graph. Default target is the first issue in the payload.
* A parent that does not exist is dropped (the issue becomes top level) and logged. A parent that is itself a sub-issue is replaced by its own parent and logged. A child that already has a parent keeps it; the request is logged and ignored.
* Node names go through `clean_name()` and keys through `make_key()` as defined above; a name whose key is rejected is dropped from the payload with a message on the card.
* A position (approve or oppose) on a solution the record already lists under that issue writes only the `APPROVE` or `OPPOSE` edge: no `PROPOSE`, no `HAVE_PROPOSED`. An existing issue whose only part in the post is to hold such positions is not claimed again; a new solution, evidence or sub-issue for it keeps the claim. The issue page still lists the post through the stance edge (GitHub issue 4, October 2026).
* When `anonymous` is true, `display_name` is stored as null and the poster's name cookie is left untouched.
* Empty payload (no issues, no solutions, no evidence) is still stored as a Post with `source = manual` and no edges, so the feed shows what the tester wrote. This is the "post as a raw statement" path of Session 1.

## Read queries

### Q1. Issues list with counts, three sorts

```cypher
MATCH (i:Issue)
OPTIONAL MATCH (i)-[:PART_OF]->(parent:Issue)
OPTIONAL MATCH (p:Person)-[c:CLAIM]->(i)
WITH i, parent, c, p.key + CASE WHEN coalesce(c.anonymous, false) THEN '|anonymous' ELSE '' END AS who
WITH i, parent, count(c) AS claims, count(DISTINCT who) AS people, collect(DISTINCT who) AS person_keys
OPTIONAL MATCH (i)-[:HAVE_PROPOSED]->(s:Solution)
WITH i, parent, claims, people, person_keys, count(DISTINCT s) AS solutions
// evidence attached to the issue itself (0 hops) or to any of its solutions (1 hop)
OPTIONAL MATCH (ev:Evidence)-[:SUPPORTS|REFUTES]->(t)<-[:HAVE_PROPOSED*0..1]-(i)
WITH i, parent, claims, people, person_keys, solutions,
     collect(DISTINCT ev.key) AS evidence_keys
// last activity: the newest edge of any type that touches the issue, so a post that only
// adds evidence or a solution still bumps "Most recent"
OPTIONAL MATCH (i)-[any]-() WHERE type(any) <> 'CHANGED' AND NOT (type(any) = 'PART_OF' AND any.post_id IS NULL)
WITH i, parent, claims, people, person_keys, solutions, evidence_keys,
     coalesce(max(any.created_at), i.created_at) AS last_activity
RETURN i.key AS key, i.name AS name, i.seed AS seed,
       parent.key AS parent_key, parent.name AS parent_name,
       claims, people, person_keys, solutions,
       size(evidence_keys) AS evidence, evidence_keys, last_activity
```

No `ORDER BY` in Cypher: the rows are grouped and sorted in Python, because a top-level issue is ranked on its whole family, not on its own counts (review C7: otherwise any friend's one-line post outranks the seed conversation). `group_issues(rows, sort)`:

1. Rows with `parent_key = null` are top level; every other row is attached under its parent.
2. For each top-level row compute inclusive counts: `people` as the size of the union of `person_keys` across the row and its children; `claims` and `solutions` summed; `evidence` as the size of the union of `evidence_keys`; `last_activity` as the max. Keep the row's own counts too.
3. Sort top-level rows, then each row's children, by the chosen key:
   * `people` (label "Most people"): inclusive people desc, inclusive claims desc, last activity desc. On day one every seed claim is from one of three seed persons, so claim count and the file's dates decide the order among sub-issues, which is what gives the seed its shape.
   * `recent`: last activity desc.
   * `evidence`: inclusive evidence desc, inclusive claims desc, last activity desc.

The page shows top-level issues in sort order, each followed by its indented sub-issues. A top-level row with children reads "3 people · 13 claims in total · 1 claim on the issue itself · 4 solutions · 14 pieces of evidence"; a row without children reads "3 people · 5 claims · 2 solutions · 4 pieces of evidence".

### Q2. Issue detail: header, parent, children

```cypher
MATCH (i:Issue {key: $key})
OPTIONAL MATCH (i)-[:PART_OF]->(parent:Issue)
OPTIONAL MATCH (child:Issue)-[:PART_OF]->(i)
RETURN i.key AS key, i.name AS name, i.created_at AS created_at,
       parent.key AS parent_key, parent.name AS parent_name,
       [c IN collect(DISTINCT child) | {key: c.key, name: c.name}] AS children
```

### Q3. Issue detail: who claims it

Revised for Phase 1 (D2): a person is counted once for their named claims and once, apart, for their anonymous claims, so no page can link an anonymous post to a name. A missing flag counts as named. For 0.1 records the numbers are unchanged.

```cypher
MATCH (p:Person)-[c:CLAIM]->(i:Issue {key: $key})
WITH p.key + CASE WHEN coalesce(c.anonymous, false) THEN '|anonymous' ELSE '' END AS who,
     coalesce(c.anonymous, false) AS hidden, p.name AS name, count(c) AS claims
RETURN sum(claims) AS claims, count(who) AS people,
       collect(DISTINCT CASE WHEN hidden THEN 'Anonymous' ELSE name END) AS names
```

### Q4. Issue detail: solutions with stance counts and evidence

```cypher
MATCH (i:Issue {key: $key})-[:HAVE_PROPOSED]->(s:Solution)
OPTIONAL MATCH (pp:Person)-[pr:PROPOSE]->(s)
OPTIONAL MATCH (pa:Person)-[:APPROVE]->(s)
OPTIONAL MATCH (po:Person)-[:OPPOSE]->(s)
WITH s, count(DISTINCT pp.key + CASE WHEN coalesce(pr.anonymous, false) THEN '|anonymous' ELSE '' END) AS proposers,
     count(DISTINCT pa) AS approves, count(DISTINCT po) AS opposes
OPTIONAL MATCH (ev:Evidence)-[r:SUPPORTS|REFUTES]->(s)
WITH s, proposers, approves, opposes,
     [x IN collect(DISTINCT {key: ev.key, name: ev.name, url: ev.url, stance: type(r)})
        WHERE x.key IS NOT NULL] AS evidence
RETURN s.key AS key, s.name AS name, proposers, approves, opposes, evidence
ORDER BY proposers DESC, approves DESC, s.created_at ASC
```

Display: "proposed by 2, approved by 3, opposed by 1", raw numbers only (addendum 01: no bars, no percentages).

### Q5. Issue detail: evidence about the issue itself

```cypher
MATCH (ev:Evidence)-[r:SUPPORTS|REFUTES]->(i:Issue {key: $key})
OPTIONAL MATCH (p:Person)-[sub:SUBMIT]->(ev)
RETURN ev.key AS key, ev.name AS name, ev.url AS url, type(r) AS stance,
       collect(DISTINCT CASE WHEN sub.anonymous THEN 'Anonymous' ELSE p.name END) AS submitted_by
ORDER BY stance, ev.created_at
```

### Q6. Posts about an issue (any edge that touches it, via post_id)

```cypher
// the issue itself plus, on a parent page, its sub-issues
MATCH (i:Issue {key: $key})
OPTIONAL MATCH (child:Issue)-[:PART_OF]->(i)
WITH i, collect(child) AS children
UNWIND [i] + children AS x
MATCH (x)-[r]-()
WHERE r.post_id IS NOT NULL
WITH DISTINCT r.post_id AS pid
MATCH (post:Post {id: pid})
RETURN post.id AS id, post.text AS text, post.display_name AS display_name,
       post.anonymous AS anonymous, post.created_at AS created_at
ORDER BY post.created_at DESC
LIMIT 60
```

### Q7. Feed page

```cypher
MATCH (post:Post)
RETURN post.id AS id, post.text AS text, post.display_name AS display_name,
       post.anonymous AS anonymous, post.created_at AS created_at, post.seed AS seed
ORDER BY post.created_at DESC
SKIP $skip LIMIT $limit
```

Then one query for the structure of the page's posts, grouped by `post_id` in Python:

```cypher
MATCH (a)-[r]->(b)
WHERE r.post_id IN $post_ids
RETURN r.post_id AS post_id, labels(a)[0] AS from_label, a.key AS from_key, a.name AS from_name,
       type(r) AS rel, labels(b)[0] AS to_label, b.key AS to_key, b.name AS to_name,
       r.anonymous AS anonymous
ORDER BY r.created_at
```

The feed shows each post's chips (one per distinct Issue, Solution, Evidence touched, linking to the issue page) and, expanded on tap, the sentences in John's format. Person names on edges with `anonymous = true` render as "Anonymous".

### Q8. Candidates for the extraction prompt and the card's autocomplete

```cypher
// issues: the 50 most claimed plus the 20 most recently created, so a junk name with no
// claims ages out of the prompt and a name created a second ago is offered to the next post
CALL {
  MATCH (i:Issue)
  OPTIONAL MATCH (i)<-[c:CLAIM]-()
  WITH i, count(c) AS claims
  ORDER BY claims DESC, i.created_at DESC LIMIT 50
  RETURN i
  UNION
  MATCH (i:Issue)
  WITH i ORDER BY i.created_at DESC LIMIT 20
  RETURN i
}
OPTIONAL MATCH (i)-[:PART_OF]->(parent:Issue)
RETURN i.name AS name, i.key AS key, parent.name AS parent
ORDER BY parent IS NOT NULL, i.name;

MATCH (s:Solution)
OPTIONAL MATCH (i:Issue)-[:HAVE_PROPOSED]->(s)
RETURN s.name AS name, collect(DISTINCT i.name) AS for_issues
ORDER BY s.created_at DESC LIMIT 200;

MATCH (e:Evidence)
RETURN e.name AS name, e.url AS url
ORDER BY e.created_at DESC LIMIT 200;
```

Three lists, queried fresh on every extraction call and every card open. No cache: at demo scale these take milliseconds, and a cache made a just-created issue invisible to the next post (review M20). They feed both the prompt's candidate section (where sub-issues are marked "part of X; cannot be a parent") and the `<datalist>` elements on the card (which get every issue, not the capped 70; a second uncapped query for names only).

### Q9. Health and admin counts

```cypher
RETURN 1 AS ok;

MATCH (n) RETURN labels(n)[0] AS label, count(*) AS n ORDER BY label;
```

### Q10. Reset (admin, destructive)

```cypher
MATCH (n) DETACH DELETE n
```

At demo scale this runs in one transaction in under a second. If the graph ever exceeds a few tens of thousands of nodes, switch to `CALL { ... } IN TRANSACTIONS` from an auto-commit session. Reset is always followed by the seed load.

### Q11. Delete one post (admin)

Two statements in one transaction.

```cypher
// 1. delete the post and the per-post edges it created; MERGEd types stay
MATCH (post:Post {id: $id})
OPTIONAL MATCH (a)-[r]->(b)
WHERE r.post_id = $id
  AND type(r) IN ['CLAIM', 'SUBMIT', 'PROPOSE', 'SUPPORTS', 'REFUTES']
WITH post, collect(DISTINCT a.key) + collect(DISTINCT b.key) AS touched, collect(r) AS rels
FOREACH (x IN rels | DELETE x)
DETACH DELETE post
RETURN [k IN touched WHERE k IS NOT NULL] AS touched;

// 2. delete any non-seed Issue, Solution or Evidence the post left with no relationships
MATCH (n)
WHERE n.key IN $touched
  AND (n:Issue OR n:Solution OR n:Evidence)
  AND coalesce(n.seed, false) = false
  AND NOT (n)--()
DELETE n
```

Removes the post, the claim, submit, propose, supports and refutes edges it created, and any node that this post alone created (so an offensive or injected issue name leaves the Issues page and the candidate list with the post, review M4). MERGEd edges (`HAVE_PROPOSED`, `APPROVE`, `OPPOSE`, `PART_OF`) are kept even when their `post_id` is this post, because later posts may rely on them (review M9); a dangling `post_id` on such an edge is harmless. A seed node is never deleted this way. The operator's guide describes exactly this.

An issue that has been tidied keeps its change record (`CHANGED`), so `NOT (n)--()` is false for it: deleting its last post leaves it on the Issues page with its history. John can merge it away if it is no longer wanted (Q30 deletes the merged issue).

## Worked example

John's drug policy statement, named, with the explicit-stance rule from `05_extraction.md`:

```
(:Person {key:'name:john kintree', name:'John Kintree'})
  -[:POSTED]->(:Post {id:'…', text:'The problem of drug dealing could be reduced by…'})
  -[:CLAIM {post_id}]->(:Issue {key:'drug dealing problem', name:'Drug dealing problem'})
  -[:PROPOSE {post_id}]->(:Solution {key:'decriminalize drug sales', name:'Decriminalize drug sales'})
  -[:PROPOSE {post_id}]->(:Solution {key:'treat drug use as medical issue', name:'Treat drug use as medical issue'})
(:Issue {drug dealing problem})-[:HAVE_PROPOSED]->(:Solution {decriminalize drug sales})
(:Issue {drug dealing problem})-[:HAVE_PROPOSED]->(:Solution {treat drug use as medical issue})
(:Person {john kintree})-[:APPROVE {post_id}]->(:Solution {treat drug use as medical issue})
```

No `PART_OF` (drug dealing is a new top-level issue), no `Evidence`. One `APPROVE`, on "Treat drug use as medical issue", because "Deal with it as a medical issue" is an imperative; none on "Decriminalize drug sales" ("could be reduced by") unless John ticks "I approve this" on the card.

## Phase 1: people and positions

Added 4 October 2026 at Gate 0 of Phase 1. This section is the binding spec for the Phase 1 code; nothing in it is built before it is agreed here. New Cypher lives in the `graph*.py` modules (for example `graph_accounts.py`, `graph_tidy.py`), with relationship types and labels substituted only from whitelists, as before.

### Decisions recorded here

| | Decision |
|---|---|
| Invitations (John, 2 October 2026) | An accepted member enters a person who has agreed in advance: name, email, country, postal code, and how they know each other. The person accepts through an emailed link that works once and chooses their own password. No password is ever sent by email. Emails go from jkintree@gmail.com. Each new person can then enter others. |
| D1 Email | Sent through the Gmail API with only the `gmail.send` permission on John's account, over HTTPS with `httpx`. Behind one function, `mailer.send(to, subject, text) -> bool`, so a platform address can replace it later. |
| D2 Anonymous posts | "Post anonymously" changes what is shown, not who the post belongs to. Every post and stance hangs off the signed-in account, so the person can edit or delete their anonymous posts; on public counts an account's anonymous posts count apart from its named ones (see Q3), so no page links an anonymous post to a name. |
| D3 People from the test weeks | `name:` and `anon:` Persons from 0.1 stay as they are, with their posts and stances. Accounts are new Persons. Nothing is linked or moved automatically. |
| D4 Passwords | At least 10 characters, no other rules. Invitation links last 14 days, password links 1 hour. One live link per person: a new link replaces the old one, and using a link clears it. A password link is sent only to an accepted, active account. "Forgot your password?" for someone entered but not yet accepted sends a fresh invitation link instead, with the same message and limits, so a lost or expired invitation never leaves anyone stuck. |
| D5 Tidying | Only accounts with `admin = true` (John's) move, rename and merge issues. Every change writes a `Change` that every member can read. |
| D6 Entering a person | `ENTERED` from inviter to person, carrying the relationship the inviter declares and `agreed: true` from the form's tick. Any accepted, active member can enter others. |
| D7 Stances | One stance per person and solution from Phase 1 on: a new stance replaces that person's opposite one, by click or by a post made with accounts on, for every Person. Pairs left from 0.1 stay and count both ways (net zero) until that person takes a new stance on that solution. Until `ACCOUNTS_ENABLED` is set, posts and the issue page work exactly as in 0.1 (decision X1, 5 October 2026). |
| D8 Between entry and acceptance | Entry creates the account Person, without a password, and its `ENTERED` in one transaction. Until acceptance the person cannot sign in, post or take a stance, and appears nowhere public. The person may correct their own name, country and postal code when accepting; the relationship stays as declared. The inviter or John may send the invitation again, or withdraw an entry never accepted. |

### Person, extended for accounts

An account is a `Person` with an `email`. Persons from 0.1 have no `email` and none of the properties below, and every constraint below ignores them.

| Property | Value | Notes |
|---|---|---|
| `key` | `acct:<uuid4>` | Never derived from the name or the email, so two people with one name stay two people. |
| `name` | string | Required. Shown on the person's named posts. `clean_name()`, at most 120 characters, and `make_key()` must accept it. |
| `anonymous` | `false` | Anonymity belongs to a post, never to an account. |
| `seed` | `false` | |
| `email` | string | Trimmed and lower-cased before it is stored or looked up; unique. Shown only to the person, the person who entered them, and the back room. |
| `country`, `postal_code` | string | As entered, at most 80 and 20 characters. Shown only where `email` is. |
| `password_hash` | string or null | `scrypt$<n>$<r>$<p>$<salt>$<hash>` from `hashlib.scrypt` (n 16384, r 8, p 1, 16 byte random salt, base64), compared in constant time. Null until accepted, and after a restore. |
| `admin` | bool | `true` only on John's account, set by `scripts/make_admin.py`. |
| `active` | bool | `false` when switched off in the back room: cannot sign in; posts and stances stay. |
| `created_at` | datetime | When the person was entered (the plan's `entered_at`). |
| `accepted_at` | datetime or null | Null until the person accepts. The back room's "invited" means null. |
| `token_hash` | string or null | SHA-256 hex of the live link's secret (`secrets.token_urlsafe(32)`). The secret exists in plain text only inside the outgoing email; it is never stored, logged or shown. |
| `token_purpose` | `invite`, `reset` or null | |
| `token_expires_at` | datetime or null | |

`password_hash` and the three `token_*` properties are read only inside the accounts code: never returned to a template, never logged at any level, never exported.

**Being signed in.** No session store, as with the passphrase. The cookie holds the account key, an expiry thirty days ahead and an HMAC under `SECRET_KEY` over both plus a SHA-256 of the current `password_hash`. A password change or reset therefore signs out every other device. Every request reads the account (Q13) and treats it as signed out when it is missing, not active or not accepted.

### New relationship types and label

| Type | From | To | Properties | Cardinality |
|---|---|---|---|---|
| `ENTERED` | Person (account) | Person (account) | `relationship` (one of `family`, `neighbor`, `friend`, `work`, `school`, `health`, `organization`), `agreed` (`true`), `created_at` | Exactly one into every account except the root, John's, made by `make_admin.py`. Created with the Person in one transaction; never moved; removed only with a Person whose entry is withdrawn. |
| `MADE` | Person (admin) | Change | `created_at` | one per Change |
| `CHANGED` | Change | Issue | `created_at` | one per Change. On a merge it points at the issue that was kept, and the removed issue's earlier `CHANGED` edges move to the kept one. |

| Label | Properties | Notes |
|---|---|---|
| `Change` | `id` (unique uuid), `kind` (`move`, `rename`, `merge`), `created_at`, `details` | `details` is a JSON string, like `Post.payload`. move: `issue_key`, `issue_name`, `from_parent_key`, `from_parent_name`, `to_parent_key`, `to_parent_name` (parents null for top level). rename: `from_key`, `from_name`, `to_key`, `to_name`. merge: `kept_key`, `kept_name`, `merged_key`, `merged_name`, and `moved`, the number of relationships moved per type. |

Changes to existing types:

* `APPROVE` and `OPPOSE` made by a click carry `source: "click"`, `anonymous: false` and `created_at`, and no `post_id`. One per person and solution, as before; now never both (D7).
* `PART_OF` made by tidying carries `created_at` and no `post_id`.
* `Post` gains `edited_at` (datetime, null until its author edits it).

### Constraints and indexes

Added to the startup list, idempotent like the others:

```cypher
CREATE CONSTRAINT person_email IF NOT EXISTS FOR (p:Person) REQUIRE p.email IS UNIQUE;
CREATE CONSTRAINT person_token IF NOT EXISTS FOR (p:Person) REQUIRE p.token_hash IS UNIQUE;
CREATE CONSTRAINT change_id    IF NOT EXISTS FOR (c:Change) REQUIRE c.id IS UNIQUE;
CREATE FULLTEXT INDEX record_names IF NOT EXISTS FOR (n:Issue|Solution|Evidence) ON EACH [n.name];
CREATE FULLTEXT INDEX post_text    IF NOT EXISTS FOR (p:Post) ON EACH [p.text];
```

The token constraint doubles as the index for looking a link up.

### Accounts

**Q12. Enter a person.** One write transaction. Python has already cleaned every field, lower-cased the email, checked the relationship against the list and the tick, and made the link (`token`, `token_hash`). An email that is already taken fails on the constraint, and Python answers that it has been entered already; a double-submitted form takes that path too, so it can never make two accounts. The email is sent only after this commits. An address in anyone's `previous_emails` (change of email, X2) makes nothing and answers `used`, which Python treats as taken; the check sits in the same transaction as the write.

```cypher
MATCH (inviter:Person {key: $inviter_key})
WHERE inviter.active AND inviter.accepted_at IS NOT NULL
OPTIONAL MATCH (earlier:Person) WHERE $email IN coalesce(earlier.previous_emails, [])
WITH inviter, count(earlier) > 0 AS used
FOREACH (_ IN CASE WHEN used THEN [] ELSE [1] END |
  CREATE (p:Person {key: $key, name: $name, anonymous: false, seed: false,
                    email: $email, country: $country, postal_code: $postal_code,
                    admin: false, active: true, created_at: $now,
                    token_hash: $token_hash, token_purpose: 'invite', token_expires_at: $expires_at})
  CREATE (inviter)-[:ENTERED {relationship: $relationship, agreed: true, created_at: $now}]->(p))
RETURN used
```

**Entered moments ago (the double tap check).** Read after Q12 fails on the email constraint: the same inviter entering the same address that has not accepted, since a given time, is a form sent twice, not a duplicate. It answers the key of the person already entered.

```cypher
MATCH (:Person {key: $inviter_key})-[e:ENTERED]->(p:Person {email: $email})
WHERE e.created_at >= $since AND p.accepted_at IS NULL
RETURN p.key AS key
```

**John's root account.** Made once by `make_admin.py`: admin, active, no `ENTERED`, no link and no password, so nothing is sent and it cannot sign in until "Forgot your password?" gives it a link (Q17). An email already taken fails on the same constraint as Q12.

```cypher
CREATE (p:Person {key: $key, name: $name, anonymous: false, seed: false,
                  email: $email, country: $country, postal_code: $postal_code,
                  admin: true, active: true, created_at: $now})
```

**Q13. The signed-in account**, on every request:

```cypher
MATCH (p:Person {key: $key})
WHERE p.active AND p.accepted_at IS NOT NULL
RETURN p.key AS key, p.name AS name, p.email AS email, p.admin AS admin, p.password_hash AS password_hash
```

**Q14. Sign in.** Python checks the password against `password_hash` and gives one answer for a wrong password, an unknown email, an account not yet accepted and one switched off.

```cypher
MATCH (p:Person {email: $email})
RETURN p.key AS key, p.password_hash AS password_hash, p.active AS active, p.accepted_at AS accepted_at
```

**Q15. Open a link.** Python compares `purpose` with the page (accept or reset) and `expires_at` with now. No row means the link was used, replaced, withdrawn or never existed; the page cannot tell which and does not try.

```cypher
MATCH (p:Person {token_hash: $token_hash})
OPTIONAL MATCH (inviter:Person)-[e:ENTERED]->(p)
RETURN p.key AS key, p.name AS name, p.email AS email, p.country AS country,
       p.postal_code AS postal_code, p.active AS active, p.accepted_at AS accepted_at,
       p.token_purpose AS purpose, p.token_expires_at AS expires_at,
       inviter.name AS inviter_name, e.relationship AS relationship
```

**Lock first, then check** (Q16, Q17, Q18, Q21, as Q23, Q24 and Q28 do): each statement matches the person, takes the write lock with the no-op `SET p.key = p.key`, and only then checks its conditions. A transaction that matched before another one committed waits for it and then sees what it left: two accepts on one link succeed once, a withdrawal racing an accept leaves the accepted account, and a new link never lands on an account accepted meanwhile. The no-op `SET x.key = x.key` (or `x.id = x.id`) is safe only where that value never changes (Person keys, Post ids, Solution keys); a no-op on `token_hash` could write a stale value back. An Issue, whose key a rename changes, is locked with a transient property instead (`SET i.tidy_lock = true REMOVE i.tidy_lock`, never committed), because the no-op reads its value before the lock is granted and would write a stale key back.

**Q16. Accept an invitation.** The link is checked again after the lock, so a form sent twice accepts once and the second sees no row.

```cypher
MATCH (p:Person {token_hash: $token_hash})
SET p.key = p.key
WITH p
WHERE p.token_hash = $token_hash AND p.token_purpose = 'invite' AND p.token_expires_at > $now AND p.active
SET p.name = $name, p.country = $country, p.postal_code = $postal_code,
    p.password_hash = $password_hash, p.accepted_at = $now,
    p.token_hash = null, p.token_purpose = null, p.token_expires_at = null
RETURN p.key AS key
```

**Q17. A new link.** Sending an invitation again (inviter or back room) and asking for a password link both replace whatever link the person had.

```cypher
// invitation sent again: only while not accepted
MATCH (p:Person {key: $key})
SET p.key = p.key
WITH p
WHERE p.accepted_at IS NULL AND p.active
SET p.token_hash = $token_hash, p.token_purpose = 'invite', p.token_expires_at = $expires_at
WITH p
OPTIONAL MATCH (inviter:Person)-[e:ENTERED]->(p)
RETURN p.email AS email, p.name AS name, inviter.name AS inviter_name, e.relationship AS relationship;

// "Forgot your password?": an accepted, active account gets a password link; someone entered
// but not yet accepted gets a fresh invitation link; anyone else gets nothing, and the page
// says the same thing either way
MATCH (p:Person {email: $email})
SET p.key = p.key
WITH p
WHERE p.active
WITH p, CASE WHEN p.accepted_at IS NULL THEN 'invite' ELSE 'reset' END AS purpose
SET p.token_hash = $token_hash, p.token_purpose = purpose,
    p.token_expires_at = CASE purpose WHEN 'invite' THEN $invite_expires_at ELSE $reset_expires_at END
WITH p, purpose
OPTIONAL MATCH (inviter:Person)-[e:ENTERED]->(p)
RETURN p.email AS email, p.name AS name, purpose, inviter.name AS inviter_name, e.relationship AS relationship
```

The inviter's version (`RESEND_BY_INVITER`) starts from the entry instead, so only the person who entered them can send again; the rest is the same.

```cypher
MATCH (:Person {key: $inviter_key})-[:ENTERED]->(p:Person {key: $key})
SET p.key = p.key
WITH p
WHERE p.accepted_at IS NULL AND p.active
SET p.token_hash = $token_hash, p.token_purpose = 'invite', p.token_expires_at = $expires_at
WITH p
OPTIONAL MATCH (inviter:Person)-[e:ENTERED]->(p)
RETURN p.email AS email, p.name AS name, inviter.name AS inviter_name, e.relationship AS relationship
```

Code takes the inviter's form whenever an inviter key is given, even an empty one, and the unscoped form only for `None`. John's root account is made by `make_admin.py` with no link and no `ENTERED`, and nothing is sent (decision X3, 5 October 2026); being not yet accepted, it gets its first link from the "Forgot your password?" statement above, sent by the site from its own settings, in John's own wording (no inviter). The back room's "Send a password link" uses the second with the account's key in place of the email and only for an accepted account. Python sends the invitation email for `invite` (John's own wording when there is no inviter) and the password email for `reset`. Every new link draws on one limit per address (three an hour), shared by "Forgot your password?", a member's "Send the invitation again" and the back room. Only the anonymous "Forgot your password?" form also has a limit per minute for the whole site; no member's or back room button takes from it, so whoever drains it blocks nothing else (second review, 5 October 2026).

**Q18. Choose a new password through a link.**

```cypher
MATCH (p:Person {token_hash: $token_hash})
SET p.key = p.key
WITH p
WHERE p.token_hash = $token_hash AND p.token_purpose = 'reset' AND p.token_expires_at > $now
  AND p.active AND p.accepted_at IS NOT NULL
SET p.password_hash = $password_hash,
    p.token_hash = null, p.token_purpose = null, p.token_expires_at = null
RETURN p.key AS key
```

**Q19. Change password while signed in.** Python has checked the current password first. Any pending password link stops working too.

```cypher
MATCH (p:Person {key: $key})
SET p.password_hash = $password_hash,
    p.token_hash = null, p.token_purpose = null, p.token_expires_at = null
```

**Q19a. Who entered an account** (`WHO_ENTERED`), for the account page's "Entered by" line. John's root has no `ENTERED` edge, so no row comes back and the line is left out.

```cypher
MATCH (inviter:Person)-[e:ENTERED]->(:Person {key: $key})
RETURN inviter.name AS inviter_name, e.relationship AS relationship, e.created_at AS entered_at
```

**Q19b. One's own details** (`OWN_DETAILS`), for the form on the account page.

```cypher
MATCH (p:Person {key: $key})
RETURN p.name AS name, p.country AS country, p.postal_code AS postal_code
```

**Q19c. Change one's own details** (`SET_DETAILS`, revision round R11). The key comes from the cookie only; Python has cleaned the name as on acceptance and needs a name and a country. The postal code may be empty (John, 18 October 2026). Posts keep the `display_name` they were posted with.

```cypher
MATCH (p:Person {key: $key})
WHERE p.active AND p.accepted_at IS NOT NULL
SET p.name = $name, p.country = $country, p.postal_code = $postal_code
```

**Q20. People one has entered**, and, without the first `MATCH`, the back room list of every account:

```cypher
MATCH (me:Person {key: $key})-[e:ENTERED]->(p:Person)
RETURN p.key AS key, p.name AS name, p.email AS email, e.relationship AS relationship,
       e.created_at AS entered_at, p.accepted_at AS accepted_at, p.active AS active,
       p.token_purpose AS purpose, p.token_expires_at AS expires_at
ORDER BY e.created_at DESC
```

The back room version starts `MATCH (p:Person) WHERE p.email IS NOT NULL OPTIONAL MATCH (inviter:Person)-[e:ENTERED]->(p)` and also returns `inviter.name` and `inviter.email` (R5: two people can share a name; back room only).

**Q21. Withdraw an entry never accepted.** Only while the person has nothing but the `ENTERED` edge; an accepted account is switched off instead.

```cypher
MATCH (:Person {key: $inviter_key})-[:ENTERED]->(p:Person {key: $key})
SET p.key = p.key
WITH p
WHERE p.accepted_at IS NULL AND COUNT { (p)--() } = 1
DETACH DELETE p
RETURN count(*) AS withdrawn
```

The back room version (`WITHDRAW_ANY`) matches any inviter. A person nobody entered, John's root, has no `ENTERED` edge and so cannot be withdrawn.

```cypher
MATCH (:Person)-[:ENTERED]->(p:Person {key: $key})
SET p.key = p.key
WITH p
WHERE p.accepted_at IS NULL AND COUNT { (p)--() } = 1
DETACH DELETE p
RETURN count(*) AS withdrawn
```

**Q22. Switch an account off or on** (back room): `MATCH (p:Person {key: $key}) WHERE p.email IS NOT NULL AND NOT p.admin SET p.active = $active`. John's own account cannot be switched off from the page.

### Stances

One stance per person and solution (D7). **Q23** takes write locks on the person and the solution before it reads, the same trick as the `PART_OF` statement, so a quick approve, oppose, withdraw from two tabs is applied in order and always leaves one stance or none.

```cypher
// set: {stance} is APPROVE or OPPOSE and {other} the opposite, both from STANCE_TYPES
MATCH (p:Person {key: $person_key}), (s:Solution {key: $solution_key})
SET p.key = p.key, s.key = s.key
WITH p, s
OPTIONAL MATCH (p)-[old:{other}]->(s)
DELETE old
WITH DISTINCT p, s
MERGE (p)-[r:{stance}]->(s)
ON CREATE SET r.source = 'click', r.anonymous = false, r.created_at = $now;

// withdraw
MATCH (p:Person {key: $person_key}), (s:Solution {key: $solution_key})
SET p.key = p.key, s.key = s.key
WITH p, s
OPTIONAL MATCH (p)-[r:APPROVE|OPPOSE]->(s)
DELETE r
```

For a post made with `ACCOUNTS_ENABLED` set (always an account's), the write path's statement 4b becomes the same set statement with the post's properties: `ON CREATE SET r.post_id = $post_id, r.anonymous = $anonymous, r.created_at = $now ON MATCH SET r.last_post_id = $post_id`, so the one-stance rule holds however an account takes a stance. With `ACCOUNTS_ENABLED` unset, 4b stays the 0.1 statement and the issue page uses the 0.1 Q4 (decision X1): the live site does not change until rollout.

A stance that a post made and a click later replaced or withdrew is gone from that post's "show what was added" list; the statement itself is unchanged.

**Q4, revised** (with `ACCOUNTS_ENABLED` set; until then Q4 as in 0.1). Solutions are ranked by net support. A 0.1 Person who holds both stances counts once each way, so adds nothing net. `$me` is the signed-in account key, or null, which matches nothing.

```cypher
MATCH (i:Issue {key: $key})-[:HAVE_PROPOSED]->(s:Solution)
OPTIONAL MATCH (pp:Person)-[pr:PROPOSE]->(s)
OPTIONAL MATCH (pa:Person)-[:APPROVE]->(s)
OPTIONAL MATCH (po:Person)-[:OPPOSE]->(s)
WITH s, count(DISTINCT pp.key + CASE WHEN coalesce(pr.anonymous, false) THEN '|anonymous' ELSE '' END) AS proposers,
     count(DISTINCT pa) AS approves, count(DISTINCT po) AS opposes
OPTIONAL MATCH (:Person {key: $me})-[mine:APPROVE|OPPOSE]->(s)
WITH s, proposers, approves, opposes, head(collect(type(mine))) AS my_stance
OPTIONAL MATCH (ev:Evidence)-[r:SUPPORTS|REFUTES]->(s)
WITH s, proposers, approves, opposes, my_stance,
     [x IN collect(DISTINCT {key: ev.key, name: ev.name, url: ev.url, stance: type(r)})
        WHERE x.key IS NOT NULL] AS evidence
RETURN s.key AS key, s.name AS name, proposers, approves, opposes, my_stance, evidence
ORDER BY approves - opposes DESC, approves DESC, toLower(s.name) ASC
```

Proposers are counted by account and anonymity (D2): an account's anonymous proposal counts apart from its named one; a missing flag is named, so records from the test weeks count as before.

Display stays raw counts ("proposed by 2 · approved by 3 · opposed by 1"); the net figure orders the list and is never shown.

### Own posts

Posts by an account are credited as before: `POSTED` from the account, `display_name` the account's name or null when anonymous, `anonymous` on the post and its edges. On public counts of people made from posts, an account's anonymous posts count apart from its named ones, so no page can link an anonymous post to a name: the identity counted is the `Person` key plus whether the edge is anonymous. In Q3 an account with one named and one anonymous claim on an issue reads 2 people, 2 claims, listed as its name and "Anonymous"; two anonymous claims by one account count once, as "Anonymous".

**Q7, revised.** The feed and the issue page also return `post.edited_at` and `EXISTS { (:Person {key: $me})-[:POSTED]->(post) } AS mine`. The author's key is never returned to a template.

**Q24. Is this my post?** Every edit and delete starts here, on the server, inside the write transaction; hiding the buttons is not the check. It locks the post, so a second delete or edit from another tab waits, then finds the post gone and says so.

```cypher
MATCH (:Person {key: $me})-[:POSTED]->(post:Post {id: $id})
WHERE coalesce(post.seed, false) = false
SET post.id = post.id
RETURN post.id AS id, post.text AS text, post.anonymous AS anonymous,
       post.payload AS payload, post.created_at AS created_at
```

**Delete** is Q11 unchanged, after Q24.

**Q25. Edit.** One write transaction, under the same post id, in this order: (1) Q11 statement 1 without the final `DETACH DELETE post`, so the post's `CLAIM`, `SUBMIT`, `PROPOSE`, `SUPPORTS` and `REFUTES` edges go and their touched element ids are kept; (2) write path statements 3 to 5b from the edited card with the same `post_id` and person, and the `anonymous` chosen on the edit page; (3) Q11 statement 2 on the touched ids, so only what the new version no longer uses is removed; (4) the post itself:

```cypher
MATCH (post:Post {id: $id})
SET post.text = $text, post.payload = $payload, post.source = $source,
    post.extraction_raw = $extraction_raw, post.model = $model, post.latency_ms = $latency_ms,
    post.edited_at = $now, post.anonymous = $anonymous, post.display_name = $display_name
```

and (5) the stances this post made, which MERGE kept through step 2:

```cypher
MATCH (:Person {key: $me})-[r:APPROVE|OPPOSE]->(:Solution)
WHERE r.post_id = $id
SET r.anonymous = $anonymous
```

`created_at` stays, so the post keeps its place in the feed. Since the revision round (R4, John, 16 October 2026) the writer may switch between their name and Anonymous at any time, either way: the post and every edge carrying its `post_id` take the new choice, so the public counts keep named and anonymous apart as before.

The edit card is built from the post's current edges (Q7's structure query for this one post, with issue names and parents from Q2), not from its stored `payload`, so an issue renamed or merged since shows as it is now and is never made again; the stored payload gives only evidence links. A solution's position on the card is the stance edge this post still holds, so a stance a click has since replaced shows as no position. When the card is resolved for saving, a solution this post itself proposes is proposed again (its own `HAVE_PROPOSED` link is left out of the candidates), never read as a position on a solution already listed (GitHub issue 4's rule); so an unchanged edit leaves the post's edges as they were. MERGEd edges (`HAVE_PROPOSED`, `APPROVE`, `OPPOSE`, `PART_OF`) stay, as with delete: a position added in the edit is taken (Q23 rules), a position removed from the card is not withdrawn; that is done with the buttons.

**Q36. My Statements** (no-cost extra X1, added 20 October 2026; read only, no schema change). Your account lists the member's own posts, anonymous ones included, newest first, 50 at a time (`$limit` is one more than shown, to know whether to offer more). The feed's Q7 flags and structure query then decorate them as on the Write page.

```cypher
MATCH (:Person {key: $me})-[:POSTED]->(post:Post)
WHERE coalesce(post.seed, false) = false
RETURN post.id AS id, post.text AS text, post.display_name AS display_name,
       post.anonymous AS anonymous, post.created_at AS created_at, post.seed AS seed
ORDER BY post.created_at DESC
LIMIT $limit
```

### Search

Search does not need accounts: it works behind the passphrase too. It ships with the rest of Phase 1, since its pages build on the Phase 1 access code. The query is cut to 200 characters and ten words, lower-cased, and every Lucene special character (`+ - & | ! ( ) { } [ ] ^ " ~ * ? : \ /`) is escaped with a backslash; every word must then match, as written or as the start of a word (`+(housing housing*) +(costs costs*)`), so a second word narrows the results, as the page's "Try another word, or fewer words" says. An empty query shows the normal Issues list. Search by meaning (embeddings, GitHub issue 2) and event dates belong to Phase 3.

**Q26. Names.**

```cypher
CALL db.index.fulltext.queryNodes('record_names', $query) YIELD node, score
WITH node, score ORDER BY score DESC LIMIT 30
OPTIONAL MATCH (node)<-[:HAVE_PROPOSED]-(home:Issue)
OPTIONAL MATCH (node)-[:SUPPORTS|REFUTES]->(target)
OPTIONAL MATCH (target)<-[:HAVE_PROPOSED]-(target_home:Issue)
WITH node, score, collect(DISTINCT home.key) AS solution_homes,
     collect(DISTINCT CASE WHEN target:Issue THEN target.key ELSE target_home.key END) AS evidence_homes
RETURN labels(node)[0] AS label, node.key AS key, node.name AS name, score,
       solution_homes, evidence_homes
ORDER BY score DESC
```

Python picks each result's link: an issue to itself, a solution to its first issue, evidence to the first issue it is about directly or through a solution. Evidence about other evidence only is listed without a link.

**Q27. Posts.** Rows are decorated like the feed, so their chips link to issue pages.

```cypher
CALL db.index.fulltext.queryNodes('post_text', $query) YIELD node, score
WITH node, score ORDER BY score DESC LIMIT 20
RETURN node.id AS id, node.text AS text, node.display_name AS display_name,
       node.anonymous AS anonymous, node.created_at AS created_at, node.seed AS seed,
       node.edited_at AS edited_at
```

### Tidying the issue tree

Admin accounts only (D5). Each statement below runs in one write transaction with Q31, so a change and its record land together or not at all. Both issues are locked first with the transient property (`SET i.tidy_lock = true REMOVE i.tidy_lock`), and read only after the lock, in a later statement. The one-level rule of `PART_OF` holds after every change: no sub-issue of a sub-issue, no issue part of itself.

**Q28. Move.** Make an issue part of a top-level issue, or make it top level. Refused when the issue has sub-issues of its own (it stays top level), when the new parent is itself a sub-issue, or when they are the same issue.

```cypher
// 0. lock both issues first, as one statement: keys is [key, parent_key]
MATCH (i:Issue) WHERE i.key IN $keys SET i.tidy_lock = true REMOVE i.tidy_lock;

// under a parent
MATCH (child:Issue {key: $key}), (parent:Issue {key: $parent_key})
WHERE child <> parent
  AND NOT (parent)-[:PART_OF]->(:Issue)
  AND NOT (:Issue)-[:PART_OF]->(child)
OPTIONAL MATCH (child)-[old:PART_OF]->(:Issue)
DELETE old
WITH DISTINCT child, parent
CREATE (child)-[:PART_OF {created_at: $now}]->(parent)
RETURN child.key AS key;

// top level
MATCH (child:Issue {key: $key})-[old:PART_OF]->(:Issue)
DELETE old
```

**Q29. Rename.** The name goes through `clean_name()` and the key through `make_key()`. When the new key is the issue's own key only the name changes. When another issue has that key the rename is refused and the page suggests a merge; the constraint backs this up. Issue keys only: a solution or evidence may share a name with an issue (GitHub issue 1).

```cypher
MATCH (i:Issue {key: $key})
WHERE NOT EXISTS { MATCH (other:Issue {key: $new_key}) WHERE other <> i }
SET i.name = $new_name, i.key = $new_key
RETURN i.key AS key
```

**Q30. Merge issue B into issue A.** Every relationship of B moves to A with its properties, one statement per type, plain Cypher, no APOC. A keeps its own place in the tree.

```cypher
// 0. lock both issues (keys is [kept, merged]), then read their names; refuse when A and B
//    are the same issue or one is gone
MATCH (i:Issue) WHERE i.key IN $keys SET i.tidy_lock = true REMOVE i.tidy_lock;
MATCH (a:Issue {key: $kept}), (b:Issue {key: $merged}) WHERE a <> b
RETURN a.name AS kept_name, b.name AS merged_name;
// 1. a PART_OF between the two goes (no self-loop)
MATCH (a:Issue {key: $kept})-[r:PART_OF]-(b:Issue {key: $merged}) DELETE r;
// 2. claims
MATCH (p:Person)-[r:CLAIM]->(b:Issue {key: $merged}), (a:Issue {key: $kept})
CREATE (p)-[n:CLAIM]->(a) SET n = properties(r) DELETE r;
// 3. evidence about B; {rel} is SUPPORTS, then REFUTES, from EVIDENCE_TYPES
MATCH (e:Evidence)-[r:{rel}]->(b:Issue {key: $merged}), (a:Issue {key: $kept})
CREATE (e)-[n:{rel}]->(a) SET n = properties(r) DELETE r;
// 4. solutions: A keeps its own link when it already has one, so stances follow the solution
MATCH (b:Issue {key: $merged})-[r:HAVE_PROPOSED]->(s:Solution), (a:Issue {key: $kept})
MERGE (a)-[n:HAVE_PROPOSED]->(s) ON CREATE SET n = properties(r)
DELETE r;
// 5. B's sub-issues: under A when A is top level, otherwise under A's parent
MATCH (c:Issue)-[r:PART_OF]->(b:Issue {key: $merged}), (a:Issue {key: $kept})
OPTIONAL MATCH (a)-[:PART_OF]->(ap:Issue)
WITH c, r, coalesce(ap, a) AS parent
MERGE (c)-[n:PART_OF]->(parent) ON CREATE SET n = properties(r)
DELETE r;
// 6. B's own parent link goes; A does not move
MATCH (b:Issue {key: $merged})-[r:PART_OF]->(:Issue) DELETE r;
// 7. earlier change records about B now point at A
MATCH (c:Change)-[r:CHANGED]->(b:Issue {key: $merged}), (a:Issue {key: $kept})
CREATE (c)-[n:CHANGED]->(a) SET n = properties(r) DELETE r;
// 8. plain DELETE, not DETACH: if any relationship was missed the whole merge fails
MATCH (b:Issue {key: $merged}) DELETE b
```

Statement 5 cannot make a sub-issue of a sub-issue: a sub-issue has no children, so A's parent is top level. The counts of each type moved go into the Change's `details`. Posts that claimed B now show A in their chips, because their `CLAIM` edges point at A under the same `post_id`; their saved `payload` text is not rewritten.

The kept issue keeps its own `seed` value: merging a seed issue into an issue made by a post does not make the kept issue a seed issue. `scripts.seed --reset` without `--force` refuses after any merge in any case, because `non_seed_count()` counts every node whose `seed` is not true, except accounts, and the merge's change record is such a node.

**Q31. The change record**, inside the same transaction:

```cypher
MATCH (p:Person {key: $person_key}), (i:Issue {key: $issue_key})
CREATE (c:Change {id: $id, kind: $kind, created_at: $now, details: $details})
CREATE (p)-[:MADE {created_at: $now}]->(c)
CREATE (c)-[:CHANGED {created_at: $now}]->(i)
```

**Q32. Changes, newest first**, for the Changes page:

```cypher
MATCH (p:Person)-[:MADE]->(c:Change)
OPTIONAL MATCH (c)-[:CHANGED]->(i:Issue)
RETURN c.id AS id, c.kind AS kind, c.created_at AS created_at, c.details AS details,
       p.name AS by, i.key AS issue_key, i.name AS issue_name
ORDER BY c.created_at DESC, c.id DESC
LIMIT 200
```

**Q1, revised.** `last_activity` ignores `CHANGED` and a `PART_OF` with no `post_id` (made by a move, Q28, or by the seed's issues block): `OPTIONAL MATCH (i)-[r]-() WHERE type(r) <> 'CHANGED' AND NOT (type(r) = 'PART_OF' AND r.post_id IS NULL)`. So tidying an issue, a move included, does not move it or its parent up "Most recent". (The seed's `PART_OF` edges carry the seed's first date, the same as its issues' `created_at`, so the seed's order does not change.) People are counted by account and anonymity (D2): an account's anonymous claims count apart from its named ones, as on the issue page (Q3); records from the test weeks count as before.

### Back room, seed, export and restore

**Q10, revised.** "Reset to seed" keeps accounts and who entered whom, so nobody is locked out by a reset; everything else goes, including change records:

```cypher
MATCH (n) WHERE NOT (n:Person AND n.email IS NOT NULL) DETACH DELETE n
```

`scripts/seed.py --reset` follows the same rule, and counts accounts as neither seed nor non-seed when it decides whether to refuse.

The count that makes `scripts/seed.py --reset` refuse ignores accounts:

```cypher
MATCH (n) WHERE coalesce(n.seed, false) = false AND NOT (n:Person AND n.email IS NOT NULL)
RETURN count(n) AS n
```

**Reload seed** adds only seed statements that are missing. When every seed statement is present it writes nothing, so a seed issue that John renamed or merged does not come back under its old name. When some are missing (deleted in the back room), each seed issue name in the issues block and in the seed posts loaded again is first read as the issue it became, following every rename and merge in the change records, so the old name does not come back that way either. A seed issue that John moved, or kept in a merge, keeps the place it has: its seed parent is not applied again, in the issues block or in the posts loaded again, so a reload never undoes a move either. The history it reads includes moves, all of them, oldest first, not Q32's newest 200:

```cypher
MATCH (c:Change) WHERE c.kind IN ['rename', 'merge', 'move']
RETURN c.kind AS kind, c.details AS details, c.created_at AS created_at
ORDER BY c.created_at, c.id
```

**Q33. Export, version 2.** `Change` (identity `id`) joins the labels; `ENTERED` (Person to Person), `MADE` (Person to Change) and `CHANGED` (Change to Issue) join the types. `password_hash`, `token_hash`, `token_purpose` and `token_expires_at` are left out of every node. Restore accepts versions 1 and 2. A restored account keeps `accepted_at` but has no password, and its owner uses "Forgot your password?".

## Phase 2: evidence that checks itself

Added 20 October 2026, before any Phase 2 code. Properties only: no new label, no new relationship type, no new constraint or index. Everything here is written only when `EVIDENCE_CHECK_ENABLED` is set; unset, the write path is exactly the Phase 1 one and these properties stay absent (read queries treat absent as null).

### The check on the evidence edge

A post's `SUPPORTS` or `REFUTES` edge (Evidence to Issue, Solution or Evidence) gains three properties, set in the same CREATE as the edge, from the card:

| Property | Type | Meaning |
|---|---|---|
| `check` | string or null | How the page behind the evidence's link was read for this claim: `supports`, `refutes`, `unclear` (read, but the page does not clearly say either way, or the quote was not found on the page), `unread` (the page could not be opened or read), or null (not checked: no link, no reading service, flag off, the writer posted before the check came back, or a link that is not a web page and "cannot be read yet"). |
| `check_quote` | string or null | The sentence from the page the reading rests on, at most 500 characters. Null unless `check` is `supports` or `refutes`. Checked in Python to appear on the fetched page (whitespace normalised) before it is ever stored. |
| `checked_at` | datetime or null | When the page was read. |

The edge type stays the writer's choice. "The writer disagreed with the reading" is `(type(r) = 'SUPPORTS' AND r.check = 'refutes') OR (type(r) = 'REFUTES' AND r.check = 'supports')`. Nothing is blocked or deleted because of it (flag, never delete).

The card sends the check with each evidence row; the server does not trust it blindly. A row's `check` is kept only when the server's own cache (below) holds a reading of the same URL, for the same target, with the same verdict and quote; otherwise the row is stored with `check = null`. So a tester cannot write a reading the site never made. The statement the reading was made with does not have to match: a writer who tidies the statement after the link was read keeps the reading, since it was of the same page for the same claim (`check.confirmed`, decided 20 October 2026). "The same target" is the one the row lands on: a row whose `about` names nothing on the card or in the record, and so falls back to the card's first issue, keeps no reading, and of two rows with the same evidence name only the first, the one written, can carry one (`check.kept_checks`, 20 October 2026).

### Source facts on Evidence

`Evidence` is shared (MERGE by key, like `url`), so what the page says about itself is stored once, when it is first read:

| Property | Type | Meaning |
|---|---|---|
| `source_type` | string or null | One of `news`, `research`, `government`, `reference`, `organisation`, `blog`, `other`. |
| `source_primary` | bool or null | True for a primary source (the original study, record, data or first hand account), false for a report about one, null when it cannot be told. |
| `source_published` | string or null | `YYYY-MM-DD`, `YYYY-MM` or `YYYY` as the page gives it; null when the page gives no date. For a reference work (an encyclopedia or dictionary page), which is kept up to date, the date it was last updated rather than first written. |
| `source_checked_at` | datetime or null | When these were set. |

Written with `coalesce` so the first reading wins and a later post never overwrites them, and only when the post's evidence row carries a kept check of the same URL as `e.url`:

```cypher
// 5, extended. $source is null unless the row's check was kept and its url is the evidence's url.
MERGE (e:Evidence {key: $evidence_key})
ON CREATE SET e.name = $evidence_name, e.url = $url, e.created_at = datetime(), e.seed = false
ON MATCH  SET e.url = coalesce(e.url, $url)
WITH e
FOREACH (_ IN CASE WHEN $source IS NOT NULL AND e.url = $url AND e.source_checked_at IS NULL THEN [1] ELSE [] END |
  SET e.source_type = $source.type, e.source_primary = $source.primary,
      e.source_published = $source.published, e.source_checked_at = datetime())
WITH e
MATCH (p:Person {key: $person_key})
CREATE (p)-[:SUBMIT {post_id: $post_id, anonymous: $anonymous, created_at: datetime()}]->(e);

// 5b, extended.
MATCH (e:Evidence {key: $evidence_key}), (t:Issue {key: $target_key})
CREATE (e)-[:SUPPORTS {post_id: $post_id, created_at: datetime(),
                       check: $check, check_quote: $check_quote, checked_at: $checked_at}]->(t);
```

Editing one's own post (Q24, Q25) recreates the post's evidence edges from the card, so a check travels the same way: kept when the edited row still carries a kept check, null otherwise. On an edit a check is also kept when it is the one the record already holds on this post's edge for the same evidence, target and link (Q35 below), so an edit after a restart does not lose it; a kept stored check keeps its `checked_at` and leaves the source facts alone. The edit card shows each row's stored check and does not read the page again unless the link or what it is about changes.

The extended statements 5 and 5b live in `app/graph_evidence.py` (graph.py is near its 500 line limit); they use the transaction's `$now`, like every other write statement, where the sketch above says `datetime()`, and `e.seed = $seed` where it says `false`, as the Phase 1 statement 5 does.

```cypher
// Q35. The checks one post holds, for the edit card and the edit's save.
MATCH (e:Evidence)-[r:SUPPORTS|REFUTES]->(t)
WHERE r.post_id = $post_id AND r.check IS NOT NULL
RETURN e.key AS evidence_key, t.key AS target_key, e.url AS url, r.check AS check,
       r.check_quote AS check_quote, r.checked_at AS checked_at,
       e.source_type AS source_type, e.source_primary AS source_primary, e.source_published AS source_published
```

The link compared on an edit is the one in the post's stored payload, not `e.url`, which may be an earlier post's.

### Agreement with other evidence (computed, never stored)

Source confidence's fourth part is counted when a page is shown, not stored, so it is always current. For one evidence item `e` and the thing `t` it is about:

```cypher
// Q34. Agreement on one target. $keys: the evidence keys shown for t.
// Not run as written: Q39 below answers it for a whole issue page in one read.
MATCH (other:Evidence)-[r:SUPPORTS|REFUTES]->(t {key: $target_key})
WHERE other.key IN $keys
WITH other.key AS key, collect(DISTINCT type(r)) AS stances
RETURN key, stances
```

Python then says, for each item, how many other items on the same target take the same side and how many the other side.

**Q39. Source confidence on one issue page** (days 7 and 8, added 20 October 2026; read only). With `EVIDENCE_CHECK_ENABLED` set, the issue page makes this one extra read and leaves Q4 (either form) and Q5 exactly as they are; unset, it is never run and the page is Phase 1's. It answers Q34 for the issue and all its solutions in one round trip: one row per evidence edge into the issue or one of its proposed solutions, with the edge's reading and the evidence's source facts. It lives in `app/graph_evidence.py`.

```cypher
// Q39. $key: the issue shown.
MATCH (i:Issue {key: $key})
OPTIONAL MATCH (i)-[:HAVE_PROPOSED]->(s:Solution)
WITH i, collect(s) AS solutions
UNWIND [i] + solutions AS t
MATCH (e:Evidence)-[r:SUPPORTS|REFUTES]->(t)
RETURN CASE WHEN t:Issue THEN 'issue' ELSE 'solution' END AS target_kind, t.key AS target_key,
       e.key AS evidence_key, type(r) AS stance, r.check AS check,
       e.source_checked_at IS NOT NULL AS source_known, e.source_type AS source_type,
       e.source_primary AS source_primary, e.source_published AS source_published
```

Python (`app/confidence.py`, no Cypher) groups the rows by target (kind and key, since an issue and a solution may share a key). For an item `e` shown under one side on `t`, "say the same" counts the other evidence items with an edge of that side into `t`, and "disagree" those with an edge of the other side; an item never counts itself, and an item cited on both sides of `t` counts once on each. Type, date and primary or secondary come from the source facts only when `source_known`.

**The disagreement line, when one evidence item is cited about the same target by several posts** (decided 20 October 2026). Each post's edge carries its own reading. Under "Supported by", "The page was read as arguing against this." shows when **any** post's `SUPPORTS` edge from `e` to `t` has `check = 'refutes'`; under "Refuted by", "The page was read as supporting this." shows when any `REFUTES` edge from `e` to `t` has `check = 'supports'`. Edges that agree with their reading, or have none, do not cancel it. Why any rather than most: every reading is of the same page for the same claim, so readings rarely differ, and when one does, the reader should hear it (flag, never delete). Readings on other targets never count.

### What is never stored

The page text, the raw response of the reading service, and the suggestions the page prompted. Suggestions the writer ticks become ordinary card rows and are written like any other row. The raw response goes to DEBUG logs only.

### The check cache (process memory, not the database)

`app/check.py` keeps, for the life of the process, the last 500 readings keyed by (URL, target name, statement hash), each with its verdict, quote and source facts. It lets the write path confirm a check (above) and keeps the same link from being read twice in a session. A restart empties it; a post made across a restart is stored with `check = null`.

### Export and restore

Export version 2 already carries every node and edge property not on the account deny list, so these properties travel with no format change. Restore's validator accepts them (strings, booleans, datetimes, nulls).

### Revision round: PDFs and arXiv papers (added 22 October 2026)

Written before the code (Eston, 22 October: PDFs are built inside Phase 2). Nothing new is stored: no new property, label, relationship type, constraint or index. A PDF's reading is stored exactly like a page's (`check`, `check_quote`, `checked_at` on the edge, the source facts on `Evidence`).

**Reading a PDF** (`app/fetch_pdf.py`, no Cypher; `app/fetch_page.py` hands a PDF over to it). A reply is a PDF when its content type is `application/pdf` (or `application/x-pdf`), whatever the address ends in, or `application/octet-stream` for an address ending `.pdf`. The same public address checks run on every redirect. The file stops at 15 MB (larger is not read: a PDF cut short cannot be opened), the download at 30 seconds, and the text is taken from at most the first 40 pages, in a separate process stopped after 10 seconds, so a hostile file cannot hold the server. The text goes through the same `cut()` and the same check as a page. The PDF's own title, and its creation date (else its last change date), stand in for a page's title and published date.

**A PDF with no text** (a scanned document: pages of pictures) is not read. The check answers `notext`, which, like `unsupported`, is never stored (the edge's `check` stays null).

**arXiv.** An `arxiv.org/abs/<id>` link is read as a page (the abstract). When that reading is `unclear` or `unread`, the full paper at `arxiv.org/pdf/<id>` is read too, against the same claim and statement, and its reading is the link's: the quote is from the paper, and the cache keeps it under the `abs` link the card holds, so the write path confirms it as usual. For any `arxiv.org/abs/` or `arxiv.org/pdf/` link the source facts say `research`, primary (`source_type = 'research'`, `source_primary = true`), whatever the reading guessed. This lives in `app/routes_evidence.py` (`read_link`), around `check.check_evidence`, so `app/check.py` is unchanged.

## Change of email (no-cost extra X2, added 20 October 2026)

John's "chain of custody" note, 17 October 2026. Properties only, on account `Person`s; no new label, type or constraint (`person_email` stays on `email` alone). Not behind `EVIDENCE_CHECK_ENABLED`: it is part of Your account, so it needs `ACCOUNTS_ENABLED` like the rest of it, and its own switch, `EMAIL_CHANGE_ENABLED` (added 20 October 2026, so Phase 2 can go live before John approves the wording). Unset, Your account has no change of email form, `/account/email` and `/email/{link}` answer not found, and nothing here is written; the properties below stay absent, and the back room and export show only what is there.

| Property | Value | Notes |
|---|---|---|
| `token_purpose` | gains `email` | The one live link may now also be a change of email. |
| `pending_email` | string or null | The address the `email` link would move the account to. Set with the link; a link field like the `token_*` ones: never in a template, a log or a copy. |
| `previous_emails` | list of strings or absent | Every address the account used before, oldest first. |
| `previous_emails_until` | list of datetimes or absent | When each address in `previous_emails` stopped being used, in the same order. Two parallel lists rather than `address|date` strings, so the dates stay datetimes and restore checks them as such. |

An address is never used by two people over time: a new address is refused when it is another account's `email` or in another account's `previous_emails` (both at asking and again at confirming), and entering a person (Q12) refuses an address in anyone's `previous_emails` with the same answer as an address already taken. Changing back to one's own earlier address is allowed. Sign in reads `email` only; earlier addresses are history. They show to the account's owner nowhere and in the back room's People list.

**Q37. Ask to change the email.** After the current password is checked in Python. Lock first, then check, as Q16 to Q18. No row: nothing is sent (the page says the same either way).

```cypher
MATCH (p:Person {key: $key})
SET p.key = p.key
WITH p
WHERE p.active AND p.accepted_at IS NOT NULL AND p.email <> $email
  AND NOT EXISTS { MATCH (other:Person) WHERE other.key <> p.key
                   AND (other.email = $email OR $email IN coalesce(other.previous_emails, [])) }
SET p.token_hash = $token_hash, p.token_purpose = 'email', p.token_expires_at = $expires_at,
    p.pending_email = $email
RETURN p.name AS name, p.email AS email
```

**Q38. Confirm through the link.** The link is used either way; the address moves only when it is still free.

```cypher
MATCH (p:Person {token_hash: $token_hash})
SET p.key = p.key
WITH p
WHERE p.token_hash = $token_hash AND p.token_purpose = 'email' AND p.token_expires_at > $now
  AND p.active AND p.pending_email IS NOT NULL
OPTIONAL MATCH (other:Person)
WHERE other.key <> p.key AND (other.email = p.pending_email OR p.pending_email IN coalesce(other.previous_emails, []))
WITH p, count(other) = 0 AS free, p.email AS old, p.pending_email AS new
SET p.previous_emails = CASE WHEN free THEN coalesce(p.previous_emails, []) + old ELSE p.previous_emails END,
    p.previous_emails_until = CASE WHEN free THEN coalesce(p.previous_emails_until, []) + $now ELSE p.previous_emails_until END,
    p.email = CASE WHEN free THEN new ELSE old END,
    p.token_hash = null, p.token_purpose = null, p.token_expires_at = null, p.pending_email = null
RETURN p.key AS key, free, old, new
```

Q15 (open a link) also returns `pending_email`; the back room's account list (Q20) also returns `previous_emails` and `previous_emails_until`.

**Export and restore.** `pending_email` joins the properties never in a copy (with the link it belongs to). `previous_emails` and `previous_emails_until` travel; restore checks they are a list of strings and a list of datetimes of the same length. No new format version: version 2 already carries any other property.
