# Third-party notices

Project-authored code, documentation and synthetic fixtures are licensed under
AGPL-3.0-only by CacinieP. The components below retain their own notices and terms.

## TeXWizard interface reference

The local Studio interface adapts the layout and visual styling of
[`原型-GPT5.1.html`](https://github.com/CacinieP/TeXWizard/blob/main/%E5%8E%9F%E5%9E%8B-GPT5.1.html)
from [CacinieP/TeXWizard](https://github.com/CacinieP/TeXWizard),
source blob `aab7f51a3932e28e281c4068928b36021eb652a1`.
The reference provides interface styling; the document, inference, checking,
review, persistence and preview behavior is implemented in this repository.

The reference's MIT notice is preserved below. Modifications in this repository
remain covered by this repository's AGPL-3.0-only terms.

```text
MIT License

Copyright (c) 2026 CacinieP

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

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
`samples/docs`, `samples/paper-01`, `samples/exam-01`, `samples/report-01`, and the
checker regression catalog in `samples/evaluation` are synthetic test fixtures.
The historical `GTM249-p101-120.tex` textbook extract and both of its blob versions
have been removed from the current tree and reachable `main` history because no
redistribution grant is recorded. Old clones and private pre-rewrite backups may still contain it; exclude that
extract from redistributed copies. Cleanup details are in the
[security record](docs/security-scan-notes.md).

## Active Calculus research pilot

`samples/research/active_calculus_cases.json` contains formula excerpts and
explicitly modified variants from *Active Calculus Single Variable, Second
Edition*, © 2012–2025 Matthew Boelkins and contributors. The dataset and formula-
containing pilot outputs retain **CC-BY-SA-4.0**, not the project's AGPL license.
Exact pinned sources, changes, attribution and reproduction are in
[ACTIVE_CALCULUS_NOTICE.md](samples/research/ACTIVE_CALCULUS_NOTICE.md).
