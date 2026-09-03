# Python sidecar

所有 `/api/*` 路由要求 `Authorization: Bearer <session token>`。Electron 为每次启动生成随机令牌并仅绑定 `127.0.0.1`。

主要路由：

- `/api/projects`, `/api/datasets/import`, `/api/datasets/preview`
- `/api/analysis/audit`, `/clean`, `/statistics`, `/models`, `/time-series`, `/chart`
- `/api/analysis/python/validate`, `/execute`
- `/api/ai/context-preview`, `/ai/plan`
- `/api/database/query`, `/database/write/prepare`, `/database/write/execute`
- `/api/reports/build`, `/reports/reproducibility`

