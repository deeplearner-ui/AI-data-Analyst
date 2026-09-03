from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path
from typing import Any

from . import SCHEMA_VERSION
from .models import new_id, now_iso


class ProjectStore:
    def __init__(self, directory: str):
        self.root = Path(directory).expanduser().resolve()
        self.meta = self.root / ".aida"
        self.data = self.meta / "data"
        self.db_path = self.meta / "project.sqlite3"

    def create(self, name: str, language: str) -> dict[str, Any]:
        if (self.meta / "manifest.json").exists():
            raise FileExistsError("An AI Data Analyst project already exists in this directory")
        self.data.mkdir(parents=True, exist_ok=True)
        project_id = new_id("project")
        manifest = {
            "schemaVersion": SCHEMA_VERSION,
            "id": project_id,
            "name": name,
            "language": language,
            "datasets": [],
            "createdAt": now_iso(),
            "updatedAt": now_iso(),
        }
        (self.meta / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        self._initialize()
        self.audit("project.created", {"projectId": project_id, "name": name})
        return manifest

    def open(self) -> dict[str, Any]:
        manifest_path = self.meta / "manifest.json"
        if not manifest_path.exists():
            raise FileNotFoundError("This directory is not an AI Data Analyst project")
        self._initialize()
        return json.loads(manifest_path.read_text(encoding="utf-8"))

    def save_manifest(self, manifest: dict[str, Any]) -> None:
        manifest["updatedAt"] = now_iso()
        (self.meta / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    def semantic_profile(self, version_id: str) -> dict[str, Any] | None:
        version = self.get_version(version_id)
        manifest = self.open()
        dataset = next((item for item in manifest["datasets"] if item["id"] == version["datasetId"]), None)
        return dataset.get("semanticProfile") if dataset else None

    def save_semantic_profile(self, version_id: str, profile: dict[str, Any]) -> dict[str, Any]:
        version = self.get_version(version_id)
        manifest = self.open()
        dataset = next((item for item in manifest["datasets"] if item["id"] == version["datasetId"]), None)
        if dataset is None: raise KeyError(f"Dataset not found for version: {version_id}")
        stored = {**profile, "confirmed": True, "updatedAt": now_iso()}
        dataset["semanticProfile"] = stored
        self.save_manifest(manifest)
        self.audit("dataset.semantic-profile.saved", {"datasetId": version["datasetId"], "versionId": version_id, "profile": stored})
        return stored

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        return connection

    def _initialize(self) -> None:
        self.meta.mkdir(parents=True, exist_ok=True)
        with self._connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS dataset_versions (
                    id TEXT PRIMARY KEY, dataset_id TEXT NOT NULL, parent_version_id TEXT,
                    fingerprint TEXT NOT NULL, row_count INTEGER NOT NULL, columns_json TEXT NOT NULL,
                    storage_path TEXT NOT NULL, operation TEXT NOT NULL, created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS analysis_steps (
                    id TEXT PRIMARY KEY, plan_id TEXT NOT NULL, payload_json TEXT NOT NULL,
                    status TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS analysis_plans (
                    id TEXT PRIMARY KEY, payload_json TEXT NOT NULL, status TEXT NOT NULL,
                    created_at TEXT NOT NULL, updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS artifacts (
                    id TEXT PRIMARY KEY, plan_id TEXT, step_id TEXT, kind TEXT NOT NULL,
                    dataset_version_id TEXT, payload_json TEXT NOT NULL, created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS audit_log (
                    sequence INTEGER PRIMARY KEY AUTOINCREMENT, occurred_at TEXT NOT NULL,
                    action TEXT NOT NULL, payload_json TEXT NOT NULL, previous_hash TEXT NOT NULL,
                    entry_hash TEXT NOT NULL
                );
            """)

    def add_version(self, version: dict[str, Any]) -> None:
        with self._connect() as db:
            db.execute(
                "INSERT INTO dataset_versions VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (version["id"], version["datasetId"], version.get("parentVersionId"), version["fingerprint"],
                 version["rowCount"], json.dumps(version["columns"]), version["storagePath"],
                 version["operation"], version["createdAt"]),
            )

    def get_version(self, version_id: str) -> dict[str, Any]:
        with self._connect() as db:
            row = db.execute("SELECT * FROM dataset_versions WHERE id = ?", (version_id,)).fetchone()
        if row is None:
            raise KeyError(f"Unknown dataset version: {version_id}")
        return {
            "id": row["id"], "datasetId": row["dataset_id"], "parentVersionId": row["parent_version_id"],
            "fingerprint": row["fingerprint"], "rowCount": row["row_count"],
            "columns": json.loads(row["columns_json"]), "storagePath": row["storage_path"],
            "operation": row["operation"], "createdAt": row["created_at"],
        }

    def all_versions(self) -> list[dict[str, Any]]:
        with self._connect() as db:
            rows = db.execute("SELECT * FROM dataset_versions ORDER BY created_at").fetchall()
        return [{
            "id": row["id"], "datasetId": row["dataset_id"], "parentVersionId": row["parent_version_id"],
            "fingerprint": row["fingerprint"], "rowCount": row["row_count"],
            "columns": json.loads(row["columns_json"]), "operation": row["operation"], "createdAt": row["created_at"],
        } for row in rows]

    def save_plan(self, plan: dict[str, Any]) -> None:
        updated = now_iso()
        plan["updatedAt"] = updated
        payload = json.dumps(plan, ensure_ascii=False, default=str)
        with self._connect() as db:
            db.execute(
                """INSERT INTO analysis_plans (id, payload_json, status, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?)
                   ON CONFLICT(id) DO UPDATE SET payload_json=excluded.payload_json,
                   status=excluded.status, updated_at=excluded.updated_at""",
                (plan["id"], payload, plan["status"], plan.get("createdAt", updated), updated),
            )
            for step in plan.get("steps", []):
                db.execute(
                    """INSERT INTO analysis_steps (id, plan_id, payload_json, status, created_at, updated_at)
                       VALUES (?, ?, ?, ?, ?, ?)
                       ON CONFLICT(id) DO UPDATE SET payload_json=excluded.payload_json,
                       status=excluded.status, updated_at=excluded.updated_at""",
                    (step["id"], plan["id"], json.dumps(step, ensure_ascii=False, default=str),
                     step["status"], plan.get("createdAt", updated), updated),
                )

    def get_plan(self, plan_id: str) -> dict[str, Any]:
        with self._connect() as db:
            row = db.execute("SELECT payload_json FROM analysis_plans WHERE id = ?", (plan_id,)).fetchone()
        if row is None: raise KeyError(f"Unknown analysis plan: {plan_id}")
        return json.loads(row["payload_json"])

    def latest_plan(self) -> dict[str, Any] | None:
        with self._connect() as db:
            row = db.execute("SELECT payload_json FROM analysis_plans ORDER BY updated_at DESC LIMIT 1").fetchone()
        return json.loads(row["payload_json"]) if row else None

    def add_artifact(self, artifact: dict[str, Any]) -> None:
        with self._connect() as db:
            db.execute(
                "INSERT INTO artifacts (id, plan_id, step_id, kind, dataset_version_id, payload_json, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (artifact["id"], artifact.get("planId"), artifact.get("stepId"), artifact["kind"],
                 artifact.get("datasetVersionId"), json.dumps(artifact["payload"], ensure_ascii=False, default=str), artifact["createdAt"]),
            )

    def artifacts_for_plan(self, plan_id: str) -> list[dict[str, Any]]:
        with self._connect() as db:
            rows = db.execute("SELECT * FROM artifacts WHERE plan_id = ? ORDER BY created_at", (plan_id,)).fetchall()
        return [{
            "id": row["id"], "planId": row["plan_id"], "stepId": row["step_id"],
            "kind": row["kind"], "datasetVersionId": row["dataset_version_id"],
            "payload": json.loads(row["payload_json"]), "createdAt": row["created_at"],
        } for row in rows]

    def audit(self, action: str, payload: dict[str, Any]) -> None:
        serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
        with self._connect() as db:
            row = db.execute("SELECT entry_hash FROM audit_log ORDER BY sequence DESC LIMIT 1").fetchone()
            previous = row[0] if row else "0" * 64
            occurred = now_iso()
            digest = hashlib.sha256(f"{previous}|{occurred}|{action}|{serialized}".encode()).hexdigest()
            db.execute(
                "INSERT INTO audit_log (occurred_at, action, payload_json, previous_hash, entry_hash) VALUES (?, ?, ?, ?, ?)",
                (occurred, action, serialized, previous, digest),
            )

    def audit_entries(self, limit: int = 200) -> list[dict[str, Any]]:
        with self._connect() as db:
            rows = db.execute("SELECT * FROM audit_log ORDER BY sequence DESC LIMIT ?", (limit,)).fetchall()
        return [dict(row) for row in rows]
