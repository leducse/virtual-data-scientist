#!/usr/bin/env python3
"""Local POC server for the AI-native BI report platform.

The POC intentionally uses only the Python standard library so it can run
without dependency installation. It models the product loop with SQLite as a
demo warehouse and a deterministic mock agent that can later be replaced by
Bedrock-backed orchestration.
"""

from __future__ import annotations

import csv
import datetime as dt
import hashlib
import io
import json
import math
import os
import random
import re
import sqlite3
import sys
import threading
import time
import uuid
from dataclasses import dataclass
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

from analysis_engine.deep_worker import run_local_deep_analysis
from analysis_engine.method_catalog import meaningful_numeric_columns

try:
    import boto3  # type: ignore[import-not-found]
except ImportError:  # pragma: no cover - optional real-service dependency
    boto3 = None

try:
    import psycopg  # type: ignore[import-not-found]
except ImportError:  # pragma: no cover - optional real-service dependency
    psycopg = None


BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = Path(os.environ.get("DATA_DIR", str(BASE_DIR / "data")))
STATIC_DIR = BASE_DIR / "static"
DB_PATH = DATA_DIR / "poc_warehouse.sqlite"
REPORTS_PATH = DATA_DIR / "reports.json"
ANALYSIS_PATH = DATA_DIR / "analysis_sessions.json"
ANALYSIS_ARTIFACT_DIR = DATA_DIR / "analysis_artifacts"
SESSION_DATA_SOURCES: dict[str, dict[str, Any]] = {}
ANALYSIS_LOCK = threading.Lock()


@dataclass(frozen=True)
class ServiceConfig:
    agent_mode: str
    aws_region: str
    bedrock_model_id: str
    s3_bucket: str
    s3_prefix: str
    csv_storage: str


def get_service_config() -> ServiceConfig:
    return ServiceConfig(
        agent_mode=os.environ.get("AGENT_MODE", "auto").strip().lower(),
        aws_region=os.environ.get("AWS_REGION", os.environ.get("AWS_DEFAULT_REGION", "us-east-1")),
        bedrock_model_id=os.environ.get("BEDROCK_MODEL_ID", "").strip(),
        s3_bucket=os.environ.get("S3_UPLOAD_BUCKET", "").strip(),
        s3_prefix=os.environ.get("S3_UPLOAD_PREFIX", "agentic-bi-poc/uploads").strip().strip("/"),
        csv_storage=os.environ.get("CSV_STORAGE", "local").strip().lower(),
    )

BLOCKED_SQL_KEYWORDS = {
    "alter",
    "attach",
    "call",
    "copy",
    "create",
    "delete",
    "detach",
    "drop",
    "grant",
    "insert",
    "merge",
    "pragma",
    "replace",
    "revoke",
    "truncate",
    "update",
    "vacuum",
}


def utc_now() -> str:
    return dt.datetime.now(dt.UTC).isoformat(timespec="seconds")


def ensure_dirs() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    try:
        STATIC_DIR.mkdir(parents=True, exist_ok=True)
    except OSError:
        pass
    ANALYSIS_ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)


def connect_db() -> sqlite3.Connection:
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    return con


def initialize_demo_database() -> None:
    ensure_dirs()
    con = connect_db()
    try:
        existing = con.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='orders'"
        ).fetchone()
        if existing:
            return

        con.executescript(
            """
            CREATE TABLE regions (
              id INTEGER PRIMARY KEY,
              region_name TEXT NOT NULL UNIQUE,
              vp_name TEXT NOT NULL
            );

            CREATE TABLE customers (
              id INTEGER PRIMARY KEY,
              customer_name TEXT NOT NULL,
              segment TEXT NOT NULL,
              region_id INTEGER NOT NULL REFERENCES regions(id),
              signup_date TEXT NOT NULL
            );

            CREATE TABLE products (
              id INTEGER PRIMARY KEY,
              product_name TEXT NOT NULL,
              category TEXT NOT NULL,
              unit_cost REAL NOT NULL
            );

            CREATE TABLE orders (
              id INTEGER PRIMARY KEY,
              customer_id INTEGER NOT NULL REFERENCES customers(id),
              order_date TEXT NOT NULL,
              sales_channel TEXT NOT NULL,
              status TEXT NOT NULL
            );

            CREATE TABLE order_items (
              id INTEGER PRIMARY KEY,
              order_id INTEGER NOT NULL REFERENCES orders(id),
              product_id INTEGER NOT NULL REFERENCES products(id),
              quantity INTEGER NOT NULL,
              unit_price REAL NOT NULL
            );

            CREATE TABLE sales_targets (
              id INTEGER PRIMARY KEY,
              region_id INTEGER NOT NULL REFERENCES regions(id),
              target_month TEXT NOT NULL,
              revenue_target REAL NOT NULL
            );

            CREATE TABLE returns (
              id INTEGER PRIMARY KEY,
              order_item_id INTEGER NOT NULL REFERENCES order_items(id),
              return_date TEXT NOT NULL,
              reason TEXT NOT NULL,
              quantity_returned INTEGER NOT NULL
            );

            CREATE TABLE inventory_snapshots (
              id INTEGER PRIMARY KEY,
              product_id INTEGER NOT NULL REFERENCES products(id),
              snapshot_date TEXT NOT NULL,
              warehouse_region_id INTEGER NOT NULL REFERENCES regions(id),
              on_hand_units INTEGER NOT NULL,
              reorder_point INTEGER NOT NULL
            );
            """
        )

        seed_demo_rows(con)
        con.commit()
    finally:
        con.close()


def seed_demo_rows(con: sqlite3.Connection) -> None:
    random.seed(38)

    regions = [
        (1, "Northeast", "Avery Kim"),
        (2, "Southeast", "Jordan Ellis"),
        (3, "Midwest", "Morgan Patel"),
        (4, "Southwest", "Riley Chen"),
        (5, "West", "Casey Rivera"),
    ]
    con.executemany("INSERT INTO regions VALUES (?, ?, ?)", regions)

    products = [
        ("Insight Hub License", "Software", 42.0, 119.0),
        ("Data Quality Monitor", "Software", 36.0, 99.0),
        ("Executive Brief Template", "Services", 18.0, 75.0),
        ("Warehouse Connector", "Infrastructure", 54.0, 149.0),
        ("Forecasting Add-on", "Software", 48.0, 129.0),
        ("Onboarding Sprint", "Services", 320.0, 850.0),
        ("Managed Refresh Pack", "Services", 96.0, 225.0),
        ("Embedded Analytics Seat", "Software", 24.0, 69.0),
        ("Governance Audit Pack", "Services", 180.0, 480.0),
        ("Report Distribution Pack", "Infrastructure", 44.0, 135.0),
    ]
    product_rows = []
    for idx, (name, category, cost, price) in enumerate(products, start=1):
        product_rows.append((idx, name, category, cost))
    con.executemany("INSERT INTO products VALUES (?, ?, ?, ?)", product_rows)

    first_names = [
        "Atlas",
        "Northstar",
        "Brightpath",
        "Summit",
        "Beacon",
        "Harbor",
        "Keystone",
        "Cobalt",
        "Juniper",
        "Evergreen",
        "Pioneer",
        "Crescent",
    ]
    suffixes = ["Foods", "Logistics", "Health", "Retail", "Energy", "Media", "Finance"]
    segments = ["Enterprise", "Mid-Market", "Commercial"]

    customers = []
    for customer_id in range(1, 181):
        name = f"{random.choice(first_names)} {random.choice(suffixes)} {customer_id:03d}"
        segment = random.choices(segments, weights=[0.24, 0.43, 0.33])[0]
        region_id = random.randint(1, len(regions))
        signup = dt.date(2023, 1, 1) + dt.timedelta(days=random.randint(0, 900))
        customers.append((customer_id, name, segment, region_id, signup.isoformat()))
    con.executemany("INSERT INTO customers VALUES (?, ?, ?, ?, ?)", customers)

    start_date = dt.date(2025, 1, 1)
    end_date = dt.date(2026, 6, 30)
    total_days = (end_date - start_date).days
    sales_channels = ["Direct", "Partner", "Self-Serve", "Marketplace"]
    product_prices = {idx: price for idx, (_, _, _, price) in enumerate(products, start=1)}

    order_rows = []
    item_rows = []
    return_rows = []
    item_id = 1
    return_id = 1

    for order_id in range(1, 1201):
        customer_id = random.randint(1, len(customers))
        order_date = start_date + dt.timedelta(days=random.randint(0, total_days))
        channel = random.choices(sales_channels, weights=[0.42, 0.29, 0.2, 0.09])[0]
        status = random.choices(["Complete", "Complete", "Complete", "Pending"], weights=[0.48, 0.35, 0.1, 0.07])[0]
        order_rows.append((order_id, customer_id, order_date.isoformat(), channel, status))

        for _ in range(random.randint(1, 4)):
            product_id = random.randint(1, len(products))
            quantity = random.choices([1, 2, 3, 4, 5, 8, 10], weights=[0.2, 0.24, 0.2, 0.14, 0.1, 0.07, 0.05])[0]
            list_price = product_prices[product_id]
            discount = random.choices([0, 0.05, 0.1, 0.15, 0.2], weights=[0.35, 0.25, 0.2, 0.14, 0.06])[0]
            unit_price = round(list_price * (1 - discount), 2)
            item_rows.append((item_id, order_id, product_id, quantity, unit_price))

            if status == "Complete" and random.random() < 0.055:
                return_date = order_date + dt.timedelta(days=random.randint(3, 45))
                reason = random.choice(["Defect", "Duplicate", "Expectation Gap", "Late Delivery"])
                return_quantity = random.randint(1, max(1, min(quantity, 3)))
                return_rows.append(
                    (return_id, item_id, return_date.isoformat(), reason, return_quantity)
                )
                return_id += 1
            item_id += 1

    con.executemany("INSERT INTO orders VALUES (?, ?, ?, ?, ?)", order_rows)
    con.executemany("INSERT INTO order_items VALUES (?, ?, ?, ?, ?)", item_rows)
    con.executemany("INSERT INTO returns VALUES (?, ?, ?, ?, ?)", return_rows)

    target_rows = []
    target_id = 1
    month = dt.date(2025, 1, 1)
    while month <= dt.date(2026, 6, 1):
        for region_id in range(1, len(regions) + 1):
            seasonal = 1.18 if month.month in (10, 11, 12) else 1.0
            target = round(random.uniform(85000, 145000) * seasonal, 2)
            target_rows.append((target_id, region_id, month.isoformat()[:7], target))
            target_id += 1
        next_month = month.month + 1
        next_year = month.year + (1 if next_month > 12 else 0)
        month = dt.date(next_year, 1 if next_month > 12 else next_month, 1)
    con.executemany("INSERT INTO sales_targets VALUES (?, ?, ?, ?)", target_rows)

    inventory_rows = []
    inventory_id = 1
    for region_id in range(1, len(regions) + 1):
        for product_id in range(1, len(products) + 1):
            for snapshot_date in [dt.date(2026, 4, 30), dt.date(2026, 5, 31), dt.date(2026, 6, 30)]:
                reorder_point = random.randint(140, 320)
                on_hand = random.randint(75, 620)
                inventory_rows.append(
                    (
                        inventory_id,
                        product_id,
                        snapshot_date.isoformat(),
                        region_id,
                        on_hand,
                        reorder_point,
                    )
                )
                inventory_id += 1
    con.executemany("INSERT INTO inventory_snapshots VALUES (?, ?, ?, ?, ?, ?)", inventory_rows)


def read_reports() -> dict[str, Any]:
    if not REPORTS_PATH.exists():
        return {"reports": []}
    with REPORTS_PATH.open("r", encoding="utf-8") as f:
        return json.load(f)


