"""Make John's own account, the root of who entered whom. It sends nothing and prints no link.

Run once against production from a shell, with only the connection variables typed inline
(sub-plan F, the rollout):

    NEO4J_URI=... NEO4J_USERNAME=... NEO4J_PASSWORD=... NEO4J_DATABASE=... \
      python -m scripts.make_admin --email ADDRESS --name "John Kintree" [--country C] [--postal-code P] --yes

It reads the shell's environment only, never a .env file, so a saved development setting cannot
send it to the wrong database. It prints the database it is about to write to and needs --yes; a
database on this machine also needs --local. Afterwards John opens "Forgot your password?" on the
live site: his account is not yet accepted, so the site emails him a fresh link to choose his
password, from its own settings.

Exit codes: 0 made; 2 bad arguments, a missing NEO4J_* variable, a local database without --local,
or no --yes; 3 the address already has an account.
"""

from __future__ import annotations

import argparse
import os
import sys
import uuid
from datetime import datetime, timezone
from urllib.parse import urlsplit

from app import accounts, graph, graph_accounts
from app.config import Settings
from app.graph_accounts import EmailTaken

LOCAL_HOSTS = ("localhost", "127.0.0.1", "::1")


def _settings(parser: argparse.ArgumentParser) -> Settings:
    """Connection settings from the shell's environment only. The app's other required variables
    (passphrase, secret key, admin token) are not needed here, so they are never typed on a laptop."""
    env = os.environ
    for name in ("NEO4J_URI", "NEO4J_USERNAME", "NEO4J_PASSWORD"):
        if not env.get(name):
            parser.error(f"{name} is not set")
    return Settings("unused", "unused", "unused", env["NEO4J_URI"], env["NEO4J_USERNAME"],
                    env["NEO4J_PASSWORD"], neo4j_database=env.get("NEO4J_DATABASE") or "neo4j")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--email", required=True)
    parser.add_argument("--name", required=True)
    parser.add_argument("--country", default="")
    parser.add_argument("--postal-code", default="")
    parser.add_argument("--local", action="store_true", help="allow a database on this machine")
    parser.add_argument("--yes", action="store_true", help="make the account")
    args = parser.parse_args(argv)
    email = accounts.normalise_email(args.email)
    name = accounts.person_name(args.name)
    if not accounts.looks_like_email(email) or not name:
        parser.error("give a whole email address and a name")
    settings = _settings(parser)
    host = urlsplit(settings.neo4j_uri).hostname or ""
    if host in LOCAL_HOSTS and not args.local:
        parser.error(f"{host} is a database on this machine; add --local if that is what you mean")
    print(f"Database: {host}, {settings.neo4j_database}")
    if not args.yes:
        print("Nothing written. Add --yes to make the account.", file=sys.stderr)
        return 2
    graph.open_driver(settings)
    try:
        graph.ensure_constraints()
        try:
            graph_accounts.create_root(key=f"acct:{uuid.uuid4()}", name=name, email=email,
                                       country=" ".join(args.country.split())[:80],
                                       postal_code=" ".join(args.postal_code.split())[:20],
                                       now=datetime.now(timezone.utc))
        except EmailTaken:
            print("That address already has an account. Use Forgot your password? on the sign in page.",
                  file=sys.stderr)
            return 3
        print(f"Account made for {name}. Open Forgot your password? on the site with {email} "
              "to get the link to choose a password.")
        return 0
    finally:
        graph.close_driver()


if __name__ == "__main__":
    sys.exit(main())
