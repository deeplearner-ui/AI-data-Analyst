from __future__ import annotations

import os
from typing import Any

import pandas as pd
from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from . import SCHEMA_VERSION, __version__
from .ai import create_plan, safe_context
from .analysis import adjust_p_values, audit, chart, clean, eda, model, statistical_test, time_series
from .database import execute_write, prepare_write, query, schemas
from .datasets import fingerprint, import_file, load_version, preview_frame, save_derived
from .models import (
    ChartRequest, CleanRequest, DatabaseConfig, DatabaseQuery, DatabaseWriteExecute,
    DatabaseWritePrepare, DatasetExportRequest, DatasetOperation, FileImport, PlanRequest, ProjectCreate,
    PlanExecution, PlanTaskCommand, PythonExecution, PythonValidation, ReportExportRequest, ReportRequest,
    ReproducibilityRequest, SemanticProfileRequest, StatsRequest,
)
from .reporting import build_report, dataset_export, report_export, reproducibility_bundle
from .security import execute_python, validate_python
from .store import ProjectStore
from .workflow import execute_plan, semantic_profile_suggestion
from .tasks import plan_tasks


SESSION_TOKEN = os.environ.get("AIDA_SESSION_TOKEN", "development-token")
app = FastAPI(title="AI Data Analyst Sidecar", version=__version__, docs_url=None, redoc_url=None)
app.add_middleware(CORSMiddleware, allow_origins=[], allow_credentials=False, allow_methods=[], allow_headers=[])


def authorize(authorization: str | None = Header(default=None)) -> None:
    if authorization != f"Bearer {SESSION_TOKEN}": raise HTTPException(status_code=401, detail="Invalid sidecar session token")


def fail(error: Exception) -> HTTPException:
    return HTTPException(status_code=400, detail=str(error))


def validate_report_references(store: ProjectStore, version_id: str | None, plan_id: str | None, sections: list[dict[str, Any]]) -> None:
    if version_id: store.get_version(version_id)
    if not plan_id: return
    store.get_plan(plan_id)
    artifacts = store.artifacts_for_plan(plan_id)
    available = {str(artifact["id"]) for artifact in artifacts}
    available.update(str(artifact["payload"]["id"]) for artifact in artifacts if isinstance(artifact.get("payload"), dict) and artifact["payload"].get("id"))
    available.update(
        str(visualization["id"])
        for artifact in artifacts
        if isinstance(artifact.get("payload"), dict)
        for visualization in artifact["payload"].get("reportVisualizations", [])
        if isinstance(visualization, dict) and visualization.get("id")
    )
    requested = {str(item) for section in sections for key in ("resultIds", "chartIds") for item in section.get(key, [])}
    missing = sorted(requested - available)
    if missing: raise ValueError(f"Report references are not present in the selected analysis plan: {', '.join(missing)}")


@app.get("/api/health", dependencies=[Depends(authorize)])
def health() -> dict[str, Any]:
    return {"status": "ok", "schemaVersion": SCHEMA_VERSION, "version": __version__, "capabilities": ["projects", "csv", "xlsx", "audit", "clean", "eda", "statistics", "models", "time-series", "plotly", "postgresql", "mysql", "ai-plan", "plan-execution", "artifacts", "reports", "semantic-profiles"]}


@app.post("/api/projects", dependencies=[Depends(authorize)])
def create_project(request: ProjectCreate):
    try: return ProjectStore(request.directory).create(request.name, request.language)
    except Exception as error: raise fail(error) from error


@app.post("/api/projects/open", dependencies=[Depends(authorize)])
def open_project(request: dict[str, str]):
    try: return ProjectStore(request["directory"]).open()
    except Exception as error: raise fail(error) from error


@app.post("/api/projects/audit-log", dependencies=[Depends(authorize)])
def project_audit_log(request: dict[str, Any]):
    try: return {"entries": ProjectStore(request["projectDirectory"]).audit_entries(int(request.get("limit", 200)))}
    except Exception as error: raise fail(error) from error


@app.post("/api/datasets/import", dependencies=[Depends(authorize)])
def dataset_import(request: FileImport):
    try: return import_file(request)
    except Exception as error: raise fail(error) from error


