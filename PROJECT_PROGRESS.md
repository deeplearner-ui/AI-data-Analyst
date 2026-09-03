# AI Data Analyst：项目进度与跨对话交接

> 这是项目的持续状态基线。新对话应先阅读本文档；每轮设计或实现结束后，应更新本文档，而不是只把结论留在聊天记录中。

## 1. 文档信息

| 字段 | 当前值 |
| --- | --- |
| 最后更新 | 2026-09-03（Asia/Shanghai） |
| Desktop 版本 | 0.1.5 |
| Python sidecar 版本 | 0.1.0 |
| Schema 版本 | 1.0 |
| 工作目录 | D:\Projects\AI-data-Analyst |
| 当前阶段 | 可执行 MVP 纵向切片；后台分析、可确认语义配置、十章证据报告 V3、多图表和模板化导出已接通，安装态 UI E2E 仍未完成 |
| Git 状态 | 当前目录不是 Git 仓库，暂无提交历史 |

状态含义：

- **界面可用**：普通用户可以从桌面界面完成。
- **仅 API**：后端已实现，但界面没有完整入口。
- **骨架**：只有类型、占位接口或局部实现。
- **未实现**：当前代码中不存在有效实现。

更新本文档时：

1. 更新日期、版本和验证结果。
2. 按真实状态调整能力矩阵。
3. 将重要架构决定追加到决策日志。
4. 已知问题解决后保留记录，并标注解决版本。

## 2. 产品目标

构建 Windows 优先、本地优先的 AI 数据分析桌面助手。用户导入本地文件或查询数据库后，可以完成数据审计、非破坏式清洗、EDA、统计分析、建模、可视化和可追溯报告。

目标安全边界：

- 完整数据默认只在本地处理。
- 云模型仅接收 schema、统计摘要和可关闭的脱敏样例。
- 数据库写入必须逐次审批并在事务中执行。
- 自动 Python 执行限制依赖、系统命令、网络和项目外文件访问。
- 本地限制用于降低误操作风险，不是恶意代码的虚拟机级隔离。

## 3. 当前架构

    React Renderer
        │ 只通过 window.aida
        ▼
    Electron preload / 主进程
        │ 随机本地端口 + 会话令牌
        ▼
    FastAPI Python sidecar
        ├─ pandas / scipy / statsmodels / scikit-learn
        ├─ Parquet 数据版本
        └─ SQLite 项目元数据与审计日志

工程目录：

    apps/desktop/                 Electron + React + TypeScript
    apps/desktop/src/main/        主进程、sidecar 生命周期、安全 IPC
    apps/desktop/src/preload/     contextBridge
    apps/desktop/src/renderer/    工作台界面
    apps/sidecar/aida_sidecar/    Python 分析服务
    apps/sidecar/tests/           Python 测试
    packages/contracts/           TypeScript 公共契约

Renderer 已启用 contextIsolation 和 sandbox，不直接访问 Node.js、文件系统或数据库。preload 当前构建为 CommonJS index.cjs。

## 4. 当前输入与输出

### 4.1 界面已接通的输入

| 输入 | 当前支持 | 限制 |
| --- | --- | --- |
| 项目目录 | 创建、打开本地项目 | 没有最近项目列表和迁移 UI |
| 界面语言 | 左上角切换中文/English | 偏好保存在本机；新建项目、固定模板计划和报告同步使用所选语言 |
| 文件 | CSV、XLSX | 选择器接受 XLS，但缺少 xlrd，不能视为可靠支持 |
| 数据语义 | 为目标、正向结果、标识、分类、数值驱动和日期字段确认角色；填写业务背景与证据阈值 | 每个数据集保存一份配置；尚无领域词典和批量模板 |
| 分析目标 | 自然语言目标、是否包含脱敏样例 | UI 没有模型配置，通常返回可执行的固定模板计划 |
| Python | Monaco 中输入受限 Python | 同步执行，不是完整沙箱 |
| 数据库 | PostgreSQL/MySQL 连接信息 | 查询结果不能导入数据版本链 |
| SQL | 查询或写入语句 | UI 参数固定为空对象 |
| 报告 | 自动十章证据报告、管理/完整/技术三种模板、章节开关、Markdown 文本 | 包含分群差异、数值驱动因素、字段风险、证据等级和决策门槛；编辑后回退为手工单章内容 |

### 4.2 界面已接通的输出

