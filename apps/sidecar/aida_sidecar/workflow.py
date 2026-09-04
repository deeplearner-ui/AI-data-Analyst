from __future__ import annotations

from time import perf_counter
from typing import Any, Callable

import pandas as pd

from .analysis import audit, chart, clean, eda, json_value, model, statistical_test, time_series
from .datasets import load_version, preview_frame, save_derived
from .privacy import sanitize_diagnostic
from .models import new_id, now_iso
from .reporting import build_report
from .store import ProjectStore


def _numeric_columns(frame: pd.DataFrame) -> list[str]:
    return [str(column) for column in frame.select_dtypes(include="number").columns]


def _is_identifier(frame: pd.DataFrame, column: str) -> bool:
    normalized = "".join(character for character in column.lower() if character.isalnum())
    if normalized == "id" or normalized.endswith("id") or any(token in normalized for token in ("identifier", "编号", "序号")):
        return True
    series = frame[column]
    return len(series) > 20 and series.nunique(dropna=True) / max(1, series.notna().sum()) > 0.98 and pd.api.types.is_integer_dtype(series)


def _analysis_roles(frame: pd.DataFrame, profile: dict[str, Any] | None = None) -> dict[str, Any]:
    columns = [str(column) for column in frame.columns]
    if profile and profile.get("confirmed"):
        target = profile.get("targetColumn") if profile.get("targetColumn") in columns else None
        identifiers = [item for item in profile.get("identifierColumns", []) if item in columns and item != target]
        categorical = [item for item in profile.get("categoricalColumns", []) if item in columns and item != target and item not in identifiers]
        numeric = [item for item in profile.get("numericColumns", []) if item in columns and item != target and item not in identifiers]
        return {"target": target, "categorical": categorical, "numeric": numeric, "identifiers": identifiers, "date": profile.get("dateColumn"), "positiveValue": profile.get("positiveValue"), "confirmed": True}
    usable = [column for column in columns if not _is_identifier(frame, column)]
    target_tokens = ("survived", "target", "outcome", "label", "response", "churn", "default", "fraud", "converted", "是否", "结果", "目标")
    binary = [column for column in usable if frame[column].nunique(dropna=True) == 2]
    target = next((column for column in binary if any(token in column.lower() for token in target_tokens)), binary[0] if binary else None)
    categorical = [column for column in usable if column != target and 2 <= frame[column].nunique(dropna=True) <= 12]
    category_tokens = ("sex", "gender", "class", "group", "treatment", "category", "segment", "embarked", "性别", "类别", "分组", "等级")
    categorical.sort(key=lambda column: (not any(token in column.lower() for token in category_tokens), frame[column].nunique(dropna=True), columns.index(column)))
    numeric = [column for column in _numeric_columns(frame) if column in usable and column != target and frame[column].nunique(dropna=True) > 5]
    numeric_tokens = ("age", "fare", "price", "income", "score", "value", "amount", "年龄", "价格", "收入", "得分", "金额")
    numeric.sort(key=lambda column: (not any(token in column.lower() for token in numeric_tokens), columns.index(column)))
    return {"target": target, "categorical": categorical, "numeric": numeric, "identifiers": [column for column in columns if column not in usable], "date": None, "positiveValue": None, "confirmed": False}


def semantic_profile_suggestion(frame: pd.DataFrame) -> dict[str, Any]:
    roles = _analysis_roles(frame)
    positive = _positive_target_value(frame[roles["target"]]) if roles["target"] else None
    assigned = set(roles["identifiers"] + roles["categorical"] + roles["numeric"] + ([roles["target"]] if roles["target"] else []))
    date = next((str(column) for column in frame.columns if str(column) not in assigned and pd.api.types.is_datetime64_any_dtype(frame[column])), None)
    return {"targetColumn": roles["target"], "positiveValue": None if positive is None else str(positive), "identifierColumns": roles["identifiers"], "categoricalColumns": roles["categorical"], "numericColumns": roles["numeric"], "dateColumn": date, "businessContext": "", "materialGapPoints": 10, "missingWarningPercent": 5, "strongCorrelation": .7, "confirmed": False}


def _automatic_statistics(frame: pd.DataFrame, profile: dict[str, Any] | None = None) -> tuple[str, list[str], dict[str, Any]] | None:
    roles = _analysis_roles(frame, profile)
    if roles["target"] and roles["categorical"]:
        return "auto", [roles["target"], roles["categorical"][0]], {"selectionReason": "binary-target-and-categorical-predictor", "analysisGoal": "relationship"}
    if len(roles["numeric"]) >= 2:
        return "auto", roles["numeric"][:2], {"selectionReason": "two-meaningful-numeric-fields", "analysisGoal": "relationship"}
    return None


