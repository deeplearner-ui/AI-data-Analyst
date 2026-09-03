from pathlib import Path

import pandas as pd

from aida_sidecar.ai import fallback_plan
from aida_sidecar.datasets import import_file
from aida_sidecar.models import FileImport
from aida_sidecar.store import ProjectStore
from aida_sidecar.workflow import execute_plan


def test_plan_can_be_cancelled_before_next_step(tmp_path: Path) -> None:
    project = tmp_path / "cancel-project"
    source = tmp_path / "cancel.csv"
    pd.DataFrame({"a": [1, 2, 3], "b": [2, 3, 5]}).to_csv(source, index=False)
    store = ProjectStore(str(project))
    manifest = store.create("cancel", "en")
    imported = import_file(FileImport(project_directory=str(project), path=str(source)))
    plan = fallback_plan("Cancel this plan", manifest["id"], imported["version"]["id"], "en")
    store.save_plan(plan)

    result = execute_plan(store, plan["id"], "en", cancellation_requested=lambda: True)

    assert result["cancelled"] is True
    assert result["plan"]["status"] == "cancelled"
    assert all(step["status"] == "cancelled" for step in result["plan"]["steps"])
    assert store.get_plan(plan["id"])["status"] == "cancelled"


def test_titanic_like_plan_uses_meaningful_fields_and_rich_report(tmp_path: Path) -> None:
    project = tmp_path / "titanic-project"
    source = tmp_path / "train.csv"
    pd.DataFrame({
        "PassengerId": range(1, 13),
        "Survived": [0, 1, 1, 1, 0, 0, 0, 0, 1, 1, 1, 0],
        "Pclass": [3, 1, 3, 1, 3, 3, 1, 3, 2, 1, 1, 3],
        "Sex": ["male", "female", "female", "female", "male", "male", "male", "male", "female", "female", "female", "male"],
        "Age": [22, 38, 26, 35, 35, None, 54, 2, 27, 14, 4, 20],
        "Fare": [7.25, 71.28, 7.93, 53.1, 8.05, 8.46, 51.86, 21.08, 11.13, 30.07, 16.7, 8.05],
    }).to_csv(source, index=False)
    store = ProjectStore(str(project))
    manifest = store.create("Titanic", "zh-CN")
    imported = import_file(FileImport(project_directory=str(project), path=str(source)))
    plan = fallback_plan("分析生存情况与乘客特征之间的关系", manifest["id"], imported["version"]["id"], "zh-CN")
    store.save_plan(plan)

    result = execute_plan(store, plan["id"], "zh-CN")

    statistics = result["latest"]["statistics"]
    assert statistics["method"] == "chi-square"
    assert statistics["columns"] == ["Survived", "Sex"]
    assert "PassengerId" not in result["latest"]["chart"]["title"]
    report = result["latest"]["report"]
    assert len(report["sections"]) == 10
    assert report["sections"][0]["title"] == "执行摘要"
    assert report["sections"][1]["title"] == "关键发现"
    assert len(report["findings"]) >= 3
    assert report["quality"]["score"] >= 0
    assert report["quality"]["grade"] in {"A", "B", "C", "D", "E"}
    deep_dive = next(section for section in report["sections"] if section["id"] == "deep-dive")
    assert deep_dive["segments"]
    assert deep_dive["segments"][0]["field"] == "Sex"
    assert deep_dive["numericDrivers"]
    assert "分群结果差异" in deep_dive["markdown"]
    quality_section = next(section for section in report["sections"] if section["id"] == "data-quality")
    assert quality_section["risks"]
    visualization = next(section for section in report["sections"] if section["id"] == "visualization")
    assert len(visualization["visualizations"]) == 3
    assert all(item.get("insight") and item.get("caution") for item in visualization["visualizations"])
    assert next(section for section in report["sections"] if section["id"] == "decision-framework")
    assert "分析生存情况" in report["markdown"]
    assert "<svg class=\"report-chart\"" in report["html"]
    assert ">dtype<" not in report["html"] and ">bdata<" not in report["html"]
    assert "REPORT V3" in report["html"]
    assert "class=\"contents\"" in report["html"]
    assert report["markdown"].count("## 执行摘要") == 1
