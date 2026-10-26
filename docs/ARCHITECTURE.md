# Architecture / 架构

AcademicUpdater uses a Python HTTP server, SQLite and browser-native HTML/CSS/JavaScript. There is no frontend build step. `cryptography` supports identity-token verification; the rest of the runtime mainly uses Python's standard library.

应用由 Python HTTP 服务、SQLite 和原生 HTML/CSS/JavaScript 组成，不需要前端构建。

| Area / 模块 | Responsibility / 职责 |
| --- | --- |
| `run.py` | Loopback server startup, instance lock and scheduler lifecycle / 启动、实例锁、计划任务 |
| `academic_updater/server.py` | Local API routes, request validation and static files / 本机接口及静态文件 |
| `academic_updater/storage.py` | SQLite schema, migrations, identifiers and persistent application state / 数据库及迁移 |
| `academic_updater/sources.py` | Crossref, arXiv and RSS/Atom collection / 来源采集 |
| `academic_updater/metadata.py` | Author/journal metadata and journal metrics / 元数据及期刊指标 |
| `academic_updater/service.py` | Daily collection, analysis and resumable jobs / 日常任务及恢复 |
| `academic_updater/history.py` | Saved historical searches, paging, assessment and timeline / 历史检索及时间线 |
| `academic_updater/ai.py` | Structured field interpretation, provider requests and output validation / AI 请求及验证 |
| `academic_updater/credentials.py` | OAuth/OIDC and Windows encrypted credentials / 登录与加密凭据 |
| `academic_updater/network.py` | HTTP helpers and outbound request checks / 网络请求 |
| `static/` | Bilingual interface and bundled guide / 双语界面与指南 |
| `tests/` | Core behavior, upgrade and history regression coverage / 核心、升级及历史检索测试 |

Collection normalizes source metadata before reconciling identifiers into the library. Analysis uses a saved research-scope version and provider settings. Long-running tasks save intermediate progress so restarting does not require redoing already saved results. Historical searches keep their own scope and links to library records rather than overwriting the daily field.

来源资料先规范化，再依据标识符与资料库合并。分析绑定保存的研究范围版本和模型设置；长任务保存中间进度。历史检索有独立范围，并关联资料库记录，不覆盖日常研究范围。

When extending the application, preserve existing data and migration paths, keep credentials out of exports, and expose source failures and incomplete coverage. Use isolated data directories during development; opening the production database through application initialization can trigger task-recovery logic.

开发时请保持迁移兼容、避免导出凭据、明确显示来源失败与覆盖限制。测试使用独立数据目录；直接初始化生产数据库会触发任务恢复逻辑。
