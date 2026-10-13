# Single-formula Math Agent handoff v1

Studio can send one existing dollar-delimited inline formula to the configured
Math Agent, receive a revision-bound candidate and let the user explicitly accept
or reject it. The experiment is disabled by default:

```sh
export TEXADA_MATH_HANDOFF_ENABLED=1
export TEXADA_MATH_ENDPOINT=http://127.0.0.1:18732
# Start Math Agent with its authorized MiniCPM-V-4.7-1B text/vision profile;
# its existing model credentials remain in the Math server process environment.
# Then start Studio using the normal MiniCPM launcher and DEMO_TOKEN.
```

The endpoint is server configuration only. Studio accepts no destination URL,
API key, image, arbitrary path or evidence reference from browser requests. The
client refuses redirects. The default loopback connection bypasses system
proxies; a configured non-loopback endpoint uses the operator's normal network
configuration. Endpoint identity is hashed in the saved transfer, so changing it
cannot send a historical review to another service.

The sidebar buttons operate on the inline formula at the cursor, or an exact
selection of its complete body without dollar delimiters. The host supports
`repair` → `syntax_repair` and `complete` → `completion_prefix`, with fixed
limits of 3 steps, 90 seconds and 2048 output tokens. The only checkpoint is
`MiniCPM-V-4.7-1B`; no second model or local fallback is invoked by the consumer.
The Math producer enforces the actual model/runtime configuration and reports
its inference fingerprint. No OCR or full TeX parser is added.

## Studio API

All routes retain the existing `DEMO_TOKEN` authentication:

- `GET /api/studio/handoff/config`: enabled flag and checkpoint only.
- `POST /api/studio/handoff`: exactly `name`, full source `content`, positive
  editor `revision`, `source_range`, `requested_action`, and UUID `transfer_id`.
- `POST /api/studio/handoff/{transfer_id}/decision`: exactly `decision`, `name`,
  current source `content`, and `revision`; decision is `accept` or `reject`.

`source_range` contains integer `start`, `end`, and
`encoding: "unicode-codepoints"`. Monaco uses UTF-16 offsets, so the browser
explicitly converts both offsets to Unicode-codepoint counts. Studio verifies
that the range equals exactly one recognized inline formula body and derives
`original_latex` from that source slice. It generates the stable formula ID,
UTF-8 document/input SHA256 hashes, versioned envelope, action scope, budget,
checkpoint, `requires_review: true`, and an empty controlled-evidence list.
The complete source is used for local binding and is not sent to Math.

The configured Math wire is `POST /api/handoff/formula`. The response must echo
the transfer, document/input hashes, range, formula ID, source revision, original
text and checkpoint. Studio checks candidate text/hash, typed Diff/evidence and
fingerprint, plus the complete review tuple: `input_hash`, `parent_revision`,
`candidate_hash`, `current_revision`. A new formula can have null Math parent
revision; candidate/current revision must be positive and match the tuple.
Source editor revision is independent of Math revisions. Native review DTO statuses are strictly lowercase `pending`, `accepted`, and
`rejected`; uppercase aliases are rejected. Optional flat tuple
mirrors in the review DTO must agree with its nested binding.

Only the bound formula range is replaced in a separate candidate document
buffer. Source files and the editor remain unchanged at proposal time. Handoff
candidates are not automatically compiled; compile status is `NOT_CHECKED`.
The diff and downloadable report retain typed evidence and the fingerprint.
Request counts are shown only when recorded by the producer, and unavailable
counts remain unknown. Syntax checks do not verify mathematical meaning.

## Human decisions and stale protection

Before every proposal or decision, the browser captures file epoch, editor
version, full source and SHA256. It checks them again after asynchronous hashing
and HTTP calls. Before adoption it also validates the full candidate hash,
formula range/input/checkpoint, and exact review tuple; the displayed candidate
buffer must still match. A source edit followed by a revert still changes the
editor version and invalidates the old candidate.

Explicit acceptance or rejection posts to the configured Math
`/api/reviews/{id}/decision` with exactly:

```json
{"decision":"accept","binding":{"input_hash":"...","parent_revision":null,
"candidate_hash":"...","current_revision":1}}
```

Studio validates the returned ID/status and every tuple member. It does not write
source files. The browser checks its source/version/file again after this remote
acknowledgment and only then adopts the candidate into the editor. Rejection
leaves the source intact. A remote decision can finish while an external edit
changes the local source; the final browser check then prevents local adoption.
The report remains available, and a fresh proposal is required for changed
source. The same stale guards now protect ordinary fixed-workflow, planner and
Skill-selection candidates as well as handoff candidates.

## Idempotence and failure boundaries

Transfers are persisted under the ignored `state/studio/handoffs` directory.
A transfer UUID is bound to the canonical complete envelope digest. Concurrent
identical requests share one execution; persisted successful responses survive
service restart. Changing the envelope with the same UUID returns a conflict.
A recorded failed transfer requires a new explicit UUID and cannot silently
start another inference. A restart after an interrupted request can re-send the
same UUID; the producer's idempotence prevents a second inference.

Decisions share the transfer lock, persist their exact intent before HTTP, and
reuse confirmed responses. Identical duplicate decisions are idempotent;
opposite decisions conflict, including after an ambiguous timeout. No automatic
network retry, source write, or candidate adoption occurs. Unavailable services,
timeouts, redirects, malformed/duplicate JSON, mismatched bindings, stale source,
and malformed local records preserve the source. This protocol is a single
formula handoff, not automatic document scheduling or shared mutable state.

Validation uses a real loopback HTTP fixture and product FastAPI routes; no
private documents, live model API or compiler is needed:

```sh
python -m unittest discover -s webui -p 'test_handoff.py'
node webui/test_studio.cjs
```