def write_reports(payload: dict[str, Any]) -> None:
    ensure_dirs()
    tmp_path = REPORTS_PATH.with_suffix(".tmp")
    with tmp_path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
    tmp_path.replace(REPORTS_PATH)


def empty_analysis_doc() -> dict[str, Any]:
    return {
        "sessions": [],
        "datasets": [],
        "runs": [],
        "artifacts": [],
        "messages": [],
        "audit_events": [],
        "data_sources": [],
    }


def analysis_storage_mode() -> str:
    return os.environ.get("ANALYSIS_STORAGE", "local").strip().lower()


def analysis_s3_bucket() -> str:
    return os.environ.get("ANALYSIS_STATE_BUCKET", "").strip()


def analysis_s3_prefix() -> str:
    return os.environ.get("ANALYSIS_STATE_PREFIX", "virtual-data-scientist/dev").strip().strip("/")


def use_s3_analysis_storage() -> bool:
    return analysis_storage_mode() == "s3"


def s3_client():
    if boto3 is None:
        raise RuntimeError("ANALYSIS_STORAGE=s3 requires boto3.")
    return boto3.client("s3", region_name=os.environ.get("AWS_REGION", os.environ.get("AWS_DEFAULT_REGION", "us-east-1")))


def analysis_s3_key(name: str) -> str:
    prefix = analysis_s3_prefix()
    return f"{prefix}/{name}" if prefix else name


def analysis_state_key() -> str:
    return analysis_s3_key("analysis_sessions.json")


def parse_s3_uri(uri: str) -> tuple[str, str]:
    if not uri.startswith("s3://"):
        raise ValueError(f"Expected s3:// URI, got {uri}")
    bucket_and_key = uri.removeprefix("s3://")
    bucket, _, key = bucket_and_key.partition("/")
    if not bucket or not key:
        raise ValueError(f"Invalid S3 URI: {uri}")
    return bucket, key


def s3_not_found(exc: Exception) -> bool:
    response = getattr(exc, "response", None)
    if not isinstance(response, dict):
        return False
    code = response.get("Error", {}).get("Code")
    return str(code) in {"NoSuchKey", "NoSuchBucket", "404", "NotFound"}


def read_analysis_doc() -> dict[str, Any]:
    if use_s3_analysis_storage():
        bucket = analysis_s3_bucket()
        if not bucket:
            raise RuntimeError("ANALYSIS_STATE_BUCKET is required when ANALYSIS_STORAGE=s3.")
        try:
            response = s3_client().get_object(Bucket=bucket, Key=analysis_state_key())
            doc = json.loads(response["Body"].read().decode("utf-8"))
        except Exception as exc:
            if s3_not_found(exc):
                return empty_analysis_doc()
            raise
        base = empty_analysis_doc()
        base.update({key: doc.get(key, value) for key, value in base.items()})
        return base

    if not ANALYSIS_PATH.exists():
        return empty_analysis_doc()
    with ANALYSIS_PATH.open("r", encoding="utf-8") as f:
        doc = json.load(f)
    base = empty_analysis_doc()
    base.update({key: doc.get(key, value) for key, value in base.items()})
    return base


def write_analysis_doc(payload: dict[str, Any]) -> None:
    if use_s3_analysis_storage():
        bucket = analysis_s3_bucket()
        if not bucket:
            raise RuntimeError("ANALYSIS_STATE_BUCKET is required when ANALYSIS_STORAGE=s3.")
        s3_client().put_object(
            Bucket=bucket,
            Key=analysis_state_key(),
            Body=json.dumps(payload, indent=2, default=str).encode("utf-8"),
            ContentType="application/json",
        )
        return

    ensure_dirs()
    tmp_path = ANALYSIS_PATH.with_suffix(".tmp")
    with tmp_path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
    tmp_path.replace(ANALYSIS_PATH)


def artifact_uri(artifact_id: str, extension: str) -> str:
    if use_s3_analysis_storage():
        bucket = analysis_s3_bucket()
        if not bucket:
            raise RuntimeError("ANALYSIS_STATE_BUCKET is required when ANALYSIS_STORAGE=s3.")
        return f"s3://{bucket}/{analysis_s3_key(f'artifacts/{artifact_id}.{extension}')}"
    return str(ANALYSIS_ARTIFACT_DIR / f"{artifact_id}.{extension}")


def write_analysis_artifact(
    doc: dict[str, Any],
    run_id: str,
    artifact_type: str,
    title: str,
    content: Any,
    content_type: str,
    summary: str,
) -> dict[str, Any]:
    artifact_id = f"artifact_{uuid.uuid4().hex[:12]}"
    extension = "json" if content_type == "application/json" else "txt"
    storage_uri = artifact_uri(artifact_id, extension)
    if storage_uri.startswith("s3://"):
        bucket, key = parse_s3_uri(storage_uri)
        body = (
            json.dumps(content, indent=2, default=str).encode("utf-8")
            if content_type == "application/json"
            else str(content).encode("utf-8")
        )
        s3_client().put_object(Bucket=bucket, Key=key, Body=body, ContentType=content_type)
    else:
        ensure_dirs()
        path = Path(storage_uri)
        if content_type == "application/json":
            with path.open("w", encoding="utf-8") as f:
                json.dump(content, f, indent=2)
        else:
            with path.open("w", encoding="utf-8") as f:
                f.write(str(content))

    artifact = {
        "id": artifact_id,
        "run_id": run_id,
        "artifact_type": artifact_type,
        "title": title,
        "storage_uri": storage_uri,
        "content_type": content_type,
        "summary": summary,
        "created_at": utc_now(),
    }
    doc["artifacts"].append(artifact)
    return artifact


def load_artifact_content(artifact: dict[str, Any]) -> Any:
    storage_uri = str(artifact.get("storage_uri", ""))
    if storage_uri.startswith("s3://"):
        bucket, key = parse_s3_uri(storage_uri)
        try:
            content = s3_client().get_object(Bucket=bucket, Key=key)["Body"].read().decode("utf-8")
        except Exception as exc:
            if s3_not_found(exc):
                return None
            raise
        if artifact.get("content_type") == "application/json":
            return json.loads(content)
        return content

    path = Path(storage_uri)
    if not path.exists():
        return None
    if artifact.get("content_type") == "application/json":
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    return path.read_text(encoding="utf-8")


def public_artifact(artifact: dict[str, Any], include_content: bool = False) -> dict[str, Any]:
    payload = dict(artifact)
    payload["storage_uri"] = str(payload.get("storage_uri", "")).rsplit("/", 1)[-1]
    if include_content:
        payload["content"] = load_artifact_content(artifact)
    return payload


def analysis_audit(doc: dict[str, Any], event_type: str, details: dict[str, Any]) -> None:
    doc["audit_events"].append(
        {
            "id": f"audit_{uuid.uuid4().hex[:10]}",
            "event_type": event_type,
            "details": details,
            "created_at": utc_now(),
        }
    )


def service_status() -> dict[str, Any]:
    config = get_service_config()
    return {
        "agent_mode": config.agent_mode,
        "bedrock": {
            "configured": bool(config.bedrock_model_id),
            "available": boto3 is not None and bool(config.bedrock_model_id),
            "model_id": config.bedrock_model_id or None,
            "region": config.aws_region,
            "dependency": "boto3" if boto3 is not None else "missing boto3",
        },
        "postgres": {
            "available": psycopg is not None,
            "dependency": "psycopg" if psycopg is not None else "missing psycopg",
            "env_configured": bool(os.environ.get("POSTGRES_HOST") and os.environ.get("POSTGRES_DATABASE")),
        },
        "s3": {
            "configured": bool(config.s3_bucket),
            "available": boto3 is not None and bool(config.s3_bucket),
            "bucket": config.s3_bucket or None,
            "prefix": config.s3_prefix,
            "csv_storage": config.csv_storage,
            "dependency": "boto3" if boto3 is not None else "missing boto3",
        },
    }


def public_data_source(source: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": source["id"],
        "name": source["name"],
        "type": source["type"],
        "status": source.get("status", "connected"),
        "read_only": source.get("read_only", True),
        "real_service": source.get("type") in {"postgres", "s3_csv"},
        "persisted": source.get("persisted", False),
    }


def env_postgres_source() -> dict[str, Any] | None:
    host = os.environ.get("POSTGRES_HOST", "").strip()
    database = os.environ.get("POSTGRES_DATABASE", "").strip()
    user = os.environ.get("POSTGRES_USER", "").strip()
    password = os.environ.get("POSTGRES_PASSWORD", "")
    if not host or not database:
        return None
    return {
        "id": "postgres_env",
        "name": os.environ.get("POSTGRES_NAME", "Environment Postgres"),
        "type": "postgres",
        "status": "configured",
        "read_only": True,
        "persisted": True,
        "connection": {
            "host": host,
            "port": int(os.environ.get("POSTGRES_PORT", "5432")),
            "dbname": database,
            "user": user,
            "password": password,
            "sslmode": os.environ.get("POSTGRES_SSLMODE", "prefer"),
        },
    }


def list_data_sources() -> list[dict[str, Any]]:
    sources = [
        {
            "id": "demo_warehouse",
            "name": "Demo Sales Warehouse",
            "type": "sqlite",
            "status": "connected",
            "read_only": True,
            "persisted": True,
        }
    ]
    env_source = env_postgres_source()
    if env_source:
        sources.append(env_source)
    try:
        sources.extend(read_analysis_doc().get("data_sources", []))
    except Exception:
        # Keep local app startup resilient when optional cloud state is not configured.
        pass
    sources.extend(SESSION_DATA_SOURCES.values())
    return sources


def get_data_source(data_source_id: str | None) -> dict[str, Any]:
    source_id = data_source_id or "demo_warehouse"
    for source in list_data_sources():
        if source["id"] == source_id:
            return source
    raise ValueError(f"Unknown data source: {source_id}")


def source_paramstyle(source: dict[str, Any]) -> str:
    if source["type"] == "postgres":
        return "pyformat"
    return "sqlite"


def compile_sql_template(sql_template: str, paramstyle: str = "sqlite") -> tuple[str, list[str]]:
    param_names: list[str] = []

    def repl(match: re.Match[str]) -> str:
        name = match.group(1).strip()
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name):
            raise ValueError(f"Invalid parameter name: {name}")
        if name not in param_names:
            param_names.append(name)
        if paramstyle == "pyformat":
            return f"%({name})s"
        return f":{name}"

    compiled = re.sub(r"\{\{\s*([A-Za-z_][A-Za-z0-9_]*)\s*\}\}", repl, sql_template)
    return compiled.strip(), param_names


def strip_sql_comments(sql: str) -> str:
    sql = re.sub(r"--.*?$", "", sql, flags=re.MULTILINE)
    sql = re.sub(r"/\*.*?\*/", "", sql, flags=re.DOTALL)
    return sql.strip()


def validate_select_sql(compiled_sql: str) -> str:
    cleaned = strip_sql_comments(compiled_sql)
    without_final_semicolon = cleaned[:-1].strip() if cleaned.endswith(";") else cleaned
    if ";" in without_final_semicolon:
        raise ValueError("Only one SQL statement is allowed.")

    normalized = re.sub(r"\s+", " ", without_final_semicolon).strip().lower()
    if not (normalized.startswith("select ") or normalized.startswith("with ")):
        raise ValueError("Only SELECT queries are allowed for report blocks.")

    tokens = set(re.findall(r"\b[a-z_]+\b", normalized))
    blocked = sorted(tokens & BLOCKED_SQL_KEYWORDS)
    if blocked:
        raise ValueError(f"Blocked SQL keyword: {', '.join(blocked)}")

    return without_final_semicolon


