"""Phase 3, ask the record: the digest the reading service answers from (03_schema.md, Phase 3,
Q40 to Q42; 05_extraction.md, Phase 3, answering). No Cypher.

The digest is compact JSON built in code, with ids the answer cites: S for a solution, E for a piece
of evidence, P for a post. It is filled in this order until DIGEST_CHARS:
1. the issue (its parent and sub-issues), its solutions by net support with their counts and the date
   of each stance, and its evidence with the readings, what each page says about itself and evidence
   on evidence. Asked of the whole record, the top solutions and evidence of the record join them;
2. the posts that took a stance, newest first (the reasons);
3. the other posts about the issue (Q6), newest first.
When posts do not fit, the digest says how many were left out. An anonymous post or edge never
carries a name; emails, countries and postal codes are never read.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Iterable

from app import graph, graph_ask, graph_own_posts, graph_search, search
from app.check import source_words
from app.fetch_video import is_video

DIGEST_CHARS = 32000  # about 8,000 tokens
POSTS_PER_ISSUE = 200
RECORD_ISSUES = 3
RECORD_TOP = 10
EVIDENCE_PIECES = 30  # pieces of evidence in one digest (part 1 is never cut, so it is capped)
SNIPPET = 200
ANONYMOUS = "Anonymous"
# The Phase 2 reading of a page, in John's words (04_interface.md, revision round).
READ_AS = {"supports": "agrees", "partly": "partly agrees", "refutes": "contradicts"}


@dataclass
class Source:
    """What the page shows for one id an answer cites."""
    id: str
    kind: str  # post, solution or evidence
    name: str  # the writer's name or Anonymous; the solution's or evidence's name
    date: str | None = None
    text: str | None = None  # a post's first SNIPPET characters
    href: str | None = None  # its issue page


@dataclass
class Digest:
    text: str
    sources: dict[str, Source] = field(default_factory=dict)
    posts_in: int = 0
    posts_left_out: int = 0
    issue_keys: list[str] = field(default_factory=list)

    @property
    def chars(self) -> int:
        return len(self.text)


def _dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _day(value: Any) -> str | None:
    return value.date().isoformat() if isinstance(value, datetime) else None


def _who(post: dict[str, Any]) -> str:
    """A post's name as the feed shows it; never the name behind an anonymous post."""
    if post.get("anonymous"):
        return ANONYMOUS
    return post.get("display_name") or ANONYMOUS


def _source_line(row: dict[str, Any], today: date | None) -> str | None:
    if not row.get("source_known"):
        return None
    facts = {"type": row.get("source_type"), "primary": row.get("source_primary"),
             "published": row.get("source_published"), "cites": row.get("source_cites")}
    return source_words(facts, today=today, video=is_video(row.get("url")))


def _ordered_posts(solutions: list[dict[str, Any]], posts: list[tuple[dict[str, Any], str]]
                   ) -> list[tuple[dict[str, Any], str]]:
    """Posts that took a stance first, then the rest, each part newest first, no repeats."""
    took = {pid for solution in solutions for stance in solution["stances"] for pid in stance["post_ids"]}
    seen: dict[str, tuple[dict[str, Any], str]] = {}
    for post, home in posts:
        seen.setdefault(post["id"], (post, home))
    newest = sorted(seen.values(), key=lambda pair: pair[0].get("created_at") or datetime.min, reverse=True)
    return [pair for pair in newest if pair[0]["id"] in took] + \
           [pair for pair in newest if pair[0]["id"] not in took]