| 输出 | 当前内容 | 限制 |
| --- | --- | --- |
| 数据预览 | schema、语义类型、总行数、前 100 行 | 无导入参数预览页 |
| 数据版本 | Parquet 原始和派生版本 | 无完整血缘视图与回退 UI |
| 数据审计 | 缺失、唯一性、常量、重复、范围、IQR 离群、内存 | 通过计划执行时持久化为 Artifact；手工快捷运行仍不持久化 |
| 清洗结果 | 预览后应用去重、缺失处理、类型转换、文本标准化和 IQR 截尾 | 预览不写版本；确认后创建非破坏式版本，无变化时不创建重复版本 |
| 分析计划 | 结构化步骤、逐步状态、耗时与错误 | 进程内后台顺序执行；界面轮询进度，可在步骤之间协作式取消 |
| 探索分析 | 数值描述统计、分类频数、相关矩阵 | 已有独立页、API、结果契约和计划步骤产物 |
| 统计结果 | 13 种常用统计方法及字段选择 | 完整假设检查、统一置信区间和多重比较仍待补充 |
| Python 结果 | JSON 结果或安全错误 | 未绑定步骤和数据版本 |
| Plotly 图表 | 按已确认字段角色自动生成目标分组图和数值分布图 | 未确认前阻止生成计划；无图表配置器和独立产物浏览器 |
| 数据库结果 | 字段、记录、行数、截断或提交结果 | 查询结果不进入 DatasetVersion |
| 报告与导出 | 十章结构化预览、质量评分、关键发现、分群/驱动因素分析、证据框架与行动建议；CSV/XLSX、含多图表 HTML/PDF 和可复现 ZIP | 使用已确认语义和用户阈值；结论生成仍为规则驱动，大文件仍经 Base64 IPC 传输 |
| 运行状态 | 最近操作、步骤状态、耗时、错误、数据行列数、后台任务进度 | 计划和产物可恢复；界面轮询任务状态，可在步骤之间取消，尚无 WebSocket 实时事件和步骤内部强制取消 |

## 5. 能力矩阵

### 5.1 项目与数据

| 能力 | 状态 | 说明 |
| --- | --- | --- |
| 创建/打开项目 | 界面可用 | manifest、SQLite 元数据和审计日志已建立 |
| CSV 导入 | 界面可用 | 探测编码，文件上限 100 MB |
| XLSX 导入 | 界面可用 | 默认第一张工作表，无工作表选择 UI |
| 旧 XLS 导入 | 骨架 | 允许后缀但没有 xlrd |
| Parquet 缓存 | 已实现 | 导入与派生版本均使用 Parquet |
| 数据指纹 | 已实现 | 列名和 pandas 行哈希生成 SHA-256 |
| 非破坏式版本链 | 部分可用 | 清洗创建 parentVersionId |
| 下游失效 | 未实现 | 上游变化不会自动使分析产物失效 |
| 清洗数据导出 | 界面可用 | 导出当前数据版本为 UTF-8 BOM CSV 或带元数据工作表的 XLSX |
| 字段语义配置 | 界面可用 | 自动建议后必须确认；持久化目标、正向值、各字段角色、业务背景与阈值，并写入审计日志 |

### 5.2 审计与清洗

| 能力 | 状态 | 说明 |
| --- | --- | --- |
| 数据审计 | 界面可用 | 缺失、重复、唯一、常量、范围、IQR 离群 |
| 去重 | 界面可用 | 可按全行或所选字段去重，先预览再创建新版本 |
| 删除/填补缺失 | 界面可用 | 支持固定值、均值、中位数、众数 |
| 类型转换 | 界面可用 | datetime、numeric、string、boolean |
| 文本标准化 | 界面可用 | trim 并合并空白 |
| 重命名/筛选 | 仅 API | mapping 与 pandas query |
| 异常值截尾 | 界面可用 | 所选字段按 IQR 边界 clip |
| 类别映射和复杂规则 | 未实现 | 缺少规则编辑、预览和撤销 |

### 5.3 EDA、统计与模型

| 能力 | 状态 | 说明 |
| --- | --- | --- |
| 基础 EDA | 界面可用 | 数值描述统计、分类频数和相关矩阵；尚无自动洞察与分布诊断 |
| Welch t 检验 | 界面可用 | 固定取前两个数值字段 |
| t、配对 t、Mann–Whitney、Wilcoxon | 界面可用 | 可选方法和数值字段，显示统计量、p 值与效应量（若方法支持） |
| 正态性、卡方、Fisher、ANOVA、Kruskal | 界面可用 | 有字段数量提示；更完整的假设检查仍待实现 |
| Pearson/Spearman/Kendall | 界面可用 | 可选两个数值字段；EDA 另有相关矩阵 |
| 多重比较修正 | 仅 API | 使用 statsmodels multipletests |
| 线性/逻辑回归 | 仅 API | 无变量角色、诊断和结果视图 |
| PCA | 仅 API | 返回方差解释率和成分 |
| K-Means/层次聚类 | 仅 API | 返回标签和数量 |
| 时间序列分解 | 仅 API | additive decomposition 和基础自相关 |
| 完整统计报告字段 | 部分实现 | CI、调整后 p 值和诊断未在所有方法中填充 |

