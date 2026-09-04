from __future__ import annotations

import math
from typing import Any

import numpy as np
import pandas as pd
from scipy import stats
from statsmodels.stats.multitest import multipletests

from .analysis import json_value, legacy_statistical_test


def _normality(values: np.ndarray) -> dict[str, Any]:
    if len(values) < 3:
        return {"applicable": False, "passed": None, "reason": "at-least-3-observations-required"}
    statistic, p_value = stats.shapiro(values[:5000])
    return {"applicable": True, "passed": bool(p_value >= .05), "statistic": float(statistic), "pValue": float(p_value), "sampleSize": min(len(values), 5000)}


def _mean_ci(left: np.ndarray, right: np.ndarray | None, confidence: float, equal_var: bool = False) -> list[float] | None:
    if right is None:
        if len(left) < 2: return None
        estimate, error, degrees = float(left.mean()), float(stats.sem(left)), len(left) - 1
    else:
        if len(left) < 2 or len(right) < 2: return None
        estimate = float(left.mean() - right.mean())
        left_variance, right_variance = left.var(ddof=1), right.var(ddof=1)
        if equal_var:
            degrees = len(left) + len(right) - 2
            pooled = ((len(left) - 1) * left_variance + (len(right) - 1) * right_variance) / degrees
            error = math.sqrt(pooled * (1 / len(left) + 1 / len(right)))
        else:
            left_term, right_term = left_variance / len(left), right_variance / len(right)
            error = math.sqrt(left_term + right_term)
            denominator = left_term**2 / (len(left) - 1) + right_term**2 / (len(right) - 1)
            degrees = (left_term + right_term) ** 2 / denominator if denominator else len(left) + len(right) - 2
    margin = float(stats.t.ppf((1 + confidence) / 2, degrees) * error)
    return [estimate - margin, estimate + margin]


def _correlation_ci(value: float, size: int, confidence: float) -> list[float] | None:
    if size <= 3 or not math.isfinite(value): return None
    transformed = float(np.arctanh(max(-.999999, min(.999999, value))))
    margin = float(stats.norm.ppf((1 + confidence) / 2) / math.sqrt(size - 3))
    return [float(np.tanh(transformed - margin)), float(np.tanh(transformed + margin))]


def _recommend(frame: pd.DataFrame, columns: list[str], parameters: dict[str, Any]) -> tuple[str, str, list[str]]:
    numeric = [pd.api.types.is_numeric_dtype(frame[column]) for column in columns]
    categorical_like = [not is_numeric or frame[column].nunique(dropna=True) <= 12 for column, is_numeric in zip(columns, numeric)]
    if len(columns) == 1:
        if not numeric[0]: raise ValueError("Automatic single-field analysis requires a numeric field")
        return "normality", "single-numeric-field", []
    if all(categorical_like):
        table = pd.crosstab(frame[columns[0]], frame[columns[1]])
        if table.shape == (2, 2) and float(stats.chi2_contingency(table)[3].min()) < 5:
            return "fisher", "sparse-2x2-table", ["chi-square"]
        return "chi-square", "categorical-independence", ["fisher"] if table.shape == (2, 2) else []
    if not all(numeric): raise ValueError("Automatic selection requires all numeric fields or two categorical fields")
    samples = [pd.to_numeric(frame[column], errors="coerce").dropna().to_numpy() for column in columns]
    if len(columns) > 2:
        parametric = all(_normality(sample).get("passed") is True for sample in samples) and stats.levene(*samples).pvalue >= .05
        return ("anova", "parametric-multigroup", ["kruskal"]) if parametric else ("kruskal", "robust-multigroup", ["anova"])
    goal = parameters.get("analysisGoal", "relationship")
    if goal == "paired-comparison":
        paired = frame[columns].apply(pd.to_numeric, errors="coerce").dropna()
        normal = _normality((paired.iloc[:, 0] - paired.iloc[:, 1]).to_numpy()).get("passed") is True
        return ("paired-t", "normal-paired-differences", ["wilcoxon"]) if normal else ("wilcoxon", "robust-paired-comparison", ["paired-t"])
    normal = all(_normality(sample).get("passed") is True for sample in samples)
    if goal == "independent-comparison":
        if not normal: return "mann-whitney", "robust-independent-comparison", ["welch"]
        return ("t-test", "equal-independent-variances", ["welch"]) if stats.levene(*samples).pvalue >= .05 else ("welch", "unequal-independent-variances", ["mann-whitney"])
    return ("pearson", "normal-linear-relationship", ["spearman"]) if normal else ("spearman", "robust-monotonic-relationship", ["pearson", "kendall"])


