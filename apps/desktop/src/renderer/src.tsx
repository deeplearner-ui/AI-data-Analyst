import React, { createContext, useContext, useEffect, useMemo, useState } from "react";
import { createRoot } from "react-dom/client";
import Editor from "@monaco-editor/react";
import Plot from "react-plotly.js";
import ReactMarkdown from "react-markdown";
import type { AnalysisPlan, ChartArtifact, DataPreview, EdaResult, PlanTask, ProjectManifest, SemanticProfile, StatisticalResult, StepStatus } from "@aida/contracts";
import "./styles.css";
import "./language.css";
import "./workflow.css";
import { defaultGoal, defaultReport, translate, translateBackendMessage, type Locale, type MessageKey } from "./i18n";

type Tab = "data" | "clean" | "audit" | "eda" | "statistics" | "code" | "chart" | "report" | "database";
type JsonMap = Record<string, any>;
type ReportTemplate = "management" | "full" | "technical";

const api = <T,>(path: string, body?: unknown, method = body === undefined ? "GET" : "POST") =>
  window.aida.sidecarRequest<T>(path, { method, body });

const stepStatusKey: Record<StepStatus, MessageKey> = {
  draft: "statusDraft", queued: "statusQueued", running: "statusRunning", completed: "statusCompleted",
  failed: "statusFailed", cancelled: "statusCancelled", stale: "statusStale"
};

type I18nValue = { locale: Locale; setLocale: (locale: Locale) => void; t: (key: MessageKey) => string };
const I18nContext = createContext<I18nValue | null>(null);
const useI18n = () => useContext(I18nContext)!;

function App() {
  const [locale, setLocale] = useState<Locale>(() => localStorage.getItem("aida-locale") === "en" ? "en" : "zh-CN");
  const value = useMemo<I18nValue>(() => ({ locale, setLocale, t: (key) => translate(locale, key) }), [locale]);
  return <I18nContext.Provider value={value}><AppContent /></I18nContext.Provider>;
}