### 5.4 AI 编排

| 能力 | 状态 | 说明 |
| --- | --- | --- |
| 本地安全上下文 | 已实现 | schema、审计摘要、已确认语义配置、可选 5 行脱敏样例 |
| 固定模板计划 | 界面可用 | 无模型配置时生成审计、EDA、统计、图表和报告 5 步计划 |
| 中英文界面与计划 | 界面可用 | 欢迎页、工作台、操作状态、固定模板计划和报告语言可即时切换 |
| OpenAI 风格计划生成 | 仅 API | 支持 base URL、模型、key、超时、语言 |
| 模型配置 UI | 未实现 | Renderer 不发送 model profile |
| 数据发送预览 UI | 未实现 | API 存在，界面未调用 |
| 计划审批 | 界面可用 | 确认后启动顺序执行；数据库写入仍保持独立审批边界 |
| 计划自动执行 | 部分可用 | 后台顺序执行、失败停止和进度轮询；计划、步骤、耗时、错误及 Artifact 写入 SQLite |
| 计划恢复 | 部分可用 | 重新打开项目会恢复最近计划和产物；检测到上次遗留的 running 状态时标记为中断，但不会自动续跑 |
| AI 错误解释/修复 | 未实现 | 尚无工具循环 |

### 5.5 Python 与任务系统

| 能力 | 状态 | 说明 |
| --- | --- | --- |
| Python AST 校验 | 界面可用 | 阻止系统、网络和未许可依赖 |
| Python 子进程执行 | 界面可用 | 过滤环境、项目目录和超时 |
| 内存/CPU/子进程限制 | 部分实现 | 不能视为恶意代码隔离 |
| TaskEvent 类型 | 骨架 | 公共契约已定义 |
| 后台任务状态 | 界面可用 | 计划启动后立即返回 task ID，界面轮询进度和持久化步骤状态 |
| WebSocket 任务事件 | 未实现 | 当前使用后台线程和 HTTP 轮询，TaskEvent/订阅接口仍是骨架 |
| 任务取消 | 部分实现 | 可请求取消计划并持久化 cancelled；仅在分析步骤边界生效，不能中断正在运行的单个 pandas/scipy 操作 |
| 崩溃/断点恢复 | 部分实现 | 步骤状态已持久化；旧 running 计划会标记为中断失败，但不会自动续跑 |

### 5.6 数据库

| 能力 | 状态 | 说明 |
| --- | --- | --- |
| PostgreSQL/MySQL 查询 | 界面可用 | UI 默认 1000 行、30 秒 |
| 参数化查询 | 仅 API | 后端支持，UI 固定传空参数 |
| Schema/table 浏览 | 仅 API | API 已有，界面未调用 |
| 写入审批预览 | 界面可用 | INSERT/UPDATE/DELETE/DDL/CALL |
| 写入事务与指纹 | 界面可用 | 审批 5 分钟有效，连接或 SQL 变化即拒绝 |
| 查询结果导入 | 未实现 | 不创建 DatasetRef/Version |
| 凭据安全存储 | 骨架 | safeStorage IPC 已有，表单未调用 |
| 真实数据库集成测试 | 未验证 | 自动测试没有真实 PostgreSQL/MySQL |

### 5.7 图表与报告

| 能力 | 状态 | 说明 |
| --- | --- | --- |
| 自动分布图 | 界面可用 | 按用户确认的字段角色生成目标分组图和最多两张数值分布图；未确认时仅显示建议，不生成计划 |
| scatter/box/line/violin | 仅 API | 无图表配置器 |
| PNG/SVG | 部分可用 | Plotly 工具栏可下载；图表定义可持久化，但图片文件没有统一管理 |
| HTML 报告 | 界面可用 | V3 封面、目录、质量评分、十章证据结构、最多三张内联 SVG 图表及完整追溯信息 |
| PDF 报告 | 界面可用 | V3 封面、目录、质量评分、A4 分页、中文字体、最多三张图表和追溯信息 |
| 可复现清单 | 界面可用 | ZIP 默认不含数据；可选附带当前版本 CSV/XLSX，并包含计划、产物、版本、环境和同模板十章 HTML/PDF 报告 |
| 结论引用追溯 | 部分可用 | 选择计划时校验报告引用的结果与图表 ID；尚无通用手工产物引用编辑器 |