@app.post("/api/datasets/preview", dependencies=[Depends(authorize)])
def dataset_preview(request: DatasetOperation):
    try:
        frame, _ = load_version(ProjectStore(request.project_directory), request.version_id)
        return preview_frame(frame)
    except Exception as error: raise fail(error) from error


@app.post("/api/analysis/semantics/get", dependencies=[Depends(authorize)])
def analysis_semantics_get(request: DatasetOperation):
    try:
        store = ProjectStore(request.project_directory); frame, _ = load_version(store, request.version_id)
        profile = store.semantic_profile(request.version_id)
        return {"profile": profile or semantic_profile_suggestion(frame), "suggested": profile is None}
    except Exception as error: raise fail(error) from error


@app.post("/api/analysis/semantics/save", dependencies=[Depends(authorize)])
def analysis_semantics_save(request: SemanticProfileRequest):
    try:
        store = ProjectStore(request.project_directory); frame, _ = load_version(store, request.version_id)
        available = {str(column) for column in frame.columns}
        profile = request.model_dump(by_alias=True, exclude={"project_directory", "version_id"})
        assigned = [item for key in ("identifierColumns", "categoricalColumns", "numericColumns") for item in profile[key]]
        referenced = set(assigned) | ({profile["targetColumn"]} if profile.get("targetColumn") else set()) | ({profile["dateColumn"]} if profile.get("dateColumn") else set())
        unknown = sorted(referenced - available)
        if unknown: raise ValueError(f"Semantic profile references unknown fields: {', '.join(unknown)}")
        if len(assigned) != len(set(assigned)): raise ValueError("A field cannot have more than one semantic role")
        if profile.get("targetColumn") in set(assigned): raise ValueError("The target field cannot also be an identifier, category, or numeric driver")
        if profile.get("dateColumn") in set(assigned) or profile.get("dateColumn") == profile.get("targetColumn"): raise ValueError("The date field cannot have another semantic role")
        invalid_numeric = [column for column in profile["numericColumns"] if not pd.api.types.is_numeric_dtype(frame[column])]
        if invalid_numeric: raise ValueError(f"Numeric driver fields are not numeric: {', '.join(invalid_numeric)}")
        if profile.get("targetColumn") and profile.get("positiveValue") is not None:
            values = {str(value) for value in frame[profile["targetColumn"]].dropna().unique()}
            if profile["positiveValue"] not in values: raise ValueError("The positive outcome is not present in the target field")
        return {"profile": store.save_semantic_profile(request.version_id, profile)}
    except Exception as error: raise fail(error) from error


@app.post("/api/datasets/export", dependencies=[Depends(authorize)])
def dataset_export_file(request: DatasetExportRequest):
    try:
        store = ProjectStore(request.project_directory)
        result = dataset_export(store, request.version_id, request.format)
        store.audit("dataset.exported", {"versionId": request.version_id, "format": request.format, "bytes": result["bytes"]})
        return result
    except Exception as error: raise fail(error) from error


@app.post("/api/analysis/audit", dependencies=[Depends(authorize)])
def run_audit(request: DatasetOperation):
    try:
        frame, version = load_version(ProjectStore(request.project_directory), request.version_id)
        return {"versionId": version["id"], "audit": audit(frame)}
    except Exception as error: raise fail(error) from error


@app.post("/api/analysis/eda", dependencies=[Depends(authorize)])
def run_eda(request: DatasetOperation):
    try:
        frame, version = load_version(ProjectStore(request.project_directory), request.version_id)
        return {"versionId": version["id"], "eda": eda(frame)}
    except Exception as error: raise fail(error) from error


@app.post("/api/analysis/clean", dependencies=[Depends(authorize)])
def run_clean(request: CleanRequest):
    try:
        store = ProjectStore(request.project_directory); frame, parent = load_version(store, request.version_id)
        result = clean(frame, request.operations)
        if fingerprint(result) == parent["fingerprint"]:
            return {"version": parent, "preview": preview_frame(result), "unchanged": True}
        version = save_derived(store, result, parent, "clean")
        return {"version": version, "preview": preview_frame(result), "unchanged": False}
    except Exception as error: raise fail(error) from error


