# Contributing / 参与贡献

Thank you for helping improve AcademicUpdater. Issues and pull requests in English or Chinese are welcome. You do not need to write code to contribute: reproducible bug reports, source suggestions, translations and documentation improvements are useful too.

欢迎用中文或英文提交 Issue 和 PR。除了代码，也欢迎可复现的问题反馈、来源建议、翻译和文档改进。

## Propose a change / 提出改进

Use the bug-report or feature-request template. Describe the research workflow, the problem, and the behavior you expect. For a large feature, discuss scope in an issue before investing in implementation. Small, focused fixes can go straight to a PR.

请描述使用场景、当前问题和期望行为。大型功能先讨论范围；小而明确的修复可直接提交 PR。请尊重其他参与者，对具体问题展开讨论。

## Development / 开发

1. Fork the repository and create a branch from `main`.
2. Install Python 3.11+ and the dependencies in `requirements.txt`, preferably in `.venv`.
3. Run a development instance with a separate database:

   ```sh
   python run.py --port 8766 --data-dir ./work/dev-data --no-scheduler
   ```

4. Make a focused change and run the checks in the README. Add meaningful regression coverage for changed behavior. Manual UI checks should cover both interface languages when relevant.
5. Open a pull request explaining the problem, resulting behavior and validation. Include screenshots for visible changes using synthetic data.

请先 Fork 并从 `main` 创建分支，使用独立的数据目录。提交时说明问题、修改后的行为和验证结果；界面改动请检查中英文，并用虚构数据截图。

## Design expectations / 设计约定

- Keep personal data local by default. Make provider requests and AI usage explicit; do not silently change providers or trigger paid fallbacks.
- Preserve existing databases. Use additive migrations where practical, cover older data with upgrade tests, and preserve notes, saved flags and prior analyses.
- Retain checkpoints for long-running work. A source failure must not discard successfully saved results.
- Validate external responses and treat retrieved text as untrusted data. Keep source URLs and evidence traceable.
- Do not invent missing metadata or impact factors. Show uncertainty and source limitations honestly.
- Keep user-facing strings bilingual and accessible. Relevance must be expressed in text as well as color.

默认保留本机隐私，保持旧库兼容、任务可恢复、来源可追溯。缺失元数据不要编造；界面文字同时维护中英文，颜色不能成为唯一提示。

## Before submitting / 提交前

- Run the backend tests, JavaScript syntax checks and `scripts/check_public_tree.py`.
- Review `git diff --cached` and `git status`. The public-tree check is a basic safeguard, not a complete secret scanner.
- Never commit `data/`, databases, exports of a personal library, notes, research prompts, credentials, `.env` files, access tokens, private logs or local validation records.
- Use temporary databases and mocked provider responses in tests. Do not require a contributor's personal account or paid quota for automated checks.
- Include only material you have the right to contribute. Contributions are provided under the project's [MIT license](LICENSE).

提交前检查实际暂存内容，不要上传个人论文库、研究提示词、笔记、凭据或日志。自动测试应使用临时数据和模拟响应，不依赖个人账号或付费额度。贡献内容适用项目 MIT 许可证。

For security issues, read [SECURITY.md](SECURITY.md) before posting details publicly.
