# Active Calculus pilot attribution

The formula excerpts and their deliberately corrupted variants in
`active_calculus_cases.json` are adapted from **Active Calculus Single Variable,
Second Edition**, © 2012–2025 Matthew Boelkins. Contributing authors: David Austin,
Christina Safranski and Steven Schlicker; production editor: Mitchel T. Keller.

- [Book](https://activecalculus.org/acs2e/)
- [Pinned source and license statement](https://github.com/active-calculus/active-calculus-single-mbx/blob/441c5b56853ec898d8adf6ed792f7d7056473862/source/bibinfo.xml)
- License: [Creative Commons Attribution-ShareAlike 4.0 International](https://creativecommons.org/licenses/by-sa/4.0/).
- Source revision: `441c5b56853ec898d8adf6ed792f7d7056473862`.

These excerpts, modifications and the resulting pilot data are distributed under
**CC-BY-SA-4.0**, separately from the project's AGPL-3.0-only code and original
documentation. The authors do not endorse this project or its results.

Changes: whitespace normalization; six paired variants remove the final closing
brace or append a trailing plus. Every record gives the exact source location,
whole-source-file SHA-256 and mutation. No original diagram or full chapter is
bundled. Unmodified source formulas are not asserted to contain errors; injected
variants are not naturally occurring OCR errors. Reference text is for reviewers,
not a completed human annotation.

## Reproduction

From the repository root, download the four small pinned source files and
recreate the catalog in an unused output location:

```bash
python scripts/prepare_open_cases.py --fetch \
  --source-dir work/active-calculus-source \
  --out work/active-calculus-reproduced.json
cmp samples/research/active_calculus_cases.json work/active-calculus-reproduced.json
```

`--fetch` explicitly permits public HTTP retrieval. Without it the generator
only reads an existing source directory. It verifies all source hashes,
including the license statement, before extraction. The fixed lexical rule is
stored in the catalog and generator; it does not call a checker or model while
selecting formulas. Three early chapters from one book give a narrow convenience
sample, not a representative or independently annotated benchmark.

Redistributed pilot outputs containing these formulas or adaptations must carry
this notice and the license link. Human review remains pending until independently
completed and imported using the [review protocol](README.md).
