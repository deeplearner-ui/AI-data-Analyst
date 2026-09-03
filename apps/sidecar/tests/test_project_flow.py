from __future__ import annotations

from pathlib import Path

import pandas as pd

from aida_sidecar.datasets import import_file, load_version, save_derived
from aida_sidecar.models import FileImport
from aida_sidecar.store import ProjectStore


def test_project_import_and_version_lineage(tmp_path: Path) -> None:
    source = tmp_path / "source.csv"
    pd.DataFrame({"x": [1, 1, 2], "y": [3, 3, 4]}).to_csv(source, index=False)
    project = tmp_path / "project"
    store = ProjectStore(str(project)); manifest = store.create("test", "zh-CN")
    imported = import_file(FileImport(project_directory=str(project), path=str(source)))
    frame, version = load_version(store, imported["version"]["id"])
    derived = save_derived(store, frame.drop_duplicates(), version, "drop_duplicates")
    assert manifest["schemaVersion"] == "1.0"
    assert derived["parentVersionId"] == version["id"]
    assert derived["rowCount"] == 2
    assert len(store.audit_entries()) >= 3

