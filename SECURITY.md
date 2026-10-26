# Security / 安全说明

AcademicUpdater is a local, single-user application. It binds to `127.0.0.1`; it is not a hardened public hosting service. Keep the latest available version and back up your data before upgrades.

AcademicUpdater 面向本机单用户使用，仅监听 `127.0.0.1`，不适合作为未经额外保护的公开托管服务。升级前请备份数据。

## Data handling / 数据处理

The SQLite database contains personal research scopes, saved records, notes and analyses. Treat the whole `data/` directory as private. Saved credentials use Windows user-bound DPAPI. Other platforms should use environment credentials or a local model rather than expecting encrypted credential persistence.

When you request remote AI analysis, the application sends the relevant research scope and paper metadata to the selected provider. Source collection sends your search queries to the selected sources. These requests are not made private merely because the database is local.

数据库包含研究范围、资料、笔记和分析，请把完整的 `data/` 视为私人数据。远程 AI 分析会把相关研究范围及论文元数据发送给所选服务；采集会把检索词发送给所选来源。本机存储不代表这些网络请求不会发送内容。

## Reporting / 报告问题

Do not put credentials, private databases, exploit details or personal research content in a public issue. If GitHub's **Report a vulnerability** option is available in this repository's Security tab, use it. Otherwise, open an issue containing only a high-level description and ask the maintainer to arrange a private reporting channel before sending sensitive details.

不要在公开 Issue 中粘贴密钥、私人数据库、可利用的漏洞细节或私人研究内容。如果仓库 Security 页面提供 **Report a vulnerability**，请使用该入口；否则只提交不含敏感细节的概述，先与维护者约定私密报告渠道。

If a credential was exposed, revoke it with its provider. Removing it from a later commit does not remove it from Git history or existing clones. Do not upload real credentials to demonstrate a bug.

凭据泄露后应在服务方撤销；后续提交删除文件不会清除历史记录及他人的克隆。复现问题不需要上传真实凭据。
