# TeXada Studio Local

Edit LaTeX, transcribe images or PDFs, check formulas and simple totals, review repair diffs, then save, compile and export on your own computer.

Studio is a local workspace opened in your browser. Documents and run records stay on your machine; image transcription and model candidates use the local model service you configure.

[中文](README.md) · [Start](#start) · [Configuration](#configuration) · [Local guide](docs/local-studio.md) · [AgentSkills](docs/agent-skills.md) · [Documentation](docs/index.md)

![TeXada Studio: local LaTeX source and a compiled Chinese PDF](assets/studio-workspace.png)

Current UI, using the repository's synthetic `welcome.tex` sample; November 4, 2026.

This remains a local, single-user development candidate, with no formal release for this revision. See the [current verification record](docs/current-validation.md); historical videos and experiments retain their own dates and versions.

## What you can do

| Task | Workflow |
| --- | --- |
| Manage documents | Import or create `.tex`, save, rename, and delete; saved changes survive refresh |
| Transcribe sources | Import PNG, JPEG, WebP, or PDF, up to five pages per request; review the candidate before creating a document |
| Edit and inspect | LaTeX highlighting, snippets and symbols, five document templates, find/replace, section outline, command palette, formula syntax checks, and simple totals |
| Review repairs | Source-preserving deterministic syntax repairs first; model candidates require syntax and mutation-scope checks before explicit review |
| Preview and export | Compile the current document, browse PDF pages, and export PDF, `.tex`, or an audit report |
| Connect a local model | Save a loopback endpoint and model name, then explicitly check availability |

Saving checks the file revision before replacing it. Edits invalidate an older PDF, so export requires compilation of the current content. Repository samples remain unchanged; saving creates a local copy.

The activity rail opens document navigation, search, image/PDF import and Agent review. Check results appear in the bottom problems panel; create and review repair candidates through Agent. The Agent drawer and bottom problems/log panels can collapse. The export menu offers the current LaTeX and its compiled PDF.

## Start

Requires **Python 3.11+**. The example uses an installed `python3.13`; substitute another supported version if needed:

```bash
git clone https://github.com/CacinieP/TeXada-Studio-with-agentskills.git
cd TeXada-Studio-with-agentskills
python3.13 -m venv .venv
.venv/bin/python -m pip install -r webui/requirements.txt
.venv/bin/python scripts/run-local-studio.py --check
./scripts/start-local-studio.command
```

On macOS, you can double-click `scripts/start-local-studio.command` after installing dependencies. The launcher opens your browser. Editor assets are bundled with the source; no frontend build is required. First-time preparation of dependencies, model weights, fonts, and TeX resources needs network access — see [first-time setup](docs/local-studio.md#首次准备与离线使用).

macOS can also generate a desktop window app (own window plus Dock entry, reusing a running session or starting its own backend): `.venv/bin/python desktop/build_app.py` — see the [desktop window guide](desktop/README.md) (Chinese).

## Configuration

### Local model service

Local mode accepts only OpenAI-compatible endpoints (`/v1/models` and `/v1/chat/completions`) on `localhost`, `127.0.0.1`, or `[::1]`. It needs no API key and never falls back to a cloud model. Three ways to connect:

1. **In the UI**: status bar "local model" → save the endpoint and model name → run the explicit connection check. The connection details are kept in the user data directory.
2. **Reuse an existing service at launch** (for example an Ollama instance already running locally):

   ```bash
   .venv/bin/python scripts/run-local-studio.py \
     --base-url http://127.0.0.1:11434/v1 \
     --model minicpm-v4.7-1b:latest --no-auto-model
   ```

   The model name must exactly match an id returned by your service's `/v1/models`; on exit the launcher stops only model processes it started itself.
3. **Auto-start local weights**: by default the launcher looks for the GGUF and projector under `~/.texada/models/` and requires `llama-server`; pass `--gguf`/`--mmproj` to point at explicit paths.

Image/PDF transcription requires an endpoint that actually supports `image_url` — appearing in the model list is not verification. Deterministic syntax repairs need no model. See the [model guide](docs/local-studio.md#本机模型连接) for downloads, default paths, and optional parameters.

### Optional tools and TeX resources

| Feature | Additional requirements |
| --- | --- |
| Editing and deterministic checks | Python dependencies above; editor assets are bundled |
| Model candidates and image transcription | A local MiniCPM-V 4.7 1B service; automatic startup also needs `llama-server`, GGUF and projector. Deterministic repairs need no model |
| PDF import | Poppler's `pdfinfo` and `pdftoppm` |
| PDF compilation and preview | Tectonic, Poppler, required TeX cache, and fonts |

Tectonic can bootstrap itself: click "Download Tectonic" in the Studio settings dialog, or run `.venv/bin/python scripts/install_local_tools.py` — a pinned official release, SHA256-verified, installed to `~/.texada/bin` and picked up by the launcher's PATH, effective in a running session without restart. Poppler still needs a system package manager (macOS: `brew install poppler`); for other platforms see the [troubleshooting guide](docs/troubleshooting.md).

Studio compiles only against cached TeX resources and never downloads packages while processing documents. First-time preparation:

```bash
.venv/bin/python scripts/prepare-local-tex.py --download-resources
```

Re-run without the flag afterwards for an offline check.

### Editor preferences and local data

Font size, word wrap, and minimap preferences persist in your browser. Documents, run records, and connection details live in the user data directory; the private browser entry is written to an owner-only `session.json`, credentials are never printed, and the entry is renewed on every launch. See [local data and recovery](docs/local-studio.md#本地数据与恢复).

## First document

1. Open `welcome.tex` or `math-clean.tex` and choose **Check**. Once compiler dependencies are ready, choose **Compile**.
2. Open `math-delimiters.tex`, generate a candidate, review the diff, and accept or reject it. Save after adopting a candidate.
3. Refresh to check persistence, then export the current `.tex` or PDF.
4. Select an authorized image or PDF, start recognition, review it against the original, and create a document from the candidate.

Use **Save** or `⌘/Ctrl+S` to persist edits. OCR and repair candidates do not automatically replace the source.

Formula repairs follow a source-preservation policy: candidates must not change numbers, variables, or operators or delete terms; unambiguous delimiters are closed and rechecked first. See the [repair-quality record](docs/formula-repair-quality.md) for the policy and evidence.

Open the command palette with `Cmd/Ctrl+Shift+P`, navigate sections through the outline, and use the editor's find/replace panels. Font size, word wrap, and minimap preferences persist in your browser. Local LaTeX snippets — common commands, theorem-class environments, Greek letters and math symbols — need no model call; `Ctrl+Space` can request suggestions. Sectioning commands, preamble/definition directives (including `\input`/`\include` file splits), and cross-reference keys each get their own color, so the document's structural modules stand out. The editor folds documents by TeX structure: environments pair with their `\end`, and sections close at the next heading. The sidebar's "new from template" action creates documents from five offline skeletons: blank article, lecture notes, exam paper, Beamer, and English article. The status bar shows cursor, selection, and word counts.

## Scope and boundaries

Syntax acceptance, compilation, faithful transcription, and mathematical correctness are separate judgments: a false equation can pass both syntax and compilation. Review OCR, repairs, and table findings against the original.

The scanner handles common inline and display math and skips comments and literal text; complex alignments, unknown macros, and unsupported structures remain for human review. The current unit of work is one `.tex` file; multi-file projects and collaboration are outside this local version's scope. See [checking and review boundaries](docs/local-studio.md#检查与审阅边界) and the [roadmap](docs/roadmap.md).

## Documentation and technical material

Start with the [local guide](docs/local-studio.md) and the [troubleshooting guide](docs/troubleshooting.md). Further entry points:

- [Studio operation Skill](skills/texada-studio/SKILL.md) and [AgentSkills guide](docs/agent-skills.md): workspace operations, formula/table/OCR inputs and review boundaries.
- [Current validation](docs/current-validation.md), [architecture](docs/architecture.md), [CLI Harness](harness/README.md), and [source packaging](docs/source-package.md).
- The complete list of casebooks, validation history, Skill experiments, series notes, and historical demos lives in the [documentation index](docs/index.md).

The legacy `run-minicpm-v47-studio.sh` explicitly selects a cloud API workflow. See [compatibility notes](docs/local-studio.md#旧云-api-入口与实验功能); its results are separate from local inference acceptance.

Original code, documentation, and synthetic fixtures use **AGPL-3.0-only**. Third-party notices remain in [LICENSE](LICENSE), [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md), and the [Active Calculus notice](samples/research/ACTIVE_CALCULUS_NOTICE.md). See [CONTRIBUTING.md](CONTRIBUTING.md) and [SUPPORT.md](SUPPORT.md).

Maintainer [@CacinieP](https://github.com/CacinieP). Citation metadata is in [CITATION.cff](CITATION.cff). Detailed technical guides are currently in Chinese.
