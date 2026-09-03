from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field


def camel(value: str) -> str:
    parts = value.split("_")
    return parts[0] + "".join(part.title() for part in parts[1:])


class ApiModel(BaseModel):
    model_config = ConfigDict(alias_generator=camel, populate_by_name=True)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class ProjectCreate(ApiModel):
    directory: str
    name: str = "新建分析项目"
    language: Literal["zh-CN", "en"] = "zh-CN"


class FileImport(ApiModel):
    project_directory: str
    path: str
    name: str | None = None
    sheet_name: str | int | None = 0
    delimiter: str | None = None
    encoding: str | None = None


class DatasetOperation(ApiModel):
    project_directory: str
    version_id: str


class CleanRequest(DatasetOperation):
    operations: list[dict[str, Any]]


class StatsRequest(DatasetOperation):
    method: str
    columns: list[str]
    parameters: dict[str, Any] = Field(default_factory=dict)


class ChartRequest(DatasetOperation):
    kind: str = "histogram"
    x: str
    y: str | None = None
    color: str | None = None
    title: str | None = None


class DatabaseConfig(ApiModel):
    dialect: Literal["postgresql", "mysql"]
    host: str
    port: int
    database: str
    username: str
    password: str
    ssl_mode: str | None = None


class DatabaseQuery(ApiModel):
    connection: DatabaseConfig
    sql: str
    parameters: dict[str, Any] = Field(default_factory=dict)
    row_limit: int = Field(default=10_000, ge=1, le=1_000_000)
    timeout_seconds: int = Field(default=30, ge=1, le=300)


class DatabaseWritePrepare(ApiModel):
    connection: DatabaseConfig
    sql: str
    parameters: dict[str, Any] = Field(default_factory=dict)


class DatabaseWriteExecute(DatabaseWritePrepare):
    approval_id: str


class ModelProfile(ApiModel):
    base_url: str
    model: str
    api_key: str
    timeout_seconds: int = Field(default=60, ge=5, le=300)
    language: Literal["zh-CN", "en"] = "zh-CN"


class PlanRequest(DatasetOperation):
    goal: str
    model: ModelProfile | None = None
    include_samples: bool = True
    language: Literal["zh-CN", "en"] = "zh-CN"


class SemanticProfileRequest(DatasetOperation):
    target_column: str | None = None
    positive_value: str | None = None
    identifier_columns: list[str] = Field(default_factory=list)
    categorical_columns: list[str] = Field(default_factory=list)
    numeric_columns: list[str] = Field(default_factory=list)
    date_column: str | None = None
    business_context: str = ""
    material_gap_points: float = Field(default=10, ge=0, le=100)
    missing_warning_percent: float = Field(default=5, ge=0, le=100)
    strong_correlation: float = Field(default=.7, ge=0, le=1)


class PlanExecution(ApiModel):
    project_directory: str
    plan_id: str
    language: Literal["zh-CN", "en"] = "zh-CN"


class PlanTaskCommand(ApiModel):
    project_directory: str
    task_id: str


class PythonValidation(ApiModel):
    code: str


class PythonExecution(PythonValidation):
    project_directory: str
    timeout_seconds: int = Field(default=30, ge=1, le=120)


class ReportRequest(ApiModel):
    project_directory: str
    title: str
    sections: list[dict[str, Any]]
    language: Literal["zh-CN", "en"] = "zh-CN"
    template: Literal["management", "full", "technical"] = "full"


class DatasetExportRequest(DatasetOperation):
    format: Literal["csv", "xlsx"] = "csv"


class ReportExportRequest(ReportRequest):
    format: Literal["html", "pdf"] = "html"
    version_id: str | None = None
    plan_id: str | None = None


class ReproducibilityRequest(ReportRequest):
    version_id: str
    plan_id: str | None = None
    include_data: bool = False
    data_format: Literal["csv", "xlsx"] = "csv"


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex}"