function AppContent() {
  const { locale, setLocale, t } = useI18n();
  const [projectDirectory, setProjectDirectory] = useState("");
  const [project, setProject] = useState<ProjectManifest | null>(null);
  const [preview, setPreview] = useState<DataPreview | null>(null);
  const [activeVersionId, setActiveVersionId] = useState("");
  const [audit, setAudit] = useState<JsonMap | null>(null);
  const [cleanPreview, setCleanPreview] = useState<JsonMap | null>(null);
  const [edaResult, setEdaResult] = useState<EdaResult | null>(null);
  const [plan, setPlan] = useState<AnalysisPlan | null>(null);
  const [planTask, setPlanTask] = useState<PlanTask | null>(null);
  const [statResult, setStatResult] = useState<StatisticalResult | null>(null);
  const [chart, setChart] = useState<ChartArtifact | null>(null);
  const [tab, setTab] = useState<Tab>("data");
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [logs, setLogs] = useState<string[]>([]);
  const [goal, setGoal] = useState(() => defaultGoal(locale));
  const [includeSamples, setIncludeSamples] = useState(true);
  const [code, setCode] = useState("import numpy as np\n\nresult = {\"mean\": float(np.mean([1, 2, 3]))}");
  const [codeResult, setCodeResult] = useState<JsonMap | null>(null);
  const [reportMarkdown, setReportMarkdown] = useState(() => defaultReport(locale));
  const [reportDocument, setReportDocument] = useState<JsonMap | null>(null);
  const [lastExport, setLastExport] = useState("");
  const [semanticProfile, setSemanticProfile] = useState<SemanticProfile | null>(null);

  const columns = preview?.columns ?? [];
  const numericColumns = useMemo(() => columns.filter((item) => item.semanticType === "numeric").map((item) => item.name), [columns]);

  function changeLocale(nextLocale: Locale) {
    if (nextLocale === locale) return;
    if (goal === defaultGoal(locale)) setGoal(defaultGoal(nextLocale));
    if (reportMarkdown === defaultReport(locale)) setReportMarkdown(defaultReport(nextLocale));
    localStorage.setItem("aida-locale", nextLocale);
    document.documentElement.lang = nextLocale;
    setLocale(nextLocale);
  }

  function applyWorkflowOutputs(latest: JsonMap) {
    if (latest.audit) setAudit(latest.audit);
    if (latest.eda) setEdaResult(latest.eda);
    if (latest.statistics && !latest.statistics.skipped) setStatResult(latest.statistics);
    if (latest.chart) setChart(latest.chart);
    if (latest.report?.markdown) { setReportMarkdown(latest.report.markdown); setReportDocument(latest.report); }
  }

  useEffect(() => {
    if (!planTask || !["queued", "running", "cancelling"].includes(planTask.status)) return;
    let disposed = false;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const poll = async () => {
      try {
        const response = await api<{ task: PlanTask }>("/api/analysis/plans/tasks/status", { projectDirectory, taskId: planTask.id });
        if (disposed) return;
        const task = response.task;
        setPlanTask(task); setPlan(task.plan);
        if (["completed", "failed", "cancelled"].includes(task.status)) {
          const result = (task.result ?? {}) as JsonMap;
          if (result.activeVersionId) setActiveVersionId(result.activeVersionId);
          if (result.preview) setPreview(result.preview);
          applyWorkflowOutputs(result.latest ?? {});
          if (task.error || result.error) setError(task.error ?? result.error);
          else if (task.status === "completed") setTab(result.latest?.eda ? "eda" : result.latest?.audit ? "audit" : "data");
          setLogs((current) => [`${new Date().toLocaleTimeString()} · ${task.message}`, ...current]);
          return;
        }
        timer = setTimeout(poll, 400);
      } catch (caught) {
        if (!disposed) {
          setError(caught instanceof Error ? caught.message : String(caught));
          setPlanTask(null);
        }
      }
    };
    timer = setTimeout(poll, 150);
    return () => { disposed = true; if (timer) clearTimeout(timer); };
  }, [planTask?.id, planTask?.status, projectDirectory]);

  async function action<T>(label: string, operation: () => Promise<T>): Promise<T | undefined> {
    setBusy(label); setError(""); setLogs((current) => [`${new Date().toLocaleTimeString()} · ${label}`, ...current]);
    try { return await operation(); }
    catch (caught) { setError(caught instanceof Error ? caught.message : String(caught)); }
    finally { setBusy(""); }
  }

  async function createProject() {
    const directory = await action(t("selectProjectDirectory"), () => window.aida.selectProjectDirectory());
    if (!directory) return;
    const manifest = await action(t("createProjectAction"), () => api<ProjectManifest>("/api/projects", { directory, name: t("defaultProjectName"), language: locale }));
    if (manifest) {
      setProjectDirectory(directory); setProject(manifest); setActiveVersionId(""); setPreview(null); setSemanticProfile(null);
      setPlan(null); setPlanTask(null); setReportDocument(null); setTab("data");
    }
  }

  async function openProject() {
    const directory = await action(t("selectProjectDirectory"), () => window.aida.selectProjectDirectory());
    if (!directory) return;
    const manifest = await action(t("openProjectAction"), () => api<ProjectManifest>("/api/projects/open", { directory }));
    if (manifest) {
      setProjectDirectory(directory); setProject(manifest); setPlanTask(null); setPreview(null); setSemanticProfile(null);
      const latest = manifest.datasets.at(-1)?.currentVersionId;
      if (latest) { setActiveVersionId(latest); void loadPreview(directory, latest); void loadSemantics(directory, latest); }
      else setActiveVersionId("");
      const workflow = await api<JsonMap>("/api/analysis/plans/latest", { projectDirectory: directory });
      if (workflow.plan) {
        setPlan(workflow.plan);
        applyWorkflowOutputs(Object.fromEntries(workflow.artifacts.map((artifact: JsonMap) => [artifact.kind, artifact.payload])));
      }
    }
  }

  async function loadPreview(directory = projectDirectory, versionId = activeVersionId) {
    const result = await action(t("readPreview"), () => api<DataPreview>("/api/datasets/preview", { projectDirectory: directory, versionId }));
    if (result) setPreview(result);
  }

  async function loadSemantics(directory = projectDirectory, versionId = activeVersionId) {
    const result = await action(t("loadSemanticsAction"), () => api<{ profile: SemanticProfile }>("/api/analysis/semantics/get", { projectDirectory: directory, versionId }));
    if (result) setSemanticProfile(result.profile);
  }

  async function saveSemantics(profile: SemanticProfile) {
    const result = await action(t("saveSemanticsAction"), () => api<{ profile: SemanticProfile }>("/api/analysis/semantics/save", { projectDirectory, versionId: activeVersionId, ...profile }));
    if (result) setSemanticProfile(result.profile);
  }

  function selectDataset(versionId: string) {
    setActiveVersionId(versionId); setCleanPreview(null); setAudit(null); setEdaResult(null); setPlan(null); setPlanTask(null); setStatResult(null); setChart(null);
    setReportMarkdown(defaultReport(locale)); setReportDocument(null); setSemanticProfile(null); setTab("data"); void loadPreview(projectDirectory, versionId); void loadSemantics(projectDirectory, versionId);
  }

  async function importData() {
    const path = await action(t("selectDataFile"), () => window.aida.selectDataFile());
    if (!path || !projectDirectory) return;
    const result = await action(t("importDataAction"), () => api<JsonMap>("/api/datasets/import", { projectDirectory, path }));
    if (result) {
      setPreview(result.preview); setActiveVersionId(result.version.id);
      setAudit(null); setCleanPreview(null); setEdaResult(null); setPlan(null); setPlanTask(null); setStatResult(null); setChart(null); setReportDocument(null); setReportMarkdown(defaultReport(locale));
      const manifest = await api<ProjectManifest>("/api/projects/open", { directory: projectDirectory }); setProject(manifest); setTab("data"); void loadSemantics(projectDirectory, result.version.id);
    }
  }

  async function runAudit() {
    const result = await action(t("runAuditAction"), () => api<JsonMap>("/api/analysis/audit", { projectDirectory, versionId: activeVersionId }));
    if (result) { setAudit(result.audit); setTab("audit"); }
  }

  async function runEda() {
    const result = await action(t("runEdaAction"), () => api<JsonMap>("/api/analysis/eda", { projectDirectory, versionId: activeVersionId }));
    if (result) { setEdaResult(result.eda); setTab("eda"); }
  }

  async function previewCleaning(operations: JsonMap[]) {
    const result = await action(t("cleaningPreviewAction"), () => api<JsonMap>("/api/analysis/clean/preview", { projectDirectory, versionId: activeVersionId, operations }));
    if (result) setCleanPreview(result);
  }

  async function applyCleaning(operations: JsonMap[]) {
    const result = await action(t("cleaningApplyAction"), () => api<JsonMap>("/api/analysis/clean", { projectDirectory, versionId: activeVersionId, operations }));
    if (!result) return;
    setActiveVersionId(result.version.id); setPreview(result.preview);
    if (!result.unchanged) {
      setAudit(null); setEdaResult(null); setPlan(null); setPlanTask(null); setStatResult(null); setChart(null); setCleanPreview(null);
      setReportMarkdown(defaultReport(locale)); setReportDocument(null);
      const manifest = await api<ProjectManifest>("/api/projects/open", { directory: projectDirectory }); setProject(manifest);
      setTab("data");
    }
  }

  async function createPlan() {
    const result = await action(t("generatePlanAction"), () => api<JsonMap>("/api/ai/plan", { projectDirectory, versionId: activeVersionId, goal, includeSamples, language: locale }));
    if (result) setPlan(result.plan);
  }

  async function executeCurrentPlan() {
    if (!plan) return;
    setPlan({ ...plan, status: "running", steps: plan.steps.map((step) => ({ ...step, status: "queued" })) });
    const response = await action(t("executePlanAction"), () => api<{ task: PlanTask }>("/api/analysis/plans/tasks/start", { projectDirectory, planId: plan.id, language: locale }));
    if (response) setPlanTask(response.task);
  }

  async function cancelCurrentPlan() {
    if (!planTask || !["queued", "running"].includes(planTask.status)) return;
    const response = await action(t("cancelPlanAction"), () => api<{ task: PlanTask }>("/api/analysis/plans/tasks/cancel", { projectDirectory, taskId: planTask.id }));
    if (response) setPlanTask(response.task);
  }

  async function runStats(method: string, selectedColumns: string[], parameters: JsonMap) {
    const validCount = method === "auto" ? selectedColumns.length >= 1 : method === "normality" ? selectedColumns.length === 1 : ["anova", "kruskal"].includes(method) ? selectedColumns.length >= 2 : selectedColumns.length === 2;
    if (!validCount) { setError(t("needTwoNumeric")); return; }
    const result = await action(t("runWelchAction"), () => api<StatisticalResult>("/api/analysis/statistics", { projectDirectory, versionId: activeVersionId, method, columns: selectedColumns, parameters }));
    if (result) { setStatResult(result); setTab("statistics"); }
  }

  async function createChart() {
    const x = numericColumns[0] ?? columns[0]?.name;
    if (!x) return;
    const result = await action(t("createChartAction"), () => api<ChartArtifact>("/api/analysis/chart", { projectDirectory, versionId: activeVersionId, kind: numericColumns.length ? "histogram" : "bar", x, title: `${x} ${t("distribution")}` }));
    if (result) { setChart(result); setTab("chart"); }
  }

  async function runCode() {
    const result = await action(t("runCodeAction"), () => api<JsonMap>("/api/analysis/python/execute", { projectDirectory, code, timeoutSeconds: 30 }));
    if (result) setCodeResult(result);
  }

  function reportSections() {
    if (reportDocument?.sections?.length) return reportDocument.sections;
    return [{ id: "summary", title: locale === "zh-CN" ? "分析摘要" : "Analysis summary", markdown: reportMarkdown, resultIds: statResult ? [statResult.id] : [], chartIds: chart ? [chart.id] : [], visualizations: chart ? [chart] : [] }];
  }

  function editReport(value: string) { setReportMarkdown(value); setReportDocument(null); }

  async function saveBinaryExport(label: string, operation: () => Promise<JsonMap>) {
    const saved = await action(label, async () => {
      const result = await operation();
      const path = await window.aida.saveExport(result.filename, result.contentBase64, "base64");
      return path ? { path, bytes: result.bytes } : null;
    });
    if (saved) {
      const filename = saved.path.split(/[\/]/).at(-1) ?? t("exportCompleted");
      setLastExport(`${filename} · ${(saved.bytes / 1024).toFixed(1)} KB`);
      setLogs((current) => [`${new Date().toLocaleTimeString()} · ${t("exportCompleted")}: ${filename}`, ...current]);
    }
  }

  function privacyAcknowledgement(required = true): boolean | null {
    if (!required || !preview?.privacy?.hasPersonalData) return false;
    return window.confirm(t("privacyExportConfirm")) ? true : null;
  }

  async function exportDataset(format: "csv" | "xlsx") {
    const acknowledgePersonalData = privacyAcknowledgement();
    if (acknowledgePersonalData === null) return;
    await saveBinaryExport(t("exportDatasetAction"), () => api<JsonMap>("/api/datasets/export", { projectDirectory, versionId: activeVersionId, format, acknowledgePersonalData }));
  }

  async function exportFormattedReport(format: "html" | "pdf", sections: JsonMap[], template: ReportTemplate) {
    const acknowledgePersonalData = privacyAcknowledgement();
    if (acknowledgePersonalData === null) return;
    await saveBinaryExport(t("buildReportAction"), () => api<JsonMap>("/api/reports/export", { projectDirectory, title: `${project?.name ?? t("defaultReportName")}${t("reportSuffix")}`, sections, language: locale, template, format, versionId: activeVersionId, planId: plan?.id, acknowledgePersonalData }));
  }

  async function exportReproducibility(includeData: boolean, dataFormat: "csv" | "xlsx", sections: JsonMap[], template: ReportTemplate) {
    const acknowledgePersonalData = privacyAcknowledgement(includeData);
    if (acknowledgePersonalData === null) return;
    await saveBinaryExport(t("exportBundleAction"), () => api<JsonMap>("/api/reports/reproducibility", { projectDirectory, title: `${project?.name ?? t("defaultReportName")}${t("reportSuffix")}`, sections, language: locale, template, versionId: activeVersionId, planId: plan?.id, includeData, dataFormat, acknowledgePersonalData }));
  }

  if (!project) return <Welcome busy={busy} error={error} onCreate={createProject} onOpen={openProject} locale={locale} onLocaleChange={changeLocale} />;

  return <div className="app-shell">
    <header className="topbar">
      <div className="brand"><span className="brand-mark">A</span><div><strong>AI Data Analyst</strong><small>{project.name}</small></div><LanguageToggle locale={locale} onChange={changeLocale} /></div>
      <div className="project-meta"><span className="status-dot" />{t("localServiceConnected")} <span className="divider" /> {t("version")} {activeVersionId ? activeVersionId.slice(-8) : "—"}</div>
      <div className="top-actions"><button className="ghost" onClick={openProject}>{t("openProject")}</button><button className="primary" onClick={importData}>{t("importData")}</button></div>
    </header>

    <aside className="left-panel">
      <SectionLabel text={t("datasets")} action="＋" onAction={importData} />
      <div className="dataset-list">{project.datasets.map((dataset) => <button key={dataset.id} className={`dataset-item ${activeVersionId === dataset.currentVersionId ? "active" : ""}`} onClick={() => selectDataset(dataset.currentVersionId)}><span className="dataset-icon">▦</span><span><strong>{dataset.name}</strong><small>{dataset.sourceKind.toUpperCase()} · {dataset.sourceLabel}</small></span></button>)}</div>
      <SectionLabel text={t("analysisSteps")} />
      <div className="step-list">{plan?.steps.map((step, index) => <div className="step" key={step.id}><span>{index + 1}</span><div><strong>{step.title}</strong><small>{step.method}</small></div><i className={step.status} /></div>) ?? <p className="empty-hint">{t("planHint")}</p>}</div>
      <div className="lineage"><strong>{t("nondestructiveVersions")}</strong><p>{t("lineageHint")}</p></div>
    </aside>

    <main className="workspace">
      <nav className="tabs">{(["data", "clean", "audit", "eda", "statistics", "code", "chart", "report", "database"] as Tab[]).map((item) => <button key={item} onClick={() => setTab(item)} className={tab === item ? "active" : ""}>{({ data: t("dataPreview"), clean: t("cleaning"), audit: t("dataAudit"), eda: t("eda"), statistics: t("statistics"), code: t("code"), chart: t("charts"), report: t("report"), database: t("database") } as Record<Tab, string>)[item]}</button>)}</nav>
      {error && <div className="error-banner"><strong>{t("operationFailed")}</strong><span>{error}</span><button onClick={() => setError("")}>×</button></div>}
      {busy && <div className="busy-line"><span />{busy}…</div>}
      <div className="canvas">
        {tab === "data" && <DataTab preview={preview} onAudit={runAudit} onClean={() => setTab("clean")} />}
        {tab === "clean" && <CleanTab preview={preview} impact={cleanPreview} busy={!!busy} onPreview={previewCleaning} onApply={applyCleaning} />}
        {tab === "audit" && <AuditTab report={audit} onRun={runAudit} />}
        {tab === "eda" && <EdaTab result={edaResult} onRun={runEda} />}
        {tab === "statistics" && <StatsTab result={statResult} columns={columns} profile={semanticProfile} busy={!!busy} onRun={runStats} />}
        {tab === "code" && <CodeTab code={code} setCode={setCode} result={codeResult} onRun={runCode} />}
        {tab === "chart" && <ChartTab artifact={chart} onCreate={createChart} />}
        {tab === "report" && <ReportTab markdown={reportMarkdown} setMarkdown={editReport} sections={reportSections()} structured={!!reportDocument?.sections?.length} busy={!!busy} activeVersionId={activeVersionId} lastExport={lastExport} onExportDataset={exportDataset} onExportReport={exportFormattedReport} onExportBundle={exportReproducibility} />}
        {tab === "database" && <DatabaseTab projectDirectory={projectDirectory} setError={setError} />}
      </div>
      <footer className="logbar"><span>{t("runLog")}</span><code>{logs[0] ?? t("waiting")}</code><span>{preview ? `${preview.rowCount.toLocaleString()} ${t("rows")} × ${preview.columns.length} ${t("columns")}` : t("noData")}</span></footer>
    </main>

    <aside className="ai-panel">
      <div className="ai-heading"><span>✦</span><div><strong>{t("assistant")}</strong><small>{t("assistantTagline")}</small></div></div>
      <div className="assistant-note">{t("assistantNote")}</div>
      {preview && semanticProfile && <SemanticProfilePanel profile={semanticProfile} columns={columns} busy={!!busy} onSave={saveSemantics} />}
      <label className="field-label">{t("analysisGoal")}</label>
      <textarea value={goal} onChange={(event) => setGoal(event.target.value)} rows={7} />
      <label className="toggle"><input type="checkbox" checked={includeSamples} onChange={(event) => setIncludeSamples(event.target.checked)} /><span />{t("includeSamples")}</label>
      <button className="primary wide" disabled={!activeVersionId || !!busy || !semanticProfile?.confirmed} onClick={createPlan}>{t("generatePlan")}</button>
      {plan && <div className="plan-card"><div className="plan-title"><strong>{plan.status === "completed" ? t("planCompleted") : plan.status === "failed" ? t("planFailed") : plan.status === "cancelled" ? t("planCancelled") : t("pendingPlan")}</strong><span>{plan.steps.length} {t("steps")}</span></div>{planTask && ["queued", "running", "cancelling"].includes(planTask.status) && <div className="task-progress"><div><span style={{ width: `${Math.max(3, planTask.progress * 100)}%` }} /></div><small>{planTask.status === "cancelling" ? t("cancellingPlan") : `${t("planProgress")} ${Math.round(planTask.progress * 100)}%`}</small></div>}{plan.steps.map((step) => <div key={step.id} className={`plan-row ${step.status}`}><span>{step.status === "completed" ? "✓" : step.status === "failed" ? "!" : step.status === "cancelled" ? "×" : "○"}</span><div><strong>{step.title}</strong><p>{step.description}</p><small>{t(stepStatusKey[step.status])}{step.durationMs !== undefined ? ` · ${step.durationMs} ms` : ""}</small>{step.error && <p className="step-error">{step.error}</p>}</div></div>)}{planTask && ["queued", "running", "cancelling"].includes(planTask.status) ? <button className="danger wide task-cancel" disabled={!!busy || planTask.status === "cancelling"} onClick={cancelCurrentPlan}>{planTask.status === "cancelling" ? t("cancellingPlan") : t("cancelPlan")}</button> : <button className="approve" disabled={!!busy || plan.status === "running"} onClick={executeCurrentPlan}>{plan.status === "completed" || plan.status === "failed" || plan.status === "cancelled" ? t("rerunPlan") : t("approvePlan")}</button>}</div>}
      <div className="privacy-card"><strong>{t("privacyPreview")}</strong><p>{t("privacyNote")}</p></div>
    </aside>
  </div>;
}

