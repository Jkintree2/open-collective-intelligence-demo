# 03. Graph schema for 0.1

> **Revised 5 September 2026 after REVIEW.md.** Changed: `display_name` is null on anonymous posts (M7); name cleaning and key rules tightened (m6, m7, m8, M4); `PART_OF` guards for a parent that is a sub-issue and a child that already has a parent (M2, M3); Q1 computes `last_activity` over every edge and returns person keys so top-level rows rank on inclusive counts (C7, m4); Q6 includes children's posts (m5); Q8 is capped and uncached (M4, M20); Q11 keeps MERGEd edges and deletes orphaned non-seed nodes (M4, M9); the worked example follows the corrected case 1 (C6).

Neo4j Aura Free, Neo4j 5 Cypher. John's README vocabulary plus only what the kickoff decisions require: sub-issues, an anonymous flag on relationships, a source link on Evidence, timestamps, and a Post node so every edge traces back to the text that produced it.

## Node labels

| Label | Properties | Notes |
|---|---|---|
| `Person` | `key` (unique), `name` (string or null), `anonymous` (bool), `created_at` | `key` is `name:<normalised name>` for a named tester, `anon:<uuid>` for an anonymous one. An anonymous Person has `name = null` and is displayed as "Anonymous". A browser gets one anonymous key, held in a cookie, so an anonymous tester's posts count as one person. |
| `Issue` | `key` (unique), `name`, `created_at`, `seed` (bool) | Top level or sub-issue. A sub-issue has exactly one outgoing `PART_OF`; the write path's guards keep it that way (first parent wins, and a sub-issue can never be a parent). |
| `Solution` | `key` (unique), `name`, `created_at`, `seed` | |
| `Evidence` | `key` (unique), `name`, `url` (string or null), `created_at`, `seed` | `name` is the citation as a short title ("2024 NOAA flooding survey"). `url` optional, never fetched. |
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

A person can hold both `APPROVE` and `OPPOSE` on the same solution if they posted both. The counts show both. Reconciling stances is the voting layer, out of scope (addendum 01).

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
* When `anonymous` is true, `display_name` is stored as null and the poster's name cookie is left untouched.
* Empty payload (no issues, no solutions, no evidence) is still stored as a Post with `source = manual` and no edges, so the feed shows what the tester wrote. This is the "post as a raw statement" path of Session 1.

## Read queries

### Q1. Issues list with counts, three sorts

```cypher
MATCH (i:Issue)
OPTIONAL MATCH (i)-[:PART_OF]->(parent:Issue)
OPTIONAL MATCH (p:Person)-[c:CLAIM]->(i)
WITH i, parent, count(c) AS claims, count(DISTINCT p) AS people,
     collect(DISTINCT p.key) AS person_keys
OPTIONAL MATCH (i)-[:HAVE_PROPOSED]->(s:Solution)
WITH i, parent, claims, people, person_keys, count(DISTINCT s) AS solutions
// evidence attached to the issue itself (0 hops) or to any of its solutions (1 hop)
OPTIONAL MATCH (ev:Evidence)-[:SUPPORTS|REFUTES]->(t)<-[:HAVE_PROPOSED*0..1]-(i)
WITH i, parent, claims, people, person_keys, solutions,
     collect(DISTINCT ev.key) AS evidence_keys
// last activity: the newest edge of any type that touches the issue, so a post that only
// adds evidence or a solution still bumps "Most recent"
OPTIONAL MATCH (i)-[any]-()
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

```cypher
MATCH (p:Person)-[c:CLAIM]->(i:Issue {key: $key})
RETURN count(c) AS claims, count(DISTINCT p) AS people,
       collect(DISTINCT CASE WHEN c.anonymous THEN 'Anonymous' ELSE p.name END) AS names
```

### Q4. Issue detail: solutions with stance counts and evidence

```cypher
MATCH (i:Issue {key: $key})-[:HAVE_PROPOSED]->(s:Solution)
OPTIONAL MATCH (pp:Person)-[:PROPOSE]->(s)
OPTIONAL MATCH (pa:Person)-[:APPROVE]->(s)
OPTIONAL MATCH (po:Person)-[:OPPOSE]->(s)
WITH s, count(DISTINCT pp) AS proposers, count(DISTINCT pa) AS approves, count(DISTINCT po) AS opposes
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