## 6. 当前 API

    GET  /api/health
    POST /api/projects
    POST /api/projects/open
    POST /api/projects/audit-log
    POST /api/datasets/import
    POST /api/datasets/preview
    POST /api/datasets/export
    POST /api/analysis/audit
    POST /api/analysis/eda
    POST /api/analysis/clean
    POST /api/analysis/clean/preview
    POST /api/analysis/statistics
    POST /api/analysis/models
    POST /api/analysis/time-series
    POST /api/analysis/adjust-p-values
    POST /api/analysis/chart
    POST /api/analysis/semantics/get
    POST /api/analysis/semantics/save
    POST /api/analysis/python/validate
    POST /api/analysis/python/execute
    POST /api/ai/context-preview
    POST /api/ai/plan
    POST /api/analysis/plans/get
    POST /api/analysis/plans/latest
    POST /api/analysis/plans/execute
    POST /api/analysis/plans/tasks/start
    POST /api/analysis/plans/tasks/status
    POST /api/analysis/plans/tasks/cancel
    POST /api/database/schemas
    POST /api/database/query
    POST /api/database/write/prepare
    POST /api/database/write/execute
    POST /api/reports/build
    POST /api/reports/export
    POST /api/reports/reproducibility

公共 TypeScript 契约包括 ProjectManifest、DatasetRef、DatasetVersion、SemanticProfile、AnalysisPlan、AnalysisStep、AnalysisArtifact、EdaResult、TaskEvent、ApprovalRequest、StatisticalResult、ChartArtifact、ReportDocument、DataPreview 和 DesktopApi。

## 7. 当前不能完整验证产品能力的原因

1. 计划已转为进程内后台任务并支持进度轮询和步骤间取消，但没有持久化任务队列、WebSocket、步骤内部取消、重试和自动续跑。
2. 常用清洗和统计方法已有字段/方法 UI，但回归、PCA、聚类、时间序列和复杂清洗规则仍缺少参数界面。
3. Artifact 已统一持久化，报告导出会校验所选计划中的结果/图表引用，但没有独立产物浏览器和上游变更自动失效。
4. 数据库查询结果没有进入数据版本链。
5. 模型设置、发送预览和凭据管理 UI 未完成。
6. CSV/XLSX、含多图表 HTML/PDF 和可复现 ZIP 已接通；字段角色已可确认，但报告洞察仍为规则驱动，大数据仍以 Base64 经 IPC 传输。
7. 没有 Playwright Electron E2E 和干净 Windows 最终验收。

因此当前应称为：**具有后台自动分析与统一导出闭环的可执行 MVP 纵向切片**，而不是完成的自动化 AI 数据分析产品。

## 8. 已知问题与风险

### 高优先级

- **安装版本混淆**：曾确认 D:\AI Data Analyst\resources\app.asar 与旧 0.1.0 哈希一致。当前交付版本为 0.1.5；继续使用旧安装目录或旧快捷方式仍可能看到按钮无反应或旧报告。
- **安装包未签名**：Windows SmartScreen 或安全软件可能提示或拦截，尚无代码签名发布流程。
- **安装态 UI E2E 尚未完成**：win-unpacked 打包态已自动通过项目创建、CSV 导入、后台计划以及审计/EDA/统计/图表/报告产物闭环；尚未自动安装 NSIS 后通过真实按钮和文件对话框完成 Playwright E2E。

### 中优先级

- Desktop 为 0.1.5，sidecar 为 0.1.0，版本策略未统一。
- XLS 选择与实际依赖不一致。
- 数据库密码表单没有调用已有 safeStorage。
- 报告 Markdown 转换仍是轻量实现；字段角色已由用户确认，但质量评分、关键发现与图表选择仍是规则驱动，尚无领域词典、因果设计或模型复核。
- 大体积导出使用 Base64 IPC，后续需要流式或临时文件协议降低峰值内存。
- 部分公共类型与后端实际返回字段没有完全对齐。
- Python 测试存在一条 Starlette/httpx 弃用警告。
- 根目录尚未初始化 Git。

## 9. 验证记录

### 2026-09-03

语义配置与报告可信度增量执行：

    pnpm typecheck
    pnpm test
    pnpm build
    pnpm build:sidecar
    electron-builder --win nsis --config.electronDist=D:\Projects\AI-data-Analyst\tmp\electron-37.3.1
    release\win-unpacked\AI Data Analyst.exe --aida-golden-test

结果：TypeScript 类型检查、生产构建、sidecar 构建和 NSIS 0.1.5 打包通过；自动测试 `15 passed, 1 warning`，contracts 1 项测试通过。

