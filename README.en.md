# TeXada Studio with Agent Skills

**Find LaTeX syntax and simple table-total problems, inspect repair candidates, and decide what to adopt.**

[中文](README.md) · [Documentation map (中文)](docs/index.md) · [Demo and evidence](docs/demo.md) · [Casebook (中文)](docs/casebook.md) · [Contributing](CONTRIBUTING.md)

TeXada combines a Monaco editor, deterministic checks, local text-model suggestions, Tectonic previews, and human review. It is intended for teachers, research writers, and developers working with trusted `.tex` documents.

**Experimental prototype; no formal release yet.** The repository is currently private. Access requires authorization. Project-authored source is licensed under [AGPL-3.0-only](LICENSE); third-party components retain their licenses. This is a single-process application for trusted users, not a public multi-user service.

![Source, PDF preview, and candidate review](docs/images/studio-overview.png)

## What it does

- A table can compile successfully while `45 + 60` is incorrectly recorded as `115`. Studio locates the inconsistency and proposes `105` using deterministic calculation.
- For an incomplete subscript such as `a_`, a local text model proposes a candidate. SymPy checks syntax and Tectonic checks compilation. Neither proves that `a_1` is what the author intended.
- Repair candidates open in a diff view. Users explicitly adopt them and can export an audit report.
- The separate CLI reads an existing `layout.json`, records node events, writes a report, and skips terminal nodes when rerun.

Automatic OCR, image-based repair, general agent planning, complex tables, project uploads, and multi-user isolation are not implemented. CLI real-model mode attempts formula repair only; table repair is currently available through test fixtures, while Studio can recompute simple totals. CLI runs do not invoke Tectonic.

## Try the offline fixture

Python 3.10+ is required; Python 3.13 is the validated environment. These are POSIX-shell commands, tested on macOS; use WSL or translate environment activation on Windows. A fresh dependency installation needs network access. This fixture needs no GPU, model, font installation, or TeX compiler.

```bash
git clone https://github.com/CacinieP/TeXada-Studio-with-agentskills.git
cd TeXada-Studio-with-agentskills
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r harness/requirements.txt
PYTHONPATH=harness python -m docforensics run samples \
  --state state/quickstart --fixture-repairs samples/fixture_repairs.json
```

Expected: `exam-01 OK=3`, `paper-01 OK=2 NEEDS_HUMAN=1`, `report-01 OK=2`. Open `state/quickstart/report.md`; it identifies the provider as an offline test double. Rerun the same command to exercise resume. Use a new state directory after changing inputs or providers. These counts are workflow checks, not model benchmarks.

Private clones require repository access and configured GitHub authentication. An authorized source archive is an alternative.

## Run the checker cases

After installing the Python dependencies above, run 27 synthetic formula and table cases:

```bash
python scripts/evaluate_cases.py --outdir state/evaluation-01
```

The [runner](scripts/evaluate_cases.py) writes `report.json` and `report.md` into a new directory and refuses to overwrite existing evidence. Cases cover syntax, Decimal totals, invalid inputs, and unsupported numeric formats. Contract matches, semantic boundaries, and known gaps are reported separately; none is a model-accuracy score. No model, OCR, or network call is made during execution.

See the [case definitions and instructions](samples/evaluation/README.md), [casebook](docs/casebook.md), and [Skills technical report](docs/skills-technical-report.md) for interpretation and limitations. These detailed documents are currently in Chinese.

## Run Studio locally

With the virtual environment activated:

```bash
python -m pip install -r webui/requirements.txt
export DEMO_TOKEN="$(python -c 'import secrets; print(secrets.token_urlsafe(32))')"
printf 'http://127.0.0.1:8888/studio?token=%s&file=report-01.tex\n' "$DEMO_TOKEN"
python -m uvicorn app:app --app-dir webui --host 127.0.0.1 --port 8888
```

Open the printed private local URL; stop with `Ctrl-C`. Do not share the token. A missing token prevents startup. `.env` is not loaded automatically; after editing a copy of `.env.example`, load it with `set -a; . ./.env; set +a`.

Additional capabilities require:

| Capability | Requirement |
| --- | --- |
| PDF compilation and first-page preview | Tectonic and `pdftoppm` on `PATH`; `TECTONIC` may specify a compiler path |
| Chinese sample compilation | `Noto Sans CJK SC` and required TeX packages |
| Formula repair in Studio | Local Ollama-compatible endpoint fixed at `127.0.0.1:11434`; an installed model selected by `VLM_MODEL` |

Run `ollama list` before selecting a model. The default `qwen3.8:27b-q4_K_M` is the recorded test-node label, not a guaranteed downloadable or preinstalled model. Model calls send text only. First-time Tectonic compilation may download packages. Studio bundles Monaco 0.52.2; the legacy dashboard at `/` still uses a KaTeX CDN.

Use a single Uvicorn worker. Jobs are kept in process memory. Uploaded files and results live under ignored `state/`; an upload with the same name replaces the previous upload. TeX compilation is not a sandbox. Read [SECURITY.md](SECURITY.md) before sharing an installation.

## Verify and contribute

```bash
python -m pip install -r webui/requirements-test.txt
python -m unittest discover -s webui -p 'test_*.py' -v
python -m unittest discover -s harness/tests -p 'test_*.py' -v
python -m unittest discover -s scripts -p test_evaluate_cases.py -v
python -m unittest discover -s skills/latex-cleanup/tests -p 'test_*.py' -v
node webui/test_studio.cjs
node skills/latex-cleanup/tests/test_audit_math.cjs
```

JavaScript checks use Node.js 22. Harness tests cover checker failures and report evidence; runner tests cover timeouts, output protocols, and report-directory protection. These checks do not require a GPU and do not replace real-browser or TeX compilation checks. There is no automated CI workflow or response-time guarantee.

Start with a synthetic edge-case sample, documentation correction, or a scoped task in the [roadmap](docs/roadmap.md). The [documentation map](docs/index.md) identifies the primary document for each topic and the pages that must change together. Include the exact commit, environment, reproduction steps, and actual verification results. Never attach private documents or credentials.

Maintained by [@CacinieP](https://github.com/CacinieP), team LinguistsWantTech (邓一纯, 刘丰华). See [CITATION.cff](CITATION.cff) for citation metadata and include your actual commit. [Release preparation](docs/open-source-release.md) and [third-party notices](THIRD_PARTY_NOTICES.md) apply before redistribution.
