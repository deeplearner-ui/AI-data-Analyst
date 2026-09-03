from pathlib import Path
from time import sleep

import pandas as pd
from fastapi.testclient import TestClient

from aida_sidecar.api import app


client = TestClient(app)
HEADERS = {"Authorization": "Bearer development-token"}


def test_sidecar_requires_session_token() -> None:
    assert client.get("/api/health").status_code == 401
    response = client.get("/api/health", headers=HEADERS)
    assert response.status_code == 200
    assert response.json()["schemaVersion"] == "1.0"


def test_vertical_project_flow(tmp_path: Path) -> None:
    project = tmp_path / "project"
    source = tmp_path / "data.csv"
    pd.DataFrame({"a": [1, 2, 3], "b": [2, 3, 5]}).to_csv(source, index=False)
    assert client.post("/api/projects", headers=HEADERS, json={"directory": str(project), "name": "flow"}).status_code == 200
    imported = client.post("/api/datasets/import", headers=HEADERS, json={"projectDirectory": str(project), "path": str(source)})
    assert imported.status_code == 200
    version_id = imported.json()["version"]["id"]
    audited = client.post("/api/analysis/audit", headers=HEADERS, json={"projectDirectory": str(project), "versionId": version_id})
    assert audited.json()["audit"]["rowCount"] == 3
    clean_payload = {"projectDirectory": str(project), "versionId": version_id, "operations": [{"kind": "filter", "expression": "a >= 2"}]}
    clean_preview = client.post("/api/analysis/clean/preview", headers=HEADERS, json=clean_payload)
    assert clean_preview.json()["before"]["rowCount"] == 3
    assert clean_preview.json()["after"]["rowCount"] == 2
    assert client.post("/api/projects/open", headers=HEADERS, json={"directory": str(project)}).json()["datasets"][0]["currentVersionId"] == version_id
    cleaned = client.post("/api/analysis/clean", headers=HEADERS, json=clean_payload)
    assert cleaned.json()["unchanged"] is False
    assert cleaned.json()["version"]["parentVersionId"] == version_id
    planned = client.post("/api/ai/plan", headers=HEADERS, json={"projectDirectory": str(project), "versionId": version_id, "goal": "分析关系", "includeSamples": False})
    assert len(planned.json()["plan"]["steps"]) >= 4

    english_plan = client.post("/api/ai/plan", headers=HEADERS, json={"projectDirectory": str(project), "versionId": version_id, "goal": "Analyze relationships", "includeSamples": False, "language": "en"})
    assert english_plan.status_code == 200
    assert english_plan.json()["plan"]["steps"][0]["title"] == "Data quality audit"
    plan_id = english_plan.json()["plan"]["id"]
    executed = client.post("/api/analysis/plans/execute", headers=HEADERS, json={"projectDirectory": str(project), "planId": plan_id, "language": "en"})
    assert executed.status_code == 200
    assert executed.json()["plan"]["status"] == "completed"
    assert {artifact["kind"] for artifact in executed.json()["artifacts"]} == {"audit", "eda", "statistics", "chart", "report"}
    persisted = client.post("/api/analysis/plans/get", headers=HEADERS, json={"projectDirectory": str(project), "planId": plan_id, "language": "en"})
    assert persisted.json()["plan"]["status"] == "completed"
    assert len(persisted.json()["artifacts"]) == 5
    latest = client.post("/api/analysis/plans/latest", headers=HEADERS, json={"projectDirectory": str(project)})
    assert latest.json()["plan"]["id"] == plan_id

    background_plan = client.post("/api/ai/plan", headers=HEADERS, json={"projectDirectory": str(project), "versionId": version_id, "goal": "Background analysis", "includeSamples": False, "language": "en"}).json()["plan"]
    started = client.post("/api/analysis/plans/tasks/start", headers=HEADERS, json={"projectDirectory": str(project), "planId": background_plan["id"], "language": "en"})
    assert started.status_code == 200
    task_id = started.json()["task"]["id"]
    task = started.json()["task"]
    for _ in range(100):
        status = client.post("/api/analysis/plans/tasks/status", headers=HEADERS, json={"projectDirectory": str(project), "taskId": task_id})
        assert status.status_code == 200
        task = status.json()["task"]
        if task["status"] in {"completed", "failed", "cancelled"}:
            break
        sleep(0.02)
    assert task["status"] == "completed"
    assert task["progress"] == 1
    assert task["plan"]["status"] == "completed"
    assert {artifact["kind"] for artifact in task["result"]["artifacts"]} == {"audit", "eda", "statistics", "chart", "report"}


