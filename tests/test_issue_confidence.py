"""Days 7 and 8: source confidence on the issue page, only with EVIDENCE_CHECK_ENABLED (03_schema.md Q39;
04_interface.md, "Source confidence, on the issue page"). Offline: Q39 is stubbed."""

from dataclasses import replace

import pytest

ISSUE = {"key": "veto", "name": "Security Council veto", "parent_key": None, "parent_name": None,
         "children": [], "created_at": None, "seed": False}
NEWS = {"source_known": True, "source_type": "news", "source_primary": False, "source_published": "2018-03-02"}
NONE = {"source_known": False, "source_type": None, "source_primary": None, "source_published": None}
ROWS = [
    {"target_kind": "issue", "target_key": "veto", "evidence_key": "report", "stance": "SUPPORTS", "check": "refutes", **NEWS},
    {"target_kind": "issue", "target_key": "veto", "evidence_key": "letter", "stance": "SUPPORTS", "check": None, **NONE},
    {"target_kind": "solution", "target_key": "abolish the veto", "evidence_key": "study", "stance": "REFUTES",
     "check": "supports", **NONE},
]
# The solutions and evidence sections with the flag off, rendered from issue.html at phase-2 54391fd
# (before source confidence): the flag off leaves it byte for byte as it was.
TODAY_SECTIONS = (
    '<h2>Proposed solutions</h2>\n'
    '<p class="counts">Listed by approvals minus oppositions.</p>\n'
    '\n'
    '<section class="solution" id="solution-abolish-the-veto">\n'
    '  <h3>Abolish the veto</h3>\n'
    '  <p class="counts">proposed by 1 · approved by <span data-approves>0</span> · opposed by <span data-opposes>0</span></p>\n'
    '  <form class="stance" method="post" action="/solutions/abolish%20the%20veto/stance">\n'
    '    <input type="hidden" name="issue" value="veto">\n'
    '    <button type="submit" name="choice" value="approve" aria-pressed="false">Approve</button>\n'
    '    <button type="submit" name="choice" value="oppose" aria-pressed="false">Oppose</button>\n'
    '    <p class="counts" role="status" data-stance-line></p>\n'
    '  </form>\n'
    '  \n'
    '  \n'
    '  \n'
    '  <p class="ev-label">Refuted by</p><ul class="evidence"><li>A study</li></ul>\n'
    '</section>\n'
    '\n'
    '\n'
    '<h2>Evidence about this issue</h2>\n'
    '\n'
    '\n'
    '<p class="ev-label">Supported by</p><ul class="evidence"><li><a href="https://example.org/report" target="_blank" rel="noopener noreferrer">UN report</a> <span class="by">submitted by Ada Tester</span></li><li>Open letter <span class="by">submitted by Anonymous</span></li></ul>\n'
    '\n'
    '\n'
    '\n'
)


def evidence():
    return [{"key": "report", "name": "UN report", "url": "https://example.org/report", "stance": "SUPPORTS",
             "submitted_by": ["Ada Tester"], "created_at": None},
            {"key": "letter", "name": "Open letter", "url": None, "stance": "SUPPORTS",
             "submitted_by": ["Anonymous"], "created_at": None}]


def solutions(key, me=None, ranked=False):
    return [{"key": "abolish the veto", "name": "Abolish the veto", "proposers": 1, "approves": 0, "opposes": 0,
             "my_stance": None, "evidence": [{"key": "study", "name": "A study", "url": None, "stance": "REFUTES"}]}]


@pytest.fixture
def page(member_app, monkeypatch):
    g = member_app.main.graph
    monkeypatch.setattr(g, "issue_header", lambda key: ISSUE if key == "veto" else None)
    monkeypatch.setattr(g, "issue_claimants", lambda key: {"claims": 0, "people": 0, "names": []})
    monkeypatch.setattr(g, "issue_evidence", lambda key: evidence())
    monkeypatch.setattr(g, "issue_posts", lambda key, limit: [])
    monkeypatch.setattr(g, "issue_solutions", solutions)
    asked = []
    monkeypatch.setattr("app.graph_evidence.issue_confidence", lambda key: asked.append(key) or ROWS)

    def get(flag):
        settings = replace(member_app.settings, evidence_check_enabled=flag)
        monkeypatch.setattr(member_app.main, "settings", settings)
        return member_app.client.get("/issues/veto").text
    member_app.sign_in()
    member_app.get, member_app.asked = get, asked
    return member_app


def section(html, start, end):
    return html[html.index(start):html.index(end)]


def test_with_the_flag_each_piece_of_evidence_says_its_source_confidence(page):
    html = page.get(True)
    assert page.asked == ["veto"]
    about = section(html, "<h2>Evidence about this issue</h2>", '<section class="feed">')
    assert ('<span class="confidence">A news report from March 2018. More than five years old. Secondary source. '
            'One other piece of evidence here says the same.</span>'
            '<span class="confidence differs">The page was read as arguing against this.</span></li>') in about
    assert '<span class="confidence">One other piece of evidence here says the same.</span></li>' in about
    solution = section(html, "<h3>Abolish the veto</h3>", "</section>")
    assert '<span class="confidence differs">The page was read as supporting this.</span></li>' in solution
    assert "confidence\">" not in solution.replace("confidence differs", "")


def test_without_the_flag_the_issue_page_is_todays(page):
    html = page.get(False)
    assert page.asked == []
    assert "confidence" not in html
    assert section(html, "<h2>Proposed solutions</h2>", '<section class="feed">') == TODAY_SECTIONS
