from __future__ import annotations

import math
from typing import Any

import numpy as np
import pandas as pd
import plotly.express as px
from scipy import stats
from sklearn.cluster import AgglomerativeClustering, KMeans
from sklearn.decomposition import PCA
from sklearn.preprocessing import StandardScaler
import statsmodels.api as sm
from statsmodels.stats.multitest import multipletests
from statsmodels.tsa.seasonal import seasonal_decompose

from .datasets import schema_for
from .models import new_id


def json_value(value: Any) -> Any:
    if isinstance(value, dict): return {str(key): json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)): return [json_value(item) for item in value]
    if isinstance(value, (np.integer,)): return int(value)
    if isinstance(value, (np.floating,)): return None if not np.isfinite(value) else float(value)
    if isinstance(value, np.ndarray): return [json_value(item) for item in value]
    if isinstance(value, pd.Timestamp): return value.isoformat()
    if value is None or pd.isna(value): return None
    return value


def audit(frame: pd.DataFrame) -> dict[str, Any]:
    columns = []
    for name in frame.columns:
        series = frame[name]
        numeric = pd.to_numeric(series, errors="coerce") if not pd.api.types.is_numeric_dtype(series) else series
        q1, q3 = (numeric.quantile(0.25), numeric.quantile(0.75)) if numeric.notna().any() else (np.nan, np.nan)
        iqr = q3 - q1
        outliers = int(((numeric < q1 - 1.5 * iqr) | (numeric > q3 + 1.5 * iqr)).sum()) if pd.notna(iqr) else 0
        columns.append({
            "name": str(name), "dtype": str(series.dtype), "missing": int(series.isna().sum()),
            "missingRate": float(series.isna().mean()) if len(series) else 0.0,
            "unique": int(series.nunique(dropna=True)), "constant": bool(series.nunique(dropna=True) <= 1),
            "outliersIqr": outliers,
            "min": json_value(numeric.min()) if numeric.notna().any() else None,
            "max": json_value(numeric.max()) if numeric.notna().any() else None,
        })
    warnings = []
    if frame.empty: warnings.append("数据集为空")
    if frame.duplicated().any(): warnings.append(f"发现 {int(frame.duplicated().sum())} 行重复记录")
    if any(column["missingRate"] > 0.5 for column in columns): warnings.append("部分字段缺失率超过 50%")
    return {
        "rowCount": len(frame), "columnCount": len(frame.columns), "duplicateRows": int(frame.duplicated().sum()),
        "memoryBytes": int(frame.memory_usage(deep=True).sum()), "schema": schema_for(frame),
        "columns": columns, "warnings": warnings,
    }


def eda(frame: pd.DataFrame) -> dict[str, Any]:
    """Return a compact, JSON-safe exploratory profile suitable for UI and reports."""
    numeric_columns = [str(name) for name in frame.select_dtypes(include=[np.number]).columns]
    categorical_columns = [str(name) for name in frame.columns if str(name) not in numeric_columns]
    numeric: dict[str, Any] = {}
    for name in numeric_columns:
        series = pd.to_numeric(frame[name], errors="coerce").dropna()
        numeric[name] = {
            "count": int(series.count()),
            "mean": json_value(series.mean()),
            "std": json_value(series.std()),
            "min": json_value(series.min()),
            "q25": json_value(series.quantile(0.25)),
            "median": json_value(series.median()),
            "q75": json_value(series.quantile(0.75)),
            "max": json_value(series.max()),
            "skew": json_value(series.skew()),
        }
    categorical: dict[str, Any] = {}
    for name in categorical_columns:
        series = frame[name]
        counts = series.dropna().astype(str).value_counts().head(10)
        categorical[name] = {
            "count": int(series.notna().sum()),
            "unique": int(series.nunique(dropna=True)),
            "topValues": [{"value": str(value), "count": int(count)} for value, count in counts.items()],
        }
    correlation = frame[numeric_columns].corr().round(6).replace({np.nan: None}).to_dict() if numeric_columns else {}
    return {
        "id": new_id("eda"),
        "rowCount": len(frame),
        "columnCount": len(frame.columns),
        "numericColumns": numeric_columns,
        "categoricalColumns": categorical_columns,
        "numeric": numeric,
        "categorical": categorical,
        "correlation": json_value(correlation),
    }


