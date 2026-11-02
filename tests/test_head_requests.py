"""A HEAD request is answered as its GET is, without the body (UptimeRobot's free monitors check with HEAD)."""


def test_the_uptime_check_on_health_reads_the_database(member_app, monkeypatch):
    reads = []
    monkeypatch.setattr(member_app.main.graph, "health", lambda: reads.append(1) or 7)
    response = member_app.client.head("/health")
    assert response.status_code == 200 and response.content == b""
    assert response.headers["content-type"] == "application/json" and reads == [1]


def test_a_signed_out_head_check_goes_where_get_goes(member_app):
    head = member_app.client.head("/", follow_redirects=False)
    get = member_app.client.get("/", follow_redirects=False)
    assert head.status_code == get.status_code == 303 and head.headers["location"] == get.headers["location"]


def test_the_page_a_head_check_is_sent_to_answers_too(member_app):
    response = member_app.client.head("/sign-in")
    assert response.status_code == 200 and response.content == b""
    assert response.headers["content-length"] == str(len(member_app.client.get("/sign-in").content))


def test_head_reaches_no_route_that_only_takes_a_form(member_app):
    assert member_app.client.head("/posts").status_code == 405
