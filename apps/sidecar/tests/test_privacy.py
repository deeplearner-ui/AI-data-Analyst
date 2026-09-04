import json
from pathlib import Path

import pandas as pd
from fastapi.testclient import TestClient

from aida_sidecar.api import app
from aida_sidecar.privacy import privacy_scan, sanitize_diagnostic


client = TestClient(app)
HEADERS = {"Authorization": "Bearer development-token"}


def test_privacy_scan_detects_risks_without_returning_raw_values() -> None:
    frame = pd.DataFrame({
        "email": ["alice@example.com"],
        "手机号": ["13800138000"],
        "身份证号": ["11010519491231002X"],
        "bank_card": ["4111111111111111"],
        "姓名": ["Alice"],
    })

    result = privacy_scan(frame)
    serialized = json.dumps(result, ensure_ascii=False)

    assert result["status"] == "sensitive"
    assert result["hasPersonalData"] is True
    assert {"email", "phone", "cn-id", "bank-card", "name"} <= {item["category"] for item in result["findings"]}
    for raw_value in frame.iloc[0].astype(str):
        assert raw_value not in serialized


def test_privacy_scan_clear_and_diagnostic_redaction() -> None:
    result = privacy_scan(pd.DataFrame({"metric": [1, 2], "group": ["A", "B"]}))
    assert result["status"] == "clear"
    assert result["findings"] == []

    diagnostic = sanitize_diagnostic(
        r"C:\Users\ExampleUser\project\data.csv password=hunter2 "
        "alice@example.com 13800138000 11010519491231002X"
    )
    for secret in ("ExampleUser", "hunter2", "alice@example.com", "13800138000", "11010519491231002X"):
        assert secret not in diagnostic
    assert "<local-path>" in diagnostic
    assert "<redacted>" in diagnostic


def test_sensitive_export_requires_explicit_acknowledgement(tmp_path: Path) -> None:
    project = tmp_path / "privacy-project"
    source = tmp_path / "privacy.csv"
    pd.DataFrame({"email": ["alice@example.com"], "score": [10]}).to_csv(source, index=False)

    assert client.post("/api/projects", headers=HEADERS, json={"directory": str(project), "name": "privacy"}).status_code == 200
    imported = client.post(
        "/api/datasets/import",
        headers=HEADERS,
        json={"projectDirectory": str(project), "path": str(source)},
    )
    assert imported.status_code == 200
    payload = imported.json()
    version_id = payload["version"]["id"]
    assert payload["preview"]["privacy"]["status"] == "sensitive"

    scanned = client.post(
        "/api/analysis/privacy/scan",
        headers=HEADERS,
        json={"projectDirectory": str(project), "versionId": version_id},
    )
    assert scanned.status_code == 200
    assert scanned.json()["privacy"]["findings"][0]["column"] == "email"

    blocked = client.post(
        "/api/datasets/export",
        headers=HEADERS,
        json={"projectDirectory": str(project), "versionId": version_id, "format": "csv"},
    )
    assert blocked.status_code == 400
    assert "Personal data risk detected" in blocked.json()["detail"]

    allowed = client.post(
        "/api/datasets/export",
        headers=HEADERS,
        json={
            "projectDirectory": str(project),
            "versionId": version_id,
            "format": "csv",
            "acknowledgePersonalData": True,
        },
    )
    assert allowed.status_code == 200
    assert allowed.json()["privacy"]["status"] == "sensitive"

    external_model = client.post(
        "/api/ai/plan",
        headers=HEADERS,
        json={
            "projectDirectory": str(project),
            "versionId": version_id,
            "goal": "test",
            "model": {"baseUrl": "https://example.com", "apiKey": "secret", "model": "remote"},
        },
    )
    assert external_model.status_code == 422