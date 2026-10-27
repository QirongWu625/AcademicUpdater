<p align="center"><img src="static/logo.png" alt="AcademicUpdater logo" width="112"></p>

# AcademicUpdater

[English](README.md) | [简体中文](README.zh-CN.md)

An AI-powered, local-first research assistant for tracking papers and industry updates, discovering influential and foundational work, and organizing a deduplicated personal library.

**Version 1.6.0 · MIT license · Contributions welcome**

## Automatic updates and parallel work

Daily updates and independent history searches can run together. Paper assessment shares a fair limit of **3 concurrent AI requests**, adjustable from 1 to 8 in **Personal profile → Sources & schedule**. History processes up to 10 papers per request. Each task has its own pause/resume control; completed results are retained. Up to 8 independent jobs can be active. Model speed, reasoning effort, provider limits and the existing daily request budget still apply.

Enable **Windows login startup** to launch in the background after signing in. The scheduler catches up that day's missed update after the configured time, and the next day's collection can start while an older analysis continues. The computer must be awake and online. Unexpected process exits resume from saved progress after restart; transient network failures use bounded retries, daily-budget pauses continue after local midnight, and manual pauses stay paused. Recent activity shows interruption causes and retry times. After five automatic job retries, or for authentication/configuration errors, resolve the displayed issue and resume manually.

**Learn from saved papers** refines the understood field before a new collection only when the current saved set changes, including unsaving or deleting/restoring saved papers. It recomputes from your original applied field and explicit exclusions, so removed papers stop contributing positive evidence. No change means no learning request; removing all saves restores the baseline without AI. For more than 80 saved papers, an evenly distributed sample is used and its size is shown. Your original prompt, pending drafts, old analyses and independently configured historical searches remain available. If learning fails, collection uses the existing field and reports the deferred update.

## Manage your collection

Delete a library record or a saved historical search to move it to **Trash**, then restore it whenever needed. Open **Trash** in the sidebar, then switch between **Library records** and **Historical searches**. Search and restoration update immediately. Deleting a search keeps its papers in the library. Deleting a record hides it from Today, history results and normal exports; collection will not automatically reimport it. Saved notes, analyses and search progress are retained. Pause any running task before deleting or restoring records. Database backups include trash. A timeline citing removed papers is hidden until those papers are restored or the search is run again.

## Starting a historical search

Interpreting your field with AI saves a **draft**, not a paper search. Review the understood field and queries, then choose **Confirm field and search papers**. The app distinguishes searches not started, source failures, pending AI review and an empty shortlist. You can inspect all retrieved candidates without weakening the influential/foundational criteria.

