# Third-party notices

Project-authored code, documentation and synthetic fixtures are licensed under
AGPL-3.0-only by CacinieP. The components below retain their own notices and terms.

## Monaco Editor 0.52.2

- Upstream: https://github.com/microsoft/monaco-editor/tree/v0.52.2
- Copyright (c) 2016 - present Microsoft Corporation.
- License: MIT, preserved verbatim at [webui/static/monaco/0.52.2/LICENSE](webui/static/monaco/0.52.2/LICENSE).
- Distribution: upstream `min/vs/` files, including its worker, CSS and font; no source modifications.
- Integrity and reproduction: [vendor documentation](webui/static/monaco/README.md), `SHA256SUMS`, and `scripts/vendor_monaco.py`.

## latex-cleanup snapshot

`skills/latex-cleanup/` was imported from the same maintainer's
`CacinieP/latex-cleanup` project. The copy included here is distributed under this
repository's AGPL-3.0-only license. This does not change the license of a separate
upstream checkout. See [PROVENANCE.md](skills/latex-cleanup/PROVENANCE.md) for revision and extraction scope.

## Separately installed or remotely loaded components

Python dependencies (FastAPI, Starlette, Uvicorn, HTTPX, SymPy and antlr4), Node.js,
Tectonic, Poppler, fonts, Ollama and model weights are not vendored here. Consult
their installed distributions for their licenses. Model weights and user-provided
documents are not covered by this repository's AGPL license.

The legacy dashboard `webui/index.html` loads KaTeX 0.16.11 from a CDN; it is not
bundled in this source tree. Its source and MIT license are available in the
[KaTeX repository](https://github.com/KaTeX/KaTeX/tree/v0.16.11).

## Samples and historical material

The retained demonstration documents, layout records and placeholder crops in
`samples/` are synthetic test fixtures. They do not establish OCR or model accuracy.
The historical `GTM249-p101-120.tex` textbook extract has been removed from the
current tree because no redistribution grant is recorded. The project license
does not grant rights to that extract in older commits. Do not publish the Git
history until the release checklist's history review is resolved.