def execute_preview_query(
    sql_template: str,
    parameters: dict[str, Any] | None = None,
    limit: int = 100,
    data_source_id: str | None = None,
) -> dict[str, Any]:
    source = get_data_source(data_source_id)
    if source["type"] == "postgres":
        return execute_postgres_preview_query(source, sql_template, parameters, limit)
    if source["type"] == "s3_csv":
        materialize_csv_source(source)
    return execute_sqlite_preview_query(sql_template, parameters, limit, source["id"])


def execute_sqlite_preview_query(
    sql_template: str,
    parameters: dict[str, Any] | None = None,
    limit: int = 100,
    data_source_id: str = "demo_warehouse",
) -> dict[str, Any]:
    parameters = parameters or {}
    compiled, param_names = compile_sql_template(sql_template, "sqlite")
    safe_sql = validate_select_sql(compiled)
    max_limit = max(1, min(int(limit or 100), 500))
    query = f"SELECT * FROM ({safe_sql}) AS preview_query LIMIT :__limit"
    bound = {name: parameters.get(name) for name in param_names}
    bound["__limit"] = max_limit

    con = connect_db()
    started = dt.datetime.now(dt.UTC)
    try:
        rows = con.execute(query, bound).fetchall()
        elapsed_ms = int((dt.datetime.now(dt.UTC) - started).total_seconds() * 1000)
        columns = list(rows[0].keys()) if rows else []
        return {
            "ok": True,
            "data_source_id": data_source_id,
            "compiled_sql": safe_sql,
            "parameters_used": bound,
            "columns": columns,
            "rows": [dict(row) for row in rows],
            "row_count": len(rows),
            "elapsed_ms": elapsed_ms,
            "limit": max_limit,
        }
    except sqlite3.Error as exc:
        raise ValueError(str(exc)) from exc
    finally:
        con.close()


def execute_postgres_preview_query(
    source: dict[str, Any],
    sql_template: str,
    parameters: dict[str, Any] | None = None,
    limit: int = 100,
) -> dict[str, Any]:
    if psycopg is None:
        raise ValueError("Postgres support requires installing dependencies from requirements.txt.")

    parameters = parameters or {}
    compiled, param_names = compile_sql_template(sql_template, "pyformat")
    safe_sql = validate_select_sql(compiled)
    max_limit = max(1, min(int(limit or 100), 500))
    query = f"SELECT * FROM ({safe_sql}) AS preview_query LIMIT %(__limit)s"
    bound = {name: parameters.get(name) for name in param_names}
    bound["__limit"] = max_limit
    connection = source["connection"]

    started = dt.datetime.now(dt.UTC)
    try:
        with psycopg.connect(**connection, connect_timeout=8) as con:
            with con.cursor() as cur:
                cur.execute("SET LOCAL statement_timeout = %s", (15000,))
                cur.execute(query, bound)
                columns = [desc.name for desc in cur.description or []]
                rows = [dict(zip(columns, row, strict=False)) for row in cur.fetchall()]
        elapsed_ms = int((dt.datetime.now(dt.UTC) - started).total_seconds() * 1000)
        return {
            "ok": True,
            "data_source_id": source["id"],
            "compiled_sql": safe_sql,
            "parameters_used": bound,
            "columns": columns,
            "rows": rows,
            "row_count": len(rows),
            "elapsed_ms": elapsed_ms,
            "limit": max_limit,
        }
    except Exception as exc:  # psycopg raises multiple concrete subclasses
        raise ValueError(str(exc)) from exc


def get_schema(data_source_id: str | None = None) -> dict[str, Any]:
    source = get_data_source(data_source_id)
    if source["type"] == "postgres":
        return get_postgres_schema(source)
    if source["type"] == "s3_csv":
        materialize_csv_source(source)
        return get_sqlite_schema({str(source["table_name"])}, source["id"])
    return get_sqlite_schema()


def quote_sqlite_ident(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


def sqlite_table_names() -> list[str]:
    con = connect_db()
    try:
        return [
            row["name"]
            for row in con.execute(
                """
                SELECT name
                FROM sqlite_master
                WHERE type='table' AND name NOT LIKE 'sqlite_%'
                ORDER BY name
                """
            ).fetchall()
        ]
    finally:
        con.close()


def is_numeric_sqlite_type(type_name: str) -> bool:
    normalized = (type_name or "").upper()
    return any(token in normalized for token in ("INT", "REAL", "FLOA", "DOUB", "NUM", "DEC"))


def parse_iso_date(value: Any) -> bool:
    if value in (None, ""):
        return False
    text = str(value).strip()
    if len(text) < 8:
        return False
    try:
        dt.date.fromisoformat(text[:10])
        return True
    except ValueError:
        return False


def pearson(xs: list[float], ys: list[float]) -> float | None:
    if len(xs) < 3 or len(xs) != len(ys):
        return None
    mean_x = sum(xs) / len(xs)
    mean_y = sum(ys) / len(ys)
    numerator = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys, strict=True))
    denom_x = math.sqrt(sum((x - mean_x) ** 2 for x in xs))
    denom_y = math.sqrt(sum((y - mean_y) ** 2 for y in ys))
    if not denom_x or not denom_y:
        return None
    return round(numerator / (denom_x * denom_y), 3)