Quoted phrases, AND, OR and parentheses work in history queries. arXiv receives its native Boolean syntax; Crossref gets separate ranked text queries with a shared candidate cap. See the [arXiv query manual](https://info.arxiv.org/help/api/user-manual.html#51-details-of-query-construction) and [Crossref API documentation](https://github.com/Crossref/rest-api-doc).

When you resume an older search with Boolean queries, affected source queries restart once with the corrected syntax. Saved papers and assessments remain; previous cursors are archived in the search export. Paused or deleted searches do not restart automatically.

## See it in action

Screenshots of the **real application** using synthetic demonstration records. Titles, authors, citation counts and assessments below are illustrative; no personal library or account is shown.

![Today: relevance-ranked research updates](docs/images/today-en.png)

<details>
<summary>Research history: a saved shortlist and referenced timeline</summary>

![Research history with influential and foundational candidates](docs/images/history-en.png)

</details>

[Suggest a feature](https://github.com/QirongWu625/AcademicUpdater/issues/new?template=feature_request.yml) · [Report a bug](https://github.com/QirongWu625/AcademicUpdater/issues/new?template=bug_report.yml) · [Contribute a pull request](CONTRIBUTING.md)

## What it does

- **Today:** collect from Crossref, arXiv and public RSS/Atom feeds; rank analyzed items by relevance with color and text labels.
- **Research field:** describe your interests in a prompt, then review and edit the AI's interpretation, bilingual field names, keywords, exclusions and search queries before applying it.
- **Library:** save papers and updates with authors, journal, notes, reading status and source versions. Filter immediately and sort by date, title, first-author surname, journal, relevance or impact factor.
- **Research history:** save a separate historical search, prioritize influential and foundational candidates, and build a referenced timeline from the shortlist. Searches and results can be reopened and exported.
- **Journal metrics:** enter or import impact factors with a year and source. Missing values remain missing; no commercial journal-metrics dataset is bundled.
- **AI settings:** use an eligible ChatGPT sign-in connection, an OpenAI API key, or a compatible local model server. Select the model and its supported reasoning effort.
- **Persistent work:** SQLite storage, identifier-based deduplication, backups, exports, per-paper checkpoints, pause/resume and recovery after interruption.
- **English and Chinese:** switch the interface language and configure the summary language separately. Personal profile contains research scope, sources, schedule and AI connection.

## Install and run

Requires **Python 3.11 or later**. Windows is the primary desktop platform. The core application can run on macOS/Linux; encrypted saved credentials currently use Windows DPAPI, so use an environment API key or a compatible local model there.

Download the source or clone this repository, then open a terminal in its folder.

### Windows

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python run.py --open
```

After installing dependencies, you can also double-click `Start.cmd`. It prefers the project's `.venv` and runs the application in the background. `Stop.cmd` stops that background instance; closing the browser does not stop it.

### macOS / Linux

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python run.py --open
```

The application opens at **http://127.0.0.1:8765/**. Use Ctrl+C to stop a foreground instance. It binds to loopback and is intended for a single user on their own computer.

## First use

1. Open **Personal profile → AI connection**. Choose a provider, connect it, load models and select a supported model and reasoning effort. A ChatGPT subscription does not include OpenAI API billing; sign-in availability depends on account eligibility and the provider. The application never silently switches to the paid API.
2. Open **Research field**, enter your prompt, review the interpreted field and search terms, and apply them. You can also enter a field and queries manually without AI.
3. Configure **Sources & schedule** with paper sources and RSS feeds for the industry or conference updates you want. Start collection and review Today.
4. Use **Research history** for a saved historical search without changing your daily scope. Start with a small result cap to check query quality before collecting a broad field.

The in-app bilingual [guide](http://127.0.0.1:8765/guide) is available while the app runs.

For environment-based OpenAI credentials, set `OPENAI_API_KEY` in the environment that launches the application and choose the API provider. Do not put credentials in source files. Local servers must support the application's OpenAI-compatible chat-completions requests and structured responses.

## How historical selection works

New searches default to focused discovery. Crossref combines citation-ranked and relevance-ranked candidates. Relevant papers qualify through a configurable citation threshold (default 100) or an abstract-supported foundational contribution. The default view and timeline show only shortlisted papers; other candidates remain available for review. Citation counts carry their source and observation date, and foundational labels remain candidates for expert verification. Existing saved searches are preserved. See [the selection rules](docs/RESEARCH_HISTORY.md).

## Data and upgrades

- `data/academicupdater.sqlite3` stores your library, settings, research scopes, notes, analyses and historical searches.
- `data/backups/` contains pre-collection database backups, at most one per UTC date.
- `data/credentials.dpapi` contains saved credentials encrypted for the current Windows user. It is excluded from library exports.
- JSONL/CSV library exports are useful for data exchange; the SQLite database is the complete application backup.

Before updating, stop the application and back up the complete `data/` folder. Replace the source files while preserving `data/`, then restart. Schema migrations retain existing papers, saved status, notes and analyses. Credentials copied to another computer or OS account may not be decryptable; reconnect there. Avoid running two versions against the same database.

Interrupted collection/analysis jobs resume on startup. Jobs paused manually or at a usage limit require **Resume**. A request interrupted before its result was saved may be sent again; saved results are checkpointed.

The public repository intentionally contains no personal library, credentials or runtime logs. Use a separate data folder for experiments:

```sh
python run.py --port 8766 --data-dir ./work/dev-data --no-scheduler
```

## Coverage and limitations

- Daily scheduling works while the application is running and the computer is awake. The default is 08:00 at a fixed UTC+10 offset; configure your own time and offset. No OS startup task is installed.
- AI works from titles and abstracts/descriptions, not full-text review. Assessments and timeline narratives need human checking; they do not prove historical priority.
- “All matches” means results retrievable for the chosen queries and source limits, not every paper in a field. Broad queries may return weak matches; source limits and failures are displayed. The history overview uses up to 80 relevant papers sampled across publication years; all candidates and individual assessments remain saved.
- Matching DOI, arXiv ID, source ID or canonical URL can reconcile records. Similar titles alone are not automatically merged.
- Impact factors are user-supplied, year-specific values. Preprints and other inapplicable record types do not receive an inferred journal IF.
- This is a local personal application, not a hosted multi-user service. Do not expose its port publicly without designing and reviewing an appropriate authentication and deployment layer.

## Contribute

Feature ideas, bug reports, translations, documentation and pull requests are welcome. Please read [CONTRIBUTING.md](CONTRIBUTING.md). Issue templates support English and Chinese; either language is welcome.

Useful contribution areas include additional source connectors, better historical search quality, cross-platform credential storage, accessibility and import/export interoperability. Please discuss large architectural changes before implementing them.

```sh
python -m pip install -r requirements.txt
python -m unittest discover -s tests -v
python scripts/check_public_tree.py
node --check static/app.js
node --check static/history.js
node --check static/i18n.js
```

Node.js is needed only for the JavaScript syntax checks, not for running the application. Tests use isolated temporary databases and mocked provider responses; they do not require personal AI credentials. GitHub Actions is configured to run backend tests and syntax checks on Windows and Ubuntu with Python 3.11 and 3.13.

See [architecture](docs/ARCHITECTURE.md), [changes](CHANGELOG.md), and [security guidance](SECURITY.md). The code is licensed under [MIT](LICENSE). Third-party content and services remain subject to their own terms.