function SemanticProfilePanel({ profile, columns, busy, onSave }: { profile: SemanticProfile; columns: DataPreview["columns"]; busy: boolean; onSave: (profile: SemanticProfile) => void }) {
  const { locale } = useI18n();
  const [draft, setDraft] = useState(profile);
  useEffect(() => setDraft(profile), [profile]);
  const label = (zh: string, en: string) => locale === "zh-CN" ? zh : en;
  const roleOf = (name: string) => draft.targetColumn === name ? "target" : draft.identifierColumns.includes(name) ? "identifier" : draft.categoricalColumns.includes(name) ? "categorical" : draft.numericColumns.includes(name) ? "numeric" : draft.dateColumn === name ? "date" : "ignore";
  const setRole = (name: string, role: string) => setDraft((current) => ({
    ...current,
    targetColumn: role === "target" ? name : current.targetColumn === name ? null : current.targetColumn,
    positiveValue: role === "target" ? current.positiveValue : current.targetColumn === name ? null : current.positiveValue,
    identifierColumns: current.identifierColumns.filter((item) => item !== name).concat(role === "identifier" ? [name] : []),
    categoricalColumns: current.categoricalColumns.filter((item) => item !== name).concat(role === "categorical" ? [name] : []),
    numericColumns: current.numericColumns.filter((item) => item !== name).concat(role === "numeric" ? [name] : []),
    dateColumn: role === "date" ? name : current.dateColumn === name ? null : current.dateColumn,
    confirmed: false
  }));
  const update = (values: Partial<SemanticProfile>) => setDraft((current) => ({ ...current, ...values, confirmed: false }));
  return <details className={`semantic-panel ${draft.confirmed ? "confirmed" : "pending"}`} open={!draft.confirmed}>
    <summary><span>{label("业务语义配置", "Business semantics")}</span><small>{draft.confirmed ? label("已确认", "Confirmed") : label("需要确认后才能生成计划", "Confirm before planning")}</small></summary>
    <div className="semantic-body">
      <label><span>{label("业务背景", "Business context")}</span><textarea rows={2} value={draft.businessContext} onChange={(event) => update({ businessContext: event.target.value })} placeholder={label("例如：识别高风险客群并制定干预策略", "Example: identify high-risk segments and interventions")} /></label>
      <div className="semantic-fields"><div className="semantic-field-head"><span>{label("字段", "Field")}</span><span>{label("角色", "Role")}</span></div>{columns.map((column) => <label key={column.name}><span title={column.dtype}>{column.name}</span><select value={roleOf(column.name)} onChange={(event) => setRole(column.name, event.target.value)}><option value="ignore">{label("不参与", "Ignore")}</option><option value="target">{label("目标字段", "Target")}</option><option value="identifier">{label("标识字段", "Identifier")}</option><option value="categorical">{label("分组字段", "Segment")}</option><option value="numeric" disabled={column.semanticType !== "numeric"}>{label("数值驱动", "Numeric driver")}</option><option value="date">{label("时间字段", "Date")}</option></select></label>)}</div>
      {draft.targetColumn && <label><span>{label("正向结果值", "Positive outcome value")}</span><input value={draft.positiveValue ?? ""} onChange={(event) => update({ positiveValue: event.target.value || null })} placeholder={label("例如 1、是、成功", "Example: 1, yes, success")} /></label>}
      <div className="semantic-thresholds"><label><span>{label("重大分群差异（百分点）", "Material segment gap (pp)")}</span><input type="number" min="0" max="100" value={draft.materialGapPoints} onChange={(event) => update({ materialGapPoints: Number(event.target.value) })} /></label><label><span>{label("缺失预警（%）", "Missingness warning (%)")}</span><input type="number" min="0" max="100" value={draft.missingWarningPercent} onChange={(event) => update({ missingWarningPercent: Number(event.target.value) })} /></label><label><span>{label("强相关阈值", "Strong correlation threshold")}</span><input type="number" min="0" max="1" step="0.05" value={draft.strongCorrelation} onChange={(event) => update({ strongCorrelation: Number(event.target.value) })} /></label></div>
      <button className="approve semantic-save" disabled={busy} onClick={() => onSave(draft)}>{draft.confirmed ? label("重新确认配置", "Reconfirm profile") : label("确认并保存配置", "Confirm and save")}</button>
    </div>
  </details>;
}