@app.post("/api/analysis/clean/preview", dependencies=[Depends(authorize)])
def preview_clean(request: CleanRequest):
    try:
        store = ProjectStore(request.project_directory); frame, version = load_version(store, request.version_id)
        result = clean(frame, request.operations)
        return {
            "versionId": version["id"], "operations": request.operations,
            "before": audit(frame), "after": audit(result), "preview": preview_frame(result),
            "changed": fingerprint(result) != version["fingerprint"],
        }
    except Exception as error: raise fail(error) from error


@app.post("/api/analysis/statistics", dependencies=[Depends(authorize)])
def run_statistics(request: StatsRequest):
    try:
        frame, _ = load_version(ProjectStore(request.project_directory), request.version_id)
        return statistical_test(frame, request.method, request.columns, request.parameters)
    except Exception as error: raise fail(error) from error


@app.post("/api/analysis/models", dependencies=[Depends(authorize)])
def run_model(request: StatsRequest):
    try:
        frame, _ = load_version(ProjectStore(request.project_directory), request.version_id)
        return model(frame, request.method, request.columns, request.parameters)
    except Exception as error: raise fail(error) from error


@app.post("/api/analysis/time-series", dependencies=[Depends(authorize)])
def run_time_series(request: StatsRequest):
    try:
        frame, _ = load_version(ProjectStore(request.project_directory), request.version_id)
        return time_series(frame, request.columns[0], request.columns[1], int(request.parameters.get("period", 12)))
    except Exception as error: raise fail(error) from error


@app.post("/api/analysis/adjust-p-values", dependencies=[Depends(authorize)])
def run_adjustment(request: dict[str, Any]):
    try: return {"adjustedPValues": adjust_p_values(request["pValues"], request.get("method", "fdr_bh"))}
    except Exception as error: raise fail(error) from error


@app.post("/api/analysis/chart", dependencies=[Depends(authorize)])
def run_chart(request: ChartRequest):
    try:
        frame, _ = load_version(ProjectStore(request.project_directory), request.version_id)
        artifact = chart(frame, request.kind, request.x, request.y, request.color, request.title)
        artifact["datasetVersionId"] = request.version_id
        return artifact
    except Exception as error: raise fail(error) from error


@app.post("/api/analysis/python/validate", dependencies=[Depends(authorize)])
def validate_code(request: PythonValidation): return {"valid": not (issues := validate_python(request.code)), "issues": issues}


@app.post("/api/analysis/python/execute", dependencies=[Depends(authorize)])
def execute_code(request: PythonExecution):
    try: return execute_python(request.code, request.project_directory, request.timeout_seconds)
    except Exception as error: raise fail(error) from error


@app.post("/api/ai/context-preview", dependencies=[Depends(authorize)])
def context_preview(request: PlanRequest):
    try:
        store = ProjectStore(request.project_directory)
        frame, _ = load_version(store, request.version_id)
        context = safe_context(frame, request.include_samples)
        profile = store.semantic_profile(request.version_id)
        if profile: context["semanticProfile"] = profile
        return context
    except Exception as error: raise fail(error) from error


@app.post("/api/ai/plan", dependencies=[Depends(authorize)])
async def ai_plan(request: PlanRequest):
    try:
        store = ProjectStore(request.project_directory); manifest = store.open(); frame, _ = load_version(store, request.version_id)
        context = safe_context(frame, request.include_samples)
        profile = store.semantic_profile(request.version_id)
        if profile: context["semanticProfile"] = profile
        plan = await create_plan(request.goal, manifest["id"], request.version_id, context, request.model, request.language)
        store.save_plan(plan)
        store.audit("analysis.plan.created", {"planId": plan["id"], "goal": request.goal, "usedCloudModel": request.model is not None, "semanticProfileConfirmed": bool(profile and profile.get("confirmed"))})
        return {"plan": plan, "contextPreview": context}
    except Exception as error: raise fail(error) from error


@app.post("/api/analysis/plans/get", dependencies=[Depends(authorize)])
def analysis_plan_get(request: PlanExecution):
    try:
        store = ProjectStore(request.project_directory)
        return {"plan": store.get_plan(request.plan_id), "artifacts": store.artifacts_for_plan(request.plan_id)}
    except Exception as error: raise fail(error) from error