def build(scope: str, issues: list[dict[str, Any]], solutions: list[dict[str, Any]],
          evidence_rows: list[dict[str, Any]], posts: list[tuple[dict[str, Any], str]], *,
          cap: int = DIGEST_CHARS, today: date | None = None) -> Digest:
    """The digest from rows already read. `scope` is the issue's name, or None for the whole record;
    `issues` are {key, name, parent, sub_issues, people, claims}; `solutions` Q40 and Q42 rows (repeats
    dropped by key); `evidence_rows` Q41 rows; `posts` (Q6 row, the issue key it was read under)."""
    first: dict[str, dict[str, Any]] = {}
    for row in solutions:
        first.setdefault(row["key"], row)
    solutions = list(first.values())
    s_ids = {row["key"]: f"S{n}" for n, row in enumerate(solutions, 1)}
    e_ids: dict[str, str] = {}
    for row in evidence_rows:
        for key in (row["key"], row["target_key"] if row["target_kind"] == "evidence" else None):
            if key and key not in e_ids and len(e_ids) < EVIDENCE_PIECES:
                e_ids[key] = f"E{len(e_ids) + 1}"
    evidence_rows = [row for row in evidence_rows if row["key"] in e_ids
                     and (row["target_kind"] != "evidence" or row["target_key"] in e_ids)]
    ordered = _ordered_posts(solutions, posts)
    p_ids = {post["id"]: f"P{n}" for n, (post, _) in enumerate(ordered, 1)}
    home = issues[0]["key"] if scope and issues else None

    def head(kept: set[str]) -> dict[str, Any]:
        """Section 1, citing only the posts in `kept`."""
        def cite(ids: Iterable[str]) -> list[str]:
            return [p_ids[pid] for pid in ids if pid in kept]

        out_issues = []
        for issue in issues:
            entry: dict[str, Any] = {"name": issue["name"]}
            if issue.get("parent"):
                entry["part_of"] = issue["parent"]
            if issue.get("sub_issues"):
                entry["sub_issues"] = issue["sub_issues"]
            entry["people_claiming"] = issue.get("people", 0)
            out_issues.append(entry)
        out_solutions = []
        for row in solutions:
            entry = {"id": s_ids[row["key"]], "name": row["name"],
                     "issues": [item["name"] for item in row["issues"]],
                     "approved_by": row["approves"], "opposed_by": row["opposes"],
                     "proposed_by": row["proposers"]}
            if (proposed := cite(row["proposed_in"])):
                entry["proposed_in"] = proposed
            stances = []
            for stance in row["stances"]:
                item = {"stance": stance["stance"], "date": stance["date"]}
                if (took := cite(stance["post_ids"])):
                    item["posts"] = took
                stances.append(item)
            if stances:
                entry["stances"] = stances
            out_solutions.append(entry)
        out_evidence: dict[str, dict[str, Any]] = {}

        def piece(key: str, name: str, url: str | None) -> dict[str, Any]:
            if key not in out_evidence:
                out_evidence[key] = {"id": e_ids[key], "name": name}
                if url:
                    out_evidence[key]["link"] = url
            return out_evidence[key]

        for row in evidence_rows:
            entry = piece(row["key"], row["name"], row.get("url"))
            if "source" not in entry and (line := _source_line(row, today)):
                entry["source"] = line
            kind, target = row["target_kind"], row["target_key"]
            if kind == "evidence":
                what = f"evidence {e_ids[target]}"
                side = piece(target, row["target_name"], row.get("target_url"))
                by = side.setdefault("supported_by" if row["stance"] == "supports" else "refuted_by", [])
                if e_ids[row["key"]] not in by:
                    by.append(e_ids[row["key"]])
            elif kind == "solution" and target in s_ids:
                what = f"solution {s_ids[target]}"
            else:
                what = f"{kind} {row['target_name']}"
            about: dict[str, Any] = {"what": what, "says": row["stance"]}
            if (word := READ_AS.get(row.get("check") or "")):
                about["page_read_as"] = word
            if row.get("personal"):
                about["from_personal_experience"] = True
            if (cited := cite([row["post_id"]] if row.get("post_id") else [])):
                about["post"] = cited[0]
            entry.setdefault("about", []).append(about)
        section: dict[str, Any] = {"asked_about": f"the issue {scope}" if scope else "the whole record",
                                   "issues": out_issues}
        if out_solutions:
            section["solutions"] = out_solutions
        if out_evidence:
            section["evidence"] = list(out_evidence.values())
        return section

    def post_entry(post: dict[str, Any]) -> dict[str, Any]:
        entry = {"id": p_ids[post["id"]], "by": _who(post), "date": _day(post.get("created_at"))}
        if (edited := _day(post.get("edited_at"))):
            entry["edited"] = edited
        entry["text"] = post.get("text") or ""
        return entry

    # Fit the posts against the head as if it cited every post (an upper bound), then write it again
    # citing only the posts that went in.
    budget = cap - len(_dumps(head(set(p_ids)))) - len(',"posts":[],"note":""') - 60
    kept: list[tuple[dict[str, Any], str]] = []
    for pair in ordered:
        size = len(_dumps(post_entry(pair[0]))) + 1
        if size > budget:
            break
        kept.append(pair)
        budget -= size
    kept_ids = {post["id"] for post, _ in kept}
    digest = head(kept_ids)
    if kept:
        digest["posts"] = [post_entry(post) for post, _ in kept]
    left_out = len(ordered) - len(kept)
    if left_out:
        digest["note"] = f"{left_out} more post{'s were' if left_out != 1 else ' was'} left out."

    sources: dict[str, Source] = {}
    for post, issue_key in kept:
        sources[p_ids[post["id"]]] = Source(p_ids[post["id"]], "post", _who(post), _day(post.get("created_at")),
                                            (post.get("text") or "")[:SNIPPET], search.issue_href(issue_key))
    for row in solutions:
        first = row["issues"][0]["key"] if row["issues"] else None
        sources[s_ids[row["key"]]] = Source(s_ids[row["key"]], "solution", row["name"],
                                            href=search.issue_href(first) if first else None)
    for item in digest.get("evidence", []):
        sources[item["id"]] = Source(item["id"], "evidence", item["name"],
                                     href=search.issue_href(home) if home else None)
    return Digest(_dumps(digest), sources, len(kept), left_out, [issue["key"] for issue in issues])


