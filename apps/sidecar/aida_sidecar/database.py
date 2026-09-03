from __future__ import annotations

import hashlib
import re
import secrets
import threading
import time
from dataclasses import dataclass
from typing import Any

import pandas as pd
import sqlglot
from sqlalchemy import URL, create_engine, inspect, text

from .models import DatabaseConfig


WRITE_WORDS = {"INSERT": "insert", "UPDATE": "update", "DELETE": "delete", "CREATE": "ddl", "ALTER": "ddl", "DROP": "ddl", "TRUNCATE": "ddl", "CALL": "procedure"}


@dataclass
class PendingApproval:
    fingerprint: str
    expires_at: float


_approvals: dict[str, PendingApproval] = {}
_lock = threading.Lock()


def engine_for(config: DatabaseConfig):
    driver = "postgresql+psycopg" if config.dialect == "postgresql" else "mysql+pymysql"
    url = URL.create(driver, username=config.username, password=config.password, host=config.host, port=config.port, database=config.database)
    connect_args: dict[str, Any] = {}
    if config.dialect == "postgresql" and config.ssl_mode: connect_args["sslmode"] = config.ssl_mode
    return create_engine(url, pool_pre_ping=True, pool_recycle=300, connect_args=connect_args)


def one_statement(sql: str):
    parsed = sqlglot.parse(sql)
    if len(parsed) != 1: raise ValueError("Exactly one SQL statement is allowed")
    return parsed[0]


def classify(sql: str) -> str:
    one_statement(sql)
    first = re.match(r"^\s*([A-Za-z]+)", sql)
    word = first.group(1).upper() if first else ""
    return WRITE_WORDS.get(word, "read")


def fingerprint(sql: str, parameters: dict[str, Any], config: DatabaseConfig) -> str:
    normalized = sqlglot.transpile(sql, pretty=False)[0]
    payload = f"{config.dialect}|{config.host}|{config.port}|{config.database}|{config.username}|{normalized}|{sorted(parameters.items())}"
    return hashlib.sha256(payload.encode()).hexdigest()


def schemas(config: DatabaseConfig) -> dict[str, Any]:
    engine = engine_for(config)
    try:
        inspector = inspect(engine)
        result = []
        for schema in inspector.get_schema_names():
            if schema in {"information_schema", "pg_catalog", "mysql", "performance_schema", "sys"}: continue
            result.append({"name": schema, "tables": inspector.get_table_names(schema=schema)})
        return {"schemas": result}
    finally: engine.dispose()


def query(config: DatabaseConfig, sql: str, parameters: dict[str, Any], row_limit: int, timeout_seconds: int) -> dict[str, Any]:
    if classify(sql) != "read": raise ValueError("Write statements must use the approval endpoint")
    engine = engine_for(config)
    try:
        with engine.connect() as connection:
            if config.dialect == "postgresql": connection.execute(text(f"SET LOCAL statement_timeout = {int(timeout_seconds * 1000)}"))
            frame = pd.read_sql(text(sql), connection, params=parameters).head(row_limit + 1)
        truncated = len(frame) > row_limit
        if truncated: frame = frame.head(row_limit)
        return {"columns": [str(column) for column in frame.columns], "rows": frame.where(pd.notna(frame), None).to_dict("records"), "rowCount": len(frame), "truncated": truncated}
    finally: engine.dispose()


def prepare_write(config: DatabaseConfig, sql: str, parameters: dict[str, Any]) -> dict[str, Any]:
    operation = classify(sql)
    if operation == "read": raise ValueError("This endpoint only prepares write statements")
    expression = one_statement(sql)
    targets = sorted({table.sql() for table in expression.find_all(sqlglot.exp.Table)})
    approval_id = secrets.token_urlsafe(24)
    expires = time.time() + 300
    with _lock:
        _approvals[approval_id] = PendingApproval(fingerprint(sql, parameters, config), expires)
        for key in [key for key, item in _approvals.items() if item.expires_at < time.time()]: _approvals.pop(key, None)
    return {
        "id": approval_id, "operation": operation, "statement": sql, "parameters": parameters,
        "targetObjects": targets, "warnings": ["提交到外部数据库后无法由本应用自动撤销", "请确认目标数据库、对象和参数"],
        "expiresAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(expires)),
    }


def execute_write(config: DatabaseConfig, sql: str, parameters: dict[str, Any], approval_id: str) -> dict[str, Any]:
    current = fingerprint(sql, parameters, config)
    with _lock: approval = _approvals.pop(approval_id, None)
    if approval is None or approval.expires_at < time.time(): raise ValueError("Approval is missing or expired")
    if not secrets.compare_digest(approval.fingerprint, current): raise ValueError("SQL, parameters, or connection changed after approval")
    engine = engine_for(config)
    try:
        with engine.begin() as connection:
            result = connection.execute(text(sql), parameters)
            row_count = result.rowcount
        return {"committed": True, "rowCount": row_count}
    finally: engine.dispose()