function LanguageToggle({ locale, onChange }: { locale: Locale; onChange: (locale: Locale) => void }) {
  const { t } = useI18n();
  return <div className="language-toggle" role="group" aria-label={t("language")}><button className={locale === "zh-CN" ? "active" : ""} aria-pressed={locale === "zh-CN"} onClick={() => onChange("zh-CN")}>{t("chinese")}</button><button className={locale === "en" ? "active" : ""} aria-pressed={locale === "en"} onClick={() => onChange("en")}>{t("english")}</button></div>;
}

function Welcome({ busy, error, onCreate, onOpen, locale, onLocaleChange }: { busy: string; error: string; onCreate: () => void; onOpen: () => void; locale: Locale; onLocaleChange: (locale: Locale) => void }) {
  const { t } = useI18n();
  return <div className="welcome"><div className="welcome-language"><LanguageToggle locale={locale} onChange={onLocaleChange} /></div><div className="welcome-card"><span className="welcome-logo">A</span><p className="eyebrow">{t("welcomeEyebrow")}</p><h1>{t("welcomeTitle1")}<br/><em>{t("welcomeTitle2")}</em></h1><p>{t("welcomeBody")}</p><div className="welcome-actions"><button className="primary" onClick={onCreate}>{t("createProject")}</button><button className="ghost" onClick={onOpen}>{t("openExisting")}</button></div>{busy && <small>{busy}…</small>}{error && <div className="error-text">{error}</div>}<div className="feature-grid"><span>▦ CSV / Excel</span><span>⌁ PostgreSQL / MySQL</span><span>{t("reproducibleStats")}</span></div></div></div>;
}

function SectionLabel({ text, action, onAction }: { text: string; action?: string; onAction?: () => void }) { return <div className="section-label"><span>{text}</span>{action && <button onClick={onAction}>{action}</button>}</div>; }

function Empty({ title, body, action, onClick }: { title: string; body: string; action: string; onClick: () => void }) { return <div className="empty-state"><span>⌁</span><h2>{title}</h2><p>{body}</p><button className="primary" onClick={onClick}>{action}</button></div>; }