- 右侧分析助手增加字段语义确认：目标字段、正向结果、标识列、分类/分群列、数值驱动列、日期列、业务背景和三项报告阈值。
- 语义配置按数据集写入 manifest 和哈希审计日志；重开项目或切换版本后可恢复，编辑后重新进入待确认状态。
- 未确认语义时禁用“生成分析计划”；确认后同一配置进入安全计划上下文，并统一驱动自动统计、图表、分群、驱动因素、质量风险和报告措辞。
- 保存接口拒绝不存在字段、重复角色、非数值驱动列和不存在的正向结果值。
- 修复多图表报告导出引用校验遗漏嵌套图表 ID 的问题，并增加 PDF 导出回归覆盖。
- 0.1.5 win-unpacked 黄金路径通过：`rowCount=4`、`semanticConfirmed=true`、`planStatus=completed`、五类 Artifact 完整、`reportSections=10`；CSV/XLSX/PDF/ZIP 分别为 86/5814/47125/66790 bytes，ZIP 默认不含数据。

### 2026-09-02

报告 V3 深度分析增量执行：

    pnpm typecheck
    apps\sidecar\.venv\Scripts\python.exe -m pytest apps\sidecar\tests -q
    pnpm build
    pnpm build:sidecar
    electron-builder --win nsis --config.electronDist=D:\Projects\AI-data-Analyst\tmp\electron-37.3.1

结果：TypeScript 类型检查、生产构建、sidecar 构建和 NSIS 0.1.4 打包通过；Python 测试 `14 passed, 1 warning in 4.71s`。

报告 V3 新增与验证：

- 报告扩展为十章，新增“驱动因素与分群分析”和“证据与决策框架”。
- 二元目标会自动比较最多四个分类分群，报告最高/最低组、样本量、结果率、百分点差和置信等级。
- 自动比较最多六个数值字段在目标组之间的均值、中位数、标准化效应量和样本量，并按效应强度排序。
- 数值关系从单个最强相关升级为前五关系排序，同时继续明确“相关不等于因果”。
- 数据质量从综合分数扩展到字段级风险登记，区分缺失、IQR 异常值、常量字段及高/中/低风险。
- 行动建议增加 P0/P1/P2、建议负责人和可验证验收标准；证据框架增加高/中/低置信等级及数据、证据、业务三道决策门槛。
- 7 页 A4 PDF 样例完成逐页原始分辨率检查，并修复章节标题孤立在页尾的问题；未发现裁切、重叠、黑块或乱码。

0.1.4 win-unpacked 黄金路径通过：`rowCount=4`，`planStatus=completed`，五类 Artifact 完整，`reportSections=10`；CSV/XLSX/PDF/ZIP 导出分别为 53/5752/43726/58826 bytes，ZIP 默认不含数据，退出后 `remaining_processes=0`。

### 2026-09-01

报告 V2 增量验证执行：

    pnpm typecheck
    apps\sidecar\.venv\Scripts\python.exe -m pytest apps\sidecar\tests -q
    pnpm build
    pnpm build:sidecar
    electron-builder --win nsis --config.electronDist=D:\Projects\AI-data-Analyst\tmp\electron-37.3.1

结果：TypeScript 类型检查、生产构建、sidecar 构建和 NSIS 0.1.3 打包通过；Python 测试 `14 passed, 1 warning in 4.77s`。

报告 V2 新增与验证：

- 自动报告升级为执行摘要、关键发现、数据质量评估、探索性发现、统计证据、可视化证据、行动建议、限制与方法八章。
- 增加 0–100 数据质量评分、3–5 条结构化关键发现、明确行动建议、管理/完整/技术三种模板，以及导出章节开关。
- 自动生成最多三张相关图表，每张图表附观察结论与解读边界；离线 HTML/PDF 可正确解码 Plotly typed-array 数据，不再把 `dtype`/`bdata` 误作图表类别。
- 6 页 A4 PDF 样例完成逐页原始分辨率视觉检查；目录、关键发现块、统计证据、三张图表、行动建议和追溯信息均无裁切、重叠、黑块或乱码，文本提取也验证了必要章节。
- 0.1.3 win-unpacked 黄金路径通过：4 行 CSV 完成 audit、eda、statistics、chart、report 五类 Artifact；报告包含 8 个章节；CSV/XLSX/PDF/ZIP 导出成功，ZIP 默认不含数据；退出后 `remaining_processes=0`。

黄金路径摘要：`rowCount=4`，`planStatus=completed`，`reportSections=8`，`csvBytes=53`，`xlsxBytes=5754`，`pdfBytes=41867`，`zipBytes=55798`。

此前 0.1.2 验证记录：

执行：

    pnpm typecheck
    apps\sidecar\.venv\Scripts\python.exe -m pytest apps\sidecar\tests -q
    pnpm build
    pnpm build:sidecar
    electron-builder --win nsis --config.electronDist=D:\Projects\AI-data-Analyst\tmp\electron-37.3.1

结果：TypeScript 类型检查和生产构建通过；最终 Python 测试 14 passed, 1 warning in 4.99s；Python sidecar 与 NSIS 0.1.2 安装包构建成功。

