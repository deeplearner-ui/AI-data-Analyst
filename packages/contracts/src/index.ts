export const SCHEMA_VERSION = "1.0" as const;

export type Language = "zh-CN" | "en";
export type DatasetSourceKind = "csv" | "xlsx" | "postgresql" | "mysql";
export type StepStatus = "draft" | "queued" | "running" | "completed" | "failed" | "cancelled" | "stale";
export type ApprovalLevel = "none" | "plan" | "database-write" | "code-risk";

export interface ColumnSchema {
  name: string;
  dtype: string;
  nullable: boolean;
  semanticType?: "numeric" | "categorical" | "datetime" | "text" | "boolean" | "unknown";
}

export interface DatasetRef {
  id: string;
  name: string;
  sourceKind: DatasetSourceKind;
  sourceLabel: string;
  currentVersionId: string;
  semanticProfile?: SemanticProfile;
  createdAt: string;
}

export interface SemanticProfile {
  targetColumn?: string | null;
  positiveValue?: string | null;
  identifierColumns: string[];
  categoricalColumns: string[];
  numericColumns: string[];
  dateColumn?: string | null;
  businessContext: string;
  materialGapPoints: number;
  missingWarningPercent: number;
  strongCorrelation: number;
  confirmed: boolean;
  updatedAt?: string;
}

export interface DatasetVersion {
  id: string;
  datasetId: string;
  parentVersionId?: string;
  fingerprint: string;
  rowCount: number;
  columns: ColumnSchema[];
  storagePath?: string;
  operation: string;
  createdAt: string;
}

export interface ProjectManifest {
  schemaVersion: typeof SCHEMA_VERSION;
  id: string;
  name: string;
  language: Language;
  modelProfileId?: string;
  datasets: DatasetRef[];
  createdAt: string;
  updatedAt: string;
}

export type AnalysisMethod =
  | "audit" | "clean" | "eda" | "statistical-test" | "correlation"
  | "regression" | "pca" | "clustering" | "time-series" | "chart" | "report" | "python" | "sql";

export interface AnalysisStep {
  id: string;
  planId: string;
  title: string;
  description: string;
  method: AnalysisMethod;
  inputVersionIds: string[];
  outputVersionId?: string;
  dependencies: string[];
  code?: string;
  parameters: Record<string, unknown>;
  approvalLevel: ApprovalLevel;
  status: StepStatus;
  durationMs?: number;
  logs?: string[];
  artifactIds?: string[];
  error?: string;
}

export interface AnalysisPlan {
  id: string;
  projectId: string;
  goal: string;
  status: "draft" | "approved" | "running" | "completed" | "failed" | "cancelled";
  steps: AnalysisStep[];
  createdAt: string;
  updatedAt?: string;
}

export interface PlanTask {
  id: string;
  planId: string;
  status: "queued" | "running" | "cancelling" | "completed" | "failed" | "cancelled";
  progress: number;
  message: string;
  createdAt: string;
  updatedAt: string;
  plan: AnalysisPlan;
  result?: Record<string, unknown> | null;
  error?: string | null;
}

export interface AnalysisArtifact<T = unknown> {
  id: string;
  planId?: string;
  stepId?: string;
  kind: string;
  datasetVersionId?: string;
  payload: T;
  createdAt: string;
}

export interface EdaResult {
  id: string;
  rowCount: number;
  columnCount: number;
  numericColumns: string[];
  categoricalColumns: string[];
  numeric: Record<string, { count: number; mean?: number; std?: number; min?: number; q25?: number; median?: number; q75?: number; max?: number; skew?: number }>;
  categorical: Record<string, { count: number; unique: number; topValues: Array<{ value: string; count: number }> }>;
  correlation: Record<string, Record<string, number | null>>;
}

export type TaskEventType = "progress" | "log" | "result" | "approval-required" | "error" | "cancelled" | "completed";
export interface TaskEvent<T = unknown> {
  schemaVersion: typeof SCHEMA_VERSION;
  taskId: string;
  stepId?: string;
  type: TaskEventType;
  timestamp: string;
  progress?: number;
  message?: string;
  payload?: T;
}

export interface ApprovalRequest {
  id: string;
  operation: "insert" | "update" | "delete" | "ddl" | "procedure" | "python";
  statement: string;
  parameters: Record<string, unknown>;
  targetObjects: string[];
  estimatedRows?: number;
  preview?: Record<string, unknown>[];
  warnings: string[];
  expiresAt: string;
}

export interface StatisticalResult {
  id: string;
  method: string;
  assumptions: Record<string, boolean | number | string>;
  sampleSize: number | Record<string, number>;
  statistic?: number;
  effectSize?: number;
  confidenceInterval?: [number, number];
  pValue?: number;
  adjustedPValue?: number;
  diagnostics: string[];
  interpretation: string;
}

export interface ChartArtifact {
  id: string;
  title: string;
  datasetVersionId: string;
  plotly: { data: unknown[]; layout: Record<string, unknown>; config?: Record<string, unknown> };
  filters: Record<string, unknown>;
  createdAt: string;
}

export interface ReportSection {
  id: string;
  title: string;
  markdown: string;
  resultIds: string[];
  chartIds: string[];
  visualizations?: ChartArtifact[];
  audiences?: Array<"management" | "full" | "technical">;
  findings?: Array<{ title: string; detail: string; evidence: string; severity: "success" | "warning" | "info"; confidence: "high" | "medium" | "low" }>;
  metrics?: { score: number; grade: string; level: string; missingCells: number; missingRate: number; duplicateRate: number; constantFields: number; outlierCells: number; outlierRate: number };
  risks?: Array<{ field: string; kind: "missing" | "outlier" | "constant"; rate: number; count: number; severity: "high" | "medium" | "low" }>;
  segments?: Array<{ field: string; positiveValue: string; highGroup: string; lowGroup: string; highRate: number; lowRate: number; gap: number; highCount: number; lowCount: number; confidence: "high" | "medium" | "low" }>;
  numericDrivers?: Array<{ field: string; positiveValue: string; positiveMean: number; otherMean: number; positiveMedian: number; otherMedian: number; effectSize: number | null; positiveCount: number; otherCount: number; confidence: "high" | "medium" | "low" }>;
  correlations?: Array<{ left: string; right: string; value: number }>;
}

export interface ReportDocument {
  schemaVersion: typeof SCHEMA_VERSION;
  id: string;
  projectId: string;
  title: string;
  language: Language;
  template?: "management" | "full" | "technical";
  sections: ReportSection[];
  updatedAt: string;
}

export interface DataPreview {
  columns: ColumnSchema[];
  rows: Record<string, unknown>[];
  rowCount: number;
  truncated: boolean;
}

export interface SidecarHealth {
  status: "ok";
  schemaVersion: typeof SCHEMA_VERSION;
  version: string;
  capabilities: string[];
}

export interface DesktopApi {
  sidecarRequest<T>(path: string, init?: { method?: string; body?: unknown }): Promise<T>;
  selectDataFile(): Promise<string | null>;
  selectProjectDirectory(): Promise<string | null>;
  saveExport(suggestedName: string, content: string, encoding?: "utf8" | "base64"): Promise<string | null>;
  setSecret(key: string, value: string): Promise<void>;
  getSecret(key: string): Promise<string | null>;
  deleteSecret(key: string): Promise<void>;
  subscribeTask(taskId: string, listener: (event: TaskEvent) => void): () => void;
}
