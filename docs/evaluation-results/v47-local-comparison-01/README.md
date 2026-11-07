# Local MiniCPM-V 4.7: 35B Q4, 1B Q4 and 1B F16

Measured on 2026-11-08 (Asia/Shanghai). The 1B main run uses **non-quantized F16**
weights, as requested; the earlier Q4 download is retained as a comparison.
F16 here means full-precision inference weights, not full-parameter fine-tuning.
The 1B F16 language weights are 2,024,372,320 bytes and the F16 vision projector
is 1,110,117,984 bytes (about 3.13 GB combined on disk, not a peak RAM estimate).
All model and projector SHA-256 values match the official upstream metadata.

## Results

| Variant | Candidate syntax pass, Skill off | Candidate syntax pass, Skill on | Median repair request, off / on | One-page OCR |
| --- | ---: | ---: | ---: | ---: |
| 35B-A3B Q4_K_M | 5 / 7 | 5 / 7 | 0.776 / 0.805 s | 3.827 s |
| 1B Q4_K_M | 1 / 7 | 1 / 7 | 0.214 / 0.218 s | 3.492 s |
| **1B F16** | **3 / 7** | **2 / 7** | **0.264 / 0.264 s** | **2.546 s** |

The 12-case Active Calculus catalog has five initially parseable inputs (no
repair model call) and seven inputs that the checker sends for repair. The
denominator above is seven, not twelve. Cases can have two attempts. Initial
parseable controls are not counted as successful model repairs. Pass means the
candidate survives the current parser; all semantic review remains pending.
For example, the original AV interval notation is rejected by this parser,
which is a checker-support limitation as well as a repair-workflow challenge.
Do not interpret these ratios as general mathematical accuracy.

The separate three-case smoke catalog has one repair input (`a_+b`). None of
the variants resolved it in either arm. Five initially parseable Active
Calculus inputs and two smoke controls are skipped by design, not successful
model calls. Skill instructions did not improve the aggregate pass count here;
this run does not establish a general Skill effect.

1B F16 improves the candidate contract outcome over 1B Q4 on this small catalog,
but still produces unresolved repairs and malformed JSON. 35B returns parseable
candidates for five of seven inputs in both arms. This supports keeping the
repair default unchanged until broader review rather than switching to 1B
based only on size or latency.

## OCR observations

The same original synthetic `samples/ocr/inlines-01.png` is sent through the
shared OpenAI-compatible transport with the same prompt and 2048-token budget.
All three return `OK`, which means text candidates exist, not that they are
correct. The outputs have 10, 11 and 10 lines respectively; line count is not an
accuracy metric. Both 1B outputs confuse the integral sign with `f` (F16:
`f^1_j0 x^2 dx=1/3`), whereas the 35B output retains the integral. Neither 1B
output is ready for automatic mathematical adoption. No CER/WER or OCR accuracy
score is inferred from a single unannotated page. Each result is one request;
latencies are observations, not statistically stable speed rankings.

## Ollama versus independent server

An unchanged 35B Ollama retest (same tag, 4096-token budget, 120-second HTTP
limit) again timed out once per model arm, with no candidates. The original
Ollama process was left running. Its status showed another OCR runner
stopping during the beginning of the retest. This is evidence of environment
state, not proof of the timeout's cause.

The **same local 35B GGUF and projector** then ran successfully through a
separate loopback llama.cpp server. Thus the earlier claim that this Mac cannot
run the model is false. Backend, scheduler state, and explicit reasoning-off
configuration differ between these runs; the experiment does not isolate which
one caused the Ollama timeout. It does not show that CUDA is required.

## Reproduction and evidence

- [Configuration](configuration.json): llama.cpp version/commit, context 8192,
  one slot, 99 requested GPU layers, reasoning off; the device enumerates an
  Apple Metal GPU. Existing host services were not shut down. Our model
  requests ran sequentially, but this is not an isolated hardware benchmark.
- [Machine-readable summary](summary.json).
- [35B identity](35b-q4/identity.json), [1B Q4 identity](1b-q4/identity.json),
  [1B F16 identity](1b-f16/identity.json): exact weight and projector hashes.
  Each directory also includes official upstream revision and LFS metadata.
- Each variant has `repair-smoke/` and `repair-calculus/` manifests, original
  JSONL traces, reports, blank blind-review sheets, and `ocr.json`.
- [Ollama retest](ollama-35b-retest/manifest.json) preserves both timeouts.
- All complete-run file digests were verified; catalog and implementation
  fingerprints remained unchanged during each repair run. Only synthetic OCR
  content and already-authorized research formulas are included. Model weights,
  host logs, signed download URLs and credentials are excluded.

Start a server with the command pattern in `configuration.json`, then run:

```sh
python scripts/probe_local_v47.py \
  --base http://127.0.0.1:18148 --model MODEL_ALIAS \
  --model-file /path/to/model.gguf --projector /path/to/mmproj.gguf \
  --outdir state/new-local-probe
```

Use the official root (non-thinking) 1B F16 GGUF, not the separate thinking
variant. The script runs actual model repair arms and the real synthetic PNG;
fixture results are never reported as model measurements. No model default is
changed by this experiment. Temporary test servers have been stopped.