def clean(frame: pd.DataFrame, operations: list[dict[str, Any]]) -> pd.DataFrame:
    result = frame.copy()
    for operation in operations:
        kind = operation.get("kind")
        columns = operation.get("columns", [])
        if kind == "drop_duplicates": result = result.drop_duplicates(subset=columns or None)
        elif kind == "drop_missing": result = result.dropna(subset=columns or None)
        elif kind == "fill_missing":
            strategy, value = operation.get("strategy", "value"), operation.get("value")
            for column in columns:
                if strategy == "mean": value = pd.to_numeric(result[column], errors="coerce").mean()
                elif strategy == "median": value = pd.to_numeric(result[column], errors="coerce").median()
                elif strategy == "mode": value = result[column].mode(dropna=True).iloc[0] if not result[column].mode(dropna=True).empty else None
                result[column] = result[column].fillna(value)
        elif kind == "cast":
            dtype = operation["dtype"]
            for column in columns:
                if dtype == "datetime": result[column] = pd.to_datetime(result[column], errors="coerce")
                elif dtype == "numeric": result[column] = pd.to_numeric(result[column], errors="coerce")
                else: result[column] = result[column].astype(dtype)
        elif kind == "normalize_text":
            for column in columns: result[column] = result[column].astype("string").str.strip().str.replace(r"\s+", " ", regex=True)
        elif kind == "rename": result = result.rename(columns=operation.get("mapping", {}))
        elif kind == "filter": result = result.query(operation["expression"], engine="python")
        elif kind == "clip_outliers":
            for column in columns:
                values = pd.to_numeric(result[column], errors="coerce")
                q1, q3 = values.quantile([0.25, 0.75]); iqr = q3 - q1
                result[column] = values.clip(q1 - 1.5 * iqr, q3 + 1.5 * iqr)
        else: raise ValueError(f"Unsupported cleaning operation: {kind}")
    return result.reset_index(drop=True)


def _cohen_d(left: np.ndarray, right: np.ndarray) -> float | None:
    n1, n2 = len(left), len(right)
    if n1 < 2 or n2 < 2: return None
    pooled = math.sqrt(((n1 - 1) * left.var(ddof=1) + (n2 - 1) * right.var(ddof=1)) / (n1 + n2 - 2))
    return float((left.mean() - right.mean()) / pooled) if pooled else None


