"""The process database connection and query execution."""

import json
import logging
from typing import Any

from neo4j import Driver, GraphDatabase, RoutingControl
from neo4j.exceptions import ServiceUnavailable

from app.config import Settings

log = logging.getLogger("oci")
RETRY_SECONDS = 10.0


class RecordAsleep(Exception):
    """The record cannot be reached."""


def database() -> str:
    return _database


_driver: Driver | None = None
_database: str = "neo4j"


def open_driver(settings: Settings) -> Driver:
    """Create the process's one driver. A database that does not answer is a warning, not a stop."""
    global _driver, _database
    _driver = GraphDatabase.driver(
        settings.neo4j_uri,
        auth=(settings.neo4j_username, settings.neo4j_password),
        max_transaction_retry_time=RETRY_SECONDS,
    )
    _database = settings.neo4j_database
    try:
        _driver.verify_connectivity()
    except Exception as exc:  # noqa: BLE001  a paused database must not stop the process
        log.warning(json.dumps({"event": "database_unreachable", "error": type(exc).__name__}))
    return _driver


def close_driver() -> None:
    global _driver
    if _driver is not None:
        _driver.close()
        _driver = None


def driver() -> Driver:
    if _driver is None:
        raise RuntimeError("the database driver is not open")
    return _driver


def _read(query: str, **params: Any) -> list[dict[str, Any]]:
    try:
        result = driver().execute_query(
            query, params, database_=_database, routing_=RoutingControl.READ
        )
    except ServiceUnavailable as exc:
        raise RecordAsleep(str(exc)) from exc
    return [_native(record.data()) for record in result.records]


def _write(query: str, **params: Any) -> None:
    try:
        driver().execute_query(query, params, database_=_database)
    except ServiceUnavailable as exc:
        raise RecordAsleep(str(exc)) from exc


def _native(row: dict[str, Any]) -> dict[str, Any]:
    """Driver temporal values to Python datetimes, one level deep."""
    for name, value in row.items():
        if hasattr(value, "to_native"):
            row[name] = value.to_native()
    return row
