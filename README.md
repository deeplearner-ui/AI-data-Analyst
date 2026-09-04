# AI Data Analyst

Windows 优先、本地优先的 AI 数据分析桌面助手。React/Electron 提供项目工作台，Python sidecar 完成数据审计、非破坏式清洗、统计推断、建模、时间序列与 Plotly 可视化。

## 已实现能力

- CSV/XLSX 导入、类型推断、100 MB 文件限制和 Parquet 版本缓存。
- SQLite 项目元数据、数据血缘和 SHA-256 哈希链审计日志。
- 可确认的数据集语义配置：目标/正向结果、标识、分群、数值驱动和日期角色，以及业务背景与报告阈值。
- 缺失、重复、常量列、唯一性、范围与 IQR 离群值审计。
- 结构化清洗操作及不可变版本链。
- 统计方法自动推荐与适用性检查；支持 t/Welch、配对检验、Mann–Whitney、Wilcoxon、卡方、Fisher、ANOVA、Kruskal 和相关分析。
- 显式呈现假设诊断、估计值与可用置信区间、效应量、统计/实际显著性，并支持 Holm、FDR 和 Bonferroni 多重比较修正。
- OLS、逻辑回归、PCA、K-Means、层次聚类和基础时间序列分解。
- Plotly 交互图表、受限 Python 编辑器、十章证据报告、PDF/HTML 导出与可复现清单。
- 本地规则引擎生成分析计划；不提供外部模型网络出口，分析数据不会发送到第三方模型。
- PostgreSQL/MySQL 查询；所有写操作必须经过短时审批令牌和 SQL 指纹校验后在事务中提交。
- Electron context isolation、sandbox Renderer、随机 sidecar 会话令牌和 Windows 加密凭据存储。
- 导入时检测邮箱、手机号、身份证号、银行卡号、IP 及敏感字段名；检测结果不包含原始命中值，敏感数据导出需显式确认。
- 主进程和工作流持久日志会脱敏本地路径、密钥、邮箱、电话与身份证号，并限制单条诊断长度。

## 开发启动

```powershell
pnpm install
cd apps\sidecar
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
cd ..\..
pnpm dev
```

可设置 `AIDA_PYTHON` 指向自定义 Python；默认使用 `apps/sidecar/.venv/Scripts/python.exe`。

## 验证

```powershell
pnpm typecheck
pnpm build
apps\sidecar\.venv\Scripts\python.exe -m pytest apps\sidecar\tests -q
```

## Windows 安装包

```powershell
pnpm package:win
```

该命令先用 PyInstaller 生成独立 Python sidecar，再由 electron-builder 生成 NSIS 安装包。打包产物不依赖目标机器上的 Node.js 或 Python。

## 安全边界

自动 Python 执行使用 AST 许可策略、隔离子进程、过滤后的环境、项目工作目录和超时。它用于降低模型生成代码的误操作风险，不是针对恶意代码的虚拟机级隔离。数据库凭据不会写入项目；外部数据库事务提交后不能由应用自动撤销。个人信息检测是风险提示，不替代人工合规审查；报告和数据在用户确认后仍可导出。