function DataTab({ preview, onAudit, onClean }: { preview: DataPreview | null; onAudit: () => void; onClean: () => void }) {
  const { t } = useI18n();
  if (!preview) return <Empty title={t("importFirst")} body={t("importFirstBody")} action={t("selectDataFile")} onClick={() => document.querySelector<HTMLButtonElement>(".top-actions .primary")?.click()} />;
  return <><div className="canvas-header"><div><p className="eyebrow">DATASET OVERVIEW</p><h2>{t("dataPreview")}</h2></div><div><button className="ghost" onClick={onClean}>{t("configureCleaning")}</button><button className="primary" onClick={onAudit}>{t("runAudit")}</button></div></div>{preview.privacy && <section className={`privacy-scan ${preview.privacy.status}`}><div><strong>{preview.privacy.hasPersonalData ? t("privacyRiskTitle") : t("privacyClearTitle")}</strong><p>{preview.privacy.hasPersonalData ? t("privacyRiskHint") : t("privacyClearHint")}</p><small>{t("privacyScanned")} {preview.privacy.scannedRows.toLocaleString()} / {preview.privacy.totalRows.toLocaleString()} {t("rows")} · {preview.privacy.findings.length} {t("privacyFindings")}</small></div>{preview.privacy.findings.length > 0 && <div className="privacy-findings">{preview.privacy.findings.map((finding) => <span key={`${finding.column}-${finding.category}`}><strong>{finding.column}</strong>{finding.category} · {finding.confidence} · {finding.matchCount}</span>)}</div>}</section>}<div className="metric-row"><Metric label={t("totalRows")} value={preview.rowCount.toLocaleString()} /><Metric label={t("fieldCount")} value={String(preview.columns.length)} /><Metric label={t("previewStatus")} value={preview.truncated ? t("first100") : t("complete")} /></div><div className="table-wrap"><table><thead><tr>{preview.columns.map((column) => <th key={column.name}>{column.name}<small>{column.dtype}</small></th>)}</tr></thead><tbody>{preview.rows.map((row, index) => <tr key={index}>{preview.columns.map((column) => <td key={column.name}>{String(row[column.name] ?? "—")}</td>)}</tr>)}</tbody></table></div></>;
}

function CleanTab({ preview, impact, busy, onPreview, onApply }: { preview: DataPreview | null; impact: JsonMap | null; busy: boolean; onPreview: (operations: JsonMap[]) => void; onApply: (operations: JsonMap[]) => void }) {
  const { t } = useI18n();
  const [kind, setKind] = useState("drop_duplicates");
  const [selected, setSelected] = useState<string[]>([]);
  const [strategy, setStrategy] = useState("median");
  const [value, setValue] = useState("");
  const [dtype, setDtype] = useState("numeric");
  if (!preview) return <Empty title={t("importFirst")} body={t("importFirstBody")} action={t("selectDataFile")} onClick={() => document.querySelector<HTMLButtonElement>(".top-actions .primary")?.click()} />;
  const operation: JsonMap = { kind, columns: selected };
  if (kind === "fill_missing") { operation.strategy = strategy; if (strategy === "value") operation.value = /^-?\d+(\.\d+)?$/.test(value) ? Number(value) : value; }
  if (kind === "cast") operation.dtype = dtype;
  const operations = [operation];
  const requiresColumns = ["fill_missing", "cast", "normalize_text", "clip_outliers"].includes(kind);
  const valid = !requiresColumns || selected.length > 0;
  const currentImpact = impact && JSON.stringify(impact.operations) === JSON.stringify(operations) ? impact : null;
  const toggleColumn = (name: string) => setSelected((current) => current.includes(name) ? current.filter((item) => item !== name) : [...current, name]);
  const missingCount = (report: JsonMap) => report.columns.reduce((sum: number, column: JsonMap) => sum + column.missing, 0);
  return <><div className="canvas-header"><div><p className="eyebrow">NON-DESTRUCTIVE CLEANING</p><h2>{t("configureCleaning")}</h2><p className="subtle">{t("cleanSafety")}</p></div></div><div className="clean-layout"><section className="control-card"><label className="field-label">{t("operation")}</label><select value={kind} onChange={(event) => { setKind(event.target.value); setSelected([]); }}><option value="drop_duplicates">{t("dropDuplicates")}</option><option value="drop_missing">{t("dropMissing")}</option><option value="fill_missing">{t("fillMissing")}</option><option value="cast">{t("castType")}</option><option value="normalize_text">{t("normalizeText")}</option><option value="clip_outliers">{t("clipOutliers")}</option></select>{kind === "fill_missing" && <div className="inline-controls"><label><span>{t("strategy")}</span><select value={strategy} onChange={(event) => setStrategy(event.target.value)}><option value="mean">{t("mean")}</option><option value="median">{t("median")}</option><option value="mode">Mode</option><option value="value">{t("fixedValue")}</option></select></label>{strategy === "value" && <label><span>{t("value")}</span><input value={value} onChange={(event) => setValue(event.target.value)} /></label>}</div>}{kind === "cast" && <div className="inline-controls"><label><span>{t("dtype")}</span><select value={dtype} onChange={(event) => setDtype(event.target.value)}><option value="numeric">Numeric</option><option value="datetime">Datetime</option><option value="string">String</option><option value="boolean">Boolean</option></select></label></div>}<label className="field-label field-section">{t("selectFields")}</label><p className="subtle">{t("allFieldsDefault")}</p><div className="field-picker">{preview.columns.map((column) => <label key={column.name} className={selected.includes(column.name) ? "selected" : ""}><input type="checkbox" checked={selected.includes(column.name)} onChange={() => toggleColumn(column.name)} /><span><strong>{column.name}</strong><small>{column.dtype}</small></span></label>)}</div><div className="clean-actions"><button className="ghost" disabled={!valid || busy} onClick={() => onPreview(operations)}>{t("previewChanges")}</button><button className="primary" disabled={!valid || busy || !currentImpact?.changed} onClick={() => onApply(operations)}>{t("applyChanges")}</button></div></section><section className="impact-card">{currentImpact ? <><h3>{t("cleaningImpact")}</h3><div className="impact-comparison"><div><span>{t("before")}</span><strong>{currentImpact.before.rowCount.toLocaleString()} {t("rows")}</strong><small>{currentImpact.before.duplicateRows} {t("duplicateRows")} · {missingCount(currentImpact.before)} {t("missingCells")}</small></div><div><span>{t("after")}</span><strong>{currentImpact.after.rowCount.toLocaleString()} {t("rows")}</strong><small>{currentImpact.after.duplicateRows} {t("duplicateRows")} · {missingCount(currentImpact.after)} {t("missingCells")}</small></div></div>{!currentImpact.changed && <div className="warning">{t("noChanges")}</div>}<div className="table-wrap clean-preview-table"><table><thead><tr>{currentImpact.preview.columns.map((column: JsonMap) => <th key={column.name}>{column.name}<small>{column.dtype}</small></th>)}</tr></thead><tbody>{currentImpact.preview.rows.slice(0, 10).map((row: JsonMap, index: number) => <tr key={index}>{currentImpact.preview.columns.map((column: JsonMap) => <td key={column.name}>{String(row[column.name] ?? "—")}</td>)}</tr>)}</tbody></table></div></> : <Empty title={t("previewChanges")} body={t("cleanSafety")} action={t("previewChanges")} onClick={() => valid && onPreview(operations)} />}</section></div></>;
}

function Metric({ label, value }: { label: string; value: string }) { return <div className="metric"><span>{label}</span><strong>{value}</strong></div>; }

function AuditTab({ report, onRun }: { report: JsonMap | null; onRun: () => void }) {
  const { locale, t } = useI18n();
  if (!report) return <Empty title={t("noAudit")} body={t("auditBody")} action={t("startAudit")} onClick={onRun} />;
  return <><div className="canvas-header"><div><p className="eyebrow">QUALITY PROFILE</p><h2>{t("qualityAudit")}</h2></div><button className="ghost" onClick={onRun}>{t("rerun")}</button></div><div className="metric-row"><Metric label={t("rowCount")} value={report.rowCount.toLocaleString()} /><Metric label={t("duplicateRows")} value={report.duplicateRows.toLocaleString()} /><Metric label={t("memory")} value={`${(report.memoryBytes / 1024 / 1024).toFixed(2)} MB`} /></div>{report.warnings?.map((warning: string) => <div className="warning" key={warning}>! {translateBackendMessage(locale, warning)}</div>)}<div className="table-wrap"><table><thead><tr><th>{t("field")}</th><th>{t("type")}</th><th>{t("missing")}</th><th>{t("unique")}</th><th>{t("outliers")}</th><th>{t("range")}</th></tr></thead><tbody>{report.columns.map((column: JsonMap) => <tr key={column.name}><td><strong>{column.name}</strong></td><td>{column.dtype}</td><td>{(column.missingRate * 100).toFixed(1)}%</td><td>{column.unique}</td><td>{column.outliersIqr}</td><td>{column.min ?? "—"} → {column.max ?? "—"}</td></tr>)}</tbody></table></div></>;
}