本次新增覆盖与修复：

- 脱敏样例中缺失值统一序列化为 JSON `null`，修复勾选“包含脱敏样例”后计划接口因 `NaN` 返回 500。
- 自动字段角色推断排除 PassengerId 等明显标识列；二元目标配合分类解释变量时优先执行卡方检验，否则回退到有意义数值字段的 Pearson 相关。
- 自动报告扩展为执行摘要、数据质量评估、探索性发现、统计证据、可视化与解读、限制与下一步六章，并包含目标分布、缺失概况、统计方法解释与追溯信息。
- 工作台报告预览保留结构化章节和 Plotly 图表；HTML 使用离线内联 SVG，PDF 与可复现 ZIP 内的 PDF 均包含可视化摘要。
- PDF 样例经文本提取、A4 元数据检查、两页渲染及逐页视觉检查，未发现裁切、重叠、黑块或孤立标题。

0.1.2 win-unpacked 黄金路径通过：使用含缺失值的 4 行 CSV，开启脱敏样例，完成 audit、eda、statistics、chart、report 五类 Artifact；报告包含 6 个章节和嵌入图表；CSV/XLSX/PDF/ZIP 文件签名通过，ZIP 默认不含数据；退出后 `remaining_processes=0`。

### 2026-08-31

执行：

    pnpm typecheck
    apps\sidecar\.venv\Scripts\python.exe -m pytest apps\sidecar\tests -q
    pnpm build

结果：TypeScript 类型检查和生产构建通过；Python 测试 12 passed, 1 warning in 4.21s。

本次新增覆盖：

- 清洗预览不写数据版本，确认后才创建派生版本。
- 正态性、Pearson 相关和卡方等界面开放方法可执行。
- 后台计划任务能够返回进度和最终五类 Artifact，取消会把计划与未执行步骤持久化为 cancelled。
- CSV/XLSX 数据导出、HTML/PDF 报告导出、引用校验，以及默认不含数据/可选附带数据的可复现 ZIP。
- PDF 经文本提取、A4 元数据检查、144 DPI 渲染和人工视觉检查，中文、分页、页脚与追溯信息正常。

最新 sidecar 与 NSIS 安装包已重建。win-unpacked 黄金路径测试通过：打包态 Renderer 通过 `window.aida` 创建临时项目、导入 4 行 CSV，由后台任务完成 audit、eda、statistics、chart、report 五类 Artifact，并验证 CSV/XLSX/PDF/ZIP 的文件签名与保存链路；测试结束后无残留 Electron/sidecar 进程。

### 2026-08-30

执行：

    pnpm typecheck

结果：通过。contracts 和 desktop TypeScript 类型检查成功。

执行：

    pnpm build

结果：通过。main、CommonJS preload 和 Renderer 生产构建成功。

执行：

    apps\sidecar\.venv\Scripts\python.exe -m pytest apps\sidecar\tests -q

结果：9 passed, 1 warning in 3.68s。

当前 Python 自动测试覆盖：

- 项目导入与版本血缘。
- sidecar 会话令牌。
- API 纵向项目流程。
- 审计质量信号。
- 清洗不修改原数据。
- Welch 检验包含效应量和 p 值。
- Python 许可依赖。
- 系统与网络逃逸入口阻止。
- 英文固定模板计划输出。
- 基础 EDA 数值、分类与相关矩阵结果。
- 固定计划从生成、持久化、顺序执行到 Artifact 恢复的纵向流程。

执行：

    pnpm build:sidecar
    electron-builder --win nsis --config.electronDist=<本机 Electron 37.3.1 缓存目录>

结果：通过。最新 Python sidecar、win-unpacked 和 NSIS 0.1.1 安装包已生成。常规 electron-builder 下载两次在 100% 后被服务器中断，最终显式使用已校验的本机 Electron 37.3.1 缓存完成打包；未修改代理或系统设置。

执行：

    release\win-unpacked\AI Data Analyst.exe --aida-smoke-test

结果：通过。打包态 sidecar 启动成功，Renderer 已加载，`window.aida` 和项目目录选择桥接均存在。

本次未执行：

- 安装后的 Electron UI 冒烟测试
- Playwright E2E
- 真实 PostgreSQL/MySQL 集成测试
- PDF、PNG、SVG、XLSX 导出测试

## 10. 命令与安装包

开发：

    pnpm dev

验证：

    pnpm typecheck
    pnpm test
    pnpm build

Windows 打包：

    pnpm package:win

最新安装包位置：

    apps\desktop\release\AI Data Analyst Setup 0.1.5.exe

