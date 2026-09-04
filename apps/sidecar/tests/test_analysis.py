from __future__ import annotations

import pandas as pd

from aida_sidecar.analysis import audit, clean, eda, statistical_test


def fixture_frame() -> pd.DataFrame:
    return pd.DataFrame({"group_a": [1.0, 2.0, 3.0, 4.0, None], "group_b": [2.0, 3.0, 4.0, 5.0, 6.0], "category": [" a ", "b", "b", "c", "c"], "category_b": ["x", "x", "y", "y", "y"]})


def test_audit_reports_quality_signals() -> None:
    report = audit(fixture_frame())
    assert report["rowCount"] == 5
    assert report["columns"][0]["missing"] == 1
    assert report["schema"][0]["semanticType"] == "numeric"


def test_cleaning_is_non_mutating() -> None:
    original = fixture_frame()
    result = clean(original, [{"kind": "fill_missing", "columns": ["group_a"], "strategy": "median"}, {"kind": "normalize_text", "columns": ["category"]}])
    assert original["group_a"].isna().sum() == 1
    assert result["group_a"].isna().sum() == 0
    assert result.loc[0, "category"] == "a"


def test_welch_test_contains_effect_and_p_value() -> None:
    result = statistical_test(fixture_frame(), "welch", ["group_a", "group_b"], {"alpha": 0.05})
    assert result["sampleSize"] == {"group_a": 4, "group_b": 5}
    assert isinstance(result["pValue"], float)
    assert isinstance(result["effectSize"], float)


def test_eda_profiles_numeric_and_categorical_fields() -> None:
    result = eda(fixture_frame())
    assert result["numericColumns"] == ["group_a", "group_b"]
    assert result["numeric"]["group_a"]["median"] == 2.5
    assert result["categorical"]["category"]["unique"] == 3
    assert result["correlation"]["group_a"]["group_b"] is not None


def test_additional_ui_statistics_methods_are_executable() -> None:
    frame = fixture_frame()
    normality = statistical_test(frame, "normality", ["group_a"], {"alpha": 0.05})
    correlation = statistical_test(frame, "pearson", ["group_a", "group_b"], {"alpha": 0.05})
    contingency = statistical_test(frame, "chi-square", ["category", "category_b"], {"alpha": 0.05})
    assert normality["sampleSize"] == 4
    assert correlation["effectSize"] == correlation["statistic"]
    assert contingency["sampleSize"] == 5



def test_p0_statistics_reports_suitability_confidence_and_practical_effect() -> None:
    frame = pd.DataFrame({"left": [10, 11, 12, 13, 14, 15, 16, 17], "right": [1, 2, 3, 4, 5, 6, 7, 8]})
    result = statistical_test(frame, "welch", ["left", "right"], {"alpha": .05, "confidenceLevel": .95, "minimumEffect": .5})
    assert result["status"] in {"completed", "warning"}
    assert result["confidenceInterval"][0] < result["estimate"] < result["confidenceInterval"][1]
    assert "normality" in result["assumptions"]
    assert result["significance"]["statisticallySignificant"] is True
    assert result["significance"]["practicallySignificant"] is True


def test_p0_auto_selection_and_multiplicity_adjustment() -> None:
    categorical = pd.DataFrame({"outcome": ["yes", "yes", "no", "no"], "segment": ["A", "A", "A", "B"]})
    selected = statistical_test(categorical, "auto", ["outcome", "segment"], {"analysisGoal": "relationship"})
    assert selected["method"] == "fisher"
    assert selected["recommendationReason"] == "sparse-2x2-table"
    groups = pd.DataFrame({"a": [1, 2, 3, 4, 5, 6], "b": [2, 3, 4, 5, 6, 7], "c": [10, 11, 12, 13, 14, 15]})
    result = statistical_test(groups, "anova", ["a", "b", "c"], {"postHoc": True, "pAdjustment": "holm"})
    assert len(result["comparisons"]) == 3
    assert all(item["adjustment"] == "holm" for item in result["comparisons"])
    assert all(item["adjustedPValue"] >= item["pValue"] for item in result["comparisons"])


def test_p0_insufficient_sample_is_explicitly_not_applicable() -> None:
    frame = pd.DataFrame({"a": [1, None], "b": [2, None]})
    result = statistical_test(frame, "pearson", ["a", "b"], {"alpha": .05})
    assert result["status"] == "not-applicable"
    assert result["alternatives"] == ["collect-more-data"]
