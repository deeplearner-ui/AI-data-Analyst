export type Locale = "zh-CN" | "en";

const messages = {
  "zh-CN": {
    localServiceConnected: "本地分析服务已连接", version: "版本", openProject: "打开项目", importData: "＋ 导入数据",
    datasets: "数据集", analysisSteps: "分析步骤", planHint: "在右侧描述目标，生成可审阅的分析计划。",
    nondestructiveVersions: "非破坏式版本", lineageHint: "原始数据保持只读。每次清洗生成新版本，上游变化会使下游结果失效。",
    dataPreview: "数据预览", cleaning: "数据清洗", dataAudit: "数据审计", eda: "探索分析", statistics: "统计分析", code: "代码", charts: "图表", report: "报告", database: "数据库",
    operationFailed: "操作失败", runLog: "运行日志", waiting: "等待操作", rows: "行", columns: "列", noData: "未载入数据",
    assistant: "分析助手", assistantTagline: "计划先行 · 本地执行", assistantNote: "分析计划由本地规则引擎生成，分析过程不连接外部模型，完整数据不会离开本机。",
    analysisGoal: "分析目标", includeSamples: "包含脱敏样例", generatePlan: "✦ 生成分析计划", pendingPlan: "待执行计划", steps: "步", approvePlan: "确认并执行", rerunPlan: "重新执行计划", planCompleted: "计划执行完成", planFailed: "计划执行失败", planCancelled: "计划已取消", cancelPlan: "取消执行", cancellingPlan: "正在取消…", planProgress: "执行进度",
    privacyPreview: "隐私与网络", privacyNote: "计划生成与分析均在本机完成，不提供外部模型网络出口。", privacyRiskTitle: "检测到个人信息风险", privacyClearTitle: "未检测到明显个人信息", privacyRiskHint: "检测结果仅包含字段名、类别和数量，不保存或显示命中的原始值。导出前需要你明确确认。", privacyClearHint: "已扫描字段名和数据模式；仍建议在对外发送文件前人工复核。", privacyScanned: "已扫描", privacyFindings: "项风险", privacyExportConfirm: "当前数据可能包含个人信息。确认你已审阅风险并仍要导出吗？",
    welcomeEyebrow: "本地优先分析", welcomeTitle1: "从原始数据到", welcomeTitle2: "可验证的洞察", welcomeBody: "在本机完成数据审计、清洗、统计分析与交互式图表。AI 负责规划和解释，代码与证据始终可审阅。",
    createProject: "创建分析项目", openExisting: "打开已有项目", reproducibleStats: "◇ 可复现统计",
    importFirst: "导入第一个数据集", importFirstBody: "支持 CSV、XLSX，也可以在数据库页连接 PostgreSQL 或 MySQL。", selectDataFile: "选择数据文件",
    createDedupVersion: "创建去重版本", runAudit: "运行数据审计", totalRows: "总行数", fieldCount: "字段数", previewStatus: "预览状态", first100: "前 100 行", complete: "完整",
    configureCleaning: "配置数据清洗", cleanSafety: "先预览影响，再确认创建非破坏式数据版本。原始数据不会被覆盖。", operation: "操作", selectFields: "选择字段", allFieldsDefault: "不选择字段时应用到整行或所有适用字段。", dropDuplicates: "删除重复行", dropMissing: "删除缺失行", fillMissing: "填补缺失值", castType: "类型转换", normalizeText: "文本标准化", clipOutliers: "IQR 异常值截尾", strategy: "填补策略", fixedValue: "固定值", value: "值", dtype: "目标类型", previewChanges: "预览变更", applyChanges: "确认并创建版本", noChanges: "该配置不会改变当前数据", cleaningImpact: "清洗影响", before: "清洗前", after: "清洗后", missingCells: "缺失单元格", cleaningPreviewAction: "预览数据清洗", cleaningApplyAction: "应用数据清洗",
    noAudit: "尚未执行数据审计", auditBody: "检查缺失、重复、常量列、唯一性、范围与 IQR 离群值。", startAudit: "开始审计", qualityAudit: "数据质量审计", rerun: "重新运行",
    rowCount: "行数", duplicateRows: "重复行", memory: "内存", field: "字段", type: "类型", missing: "缺失", unique: "唯一值", outliers: "离群值", range: "范围",
    noEda: "尚未执行探索分析", edaBody: "生成数值字段描述统计、分类字段频数和相关矩阵。", runEda: "开始探索分析", numericFields: "数值字段", categoricalFields: "分类/文本字段", mean: "均值", std: "标准差", median: "中位数", minimum: "最小值", maximum: "最大值", correlationMatrix: "相关矩阵", topValues: "高频值",
    comparePrefix: "已选择字段：", noNumeric: "尚无数值字段", runWelch: "运行统计分析", method: "方法", statistic: "统计量", pValue: "p 值", effectSize: "效应量", selectMethod: "选择统计方法", selectedFields: "分析字段", statsRequirement: "请按方法要求选择字段。单变量检验选 1 个字段，双变量检验选 2 个，ANOVA/Kruskal 可选 2 个以上。", tTest: "独立样本 t 检验", welchTest: "Welch t 检验", pairedT: "配对 t 检验", mannWhitney: "Mann–Whitney U", wilcoxon: "Wilcoxon 配对检验", normality: "Shapiro–Wilk 正态性", chiSquare: "卡方独立性检验", fisher: "Fisher 精确检验", anova: "单因素 ANOVA", kruskal: "Kruskal–Wallis", pearson: "Pearson 相关", spearman: "Spearman 相关", kendall: "Kendall 相关",
    interpretation: "解释", statsCaution: "统计显著性不等于实际重要性，请结合效应量、样本设计和领域背景。", chooseMethod: "选择统计方法", statsBody: "MVP API 已支持 t/Welch、配对检验、Mann–Whitney、Wilcoxon、卡方、Fisher、ANOVA、Kruskal 和三类相关系数。", runQuickTest: "运行快捷检验",
    pythonEditor: "Python 编辑器", validateRun: "▶ 验证并运行", securityNote: "受限执行用于防止误操作，不是运行恶意代码的虚拟机边界。禁止系统命令、外部网络和未许可依赖。",
    regenerate: "重新生成", firstChart: "生成第一张图表", chartBody: "Plotly 图表支持缩放、筛选、悬停和 PNG/SVG 导出。", generateDistribution: "生成字段分布", distribution: "分布",
    analysisReport: "分析报告", exportHtml: "导出独立 HTML", exportCenterHint: "选择报告模板与章节，再交付正式报告或完整的可复现分析包。", reportTemplate: "报告模板", managementBrief: "管理层摘要", fullAnalysis: "完整分析", technicalAudit: "技术审计", reportChapters: "报告章节", selectAll: "全选", structuredReport: "结构化报告 V2", manualEditWarning: "编辑 Markdown 会切换为单章节手工报告。", keyFindings: "关键发现", qualityScore: "质量评分", chartsIncluded: "报告图表", cleanDataExport: "清洗数据", cleanDataExportHint: "导出当前数据版本；CSV 使用 UTF-8 BOM，XLSX 包含版本元数据。", formalReport: "正式报告", formalReportHint: "包含封面、目录、关键发现、多图解读与追溯信息。", reproducibilityZip: "可复现 ZIP", reproducibilityHint: "包含计划、产物、版本清单、同版 HTML 和 PDF；默认不含数据。", includeCurrentData: "包含当前数据版本", exportDataset: "导出数据", exportReport: "导出报告", exportZip: "生成 ZIP", exportCompleted: "导出完成", host: "主机", port: "端口", dbName: "数据库", username: "用户名", password: "密码（不会写入项目）", executing: "执行中…", previewExecute: "预览 / 执行",
    confirmDbWrite: "确认外部数据库写入", target: "目标", unknownTarget: "无法自动识别", reject: "拒绝", commitTransaction: "确认并提交事务", projectDirectory: "项目目录",
    selectProjectDirectory: "选择项目目录", createProjectAction: "创建项目", openProjectAction: "打开项目", readPreview: "读取数据预览", importDataAction: "导入数据", runAuditAction: "运行数据审计", createDedupAction: "创建去重版本",
    generatePlanAction: "生成分析计划", executePlanAction: "启动分析计划", cancelPlanAction: "取消分析计划", runEdaAction: "运行探索分析", needTwoNumeric: "所选统计方法的字段数量不符合要求", runWelchAction: "运行统计分析", createChartAction: "生成交互图表", runCodeAction: "验证并运行代码", buildReportAction: "导出正式报告", exportDatasetAction: "导出当前数据", exportBundleAction: "生成可复现分析包",
    loadSemanticsAction: "读取业务语义配置", saveSemanticsAction: "保存业务语义配置",
    statusDraft: "待执行", statusQueued: "排队中", statusRunning: "执行中", statusCompleted: "已完成", statusFailed: "失败", statusCancelled: "已取消", statusStale: "已失效",
    defaultProjectName: "数据分析项目", defaultReportName: "数据分析", reportSuffix: "报告",
    language: "语言", chinese: "中文", english: "English"
  },
  en: {
    localServiceConnected: "Local analysis service connected", version: "Version", openProject: "Open project", importData: "+ Import data",
    datasets: "Datasets", analysisSteps: "Analysis steps", planHint: "Describe your goal on the right to generate a reviewable analysis plan.",
    nondestructiveVersions: "Non-destructive versions", lineageHint: "Raw data stays read-only. Each cleaning operation creates a new version, and upstream changes invalidate downstream results.",
    dataPreview: "Data preview", cleaning: "Cleaning", dataAudit: "Data audit", eda: "Explore", statistics: "Statistics", code: "Code", charts: "Charts", report: "Report", database: "Database",
    operationFailed: "Operation failed", runLog: "Run log", waiting: "Waiting", rows: "rows", columns: "columns", noData: "No data loaded",
    assistant: "Analysis Assistant", assistantTagline: "Plan first · Run locally", assistantNote: "Plans are generated by the local rules engine. Analysis does not connect to external models, and complete data stays on this device.",
    analysisGoal: "Analysis goal", includeSamples: "Include masked samples", generatePlan: "✦ Generate analysis plan", pendingPlan: "Plan ready to run", steps: "steps", approvePlan: "Approve and run", rerunPlan: "Run plan again", planCompleted: "Plan completed", planFailed: "Plan failed", planCancelled: "Plan cancelled", cancelPlan: "Cancel run", cancellingPlan: "Cancelling…", planProgress: "Progress",
    privacyPreview: "Privacy and network", privacyNote: "Planning and analysis run locally, with no external model network egress.", privacyRiskTitle: "Personal-data risk detected", privacyClearTitle: "No obvious personal data detected", privacyRiskHint: "Results contain only field names, categories, and counts; matched raw values are never stored or displayed. Explicit confirmation is required before export.", privacyClearHint: "Field names and value patterns were scanned. Manually review files before sharing them externally.", privacyScanned: "Scanned", privacyFindings: "findings", privacyExportConfirm: "This dataset may contain personal data. Confirm that you reviewed the risks and still want to export it.",
    welcomeEyebrow: "LOCAL-FIRST ANALYTICS", welcomeTitle1: "From raw data to", welcomeTitle2: "verifiable insight", welcomeBody: "Audit, clean, analyze, and visualize data on your device. AI plans and explains while code and evidence remain reviewable.",
    createProject: "Create analysis project", openExisting: "Open existing project", reproducibleStats: "◇ Reproducible statistics",
    importFirst: "Import your first dataset", importFirstBody: "Supports CSV and XLSX, or connect to PostgreSQL or MySQL from the Database tab.", selectDataFile: "Choose data file",
    createDedupVersion: "Create deduplicated version", runAudit: "Run data audit", totalRows: "Total rows", fieldCount: "Fields", previewStatus: "Preview", first100: "First 100 rows", complete: "Complete",
    configureCleaning: "Configure data cleaning", cleanSafety: "Preview the impact before creating a non-destructive data version. Raw data is never overwritten.", operation: "Operation", selectFields: "Select fields", allFieldsDefault: "With no fields selected, the operation applies to full rows or all applicable fields.", dropDuplicates: "Remove duplicate rows", dropMissing: "Remove rows with missing values", fillMissing: "Fill missing values", castType: "Convert field type", normalizeText: "Normalize text", clipOutliers: "Clip IQR outliers", strategy: "Fill strategy", fixedValue: "Fixed value", value: "Value", dtype: "Target type", previewChanges: "Preview changes", applyChanges: "Confirm and create version", noChanges: "This configuration does not change the current data", cleaningImpact: "Cleaning impact", before: "Before", after: "After", missingCells: "Missing cells", cleaningPreviewAction: "Preview data cleaning", cleaningApplyAction: "Apply data cleaning",
    noAudit: "No data audit yet", auditBody: "Check missing values, duplicates, constant columns, uniqueness, ranges, and IQR outliers.", startAudit: "Start audit", qualityAudit: "Data quality audit", rerun: "Run again",
    rowCount: "Rows", duplicateRows: "Duplicate rows", memory: "Memory", field: "Field", type: "Type", missing: "Missing", unique: "Unique", outliers: "Outliers", range: "Range",
    noEda: "No exploratory analysis yet", edaBody: "Generate descriptive statistics, categorical frequencies, and a correlation matrix.", runEda: "Run exploratory analysis", numericFields: "Numeric fields", categoricalFields: "Categorical/text fields", mean: "Mean", std: "Std. deviation", median: "Median", minimum: "Minimum", maximum: "Maximum", correlationMatrix: "Correlation matrix", topValues: "Top values",
    comparePrefix: "Selected fields: ", noNumeric: "No numeric fields", runWelch: "Run statistical analysis", method: "Method", statistic: "Statistic", pValue: "p-value", effectSize: "Effect size", selectMethod: "Select method", selectedFields: "Analysis fields", statsRequirement: "Select fields required by the method: 1 for a univariate test, 2 for a bivariate test, and 2 or more for ANOVA/Kruskal.", tTest: "Independent t-test", welchTest: "Welch t-test", pairedT: "Paired t-test", mannWhitney: "Mann–Whitney U", wilcoxon: "Paired Wilcoxon", normality: "Shapiro–Wilk normality", chiSquare: "Chi-square independence", fisher: "Fisher exact test", anova: "One-way ANOVA", kruskal: "Kruskal–Wallis", pearson: "Pearson correlation", spearman: "Spearman correlation", kendall: "Kendall correlation",
    interpretation: "Interpretation", statsCaution: "Statistical significance is not practical importance. Consider effect size, study design, and domain context.", chooseMethod: "Choose a statistical method", statsBody: "The MVP API supports t/Welch, paired tests, Mann–Whitney, Wilcoxon, chi-square, Fisher, ANOVA, Kruskal, and three correlation methods.", runQuickTest: "Run quick test",
    pythonEditor: "Python editor", validateRun: "▶ Validate and run", securityNote: "Restricted execution reduces accidental misuse; it is not a VM security boundary for hostile code. System commands, external networking, and unapproved dependencies are blocked.",
    regenerate: "Regenerate", firstChart: "Create your first chart", chartBody: "Plotly charts support zooming, filtering, hover details, and PNG/SVG export.", generateDistribution: "Generate distribution", distribution: "distribution",
    analysisReport: "Analysis report", exportHtml: "Export standalone HTML", exportCenterHint: "Choose a report template and chapters, then deliver a formal report or reproducibility bundle.", reportTemplate: "Report template", managementBrief: "Executive brief", fullAnalysis: "Full analysis", technicalAudit: "Technical audit", reportChapters: "Report chapters", selectAll: "Select all", structuredReport: "Structured report V2", manualEditWarning: "Editing Markdown switches to a single-section manual report.", keyFindings: "Key findings", qualityScore: "Quality score", chartsIncluded: "Report charts", cleanDataExport: "Clean data", cleanDataExportHint: "Export the active version. CSV uses UTF-8 BOM; XLSX includes version metadata.", formalReport: "Formal report", formalReportHint: "Includes a cover, contents, key findings, multi-chart commentary, and traceability.", reproducibilityZip: "Reproducibility ZIP", reproducibilityHint: "Includes plan, artifacts, version inventory, and matching HTML/PDF. Data is excluded by default.", includeCurrentData: "Include active data version", exportDataset: "Export data", exportReport: "Export report", exportZip: "Build ZIP", exportCompleted: "Export completed", host: "Host", port: "Port", dbName: "Database", username: "Username", password: "Password (not saved to project)", executing: "Running…", previewExecute: "Preview / Run",
    confirmDbWrite: "Confirm external database write", target: "Target", unknownTarget: "Could not identify automatically", reject: "Reject", commitTransaction: "Confirm and commit transaction", projectDirectory: "Project directory",
    selectProjectDirectory: "Select project directory", createProjectAction: "Create project", openProjectAction: "Open project", readPreview: "Load data preview", importDataAction: "Import data", runAuditAction: "Run data audit", createDedupAction: "Create deduplicated version",
    generatePlanAction: "Generate analysis plan", executePlanAction: "Start analysis plan", cancelPlanAction: "Cancel analysis plan", runEdaAction: "Run exploratory analysis", needTwoNumeric: "The selected field count does not meet this method's requirements", runWelchAction: "Run statistical analysis", createChartAction: "Generate interactive chart", runCodeAction: "Validate and run code", buildReportAction: "Export formal report", exportDatasetAction: "Export active data", exportBundleAction: "Build reproducibility bundle",
    loadSemanticsAction: "Load business semantics", saveSemanticsAction: "Save business semantics",
    statusDraft: "Ready", statusQueued: "Queued", statusRunning: "Running", statusCompleted: "Completed", statusFailed: "Failed", statusCancelled: "Cancelled", statusStale: "Stale",
    defaultProjectName: "Data Analysis Project", defaultReportName: "Data Analysis", reportSuffix: " Report",
    language: "Language", chinese: "中文", english: "English"
  }
} as const;