2026-09-03 17:48 最新构建：250,567,909 bytes，SHA-256 `B6C26C001993100FD1D9403CFA5C21DAB8895F661B703EA88F56D2A3684C3130`。该安装包未数字签名，已通过语义确认、缺失值脱敏样例、十章证据报告、多图表和 CSV/XLSX/PDF/ZIP 的 win-unpacked 自动黄金路径，但尚未执行 NSIS 安装后的真实 UI 点击验收。

apps\desktop\dist 中是旧构建，不应继续用于验证。

## 11. 下一轮设计应优先决定

这里只记录设计问题，不代表授权实现。

1. 如何从现有进程内后台顺序任务升级为可恢复队列与依赖 DAG。
2. 每种 AnalysisMethod 的参数 UI、适用性检查和失败/跳过语义。
3. Artifact 浏览、引用校验、下游失效和清理策略。
4. 如何在现有可确认语义配置上增加领域词典、配置模板、因果/时间口径和跨数据集映射。
5. 后台任务、WebSocket、取消、超时、重试和恢复。
6. 哪些步骤可自动执行，哪些需要审批。
7. 假设检查、效应量、置信区间和多重比较的统一规范。
8. 数据库查询的数据集化、刷新、采样、指纹和血缘。
9. 连接配置和密码的保存策略。
10. 大文件流式导出、可自由编排的多图布局，以及可保存的自定义报告模板。
11. Desktop/sidecar 版本、旧包隔离、签名、升级与回滚。
12. 如何为已接通的后台任务与导出黄金路径建立安装态自动验收。

## 12. 黄金路径现状与下一阶段

当前源码态已经接通基础纵向切片：

    创建/打开项目
      → 导入 CSV/XLSX
      → 生成并确认固定分析计划
      → 后台顺序执行审计、EDA、统计、图表和报告
      → 持久化计划、步骤状态、耗时、错误与 Artifact
      → 重新打开项目并恢复最近计划和结果

下一阶段需要把它扩展为可中断、可配置和可安装验收的黄金路径：

    创建项目
      → 导入 CSV/XLSX
      → 查看模型数据发送预览
      → 生成并确认分析计划
      → 后台执行审计、清洗、EDA、统计和图表（基础任务与步骤间取消已完成）
      → 修改上游步骤并重跑
      → 自动标记下游产物失效
      → 生成带版本、结果引用、质量评分、分群/驱动因素和多图表的十章 HTML/PDF 报告（已完成 V3 基础链路）
      → 导出 CSV/XLSX 和可复现 ZIP（已完成基础链路）

只有扩展路径能在安装后的 Windows 应用中端到端完成，才应把状态改为“可验证 MVP”。

## 13. 决策日志