def statistical_test(frame: pd.DataFrame, method: str, columns: list[str], parameters: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {"id": new_id("stat"), "method": method, "columns": columns, "diagnostics": [], "assumptions": {}}
    samples = [pd.to_numeric(frame[column], errors="coerce").dropna().to_numpy() for column in columns]
    alternative = parameters.get("alternative", "two-sided")
    if method in {"t-test", "welch"}:
        equal = method == "t-test"
        statistic, p = stats.ttest_ind(samples[0], samples[1], equal_var=equal, alternative=alternative)
        result.update(statistic=statistic, pValue=p, effectSize=_cohen_d(samples[0], samples[1]), sampleSize={columns[0]: len(samples[0]), columns[1]: len(samples[1])})
    elif method == "paired-t":
        paired = frame[columns].apply(pd.to_numeric, errors="coerce").dropna()
        statistic, p = stats.ttest_rel(paired.iloc[:, 0], paired.iloc[:, 1], alternative=alternative)
        diff = paired.iloc[:, 0] - paired.iloc[:, 1]
        result.update(statistic=statistic, pValue=p, effectSize=float(diff.mean() / diff.std(ddof=1)), sampleSize=len(paired))
    elif method == "mann-whitney":
        statistic, p = stats.mannwhitneyu(samples[0], samples[1], alternative=alternative)
        result.update(statistic=statistic, pValue=p, sampleSize={columns[0]: len(samples[0]), columns[1]: len(samples[1])})
    elif method == "wilcoxon":
        paired = frame[columns].apply(pd.to_numeric, errors="coerce").dropna()
        statistic, p = stats.wilcoxon(paired.iloc[:, 0], paired.iloc[:, 1], alternative=alternative)
        result.update(statistic=statistic, pValue=p, sampleSize=len(paired))
    elif method in {"pearson", "spearman", "kendall"}:
        paired = frame[columns].apply(pd.to_numeric, errors="coerce").dropna()
        function = {"pearson": stats.pearsonr, "spearman": stats.spearmanr, "kendall": stats.kendalltau}[method]
        statistic, p = function(paired.iloc[:, 0], paired.iloc[:, 1])
        result.update(statistic=statistic, pValue=p, effectSize=statistic, sampleSize=len(paired))
    elif method in {"anova", "kruskal"}:
        function = stats.f_oneway if method == "anova" else stats.kruskal
        statistic, p = function(*samples)
        result.update(statistic=statistic, pValue=p, sampleSize={column: len(sample) for column, sample in zip(columns, samples)})
    elif method == "normality":
        sample = samples[0]
        statistic, p = stats.shapiro(sample[:5000])
        result.update(statistic=statistic, pValue=p, sampleSize=len(sample), diagnostics=["Shapiro-Wilk 使用最多前 5000 个有效观测"])
    elif method in {"chi-square", "fisher"}:
        table = pd.crosstab(frame[columns[0]], frame[columns[1]])
        if method == "fisher": statistic, p = stats.fisher_exact(table.to_numpy())
        else:
            statistic, p, _, expected = stats.chi2_contingency(table)
            result["assumptions"] = {"minimumExpectedCount": float(expected.min())}
        total = int(table.to_numpy().sum())
        denominator = total * max(1, min(table.shape[0] - 1, table.shape[1] - 1))
        effect_size = math.sqrt(float(statistic) / denominator) if method == "chi-square" and denominator else None
        result.update(
            statistic=statistic, pValue=p, effectSize=effect_size, sampleSize=total,
            contingency={str(index): {str(key): int(value) for key, value in row.items()} for index, row in table.to_dict(orient="index").items()},
        )
    else: raise ValueError(f"Unsupported statistical method: {method}")
    p_value = result.get("pValue")
    result["interpretation"] = "结果具有统计显著性" if p_value is not None and p_value < parameters.get("alpha", 0.05) else "未发现统计显著性"
    return {key: json_value(value) for key, value in result.items()}


def model(frame: pd.DataFrame, method: str, columns: list[str], parameters: dict[str, Any]) -> dict[str, Any]:
    clean_frame = frame[columns].apply(pd.to_numeric, errors="coerce").dropna()
    if method in {"linear-regression", "logistic-regression"}:
        y = clean_frame[columns[0]]; x = sm.add_constant(clean_frame[columns[1:]])
        fitted = (sm.OLS(y, x) if method == "linear-regression" else sm.Logit(y, x)).fit(disp=False)
        return {"method": method, "sampleSize": len(clean_frame), "coefficients": {str(k): float(v) for k, v in fitted.params.items()}, "pValues": {str(k): float(v) for k, v in fitted.pvalues.items()}, "rSquared": float(getattr(fitted, "rsquared", np.nan)) if method == "linear-regression" else float(fitted.prsquared)}
    values = StandardScaler().fit_transform(clean_frame)
    if method == "pca":
        estimator = PCA(n_components=parameters.get("components", min(2, len(columns)))).fit(values)
        return {"method": method, "sampleSize": len(clean_frame), "explainedVarianceRatio": estimator.explained_variance_ratio_.tolist(), "components": estimator.components_.tolist()}
    clusters = int(parameters.get("clusters", 3))
    estimator = KMeans(n_clusters=clusters, random_state=42, n_init="auto") if method == "kmeans" else AgglomerativeClustering(n_clusters=clusters)
    labels = estimator.fit_predict(values)
    return {"method": method, "sampleSize": len(clean_frame), "clusters": clusters, "counts": pd.Series(labels).value_counts().sort_index().to_dict(), "labels": labels.tolist()}


def time_series(frame: pd.DataFrame, date_column: str, value_column: str, period: int) -> dict[str, Any]:
    series_frame = frame[[date_column, value_column]].copy()
    series_frame[date_column] = pd.to_datetime(series_frame[date_column], errors="coerce")
    series_frame[value_column] = pd.to_numeric(series_frame[value_column], errors="coerce")
    series = series_frame.dropna().sort_values(date_column).set_index(date_column)[value_column]
    decomposition = seasonal_decompose(series, model="additive", period=period, extrapolate_trend="freq")
    return {"sampleSize": len(series), "period": period, "dates": [item.isoformat() for item in series.index], "observed": [json_value(v) for v in decomposition.observed], "trend": [json_value(v) for v in decomposition.trend], "seasonal": [json_value(v) for v in decomposition.seasonal], "autocorrelation": [json_value(series.autocorr(lag)) for lag in range(1, min(period + 1, len(series)))]}


def adjust_p_values(values: list[float], method: str = "fdr_bh") -> list[float]:
    return multipletests(values, method=method)[1].tolist()


def chart(frame: pd.DataFrame, kind: str, x: str, y: str | None, color: str | None, title: str | None) -> dict[str, Any]:
    functions = {"histogram": px.histogram, "scatter": px.scatter, "box": px.box, "bar": px.bar, "line": px.line, "violin": px.violin}
    if kind not in functions: raise ValueError(f"Unsupported chart type: {kind}")
    figure = functions[kind](frame, x=x, y=y, color=color, title=title or f"{kind}: {x}")
    payload = figure.to_plotly_json()
    return {"id": new_id("chart"), "title": title or f"{kind}: {x}", "plotly": {"data": payload["data"], "layout": payload["layout"], "config": {"responsive": True, "displaylogo": False}}, "filters": {}}
