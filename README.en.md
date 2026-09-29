# TeXada Studio with Agent Skills

Check formula syntax and simple table totals in a LaTeX editor, review repair candidates, and decide what to adopt.

[中文](README.md) · [Demo video](https://www.bilibili.com/video/BV16Kan6rEGv/) · [WeChat article](https://mp.weixin.qq.com/s/kDkmQp12pBSPkqw2UpeLXw) · [Skill design and technical report](docs/skills-technical-report.md) · [Documentation](docs/index.md) · [Casebook](docs/casebook.md)

TeXada combines Monaco, deterministic checks, a local text model, and Tectonic previews. Formula candidates appear as a diff; after review, users can adopt a candidate and export `.tex`, PDF, and an audit report.

This is a reproducible experimental prototype under AGPL-3.0-only, with no formal release yet. Deployment uses one process and a shared token for trusted users.

![Source, preview, and candidate review](docs/images/studio-overview.png)

## Demo and project materials

An entry in the third NVIDIA DGX Spark Hackathon, Agent Skills Development Challenge.

| Material | Link |
| --- | --- |
| Live demonstration | [Bilibili video](https://www.bilibili.com/video/BV16Kan6rEGv/): about 3:42, including the model wait, diff review, and manual adoption; [recording and evidence](docs/dynamic-demo.md) |
| Project overview | [Project report](docs/project-report.md): use cases, workflow, and implementation scope |
| Skill technical report | [Design and implementation](docs/skills-technical-report.md): responsibilities, state contracts, loading, extension, and validation |
| Competition article | [Published on WeChat (Chinese)](https://mp.weixin.qq.com/s/kDkmQp12pBSPkqw2UpeLXw) · [Repository text](docs/technical-article.md) |
| Reproducible results | [Casebook](docs/casebook.md) · [Validation](docs/validation.md) · [Skill comparison](docs/skills-pilot-analysis.md) |

TeXada organizes instructions, checking scripts, and cases into Skill task packages that can be maintained separately. The Python host explicitly loads instructions and manages states, allowing at most two candidate requests per formula. The checker evaluates each candidate, and the user reviews it before deciding whether to adopt it; requests, candidates, and check results are saved. Currently, only the `doc-formula-verify` instructions enter the model's system message; other task packages use their own scripts or operating procedures.

## 1. Run a sample without a model

Requires Python 3.11+; the validated version is 3.13. Commands use a POSIX shell; Windows users can use WSL. The initial dependency installation needs network access.

```bash
git clone https://github.com/CacinieP/TeXada-Studio-with-agentskills.git
cd TeXada-Studio-with-agentskills
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r harness/requirements.txt
PYTHONPATH=harness python -m docforensics run samples \
  --state state/quickstart --fixture-repairs samples/fixture_repairs.json
```

Expected output:

```text
exam-01: OK=3 NEEDS_HUMAN=0
paper-01: OK=2 NEEDS_HUMAN=1
report-01: OK=2 NEEDS_HUMAN=0
report: state/quickstart/report.md
```

Open `state/quickstart/report.md` for candidates and items needing review. This mode reads preset repairs to exercise the workflow; it needs no GPU, model, or TeX installation. Rerun the same command to check resume behavior. See the [CLI manual](harness/README.md).

## 2. Open Studio

Install the Web dependencies in the same environment and start the server:

```bash
python -m pip install -r webui/requirements.txt
export DEMO_TOKEN="$(python -c 'import secrets; print(secrets.token_urlsafe(32))')"
printf 'http://127.0.0.1:8888/studio?token=%s&file=math-clean.tex\n' "$DEMO_TOKEN"
python -m uvicorn app:app --app-dir webui --host 127.0.0.1 --port 8888 --workers 1
```

Open the printed local URL; stop with `Ctrl-C`. Keep the token private. The application does not load `.env` automatically: run `set -a; . ./.env; set +a` when using a configuration file. Available settings are in [`.env.example`](.env.example).

Start with `math-clean.tex`, switch to `math-delimiters.tex` for a missing closing delimiter, then inspect the valid syntax but incorrect integral in `math-semantics.tex`. The library contains [13 Studio samples](samples/README.md).

| Feature | Dependencies |
| --- | --- |
| Editing, formula analysis, simple table checks | The Python dependencies above; Monaco 0.52.2 is bundled |
| PDF compilation and first-page preview | [Tectonic](https://tectonic-typesetting.github.io/) and Poppler's `pdftoppm` on `PATH`; `TECTONIC` can specify the compiler path |
| Chinese sample compilation | `Noto Sans CJK SC`; the new English math samples do not need this font |
| Formula candidate generation | The local model service in the next section |

Tectonic may download TeX packages on first compilation. See [troubleshooting](docs/troubleshooting.md) for setup issues and the [deployment guide](deploy/README.md) for persistent operation and upgrades.

## 3. Connect a real model

Prepare a local Ollama-compatible service and select an installed model tag:

```bash
ollama list
curl --fail http://127.0.0.1:11434/v1/models
export VLM_MODEL='REPLACE_WITH_AN_INSTALLED_MODEL_TAG'
export SKILL_MODE=on
```

Start or restart Studio from that terminal. Its model endpoint is fixed at `127.0.0.1:11434`. It sends formula text and allows up to two candidate attempts. `SKILL_MODE=on` adds the formula Skill's instructions to the system message; `off` provides the comparison mode. Defaults differ between entry points, so set the model explicitly.

To use the same model from the CLI:

```bash
PYTHONPATH=harness python -m docforensics run samples \
  --state state/model-01 \
  --vlm http://127.0.0.1:11434 --vlm-model "$VLM_MODEL" --skill-mode on
```

Candidates and counts depend on the model. Reports go to the `--state` directory. The [CLI manual](harness/README.md) covers Skill records, request parameters, and resume rules.

## 4. Reproduce tests and evaluations

```bash
python -m pip install -r webui/requirements-test.txt
python -m unittest discover -s webui -p 'test_*.py' -v
python -m unittest discover -s harness/tests -p 'test_*.py' -v
python -m unittest discover -s scripts -p 'test_evaluate_*.py' -v
python -m unittest discover -s skills/latex-cleanup/tests -p 'test_*.py' -v
node webui/test_studio.cjs
node skills/latex-cleanup/tests/test_audit_math.cjs
```

JavaScript tests use Node.js 22. These regression tests need no model. Studio sample compilation is listed below; latex-cleanup compilation tests have a [separate guide](skills/latex-cleanup/tests/CASES.md).

| Goal | Command or guide | Output |
| --- | --- | --- |
| 27 deterministic checker cases | `python scripts/evaluate_cases.py --outdir state/evaluation-01` | `report.json`, `report.md` |
| Three-group Skills execution plan | The dry-run command below | Configuration, per-case results, report, blank review sheet |
| Same-model comparison with / without Skill | [Research protocol](samples/research/README.md) | A new run directory; semantic review is imported separately |
| 12 Studio compilation inputs | `python scripts/compile_studio_cases.py --outdir state/studio-compile-01` | `report.json`, source copies, logs, and PDFs; [requirements and expectations](docs/evaluation-results/studio-latex/README.md) |
| Existing experiments and compile checks | [Validation records](docs/validation.md) | Fixed inputs, environment, and original results |

```bash
python scripts/evaluate_skills.py run \
  --cases samples/research/smoke_cases.json \
  --outdir work/research-dry-01 --mode dry-run
```

Evaluation and compilation runners require a new output directory. Dry-run validates the plan only. Each guide explains how to interpret checker, fixture, and real-model results.

## Scope and data

Studio accepts a single `.tex`, extracts same-line `$...$` formulas, and checks simple tables. The CLI accepts existing `layout.json` inputs and runs formula and table checks. Studio can recompute simple totals; the CLI's real-model provider repairs formulas only. PDF preview shows the first page. Project uploads, OCR, multiline formula extraction, and multi-user isolation are on the [roadmap](docs/roadmap.md).

Syntax acceptance, successful compilation, and mathematical correctness are separate judgments. For example, `∫₀¹ x dx = 1` can pass the first two checks although the correct value is `1/2`. Review candidates against the intended meaning.

Uploads are saved in `state/studio/documents/`; uploading the same name replaces an earlier upload. Task records are in `state/studio/jobs/`. Completed tasks can be queried by job ID; interrupted tasks must be started again. Deploy for trusted documents; see [SECURITY.md](SECURITY.md) for the TeX compilation trust boundary.

## Development and license

Code entry points: [`webui/`](webui/) for Studio, [`harness/`](harness/) for the CLI, [`skills/`](skills/) for instructions and checkers, [`samples/`](samples/) for runnable inputs, and [`scripts/`](scripts/) for evaluation and packaging. See [CONTRIBUTING.md](CONTRIBUTING.md) and [SUPPORT.md](SUPPORT.md).

Original code, documentation, and synthetic samples use **AGPL-3.0-only**; see [LICENSE](LICENSE). Third-party components and textbook samples retain their licenses, documented in [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) and the [Active Calculus notice](samples/research/ACTIVE_CALCULUS_NOTICE.md). Modified network deployments must provide access to corresponding source.

Team LinguistsWantTech: captain 邓一纯, member 刘丰华; maintainer [@CacinieP](https://github.com/CacinieP). Citation metadata is in [CITATION.cff](CITATION.cff). Project and release materials are listed in the [documentation index](docs/index.md). Detailed guides are currently in Chinese.