export type MessageKey = keyof typeof messages["zh-CN"];
export const translate = (locale: Locale, key: MessageKey): string => {
  if (key === "structuredReport") return locale === "zh-CN" ? "结构化深度报告 V3" : "Structured evidence report V3";
  if (key === "formalReportHint") return locale === "zh-CN" ? "包含分群差异、驱动因素、字段风险、证据等级、决策门槛、多图解读与追溯信息。" : "Includes segment gaps, drivers, field risks, evidence grades, decision gates, multi-chart commentary, and traceability.";
  return messages[locale][key];
};

export const defaultGoal = (locale: Locale) => locale === "zh-CN"
  ? "请审计数据质量，完成探索性分析，选择合适的统计方法并生成图表汇总。"
  : "Audit data quality, perform exploratory analysis, select appropriate statistical methods, and create a chart summary.";

export const defaultReport = (locale: Locale) => locale === "zh-CN"
  ? "## 分析摘要\n\n导入数据并完成审计后，可在这里整理结论。\n\n- 所有结论应关联到具体数据版本和统计结果。\n- p 值应与效应量、置信区间一起解释。"
  : "## Analysis summary\n\nAfter importing and auditing data, organize the conclusions here.\n\n- Every conclusion should reference a specific data version and statistical result.\n- Interpret p-values together with effect sizes and confidence intervals.";

export function translateBackendMessage(locale: Locale, message: string): string {
  if (locale === "zh-CN") return message;
  const duplicateMatch = message.match(/^发现 (\d+) 行重复记录$/);
  if (duplicateMatch) return `Found ${duplicateMatch[1]} duplicate rows`;
  return ({
    "数据集为空": "The dataset is empty",
    "部分字段缺失率超过 50%": "Some fields have more than 50% missing values",
    "结果具有统计显著性": "The result is statistically significant",
    "未发现统计显著性": "No statistical significance was detected",
    "提交到外部数据库后无法由本应用自动撤销": "Changes committed to an external database cannot be automatically undone by this app",
    "请确认目标数据库、对象和参数": "Confirm the target database, objects, and parameters"
  } as Record<string, string>)[message] ?? message;
}