def _pairwise(samples: list[np.ndarray], columns: list[str], parametric: bool, adjustment: str) -> list[dict[str, Any]]:
    pairs: list[tuple[int, int, float, float]] = []
    for left_index in range(len(samples)):
        for right_index in range(left_index + 1, len(samples)):
            left, right = samples[left_index], samples[right_index]
            statistic, p_value = stats.ttest_ind(left, right, equal_var=False) if parametric else stats.mannwhitneyu(left, right)
            pairs.append((left_index, right_index, float(statistic), float(p_value)))
    adjusted = multipletests([pair[3] for pair in pairs], method=adjustment)[1] if pairs else []
    return [{"left": columns[pair[0]], "right": columns[pair[1]], "statistic": pair[2], "pValue": pair[3], "adjustedPValue": float(adjusted[index]), "adjustment": adjustment} for index, pair in enumerate(pairs)]


def statistical_test(frame: pd.DataFrame, method: str, columns: list[str], parameters: dict[str, Any]) -> dict[str, Any]:
    unknown = [column for column in columns if column not in frame.columns]
    if unknown: raise ValueError(f"Unknown statistical fields: {', '.join(unknown)}")
    if not columns or len(columns) != len(set(columns)): raise ValueError("Statistical fields are required and must be unique")
    requested, reason, alternatives = method, "explicit-method", []
    if method == "auto": method, reason, alternatives = _recommend(frame, columns, parameters)
    alpha = float(parameters.get("alpha", .05))
    confidence = float(parameters.get("confidenceLevel", 1 - alpha))
    if not 0 < alpha < 1 or not 0 < confidence < 1: raise ValueError("alpha and confidenceLevel must be between 0 and 1")
    samples = [pd.to_numeric(frame[column], errors="coerce").dropna().to_numpy() for column in columns]
    minimum = 3 if method == "normality" else 2
    if method not in {"chi-square", "fisher"} and any(len(sample) < minimum for sample in samples):
        return {"id": None, "method": method, "requestedMethod": requested, "columns": columns, "status": "not-applicable", "sampleSize": {column: len(sample) for column, sample in zip(columns, samples)}, "assumptions": {}, "diagnostics": [f"minimum-{minimum}-valid-observations-per-field"], "alternatives": alternatives or ["collect-more-data"], "recommendationReason": "insufficient-sample", "interpretation": "Method requirements were not met"}
    result = legacy_statistical_test(frame, method, columns, parameters)
    result.update(requestedMethod=requested, status="completed", recommendationReason=reason, alternatives=alternatives)
    if method in {"t-test", "welch"}:
        normality = {column: _normality(sample) for column, sample in zip(columns, samples)}
        levene = stats.levene(*samples)
        result["assumptions"] = {"normality": normality, "equalVariance": {"passed": bool(levene.pvalue >= .05), "pValue": float(levene.pvalue), "required": method == "t-test"}, "independentObservations": "study-design-confirmation-required"}
        result["estimate"], result["estimateLabel"] = float(samples[0].mean() - samples[1].mean()), "mean-difference"
        result["confidenceInterval"] = _mean_ci(samples[0], samples[1], confidence, method == "t-test")
        if method == "t-test" and levene.pvalue < .05: result.update(status="warning", recommendationReason="equal-variance-warning", alternatives=["welch", "mann-whitney"])
        elif any(check.get("passed") is False for check in normality.values()): result.update(status="warning", recommendationReason="normality-warning", alternatives=["mann-whitney"])
    elif method == "paired-t":
        paired = frame[columns].apply(pd.to_numeric, errors="coerce").dropna()
        differences = (paired.iloc[:, 0] - paired.iloc[:, 1]).to_numpy()
        result["assumptions"] = {"pairedDifferenceNormality": _normality(differences), "matchedObservations": "study-design-confirmation-required"}
        result["estimate"], result["estimateLabel"] = float(differences.mean()), "paired-mean-difference"
        result["confidenceInterval"] = _mean_ci(differences, None, confidence)
        if result["assumptions"]["pairedDifferenceNormality"].get("passed") is False: result.update(status="warning", recommendationReason="paired-normality-warning", alternatives=["wilcoxon"])
    elif method == "mann-whitney":
        result["effectSize"] = 2 * float(result["statistic"]) / (len(samples[0]) * len(samples[1])) - 1
        result["estimate"], result["estimateLabel"] = float(np.median(samples[0]) - np.median(samples[1])), "median-difference"
        result["assumptions"] = {"ordinalOrContinuous": True, "independentObservations": "study-design-confirmation-required"}
    elif method in {"pearson", "spearman", "kendall"}:
        result["estimate"], result["estimateLabel"] = result["statistic"], "correlation-coefficient"
        result["confidenceInterval"] = _correlation_ci(float(result["statistic"]), int(result["sampleSize"]), confidence)
        normality = {column: _normality(frame[columns].apply(pd.to_numeric, errors="coerce").dropna()[column].to_numpy()) for column in columns}
        result["assumptions"] = {"normality": normality, "relationshipShape": "scatter-plot-review-required", "independentObservations": "study-design-confirmation-required"}
        if method == "pearson" and any(check.get("passed") is False for check in normality.values()): result.update(status="warning", recommendationReason="pearson-normality-warning", alternatives=["spearman", "kendall"])
    elif method in {"anova", "kruskal"}:
        total = sum(len(sample) for sample in samples)
        if method == "anova":
            grand = np.concatenate(samples).mean()
            denominator = sum(float(((sample - grand) ** 2).sum()) for sample in samples)
            result["effectSize"] = float(sum(len(sample) * (sample.mean() - grand) ** 2 for sample in samples) / denominator) if denominator else None
            normality = {column: _normality(sample) for column, sample in zip(columns, samples)}
            levene = stats.levene(*samples)
            result["assumptions"] = {"normality": normality, "equalVariance": {"passed": bool(levene.pvalue >= .05), "pValue": float(levene.pvalue)}, "independentObservations": "study-design-confirmation-required"}
            if levene.pvalue < .05 or any(check.get("passed") is False for check in normality.values()): result.update(status="warning", recommendationReason="anova-assumption-warning", alternatives=["kruskal"])
        else:
            result["effectSize"] = float((result["statistic"] - len(samples) + 1) / (total - len(samples))) if total > len(samples) else None
            result["assumptions"] = {"similarDistributionShape": "visual-review-required", "independentObservations": "study-design-confirmation-required"}
        result["comparisons"] = _pairwise(samples, columns, method == "anova", parameters.get("pAdjustment", "holm")) if len(samples) > 2 and parameters.get("postHoc", True) else []
    elif method == "chi-square":
        minimum_expected = float(result["assumptions"].get("minimumExpectedCount", 0))
        table = pd.crosstab(frame[columns[0]], frame[columns[1]])
        expected = stats.chi2_contingency(table)[3]
        low_count = int((expected < 5).sum())
        result["assumptions"].update(cellsBelowFive=low_count, percentCellsBelowFive=float(low_count / expected.size * 100), independentObservations="study-design-confirmation-required")
        if minimum_expected < 1 or low_count / expected.size > .2: result.update(status="warning", recommendationReason="sparse-expected-counts", alternatives=["fisher"] if table.shape == (2, 2) else ["combine-sparse-levels", "collect-more-data"])
    minimum_effect, effect_size = parameters.get("minimumEffect"), result.get("effectSize")
    result["significance"] = {"alpha": alpha, "confidenceLevel": confidence, "statisticallySignificant": result.get("pValue") is not None and result["pValue"] < alpha, "minimumEffect": minimum_effect, "practicallySignificant": None if minimum_effect is None or effect_size is None else abs(effect_size) >= float(minimum_effect)}
    return {key: json_value(value) for key, value in result.items()}
