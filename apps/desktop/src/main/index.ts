import { app, BrowserWindow, dialog, ipcMain, safeStorage } from "electron";
import { spawn, type ChildProcessWithoutNullStreams } from "node:child_process";
import { createServer } from "node:net";
import { appendFile, mkdir, mkdtemp, readFile, rm, writeFile, unlink } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import crypto from "node:crypto";
import { fileURLToPath } from "node:url";

let mainWindow: BrowserWindow | null = null;
let sidecar: ChildProcessWithoutNullStreams | null = null;
let sidecarBaseUrl = "";
let sidecarToken = "";
let isQuitting = false;

const __dirname = path.dirname(fileURLToPath(import.meta.url));

function sanitizeLogMessage(value: unknown): string {
  let text = String(value);
  text = text.replace(/Bearer\s+[A-Za-z0-9._~+/=-]+/gi, "Bearer <redacted>");
  text = text.replace(/(api[-_ ]?key|password|passwd|access[-_ ]?token|authorization|secret)(\s*[:=]\s*)([^\s,;]+)/gi, "$1$2<redacted>");
  text = text.replace(/(?:file:\/\/\/)?[A-Z]:\\[^\r\n\t"'<>|]+/gi, "<local-path>");
  text = text.replace(/\/(?:Users|home)\/[^/\s]+/gi, "<user-home>");
  text = text.replace(/(?<![A-Z0-9._%+-])[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,63}(?![A-Z0-9._%+-])/gi, "<email>");
  text = text.replace(/(?<!\d)(?:\+?86)?1[3-9]\d{9}(?!\d)/g, "<phone>");
  text = text.replace(/(?<!\d)\d{17}[0-9Xx](?!\d)/g, "<identity-number>");
  return text.slice(0, 4000);
}

async function logMain(message: unknown): Promise<void> {
  try {
    const directory = app.getPath("logs");
    await mkdir(directory, { recursive: true });
    await appendFile(path.join(directory, "main.log"), `${new Date().toISOString()} ${sanitizeLogMessage(message)}\n`, "utf8");
  } catch {
    // Logging must never crash the application.
  }
}

process.on("uncaughtException", (error) => { void logMain(`uncaughtException ${error.stack ?? String(error)}`); });
process.on("unhandledRejection", (error) => { void logMain(`unhandledRejection ${String(error)}`); });

async function freePort(): Promise<number> {
  return new Promise((resolve, reject) => {
    const server = createServer();
    server.once("error", reject);
    server.listen(0, "127.0.0.1", () => {
      const address = server.address();
      const port = typeof address === "object" && address ? address.port : 0;
      server.close(() => resolve(port));
    });
  });
}

function sidecarRoot(): string {
  return app.isPackaged
    ? path.join(process.resourcesPath, "sidecar-runtime")
    : path.resolve(__dirname, "../../../sidecar");
}

async function waitForSidecar(): Promise<void> {
  let lastError: unknown;
  for (let attempt = 0; attempt < 160; attempt += 1) {
    try {
      const response = await fetch(`${sidecarBaseUrl}/api/health`, {
        headers: { Authorization: `Bearer ${sidecarToken}` }
      });
      if (response.ok) {
        await logMain(`sidecar ready at ${sidecarBaseUrl}`);
        return;
      }
    } catch (error) {
      lastError = error;
    }
    await new Promise((resolve) => setTimeout(resolve, 250));
  }
  throw new Error(`Python analysis service did not start: ${String(lastError ?? "timeout")}`);
}

async function startSidecar(): Promise<void> {
  const port = await freePort();
  sidecarToken = crypto.randomBytes(32).toString("hex");
  sidecarBaseUrl = `http://127.0.0.1:${port}`;
  const root = sidecarRoot();
  const packagedExecutable = path.join(root, "aida-sidecar.exe");
  const developmentVenv = path.join(root, ".venv", "Scripts", "python.exe");
  const executable = process.env.AIDA_PYTHON ?? (app.isPackaged ? packagedExecutable : developmentVenv);
  const args = app.isPackaged
    ? ["--host", "127.0.0.1", "--port", String(port)]
    : ["-m", "aida_sidecar", "--host", "127.0.0.1", "--port", String(port)];
  sidecar = spawn(executable, args, {
    cwd: root,
    env: {
      PATH: process.env.PATH,
      SYSTEMROOT: process.env.SYSTEMROOT,
      TEMP: process.env.TEMP,
      TMP: process.env.TMP,
      PYTHONPATH: root,
      AIDA_SESSION_TOKEN: sidecarToken,
      AIDA_APP_DATA: app.getPath("userData")
    },
    windowsHide: true,
    stdio: "pipe"
  });
  await logMain(`starting sidecar mode=${app.isPackaged ? "packaged" : "development"} executable=${path.basename(executable)}`);
  sidecar.on("error", (error) => { void logMain(`sidecar spawn error ${error.stack ?? String(error)}`); });
  sidecar.stderr.on("data", (chunk) => {
    const line = String(chunk).trimEnd();
    console.error(`[sidecar] ${line}`);
    void logMain(`sidecar stderr ${line}`);
  });
  sidecar.on("exit", (code) => {
    if (code && !isQuitting) mainWindow?.webContents.send("sidecar-exited", code);
  });
  await waitForSidecar();
}

async function sidecarRequest(pathname: string, init?: { method?: string; body?: unknown }) {
  if (!pathname.startsWith("/api/")) throw new Error("Only versioned sidecar API routes are allowed");
  const response = await fetch(`${sidecarBaseUrl}${pathname}`, {
    method: init?.method ?? "GET",
    headers: { Authorization: `Bearer ${sidecarToken}`, "Content-Type": "application/json" },
    body: init?.body === undefined ? undefined : JSON.stringify(init.body)
  });
  const payload = await response.json().catch(() => ({ detail: response.statusText }));
  if (!response.ok) throw new Error(payload.detail ?? `Request failed (${response.status})`);
  return payload;
}

async function secretPath(key: string): Promise<string> {
  const directory = path.join(app.getPath("userData"), "secrets");
  await mkdir(directory, { recursive: true });
  return path.join(directory, `${crypto.createHash("sha256").update(key).digest("hex")}.secret`);
}

function registerIpc(): void {
  ipcMain.handle("sidecar:request", (_event, pathname, init) => sidecarRequest(pathname, init));
  ipcMain.handle("file:select-data", async () => {
    const result = await dialog.showOpenDialog({ properties: ["openFile"], filters: [{ name: "Data", extensions: ["csv", "xlsx", "xls"] }] });
    return result.canceled ? null : result.filePaths[0] ?? null;
  });
  ipcMain.handle("file:select-project", async () => {
    const result = await dialog.showOpenDialog({ properties: ["openDirectory", "createDirectory"] });
    return result.canceled ? null : result.filePaths[0] ?? null;
  });
  ipcMain.handle("file:save-export", async (_event, suggestedName: string, content: string, encoding = "utf8") => {
    const result = await dialog.showSaveDialog({ defaultPath: suggestedName });
    if (result.canceled || !result.filePath) return null;
    await writeFile(result.filePath, content, encoding === "base64" ? "base64" : "utf8");
    return result.filePath;
  });
  ipcMain.handle("secret:set", async (_event, key: string, value: string) => {
    if (!safeStorage.isEncryptionAvailable()) throw new Error("Windows secure storage is unavailable");
    await writeFile(await secretPath(key), safeStorage.encryptString(value));
  });
  ipcMain.handle("secret:get", async (_event, key: string) => {
    try { return safeStorage.decryptString(await readFile(await secretPath(key))); } catch { return null; }
  });
  ipcMain.handle("secret:delete", async (_event, key: string) => { try { await unlink(await secretPath(key)); } catch { /* absent */ } });
}

async function createWindow(): Promise<void> {
  const preloadPath = path.join(__dirname, "../preload/index.cjs");
  await logMain(`creating window preload=${path.basename(preloadPath)}`);
  mainWindow = new BrowserWindow({
    width: 1500,
    height: 940,
    minWidth: 1100,
    minHeight: 720,
    backgroundColor: "#f4f1eb",
    webPreferences: {
      preload: preloadPath,
      contextIsolation: true,
      sandbox: true,
      nodeIntegration: false
    }
  });
  mainWindow.webContents.on("preload-error", (_event, failedPath, error) => {
    void logMain(`preload-error path=${failedPath} error=${error.stack ?? String(error)}`);
  });
  mainWindow.webContents.on("did-fail-load", (_event, code, description) => {
    void logMain(`did-fail-load code=${code} description=${description}`);
  });
  mainWindow.webContents.on("console-message", (_event, level, message) => {
    if (level >= 2) void logMain(`renderer console level=${level} ${message}`);
  });
  if (process.env.ELECTRON_RENDERER_URL) await mainWindow.loadURL(process.env.ELECTRON_RENDERER_URL);
  else await mainWindow.loadFile(path.join(__dirname, "../renderer/index.html"));
  await logMain("renderer loaded");
  if (process.argv.includes("--aida-golden-test")) {
    const testRoot = await mkdtemp(path.join(tmpdir(), "aida-golden-"));
    const projectDirectory = path.join(testRoot, "project");
    const dataPath = path.join(testRoot, "sample.csv");
    try {
        await writeFile(dataPath, "id,outcome,group,value,score\n1,yes,A,10,1\n2,no,A,,2\n3,yes,B,18,3\n4,no,B,20,5\n", "utf8");
      const result = await mainWindow.webContents.executeJavaScript(`(async () => {
        const request = (pathname, body) => window.aida.sidecarRequest(pathname, { method: "POST", body });
        const projectDirectory = ${JSON.stringify(projectDirectory)};
        const created = await request("/api/projects", { directory: projectDirectory, name: "Packaged golden path", language: "en" });
        const imported = await request("/api/datasets/import", { projectDirectory, path: ${JSON.stringify(dataPath)} });
        const versionId = imported.version.id;
        if (imported.preview.privacy?.status !== "clear") throw new Error("Privacy scan unexpectedly flagged the golden dataset");
        const suggestedSemantics = await request("/api/analysis/semantics/get", { projectDirectory, versionId });
        if (suggestedSemantics.profile.confirmed) throw new Error("Semantic suggestion must require confirmation");
        const semantics = await request("/api/analysis/semantics/save", {
          projectDirectory, versionId, targetColumn: "outcome", positiveValue: "yes",
          identifierColumns: ["id"], categoricalColumns: ["group"], numericColumns: ["value", "score"],
          dateColumn: null, businessContext: "Golden path conversion analysis",
          materialGapPoints: 10, missingWarningPercent: 5, strongCorrelation: 0.7
        });
        const planned = await request("/api/ai/plan", { projectDirectory, versionId, goal: "Audit and summarize the sample", includeSamples: true, language: "en" });
        if (!planned.contextPreview.semanticProfile?.confirmed) throw new Error("Confirmed semantics are missing from plan context");
        const started = await request("/api/analysis/plans/tasks/start", { projectDirectory, planId: planned.plan.id, language: "en" });
        let task = started.task;
        for (let attempt = 0; attempt < 200 && !["completed", "failed", "cancelled"].includes(task.status); attempt += 1) {
          await new Promise((resolve) => setTimeout(resolve, 50));
          task = (await request("/api/analysis/plans/tasks/status", { projectDirectory, taskId: task.id })).task;
        }
        if (task.status !== "completed") throw new Error("Golden path task ended with " + task.status + ": " + (task.error || task.message));
        const sections = task.result.latest.report.sections;
        const statistics = task.result.latest.statistics;
        if (!statistics.status || !statistics.significance) throw new Error("P0 statistical evidence metadata is missing");
        if (!sections.some((section) => section.id === "statistics" && section.markdown.includes("Suitability status"))) throw new Error("P0 statistical evidence is missing from the report");
        const csv = await request("/api/datasets/export", { projectDirectory, versionId, format: "csv" });
        const xlsx = await request("/api/datasets/export", { projectDirectory, versionId, format: "xlsx" });
        const pdf = await request("/api/reports/export", { projectDirectory, title: "Golden path report", sections, language: "en", format: "pdf", versionId, planId: planned.plan.id });
        const bundle = await request("/api/reports/reproducibility", { projectDirectory, title: "Golden path report", sections, language: "en", versionId, planId: planned.plan.id, includeData: false, dataFormat: "csv" });
        if (!atob(pdf.contentBase64).startsWith("%PDF-") || !atob(bundle.contentBase64).startsWith("PK")) throw new Error("Export signatures are invalid");
        if (sections.length < 6 || !sections.some((section) => section.visualizations?.length)) throw new Error("Rich report sections or embedded visualization are missing");
        return {
          hasAida: typeof window.aida === "object",
          projectId: created.id,
          rowCount: imported.preview.rowCount,
          privacyStatus: imported.preview.privacy.status,
          planStatus: task.plan.status,
          artifactKinds: task.result.artifacts.map((artifact) => artifact.kind).sort(),
          semanticConfirmed: semantics.profile.confirmed && task.result.latest.report.semanticProfile?.confirmed,
          statisticalMethod: statistics.method,
          statisticalStatus: statistics.status,
          reportSections: sections.length,
          exports: { csvBytes: csv.bytes, xlsxBytes: xlsx.bytes, pdfBytes: pdf.bytes, zipBytes: bundle.bytes, zipIncludesData: bundle.includedData }
        };
      })()`);
      await logMain(`golden-test ${JSON.stringify(result)}`);
      console.log(`AIDA_GOLDEN_RESULT=${JSON.stringify(result)}`);
    } catch (error) {
      await logMain(`golden-test failed ${error instanceof Error ? error.stack : String(error)}`);
      console.error(`AIDA_GOLDEN_ERROR=${error instanceof Error ? error.message : String(error)}`);
      process.exitCode = 1;
    } finally {
      if (sidecar && sidecar.exitCode === null) {
        sidecar.kill();
        await Promise.race([
          new Promise<void>((resolve) => sidecar?.once("exit", () => resolve())),
          new Promise<void>((resolve) => setTimeout(resolve, 1000))
        ]);
      }
      try { await rm(testRoot, { recursive: true, force: true, maxRetries: 5, retryDelay: 150 }); }
      catch (error) { await logMain(`golden-test cleanup deferred ${String(error)}`); }
      setTimeout(() => app.exit(Number(process.exitCode ?? 0)), 250);
    }
    return;
  }
  if (process.argv.includes("--aida-smoke-test")) {
    const result = await mainWindow.webContents.executeJavaScript("({ hasAida: typeof window.aida === 'object', hasProjectPicker: typeof window.aida?.selectProjectDirectory === 'function' })");
    await logMain(`smoke-test ${JSON.stringify(result)}`);
    console.log(`AIDA_SMOKE_RESULT=${JSON.stringify(result)}`);
    setTimeout(() => app.quit(), 250);
  }
}

app.whenReady().then(async () => {
  await logMain(`app ready version=${app.getVersion()} packaged=${app.isPackaged}`);
  registerIpc();
  try { await startSidecar(); } catch (error) {
    await logMain(`sidecar startup failed ${error instanceof Error ? error.stack : String(error)}`);
    dialog.showErrorBox("分析服务启动失败", sanitizeLogMessage(error));
  }
  await createWindow();
  app.on("activate", () => { if (BrowserWindow.getAllWindows().length === 0) void createWindow(); });
}).catch((error) => { void logMain(`startup failed ${error instanceof Error ? error.stack : String(error)}`); });

app.on("before-quit", () => { isQuitting = true; sidecar?.kill(); });
app.on("window-all-closed", () => { if (process.platform !== "darwin") app.quit(); });
