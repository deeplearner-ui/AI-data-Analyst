from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

import chardet
import numpy as np
import pandas as pd

from .models import FileImport, new_id, now_iso
from .privacy import privacy_scan
from .store import ProjectStore


MAX_FILE_BYTES = 100 * 1024 * 1024


def semantic_type(series: pd.Series) -> str:
    if pd.api.types.is_bool_dtype(series): return "boolean"
    if pd.api.types.is_numeric_dtype(series): return "numeric"
    if pd.api.types.is_datetime64_any_dtype(series): return "datetime"
    unique_ratio = series.nunique(dropna=True) / max(len(series), 1)
    return "categorical" if unique_ratio < 0.2 or series.nunique(dropna=True) <= 50 else "text"


def schema_for(frame: pd.DataFrame) -> list[dict[str, Any]]:
    return [{
        "name": str(column), "dtype": str(frame[column].dtype),
        "nullable": bool(frame[column].isna().any()), "semanticType": semantic_type(frame[column]),
    } for column in frame.columns]


def fingerprint(frame: pd.DataFrame) -> str:
    digest = hashlib.sha256()
    digest.update("|".join(map(str, frame.columns)).encode())
    digest.update(pd.util.hash_pandas_object(frame, index=True).values.tobytes())
    return digest.hexdigest()


def read_source(request: FileImport) -> pd.DataFrame:
    source = Path(request.path).expanduser().resolve()
    if not source.is_file(): raise FileNotFoundError(f"Data file does not exist: {source}")
    if source.stat().st_size > MAX_FILE_BYTES: raise ValueError("File exceeds the 100 MB MVP limit")
    suffix = source.suffix.lower()
    if suffix == ".csv":
        raw = source.read_bytes()[:65_536]
        encoding = request.encoding or chardet.detect(raw).get("encoding") or "utf-8"
        options: dict[str, Any] = {"encoding": encoding}
        if request.delimiter: options["sep"] = request.delimiter
        return pd.read_csv(source, **options)
    if suffix in {".xlsx", ".xls"}:
        return pd.read_excel(source, sheet_name=request.sheet_name)
    raise ValueError("Only CSV, XLSX, and XLS files are supported")


def import_file(request: FileImport) -> dict[str, Any]:
    store = ProjectStore(request.project_directory)
    manifest = store.open()
    frame = read_source(request)
    if not isinstance(frame, pd.DataFrame): raise ValueError("The selected sheet did not produce a table")
    dataset_id, version_id = new_id("dataset"), new_id("version")
    storage = store.data / f"{version_id}.parquet"
    frame.to_parquet(storage, index=False)
    version = {
        "id": version_id, "datasetId": dataset_id, "fingerprint": fingerprint(frame),
        "rowCount": len(frame), "columns": schema_for(frame), "storagePath": str(storage),
        "operation": "import", "createdAt": now_iso(),
    }
    dataset = {
        "id": dataset_id, "name": request.name or Path(request.path).stem,
        "sourceKind": "csv" if Path(request.path).suffix.lower() == ".csv" else "xlsx",
        "sourceLabel": str(Path(request.path).name), "currentVersionId": version_id, "createdAt": now_iso(),
    }
    store.add_version(version)
    manifest["datasets"].append(dataset)
    store.save_manifest(manifest)
    store.audit("dataset.imported", {"datasetId": dataset_id, "versionId": version_id, "source": dataset["sourceLabel"]})
    return {"dataset": dataset, "version": version, "preview": preview_frame(frame)}


def load_version(store: ProjectStore, version_id: str) -> tuple[pd.DataFrame, dict[str, Any]]:
    version = store.get_version(version_id)
    return pd.read_parquet(version["storagePath"]), version


def preview_frame(frame: pd.DataFrame, limit: int = 100) -> dict[str, Any]:
    safe = frame.head(limit).replace({np.nan: None})
    return {
        "columns": schema_for(frame), "rows": safe.to_dict(orient="records"),
        "rowCount": len(frame), "truncated": len(frame) > limit, "privacy": privacy_scan(frame),
    }


def save_derived(store: ProjectStore, frame: pd.DataFrame, parent: dict[str, Any], operation: str) -> dict[str, Any]:
    version_id = new_id("version")
    storage = store.data / f"{version_id}.parquet"
    frame.to_parquet(storage, index=False)
    version = {
        "id": version_id, "datasetId": parent["datasetId"], "parentVersionId": parent["id"],
        "fingerprint": fingerprint(frame), "rowCount": len(frame), "columns": schema_for(frame),
        "storagePath": str(storage), "operation": operation, "createdAt": now_iso(),
    }
    store.add_version(version)
    manifest = store.open()
    for dataset in manifest["datasets"]:
        if dataset["id"] == parent["datasetId"]: dataset["currentVersionId"] = version_id
    store.save_manifest(manifest)
    store.audit("dataset.version.created", {"versionId": version_id, "parentVersionId": parent["id"], "operation": operation})
    return version