| 日期 | 决策 | 原因 | 状态 |
| --- | --- | --- | --- |
| 2026-08-29 | Windows 优先，Electron + React + TypeScript + Python sidecar | 桌面体验结合 Python 数据生态 | 已采用 |
| 2026-08-29 | Renderer 不直接访问 Node、文件系统或数据库 | 缩小安全边界 | 已采用 |
| 2026-08-29 | 原始数据只读，清洗产生 Parquet 派生版本 | 可追溯、非破坏式 | 部分完成 |
| 2026-08-29 | 数据库写入逐次审批并校验 SQL 指纹 | 避免计划审批扩大为写权限 | 已实现基础流程 |
| 2026-08-29 | preload 改为 CommonJS index.cjs | 修复 sandbox 窗口中按钮无响应 | 代码已修复，安装验证待完成 |
| 2026-08-30 | 本文档作为跨对话状态基线 | 避免事实和设计决策丢失 | 已建立 |
| 2026-08-30 | 界面语言由左上角全局切换，并同步计划与报告输出语言 | 保证中英文体验一致，且不覆盖用户已编辑内容 | 已实现并通过构建与测试 |
| 2026-08-30 | 先采用同步顺序状态机打通计划执行，再升级后台任务/DAG | 用最小纵向切片验证计划、步骤和产物契约 | 已实现基础执行器 |
| 2026-08-30 | 计划、步骤状态与 Artifact 存入项目 SQLite | 支持审计追踪和重新打开项目后的结果恢复 | 已实现，失效与清理待完成 |
| 2026-08-31 | 清洗操作先预览、确认后再创建派生版本 | 避免配置错误和无变化操作污染版本链 | 已实现常用操作 |
| 2026-08-31 | 统计页开放方法和字段选择 | 将已有统计 API 转化为普通用户可执行能力 | 已实现 13 种方法入口 |
| 2026-08-31 | 计划执行改为进程内后台任务、HTTP 轮询进度和协作式取消 | 先解除长请求对界面的阻塞并保留现有同步接口兼容性 | 已实现基础链路，WebSocket 与步骤内部取消待完成 |
| 2026-08-31 | win-unpacked 增加自动黄金路径参数 | 在每次交付前验证打包态 sidecar、preload、项目、导入、任务与五类产物 | 已实现；NSIS 安装态 Playwright E2E 待完成 |
| 2026-08-31 | 统一导出经 preload 保存 Base64 二进制结果 | 保持 sandbox Renderer 不直接访问 Node/文件系统，并复用受控保存对话框 | 已实现；大文件流式传输待完成 |
| 2026-08-31 | 可复现 ZIP 默认不包含数据并移除内部存储路径 | 遵守本地优先和最小披露原则，同时允许用户显式附带当前版本数据 | 已实现 CSV/XLSX 可选项 |
| 2026-08-31 | PDF 使用 ReportLab 与 Windows 中文字体，并在导出前校验计划引用 | 获得离线、可分页、可追溯的正式报告，同时阻止悬空结果/图表引用 | 已实现并完成视觉验收 |
| 2026-09-01 | 所有模型上下文先递归清理非有限数值 | JSON 不允许 `NaN`，缺失值应以 `null` 表示，避免计划接口返回 500 | 已实现并增加回归测试 |
| 2026-09-01 | 自动分析按字段角色选择统计方法和图表，并排除明显标识列 | 避免 PassengerId 等 ID 字段主导统计结论，使 Titanic 类数据优先分析目标与解释变量 | 已实现启发式版本 |
| 2026-09-01 | 报告统一为六章结构，并在工作台、HTML、PDF 和 ZIP 中保留主要图表 | 把数据规模罗列升级为可解释、可追溯且适合审阅的分析交付物 | 已实现基础版并完成 PDF 视觉验收 |
| 2026-09-01 | Desktop 版本提升至 0.1.2 | 明确区分旧 0.1.1 安装包与本轮报告/计划修复 | 已构建并通过 win-unpacked 黄金路径 |
| 2026-09-01 | 报告 V2 采用八章结构、质量评分、结构化关键发现和行动建议 | 让报告从结果罗列升级为可用于审阅和决策的交付物 | 已实现并完成 PDF 逐页视觉验收 |
| 2026-09-01 | 自动报告最多生成三张图表并为每张图表提供观察与边界 | 提高证据密度，同时避免图表脱离解释语境 | 已实现启发式版本 |
| 2026-09-01 | 报告模板使用章节 audience 标签与导出章节筛选 | 同一分析结果可面向管理者、完整审阅和技术审阅复用 | 已实现管理/完整/技术三种模板 |
| 2026-09-01 | 离线导出显式解码 Plotly typed-array 数据 | 防止 HTML/PDF 将序列化元数据误绘制为类别 | 已实现并增加回归测试 |
| 2026-09-01 | Desktop 版本提升至 0.1.3 | 明确区分报告 V2 与 0.1.2 六章基础报告 | 已构建并通过 win-unpacked 黄金路径 |
| 2026-09-02 | 报告 V3 新增分群差异、数值驱动因素和前五相关关系 | 从描述结果升级为解释“差异在哪里、强度多大、证据多稳” | 已实现并增加回归测试 |
| 2026-09-02 | 字段级风险登记和证据/决策框架进入正式报告 | 将数据质量问题与决策前置条件显式化，避免仅凭 p 值或单图行动 | 已实现 |
| 2026-09-02 | 行动建议统一包含优先级、责任角色和验收标准 | 使报告建议可分派、可复核，而不是泛化措辞 | 已实现基础规则 |
| 2026-09-02 | Desktop 版本提升至 0.1.4 | 明确区分十章证据报告 V3 与 0.1.3 报告 V2 | 已构建并通过 win-unpacked 黄金路径 |
| 2026-09-03 | 自动推断改为“建议后确认”的数据集语义配置 | 避免系统误把 ID、目标或分群字段用于统计结论，并让业务阈值进入报告 | 已实现并通过持久化、执行与导出回归 |
| 2026-09-03 | 计划生成前必须确认语义配置 | 防止用户在字段含义未核对时直接产出貌似完整但口径错误的报告 | 已在界面禁用计划按钮并提供双语配置入口 |
| 2026-09-03 | Desktop 版本提升至 0.1.5 | 明确区分语义确认版本与 0.1.4 的纯启发式报告 | 已构建并通过 win-unpacked 黄金路径 |

## 14. 新对话接续提示词

    请先完整阅读 D:\Projects\AI-data-Analyst\PROJECT_PROGRESS.md，
    把它作为当前项目事实基线。
    本轮先做软件设计，不要直接实现。
    请明确区分界面可用、仅 API、骨架和未实现能力。
    设计确认后，把架构决策、阶段目标和验收标准回写到该文档，
    并保留历史问题和决策记录。