@app.post("/api/analysis/plans/latest", dependencies=[Depends(authorize)])
def analysis_plan_latest(request: dict[str, str]):
    try:
        store = ProjectStore(request["projectDirectory"]); plan = store.latest_plan()
        return {"plan": plan, "artifacts": store.artifacts_for_plan(plan["id"]) if plan else []}
    except Exception as error: raise fail(error) from error


@app.post("/api/analysis/plans/execute", dependencies=[Depends(authorize)])
def analysis_plan_execute(request: PlanExecution):
    try: return execute_plan(ProjectStore(request.project_directory), request.plan_id, request.language)
    except Exception as error: raise fail(error) from error


@app.post("/api/analysis/plans/tasks/start", dependencies=[Depends(authorize)])
def analysis_plan_task_start(request: PlanExecution):
    try: return plan_tasks.start(request.project_directory, request.plan_id, request.language)
    except Exception as error: raise fail(error) from error


@app.post("/api/analysis/plans/tasks/status", dependencies=[Depends(authorize)])
def analysis_plan_task_status(request: PlanTaskCommand):
    try: return plan_tasks.snapshot(request.task_id, project_directory=request.project_directory)
    except Exception as error: raise fail(error) from error


@app.post("/api/analysis/plans/tasks/cancel", dependencies=[Depends(authorize)])
def analysis_plan_task_cancel(request: PlanTaskCommand):
    try: return plan_tasks.cancel(request.task_id, request.project_directory)
    except Exception as error: raise fail(error) from error


@app.post("/api/database/schemas", dependencies=[Depends(authorize)])
def database_schemas(request: DatabaseConfig):
    try: return schemas(request)
    except Exception as error: raise fail(error) from error


@app.post("/api/database/query", dependencies=[Depends(authorize)])
def database_query(request: DatabaseQuery):
    try: return query(request.connection, request.sql, request.parameters, request.row_limit, request.timeout_seconds)
    except Exception as error: raise fail(error) from error


@app.post("/api/database/write/prepare", dependencies=[Depends(authorize)])
def database_prepare_write(request: DatabaseWritePrepare):
    try: return prepare_write(request.connection, request.sql, request.parameters)
    except Exception as error: raise fail(error) from error


@app.post("/api/database/write/execute", dependencies=[Depends(authorize)])
def database_execute_write(request: DatabaseWriteExecute):
    try: return execute_write(request.connection, request.sql, request.parameters, request.approval_id)
    except Exception as error: raise fail(error) from error


@app.post("/api/reports/build", dependencies=[Depends(authorize)])
def report_build(request: ReportRequest):
    try:
        report = build_report(request.title, request.sections, request.language, template=request.template)
        ProjectStore(request.project_directory).audit("report.generated", {"reportId": report["id"], "title": request.title})
        return report
    except Exception as error: raise fail(error) from error


@app.post("/api/reports/export", dependencies=[Depends(authorize)])
def report_export_file(request: ReportExportRequest):
    try:
        validate_report_references(ProjectStore(request.project_directory), request.version_id, request.plan_id, request.sections)
        result = report_export(request.title, request.sections, request.language, request.format, request.version_id, request.plan_id, request.template)
        ProjectStore(request.project_directory).audit("report.exported", {"reportId": result["reportId"], "format": request.format, "bytes": result["bytes"]})
        return result
    except Exception as error: raise fail(error) from error


@app.post("/api/reports/reproducibility", dependencies=[Depends(authorize)])
def report_bundle(request: ReproducibilityRequest):
    try:
        validate_report_references(ProjectStore(request.project_directory), request.version_id, request.plan_id, request.sections)
        result = reproducibility_bundle(request.project_directory, request.version_id, request.plan_id, request.title, request.sections, request.language, request.include_data, request.data_format, request.template)
        ProjectStore(request.project_directory).audit("report.bundle.exported", {"versionId": request.version_id, "planId": request.plan_id, "includedData": request.include_data, "bytes": result["bytes"]})
        return result
    except Exception as error: raise fail(error) from error
