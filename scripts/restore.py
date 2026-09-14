"""Restore a downloaded shared record into an empty database.

    python -m scripts.restore export.json

Use the destination connection variables in the shell. Existing records are
never overwritten. Stop writers while moving a record into its new home.
"""

import argparse
from pathlib import Path
import sys

from app import graph
from app.backup import InvalidBackup, read_record
from app.config import load_settings
from app.graph_backup import NonemptyRecord


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("file", type=Path)
    args = parser.parse_args(argv)
    try:
        data = read_record(args.file)
    except InvalidBackup:
        print("The file is not a valid shared record export. Nothing was restored.", file=sys.stderr)
        return 2
    try:
        settings = load_settings()
        graph.open_driver(settings)
        nodes, relationships = graph.restore_record(data)
        print(f"Restored {nodes} records and {relationships} connections.")
        return 0
    except NonemptyRecord:
        print("Restore refused: the database is not empty. Nothing was restored.", file=sys.stderr)
        return 3
    except (Exception, SystemExit):
        print("Restore failed. Check the destination connection and try again.", file=sys.stderr)
        return 1
    finally:
        graph.close_driver()


if __name__ == "__main__":
    sys.exit(main())