def test_plan_context_serializes_missing_masked_samples(tmp_path: Path) -> None:
    project = tmp_path / "missing-context-project"
    source = tmp_path / "missing-context.csv"
    pd.DataFrame({"Age": [22.0, None], "Name": ["Alice", None]}).to_csv(source, index=False)
    assert client.post("/api/projects", headers=HEADERS, json={"directory": str(project), "name": "missing"}).status_code == 200
    imported = client.post("/api/datasets/import", headers=HEADERS, json={"projectDirectory": str(project), "path": str(source)}).json()

    planned = client.post("/api/ai/plan", headers=HEADERS, json={"projectDirectory": str(project), "versionId": imported["version"]["id"], "goal": "检查缺失值", "includeSamples": True, "language": "zh-CN"})

    assert planned.status_code == 200
    samples = planned.json()["contextPreview"]["maskedSamples"]
    assert samples[1]["Age"] is None
    assert samples[1]["Name"] is None


def test_confirmed_semantic_profile_drives_plan_and_report(tmp_path: Path) -> None:
    project = tmp_path / "semantic-project"
    source = tmp_path / "semantic.csv"
    pd.DataFrame({
        "RecordNo": range(1, 9),
        "Outcome": ["yes", "yes", "no", "no", "yes", "no", "yes", "no"],
        "Region": ["north", "north", "north", "south", "south", "south", "north", "south"],
        "Spend": [120, 110, 30, 45, 90, 35, 130, 40],
        "Score": [9, 8, 2, 3, 7, 2, 10, 3],
    }).to_csv(source, index=False)
    assert client.post("/api/projects", headers=HEADERS, json={"directory": str(project), "name": "semantics"}).status_code == 200
    imported = client.post("/api/datasets/import", headers=HEADERS, json={"projectDirectory": str(project), "path": str(source)}).json()
    version_id = imported["version"]["id"]

    suggested = client.post("/api/analysis/semantics/get", headers=HEADERS, json={"projectDirectory": str(project), "versionId": version_id})
    assert suggested.status_code == 200
    assert suggested.json()["suggested"] is True
    assert suggested.json()["profile"]["confirmed"] is False

    payload = {
        "projectDirectory": str(project), "versionId": version_id,
        "targetColumn": "Outcome", "positiveValue": "yes",
        "identifierColumns": ["RecordNo"], "categoricalColumns": ["Region"],
        "numericColumns": ["Spend", "Score"], "dateColumn": None,
        "businessContext": "Evaluate conversion performance by sales region.",
        "materialGapPoints": 15, "missingWarningPercent": 3, "strongCorrelation": .8,
    }
    saved = client.post("/api/analysis/semantics/save", headers=HEADERS, json=payload)
    assert saved.status_code == 200
    assert saved.json()["profile"]["confirmed"] is True

    reopened = client.post("/api/projects/open", headers=HEADERS, json={"directory": str(project)}).json()
    assert reopened["datasets"][0]["semanticProfile"]["targetColumn"] == "Outcome"
    loaded = client.post("/api/analysis/semantics/get", headers=HEADERS, json={"projectDirectory": str(project), "versionId": version_id}).json()
    assert loaded["suggested"] is False

    planned = client.post("/api/ai/plan", headers=HEADERS, json={"projectDirectory": str(project), "versionId": version_id, "goal": "Explain conversion", "includeSamples": False, "language": "en"})
    assert planned.status_code == 200
    assert planned.json()["contextPreview"]["semanticProfile"]["targetColumn"] == "Outcome"
    executed = client.post("/api/analysis/plans/execute", headers=HEADERS, json={"projectDirectory": str(project), "planId": planned.json()["plan"]["id"], "language": "en"})
    assert executed.status_code == 200
    latest = executed.json()["latest"]
    assert latest["statistics"]["columns"] == ["Outcome", "Region"]
    assert latest["report"]["semanticProfile"]["confirmed"] is True
    report_text = "\n".join(section["markdown"] for section in latest["report"]["sections"])
    assert "Evaluate conversion performance by sales region." in report_text
    assert "materiality threshold 15.0 pp" in report_text
    exported = client.post("/api/reports/export", headers=HEADERS, json={
        "projectDirectory": str(project), "title": "Semantic report", "sections": latest["report"]["sections"],
        "language": "en", "format": "pdf", "versionId": version_id, "planId": planned.json()["plan"]["id"],
    })
    assert exported.status_code == 200
    assert exported.json()["bytes"] > 1000

    invalid = {**payload, "identifierColumns": ["Region"]}
    rejected = client.post("/api/analysis/semantics/save", headers=HEADERS, json=invalid)
    assert rejected.status_code == 400
