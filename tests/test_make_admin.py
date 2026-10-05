import pytest

from scripts import make_admin

LIVE = {"NEO4J_URI": "neo4j+s://abc123.databases.neo4j.io", "NEO4J_USERNAME": "neo4j",
        "NEO4J_PASSWORD": "pw", "NEO4J_DATABASE": "abc123"}
ARGS = ["--email", " John@Example.org ", "--name", "  john   kintree "]


@pytest.fixture
def script(monkeypatch, tmp_path):
    """A shell with only the variables a test sets, in a folder whose .env must never be read."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".env").write_text("NEO4J_URI=neo4j://from-dotenv:7687\nNEO4J_USERNAME=x\nNEO4J_PASSWORD=x\n")
    for name in ("NEO4J_URI", "NEO4J_USERNAME", "NEO4J_PASSWORD", "NEO4J_DATABASE"):
        monkeypatch.delenv(name, raising=False)
    opened, made = [], []
    monkeypatch.setattr(make_admin.graph, "open_driver", lambda settings: opened.append(settings))
    monkeypatch.setattr(make_admin.graph, "close_driver", lambda: None)
    monkeypatch.setattr(make_admin.graph, "ensure_constraints", lambda: None)
    monkeypatch.setattr(make_admin.graph_accounts, "create_root", lambda **kw: made.append(kw))
    monkeypatch.setattr("app.mailer.send", lambda *a, **kw: pytest.fail("make_admin sends nothing (X3)"))

    def env(**values):
        for name, value in values.items():
            monkeypatch.setenv(name, value)
    return opened, made, env


def test_makes_johns_root_account_and_sends_nothing(script, capsys):
    opened, made, env = script
    env(**LIVE)
    assert make_admin.main([*ARGS, "--yes"]) == 0
    root = made[0]
    assert root["email"] == "john@example.org" and root["name"] == "John kintree"
    assert root["key"].startswith("acct:") and "token_hash" not in root
    assert opened[0].neo4j_uri == LIVE["NEO4J_URI"] and opened[0].neo4j_database == "abc123"
    out = capsys.readouterr().out
    assert "abc123.databases.neo4j.io" in out and "abc123" in out
    assert "Forgot your password?" in out and "accept/" not in out


def test_make_admin_reads_only_the_shells_environment(script, capsys):
    """The .env in this folder names a database; with nothing in the shell, the script refuses."""
    opened, made, _ = script
    with pytest.raises(SystemExit) as exit_info:
        make_admin.main([*ARGS, "--yes"])
    assert exit_info.value.code == 2 and "NEO4J_URI is not set" in capsys.readouterr().err
    assert opened == [] and made == []


def test_make_admin_asks_before_writing(script, capsys):
    opened, made, env = script
    env(**LIVE)
    assert make_admin.main(ARGS) == 2
    out = capsys.readouterr()
    assert "abc123.databases.neo4j.io" in out.out and "--yes" in out.err
    assert opened == [] and made == []


def test_make_admin_refuses_a_local_database_unless_told(script):
    opened, made, env = script
    env(**{**LIVE, "NEO4J_URI": "neo4j://localhost:7687", "NEO4J_DATABASE": "neo4j"})
    with pytest.raises(SystemExit) as exit_info:
        make_admin.main([*ARGS, "--yes"])
    assert exit_info.value.code == 2 and made == []
    assert make_admin.main([*ARGS, "--yes", "--local"]) == 0 and len(made) == 1


def test_an_address_that_already_has_an_account_is_refused(script, monkeypatch, capsys):
    from app.graph_accounts import EmailTaken
    _, _, env = script
    env(**LIVE)

    def taken(**kw):
        raise EmailTaken()
    monkeypatch.setattr(make_admin.graph_accounts, "create_root", taken)
    assert make_admin.main([*ARGS, "--yes"]) == 3
    assert "already has an account" in capsys.readouterr().err


def test_a_bad_address_is_refused_before_connecting(script):
    opened, _, env = script
    env(**LIVE)
    with pytest.raises(SystemExit) as exit_info:
        make_admin.main(["--email", "not-an-address", "--name", "John Kintree", "--yes"])
    assert exit_info.value.code == 2 and opened == []


def _failures():
    from neo4j.exceptions import AuthError, ClientError, ServiceUnavailable
    from app.graph_runtime import RecordAsleep
    return [ServiceUnavailable("bolt://10.1.2.3:7687 refused"), AuthError("bad password for neo4j-user"),
            ClientError("Neo.ClientError.Database.DatabaseNotFound abc123"), RecordAsleep("asleep at 10.1.2.3")]


@pytest.mark.parametrize("where", ["open", "write"])
@pytest.mark.parametrize("failure", _failures(), ids=lambda exc: type(exc).__name__)
def test_a_database_that_cannot_be_reached_is_said_plainly(script, monkeypatch, capsys, where, failure):
    _, made, env = script
    env(**LIVE)

    def fail(*args, **kwargs):
        raise failure
    monkeypatch.setattr(make_admin.graph, "open_driver" if where == "open" else "ensure_constraints", fail)
    assert make_admin.main([*ARGS, "--yes"]) == 4
    err = capsys.readouterr().err
    assert err == (f"Could not reach the database ({type(failure).__name__}). Check the address, user and "
                   "password, and that the instance is running.\n")
    assert str(failure) not in err and "10.1.2.3" not in err and made == []


def test_make_admin_refuses_0_0_0_0_unless_told(script):
    opened, made, env = script
    env(**{**LIVE, "NEO4J_URI": "neo4j://0.0.0.0:7687", "NEO4J_DATABASE": "neo4j"})
    with pytest.raises(SystemExit) as exit_info:
        make_admin.main([*ARGS, "--yes"])
    assert exit_info.value.code == 2 and opened == [] and made == []


def test_make_admin_refuses_an_unknown_address_scheme(script, capsys):
    opened, made, env = script
    env(**{**LIVE, "NEO4J_URI": "neo4+s://user:secretpw@abc123.databases.neo4j.io"})
    with pytest.raises(SystemExit) as exit_info:
        make_admin.main([*ARGS, "--yes"])
    captured = capsys.readouterr()
    assert exit_info.value.code == 2 and opened == [] and made == []
    assert "neo4+s" in captured.err and "secretpw" not in captured.err + captured.out
    assert "Database:" not in captured.out
