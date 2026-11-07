# Studio allowlisted Skill selection experiment

The sidebar has a separate **模型选择公式/表格 Skill** checkbox, initially unchecked.
The API accepts `skill_selection: true` independently of `planner_mode` and
persists both flags at job acceptance. With selection alone, Python keeps the
fixed check→candidate→human sequence. With both experiments enabled, the model
also chooses constrained actions. Leaving both disabled preserves the default
fixed formula instruction loading and existing workflow.

The catalog consists of exactly two versioned `capability.json` files:

| ID | Capability | Accepted input |
|---|---|---|
| `doc-formula-verify` | text formula syntax review | bounded LaTeX string |
| `doc-table-audit` | simple tabular numeric totals | bounded supplied document text |

Each declares `schema_version`, semantic `version`, node kind, input JSON schema
and supported action names. The host accepts only those two known contracts;
arbitrary paths, schema variants, tools, OCR capabilities and unknown metadata
schema versions are rejected. Metadata is read and hashed before selection; loading the
catalog never reads a `SKILL.md` body. The selecting model sees the metadata,
node ID/kind and current revision, and returns an ID or null with that revision.
All calls use the already configured MiniCPM checkpoint and credential environment.

The host validates the exact response schema, current revision, allowlist and
node applicability before reading the chosen body. Path confinement, UTF-8/body
size, frontmatter name and metadata/body version matching are checked. Selection
and loading are separate `SKILL_SELECTED` and `SKILL_LOADED` events. The latter
records the metadata hash, body hash, checker hash, ID, capability and version.
A body/version/path failure has a rejection event and reaches no checker or
repair callback. Formula repair receives the selected formula instructions only
after loading; table instructions are loaded for the existing deterministic host,
whose candidates still come from Decimal arithmetic rather than a model.

Null/declined selection, unknown IDs, mismatched kinds, malformed responses,
no applicable capability, unavailable catalogs and load failures preserve the
source and become visible human requests. Selecting a Skill grants no execution
on its own: revision/parameter/action mask checks still gate each host callback.
The model cannot load arbitrary files or run Skill scripts by returning a path.
Selection, planning and text repair consume the same per-job 12-request budget;
selection calls count even when the model refuses or the network fails.

The downloadable report includes selected versions/hashes, rejected choices,
loads and human requests. Neither selection nor syntax acceptance validates
mathematical meaning. This experiment adds no extraction, re-cropping, image
inspection, cross-page reconstruction or automatic source adoption.

Use the shared reproducible paired runner:

```sh
python scripts/evaluate_studio_planner.py --provider fixture --output work/skill-paired.json
# Optional model comparison over the same public synthetic cases:
python scripts/evaluate_studio_planner.py --provider live --output work/skill-live-paired.json
```

It runs fixed, planner, fixed-with-selection, and planner-with-selection arms on
each identical source, recording checker completion, rejected actions/choices,
actual calls, reservations, loaded versions/hashes and elapsed time. The default
fixture is routing evidence, not inference or a quality claim. A live run is
explicitly tagged; no private documents, PDF compiler or OCR is involved. The
five cases are too small to justify a general quality/performance claim or to
turn either experiment on by default.