function EdaTab({ result, onRun }: { result: EdaResult | null; onRun: () => void }) {
  const { t } = useI18n();
  if (!result) return <Empty title={t("noEda")} body={t("edaBody")} action={t("runEda")} onClick={onRun} />;
  const correlationColumns = result.numericColumns.filter((name) => result.correlation[name]);
  return <><div className="canvas-header"><div><p className="eyebrow">EXPLORATORY PROFILE</p><h2>{t("eda")}</h2></div><button className="ghost" onClick={onRun}>{t("rerun")}</button></div><div className="metric-row"><Metric label={t("rowCount")} value={result.rowCount.toLocaleString()} /><Metric label={t("numericFields")} value={String(result.numericColumns.length)} /><Metric label={t("categoricalFields")} value={String(result.categoricalColumns.length)} /></div>{result.numericColumns.length > 0 && <><h3 className="result-heading">{t("numericFields")}</h3><div className="table-wrap eda-table"><table><thead><tr><th>{t("field")}</th><th>{t("mean")}</th><th>{t("std")}</th><th>{t("minimum")}</th><th>{t("median")}</th><th>{t("maximum")}</th></tr></thead><tbody>{result.numericColumns.map((name) => { const item = result.numeric[name]!; return <tr key={name}><td><strong>{name}</strong></td><td>{formatNumber(item.mean)}</td><td>{formatNumber(item.std)}</td><td>{formatNumber(item.min)}</td><td>{formatNumber(item.median)}</td><td>{formatNumber(item.max)}</td></tr>; })}</tbody></table></div></>}{result.categoricalColumns.length > 0 && <><h3 className="result-heading">{t("categoricalFields")}</h3><div className="table-wrap eda-table"><table><thead><tr><th>{t("field")}</th><th>{t("unique")}</th><th>{t("topValues")}</th></tr></thead><tbody>{result.categoricalColumns.map((name) => <tr key={name}><td><strong>{name}</strong></td><td>{result.categorical[name]!.unique}</td><td>{result.categorical[name]!.topValues.slice(0, 5).map((item) => `${item.value} (${item.count})`).join(" · ") || "—"}</td></tr>)}</tbody></table></div></>}{correlationColumns.length > 1 && <><h3 className="result-heading">{t("correlationMatrix")}</h3><div className="table-wrap eda-table"><table><thead><tr><th>{t("field")}</th>{correlationColumns.map((name) => <th key={name}>{name}</th>)}</tr></thead><tbody>{correlationColumns.map((row) => <tr key={row}><td><strong>{row}</strong></td>{correlationColumns.map((column) => <td key={column}>{formatNumber(result.correlation[row]?.[column])}</td>)}</tr>)}</tbody></table></div></>}</>;
}

function formatNumber(value: number | null | undefined): string { return value === null || value === undefined ? "—" : Number(value).toLocaleString(undefined, { maximumFractionDigits: 4 }); }