def sqlite_table_profile(con: sqlite3.Connection, table_name: str) -> dict[str, Any]:
    available_tables = sqlite_table_names()
    if table_name not in available_tables:
        raise ValueError(f"Unknown SQLite table: {table_name}")

    quoted_table = quote_sqlite_ident(table_name)
    columns = [
        {
            "name": row["name"],
            "type": row["type"] or "TEXT",
            "not_null": bool(row["notnull"]),
            "primary_key": bool(row["pk"]),
        }
        for row in con.execute(f"PRAGMA table_info({quoted_table})").fetchall()
    ]
    row_count = con.execute(f"SELECT COUNT(*) AS c FROM {quoted_table}").fetchone()["c"]
    sample_rows = [dict(row) for row in con.execute(f"SELECT * FROM {quoted_table} LIMIT 5").fetchall()]

    column_profiles = []
    numeric_columns: list[str] = []
    date_columns: list[str] = []
    categorical_columns: list[str] = []
    text_columns: list[str] = []
    warnings: list[str] = []

    for column in columns:
        col_name = column["name"]
        quoted_col = quote_sqlite_ident(col_name)
        stats_row = con.execute(
            f"""
            SELECT
              COUNT({quoted_col}) AS non_null_count,
              COUNT(DISTINCT {quoted_col}) AS distinct_count
            FROM {quoted_table}
            """
        ).fetchone()
        non_null_count = int(stats_row["non_null_count"] or 0)
        distinct_count = int(stats_row["distinct_count"] or 0)
        missing_count = max(0, int(row_count) - non_null_count)
        missing_pct = round((missing_count / row_count) * 100, 1) if row_count else 0.0
        profile: dict[str, Any] = {
            "name": col_name,
            "type": column["type"],
            "non_null_count": non_null_count,
            "missing_count": missing_count,
            "missing_pct": missing_pct,
            "distinct_count": distinct_count,
        }

        if missing_pct >= 25:
            warnings.append(f"{table_name}.{col_name} is {missing_pct}% missing.")

        if is_numeric_sqlite_type(column["type"]):
            numeric_columns.append(col_name)
            numeric = con.execute(
                f"""
                SELECT
                  MIN({quoted_col}) AS min_value,
                  MAX({quoted_col}) AS max_value,
                  AVG({quoted_col}) AS avg_value
                FROM {quoted_table}
                WHERE {quoted_col} IS NOT NULL
                """
            ).fetchone()
            profile.update(
                {
                    "min": numeric["min_value"],
                    "max": numeric["max_value"],
                    "avg": round(float(numeric["avg_value"]), 4)
                    if numeric["avg_value"] is not None
                    else None,
                }
            )
        else:
            top_rows = con.execute(
                f"""
                SELECT CAST({quoted_col} AS TEXT) AS value, COUNT(*) AS count
                FROM {quoted_table}
                WHERE {quoted_col} IS NOT NULL AND TRIM(CAST({quoted_col} AS TEXT)) <> ''
                GROUP BY CAST({quoted_col} AS TEXT)
                ORDER BY count DESC, value
                LIMIT 5
                """
            ).fetchall()
            top_values = [{"value": row["value"], "count": row["count"]} for row in top_rows]
            profile["top_values"] = top_values
            sample_values = [row.get(col_name) for row in sample_rows]
            if "date" in col_name.lower() or sum(parse_iso_date(value) for value in sample_values) >= 2:
                date_columns.append(col_name)
                profile["semantic_type"] = "date"
            elif distinct_count and distinct_count <= min(30, max(10, row_count // 10 if row_count else 10)):
                categorical_columns.append(col_name)
                profile["semantic_type"] = "category"
            else:
                text_columns.append(col_name)
                profile["semantic_type"] = "text"

        column_profiles.append(profile)

    table_shape = {"numeric_columns": numeric_columns}
    meaningful_numeric = meaningful_numeric_columns(table_shape)
    if numeric_columns and not meaningful_numeric:
        warnings.append(
            f"{table_name} has numeric fields, but they look ID-like or are not clear business measures."
        )

    correlations = []
    for left_index, left in enumerate(meaningful_numeric[:6]):
        for right in meaningful_numeric[left_index + 1 : 6]:
            left_q = quote_sqlite_ident(left)
            right_q = quote_sqlite_ident(right)
            pair_rows = con.execute(
                f"""
                SELECT {left_q} AS x, {right_q} AS y
                FROM {quoted_table}
                WHERE {left_q} IS NOT NULL AND {right_q} IS NOT NULL
                LIMIT 1000
                """
            ).fetchall()
            xs = [float(row["x"]) for row in pair_rows]
            ys = [float(row["y"]) for row in pair_rows]
            corr = pearson(xs, ys)
            if corr is not None and abs(corr) >= 0.35:
                correlations.append({"left": left, "right": right, "correlation": corr})

    methods = []
    if date_columns and meaningful_numeric:
        methods.append(
            {
                "type": "forecasting",
                "reason": (
                    f"Detected date columns ({', '.join(date_columns[:3])}) and "
                    f"business measures ({', '.join(meaningful_numeric[:3])})."
                ),
            }
        )
    if categorical_columns and meaningful_numeric:
        methods.append(
            {
                "type": "classification_or_group_comparison",
                "reason": (
                    f"Detected categorical fields ({', '.join(categorical_columns[:3])}) "
                    f"with business measures ({', '.join(meaningful_numeric[:3])})."
                ),
            }
        )
    if len(meaningful_numeric) >= 2 or (meaningful_numeric and categorical_columns):
        methods.append(
            {
                "type": "regression_or_drivers",
                "reason": "Business measures and grouping fields can support driver analysis if a target is selected.",
            }
        )
    if meaningful_numeric:
        methods.append(
            {
                "type": "anomaly_detection",
                "reason": f"Business measures ({', '.join(meaningful_numeric[:3])}) can be scanned for unusual records or segments.",
            }
        )
    if len(meaningful_numeric) >= 2 and (categorical_columns or len(meaningful_numeric) >= 3):
        methods.append(
            {
                "type": "clustering_or_segmentation",
                "reason": "The table has enough non-ID business dimensions for exploratory grouping.",
            }
        )
    if text_columns:
        methods.append(
            {
                "type": "text_analysis",
                "reason": f"Detected free-text-like fields ({', '.join(text_columns[:3])}).",
            }
        )
    if not methods:
        reason = "The table is best suited for summaries until a clearer target or richer data is provided."
        if date_columns and numeric_columns and not meaningful_numeric:
            reason = (
                "Detected date columns, but no clear non-ID business measure; use descriptive trend counts "
                "before forecasting."
            )
        methods.append(
            {
                "type": "descriptive_analysis",
                "reason": reason,
            }
        )

    return {
        "table_name": table_name,
        "row_count": row_count,
        "column_count": len(columns),
        "columns": column_profiles,
        "numeric_columns": numeric_columns,
        "meaningful_numeric_columns": meaningful_numeric,
        "date_columns": date_columns,
        "categorical_columns": categorical_columns,
        "text_columns": text_columns,
        "correlations": correlations[:10],
        "candidate_methods": methods,
        "warnings": warnings,
        "sample_rows": sample_rows,
    }


def build_light_profile(data_source_id: str, table_name: str | None, user_question: str) -> dict[str, Any]:
    source = get_data_source(data_source_id)
    now = utc_now()
    if source["type"] == "postgres":
        schema = get_postgres_schema(source)
        return {
            "data_source_id": source["id"],
            "data_source_name": source["name"],
            "data_source_type": source["type"],
            "table_name": table_name or "schema_only",
            "generated_at": now,
            "user_question": user_question,
            "tables": schema.get("tables", [])[:8],
            "candidate_methods": [
                {
                    "type": "schema_review",
                    "reason": "Postgres light analysis is currently schema-only in the local POC.",
                }
            ],
            "warnings": [
                "Postgres profiling is intentionally schema-only until query cost controls and metadata persistence are added."
            ],
        }

    if source["type"] == "s3_csv":
        materialize_csv_source(source)
        available = [str(source["table_name"])]
        if not table_name:
            table_name = str(source["table_name"])
    else:
        available = sqlite_table_names()
    selected_tables = [table_name] if table_name else available[:6]
    con = connect_db()
    try:
        table_profiles = [sqlite_table_profile(con, table) for table in selected_tables if table in available]
    finally:
        con.close()

    if not table_profiles:
        raise ValueError("No analyzable tables were found for the selected data source.")

    warnings = []
    methods_by_type: dict[str, dict[str, Any]] = {}
    for table in table_profiles:
        warnings.extend(table.get("warnings", []))
        for method in table.get("candidate_methods", []):
            methods_by_type.setdefault(method["type"], method)

    fingerprint_source = json.dumps(
        {
            "data_source_id": source["id"],
            "tables": [
                {
                    "table_name": table["table_name"],
                    "row_count": table["row_count"],
                    "columns": [
                        {
                            "name": column["name"],
                            "type": column["type"],
                            "missing_count": column["missing_count"],
                            "distinct_count": column["distinct_count"],
                        }
                        for column in table["columns"]
                    ],
                }
                for table in table_profiles
            ],
        },
        sort_keys=True,
    )
    fingerprint = "sha256:" + hashlib.sha256(fingerprint_source.encode("utf-8")).hexdigest()

    return {
        "data_source_id": source["id"],
        "data_source_name": source["name"],
        "data_source_type": source["type"],
        "storage_uri": source.get("storage_uri"),
        "table_name": table_name or "all_tables",
        "generated_at": now,
        "user_question": user_question,
        "dataset_fingerprint": fingerprint,
        "table_count": len(table_profiles),
        "tables": table_profiles,
        "candidate_methods": list(methods_by_type.values()),
        "warnings": warnings[:12],
    }


def build_light_analysis_code(profile: dict[str, Any]) -> str:
    table_names = [table.get("table_name") for table in profile.get("tables", [])]
    return f'''#!/usr/bin/env python3
"""Reproduce the light analysis profile generated by the POC.

This script uses only the Python standard library. It expects to run from the
project root with the local SQLite warehouse at data/poc_warehouse.sqlite.
"""

import sqlite3
from pathlib import Path

DB_PATH = Path("data/poc_warehouse.sqlite")
TABLES = {table_names!r}


def quote_ident(name):
    return '"' + name.replace('"', '""') + '"'


def profile_table(connection, table_name):
    table = quote_ident(table_name)
    row_count = connection.execute(f"SELECT COUNT(*) AS c FROM {{table}}").fetchone()[0]
    columns = connection.execute(f"PRAGMA table_info({{table}})").fetchall()
    results = {{"table_name": table_name, "row_count": row_count, "columns": []}}
    for column in columns:
        name = column[1]
        quoted = quote_ident(name)
        row = connection.execute(
            f"SELECT COUNT({{quoted}}), COUNT(DISTINCT {{quoted}}) FROM {{table}}"
        ).fetchone()
        results["columns"].append(
            {{"name": name, "type": column[2], "non_null_count": row[0], "distinct_count": row[1]}}
        )
    return results


def main():
    with sqlite3.connect(DB_PATH) as connection:
        for table_name in TABLES:
            print(profile_table(connection, table_name))


if __name__ == "__main__":
    main()
'''


def build_light_report(profile: dict[str, Any]) -> str:
    lines = [
        "# Light Analysis Summary",
        "",
        f"Data source: {profile.get('data_source_name')} ({profile.get('data_source_type')})",
        f"Scope: {profile.get('table_name')}",
        f"Generated at: {profile.get('generated_at')}",
        "",
        "## Candidate Analysis Paths",
    ]
    for method in profile.get("candidate_methods", []):
        lines.append(f"- {method['type']}: {method['reason']}")
    warnings = profile.get("warnings") or []
    if warnings:
        lines.extend(["", "## Data Quality Warnings"])
        lines.extend(f"- {warning}" for warning in warnings)
    lines.extend(["", "## Tables"])
    for table in profile.get("tables", []):
        lines.append(
            f"- {table['table_name']}: {table['row_count']} rows, {table['column_count']} columns"
        )
        if table.get("numeric_columns"):
            lines.append(f"  - Numeric: {', '.join(table['numeric_columns'][:6])}")
        if table.get("categorical_columns"):
            lines.append(f"  - Categorical: {', '.join(table['categorical_columns'][:6])}")
        if table.get("date_columns"):
            lines.append(f"  - Date/time: {', '.join(table['date_columns'][:6])}")
    return "\n".join(lines) + "\n"


def latest_item(items: list[dict[str, Any]], key: str = "created_at") -> dict[str, Any] | None:
    if not items:
        return None
    return sorted(items, key=lambda item: str(item.get(key, "")), reverse=True)[0]


def find_record(doc: dict[str, Any], collection: str, record_id: str) -> dict[str, Any]:
    for item in doc.get(collection, []):
        if item.get("id") == record_id:
            return item
    raise ValueError(f"Unknown {collection.rstrip('s')}: {record_id}")


def create_analysis_session(payload: dict[str, Any]) -> dict[str, Any]:
    now = utc_now()
    user_goal = str(payload.get("user_goal") or "Explore this dataset.").strip()
    data_source_id = str(payload.get("data_source_id") or "demo_warehouse")
    table_name = str(payload.get("table_name") or "").strip() or None
    get_data_source(data_source_id)

    with ANALYSIS_LOCK:
        doc = read_analysis_doc()
        session = {
            "id": f"sess_{uuid.uuid4().hex[:12]}",
            "workspace_id": "local_poc",
            "owner_user_id": "local_user",
            "title": user_goal[:80] or "Analysis Session",
            "current_dataset_id": None,
            "user_goal": user_goal,
            "data_source_id": data_source_id,
            "table_name": table_name,
            "status": "active",
            "created_at": now,
            "updated_at": now,
        }
        doc["sessions"].append(session)
        doc["messages"].append(
            {
                "id": f"msg_{uuid.uuid4().hex[:10]}",
                "session_id": session["id"],
                "actor": "user",
                "message_text": user_goal,
                "related_run_id": None,
                "created_at": now,
            }
        )
        analysis_audit(doc, "analysis_session_created", {"session_id": session["id"]})
        write_analysis_doc(doc)
    return {"ok": True, "session": session}


def ensure_analysis_session(doc: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
    session_id = str(payload.get("session_id") or "").strip()
    if session_id:
        return find_record(doc, "sessions", session_id)

    now = utc_now()
    session = {
        "id": f"sess_{uuid.uuid4().hex[:12]}",
        "workspace_id": "local_poc",
        "owner_user_id": "local_user",
        "title": str(payload.get("user_question") or payload.get("user_goal") or "Analysis Session")[:80],
        "current_dataset_id": None,
        "user_goal": str(payload.get("user_question") or payload.get("user_goal") or "Explore this dataset."),
        "data_source_id": str(payload.get("data_source_id") or "demo_warehouse"),
        "table_name": str(payload.get("table_name") or "").strip() or None,
        "status": "active",
        "created_at": now,
        "updated_at": now,
    }
    doc["sessions"].append(session)
    analysis_audit(doc, "analysis_session_created", {"session_id": session["id"], "implicit": True})
    return session


def upsert_dataset_from_profile(doc: dict[str, Any], session: dict[str, Any], profile: dict[str, Any]) -> dict[str, Any]:
    fingerprint = profile.get("dataset_fingerprint")
    data_source_id = profile.get("data_source_id")
    table_name = profile.get("table_name")
    for dataset in doc["datasets"]:
        if (
            dataset.get("workspace_id") == session.get("workspace_id")
            and dataset.get("data_source_id") == data_source_id
            and dataset.get("table_name") == table_name
            and dataset.get("fingerprint") == fingerprint
        ):
            session["current_dataset_id"] = dataset["id"]
            return dataset

    row_count = sum(int(table.get("row_count") or 0) for table in profile.get("tables", []))
    column_count = sum(int(table.get("column_count") or 0) for table in profile.get("tables", []))
    dataset = {
        "id": f"ds_{uuid.uuid4().hex[:12]}",
        "workspace_id": session.get("workspace_id", "local_poc"),
        "source_type": profile.get("data_source_type"),
        "data_source_id": data_source_id,
        "display_name": f"{profile.get('data_source_name')} / {table_name}",
        "table_name": table_name,
        "storage_uri": profile.get("storage_uri") or f"sqlite://{DB_PATH.name}/{table_name}",
        "fingerprint": fingerprint,
        "row_count": row_count,
        "column_count": column_count,
        "schema_json": {
            "tables": [
                {
                    "table_name": table.get("table_name"),
                    "columns": [
                        {"name": column.get("name"), "type": column.get("type")}
                        for column in table.get("columns", [])
                    ],
                }
                for table in profile.get("tables", [])
            ]
        },
        "created_at": utc_now(),
    }
    doc["datasets"].append(dataset)
    session["current_dataset_id"] = dataset["id"]
    return dataset


def run_light_analysis(payload: dict[str, Any]) -> dict[str, Any]:
    user_question = str(payload.get("user_question") or "").strip()
    data_source_id = str(payload.get("data_source_id") or "demo_warehouse")
    table_name = str(payload.get("table_name") or "").strip() or None
    profile = build_light_profile(data_source_id, table_name, user_question)
    code = build_light_analysis_code(profile)
    report = build_light_report(profile)
    now = utc_now()

    with ANALYSIS_LOCK:
        doc = read_analysis_doc()
        session = ensure_analysis_session(doc, payload)
        session["data_source_id"] = data_source_id
        session["table_name"] = table_name
        session["updated_at"] = now
        dataset = upsert_dataset_from_profile(doc, session, profile)
        run = {
            "id": f"run_{uuid.uuid4().hex[:12]}",
            "session_id": session["id"],
            "dataset_id": dataset["id"],
            "run_type": "light",
            "status": "succeeded",
            "user_question": user_question,
            "selected_analysis_type": (profile.get("candidate_methods") or [{}])[0].get("type"),
            "agentcore_session_id": None,
            "started_at": now,
            "finished_at": utc_now(),
            "error_message": None,
        }
        doc["runs"].append(run)
        profile_artifact = write_analysis_artifact(
            doc,
            run["id"],
            "profile",
            "Light analysis profile",
            profile,
            "application/json",
            f"Profiled {profile.get('table_count', 1)} table(s) and inferred candidate methods.",
        )
        code_artifact = write_analysis_artifact(
            doc,
            run["id"],
            "code",
            "Light analysis reproduction code",
            code,
            "text/x-python",
            "Python code used to reproduce the initial profile.",
        )
        report_artifact = write_analysis_artifact(
            doc,
            run["id"],
            "report",
            "Light analysis summary",
            report,
            "text/markdown",
            "Plain-English summary of data shape, warnings, and likely analysis paths.",
        )
        doc["messages"].append(
            {
                "id": f"msg_{uuid.uuid4().hex[:10]}",
                "session_id": session["id"],
                "actor": "agent",
                "message_text": "Completed light analysis and stored profile, code, and summary artifacts.",
                "related_run_id": run["id"],
                "created_at": utc_now(),
            }
        )
        analysis_audit(
            doc,
            "light_analysis_succeeded",
            {"session_id": session["id"], "dataset_id": dataset["id"], "run_id": run["id"]},
        )
        write_analysis_doc(doc)

    return {
        "ok": True,
        "session": session,
        "dataset": dataset,
        "run": run,
        "profile": profile,
        "artifacts": [
            public_artifact(profile_artifact, include_content=True),
            public_artifact(code_artifact, include_content=True),
            public_artifact(report_artifact, include_content=True),
        ],
    }


def artifacts_for_run(doc: dict[str, Any], run_id: str, include_content: bool = False) -> list[dict[str, Any]]:
    return [
        public_artifact(artifact, include_content=include_content)
        for artifact in doc.get("artifacts", [])
        if artifact.get("run_id") == run_id
    ]


def latest_light_context(doc: dict[str, Any], session_id: str) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    light_runs = [
        run
        for run in doc.get("runs", [])
        if run.get("session_id") == session_id and run.get("run_type") == "light" and run.get("status") == "succeeded"
    ]
    light_run = latest_item(light_runs, "finished_at")
    if not light_run:
        return None, []
    return light_run, artifacts_for_run(doc, light_run["id"], include_content=False)


def build_context_bundle(
    session: dict[str, Any],
    dataset: dict[str, Any] | None,
    user_question: str,
    light_run: dict[str, Any] | None,
    light_artifacts: list[dict[str, Any]],
    constraints: dict[str, Any],
) -> dict[str, Any]:
    by_type = {artifact.get("artifact_type"): artifact for artifact in light_artifacts}
    return {
        "session_id": session["id"],
        "dataset_id": dataset.get("id") if dataset else session.get("current_dataset_id"),
        "dataset_uri": dataset.get("storage_uri") if dataset else None,
        "dataset_fingerprint": dataset.get("fingerprint") if dataset else None,
        "user_question": user_question,
        "light_analysis_run_id": light_run.get("id") if light_run else None,
        "light_analysis_report_id": by_type.get("report", {}).get("id"),
        "light_analysis_code_id": by_type.get("code", {}).get("id"),
        "schema_profile_id": by_type.get("profile", {}).get("id"),
        "prior_run_ids": [
            run["id"]
            for run in read_analysis_doc().get("runs", [])
            if run.get("session_id") == session["id"]
        ],
        "constraints": constraints,
    }


def request_deep_analysis(payload: dict[str, Any]) -> dict[str, Any]:
    session_id = str(payload.get("session_id") or "").strip()
    if not session_id:
        raise ValueError("session_id is required before requesting deep analysis.")
    user_question = str(payload.get("user_question") or "").strip()
    constraints = payload.get("constraints") if isinstance(payload.get("constraints"), dict) else {}
    if not user_question:
        user_question = "Continue from the light analysis and recommend the best deeper analysis path."
    constraints = {
        "max_runtime_minutes": int(constraints.get("max_runtime_minutes") or 15),
        "privacy_mode": str(constraints.get("privacy_mode") or "registered_dataset_only"),
        "agentcore_mode": os.environ.get("DEEP_ANALYSIS_AGENT_MODE", "local_worker"),
    }

    now = utc_now()
    with ANALYSIS_LOCK:
        doc = read_analysis_doc()
        session = find_record(doc, "sessions", session_id)
        dataset = None
        if session.get("current_dataset_id"):
            dataset = find_record(doc, "datasets", session["current_dataset_id"])
        light_run, light_artifacts = latest_light_context(doc, session_id)
        context_bundle = build_context_bundle(session, dataset, user_question, light_run, light_artifacts, constraints)
        run = {
            "id": f"run_{uuid.uuid4().hex[:12]}",
            "session_id": session["id"],
            "dataset_id": dataset.get("id") if dataset else None,
            "run_type": "deep",
            "status": "queued",
            "user_question": user_question,
            "selected_analysis_type": "local_deep_analysis",
            "agentcore_session_id": f"local_worker_{uuid.uuid4().hex[:10]}",
            "started_at": None,
            "finished_at": None,
            "error_message": None,
            "queued_at": now,
        }
        doc["runs"].append(run)
        context_artifact = write_analysis_artifact(
            doc,
            run["id"],
            "context_bundle",
            "AgentCore handoff context bundle",
            context_bundle,
            "application/json",
            "References the dataset, light-analysis report, code, schema profile, and constraints.",
        )
        doc["messages"].append(
            {
                "id": f"msg_{uuid.uuid4().hex[:10]}",
                "session_id": session["id"],
                "actor": "agent",
                "message_text": "Queued local deep analysis with the light-analysis context bundle.",
                "related_run_id": run["id"],
                "created_at": now,
            }
        )
        analysis_audit(doc, "deep_analysis_queued", {"session_id": session["id"], "run_id": run["id"]})
        write_analysis_doc(doc)

    if os.environ.get("DEEP_ANALYSIS_EXECUTION_MODE", "background").strip().lower() == "inline":
        complete_deep_analysis_worker(run["id"])
        with ANALYSIS_LOCK:
            doc = read_analysis_doc()
            run = find_record(doc, "runs", run["id"])
            artifacts = artifacts_for_run(doc, run["id"], include_content=True)
        return {
            "ok": True,
            "run": run,
            "context_bundle": context_bundle,
            "artifacts": artifacts,
        }

    thread = threading.Thread(target=complete_deep_analysis_worker, args=(run["id"],), daemon=True)
    thread.start()

    return {
        "ok": True,
        "run": run,
        "context_bundle": context_bundle,
        "artifacts": [public_artifact(context_artifact, include_content=True)],
    }


def update_run_status(run_id: str, status: str, updates: dict[str, Any] | None = None) -> None:
    with ANALYSIS_LOCK:
        doc = read_analysis_doc()
        run = find_record(doc, "runs", run_id)
        run["status"] = status
        if updates:
            run.update(updates)
        analysis_audit(doc, f"analysis_run_{status}", {"run_id": run_id})
        write_analysis_doc(doc)


def complete_deep_analysis_worker(run_id: str) -> None:
    time.sleep(0.25)
    update_run_status(run_id, "running", {"started_at": utc_now()})
    try:
        with ANALYSIS_LOCK:
            doc = read_analysis_doc()
            context_artifacts = [
                artifact
                for artifact in doc["artifacts"]
                if artifact.get("run_id") == run_id and artifact.get("artifact_type") == "context_bundle"
            ]
            context = load_artifact_content(context_artifacts[0]) if context_artifacts else {}
            profile_artifact_id = context.get("schema_profile_id") if isinstance(context, dict) else None
            profile_artifact = (
                find_record(doc, "artifacts", str(profile_artifact_id)) if profile_artifact_id else None
            )
            profile = load_artifact_content(profile_artifact) if profile_artifact else {}

        worker_result = run_local_deep_analysis(
            context_bundle=context if isinstance(context, dict) else {},
            profile=profile if isinstance(profile, dict) else {},
            db_path=DB_PATH,
        )
        report = worker_result["report"]
        code = worker_result["code"]
        primary_method = report.get("primary_method", {})

        with ANALYSIS_LOCK:
            doc = read_analysis_doc()
            run = find_record(doc, "runs", run_id)
            report_artifact = write_analysis_artifact(
                doc,
                run_id,
                "report",
                "Local deep analysis report",
                report,
                "application/json",
                str(report.get("summary") or "Local deep-analysis report."),
            )
            code_artifact = write_analysis_artifact(
                doc,
                run_id,
                "code",
                "Deep analysis reproduction code",
                code,
                "text/x-python",
                "Python code used by the local deep-analysis worker.",
            )
            run["status"] = "succeeded"
            run["selected_analysis_type"] = primary_method.get("type", "local_deep_analysis")
            run["finished_at"] = utc_now()
            doc["messages"].append(
                {
                    "id": f"msg_{uuid.uuid4().hex[:10]}",
                    "session_id": run["session_id"],
                    "actor": "agent",
                    "message_text": "Local deep analysis completed and stored report and code artifacts.",
                    "related_run_id": run_id,
                    "created_at": utc_now(),
                }
            )
            analysis_audit(
                doc,
                "deep_analysis_succeeded",
                {"run_id": run_id, "artifact_ids": [report_artifact["id"], code_artifact["id"]]},
            )
            write_analysis_doc(doc)
    except Exception as exc:  # pragma: no cover - defensive async failure path
        update_run_status(run_id, "failed", {"finished_at": utc_now(), "error_message": str(exc)})


def get_analysis_status(run_id: str) -> dict[str, Any]:
    with ANALYSIS_LOCK:
        doc = read_analysis_doc()
        run = find_record(doc, "runs", run_id)
        return {"ok": True, "run": run, "artifacts": artifacts_for_run(doc, run_id, include_content=True)}


def list_analysis_sessions() -> dict[str, Any]:
    with ANALYSIS_LOCK:
        doc = read_analysis_doc()
        return {
            "ok": True,
            "sessions": doc["sessions"],
            "datasets": doc["datasets"],
            "runs": doc["runs"],
            "artifacts": [public_artifact(artifact) for artifact in doc["artifacts"]],
        }


def get_analysis_session_detail(session_id: str) -> dict[str, Any]:
    if not session_id:
        raise ValueError("session_id is required.")

    with ANALYSIS_LOCK:
        doc = read_analysis_doc()
        session = find_record(doc, "sessions", session_id)
        dataset = None
        if session.get("current_dataset_id"):
            dataset = find_record(doc, "datasets", session["current_dataset_id"])
        runs = [run for run in doc["runs"] if run.get("session_id") == session_id]
        run_ids = {run["id"] for run in runs}
        artifacts = [
            public_artifact(artifact)
            for artifact in doc["artifacts"]
            if artifact.get("run_id") in run_ids
        ]
        messages = [
            {
                "id": message.get("id"),
                "session_id": message.get("session_id"),
                "actor": message.get("actor"),
                "message_text": message.get("message_text"),
                "related_run_id": message.get("related_run_id"),
                "created_at": message.get("created_at"),
            }
            for message in doc["messages"]
            if message.get("session_id") == session_id
        ]

    return {
        "ok": True,
        "session": session,
        "dataset": dataset,
        "runs": sorted(runs, key=lambda run: str(run.get("queued_at") or run.get("started_at") or run.get("finished_at") or "")),
        "artifacts": sorted(artifacts, key=lambda artifact: str(artifact.get("created_at") or "")),
        "messages": sorted(messages, key=lambda message: str(message.get("created_at") or "")),
    }


def continue_analysis(payload: dict[str, Any]) -> dict[str, Any]:
    session_id = str(payload.get("session_id") or "").strip()
    message = str(payload.get("message") or "").strip()
    if not session_id:
        raise ValueError("session_id is required.")
    if not message:
        raise ValueError("message is required.")

    with ANALYSIS_LOCK:
        doc = read_analysis_doc()
        session = find_record(doc, "sessions", session_id)
        now = utc_now()
        doc["messages"].append(
            {
                "id": f"msg_{uuid.uuid4().hex[:10]}",
                "session_id": session_id,
                "actor": "user",
                "message_text": message,
                "related_run_id": None,
                "created_at": now,
            }
        )
        session["updated_at"] = now
        related_runs = [run for run in doc["runs"] if run.get("session_id") == session_id]
        related_artifacts = [
            public_artifact(artifact)
            for artifact in doc["artifacts"]
            if artifact.get("run_id") in {run["id"] for run in related_runs}
        ]
        analysis_audit(doc, "analysis_session_continued", {"session_id": session_id})
        write_analysis_doc(doc)
    return {
        "ok": True,
        "session": session,
        "message": "Follow-up saved. Run light or deep analysis again to produce new artifacts.",
        "run_count": len(related_runs),
        "artifacts": related_artifacts,
    }


def get_sqlite_schema(
    table_filter: set[str] | None = None,
    active_data_source_id: str = "demo_warehouse",
) -> dict[str, Any]:
    con = connect_db()
    try:
        tables = []
        table_rows = con.execute(
            """
            SELECT name
            FROM sqlite_master
            WHERE type='table' AND name NOT LIKE 'sqlite_%'
            ORDER BY name
            """
        ).fetchall()
        for table in table_rows:
            table_name = table["name"]
            if table_filter is not None and table_name not in table_filter:
                continue
            columns = [
                {
                    "name": row["name"],
                    "type": row["type"] or "TEXT",
                    "not_null": bool(row["notnull"]),
                    "primary_key": bool(row["pk"]),
                }
                for row in con.execute(f'PRAGMA table_info("{table_name}")').fetchall()
            ]
            count = con.execute(f'SELECT COUNT(*) AS c FROM "{table_name}"').fetchone()["c"]
            sample = [
                dict(row)
                for row in con.execute(f'SELECT * FROM "{table_name}" LIMIT 3').fetchall()
            ]
            tables.append(
                {
                    "name": table_name,
                    "columns": columns,
                    "row_count": count,
                    "sample": sample,
                }
            )
        return {
            "active_data_source_id": active_data_source_id,
            "data_sources": [public_data_source(source) for source in list_data_sources()],
            "tables": tables,
            "regions": [row["region_name"] for row in con.execute("SELECT region_name FROM regions ORDER BY region_name")],
        }
    finally:
        con.close()


def quote_pg_ident(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


def get_postgres_schema(source: dict[str, Any]) -> dict[str, Any]:
    if psycopg is None:
        raise ValueError("Postgres support requires installing dependencies from requirements.txt.")

    connection = source["connection"]
    try:
        with psycopg.connect(**connection, connect_timeout=8) as con:
            with con.cursor() as cur:
                cur.execute(
                    """
                    SELECT table_schema, table_name, column_name, data_type, is_nullable, ordinal_position
                    FROM information_schema.columns
                    WHERE table_schema NOT IN ('pg_catalog', 'information_schema')
                    ORDER BY table_schema, table_name, ordinal_position
                    """
                )
                rows = cur.fetchall()

                grouped: dict[tuple[str, str], list[dict[str, Any]]] = {}
                for schema_name, table_name, column_name, data_type, is_nullable, _ordinal in rows:
                    grouped.setdefault((schema_name, table_name), []).append(
                        {
                            "name": column_name,
                            "type": data_type,
                            "not_null": is_nullable == "NO",
                            "primary_key": False,
                        }
                    )

                tables = []
                for (schema_name, table_name), columns in grouped.items():
                    sample_rows: list[dict[str, Any]] = []
                    try:
                        sample_sql = (
                            f"SELECT * FROM {quote_pg_ident(schema_name)}.{quote_pg_ident(table_name)} LIMIT 3"
                        )
                        cur.execute(sample_sql)
                        sample_cols = [desc.name for desc in cur.description or []]
                        sample_rows = [dict(zip(sample_cols, row, strict=False)) for row in cur.fetchall()]
                    except Exception:
                        sample_rows = []
                    tables.append(
                        {
                            "name": f"{schema_name}.{table_name}",
                            "schema": schema_name,
                            "table": table_name,
                            "columns": columns,
                            "row_count": None,
                            "sample": sample_rows,
                        }
                    )
        return {
            "active_data_source_id": source["id"],
            "data_sources": [public_data_source(item) for item in list_data_sources()],
            "tables": tables,
            "regions": [],
        }
    except Exception as exc:
        raise ValueError(str(exc)) from exc


def infer_column_type(values: list[str]) -> str:
    non_blank = [value for value in values if value not in ("", None)]
    if not non_blank:
        return "TEXT"
    int_ok = True
    real_ok = True
    for value in non_blank:
        try:
            int(value)
        except ValueError:
            int_ok = False
        try:
            float(value)
        except ValueError:
            real_ok = False
    if int_ok:
        return "INTEGER"
    if real_ok:
        return "REAL"
    return "TEXT"


def sanitize_identifier(name: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_]+", "_", name.strip().lower()).strip("_")
    if not cleaned:
        cleaned = "uploaded_data"
    if cleaned[0].isdigit():
        cleaned = f"t_{cleaned}"
    return cleaned[:48]


def upload_csv_table(
    name: str,
    csv_text: str,
    table_name: str | None = None,
    replace_existing: bool = False,
) -> dict[str, Any]:
    reader = csv.DictReader(io.StringIO(csv_text))
    if not reader.fieldnames:
        raise ValueError("CSV is missing a header row.")

    rows = list(reader)
    if not rows:
        raise ValueError("CSV does not contain data rows.")

    base_table = table_name or f"uploaded_{sanitize_identifier(name)}"
    columns = [sanitize_identifier(col) for col in reader.fieldnames]
    if len(columns) != len(set(columns)):
        raise ValueError("CSV headers must be unique after normalization.")

    samples_by_col = {col: [] for col in columns}
    original_to_clean = dict(zip(reader.fieldnames, columns, strict=True))
    for row in rows[:200]:
        for original, clean in original_to_clean.items():
            samples_by_col[clean].append(row.get(original, ""))
    column_types = {col: infer_column_type(samples_by_col[col]) for col in columns}

    con = connect_db()
    try:
        selected_table = base_table
        if table_name:
            if replace_existing:
                con.execute(f"DROP TABLE IF EXISTS {quote_sqlite_ident(selected_table)}")
            elif con.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name = ?", (selected_table,)
            ).fetchone():
                return {"table_name": selected_table, "row_count": len(rows), "columns": columns}
        else:
            suffix = 2
            while con.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name = ?", (selected_table,)
            ).fetchone():
                selected_table = f"{base_table}_{suffix}"
                suffix += 1

        column_defs = ", ".join(f"{quote_sqlite_ident(col)} {column_types[col]}" for col in columns)
        con.execute(f"CREATE TABLE {quote_sqlite_ident(selected_table)} ({column_defs})")
        placeholders = ", ".join("?" for _ in columns)
        insert_sql = (
            f"INSERT INTO {quote_sqlite_ident(selected_table)} "
            f"({', '.join(quote_sqlite_ident(col) for col in columns)}) "
            f"VALUES ({placeholders})"
        )

        insert_rows = []
        for row in rows:
            values = []
            for original, clean in original_to_clean.items():
                raw = row.get(original, "")
                col_type = column_types[clean]
                if raw == "":
                    values.append(None)
                elif col_type == "INTEGER":
                    values.append(int(raw))
                elif col_type == "REAL":
                    values.append(float(raw))
                else:
                    values.append(raw)
            insert_rows.append(values)
        con.executemany(insert_sql, insert_rows)
        con.commit()
        return {"table_name": selected_table, "row_count": len(rows), "columns": columns}
    finally:
        con.close()


def upload_csv_to_s3(name: str, csv_text: str) -> dict[str, Any]:
    config = get_service_config()
    if config.csv_storage != "s3":
        return {"s3": {"enabled": False}}
    if not config.s3_bucket:
        return {"s3": {"enabled": True, "uploaded": False, "reason": "S3_UPLOAD_BUCKET is not set"}}
    if boto3 is None:
        return {"s3": {"enabled": True, "uploaded": False, "reason": "boto3 is not installed"}}

    table_name = sanitize_identifier(name)
    object_key = f"{config.s3_prefix}/{table_name}/{uuid.uuid4().hex}.csv"
    try:
        client = boto3.client("s3", region_name=config.aws_region)
        client.put_object(
            Bucket=config.s3_bucket,
            Key=object_key,
            Body=csv_text.encode("utf-8"),
            ContentType="text/csv; charset=utf-8",
        )
        return {
            "s3": {
                "enabled": True,
                "uploaded": True,
                "bucket": config.s3_bucket,
                "key": object_key,
                "uri": f"s3://{config.s3_bucket}/{object_key}",
            }
        }
    except Exception as exc:
        return {"s3": {"enabled": True, "uploaded": False, "reason": str(exc)}}


def sqlite_table_exists(table_name: str) -> bool:
    con = connect_db()
    try:
        return (
            con.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name = ?", (table_name,)).fetchone()
            is not None
        )
    finally:
        con.close()


def cloud_csv_upload_enabled() -> bool:
    return use_s3_analysis_storage()


def materialize_csv_source(source: dict[str, Any]) -> None:
    if source.get("type") != "s3_csv":
        return
    table_name = str(source.get("table_name") or "").strip()
    storage_uri = str(source.get("storage_uri") or "").strip()
    if not table_name or not storage_uri:
        raise ValueError("Uploaded CSV source is missing table metadata.")
    if sqlite_table_exists(table_name):
        return

    bucket, key = parse_s3_uri(storage_uri)
    try:
        response = s3_client().get_object(Bucket=bucket, Key=key)
        csv_text = response["Body"].read().decode("utf-8")
    except Exception as exc:
        if s3_not_found(exc):
            raise ValueError("Uploaded CSV object was not found.") from exc
        raise
    upload_csv_table(source.get("name") or table_name, csv_text, table_name, replace_existing=True)


def upload_csv_dataset(name: str, csv_text: str) -> dict[str, Any]:
    if not csv_text.strip():
        raise ValueError("CSV text is required.")

    if not cloud_csv_upload_enabled():
        result = upload_csv_table(name, csv_text)
        s3_result = upload_csv_to_s3(name, csv_text)
        return {
            "ok": True,
            "data_source_id": "demo_warehouse",
            **result,
            **s3_result,
            "schema": get_schema(),
        }

    bucket = analysis_s3_bucket()
    if not bucket:
        raise RuntimeError("ANALYSIS_STATE_BUCKET is required when ANALYSIS_STORAGE=s3.")

    source_id = f"csv_{uuid.uuid4().hex[:12]}"
    table_name = f"uploaded_{sanitize_identifier(name)}_{source_id[-8:]}"
    result = upload_csv_table(name, csv_text, table_name=table_name, replace_existing=True)
    key = analysis_s3_key(f"uploads/{source_id}/{table_name}.csv")
    s3_client().put_object(
        Bucket=bucket,
        Key=key,
        Body=csv_text.encode("utf-8"),
        ContentType="text/csv; charset=utf-8",
    )
    source = {
        "id": source_id,
        "name": name.strip() or table_name,
        "type": "s3_csv",
        "status": "connected",
        "read_only": True,
        "persisted": True,
        "table_name": result["table_name"],
        "row_count": result["row_count"],
        "columns": result["columns"],
        "storage_uri": f"s3://{bucket}/{key}",
        "created_at": utc_now(),
    }
    with ANALYSIS_LOCK:
        doc = read_analysis_doc()
        doc.setdefault("data_sources", [])
        doc["data_sources"] = [item for item in doc["data_sources"] if item.get("id") != source_id]
        doc["data_sources"].append(source)
        analysis_audit(doc, "csv_data_source_uploaded", {"data_source_id": source_id, "table_name": table_name})
        write_analysis_doc(doc)
    return {
        "ok": True,
        "data_source_id": source_id,
        "source": public_data_source(source),
        "table_name": result["table_name"],
        "row_count": result["row_count"],
        "columns": result["columns"],
        "s3": {
            "enabled": True,
            "uploaded": True,
            "bucket": bucket,
            "key": key,
            "uri": source["storage_uri"],
        },
        "schema": get_schema(source_id),
    }


def normalize_postgres_payload(payload: dict[str, Any]) -> dict[str, Any]:
    name = str(payload.get("name") or "Postgres Source").strip()
    host = str(payload.get("host") or "").strip()
    database = str(payload.get("database") or payload.get("dbname") or "").strip()
    user = str(payload.get("user") or "").strip()
    password = str(payload.get("password") or "")
    sslmode = str(payload.get("sslmode") or "prefer").strip()
    port = int(payload.get("port") or 5432)

    if not host:
        raise ValueError("Postgres host is required.")
    if not database:
        raise ValueError("Postgres database is required.")
    if not user:
        raise ValueError("Postgres user is required.")

    return {
        "name": name,
        "host": host,
        "port": port,
        "dbname": database,
        "user": user,
        "password": password,
        "sslmode": sslmode,
    }


def make_postgres_source(payload: dict[str, Any], source_id: str | None = None) -> dict[str, Any]:
    normalized = normalize_postgres_payload(payload)
    source_name = normalized.pop("name")
    return {
        "id": source_id or f"postgres_{uuid.uuid4().hex[:10]}",
        "name": source_name,
        "type": "postgres",
        "status": "connected",
        "read_only": True,
        "persisted": False,
        "connection": normalized,
    }


def test_postgres_connection(payload: dict[str, Any]) -> dict[str, Any]:
    source = make_postgres_source(payload, "postgres_test")
    schema = get_postgres_schema(source)
    return {
        "ok": True,
        "source": public_data_source(source),
        "table_count": len(schema["tables"]),
        "tables": schema["tables"][:12],
    }


def save_session_postgres_source(payload: dict[str, Any]) -> dict[str, Any]:
    source = make_postgres_source(payload)
    schema = get_postgres_schema(source)
    SESSION_DATA_SOURCES[source["id"]] = source
    return {
        "ok": True,
        "source": public_data_source(source),
        "schema": {
            **schema,
            "data_sources": [public_data_source(item) for item in list_data_sources()],
        },
    }


def default_parameters() -> list[dict[str, Any]]:
    return [
        {
            "name": "start_date",
            "label": "Start Date",
            "type": "date",
            "default": "2025-01-01",
            "value": "2025-01-01",
        },
        {
            "name": "end_date",
            "label": "End Date",
            "type": "date",
            "default": "2026-06-30",
            "value": "2026-06-30",
        },
        {
            "name": "region",
            "label": "Region",
            "type": "select",
            "default": "All",
            "value": "All",
            "options": ["All", "Midwest", "Northeast", "Southeast", "Southwest", "West"],
        },
    ]


def compact_schema_context(schema: dict[str, Any], max_tables: int = 18, max_columns: int = 24) -> str:
    lines = []
    for table in schema.get("tables", [])[:max_tables]:
        columns = table.get("columns", [])[:max_columns]
        column_text = ", ".join(f"{col['name']} {col.get('type', '')}".strip() for col in columns)
        lines.append(f"- {table['name']}: {column_text}")
    return "\n".join(lines)


def extract_json_object(text: str) -> dict[str, Any]:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    first = cleaned.find("{")
    last = cleaned.rfind("}")
    if first == -1 or last == -1 or first >= last:
        raise ValueError("Bedrock response did not contain a JSON object.")
    return json.loads(cleaned[first : last + 1])


def normalize_agent_report(
    raw: dict[str, Any],
    prompt: str,
    data_source_id: str,
    source_name: str,
) -> dict[str, Any]:
    now = utc_now()
    blocks = raw.get("blocks")
    if not isinstance(blocks, list) or not blocks:
        raise ValueError("Agent response did not include report blocks.")

    normalized_blocks = []
    for index, block in enumerate(blocks, start=1):
        if not isinstance(block, dict):
            continue
        sql_template = str(block.get("sql_template") or "").strip()
        if not sql_template:
            continue
        normalized_blocks.append(
            {
                "id": sanitize_identifier(str(block.get("id") or f"block_{index}")),
                "title": str(block.get("title") or f"Report Block {index}"),
                "visual_type": str(block.get("visual_type") or "table").lower(),
                "x": block.get("x"),
                "y": block.get("y"),
                "narrative": str(block.get("narrative") or ""),
                "sql_template": sql_template,
                "data_source_id": data_source_id,
            }
        )

    if not normalized_blocks:
        raise ValueError("Agent response did not include usable SQL blocks.")

    parameters = raw.get("parameters")
    if not isinstance(parameters, list) or not parameters:
        parameters = []
    normalized_parameters = []
    for param in parameters:
        if not isinstance(param, dict) or not param.get("name"):
            continue
        default = param.get("default", param.get("value", ""))
        normalized_parameters.append(
            {
                "name": sanitize_identifier(str(param["name"])),
                "label": str(param.get("label") or human_label(str(param["name"]))),
                "type": str(param.get("type") or "text"),
                "default": default,
                "value": param.get("value", default),
                **({"options": param["options"]} if isinstance(param.get("options"), list) else {}),
            }
        )

    return {
        "id": f"draft_{uuid.uuid4().hex[:10]}",
        "title": str(raw.get("title") or "Generated Data Report"),
        "status": "draft",
        "prompt": prompt,
        "template": str(raw.get("template") or "executive-summary-v1"),
        "data_source_id": data_source_id,
        "data_source_name": source_name,
        "created_at": now,
        "updated_at": now,
        "version": 1,
        "parameters": normalized_parameters,
        "blocks": normalized_blocks,
    }


def human_label(name: str) -> str:
    return re.sub(r"\s+", " ", name.replace("_", " ")).strip().title()


def bedrock_agent_report(prompt: str, data_source_id: str) -> dict[str, Any]:
    config = get_service_config()
    if boto3 is None:
        raise ValueError("Bedrock support requires installing boto3 from requirements.txt.")
    if not config.bedrock_model_id:
        raise ValueError("BEDROCK_MODEL_ID is required for Bedrock agent generation.")

    source = get_data_source(data_source_id)
    schema = get_schema(data_source_id)
    schema_context = compact_schema_context(schema)
    system_prompt = """
You generate report artifacts for an AI-native BI platform.
Return strict JSON only, no markdown.
The JSON shape must be:
{
  "title": "string",
  "template": "executive-summary-v1",
  "parameters": [
    {"name": "param_name", "label": "Label", "type": "text|date|select|number", "default": "value", "value": "value"}
  ],
  "blocks": [
    {
      "id": "snake_case_id",
      "title": "string",
      "visual_type": "kpi|line|bar|table",
      "x": "column_for_charts_or_null",
      "y": "numeric_column_for_charts_or_null",
      "narrative": "brief explanation",
      "sql_template": "SELECT-only SQL using {{ parameter }} placeholders when needed"
    }
  ]
}
Use only tables and columns from the schema. Create one SQL block per visual.
Do not include INSERT, UPDATE, DELETE, CREATE, DROP, ALTER, or multiple statements.
Prefer portable SQL. Keep each query independently runnable.
""".strip()
    user_prompt = f"""
Data source: {source['name']} ({source['type']})

Schema:
{schema_context}

User request:
{prompt}
""".strip()

    client = boto3.client("bedrock-runtime", region_name=config.aws_region)
    try:
        response = client.converse(
            modelId=config.bedrock_model_id,
            system=[{"text": system_prompt}],
            messages=[{"role": "user", "content": [{"text": user_prompt}]}],
            inferenceConfig={"temperature": 0.2, "maxTokens": 5000},
        )
        parts = response["output"]["message"]["content"]
        text = "\n".join(part.get("text", "") for part in parts if "text" in part)
        raw = extract_json_object(text)
        return normalize_agent_report(raw, prompt, data_source_id, source["name"])
    except Exception as exc:
        raise ValueError(f"Bedrock report generation failed: {exc}") from exc


def generate_agent_report(prompt: str, data_source_id: str | None) -> dict[str, Any]:
    source = get_data_source(data_source_id)
    config = get_service_config()
    if config.agent_mode == "mock":
        if source["id"] != "demo_warehouse":
            raise ValueError("Mock agent only supports the demo warehouse. Configure Bedrock for real sources.")
        return mock_agent_report(prompt, source["id"])

    if config.agent_mode in {"bedrock", "auto"} and boto3 is not None and config.bedrock_model_id:
        return bedrock_agent_report(prompt, source["id"])

    if source["id"] != "demo_warehouse":
        raise ValueError("Real data sources require Bedrock. Set BEDROCK_MODEL_ID and install boto3.")
    return mock_agent_report(prompt, source["id"])


def mock_agent_report(prompt: str, data_source_id: str = "demo_warehouse") -> dict[str, Any]:
    title = "Executive Sales Performance Brief"
    if "inventory" in prompt.lower():
        title = "Sales And Inventory Risk Brief"
    elif "region" in prompt.lower():
        title = "Regional Sales Performance Brief"

    report_id = f"draft_{uuid.uuid4().hex[:10]}"
    blocks = [
        {
            "id": "summary_kpis",
            "title": "Executive KPI Snapshot",
            "visual_type": "kpi",
            "data_source_id": data_source_id,
            "narrative": "Revenue, margin, order volume, and return exposure for the selected period.",
            "sql_template": """
SELECT
  ROUND(SUM(oi.quantity * oi.unit_price), 2) AS revenue,
  ROUND(SUM(oi.quantity * (oi.unit_price - p.unit_cost)), 2) AS gross_margin,
  ROUND(100.0 * SUM(oi.quantity * (oi.unit_price - p.unit_cost)) / NULLIF(SUM(oi.quantity * oi.unit_price), 0), 1) AS margin_pct,
  COUNT(DISTINCT o.id) AS orders,
  ROUND(100.0 * COALESCE(SUM(ret.quantity_returned), 0) / NULLIF(SUM(oi.quantity), 0), 1) AS return_rate_pct
FROM orders o
JOIN customers c ON c.id = o.customer_id
JOIN regions r ON r.id = c.region_id
JOIN order_items oi ON oi.order_id = o.id
JOIN products p ON p.id = oi.product_id
LEFT JOIN returns ret ON ret.order_item_id = oi.id
WHERE o.status = 'Complete'
  AND o.order_date BETWEEN {{ start_date }} AND {{ end_date }}
  AND ({{ region }} = 'All' OR r.region_name = {{ region }})
            """.strip(),
        },
        {
            "id": "revenue_trend",
            "title": "Revenue Trend",
            "visual_type": "line",
            "data_source_id": data_source_id,
            "x": "month",
            "y": "revenue",
            "narrative": "Monthly revenue trend generated from order-level transaction data.",
            "sql_template": """
SELECT
  substr(o.order_date, 1, 7) AS month,
  ROUND(SUM(oi.quantity * oi.unit_price), 2) AS revenue,
  COUNT(DISTINCT o.id) AS orders
FROM orders o
JOIN customers c ON c.id = o.customer_id
JOIN regions r ON r.id = c.region_id
JOIN order_items oi ON oi.order_id = o.id
WHERE o.status = 'Complete'
  AND o.order_date BETWEEN {{ start_date }} AND {{ end_date }}
  AND ({{ region }} = 'All' OR r.region_name = {{ region }})
GROUP BY 1
ORDER BY 1
            """.strip(),
        },
        {
            "id": "region_performance",
            "title": "Region Performance Against Target",
            "visual_type": "bar",
            "data_source_id": data_source_id,
            "x": "region_name",
            "y": "attainment_pct",
            "narrative": "Regional attainment compares booked revenue against monthly targets.",
            "sql_template": """
WITH revenue AS (
  SELECT
    r.region_name,
    substr(o.order_date, 1, 7) AS month,
    SUM(oi.quantity * oi.unit_price) AS revenue
  FROM orders o
  JOIN customers c ON c.id = o.customer_id
  JOIN regions r ON r.id = c.region_id
  JOIN order_items oi ON oi.order_id = o.id
  WHERE o.status = 'Complete'
    AND o.order_date BETWEEN {{ start_date }} AND {{ end_date }}
    AND ({{ region }} = 'All' OR r.region_name = {{ region }})
  GROUP BY 1, 2
)
SELECT
  revenue.region_name,
  ROUND(SUM(revenue.revenue), 2) AS revenue,
  ROUND(SUM(st.revenue_target), 2) AS target,
  ROUND(100.0 * SUM(revenue.revenue) / NULLIF(SUM(st.revenue_target), 0), 1) AS attainment_pct
FROM revenue
JOIN regions r ON r.region_name = revenue.region_name
JOIN sales_targets st ON st.region_id = r.id AND st.target_month = revenue.month
GROUP BY 1
ORDER BY attainment_pct DESC
            """.strip(),
        },
        {
            "id": "product_mix",
            "title": "Product Mix",
            "visual_type": "bar",
            "data_source_id": data_source_id,
            "x": "category",
            "y": "revenue",
            "narrative": "Category revenue mix shows which offerings are driving the period.",
            "sql_template": """
SELECT
  p.category,
  ROUND(SUM(oi.quantity * oi.unit_price), 2) AS revenue,
  ROUND(SUM(oi.quantity * (oi.unit_price - p.unit_cost)), 2) AS gross_margin,
  ROUND(100.0 * SUM(oi.quantity * (oi.unit_price - p.unit_cost)) / NULLIF(SUM(oi.quantity * oi.unit_price), 0), 1) AS margin_pct
FROM orders o
JOIN customers c ON c.id = o.customer_id
JOIN regions r ON r.id = c.region_id
JOIN order_items oi ON oi.order_id = o.id
JOIN products p ON p.id = oi.product_id
WHERE o.status = 'Complete'
  AND o.order_date BETWEEN {{ start_date }} AND {{ end_date }}
  AND ({{ region }} = 'All' OR r.region_name = {{ region }})
GROUP BY 1
ORDER BY revenue DESC
            """.strip(),
        },
        {
            "id": "margin_risk",
            "title": "Margin And Return Risk",
            "visual_type": "table",
            "data_source_id": data_source_id,
            "narrative": "Products with lower margin or elevated return rates deserve closer review.",
            "sql_template": """
SELECT
  p.product_name,
  p.category,
  ROUND(SUM(oi.quantity * oi.unit_price), 2) AS revenue,
  ROUND(100.0 * SUM(oi.quantity * (oi.unit_price - p.unit_cost)) / NULLIF(SUM(oi.quantity * oi.unit_price), 0), 1) AS margin_pct,
  ROUND(100.0 * COALESCE(SUM(ret.quantity_returned), 0) / NULLIF(SUM(oi.quantity), 0), 1) AS return_rate_pct,
  SUM(oi.quantity) AS units_sold
FROM orders o
JOIN customers c ON c.id = o.customer_id
JOIN regions r ON r.id = c.region_id
JOIN order_items oi ON oi.order_id = o.id
JOIN products p ON p.id = oi.product_id
LEFT JOIN returns ret ON ret.order_item_id = oi.id
WHERE o.status = 'Complete'
  AND o.order_date BETWEEN {{ start_date }} AND {{ end_date }}
  AND ({{ region }} = 'All' OR r.region_name = {{ region }})
GROUP BY 1, 2
ORDER BY return_rate_pct DESC, margin_pct ASC
LIMIT 8
            """.strip(),
        },
    ]

    return {
        "id": report_id,
        "title": title,
        "status": "draft",
        "prompt": prompt,
        "template": "executive-summary-v1",
        "data_source_id": data_source_id,
        "data_source_name": "Demo Sales Warehouse",
        "created_at": utc_now(),
        "updated_at": utc_now(),
        "version": 1,
        "parameters": default_parameters(),
        "blocks": blocks,
    }


def publish_report(report: dict[str, Any]) -> dict[str, Any]:
    reports_doc = read_reports()
    now = utc_now()
    existing_reports = reports_doc["reports"]
    report_id = report.get("id")
    if not report_id or str(report_id).startswith("draft_"):
        report_id = f"report_{uuid.uuid4().hex[:10]}"

    published = dict(report)
    published["id"] = report_id
    published["status"] = "published"
    published["published_at"] = now
    published["updated_at"] = now
    published["published_path"] = f"/published/{report_id}"

    existing_reports = [item for item in existing_reports if item.get("id") != report_id]
    existing_reports.append(published)
    reports_doc["reports"] = existing_reports
    write_reports(reports_doc)
    return published


def json_error(message: str, status: int = 400) -> tuple[int, dict[str, Any]]:
    return status, {"ok": False, "error": message}


def parse_query(query: str) -> dict[str, str]:
    pairs: dict[str, str] = {}
    for part in query.split("&"):
        if not part:
            continue
        key, _, value = part.partition("=")
        pairs[unquote(key)] = unquote(value)
    return pairs


class POCHandler(BaseHTTPRequestHandler):
    server_version = "AgenticBIReportPOC/0.1"

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        path = unquote(parsed.path)

        if path.startswith("/api/v2/"):
            from analysis_engine.workspace_http import handle
            handle(self, "GET", DATA_DIR)
            return

        if path == "/api/health":
            return self.send_json({"ok": True, "time": utc_now()})
        if path == "/api/config/status":
            return self.send_json(service_status())
        if path == "/api/data-sources":
            return self.send_json({"data_sources": [public_data_source(source) for source in list_data_sources()]})
        if path == "/api/schema":
            query = parse_query(parsed.query)
            return self.send_json(get_schema(query.get("data_source_id")))
        if path == "/api/analysis/sessions":
            return self.send_json(list_analysis_sessions())
        if path.startswith("/api/analysis/sessions/"):
            session_id = unquote(path.rsplit("/", 1)[-1])
            return self.send_json(get_analysis_session_detail(session_id))
        if path.startswith("/api/analysis/runs/"):
            run_id = path.rsplit("/", 1)[-1]
            return self.send_json(get_analysis_status(run_id))
        if path.startswith("/api/analysis/artifacts/"):
            artifact_id = path.rsplit("/", 1)[-1]
            with ANALYSIS_LOCK:
                doc = read_analysis_doc()
                artifact = find_record(doc, "artifacts", artifact_id)
                return self.send_json({"ok": True, "artifact": public_artifact(artifact, include_content=True)})
        if path == "/api/reports":
            return self.send_json(read_reports())
        if path.startswith("/api/reports/"):
            report_id = path.rsplit("/", 1)[-1]
            for report in read_reports()["reports"]:
                if report.get("id") == report_id:
                    return self.send_json(report)
            return self.send_json({"ok": False, "error": "Report not found."}, 404)
        if path.startswith("/published/"):
            return self.serve_static("published.html")
        if path == "/studio":
            return self.serve_static("studio.html")
        if path == "/":
            return self.serve_static("index.html")
        if path.startswith("/static/"):
            return self.serve_static(path.replace("/static/", "", 1))

        self.send_json({"ok": False, "error": "Not found."}, 404)

    def do_POST(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        path = parsed.path

        if path.startswith("/api/v2/"):
            from analysis_engine.workspace_http import handle
            handle(self, "POST", DATA_DIR)
            return

        try:
            payload = self.read_json()

            if path == "/api/agent/draft":
                prompt = str(payload.get("prompt", "")).strip()
                if not prompt:
                    raise ValueError("Prompt is required.")
                data_source_id = str(payload.get("data_source_id") or "demo_warehouse")
                return self.send_json(generate_agent_report(prompt, data_source_id))

            if path == "/api/analysis/sessions":
                return self.send_json(create_analysis_session(payload))

            if path == "/api/analysis/light":
                return self.send_json(run_light_analysis(payload))

            if path == "/api/analysis/deep":
                return self.send_json(request_deep_analysis(payload))

            if path == "/api/analysis/continue":
                return self.send_json(continue_analysis(payload))

            if path == "/api/query/preview":
                result = execute_preview_query(
                    str(payload.get("sql_template", "")),
                    payload.get("parameters") or {},
                    int(payload.get("limit") or 100),
                    str(payload.get("data_source_id") or "demo_warehouse"),
                )
                return self.send_json(result)

            if path == "/api/reports/publish":
                report = payload.get("report")
                if not isinstance(report, dict):
                    raise ValueError("Report payload is required.")
                for block in report.get("blocks", []):
                    execute_preview_query(
                        block.get("sql_template", ""),
                        {
                            param["name"]: param.get("value", param.get("default"))
                            for param in report.get("parameters", [])
                        },
                        25,
                        block.get("data_source_id") or report.get("data_source_id") or "demo_warehouse",
                    )
                return self.send_json(publish_report(report))

            if path == "/api/data-sources/postgres/test":
                return self.send_json(test_postgres_connection(payload))

            if path == "/api/data-sources/postgres/save":
                return self.send_json(save_session_postgres_source(payload))

            if path == "/api/csv/upload":
                name = str(payload.get("name", "uploaded_data"))
                csv_text = str(payload.get("csv_text", ""))
                return self.send_json(upload_csv_dataset(name, csv_text))

            status, body = json_error("Unknown endpoint.", 404)
            return self.send_json(body, status)
        except ValueError as exc:
            status, body = json_error(str(exc), 400)
            return self.send_json(body, status)
        except Exception as exc:  # pragma: no cover - local POC guardrail
            status, body = json_error(f"Unexpected server error: {exc}", 500)
            return self.send_json(body, status)

    def read_json(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0:
            return {}
        raw = self.rfile.read(length).decode("utf-8")
        return json.loads(raw)

    def send_json(self, payload: dict[str, Any], status: int = 200) -> None:
        encoded = json.dumps(payload, indent=2, default=str).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(encoded)

    def serve_static(self, name: str) -> None:
        safe_name = Path(name).name
        file_path = STATIC_DIR / safe_name
        if not file_path.exists():
            return self.send_json({"ok": False, "error": "Static file not found."}, 404)

        content_types = {
            ".html": "text/html; charset=utf-8",
            ".css": "text/css; charset=utf-8",
            ".js": "text/javascript; charset=utf-8",
            ".svg": "image/svg+xml",
        }
        encoded = file_path.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_types.get(file_path.suffix, "application/octet-stream"))
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def log_message(self, fmt: str, *args: Any) -> None:
        sys.stderr.write("[%s] %s\n" % (self.log_date_time_string(), fmt % args))


def main() -> None:
    initialize_demo_database()
    host = os.environ.get("HOST", "127.0.0.1")
    port = int(os.environ.get("PORT", "8765"))
    server = ThreadingHTTPServer((host, port), POCHandler)
    print(f"Virtual Data Scientist POC running at http://{host}:{port}")
    print("Press Ctrl+C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
