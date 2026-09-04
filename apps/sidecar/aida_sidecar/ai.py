from __future__ import annotations

from typing import Any

import pandas as pd

from .analysis import audit, json_value
from .models import new_id, now_iso


def safe_context(frame: pd.DataFrame, include_samples: bool) -> dict[str, Any]:
    report = audit(frame)
    context: dict[str, Any] = {"schema": report["schema"], "rowCount": report["rowCount"], "audit": {"duplicateRows": report["duplicateRows"], "columns": report["columns"], "warnings": report["warnings"]}}
    if include_samples:
        sample = frame.head(5).copy()
        for column in sample.select_dtypes(include=["object", "string"]).columns:
            sample[column] = sample[column].map(lambda value: None if pd.isna(value) else f"<sample:{len(str(value))} chars>")
        context["maskedSamples"] = sample.astype(object).where(pd.notna(sample), None).to_dict("records")
    return json_value(context)


def fallback_plan(goal: str, project_id: str, version_id: str, language: str = "zh-CN") -> dict[str, Any]:
    plan_id = new_id("plan")
    specs = ([
        ("Data quality audit", "Check types, missing values, duplicates, uniqueness, and outliers", "audit"),
        ("Exploratory data analysis", "Generate descriptive statistics, distributions, and relationships", "eda"),
        ("Statistical method recommendation", "Select a test or model based on variable types and the research goal", "statistical-test"),
        ("Visualization summary", "Generate traceable interactive charts", "chart"),
        ("Analysis report", "Summarize conclusions, limitations, statistical evidence, and charts", "report"),
    ] if language == "en" else [
        ("数据质量审计", "检查类型、缺失、重复、唯一性与异常值", "audit"),
        ("探索性数据分析", "生成描述统计、分布和相关关系", "eda"),
        ("统计方法建议", "依据变量类型与研究目标选择检验或模型", "statistical-test"),
        ("可视化汇总", "生成可追溯的交互图表", "chart"),
        ("分析报告", "汇总结论、限制、统计证据与图表", "report"),
    ])
    steps = []
    for index, (title, description, method) in enumerate(specs):
        steps.append({"id": new_id("step"), "planId": plan_id, "title": title, "description": description, "method": method, "inputVersionIds": [version_id], "dependencies": [steps[-1]["id"]] if steps else [], "parameters": {}, "approvalLevel": "none", "status": "draft"})
    return {"id": plan_id, "projectId": project_id, "goal": goal, "status": "draft", "steps": steps, "createdAt": now_iso()}


async def create_plan(goal: str, project_id: str, version_id: str, context: dict[str, Any], language: str = "zh-CN") -> dict[str, Any]:
    # Planning is deliberately local-only. No model URL, key, or network client is accepted here.
    return fallback_plan(goal, project_id, version_id, language)