function StatsTab({ result, columns, profile, busy, onRun }: { result: StatisticalResult | null; columns: DataPreview["columns"]; profile: SemanticProfile | null; busy: boolean; onRun: (method: string, columns: string[], parameters: JsonMap) => void }) {
  const { locale, t } = useI18n();
  const labels = locale === "zh-CN"
    ? { auto: "自动选择（推荐）", goal: "分析目的", relationship: "关系分析", independent: "独立样本比较", paired: "配对样本比较", alpha: "显著性水平 α", confidence: "置信水平", effect: "最小实际效应", adjustment: "多重比较校正", suitability: "方法适用性", estimate: "估计值", interval: "置信区间", assumptions: "适用条件检查", alternatives: "替代建议", significant: "统计显著", comparisons: "校正后事后比较", pass: "适用", warning: "需复核", unavailable: "不适用" }
    : { auto: "Automatic selection (recommended)", goal: "Analysis purpose", relationship: "Relationship", independent: "Independent comparison", paired: "Paired comparison", alpha: "Significance α", confidence: "Confidence level", effect: "Minimum practical effect", adjustment: "Multiple-testing adjustment", suitability: "Suitability", estimate: "Estimate", interval: "Confidence interval", assumptions: "Assumption checks", alternatives: "Alternatives", significant: "Statistically significant", comparisons: "Adjusted post-hoc comparisons", pass: "Suitable", warning: "Review", unavailable: "Not applicable" };
  const methods: Array<[string, string]> = [["auto", labels.auto], ["welch", t("welchTest")], ["t-test", t("tTest")], ["paired-t", t("pairedT")], ["mann-whitney", t("mannWhitney")], ["wilcoxon", t("wilcoxon")], ["normality", t("normality")], ["pearson", t("pearson")], ["spearman", t("spearman")], ["kendall", t("kendall")], ["anova", t("anova")], ["kruskal", t("kruskal")], ["chi-square", t("chiSquare")], ["fisher", t("fisher")]];
  const [method, setMethod] = useState("auto");
  const [goal, setGoal] = useState("relationship");
  const [selected, setSelected] = useState<string[]>([]);
  const [alpha, setAlpha] = useState("0.05");
  const [confidence, setConfidence] = useState("0.95");
  const [minimumEffect, setMinimumEffect] = useState("0.2");
  const [adjustment, setAdjustment] = useState("holm");
  const numeric = columns.filter((column) => column.semanticType === "numeric");
  const available = ["auto", "chi-square", "fisher"].includes(method) ? columns : numeric;
  const requiredCount = method === "normality" ? 1 : 2;
  useEffect(() => {
    setSelected((current) => {
      const valid = current.filter((name) => available.some((column) => column.name === name));
      if (valid.length) return valid;
      if (method === "auto" && profile?.targetColumn && profile.categoricalColumns[0]) return [profile.targetColumn, profile.categoricalColumns[0]];
      const preferred = method === "auto" && profile?.numericColumns.length ? profile.numericColumns : available.map((column) => column.name);
      return preferred.slice(0, requiredCount);
    });
  }, [method, columns.map((column) => column.name).join("|"), profile?.updatedAt]);
  const toggleColumn = (name: string) => setSelected((current) => current.includes(name) ? current.filter((item) => item !== name) : [...current, name]);
  const run = () => onRun(method, selected, { alpha: Number(alpha), confidenceLevel: Number(confidence), minimumEffect: Number(minimumEffect), analysisGoal: goal, pAdjustment: adjustment, postHoc: true });
  const statusLabel = result?.status === "warning" ? labels.warning : result?.status === "not-applicable" ? labels.unavailable : labels.pass;
  const interval = result?.confidenceInterval ? `[${formatNumber(result.confidenceInterval[0])}, ${formatNumber(result.confidenceInterval[1])}]` : "—";
  return <><div className="canvas-header"><div><p className="eyebrow">INFERENCE · EVIDENCE</p><h2>{t("statistics")}</h2><p className="subtle">{t("statsRequirement")}</p></div><button className="primary" disabled={busy} onClick={run}>{t("runWelch")}</button></div>
    <div className="stats-config evidence-config">
      <label><span className="field-label">{t("selectMethod")}</span><select value={method} onChange={(event) => { setMethod(event.target.value); setSelected([]); }}>{methods.map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
      {method === "auto" && <label><span className="field-label">{labels.goal}</span><select value={goal} onChange={(event) => setGoal(event.target.value)}><option value="relationship">{labels.relationship}</option><option value="independent-comparison">{labels.independent}</option><option value="paired-comparison">{labels.paired}</option></select></label>}
      <label><span className="field-label">{labels.alpha}</span><input type="number" min="0.001" max="0.2" step="0.01" value={alpha} onChange={(event) => setAlpha(event.target.value)} /></label>
      <label><span className="field-label">{labels.confidence}</span><input type="number" min="0.8" max="0.999" step="0.01" value={confidence} onChange={(event) => setConfidence(event.target.value)} /></label>
      <label><span className="field-label">{labels.effect}</span><input type="number" min="0" step="0.05" value={minimumEffect} onChange={(event) => setMinimumEffect(event.target.value)} /></label>
      <label><span className="field-label">{labels.adjustment}</span><select value={adjustment} onChange={(event) => setAdjustment(event.target.value)}><option value="holm">Holm</option><option value="fdr_bh">Benjamini–Hochberg</option><option value="bonferroni">Bonferroni</option></select></label>
      <div className="stats-fields"><span className="field-label">{t("selectedFields")}</span><div className="field-picker compact">{available.map((column) => <label key={column.name} className={selected.includes(column.name) ? "selected" : ""}><input type="checkbox" checked={selected.includes(column.name)} onChange={() => toggleColumn(column.name)} /><span><strong>{column.name}</strong><small>{column.dtype}</small></span></label>)}</div></div>
    </div>
    <p className="subtle stats-selection">{t("comparePrefix")}{selected.join(" / ") || t("noNumeric")}</p>
    {result ? <div className="evidence-result">
      <div className="metric-row"><Metric label={t("method")} value={result.method} /><Metric label={labels.suitability} value={statusLabel} /><Metric label={labels.estimate} value={formatNumber(result.estimate)} /><Metric label={labels.interval} value={interval} /></div>
      <div className="metric-row"><Metric label={t("statistic")} value={formatNumber(result.statistic)} /><Metric label={t("pValue")} value={result.pValue?.toPrecision(4) ?? "—"} /><Metric label={t("effectSize")} value={formatNumber(result.effectSize)} /><Metric label={labels.significant} value={result.significance?.statisticallySignificant ? "✓" : "—"} /></div>
      <div className={`evidence-status ${result.status ?? "completed"}`}><strong>{labels.suitability}: {statusLabel}</strong><span>{result.recommendationReason}</span>{result.alternatives?.length ? <span>{labels.alternatives}: {result.alternatives.join(" / ")}</span> : null}</div>
      <details className="assumption-panel" open={result.status === "warning"}><summary>{labels.assumptions}</summary><pre>{JSON.stringify(result.assumptions, null, 2)}</pre></details>
      {!!result.comparisons?.length && <div className="table-wrap comparison-table"><h3>{labels.comparisons}</h3><table><thead><tr><th>A</th><th>B</th><th>p</th><th>adjusted p</th><th>{labels.adjustment}</th></tr></thead><tbody>{result.comparisons.map((item) => <tr key={`${item.left}-${item.right}`}><td>{item.left}</td><td>{item.right}</td><td>{item.pValue.toPrecision(4)}</td><td>{item.adjustedPValue.toPrecision(4)}</td><td>{item.adjustment}</td></tr>)}</tbody></table></div>}
      <div className="interpretation"><strong>{t("interpretation")}</strong><p>{translateBackendMessage(locale, result.interpretation)}</p><small>{t("statsCaution")}</small></div>
    </div> : <div className="assistant-note">{t("statsBody")}</div>}</>;
}
function CodeTab({ code, setCode, result, onRun }: { code: string; setCode: (value: string) => void; result: JsonMap | null; onRun: () => void }) { const { t } = useI18n(); return <><div className="canvas-header"><div><p className="eyebrow">REPRODUCIBLE CODE</p><h2>{t("pythonEditor")}</h2></div><button className="primary" onClick={onRun}>{t("validateRun")}</button></div><div className="security-note">{t("securityNote")}</div><div className="editor-shell"><Editor height="410px" language="python" theme="vs-dark" value={code} onChange={(value) => setCode(value ?? "")} options={{ minimap: { enabled: false }, fontSize: 14, padding: { top: 16 } }} /></div>{result && <pre className={result.ok ? "result-console" : "result-console error"}>{JSON.stringify(result, null, 2)}</pre>}</>;
}

function ChartTab({ artifact, onCreate }: { artifact: ChartArtifact | null; onCreate: () => void }) { const { t } = useI18n(); return artifact ? <><div className="canvas-header"><div><p className="eyebrow">INTERACTIVE VISUAL</p><h2>{artifact.title}</h2></div><button className="ghost" onClick={onCreate}>{t("regenerate")}</button></div><div className="chart-shell"><Plot data={artifact.plotly.data as Plotly.Data[]} layout={{ ...(artifact.plotly.layout as Partial<Plotly.Layout>), autosize: true }} config={{ responsive: true, displaylogo: false, toImageButtonOptions: { format: "svg" } }} useResizeHandler style={{ width: "100%", height: "100%" }} /></div></> : <Empty title={t("firstChart")} body={t("chartBody")} action={t("generateDistribution")} onClick={onCreate} />; }

function ReportTab({ markdown, setMarkdown, sections, structured, busy, activeVersionId, lastExport, onExportDataset, onExportReport, onExportBundle }: { markdown: string; setMarkdown: (value: string) => void; sections: JsonMap[]; structured: boolean; busy: boolean; activeVersionId: string; lastExport: string; onExportDataset: (format: "csv" | "xlsx") => void; onExportReport: (format: "html" | "pdf", sections: JsonMap[], template: ReportTemplate) => void; onExportBundle: (includeData: boolean, dataFormat: "csv" | "xlsx", sections: JsonMap[], template: ReportTemplate) => void }) {
  const { t } = useI18n();
  const [dataFormat, setDataFormat] = useState<"csv" | "xlsx">("csv");
  const [reportFormat, setReportFormat] = useState<"html" | "pdf">("html");
  const [includeData, setIncludeData] = useState(false);
  const [template, setTemplate] = useState<ReportTemplate>("full");
  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const sectionSignature = sections.map((section) => section.id).join("|");
  const idsForTemplate = (value: ReportTemplate) => sections.filter((section) => !section.audiences?.length || section.audiences.includes(value)).map((section) => section.id);
  useEffect(() => { setSelectedIds(idsForTemplate(template)); }, [sectionSignature, structured]);
  const chooseTemplate = (value: ReportTemplate) => { setTemplate(value); setSelectedIds(idsForTemplate(value)); };
  const toggleSection = (id: string) => setSelectedIds((current) => current.includes(id) ? current.filter((item) => item !== id) : [...current, id]);
  const selectedSections = sections.filter((section) => selectedIds.includes(section.id));
  const quality = sections.find((section) => section.metrics)?.metrics;
  const findingCount = sections.reduce((sum, section) => sum + (section.findings?.length ?? 0), 0);
  const chartCount = selectedSections.reduce((sum, section) => sum + (section.visualizations?.length ?? 0), 0);
  return <><div className="canvas-header"><div><p className="eyebrow">TRACEABLE REPORT V2</p><h2>{t("analysisReport")}</h2><p className="subtle">{t("exportCenterHint")}</p></div></div>{structured && <div className="report-summary"><Metric label={t("qualityScore")} value={quality ? `${quality.score}/100 · ${quality.grade}` : "—"} /><Metric label={t("keyFindings")} value={String(findingCount)} /><Metric label={t("chartsIncluded")} value={String(chartCount)} /></div>}<section className="report-config"><label><span className="field-label">{t("reportTemplate")}</span><select value={template} onChange={(event) => chooseTemplate(event.target.value as ReportTemplate)}><option value="management">{t("managementBrief")}</option><option value="full">{t("fullAnalysis")}</option><option value="technical">{t("technicalAudit")}</option></select></label><div><span className="field-label">{t("reportChapters")}</span><div className="chapter-picker">{sections.map((section) => <label key={section.id} className={selectedIds.includes(section.id) ? "selected" : ""}><input type="checkbox" checked={selectedIds.includes(section.id)} onChange={() => toggleSection(section.id)} />{section.title}</label>)}</div></div></section>{structured && <p className="subtle report-edit-warning">{t("structuredReport")} · {t("manualEditWarning")}</p>}<div className="report-grid report-v2"><textarea value={markdown} onChange={(event) => setMarkdown(event.target.value)} /><article>{selectedSections.map((section) => <section className="report-preview-section" key={section.id}><h2>{section.title}</h2>{section.metrics && <div className="preview-score"><strong>{section.metrics.score}/100</strong><span>{section.metrics.grade} · {section.metrics.level}</span></div>}<ReactMarkdown>{section.markdown}</ReactMarkdown>{section.visualizations?.map((visualization: ChartArtifact) => <div className="report-chart-preview" key={visualization.id}><Plot data={visualization.plotly.data as Plotly.Data[]} layout={{ ...(visualization.plotly.layout as Partial<Plotly.Layout>), autosize: true, margin: { l: 48, r: 20, t: 48, b: 48 } }} config={{ responsive: true, displaylogo: false }} useResizeHandler style={{ width: "100%", height: "100%" }} /></div>)}</section>)}</article></div><div className="export-center"><div className="export-card"><strong>{t("cleanDataExport")}</strong><p>{t("cleanDataExportHint")}</p><select value={dataFormat} onChange={(event) => setDataFormat(event.target.value as "csv" | "xlsx")}><option value="csv">CSV (UTF-8)</option><option value="xlsx">Excel (.xlsx)</option></select><button className="ghost" disabled={busy || !activeVersionId} onClick={() => onExportDataset(dataFormat)}>{t("exportDataset")}</button></div><div className="export-card"><strong>{t("formalReport")}</strong><p>{t("formalReportHint")}</p><select value={reportFormat} onChange={(event) => setReportFormat(event.target.value as "html" | "pdf")}><option value="html">HTML</option><option value="pdf">PDF</option></select><button className="primary" disabled={busy || !activeVersionId || !selectedSections.length} onClick={() => onExportReport(reportFormat, selectedSections, template)}>{t("exportReport")}</button></div><div className="export-card"><strong>{t("reproducibilityZip")}</strong><p>{t("reproducibilityHint")}</p><label className="toggle export-toggle"><input type="checkbox" checked={includeData} onChange={(event) => setIncludeData(event.target.checked)} /><span />{t("includeCurrentData")}</label>{includeData && <select value={dataFormat} onChange={(event) => setDataFormat(event.target.value as "csv" | "xlsx")}><option value="csv">CSV (UTF-8)</option><option value="xlsx">Excel (.xlsx)</option></select>}<button className="ghost" disabled={busy || !activeVersionId || !selectedSections.length} onClick={() => onExportBundle(includeData, dataFormat, selectedSections, template)}>{t("exportZip")}</button></div></div>{lastExport && <div className="export-result"><strong>{t("exportCompleted")}</strong><span>{lastExport}</span></div>}</>;
}

function DatabaseTab({ projectDirectory, setError }: { projectDirectory: string; setError: (value: string) => void }) {
  const { locale, t } = useI18n();
  const [config, setConfig] = useState({ dialect: "postgresql", host: "localhost", port: 5432, database: "", username: "", password: "" });
  const [sql, setSql] = useState("SELECT * FROM your_table LIMIT 100"); const [result, setResult] = useState<JsonMap | null>(null); const [approval, setApproval] = useState<JsonMap | null>(null); const [busy, setBusy] = useState(false);
  const update = (key: string, value: string | number) => setConfig((current) => ({ ...current, [key]: value }));
  async function run() { setBusy(true); setError(""); try { const payload = { connection: config, sql, parameters: {}, rowLimit: 1000, timeoutSeconds: 30 }; if (/^\s*(select|with|explain)/i.test(sql)) { setResult(await api("/api/database/query", payload)); setApproval(null); } else { setApproval(await api("/api/database/write/prepare", payload)); } } catch (error) { setError(String(error)); } finally { setBusy(false); } }
  async function executeWrite() { if (!approval) return; setBusy(true); try { setResult(await api("/api/database/write/execute", { connection: config, sql, parameters: {}, approvalId: approval.id })); setApproval(null); } catch (error) { setError(String(error)); } finally { setBusy(false); } }
  return <><div className="canvas-header"><div><p className="eyebrow">DATABASE CONNECTOR</p><h2>PostgreSQL / MySQL</h2></div></div><div className="db-grid"><div className="connection-form"><select value={config.dialect} onChange={(e) => { const dialect = e.target.value; setConfig((c) => ({ ...c, dialect, port: dialect === "mysql" ? 3306 : 5432 })); }}><option value="postgresql">PostgreSQL</option><option value="mysql">MySQL</option></select><input placeholder={t("host")} value={config.host} onChange={(e) => update("host", e.target.value)} /><input placeholder={t("port")} type="number" value={config.port} onChange={(e) => update("port", Number(e.target.value))} /><input placeholder={t("dbName")} value={config.database} onChange={(e) => update("database", e.target.value)} /><input placeholder={t("username")} value={config.username} onChange={(e) => update("username", e.target.value)} /><input placeholder={t("password")} type="password" value={config.password} onChange={(e) => update("password", e.target.value)} /></div><div><Editor height="250px" language="sql" value={sql} onChange={(value) => setSql(value ?? "")} options={{ minimap: { enabled: false }, fontSize: 14 }} /><button className="primary wide" disabled={busy} onClick={run}>{busy ? t("executing") : t("previewExecute")}</button></div></div>{approval && <div className="approval-dialog"><p className="eyebrow">DATABASE WRITE APPROVAL</p><h3>{t("confirmDbWrite")}</h3><code>{approval.statement}</code><p>{t("target")}：{approval.targetObjects.join(", ") || t("unknownTarget")}</p>{approval.warnings.map((item: string) => <div className="warning" key={item}>! {translateBackendMessage(locale, item)}</div>)}<div><button className="ghost" onClick={() => setApproval(null)}>{t("reject")}</button><button className="danger" onClick={executeWrite}>{t("commitTransaction")}</button></div></div>}{result && <pre className="result-console">{JSON.stringify(result, null, 2)}</pre>}<small className="subtle">{t("projectDirectory")}：{projectDirectory}</small></>;
}

const root = createRoot(document.getElementById("root")!);
if (!window.aida) {
  root.render(<div className="welcome"><div className="welcome-card"><span className="welcome-logo">!</span><p className="eyebrow">DESKTOP BRIDGE ERROR</p><h1>桌面服务未加载</h1><p>Electron preload 没有成功注入。请安装最新版本；若问题仍存在，请查看应用日志目录中的 main.log。</p><div className="error-text">错误代码：AIDA_PRELOAD_UNAVAILABLE</div></div></div>);
} else {
  root.render(<React.StrictMode><App /></React.StrictMode>);
}