def _automatic_charts(frame: pd.DataFrame, language: str, profile: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    roles = _analysis_roles(frame, profile)
    charts: list[dict[str, Any]] = []
    if roles["target"] and roles["categorical"]:
        x, color = roles["categorical"][0], roles["target"]
        title = f"{color} by {x}" if language == "en" else f"{color} 按 {x} 分组分布"
        charts.append({"kind": "histogram", "x": x, "color": color, "title": title, "selectionReason": "target-by-category"})
    for x in roles["numeric"][:2]:
        title = f"{x} distribution" if language == "en" else f"{x} 分布"
        charts.append({"kind": "histogram", "x": x, "color": roles["target"], "title": title, "selectionReason": "meaningful-numeric-distribution"})
    if not charts and roles["categorical"]:
        x = roles["categorical"][0]
        charts.append({"kind": "histogram", "x": x, "color": None, "title": f"{x} distribution" if language == "en" else f"{x} 分布", "selectionReason": "meaningful-category-distribution"})
    if not charts:
        x = str(frame.columns[0])
        charts.append({"kind": "bar", "x": x, "color": None, "title": f"{x} distribution" if language == "en" else f"{x} 分布", "selectionReason": "first-available-field"})
    return charts[:3]


def _chart_narrative(frame: pd.DataFrame, config: dict[str, Any], language: str) -> tuple[str, str]:
    x, color, reason = config["x"], config.get("color"), config["selectionReason"]
    if reason == "target-by-category" and color:
        table = pd.crosstab(frame[x], frame[color], normalize="index")
        if not table.empty:
            outcome = table.columns[-1]
            rates = table[outcome].sort_values(ascending=False)
            high, low = rates.index[0], rates.index[-1]
            observation = (f"For outcome {outcome}, {high} has the highest within-group share ({rates.iloc[0] * 100:.1f}%), versus {low} at {rates.iloc[-1] * 100:.1f}%." if language == "en" else f"以结果 {outcome} 为观察口径，{high} 组内占比最高（{rates.iloc[0] * 100:.1f}%），{low} 最低（{rates.iloc[-1] * 100:.1f}%）。")
        else:
            observation = "Group proportions could not be calculated." if language == "en" else "当前数据不足以计算稳定的分组比例。"
        caution = "Compare group sizes and uncertainty before treating the gap as actionable." if language == "en" else "将差异用于行动前，应同时核对各组样本量和不确定性。"
        return observation, caution
    if pd.api.types.is_numeric_dtype(frame[x]):
        series = pd.to_numeric(frame[x], errors="coerce").dropna()
        if len(series):
            observation = (f"The median is {_format_number(series.median())}; the middle 50% spans {_format_number(series.quantile(.25))} to {_format_number(series.quantile(.75))}, with skewness {_format_number(series.skew(), 2)}." if language == "en" else f"中位数为 {_format_number(series.median())}，中间 50% 数据位于 {_format_number(series.quantile(.25))} 至 {_format_number(series.quantile(.75))}，偏度为 {_format_number(series.skew(), 2)}。")
        else:
            observation = "No valid numeric observations were available." if language == "en" else "没有可用于分布判断的有效数值。"
        caution = "Long tails and extreme values can make the mean unrepresentative." if language == "en" else "若分布存在长尾或极端值，均值可能无法代表典型水平。"
        return observation, caution
    counts = frame[x].dropna().astype(str).value_counts()
    total = int(counts.sum())
    if total:
        observation = (f"{counts.index[0]} is the most common category ({counts.iloc[0]:,} records, {counts.iloc[0] / total * 100:.1f}%)." if language == "en" else f"{counts.index[0]} 为最高频类别（{counts.iloc[0]:,} 条，占 {counts.iloc[0] / total * 100:.1f}%）。")
    else:
        observation = "No valid category values were available." if language == "en" else "没有可用于分类汇总的有效值。"
    caution = "Rare categories may be unstable and should be reviewed before merging." if language == "en" else "低频类别的比例可能不稳定，合并前需要结合业务定义。"
    return observation, caution


def _quality_profile(frame: pd.DataFrame, audit_result: dict[str, Any], language: str) -> dict[str, Any]:
    rows, columns = max(1, len(frame)), max(1, len(frame.columns))
    audited = audit_result.get("columns", [])
    missing_cells = sum(int(item.get("missing", 0)) for item in audited)
    outlier_cells = sum(int(item.get("outliersIqr", 0)) for item in audited)
    constant_fields = sum(1 for item in audited if item.get("constant"))
    missing_rate = missing_cells / (rows * columns)
    duplicate_rate = int(audit_result.get("duplicateRows", 0)) / rows
    constant_rate = constant_fields / columns
    outlier_rate = outlier_cells / (rows * columns)
    max_missing_rate = max([float(item.get("missingRate", 0)) for item in audited] or [0])
    score = round(max(0, min(100, 100 - missing_rate * 20 - max_missing_rate * 30 - duplicate_rate * 20 - constant_rate * 15 - outlier_rate * 15)))
    grade = "A" if score >= 90 else "B" if score >= 80 else "C" if score >= 70 else "D" if score >= 60 else "E"
    level = ("Good" if score >= 85 else "Review" if score >= 70 else "High risk") if language == "en" else ("良好" if score >= 85 else "需复核" if score >= 70 else "高风险")
    return {"score": score, "grade": grade, "level": level, "missingCells": missing_cells, "missingRate": missing_rate, "duplicateRate": duplicate_rate, "constantFields": constant_fields, "outlierCells": outlier_cells, "outlierRate": outlier_rate}


def _strongest_correlation(eda_result: dict[str, Any], roles: dict[str, Any]) -> tuple[str, str, float] | None:
    allowed = [item for item in eda_result.get("numericColumns", []) if item not in roles["identifiers"]]
    correlation = eda_result.get("correlation", {})
    candidates: list[tuple[str, str, float]] = []
    for index, left in enumerate(allowed):
        for right in allowed[index + 1:]:
            value = correlation.get(left, {}).get(right)
            if value is not None:
                candidates.append((left, right, float(value)))
    return max(candidates, key=lambda item: abs(item[2])) if candidates else None


def _top_correlations(eda_result: dict[str, Any], roles: dict[str, Any], limit: int = 5) -> list[tuple[str, str, float]]:
    allowed = [item for item in eda_result.get("numericColumns", []) if item not in roles["identifiers"]]
    correlation = eda_result.get("correlation", {})
    pairs: list[tuple[str, str, float]] = []
    for index, left in enumerate(allowed):
        for right in allowed[index + 1:]:
            value = correlation.get(left, {}).get(right)
            if value is not None:
                pairs.append((left, right, float(value)))
    return sorted(pairs, key=lambda item: abs(item[2]), reverse=True)[:limit]


def _positive_target_value(series: pd.Series, configured: Any = None) -> Any:
    values = list(series.dropna().unique())
    if configured is not None:
        configured_match = next((value for value in values if str(value) == str(configured)), None)
        if configured_match is not None:
            return configured_match
    preferred = (1, True, "1", "true", "yes", "positive", "success", "survived", "是", "成功")
    for candidate in preferred:
        for value in values:
            if str(value).strip().lower() == str(candidate).lower():
                return value
    try:
        return max(values)
    except (TypeError, ValueError):
        return values[-1] if values else None


def _segment_profiles(frame: pd.DataFrame, roles: dict[str, Any]) -> list[dict[str, Any]]:
    target = roles.get("target")
    if not target:
        return []
    positive = _positive_target_value(frame[target], roles.get("positiveValue"))
    profiles: list[dict[str, Any]] = []
    for field in roles.get("categorical", [])[:4]:
        subset = frame[[field, target]].dropna()
        if subset.empty:
            continue
        grouped = subset.assign(_positive=subset[target].eq(positive).astype(float)).groupby(field, observed=True)["_positive"].agg(["mean", "count"])
        grouped = grouped[grouped["count"] >= max(2, round(len(subset) * 0.01))]
        if len(grouped) < 2:
            continue
        high, low = grouped["mean"].idxmax(), grouped["mean"].idxmin()
        high_rate, low_rate = float(grouped.loc[high, "mean"]), float(grouped.loc[low, "mean"])
        profiles.append({
            "field": field, "positiveValue": str(positive), "highGroup": str(high), "lowGroup": str(low),
            "highRate": high_rate, "lowRate": low_rate, "gap": high_rate - low_rate,
            "highCount": int(grouped.loc[high, "count"]), "lowCount": int(grouped.loc[low, "count"]),
            "confidence": "high" if min(grouped.loc[high, "count"], grouped.loc[low, "count"]) >= 30 else "medium" if min(grouped.loc[high, "count"], grouped.loc[low, "count"]) >= 10 else "low",
        })
    return sorted(profiles, key=lambda item: item["gap"], reverse=True)


def _numeric_target_profiles(frame: pd.DataFrame, roles: dict[str, Any]) -> list[dict[str, Any]]:
    target = roles.get("target")
    if not target:
        return []
    positive = _positive_target_value(frame[target], roles.get("positiveValue"))
    profiles: list[dict[str, Any]] = []
    for field in roles.get("numeric", [])[:6]:
        subset = frame[[field, target]].copy()
        subset[field] = pd.to_numeric(subset[field], errors="coerce")
        positive_values = subset.loc[subset[target].eq(positive), field].dropna()
        other_values = subset.loc[~subset[target].eq(positive) & subset[target].notna(), field].dropna()
        if len(positive_values) < 2 or len(other_values) < 2:
            continue
        pooled_denominator = len(positive_values) + len(other_values) - 2
        pooled = (((len(positive_values) - 1) * positive_values.var(ddof=1) + (len(other_values) - 1) * other_values.var(ddof=1)) / pooled_denominator) ** .5 if pooled_denominator > 0 else 0
        effect = float((positive_values.mean() - other_values.mean()) / pooled) if pooled and pd.notna(pooled) else None
        profiles.append({
            "field": field, "positiveValue": str(positive), "positiveMean": float(positive_values.mean()),
            "otherMean": float(other_values.mean()), "positiveMedian": float(positive_values.median()),
            "otherMedian": float(other_values.median()), "effectSize": effect,
            "positiveCount": len(positive_values), "otherCount": len(other_values),
            "confidence": "high" if min(len(positive_values), len(other_values)) >= 30 else "medium" if min(len(positive_values), len(other_values)) >= 10 else "low",
        })
    return sorted(profiles, key=lambda item: abs(item["effectSize"] or 0), reverse=True)


def _quality_risks(audit_result: dict[str, Any], rows: int, missing_warning_percent: float = 5) -> list[dict[str, Any]]:
    risks: list[dict[str, Any]] = []
    missing_threshold = missing_warning_percent / 100
    for item in audit_result.get("columns", []):
        if item.get("missingRate", 0) > 0:
            rate = float(item["missingRate"])
            risks.append({"field": item["name"], "kind": "missing", "rate": rate, "count": int(item.get("missing", 0)), "severity": "high" if rate >= max(.3, missing_threshold * 2) else "medium" if rate >= missing_threshold else "low"})
        if item.get("outliersIqr", 0) > 0:
            rate = int(item["outliersIqr"]) / max(1, rows)
            risks.append({"field": item["name"], "kind": "outlier", "rate": rate, "count": int(item["outliersIqr"]), "severity": "high" if rate >= .1 else "medium" if rate >= .03 else "low"})
        if item.get("constant"):
            risks.append({"field": item["name"], "kind": "constant", "rate": 1.0, "count": rows, "severity": "medium"})
    return sorted(risks, key=lambda item: ({"high": 3, "medium": 2, "low": 1}[item["severity"]], item["rate"]), reverse=True)[:10]


def _artifact(plan_id: str, step_id: str, kind: str, version_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": new_id("artifact"), "planId": plan_id, "stepId": step_id, "kind": kind,
        "datasetVersionId": version_id, "payload": json_value(payload), "createdAt": now_iso(),
    }


def _format_number(value: Any, digits: int = 4) -> str:
    if value is None: return "—"
    try:
        number = float(value)
        if not pd.notna(number): return "—"
        if digits == 0: return f"{number:,.0f}"
        if number != 0 and abs(number) < 0.001: return f"{number:.2e}"
        return f"{number:,.{digits}f}".rstrip("0").rstrip(".")
    except (TypeError, ValueError):
        return str(value)


def _method_label(method: str, language: str) -> str:
    labels = {
        "chi-square": ("Chi-square test", "卡方独立性检验"), "fisher": ("Fisher's exact test", "Fisher 精确检验"),
        "pearson": ("Pearson correlation", "Pearson 相关分析"), "spearman": ("Spearman correlation", "Spearman 相关分析"),
        "welch": ("Welch's t-test", "Welch t 检验"), "t-test": ("Independent t-test", "独立样本 t 检验"),
    }
    english, chinese = labels.get(method, (method, method))
    return english if language == "en" else chinese


def _assumption_text(value: Any, language: str) -> str:
    if isinstance(value, dict):
        labels = {"minimumExpectedCount": "minimum expected count" if language == "en" else "最小期望频数"}
        return "; ".join(f"{labels.get(str(key), key)}={_format_number(item)}" for key, item in value.items())
    if isinstance(value, list): return "; ".join(str(item) for item in value)
    return str(value or ("Review method-specific assumptions." if language == "en" else "需要复核该方法的适用条件。"))


def _confidence_text(result: dict[str, Any], language: str) -> str:
    interval = result.get("confidenceInterval")
    if not interval:
        return "Confidence interval not available for this method." if language == "en" else "当前方法暂未提供置信区间。"
    level = float(result.get("significance", {}).get("confidenceLevel", .95)) * 100
    return f"{level:.0f}% CI [{_format_number(interval[0])}, {_format_number(interval[1])}]"


def _comparison_lines(result: dict[str, Any], language: str) -> list[str]:
    comparisons = result.get("comparisons", [])
    if not comparisons: return []
    rows = ["### Multiplicity-adjusted post-hoc comparisons" if language == "en" else "### 多重比较校正后的事后检验"]
    for item in comparisons:
        rows.append(f"- **{item['left']} vs {item['right']}**: p={_format_number(item['pValue'])}, adjusted p={_format_number(item['adjustedPValue'])} ({item['adjustment']})." if language == "en" else f"- **{item['left']} 与 {item['right']}**：原始 p={_format_number(item['pValue'])}，校正后 p={_format_number(item['adjustedPValue'])}（{item['adjustment']}）。")
    return rows


def _report_sections(language: str, goal: str, frame: pd.DataFrame, artifacts: list[dict[str, Any]], profile: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    by_kind = {item["kind"]: item["payload"] for item in artifacts}
    audit_result = by_kind.get("audit", {})
    eda_result = by_kind.get("eda", {})
    stats_result = by_kind.get("statistics", {})
    chart_result = by_kind.get("chart", {})
    roles = _analysis_roles(frame, profile)
    quality_profile = _quality_profile(frame, audit_result, language)
    missing = sorted(audit_result.get("columns", []), key=lambda item: item.get("missingRate", 0), reverse=True)
    missing = [item for item in missing if item.get("missing", 0)][:5]
    result_ids = [stats_result["id"]] if stats_result.get("id") else []
    visualizations = chart_result.get("reportVisualizations") or ([chart_result] if chart_result else [])
    chart_ids = [item["id"] for item in visualizations if item.get("id")]
    target_distribution = []
    if roles["target"]:
        counts = frame[roles["target"]].dropna().value_counts()
        total = int(counts.sum())
        target_distribution = [(str(value), int(count), count / total if total else 0) for value, count in counts.items()]
    strongest_correlation = _strongest_correlation(eda_result, roles)
    top_correlations = _top_correlations(eda_result, roles)
    segment_profiles = _segment_profiles(frame, roles)
    numeric_target_profiles = _numeric_target_profiles(frame, roles)
    quality_risks = _quality_risks(audit_result, len(frame), float((profile or {}).get("missingWarningPercent", 5)))
    material_gap = float((profile or {}).get("materialGapPoints", 10)) / 100
    strong_correlation_threshold = float((profile or {}).get("strongCorrelation", .7))
    business_context = str((profile or {}).get("businessContext", "")).strip()
    findings: list[dict[str, str]] = []
    recommendations: list[str] = []

    def add_finding(title: str, detail: str, evidence: str, severity: str = "info", confidence: str = "medium") -> None:
        findings.append({"title": title, "detail": detail, "evidence": evidence, "severity": severity, "confidence": confidence})

    if language == "en":
        quality_summary = "No missing values were detected." if not missing else "Highest missingness: " + ", ".join(f"{item['name']} {_format_number(item['missingRate'] * 100, 1)}%" for item in missing) + "."
        executive = [f"The analysis addressed: **{goal}**", f"The active dataset contains **{len(frame):,} rows** and **{len(frame.columns)} fields**.", f"Overall data quality scored **{quality_profile['score']}/100 ({quality_profile['grade']}, {quality_profile['level']})**.", quality_summary]
        if business_context: executive.insert(1, f"Business context: **{business_context}**")
        executive.append(f"Field roles are **{'confirmed by the user' if roles['confirmed'] else 'automatically inferred and require confirmation'}**; target: **{roles['target'] or 'not set'}**, positive outcome: **{roles.get('positiveValue') or 'automatic'}**.")
        add_finding("Data readiness", f"The dataset received a {quality_profile['grade']} quality grade and is classified as {quality_profile['level'].lower()}.", f"Score {quality_profile['score']}/100; {quality_profile['missingCells']:,} missing cells; {audit_result.get('duplicateRows', 0):,} duplicate rows.", "success" if quality_profile["score"] >= 85 else "warning", "high")
        if target_distribution:
            executive.append(f"The inferred target **{roles['target']}** is distributed as " + ", ".join(f"{value}: {count:,} ({_format_number(rate * 100, 1)}%)" for value, count, rate in target_distribution) + ".")
            largest = max(target_distribution, key=lambda item: item[2])
            add_finding("Target balance", f"The largest {roles['target']} class is {largest[0]} at {largest[2] * 100:.1f}%.", f"{largest[1]:,} of {sum(item[1] for item in target_distribution):,} valid target records.", "warning" if largest[2] >= .65 else "info", "high")
            if largest[2] >= .65: recommendations.append(f"Use stratified evaluation and class-aware metrics for {roles['target']}; accuracy alone may be misleading.")
        if stats_result and not stats_result.get("skipped"):
            columns = stats_result.get("columns", [])
            significant = stats_result.get("pValue") is not None and stats_result["pValue"] < 0.05
            executive.append(f"The automated {_method_label(stats_result.get('method', ''), language)} of **{' and '.join(columns)}** {'found evidence of an association' if significant else 'did not find sufficient evidence of an association'} (p={_format_number(stats_result.get('pValue'))}).")
            effect = stats_result.get("effectSize")
            magnitude = "not reported" if effect is None else "large" if abs(effect) >= .5 else "moderate" if abs(effect) >= .3 else "small"
            add_finding("Statistical evidence", f"{'An association was detected' if significant else 'Evidence was insufficient'} between {' and '.join(columns)}; the reported effect is {magnitude}.", f"{_method_label(stats_result.get('method', ''), language)}, p={_format_number(stats_result.get('pValue'))}, effect={_format_number(effect)}.", "success" if significant else "info", "medium")
            recommendations.append("Validate the statistical result against method assumptions and practical impact before acting on it." if significant else "Treat the current non-significant result as inconclusive; review sample size and test assumptions before ruling out an effect.")
        if strongest_correlation:
            left, right, coefficient = strongest_correlation
            add_finding("Strongest numeric relationship", f"{left} and {right} show the strongest observed numeric relationship (r={coefficient:.2f}).", "Pairwise correlation from complete numeric observations; association is not causation.", "info", "medium")
        if segment_profiles:
            segment = segment_profiles[0]
            add_finding("Largest segment gap", f"{segment['field']} separates the inferred positive outcome most strongly: {segment['highGroup']} is {segment['highRate'] * 100:.1f}% versus {segment['lowGroup']} at {segment['lowRate'] * 100:.1f}% ({segment['gap'] * 100:.1f} percentage-point gap).", f"n={segment['highCount']} and n={segment['lowCount']}; evidence confidence {segment['confidence']}; materiality threshold {(material_gap * 100):.1f} pp.", "warning" if segment['gap'] >= material_gap else "info", segment["confidence"])
        if numeric_target_profiles:
            driver = numeric_target_profiles[0]
            magnitude = "large" if abs(driver["effectSize"] or 0) >= .8 else "moderate" if abs(driver["effectSize"] or 0) >= .5 else "small"
            add_finding("Leading numeric discriminator", f"{driver['field']} has the largest standardized difference between target groups ({magnitude}, d={_format_number(driver['effectSize'], 2)}).", f"Positive mean {_format_number(driver['positiveMean'])} (n={driver['positiveCount']}) versus other mean {_format_number(driver['otherMean'])} (n={driver['otherCount']}).", "info", driver["confidence"])
        quality = [f"- Quality score: **{quality_profile['score']}/100 ({quality_profile['grade']})**", f"- Duplicate rows: **{audit_result.get('duplicateRows', 0):,}** ({quality_profile['duplicateRate'] * 100:.1f}%)", f"- Fields with missing values: **{sum(1 for item in audit_result.get('columns', []) if item.get('missing', 0))}**", f"- IQR outlier flags: **{quality_profile['outlierCells']:,}**"]
        quality += [f"- {item['name']}: {item['missing']:,} missing ({_format_number(item['missingRate'] * 100, 1)}%)" for item in missing]
        risk_lines = ["### Field-level risk register"] + ([f"- **{item['severity'].upper()} · {item['field']} · {item['kind']}**: {item['count']:,} records ({item['rate'] * 100:.1f}%). Validate the business meaning and treatment before reuse." for item in quality_risks] or ["- No material field-level missingness, outlier, or constant-field risk was detected by the current rules."])
        exploration = [f"- Numeric fields: **{len(eda_result.get('numericColumns', []))}**", f"- Categorical/text fields: **{len(eda_result.get('categoricalColumns', []))}**"]
        for name in roles["numeric"][:3]:
            summary = eda_result.get("numeric", {}).get(name, {})
            exploration.append(f"- {name}: mean {_format_number(summary.get('mean'))}, median {_format_number(summary.get('median'))}, range {_format_number(summary.get('min'))} to {_format_number(summary.get('max'))}, skewness {_format_number(summary.get('skew'), 2)}")
        deep_dive = ["### Segment outcome gaps"]
        deep_dive += ([f"- **{item['field']}**: {item['highGroup']} {item['highRate'] * 100:.1f}% (n={item['highCount']}) vs {item['lowGroup']} {item['lowRate'] * 100:.1f}% (n={item['lowCount']}); gap **{item['gap'] * 100:.1f} pp**, confidence {item['confidence']}." for item in segment_profiles[:4]] or ["- No stable binary-target segment comparison was available."])
        deep_dive += ["", "### Numeric differences by outcome"]
        deep_dive += ([f"- **{item['field']}**: positive mean {_format_number(item['positiveMean'])}, other mean {_format_number(item['otherMean'])}; standardized effect **d={_format_number(item['effectSize'], 2)}**, confidence {item['confidence']}." for item in numeric_target_profiles[:5]] or ["- No numeric target-group comparison met the minimum sample requirement."])
        deep_dive += ["", "### Ranked numeric relationships"]
        deep_dive += ([f"- **{left} ↔ {right}**: r={value:.2f} ({'strong' if abs(value) >= strong_correlation_threshold else 'moderate' if abs(value) >= .4 else 'weak'} linear relationship; strong threshold {strong_correlation_threshold:.2f})." for left, right, value in top_correlations] or ["- Fewer than two eligible numeric fields were available."])
        stats_lines = ["No statistically suitable automatic comparison was available."] if not stats_result or stats_result.get("skipped") else [f"- Selected method: **{_method_label(stats_result.get('method', ''), language)}** ({stats_result.get('recommendationReason', 'explicit-method')})", f"- Suitability status: **{stats_result.get('status', 'completed')}**", f"- Variables: **{' / '.join(stats_result.get('columns', []))}**", f"- Sample size: {_format_number(stats_result.get('sampleSize'), 0)}", f"- Estimate: {_format_number(stats_result.get('estimate'))} ({stats_result.get('estimateLabel', 'effect')})", f"- {_confidence_text(stats_result, language)}", f"- Statistic: {_format_number(stats_result.get('statistic'))}", f"- p-value: **{_format_number(stats_result.get('pValue'))}**", f"- Effect size: {_format_number(stats_result.get('effectSize'))}", f"- Assumptions: {_assumption_text(stats_result.get('assumptions'), language)}", f"- Alternatives: {', '.join(stats_result.get('alternatives', [])) or 'none suggested'}", "- Interpretation: statistical association does not by itself establish causation."] + _comparison_lines(stats_result, language)
        recommendations += ([f"P0 · Data owner · Address missingness in {', '.join(item['name'] for item in missing[:3])}; acceptance: document the cause and compare results before/after treatment."] if missing else ["P2 · Data owner · Preserve the current low-missingness baseline; acceptance: alert when any field exceeds 5% missingness."])
        if segment_profiles: recommendations.append(f"P1 · Analyst · Validate the {segment_profiles[0]['field']} segment gap against domain definitions and confounders; acceptance: reproduce the gap on a holdout or later time period.")
        if numeric_target_profiles: recommendations.append(f"P1 · Analyst · Test whether {numeric_target_profiles[0]['field']} remains informative in a multivariable model; acceptance: report adjusted effect and confidence interval.")
        recommendations.append("P0 · Domain owner · Confirm inferred target, identifier, numeric, and categorical roles; acceptance: save an approved field-role map before operational use.")
        limitations = ["- Field roles were user-confirmed for this dataset." if roles["confirmed"] else "- Automatic variable-role inference is heuristic and should be confirmed against domain definitions.", "- Missing values, selection bias, measurement error, and unobserved confounding may affect conclusions.", "- Review assumptions and practical significance before using results for decisions."]
        titles = ("Executive summary", "Key findings", "Data quality", "Exploratory findings", "Statistical evidence", "Visual evidence", "Recommended actions", "Limitations and methodology", "Driver and segment analysis", "Evidence and decision framework")
    else:
        quality_summary = "未发现缺失值。" if not missing else "缺失率最高的字段为：" + "、".join(f"{item['name']} {_format_number(item['missingRate'] * 100, 1)}%" for item in missing) + "。"
        executive = [f"本次分析目标：**{goal}**", f"当前数据集包含 **{len(frame):,} 行**、**{len(frame.columns)} 个字段**。", f"综合数据质量评分为 **{quality_profile['score']}/100（{quality_profile['grade']} 级，{quality_profile['level']}）**。", quality_summary]
        if business_context: executive.insert(1, f"业务背景：**{business_context}**")
        executive.append(f"字段角色**{'已经用户确认' if roles['confirmed'] else '由系统自动推断，仍需确认'}**；目标字段：**{roles['target'] or '未设置'}**，正向结果：**{roles.get('positiveValue') or '自动选择'}**。")
        add_finding("数据可用性", f"当前数据质量等级为 {quality_profile['grade']}，综合判断为“{quality_profile['level']}”。", f"评分 {quality_profile['score']}/100；缺失单元格 {quality_profile['missingCells']:,} 个；重复行 {audit_result.get('duplicateRows', 0):,} 行。", "success" if quality_profile["score"] >= 85 else "warning", "high")
        if target_distribution:
            executive.append(f"自动识别的目标字段 **{roles['target']}** 分布为：" + "、".join(f"{value} 共 {count:,} 条（{_format_number(rate * 100, 1)}%）" for value, count, rate in target_distribution) + "。")
            largest = max(target_distribution, key=lambda item: item[2])
            add_finding("目标分布", f"{roles['target']} 中占比最高的类别为 {largest[0]}，占 {largest[2] * 100:.1f}%。", f"有效目标记录共 {sum(item[1] for item in target_distribution):,} 条，其中该类别 {largest[1]:,} 条。", "warning" if largest[2] >= .65 else "info", "high")
            if largest[2] >= .65: recommendations.append(f"针对 {roles['target']} 使用分层评估和类别敏感指标，避免仅凭准确率判断效果。")
        if stats_result and not stats_result.get("skipped"):
            columns = stats_result.get("columns", [])
            significant = stats_result.get("pValue") is not None and stats_result["pValue"] < 0.05
            executive.append(f"自动采用 {_method_label(stats_result.get('method', ''), language)}分析 **{' 与 '.join(columns)}**，{'发现统计关联证据' if significant else '尚未发现充分的统计关联证据'}（p={_format_number(stats_result.get('pValue'))}）。")
            effect = stats_result.get("effectSize")
            magnitude = "未报告" if effect is None else "较大" if abs(effect) >= .5 else "中等" if abs(effect) >= .3 else "较小"
            add_finding("统计证据", f"{'检测到' if significant else '尚未确认'} {' 与 '.join(columns)} 之间的关联，报告效应量属于{magnitude}水平。", f"{_method_label(stats_result.get('method', ''), language)}；p={_format_number(stats_result.get('pValue'))}；效应量={_format_number(effect)}。", "success" if significant else "info", "medium")
            recommendations.append("在采取行动前，结合方法假设、实际效应和业务成本复核统计结论。" if significant else "当前结果不能证明没有影响；建议检查样本量和检验假设后再决定是否补充数据。")
        if strongest_correlation:
            left, right, coefficient = strongest_correlation
            add_finding("最强数值关系", f"{left} 与 {right} 是当前最强的数值关系（r={coefficient:.2f}）。", "基于有效数值记录的两两相关；相关关系不等于因果关系。", "info", "medium")
        if segment_profiles:
            segment = segment_profiles[0]
            confidence_label = {"high": "高", "medium": "中", "low": "低"}[segment["confidence"]]
            add_finding("最大分群差异", f"{segment['field']} 对自动识别的正向结果区分最明显：{segment['highGroup']} 为 {segment['highRate'] * 100:.1f}%，{segment['lowGroup']} 为 {segment['lowRate'] * 100:.1f}%，相差 {segment['gap'] * 100:.1f} 个百分点。", f"两组样本量分别为 {segment['highCount']} 和 {segment['lowCount']}；证据置信度为{confidence_label}；业务显著阈值为 {material_gap * 100:.1f} 个百分点。", "warning" if segment['gap'] >= material_gap else "info", segment["confidence"])
        if numeric_target_profiles:
            driver = numeric_target_profiles[0]
            magnitude = "较大" if abs(driver["effectSize"] or 0) >= .8 else "中等" if abs(driver["effectSize"] or 0) >= .5 else "较小"
            add_finding("首要数值区分因素", f"{driver['field']} 在目标组之间的标准化差异最大（{magnitude}，d={_format_number(driver['effectSize'], 2)}）。", f"正向组均值 {_format_number(driver['positiveMean'])}（n={driver['positiveCount']}），其他组均值 {_format_number(driver['otherMean'])}（n={driver['otherCount']}）。", "info", driver["confidence"])
        quality = [f"- 数据质量评分：**{quality_profile['score']}/100（{quality_profile['grade']} 级）**", f"- 重复行：**{audit_result.get('duplicateRows', 0):,}**（{quality_profile['duplicateRate'] * 100:.1f}%）", f"- 存在缺失值的字段：**{sum(1 for item in audit_result.get('columns', []) if item.get('missing', 0))} 个**", f"- IQR 异常值标记：**{quality_profile['outlierCells']:,} 个**"]
        quality += [f"- {item['name']}：缺失 {item['missing']:,} 条（{_format_number(item['missingRate'] * 100, 1)}%）" for item in missing]
        risk_labels = {"missing": "缺失", "outlier": "异常值", "constant": "常量字段"}
        severity_labels = {"high": "高", "medium": "中", "low": "低"}
        risk_lines = ["### 字段级风险登记"] + ([f"- **{severity_labels[item['severity']]}风险 · {item['field']} · {risk_labels[item['kind']]}**：涉及 {item['count']:,} 条（{item['rate'] * 100:.1f}%）。复用前需核对业务含义并确定处理方式。" for item in quality_risks] or ["- 当前规则未发现显著的字段缺失、异常值或常量字段风险。"])
        exploration = [f"- 数值字段：**{len(eda_result.get('numericColumns', []))} 个**", f"- 分类/文本字段：**{len(eda_result.get('categoricalColumns', []))} 个**"]
        for name in roles["numeric"][:3]:
            summary = eda_result.get("numeric", {}).get(name, {})
            exploration.append(f"- {name}：均值 {_format_number(summary.get('mean'))}，中位数 {_format_number(summary.get('median'))}，范围 {_format_number(summary.get('min'))} 至 {_format_number(summary.get('max'))}，偏度 {_format_number(summary.get('skew'), 2)}")
        deep_dive = ["### 分群结果差异"]
        deep_dive += ([f"- **{item['field']}**：{item['highGroup']} 为 {item['highRate'] * 100:.1f}%（n={item['highCount']}），{item['lowGroup']} 为 {item['lowRate'] * 100:.1f}%（n={item['lowCount']}）；相差 **{item['gap'] * 100:.1f} 个百分点**，置信度 {severity_labels[item['confidence']]}。" for item in segment_profiles[:4]] or ["- 当前没有可稳定比较的二元目标分群。"])
        deep_dive += ["", "### 不同结果组的数值差异"]
        deep_dive += ([f"- **{item['field']}**：正向组均值 {_format_number(item['positiveMean'])}，其他组均值 {_format_number(item['otherMean'])}；标准化效应 **d={_format_number(item['effectSize'], 2)}**，置信度 {severity_labels[item['confidence']]}。" for item in numeric_target_profiles[:5]] or ["- 当前没有满足最小样本要求的数值目标组比较。"])
        deep_dive += ["", "### 数值关系排序"]
        deep_dive += ([f"- **{left} ↔ {right}**：r={value:.2f}（{'强' if abs(value) >= strong_correlation_threshold else '中等' if abs(value) >= .4 else '弱'}线性关系；强相关阈值 {strong_correlation_threshold:.2f}）。" for left, right, value in top_correlations] or ["- 可用数值字段少于两个，无法形成关系排序。"])
        stats_lines = ["当前字段结构不足以支持有意义的自动统计比较，建议手工指定变量。"] if not stats_result or stats_result.get("skipped") else [f"- 自动选择方法：**{_method_label(stats_result.get('method', ''), language)}**（{stats_result.get('recommendationReason', 'explicit-method')}）", f"- 适用性状态：**{stats_result.get('status', 'completed')}**", f"- 分析变量：**{' / '.join(stats_result.get('columns', []))}**", f"- 样本量：{_format_number(stats_result.get('sampleSize'), 0)}", f"- 估计值：{_format_number(stats_result.get('estimate'))}（{stats_result.get('estimateLabel', 'effect')}）", f"- {_confidence_text(stats_result, language)}", f"- 统计量：{_format_number(stats_result.get('statistic'))}", f"- p 值：**{_format_number(stats_result.get('pValue'))}**", f"- 效应量：{_format_number(stats_result.get('effectSize'))}", f"- 方法假设：{_assumption_text(stats_result.get('assumptions'), language)}", f"- 替代方法：{'、'.join(stats_result.get('alternatives', [])) or '暂无'}", "- 解释：统计关联本身不能证明因果关系，需要结合研究设计与业务背景判断。"] + _comparison_lines(stats_result, language)
        recommendations += ([f"P0 · 数据负责人 · 处理 { '、'.join(item['name'] for item in missing[:3]) } 的缺失问题；验收标准：记录缺失原因，并对比处理前后结论。"] if missing else ["P2 · 数据负责人 · 保持当前低缺失率基线；验收标准：任一字段缺失率超过 5% 时触发提醒。"])
        if segment_profiles: recommendations.append(f"P1 · 分析人员 · 结合业务定义和潜在混杂因素复核 {segment_profiles[0]['field']} 的分群差异；验收标准：在留出样本或后续时间窗口中复现该差异。")
        if numeric_target_profiles: recommendations.append(f"P1 · 分析人员 · 检验 {numeric_target_profiles[0]['field']} 在多变量模型中是否仍有解释力；验收标准：报告调整后效应和置信区间。")
        recommendations.append("P0 · 业务负责人 · 确认目标、标识、数值和分类字段角色；验收标准：形成已审批的字段角色表后再用于运营决策。")
        limitations = ["- 当前数据集字段角色已经用户确认。" if roles["confirmed"] else "- 自动变量角色识别采用启发式规则，需要结合字段定义复核。", "- 缺失值、选择偏差、测量误差和未观测混杂因素可能影响结论。", "- 用于决策前，应进一步检查方法假设、实际效应和领域背景。"]
        titles = ("执行摘要", "关键发现", "数据质量评估", "探索性发现", "统计证据", "可视化证据", "行动建议", "限制与方法说明", "驱动因素与分群分析", "证据与决策框架")
    evidence_framework = ([
        "### Evidence grading",
        "- **High confidence**: directly computed from the current dataset with adequate group size; still descriptive unless supported by a suitable research design.",
        "- **Medium confidence**: computed evidence with limited sample size, method assumptions, or confounding risk requiring validation.",
        "- **Low confidence**: directional signal only; do not operationalize without more data or domain review.",
        "",
        "### Decision gates",
        "- **Data gate**: field roles approved and material missingness/outliers resolved or explicitly accepted.",
        "- **Evidence gate**: effect size, uncertainty, assumptions, and out-of-sample stability reviewed—not p-value alone.",
        "- **Business gate**: expected value, implementation cost, fairness, reversibility, and monitoring owner documented.",
    ] if language == "en" else [
        "### 证据分级",
        "- **高置信度**：由当前数据直接计算且分组样本相对充足；若缺少合适研究设计，仍只能视为描述性证据。",
        "- **中置信度**：已有量化证据，但受样本量、方法假设或混杂因素限制，需要进一步验证。",
        "- **低置信度**：仅作为方向性信号，不应在缺少补充数据或领域复核时直接执行。",
        "",
        "### 决策门槛",
        "- **数据门槛**：字段角色已获确认，重大缺失和异常值已处理或被明确接受。",
        "- **证据门槛**：同时审阅效应量、不确定性、方法假设和样本外稳定性，而不是只看 p 值。",
        "- **业务门槛**：记录预期价值、实施成本、公平性、可逆性和监控负责人。",
    ])
    finding_lines = []
    for item in findings[:8]:
        finding_lines += [f"### {item['title']}", item["detail"], f"> {'Evidence' if language == 'en' else '证据'}：{item['evidence']}", ""]
    chart_lines: list[str] = []
    reason_labels = {"target-by-category": ("target and category relationship", "目标变量与分类变量的关系"), "meaningful-numeric-distribution": ("meaningful numeric distribution", "有分析意义的数值字段分布"), "meaningful-category-distribution": ("meaningful category distribution", "有分析意义的分类字段分布"), "first-available-field": ("first available field", "首个可用字段")}
    for visualization in visualizations:
        reason = reason_labels.get(visualization.get("selectionReason"), ("automatic field-role inference", "自动字段角色识别"))[0 if language == "en" else 1]
        chart_lines += [f"### {visualization.get('title', '—')}", f"- {'Observation' if language == 'en' else '观察'}: {visualization.get('insight', '—')}", f"- {'Why this chart' if language == 'en' else '选择原因'}: {reason}.", f"- {'Caution' if language == 'en' else '注意'}: {visualization.get('caution', '—')}", ""]
    if not chart_lines: chart_lines = ["No chart is available." if language == "en" else "当前没有可用图表。"]
    return [
        {"id": "executive-summary", "title": titles[0], "markdown": "\n\n".join(executive), "resultIds": result_ids, "chartIds": chart_ids, "audiences": ["management", "full"]},
        {"id": "key-findings", "title": titles[1], "markdown": "\n".join(finding_lines).strip(), "findings": findings[:8], "resultIds": result_ids, "chartIds": chart_ids, "audiences": ["management", "full"]},
        {"id": "data-quality", "title": titles[2], "markdown": "\n".join(quality + [""] + risk_lines), "metrics": quality_profile, "risks": quality_risks, "resultIds": [], "chartIds": [], "audiences": ["full", "technical"]},
        {"id": "exploration", "title": titles[3], "markdown": "\n".join(exploration), "resultIds": [], "chartIds": [], "audiences": ["full", "technical"]},
        {"id": "deep-dive", "title": titles[8], "markdown": "\n".join(deep_dive), "segments": segment_profiles, "numericDrivers": numeric_target_profiles, "correlations": [{"left": left, "right": right, "value": value} for left, right, value in top_correlations], "resultIds": result_ids, "chartIds": chart_ids, "audiences": ["management", "full", "technical"]},
        {"id": "statistics", "title": titles[4], "markdown": "\n".join(stats_lines), "resultIds": result_ids, "chartIds": [], "audiences": ["full", "technical"]},
        {"id": "visualization", "title": titles[5], "markdown": "\n".join(chart_lines).strip(), "resultIds": [], "chartIds": chart_ids, "visualizations": visualizations, "audiences": ["management", "full", "technical"]},
        {"id": "recommendations", "title": titles[6], "markdown": "\n".join(f"- {item}" for item in dict.fromkeys(recommendations)), "resultIds": result_ids, "chartIds": chart_ids, "audiences": ["management", "full"]},
        {"id": "decision-framework", "title": titles[9], "markdown": "\n".join(evidence_framework), "resultIds": result_ids, "chartIds": [], "audiences": ["management", "full", "technical"]},
        {"id": "limitations", "title": titles[7], "markdown": "\n".join(limitations), "resultIds": [], "chartIds": [], "audiences": ["management", "full", "technical"]},
    ]


def execute_plan(
    store: ProjectStore,
    plan_id: str,
    language: str,
    cancellation_requested: Callable[[], bool] | None = None,
    on_progress: Callable[[dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    plan = store.get_plan(plan_id)
    if plan["status"] == "running": raise ValueError("The analysis plan is already running")
    manifest = store.open()
    plan["status"] = "running"
    for step in plan["steps"]:
        step["status"] = "queued"
        step.pop("error", None)
    store.save_plan(plan)
    store.audit("analysis.plan.started", {"planId": plan_id})
    if on_progress:
        on_progress({"type": "progress", "progress": 0, "message": "Plan started", "plan": plan})
    artifacts: list[dict[str, Any]] = []
    current_version_id = plan["steps"][0]["inputVersionIds"][0]
    frame, current_version = load_version(store, current_version_id)
    semantic_profile = store.semantic_profile(current_version_id)

    total_steps = len(plan["steps"])
    for index, step in enumerate(plan["steps"]):
        if cancellation_requested and cancellation_requested():
            for pending in plan["steps"][index:]:
                if pending["status"] in {"queued", "running"}:
                    pending["status"] = "cancelled"
            plan["status"] = "cancelled"
            store.save_plan(plan)
            store.audit("analysis.plan.cancelled", {"planId": plan_id, "completedSteps": index})
            latest = {item["kind"]: item["payload"] for item in artifacts}
            result = {"plan": plan, "artifacts": artifacts, "latest": latest, "activeVersionId": current_version_id, "preview": preview_frame(frame), "cancelled": True}
            if on_progress:
                on_progress({"type": "cancelled", "progress": index / total_steps if total_steps else 0, "message": "Plan cancelled", "plan": plan})
            return result
        started = perf_counter()
        step["status"] = "running"
        step["inputVersionIds"] = [current_version_id]
        step["logs"] = [("Running" if language == "en" else "正在执行") + f" {step['method']}"]
        store.save_plan(plan)
        if on_progress:
            on_progress({"type": "progress", "stepId": step["id"], "progress": index / total_steps if total_steps else 0, "message": step["logs"][0], "plan": plan})
        try:
            method = step["method"]
            parameters = step.get("parameters") or {}
            payload: dict[str, Any]
            kind = method
            if method == "audit":
                payload = audit(frame)
            elif method == "eda":
                payload = eda(frame)
            elif method == "clean":
                operations = parameters.get("operations", [])
                if operations:
                    frame = clean(frame, operations)
                    current_version = save_derived(store, frame, current_version, "plan-clean")
                    current_version_id = current_version["id"]
                    step["outputVersionId"] = current_version_id
                    payload = {"version": current_version, "preview": preview_frame(frame)}
                else:
                    payload = {"skipped": True, "reason": "No cleaning operations were configured"}
            elif method in {"statistical-test", "correlation"}:
                automatic = _automatic_statistics(frame, semantic_profile)
                columns = parameters.get("columns") or (automatic[1] if automatic else [])
                selected_method = parameters.get("method") or ((automatic[0] if automatic else "pearson") if method == "statistical-test" else "pearson")
                analysis_parameters = {"alpha": 0.05, **(automatic[2] if automatic else {}), **parameters}
                payload = statistical_test(frame, selected_method, columns, analysis_parameters) if len(columns) >= 2 else {"skipped": True, "reason": "No meaningful automatic field pair was found"}
                payload["selectionReason"] = analysis_parameters.get("selectionReason")
                kind = "statistics"
            elif method in {"regression", "pca", "clustering"}:
                columns = parameters.get("columns") or _numeric_columns(frame)
                selected_method = parameters.get("method") or {"regression": "linear-regression", "pca": "pca", "clustering": "kmeans"}[method]
                if len(columns) < (2 if method == "regression" else 1): payload = {"skipped": True, "reason": "Not enough numeric fields"}
                else: payload = model(frame, selected_method, columns, parameters)
                kind = "model"
            elif method == "time-series":
                columns = parameters.get("columns", [])
                if len(columns) < 2: payload = {"skipped": True, "reason": "Date and value fields are required"}
                else: payload = time_series(frame, columns[0], columns[1], int(parameters.get("period", 12)))
            elif method == "chart":
                automatic_charts = _automatic_charts(frame, language, semantic_profile)
                if parameters:
                    automatic_charts[0] = {**automatic_charts[0], **{key: value for key, value in parameters.items() if value is not None}}
                report_visualizations = []
                for configuration in automatic_charts:
                    visualization = chart(frame, configuration["kind"], configuration["x"], configuration.get("y"), configuration.get("color"), configuration["title"])
                    observation, caution = _chart_narrative(frame, configuration, language)
                    visualization.update({"datasetVersionId": current_version_id, "selectionReason": configuration["selectionReason"], "x": configuration["x"], "color": configuration.get("color"), "insight": observation, "caution": caution})
                    report_visualizations.append(visualization)
                payload = {**report_visualizations[0], "reportVisualizations": report_visualizations}
            elif method == "report":
                sections = _report_sections(language, plan.get("goal", ""), frame, artifacts, semantic_profile)
                payload = build_report(f"{manifest['name']} Report" if language == "en" else f"{manifest['name']}报告", sections, language, current_version_id, plan_id)
                payload["semanticProfile"] = semantic_profile
                payload["markdown"] = "\n\n".join(f"## {section['title']}\n\n{section['markdown']}" for section in sections)
            else:
                raise ValueError(f"Plan method is not executable yet: {method}")
            artifact = _artifact(plan_id, step["id"], kind, current_version_id, payload)
            store.add_artifact(artifact); artifacts.append(artifact)
            step["artifactIds"] = [artifact["id"]]
            step["status"] = "completed"
            step["logs"].append("Completed" if language == "en" else "执行完成")
        except Exception as error:
            diagnostic = sanitize_diagnostic(error)
            step["status"] = "failed"
            step["error"] = diagnostic
            step["logs"].append(diagnostic)
            step["durationMs"] = round((perf_counter() - started) * 1000)
            plan["status"] = "failed"
            store.save_plan(plan)
            store.audit("analysis.plan.failed", {"planId": plan_id, "stepId": step["id"], "error": diagnostic})
            latest = {item["kind"]: item["payload"] for item in artifacts}
            result = {"plan": plan, "artifacts": artifacts, "latest": latest, "activeVersionId": current_version_id, "preview": preview_frame(frame), "error": diagnostic}
            if on_progress:
                on_progress({"type": "error", "stepId": step["id"], "progress": index / total_steps if total_steps else 0, "message": diagnostic, "plan": plan})
            return result
        step["durationMs"] = round((perf_counter() - started) * 1000)
        store.save_plan(plan)
        if on_progress:
            on_progress({"type": "progress", "stepId": step["id"], "progress": (index + 1) / total_steps if total_steps else 1, "message": step["logs"][-1], "plan": plan})

    plan["status"] = "completed"
    store.save_plan(plan)
    store.audit("analysis.plan.completed", {"planId": plan_id, "artifactIds": [item["id"] for item in artifacts]})
    latest = {item["kind"]: item["payload"] for item in artifacts}
    result = {"plan": plan, "artifacts": artifacts, "latest": latest, "activeVersionId": current_version_id, "preview": preview_frame(frame)}
    if on_progress:
        on_progress({"type": "completed", "progress": 1, "message": "Plan completed", "plan": plan})
    return result