def _posts(key: str) -> list[tuple[dict[str, Any], str]]:
    """Q6 for one issue, each post with the date it was last edited (Q7's flags, asked for no one)."""
    posts = graph.issue_posts(key, limit=POSTS_PER_ISSUE)
    flags = graph_own_posts.post_flags(None, [post["id"] for post in posts])
    for post in posts:
        post["edited_at"] = flags.get(post["id"], {}).get("edited_at")
    return [(post, key) for post in posts]


def _issue(key: str) -> dict[str, Any] | None:
    header = graph.issue_header(key)
    if header is None:
        return None
    people = graph.issue_claimants(key)
    return {"key": header["key"], "name": header["name"], "parent": header.get("parent_name"),
            "sub_issues": [child["name"] for child in header.get("children") or []],
            "people": people["people"], "claims": people["claims"]}


def issue_digest(key: str, *, cap: int = DIGEST_CHARS, today: date | None = None) -> Digest | None:
    """The digest for a question asked on an issue's page. None when the issue is not in the record."""
    issue = _issue(key)
    if issue is None:
        return None
    return build(issue["name"], [issue], graph_ask.issue_stances(key), graph_ask.issue_evidence(key), _posts(key),
                 cap=cap, today=today)


def pick_issues(name_rows: list[dict[str, Any]], post_rows: list[dict[str, Any]],
                structure: dict[str, list[dict[str, Any]]], limit: int = RECORD_ISSUES) -> list[str]:
    """Up to `limit` issue keys for a question asked of the whole record (05_extraction.md, Phase 3):
    the issues of the names the question found (Q26) in score order, an issue for itself, a solution or
    piece of evidence for the issues it belongs to; then the issues the posts it found (Q27) claim."""
    keys: list[str] = []
    for row in name_rows:
        homes = [row["key"]] if row["label"] == "Issue" else \
            row["solution_homes"] if row["label"] == "Solution" else row["evidence_homes"]
        keys += homes
    for post in post_rows:
        keys += [edge["to_key"] for edge in structure.get(post["id"], []) if edge["rel"] == "CLAIM"]
    return list(dict.fromkeys(key for key in keys if key))[:limit]


def record_digest(question: str, *, cap: int = DIGEST_CHARS, today: date | None = None) -> Digest:
    """The digest for a question asked of the whole record: the issues the question's words find (up
    to three, then the homes of the top solutions), the top solutions and the top evidence."""
    query = search.question_query(question)
    keys: list[str] = []
    if query is not None:
        post_rows = graph_search.search_posts(query)
        keys = pick_issues(graph_search.search_names(query), post_rows,
                           graph.post_structure([post["id"] for post in post_rows]))
    top = graph_ask.top_solutions(RECORD_TOP)
    for row in top:
        for item in row["issues"]:
            if len(keys) < RECORD_ISSUES and item["key"] not in keys:
                keys.append(item["key"])
    issues, solutions, evidence, posts = [], [], [], []
    for key in keys:
        issue = _issue(key)
        if issue is None:
            continue
        issues.append(issue)
        solutions += graph_ask.issue_stances(key)
        evidence += graph_ask.issue_evidence(key)
        posts += _posts(key)
    seen_edges = {(row["key"], row["target_key"], row["stance"], row.get("post_id")) for row in evidence}
    evidence += [row for row in graph_ask.top_evidence(RECORD_TOP)
                 if (row["key"], row["target_key"], row["stance"], row.get("post_id")) not in seen_edges]
    return build(None, issues, solutions + top, evidence, posts, cap=cap, today=today)
