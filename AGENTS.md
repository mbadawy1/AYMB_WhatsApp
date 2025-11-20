# AGENTS.md — Orchestrator & Tasks 

> **Role:** Orchestrate tightly scoped, test-first tasks with deterministic outputs.  
> **Workers:** Claude Code (orchestrator), secondary codegen tools (e.g., Codex/Gemini) for heavy lifting.  
> **Source of Truth:** This `AGENTS.md` for task contracts. Individual worker READMEs may add details, but this file wins on conflicts.

---

## Global Guardrails

1. **One task → one PR → merge → next task.**
2. **Scope:** ≤ ~300 LOC changed and ≤ 5 files per PR (unless a task below explicitly allows more).
3. **Tests required** for every PR; include fixtures where applicable.
4. **Determinism:** repeated runs on same input must produce identical outputs (ordering, timestamps normalization, etc.).
5. **Status discipline:** every unit that can fail must set `status`, `status_reason`, and `partial` appropriately.
6. **Docs:** Each PR updates or creates a minimal README snippet for its area when behavior changes.

---

## Source Layout (canonical)

> **WhatsApp pipeline contracts:** For this repo, the canonical inputs/outputs are files (JSONL, CSV, text, etc.) and CLIs as defined in the milestone sections below.  
> CLAUDE.md’s generic HTTP/JSON `{"ok": true, ...}` envelope rules apply **only** if/when we later wrap this pipeline in HTTP services; they are **not** the source of truth for the WhatsApp pipeline itself.

Code lives under `src/`; tests under `tests/`; scripts under `scripts/`; JSON schemas under `schema/`.

**Core schema & parsing**

- `src/schema/message.py`           — `Message` dataclass, type aliases, helpers.
- `schema/message.schema.json`      — JSON schema for `Message`.
- `src/parser_agent.py`             — M1 parser logic.
- `src/utils/dates.py`              — Timestamp parsing / locale detection.


**Media resolver & indexing**

- `src/media_resolver.py`           — M2 resolver core (`MediaResolver`).
- `src/indexer/media_index.py`      — Media file index (`_scan_media`, `FileInfo`).
- `src/indexer/filename_patterns.py`— Filename regexes & token parsing.
- `src/resolvers/scoring.py`        — Scoring helpers (weights, `tau`, drift).

**Audio pipeline**

- `src/audio_transcriber.py`        — M3 audio pipeline (`AudioTranscriber`).
- `src/utils/asr.py`                — ASR client abstraction.
- `src/utils/vad.py`                — VAD wrapper & `VadStats`.
- `src/utils/cost.py`               — Cost estimation helpers.
- `src/utils/hashing.py`            — File hashing utilities.

**Writers & CLIs**

- `src/writers/messages_csv.py`     — CSV/JSONL writers for `Message[]`.
- `src/writers/exceptions_csv.py`   — Exceptions/ambiguous-media writer.
- `scripts/parse_chat.py`           — M1 CLI (parse → JSONL).
- `scripts/resolve_media.py`        — M2 CLI (media mapping).
- `scripts/transcribe_audio.py`     — M3 CLI (audio transcription).
- `config/media.yaml`               — Media resolver configuration.

Tests & fixtures:

- `tests/test_parser_basic.py`
- `tests/test_media_resolver.py`
- `tests/test_audio_transcriber.py`
- `tests/fixtures/**` (text, media, voice fixtures)
- `tests/golden/**` (golden resolution fixtures)

---

## Status & Status Reason Codes (canonical)

These enums are **global**. Milestones may *use* a subset but must not invent new codes without updating this table (and bumping schema version if needed).

### Status

```python
from typing import Literal

Status = Literal["ok", "partial", "failed", "skipped"]
````

* `"ok"`      — Operation completed successfully for this message.
* `"partial"` — Operation completed but with known gaps (e.g., some ASR chunks failed).
* `"failed"`  — Operation could not complete (no usable result).
* `"skipped"` — Operation intentionally not run (e.g., VAD gate, merged message).

### StatusReason

```python
StatusReason = Literal[
    # M1 — parser / structural
    "merged_into_previous_media",

    # M2 — media resolution
    "unresolved_media",
    "ambiguous_media",

    # M3 — audio pipeline
    "ffmpeg_failed",
    "timeout_ffmpeg",
    "vad_no_speech",
    "asr_failed",
    "timeout_asr",
    "asr_partial",
    "audio_unsupported_format",
]
```

**M1 may set:**

* `status="ok"` for normal messages.
* `status="skipped", status_reason="merged_into_previous_media"` for caption-merged rows.

**M2 may set:**

* `status="ok"` when media is resolved to a concrete file.
* `status="ok", status_reason="unresolved_media"` when no candidate passes threshold.
* `status="ok", status_reason="ambiguous_media"` when 2+ candidates tie above threshold.

**M3 may set:**

* `status="failed", status_reason="ffmpeg_failed" | "timeout_ffmpeg"` — conversion failed.
* `status="failed", status_reason="asr_failed" | "timeout_asr"` — all ASR chunks failed.
* `status="partial", status_reason="asr_partial"` — some chunks failed, some succeeded.
* `status="failed", status_reason="audio_unsupported_format"` — unsupported media type.

> `vad_no_speech` remains in the global `StatusReason` enum for potential **future** VAD-gated behavior,  
> but the v1 audio pipeline (M3) **MUST NOT** set `status="skipped"` based on VAD alone.  
> In v1, VAD is observational only; ASR is still run on all supported audio.


> **Rule:** If you need a new `status_reason`, add it to `StatusReason` in `src/schema/message.py`, update this table, and bump `schema_version`.

---

## Schema Versioning Policy

`src/schema/message.py` is the **single source of truth** for the `Message` shape and its enums.  
All JSONL/CSV writers (M1–M3, M5, M6) must serialize exactly this schema.

We track a semantic version string, e.g.:

- `schema_version = "1.2.0"`

in `src/schema/message.py` (and mirror it into `schema/message.schema.json` and any `RunManifest` structures as needed).

**Bump rules**

- **MAJOR (X.0.0)**  
  - Removing a field.  
  - Changing a field’s type (e.g. `str` → `int`).  
  - Removing an existing enum value (`kind`, `status`, or `status_reason`).  
  - Any change that makes old JSONL incompatible with new code.

- **MINOR (1.Y.0)**  
  - Adding a **new optional** field.  
  - Adding a **new enum value** that old code will simply ignore or treat as “unknown”.  
  - Any change that is backward compatible for readers that don’t rely on the new field/value.

- **PATCH (1.2.Z)**  
  - Documentation/comment changes only.  
  - Test refactors that do not alter the serialized shape at all.

**Responsibilities**

- Any change to `Message` or the global enums **must**:
  - Update `schema_version` in `src/schema/message.py`.
  - Update `schema/message.schema.json`.
  - Update tests that golden-compare `messages.*.jsonl` / CSV.
- M6 runner and downstream tools **must** check `schema_version` and either:
  - Accept compatible versions (same MAJOR, ≥ MINOR they support), or  
  - Fail loudly with a clear “unsupported schema_version” error.

## Milestones Overview

* **M1** Parser & Schema + tests. *(done / in progress)*
* **M2** Media Resolver + `<Media omitted>` heuristics + tests. *(done / in progress)*
* **M3** Audio pipeline (ffmpeg/Whisper/VAD/chunking/caching) + tests. *(in progress)*
* **M4** (Deferred) PDF & Image enrichment — OCR/captions for images & PDFs. *Skipped in v1; all image/PDF handling is placeholder-only.*
* **M5** Renderer (Text view + MD→PDF) + tests. *(active after M3)*
* **M6** Orchestrator (concurrency, resume, metrics, exceptions) + tests. *(hardening / production)*

---

---

* “CLAUDE.md’s generic HTTP/json envelope contracts apply only to future HTTP services. For this repo, the canonical contracts are the file formats and CLIs defined here.”
---


## Tooling & MCP Usage (Codex / Claude Code)

> **Assumption:** MCP servers `context7`, `chrome-devtools`, `playwright`, and `git` are available in the environment (Codex VS Code extension or Claude Code with MCP config).
> When these tools exist, prefer them over ad-hoc guessing or shelling out directly.

### 1) Context7 — Deep Library Docs & Examples

**Role**

Use the `context7` MCP whenever you need **library / framework details** instead of guessing from memory, especially for:

* ffmpeg flags, audio formats, VAD libraries (M3).
* Whisper / Google ASR client options, rate limits, error surfaces (M3, M6).
* Streamlit / frontend framework APIs used in `scripts/ui_app.py` (M6).

**Rules**

1. Before designing a non-trivial API or picking flags, call `context7` with the exact library + keyword (“ffmpeg silenceremove VAD thresholds”, “python soundfile 16k mono”, “Streamlit file uploader multiple files”).
2. Prefer **small, targeted queries**; summarize docs into explicit decisions (e.g., “we will use `-ar 16000 -ac 1 -f wav` for WhatsApp audio”).
3. Capture any critical assumptions in the relevant README (`README_M3.md`, `README_M6_UI.md`, etc.) so future tasks don’t need to re-query for the same thing.

**Prompt pattern**

> “Use the `context7` tool to fetch current docs for **`<library or CLI>`**, focused on **`<specific feature>`**.
> Summarize the options relevant to this repo, choose one consistent configuration, and show me the exact code/CLI snippet you’ll implement.”

---

### 2) Chrome DevTools / Playwright — Seeing & Poking the UI

**Role**

For any task that touches the **UI / UX** (mostly M5+M6), use browser MCPs to inspect and exercise the **actual running app**, not just static code:

* Layout and readability of `chat_with_audio.txt` / `chat_with_audio.md` previews as rendered in the Streamlit UI.
* Buttons / flows in `scripts/ui_app.py` (selecting a run, launching the pipeline, viewing previews).

**Chrome DevTools MCP**

Use `chrome-devtools` when you need **DOM, CSS, console logs, or screenshots** of the local UI (typically `http://localhost:8501` for Streamlit):

Prompt pattern:

> “Assume the Streamlit app is running at **`http://localhost:8501`**.
> Use the `chrome-devtools` MCP to:
>
> 1. open that URL,
> 2. capture the DOM structure around the main transcript preview, and
> 3. tell me what looks wrong on small screens.
>    Then propose a concrete React/Streamlit layout or CSS change and the exact code diff to implement it.”

**Playwright MCP**

Use `playwright` when you need **end-to-end flows**:

* Uploading a `_chat.txt`, running the pipeline, then verifying that the generated outputs (`messages.M*.jsonl`, `chat_with_audio.txt`, `chat_with_audio.md`) show up in the UI.
* Checking that error states from `run_manifest.json`/`metrics.json` render correctly (failed run banners, partial ASR warnings).

Prompt pattern:

> “Use the `playwright` MCP to open **`http://localhost:8501`**,
> click through the flow **‘select sample fixture → run pipeline → open transcript preview’**,
> and report:
> – which buttons/labels you had to click,
> – any visible error messages,
> – and a concise list of UI glitches or confusing states.
> Then propose code changes to `scripts/ui_app.py` (and any supporting modules) to fix them.”

---

### 3) Git MCP — Branches, Diffs, History

**Role**

Use the `git` MCP for **read-only repo introspection** instead of shelling out with raw `git` commands:

* Understanding current branch and its relation to `main`.
* Summarizing changes for a given M1.x/M2.x/M3.x/M5.x/M6.x task.
* Checking what changed in `AGENTS.md` or `CLAUDE.md` between two commits when contracts evolve.

**Rules**

1. Do **not** create commits or push from inside the agent; just read history and propose commands / PR descriptions.
2. When summarizing work, prefer “git diff” via MCP over scanning files manually; tie your summary back to the milestone/task IDs (e.g., `M3.4`, `M5.1`).
3. Use it to generate precise PR bodies that respect the “one task → one PR” rule.

**Prompt pattern**

> “Use the `git` MCP on this repo to:
> – show the diff between `main` and the current branch,
> – group changes by milestone task (M2.x/M3.x/M5.x/M6.x), and
> – draft a PR description that follows our AGENTS.md guidelines
> (scope ≤ 300 LOC / 5 files, mention fixtures & tests run).”


## CURRENT FOCUS

- Milestone: M6.7 — Manifest & Metrics Schema (Run-Level)
- Task: M6.7 — Manifest & Metrics Schema (Run-Level)
- Branch: feat/m6-7-manifest-metrics-schema
- Status: Complete

**Completed (2025-01-20):**
- ✅ Created JSON schemas (`schema/run_manifest.schema.json`, `schema/metrics.schema.json`)
- ✅ Added validation helpers (`validate_manifest()`, `validate_metrics()`)
- ✅ Created test suite (3 test files, 45+ test cases)
- ✅ Created golden fixtures for contract verification

**Previous:**
- M6.6 — Audio Error Handling & Chunking Hardening (Complete)



# M1 — Parser & Schema (Execution Tasks)

**Milestone Goal:**
Parse `_chat.txt` → normalized `Message[]` with multiline safety, locale/clock auto-detect, header parsing, kind classification, caption-merge, and schema validation.

**Code surface (initial expected files):**

* `src/schema/message.py`
* `src/parser_agent.py`
* `src/utils/dates.py`
* `schema/message.schema.json`
* `tests/test_parser_basic.py`
* `tests/fixtures/text_only/_chat.txt`

---

## M1.0 — Message Model (Canonical)

**Objective**
Define the global `Message` dataclass and wire in status enums. This is the **only** place the schema lives; all milestones import from here.

**File:** `src/schema/message.py`

**Message model (exact fields and defaults):**

```python
from dataclasses import dataclass, field
from typing import Optional, Literal, Dict, List

Kind = Literal["text", "voice", "image", "video", "document", "sticker", "system", "unknown"]
Status = Literal["ok", "partial", "failed", "skipped"]
StatusReason = Literal[
    "merged_into_previous_media",
    "unresolved_media",
    "ambiguous_media",
    "ffmpeg_failed",
    "timeout_ffmpeg",
    "vad_no_speech",
    "asr_failed",
    "timeout_asr",
    "asr_partial",
    "audio_unsupported_format",
]

@dataclass
class Message:
    idx: int
    ts: str
    sender: str
    kind: Kind

    content_text: str = ""
    raw_line: str = ""
    raw_block: str = ""

    media_hint: Optional[str] = None
    media_filename: Optional[str] = None
    caption: Optional[str] = None

    derived: Dict = field(default_factory=dict)
    status: Status = "ok"
    partial: bool = False
    status_reason: Optional[StatusReason] = None
    errors: List[str] = field(default_factory=list)
```

**Verification**

* `pytest -q` imports `schema.message.Message` without error.
* Parser, resolver, and audio modules all import `Message` from `src/schema/message.py` (no duplicate definitions).

> All subsequent tasks must **not** redefine `Message`. If you change it, you do so here and bump `schema_version`.

---

## M1.1 — Project Skeleton & Types

**Objective**
Create the minimal structure and typed model the rest of M1 builds on.

**Deliverables**

* `src/schema/message.py` (M1.0 above).
* `src/parser_agent.py` with `ParserAgent` stub.
* `src/utils/dates.py` with empty function stubs.
* `tests/test_parser_basic.py` (empty or smoke tests).
* `tests/fixtures/text_only/` directory.

**Subtasks**

1. Create folders & files as per **Source Layout**.

2. Implement `Message` dataclass and enums in `src/schema/message.py` (M1.0).

3. Stub `ParserAgent` with:

   ```python
   class ParserAgent:
       def __init__(self, root: str, locale_format: str = "auto"): ...
       def parse(self) -> list[Message]: ...
   ```

4. Add `src/utils/dates.py` with stubbed `detect_datetime_format` / `parse_ts`.

5. Add `tests/fixtures/text_only/` (empty for now).

**Verification**

* Imports succeed:

  ```bash
  pytest -q  # 0 or 1 smoke test, but no ImportError
  ```

---

## M1.2 — Timestamp & Locale Autodetect

**Objective**
Detect which timestamp pattern/locale the file uses by sampling the first ~200 non-empty lines.

**File:** `src/utils/dates.py`

**Deliverables**

* `detect_datetime_format(lines) -> dict`
* `parse_ts(s: str, fmt: dict) -> str` returning ISO 8601 `YYYY-MM-DDTHH:MM:SS`.

**Subtasks**

1. Implement multiple compiled regex candidates (12h/24h; EN/AR dialects).
2. Score candidates (hits, early lines weighted higher).
3. Return chosen `fmt` object: `{regex, strptime_pattern, tz_placeholder}`.
4. Implement `parse_ts` using `fmt` and return canonical ISO string.

**Verification & Tests**

* Fixtures:

  * `tests/fixtures/text_only/sample_24h.txt`
  * `tests/fixtures/text_only/sample_12h.txt`

* Tests (`tests/test_parser_basic.py`):

  * `test_detect_datetime_format_24h`
  * `test_detect_datetime_format_12h`

Both assert chosen pattern & correct ISO parse.

---

## M1.3 — Header Parsing & Tokenization

**Objective**
Split a line into header vs body **only when** the line starts with a timestamp. Header form: `<TS> - <SENDER>: <BODY>`.

**File:** `src/parser_agent.py`

**Deliverables**

* `ParserAgent._split_header(line, fmt) -> (ts: str | None, sender: str | None, body: str | None)`

**Subtasks**

1. If line doesn’t match timestamp → return `(None, None, line)` (continuation).
2. If it matches, extract `ts`, `sender`, `body`.
3. Use first `" - "` then first `": "` on the **header line only**.
4. Trim BOM; preserve original `raw_line` for that block.

**Verification & Tests**

* Fixture: `tests/fixtures/text_only/header_cases.txt` with:

  * normal headers
  * missing “:”
  * sender with “:”
  * Arabic names
  * emoji

* Tests:

  * `test_header_split_basic`
  * `test_header_split_colon_in_sender`
  * `test_header_split_non_header_continuation`

---

## M1.4 — Multiline Joiner

**Objective**
Aggregate continuation lines into the current message’s `raw_block` and `content_text` until the next header appears.

**File:** `src/parser_agent.py`

**Deliverables**

* `ParserAgent._to_blocks(lines, fmt) -> list[dict]` producing blocks:

  ```python
  {"ts", "sender", "raw_block", "raw_line"}
  ```

**Subtasks**

1. Iterate lines; header → start new block.
2. Continuation → append with `\n`.
3. Preserve original first `raw_line` per block.

**Verification & Tests**

* Fixture: `tests/fixtures/text_only/multiline.txt` with paragraphs/code-like blocks/RTL mix.
* Tests:

  * `test_multiline_join_preserves_newlines`
  * `test_multiline_no_false_splits`

---



**Objective**
Classify each block into `kind` and extract `media_hint` (e.g., `<Media omitted>`, `Voice message (0:36)`, `WA-*.jpg`).

**File:** `src/parser_agent.py`

**Deliverables**

* `ParserAgent._classify(block) -> (kind, media_hint, content_text)`

**Subtasks**

1. Normalize placeholders (case-insensitive, RTL-safe):

   * `<Media omitted>` / `<image omitted>` / `<video omitted>`
   * `Voice message (mm:ss)` / `Audio omitted`
   * `image WA-...jpg` / `document WA....pdf`

2. If none match → `kind="text"`; weird things fall back to `kind="unknown"`.

3. Extract `mm:ss` duration into `media_hint` when present.

4. Strip placeholder text from `content_text`.

**Verification & Tests**

* Fixture: `tests/fixtures/text_only/kinds.txt`
* Tests:

  * `test_kind_detection_voice`
  * `test_kind_detection_image`
  * `test_kind_detection_document`
  * `test_text_falls_back_unknown_when_ambiguous`

---

## M1.5 — Kind Classification & Media Hints

**Objective**  
Classify each block into `kind` and extract `media_hint` for WhatsApp media lines, including both `<Media omitted>`-style placeholders **and** explicit filename lines like `PTT-20250708-WA0028.opus (file attached)`.

**File:** `src/parser_agent.py`

**Deliverables**

* `ParserAgent._classify(block) -> (kind, media_hint, content_text)`

**Subtasks**

1. **Explicit filename + `(file attached)` fast path**

   * Detect bodies that match a WhatsApp filename with the literal suffix `(file attached)`, e.g.:

     ```text
     IMG-20250726-WA0037.jpg (file attached)
     PTT-20250708-WA0028.opus (file attached)
     AUD-20250708-WA0053.opus (file attached)
     VID-20250808-WA0039.mp4 (file attached)
     DOC-20250728-WA0001.pdf (file attached)
     ```

   * Use a regex along the lines of:

     ```text
     ^(?P<fname>(IMG|VID|PTT|AUD|DOC)-\d{8}-WA\d+\.[A-Za-z0-9]+) \(file attached\)$
     ```

   * If this matches:

     * Set `media_hint = fname` (filename only, no `(file attached)`).
     * Set `content_text = ""` (M3 will later fill this with transcript for voice notes).
     * Map prefix → `kind`:

       * `PTT-` or `AUD-` → `kind="voice"`
       * `IMG-` → `kind="image"`
       * `VID-` → `kind="video"`
       * `DOC-` or other document-like extensions → `kind="document"`

2. **Textual media placeholders (`<Media omitted>` etc.)**

   * Normalize placeholders (case-insensitive, RTL-safe), including variants such as:

     * `<Media omitted>`
     * `<image omitted>`
     * `<video omitted>`
     * `<document omitted>`

   * Behavior:

     * Always strip the placeholder from `content_text` (leave it `""`).
     * Set `media_hint` to a normalized token (e.g. `"media_omitted"`, `"image_omitted"`).
     * Set `kind` when the placeholder is specific:

       * `<image omitted>` → `kind="image"`
       * `<video omitted>` → `kind="video"`
       * `<document omitted>` → `kind="document"`
       * Plain `<Media omitted>` → `kind="unknown"` (M2 may still resolve via hints/mtime).

3. **Voice-message textual hints**

   * Detect lines like `Voice message (0:36)` or `Audio omitted`.

   * Extract the `mm:ss` duration into `media_hint` (e.g. `"00:36"`).

   * Set:

     * `kind="voice"`
     * `content_text=""` (ASR will provide the text later).

4. **System lines are left to M1.9**

   * `_classify` may detect obvious system phrases here if convenient, but full system-handling patterns are defined in **M1.9** (kind `"system"`).
   * Ensure any system handling here does **not** break multiline joins.

5. **Plain text and fallback**

   * If none of the media or system patterns match:

     * Default to `kind="text"` and leave `media_hint=None`.
     * For completely weird forms where you cannot safely decide, you may use `kind="unknown"` but must not raise.

**Verification & Tests**

* Fixture: `tests/fixtures/text_only/kinds.txt` should include:

  * Lines with `<Media omitted>`, `<image omitted>`, `<video omitted>`.
  * Lines with `IMG-… (file attached)`, `VID-… (file attached)`, `PTT-… (file attached)`, `AUD-… (file attached)`, `DOC-… (file attached)`.
  * A couple of normal text lines and ambiguous/garbage lines.

* Tests in `tests/test_parser_basic.py`:

  * `test_kind_detection_file_attached_voice_and_image` — `PTT-*/AUD-*` → `kind="voice"`, `IMG-*` → `kind="image"`, `media_hint` stripped of `(file attached)`, `content_text==""`.
  * `test_kind_detection_media_placeholders` — `<image omitted>` / `<video omitted>` / `<Media omitted>` mapped as specified.
  * `test_kind_detection_document` — DOC/PDF lines become `kind="document"`.
  * `test_text_falls_back_unknown_when_ambiguous` — weird bodies become `kind="text"` or `kind="unknown"` but never crash.



## M1.6 — Caption Merge

**Objective**
If media A is immediately followed by text B with **same sender & ts**, move B’s text to A’s `caption`; mark B as skipped.

**File:** `src/parser_agent.py`

**Deliverables**

* `ParserAgent._merge_captions(messages: list[Message]) -> list[Message]`

**Subtasks**

1. One-pass scan; for each media message, peek next.
2. Condition: same `sender` & identical `ts` string.
3. Move B’s text to A’s `caption`; keep A’s `content_text` untouched.
4. Set:

   * A: `status="ok"` (unchanged).
   * B: `status="skipped"`, `status_reason="merged_into_previous_media"`.

**Verification & Tests**

* Fixture: `tests/fixtures/text_only/caption_merge.txt` with positives & negatives.
* Tests:

  * `test_caption_merge_positive`
  * `test_caption_merge_negative_different_ts`

---

## M1.7 — Message Construction & Indexing

**Objective**
Produce stable 0→N `idx`; fill `Message` with parsed data and defaults.

**File:** `src/parser_agent.py`

**Deliverables**

* In `ParserAgent.parse()`:

  * transform blocks → `Message` instances
  * assign `idx` in order
  * fill `raw_block`, `raw_line`, `status="ok"` (unless overridden)

**Subtasks**

1. Iterate blocks deterministically.
2. Build `Message` dataclasses using `schema.message.Message`.
3. Ensure default empty strings / `None` / `default_factory` values as specified in `Message`.

**Verification & Tests**

* `test_message_indexing_stable` — re-run `parse()` yields identical `idx` & ordering.
* `test_message_fields_defaults` — fields present with expected defaults.

---

## M1.8 — JSON Schema Validation

**Objective**
Validate each `Message` against a JSON schema; enable a toggle for speed.

**Files:**

* `schema/message.schema.json`
* `src/schema/message.py` (validation helper)

**Deliverables**

* `schema/message.schema.json` mirroring `Message` fields & enums.
* `def validate_message(msg: Message) -> None` in `src/schema/message.py` (raising on violation).
* `ParserAgent._validate(msg)` that calls `validate_message` when enabled.
* `ParserAgent.parse()` invokes `_validate` when `VALIDATE_SCHEMA=true`.

**Subtasks**

1. Author JSON schema (types/enums/required) based on `Message`.
2. Add `jsonschema` (or pydantic) dependency.
3. Toggle via env `VALIDATE_SCHEMA=true|false`.

**Verification & Tests**

* `test_schema_validation_happy_path` — valid messages pass.
* `test_schema_validation_rejects_bad_kind` — invalid `kind` rejected.

---

## M1.9 — System Lines & Noise Handling

**Objective**
Mark WhatsApp system notices (encryption banner, “You created this group”, add/remove) as `kind="system"` without breaking multiline.

**File:** `src/parser_agent.py`

**Deliverables**

* Pattern list inside `_classify` to set `kind="system"`.

**Subtasks**

1. Add EN/AR variants of common system phrases.
2. Ensure multiline aggregator logic remains intact.

**Verification & Tests**

* Fixture: `tests/fixtures/text_only/system_lines.txt`.
* Tests:

  * `test_system_lines_marked`
  * `test_system_lines_do_not_split_messages`

---

## M1.10 — Parse CLI (Smoke) & Docs

**Objective**
Provide a tiny CLI to parse a folder and print JSONL for manual smoke testing.

**File:** `scripts/parse_chat.py`

**Deliverables**

* CLI: `scripts/parse_chat.py --root <folder>` → JSONL to stdout.
* `README_M1.md` with usage notes and timestamp formats supported.

**Subtasks**

1. Wire `ParserAgent(root).parse()`.
2. Serialize to JSONL with UTF-8; preserve Arabic/emoji.

**Verification & Tests**

* Manual smoke:

  ```bash
  python scripts/parse_chat.py --root samples/
  ```

* Automated:

  * `test_smoke_cli_invocation` (subprocess, exit code 0).

---

## M1 — Acceptance Criteria

* Parsing a mixed-locale `_chat.txt` produces deterministic `Message[]` with valid ISO timestamps, correct header splits, correct kinds, and caption merges where applicable.
* All tests pass (`pytest -q`), coverage for M1 code ≥ 80%.
* JSON schema present and used (toggleable), with at least one negative test.
* Unknown/odd lines do not crash; they become `kind="unknown"` or `system` with `status="ok"`.

---

# M2 — Media Resolver (+ `<Media omitted>` heuristics & tests)

**Milestone Goal**
Map placeholders/filenames to actual media using a ranked candidate set built from same-day files. If unresolved or ambiguous, annotate the message, set `status_reason`, and record ranked candidates in `exceptions.csv` (never crash the run).

**Code surface (expected files)**

* `src/media_resolver.py`
* `src/indexer/media_index.py`
* `src/indexer/filename_patterns.py`
* `src/resolvers/scoring.py`
* `src/writers/messages_csv.py`
* `src/writers/exceptions_csv.py`
* `config/media.yaml`
* `tests/test_media_resolver.py`
* `tests/fixtures/media_omitted_easy/`
* `tests/fixtures/media_omitted_ambiguous/`

**Ranking ladder (implement in order; first decisive difference wins)**

1. Nearby text hints (±2 messages)
2. Extension priority (configurable)
3. WA#### sequence proximity (same day/type)
4. File `mtime` proximity to message timestamp
5. Tie-breakers: smaller size → lexical path order

If still ambiguous → `media_filename=None`, insert `[UNRESOLVED MEDIA]`, and log candidates+scores.

---

### M2.1 — Resolver Skeleton & Config

**File:** `src/media_resolver.py`

**Objective**
Create the resolver class, dependency surfaces, and config knobs without behavior yet.

**Deliverables**

* `MediaResolver` with:

  ```python
  class MediaResolver:
      def __init__(self, root: Path, ext_priority=("voice","image","video","document","other"), cfg=None): ...
      def map_media(self, msgs: list[Message]) -> None: ...
      def _rank_candidates(self, msg: Message, day_files: list) -> list[tuple[Path, float, dict]]: ...
  ```

* Config dataclass or dict for: ladder weights, hint window, allowed extensions, unresolved policy.

**Subtasks**

1. Create module/file with class + signatures.
2. Wire basic logging (structured dicts).
3. Add minimal docstring on each public method.

**Verification & Tests**

* `pytest -q` imports clean.
* `isinstance(MediaResolver(...))` smoke test passes.

---

### M2.2 — Day-File Indexer

**File:** `src/indexer/media_index.py`

**Objective**
Build an index of media files grouped by chat-day and media type to bound candidate sets.

**Deliverables**

* `_scan_media(root) -> dict[(date, str) -> list[FileInfo]]` where `str` ∈ `{voice, image, video, document, other}`.
* `FileInfo = {path, size, mtime, name_tokens, seq_num}` (sequence parsed from `WA-####` if present).

**Subtasks**

1. Walk `root` recursively; filter known media extensions.
2. Extract `date` from `mtime` (same TZ policy used in M1).
3. Parse `WA-####` sequence; store `seq_num: Optional[int]`.

**Verification & Tests**

* Fixture folder with a few media files across two days.
* `test_index_groups_by_day_and_type` asserts counts and basic fields.

---

### M2.3 — Nearby Text Hints (Ladder #1)

**File:** `src/media_resolver.py`

**Objective**
Extract filename-ish hints from the ±2 surrounding messages (same sender preferred, then global).

**Deliverables**

* `_extract_hints(msgs, i) -> set[str]` (tokens such as `WA-0012`, `IMG-2024…`, or bare stems).

**Subtasks**

1. Tokenize `content_text`/`caption` of ±2 messages.
2. Normalize tokens: lowercase, strip punctuation, collapse whitespace.
3. Heuristics to keep only file-like or media-descriptive tokens.

**Verification & Tests**

* Fixture `tests/fixtures/media_omitted_easy/` with an obvious “see photo WA-0012” lead-in.
* `test_hints_prefer_same_sender_then_global`.

---

### M2.4 — Extension Priority (Ladder #2)

**File:** `src/resolvers/scoring.py`

**Objective**
Score candidates by type order: `voice > image > video > document > other` unless overridden.

**Deliverables**

* `_score_ext(type_str) -> float` used inside `_rank_candidates`.

**Subtasks**

1. Map types to descending weights.
2. Allow override via constructor param / config.

**Verification & Tests**

* Synthetic candidates verify strict ordering when all else equal.
* `test_ext_priority_applies_before_seq_and_mtime`.

---

### M2.5 — WA#### Sequence Proximity (Ladder #3)

**File:** `src/resolvers/scoring.py`

**Objective**
If `msg.media_hint` implies a sequence (or nearby hint does), reward closest `seq_num` among same-day/type files.

**Deliverables**

* `_score_seq(target: int | None, cand: int | None) -> float`.

**Subtasks**

1. Extract target from `media_hint` or `_extract_hints`.
2. Use absolute distance penalty; `None` loses to any integer match.

**Verification & Tests**

* `tests/fixtures/media_omitted_easy/` with three sequential images.
* `test_seq_closest_wins_over_mtime_when_ext_equal`.

---

### M2.6 — mtime Proximity & Tie-Break (Ladder #4–5)

**File:** `src/resolvers/scoring.py`

**Objective**
Prefer files whose `mtime` is closest to `msg.ts`; final tie-break by (a) smaller size, then (b) lexical path.

**Deliverables**

* `_score_mtime(delta_seconds) -> float` (monotonic penalty).
* Stable sort guaranteeing determinism.

**Subtasks**

1. Convert message ISO timestamp to epoch; compute `abs(mtime - ts)`.
2. Define epsilon for identical mtimes.

**Verification & Tests**

* `tests/fixtures/media_omitted_ambiguous/` with two same-type files close in time.
* `test_tie_breaker_size_then_lexical`.

---



**File:** `src/media_resolver.py`

**Objective**
Combine ladder components into a single scorer; return ordered candidate list; choose top iff decisively better.

**Deliverables**

* `_rank_candidates(msg, day_files) -> [(path, total_score, explanation_dict)]`
* `map_media(...)` writes:

  * **Resolved:** set `msg.media_filename = path`; `status="ok"`, `status_reason=None`.
  * **Ambiguous/Unresolved:** keep `media_filename=None`; set:

    * `status="ok"`, `status_reason="unresolved_media"` for low scores.
    * `status="ok"`, `status_reason="ambiguous_media"` for ties above `tau`.

**Subtasks**

1. Weight vector: `w = [hint, ext, seq, mtime]` (doc string with current values).
2. Decide “decisive margin” (e.g., top − second ≥ `tau`).
3. Build `explanation_dict` with per-ladder contributions.

**Verification & Tests**

* Golden test on “easy” fixture: top candidate passes decisiveness check.
* “Ambiguous” fixture: logs 2–3 ranked candidates; leaves unresolved.

---

### M2.7 — Candidate Ranking & Selection

**File:** `src/media_resolver.py`

**Objective**  
Combine ladder components into a single scorer; return ordered candidate list; choose top iff decisively better — but first, take a cheap “filename fast path” for messages that already carry an exact media filename.

**Deliverables**

* `_rank_candidates(msg, day_files) -> list[tuple[Path, float, dict]]`
* `map_media(...)` writes:

  * **Resolved:** set `msg.media_filename = path`; `status="ok"`, `status_reason=None`.
  * **Ambiguous/Unresolved:** keep `media_filename=None`; set:

    * `status="ok", status_reason="unresolved_media"` for low scores.
    * `status="ok", status_reason="ambiguous_media"` for ties above `tau`.

**Subtasks**

1. **Filename FastPath**

   * Before running the scoring ladder, check whether `msg.media_hint` looks like a concrete WhatsApp filename (e.g. `IMG-YYYYMMDD-WA####.jpg`, `PTT-YYYYMMDD-WA####.opus`, `AUD-…`, `VID-…`, `DOC-…`).
   * If so, attempt to locate that exact filename under `root` (within known media subfolders).
   * If the file exists:

     * Set `msg.media_filename` to the resolved `Path`.
     * Leave `msg.status="ok"` and `msg.status_reason=None`.
     * **Skip** the ranking ladder entirely for this message (no exception row, no `unresolved_media`/`ambiguous_media`).

   * If the file does not exist, fall back to the normal ladder below.

2. **Scoring ladder (for non-fast-path or missing files)**

   * Build candidate set from `_scan_media` for the message’s chat-day and media type.

   * Apply weighted components:

     * Hint score (`_extract_hints` output).
     * Extension priority (`_score_ext`).
     * WA#### sequence proximity (`_score_seq`).
     * mtime proximity (`_score_mtime`).

   * Combine into a total score per candidate using weights `w = [hint, ext, seq, mtime]` (document current values in code/docstring).

3. **Decisive margin and selection**

   * Sort candidates by `total_score` (descending), with tie-breaks defined in M2.6 (size, then lexical path).

   * Decide “decisive margin” (e.g. top − second ≥ `tau` from config):

     * If there is a single clear winner above threshold → assign it as resolved.
     * If top candidates tie within `tau` → treat as ambiguous.

4. **Derived explanation**

   * For non-fast-path resolutions, fill `explanation_dict` with per-ladder contributions, e.g.:

     ```python
     {
         "hint": ...,
         "ext": ...,
         "seq": ...,
         "mtime": ...,
         "total": ...,
     }
     ```

   * Attach these explanations in `derived["disambiguation"]` for ambiguous cases (see M2.10) and for debugging in tests.

**Verification & Tests**

* Golden test on “easy” fixture:

  * `test_decisive_margin_resolves_easy_case` — non-ambiguous `<Media omitted>` messages resolve to the expected files via ladder or fast path.

* Ambiguous fixture:

  * `test_ambiguous_yields_csv_and_no_assignment` — top 2–3 candidates close in score; no `media_filename` chosen; `status_reason="ambiguous_media"`; `exceptions.csv` populated.

* Fast path:

  * `test_filename_fastpath_uses_exact_match` — for messages whose `media_hint` is an exact filename that exists on disk (typical `PTT-... (file attached)` / `IMG-... (file attached)` lines), `map_media` sets `media_filename` directly and **does not** invoke the scoring ladder.


### M2.8 — Exceptions CSV & Status Discipline

**File:** `src/writers/exceptions_csv.py`

**Objective**
Emit `exceptions.csv` with all unresolved/ambiguous items (and their top-K candidates + scores). Always set `status`, `status_reason`, `partial` consistently.

**Deliverables**

* `exceptions.csv` columns:

  * `idx, ts, sender, kind, media_hint, reason, top1_path, top1_score, top2_path, top2_score, …`

* Helper: `log_exception(msg, reason, candidates)`.

**Subtasks**

1. Append rows during `MediaResolver.map_media`.
2. Ensure idempotent (overwrite file per run).

**Verification & Tests**

* Assert CSV exists for “ambiguous” fixture with expected columns.
* `test_status_reason_set_for_unresolved_and_ambiguous`.

---

### M2.9 — CLI Smoke & Docs

**File:** `scripts/resolve_media.py`

**Objective**
Provide a small CLI for manual checks and add a README note.

**Deliverables**

* `scripts/resolve_media.py --root <chat-folder>`

**Subtasks**

1. Load messages JSONL (from M1 output) or re-parse via M1 pipeline in tests.
2. Run resolver, print summary: `resolved=N, unresolved=M, ambiguous=K`.

**Verification & Tests**

* `test_smoke_cli_media_resolver` (subprocess) returns exit code 0 with expected summary.

---

### M2.10 — Status enums & `ambiguous_media` wiring + CSV surfacing

**Files:**

* `src/schema/message.py`
* `src/media_resolver.py`
* `src/writers/exceptions_csv.py`
* `docs/README_CONTRACTS.md` (or similar)

**Why**
Contracts distinguish “unresolved” from “ambiguous,” but we must ensure the enum and CSV stay in sync.

**Changes**

1. In `src/schema/message.py`:

   * Ensure `StatusReason` includes `"unresolved_media"` and `"ambiguous_media"` (as in the global list above).

2. In `src/media_resolver.py`:

   * When two (or more) candidates tie above `tau`:

     * Set `msg.status="ok"`.
     * Set `msg.status_reason="ambiguous_media"`.
     * Attach a `derived["disambiguation"]` blob:

       ```python
       {
           "candidates": [{"path": "...", "score": ...}, ...],
           "top_score": ...,
           "tie_margin": ...
       }
       ```

3. In `src/writers/exceptions_csv.py`:

   * Surface `status_reason`.
   * Write the `derived["disambiguation"]` JSON (if present) into a stable column.

4. Document the behavior in `README_CONTRACTS.md`.

**Tests**

* `tests/resolver/test_status_reason_ambiguous_media.py`:

  * Given two files scoring within the tie margin above `tau`
    → expect `status_reason="ambiguous_media"` and an `exceptions.csv` row with two candidates recorded.

* `tests/writers/test_exceptions_csv_ambiguous_blob.py`:

  * Expect stable JSON shape; golden-compare normalized keys.

**Acceptance**

* Fixture where two images differ only in EXIF time by ±30s produces exactly one `exceptions.csv` line with `ambiguous_media` and two candidates, stable across re-runs.
* No regressions in existing `unresolved_media` cases.

---

### M2.11 — Content hashing for deterministic rematch (+ CSV/JSON surfacing)

**Files:**

* `src/utils/hashing.py`
* `src/indexer/media_index.py`
* `src/schema/message.py`
* `src/writers/messages_csv.py`
* `src/writers/exceptions_csv.py`

**Why**
Re-runs on different machines must produce identical “resolves.” Hashes enable stable identity independent of file path.

**Changes**

1. `src/utils/hashing.py`:

   * `sha256_file(path: Path) -> str` (streamed, 4–8 MB chunks).

2. `src/indexer/media_index.py`:

   * Compute and store `sha256` for each media artifact once.

3. `src/schema/message.py`:

   * Add optional `derived["media_sha256"]: str | None`.

4. Writers:

   * `messages_csv` & `exceptions_csv` include `media_sha256` column when known.

**Tests**

* `tests/utils/test_hashing_streaming.py`:

  * Identical hash for same content with different paths; stable across runs.

* `tests/resolver/test_media_hash_in_outputs.py`:

  * Resolved messages have `media_sha256` in `messages.csv` and `messages.jsonl`.

**Acceptance**

* Re-running same fixture on another machine yields identical `media_sha256` values.
* Hashing adds ≤5% wall-clock to indexing on ~1k-file fixture.

---

### M2.12 — Scoring defaults & decisive margin (τ) + golden fixtures

**Files:**

* `config/media.yaml`
* `src/resolvers/scoring.py`
* `tests/fixtures/golden/easy_chat/`
* `tests/golden/test_easy_fixture_resolution.py`

**Why**
The spec names feature weights but not canonical defaults, risking drift. Pin them and assert via golden tests.

**Changes**

* `config/media.yaml`:

  ```yaml
  resolver:
    weights: {hint: 3, ext: 2, seq: 1, mtime: 1}
    tau: 0.75
    tie_margin: 0.02
  ```

* `src/resolvers/scoring.py`:

  * Load defaults; allow CLI overrides.

* Golden fixture: `tests/fixtures/golden/easy_chat/` with unambiguous media.


**Tuning guidance**

* Start with the default weights and `tau` on your golden fixtures.
* Track:

  * `resolved_media` vs `unresolved_media` vs `ambiguous_media` in `metrics.json`.
  * The share of `<Media omitted>` rows that land in each bucket.

* Heuristics:

  * If too many obviously-resolvable items land in `ambiguous_media` or `unresolved_media` (> ~10% of `<Media omitted>`):

    * Increase `weights.hint` first (neighbor text hints), then `weights.seq`.

  * If the resolver chooses the wrong *type* (e.g. video instead of image):

    * Increase `weights.ext` (extension priority).

  * If recency (mtime) seems to dominate hints and WA#### too strongly:

    * Decrease `weights.mtime` slightly.

* `tau=0.75` means: the top candidate’s score must beat the second candidate by at least 0.75 points to be considered “decisive”.

* Any intentional change to weights or `tau` should:

  * Be noted in `CHANGELOG.md`.
  * Be accompanied by updated golden fixtures (see “Golden fixture maintenance” below).


**Tests**

* `tests/resolver/test_scorer_defaults_loaded.py`
* `tests/golden/test_easy_fixture_resolution.py` — snapshot/golden of `messages.jsonl` & `messages.csv`.

**Acceptance**

* With default config, golden fixture produces an identical CSV/JSON snapshot across OSes.
* Changing any default fails the golden test until schema version is bumped.

**Tuning guidance (for humans, not code)**

When adjusting weights or `tau`, use golden fixtures as your guardrails:

- Start with the default config:

  ```yaml
  resolver:
    weights: {hint: 3, ext: 2, seq: 1, mtime: 1}
    tau: 0.75
    tie_margin: 0.02


* Measure on golden fixtures:

  * `resolution_rate` = % of `<Media omitted>` that resolve to the correct file.
  * `ambiguous_media_rate` = % ending up with `status_reason="ambiguous_media"`.
  * `wrong_type_matches` = cases where e.g. an image candidate wins for a voice message.

* Heuristics:

  * If **`ambiguous_media_rate` > ~10%** on realistic chats → try **increasing `hint` weight** so explicit mentions in text/captions dominate weak `mtime` ties.
  * If you see **wrong-type matches** (e.g. matching only on timestamp) → **increase `ext` weight** so file type agreement matters more.
  * If you want the resolver to be **more decisive**, increase `tau` slightly (e.g. `0.80`):

    * `tau = 0.75` means the top candidate must beat the second by **75% of its score** (decisive margin).
  * If it’s too conservative (too many unresolved), nudge `tau` down (e.g. `0.70`) and re-check wrong-match rate.

* Process:

  * Every time you change defaults in `config/media.yaml`, **document the rationale** briefly in `CHANGELOG.md` (or equivalent) with:

    * Old vs new weights/`tau`.
    * Fixture stats before/after (resolution %, ambiguous %, wrong-type count).
  * Golden tests must be updated deliberately when defaults change; a changed golden snapshot is a **review signal**, not something to auto-update.


---

### M2.13 — Temporal robustness: clock skew & day-boundary drift window

**Files:**

* `config/media.yaml`
* `src/media_resolver.py`
* `src/resolvers/scoring.py`
* `docs/README_ASSUMPTIONS.md`

**Why**
WhatsApp media often saves minutes/hours after the message. Add a drift window to candidate selection.

**Changes**

* `config/media.yaml`:

  ```yaml
  resolver:
    clock_drift_hours: 4
  ```

* `src/media_resolver.py`:

  * When collecting candidates, include files whose `mtime` within ±`clock_drift_hours` of message time and within a “session window”.

**Tests**

* `tests/resolver/test_clock_drift_window.py` — +2h saved files resolve correctly.
* `tests/resolver/test_day_boundary_midnight.py` — 23:58 vs 00:03 handled correctly.

**Acceptance**

* On a mixed-time fixture, enabling drift increases resolves without increasing `ambiguous_media` beyond +1% relative.

---

### M2.14 — Filename pattern expansion (Android/iOS variants) + preference rules

**Files:**

* `src/indexer/filename_patterns.py`
* `src/indexer/media_index.py`
* `src/media_resolver.py`
* `docs/README_CONTRACTS.md`

**Why**
WhatsApp uses multiple stems: `IMG-YYYYMMDD-WA####`, `VID-`, `PTT-`, `AUD-`, `DOC-`, plus localized/edited copies. Indexer must parse stems robustly.

**Changes**

* `src/indexer/filename_patterns.py`:

  * Regexes extracting `{stem, yyyymmdd?, wa_seq?, kind}`.
  * Handle OS “copy” suffixes: `(...)`, `-copy`, localized equivalents.

* `src/indexer/media_index.py`:

  * Store parsed tokens; expose search by `(wa_seq, kind)` fast-path.

* `src/media_resolver.py`:

  * Prefer candidates agreeing on `(wa_seq, kind)` over those matching only ext/mtime within `tie_margin`.

**Tests**

* `tests/indexer/test_filename_patterns_variants.py`
* `tests/resolver/test_wa_seq_precedence.py`
* `tests/indexer/test_copy_suffix_stripping.py`

**Acceptance**

* 95%+ of media in a realistic 500-file fixture gets parsed `(wa_seq, kind)` tokens.
* Disambiguation rate drops measurably on Android-heavy exports.

---

## M2 — Acceptance Criteria

* For the “easy” fixture, ≥95% of `<Media omitted>` entries resolve to an actual file with deterministic mapping across runs.
* For the “ambiguous” fixture, resolver does **not** guess; it leaves items unresolved, writes ranked candidates to `exceptions.csv`, and sets `status_reason` (`unresolved_media` vs `ambiguous_media`).
* Ladder ordering & tie-break rules enforced exactly; tests cover each rung in isolation.
* `map_media` never throws on missing folders or empty days; it degrades to unresolved with a logged exception.

---

## M2 — Test Plan (Quick List)

* `test_index_groups_by_day_and_type`
* `test_hints_prefer_same_sender_then_global`
* `test_ext_priority_applies_before_seq_and_mtime`
* `test_seq_closest_wins_over_mtime_when_ext_equal`
* `test_tie_breaker_size_then_lexical`
* `test_decisive_margin_resolves_easy_case`
* `test_ambiguous_yields_csv_and_no_assignment`
* `test_status_reason_set_for_unresolved_and_ambiguous`
* `test_smoke_cli_media_resolver`
* `test_status_reason_ambiguous_media`
* `test_exceptions_csv_ambiguous_blob`
* `test_hashing_streaming`
* `test_media_hash_in_outputs`
* `test_scorer_defaults_loaded`
* `test_easy_fixture_resolution`
* `test_clock_drift_window`
* `test_day_boundary_midnight`
* `test_filename_patterns_variants`
* `test_wa_seq_precedence`
* `test_copy_suffix_stripping`

---

## M2 — Running & Commit Guidelines

**Run**

```bash
pytest -q
python scripts/resolve_media.py --root tests/fixtures/media_omitted_easy/
```

**PR**

* One task per PR (≤ ~300 LOC, ≤ 5 files), include fixtures & tests, and a short README delta for M2 behavior/knobs.
* Title: `feat(media): M2.x <short description>`.
* Body: what changed, how verified, decisive-margin/tie-break values used.

---

# M3 — Audio Pipeline (ffmpeg/Whisper/VAD/chunking/caching) + tests

**Milestone Goal**
Convert OPUS (and other WhatsApp voice formats) → WAV, chunk into 120s windows with 0.25s overlap, optionally run VAD for speech metrics/segmentation (ASR is still run on all chunks), call Whisper/Google (or compatible ASR) with retries, cache artifacts & metadata, and set `status`, `status_reason`, and `partial` precisely on each `Message`.


**Code surface (expected files)**

* `src/audio_transcriber.py`
* `src/utils/asr.py`
* `src/utils/vad.py`
* `src/utils/cost.py`
* `src/utils/hashing.py` (shared with M2.11 if reused)
* `tests/test_audio_transcriber.py`
* `tests/fixtures/voice_multi/`
* `tests/fixtures/voice_asr_failure/`
* `tests/fixtures/voice_nonspeech/`

**Behavioral outline**

1. Take a `Message` with `kind="voice"` and `media_filename` resolved by M2.
2. Use ffmpeg to normalize audio → 16 kHz mono WAV.
3. Optionally run VAD on WAV to compute speech metrics / segments (for debugging or smarter chunking), but do not treat this as a hard skip gate.
4. Chunk into 120s segments with 0.25s overlap.
5. Call ASR provider per chunk (Whisper local/API) with timeouts/retries.
6. Join chunk transcripts in order; attach transcript and rich metadata under `msg.derived["asr"]`.
7. Write a cache entry `cache/audio/{hash}.json` capturing billing, duration, VAD stats, costs, and status.
8. Map any failures to clear `status`, `status_reason`, and `partial`.

*All tasks follow global guardrails.*

---

## M3.1 — AudioTranscriber Skeleton & Config

**File:** `src/audio_transcriber.py`

**Objective**
Create the basic `AudioTranscriber` surface, config plumbing, and minimal test harness with no real ffmpeg/VAD/ASR yet.

**Deliverables**

* `AudioConfig` (dataclass or TypedDict):

  * `ffmpeg_bin`, `sample_rate`, `channels`
  * `chunk_seconds`, `chunk_overlap_seconds`
  * `vad_min_speech_ratio`, `vad_min_speech_seconds`
  * `asr_provider`, `asr_model`, `asr_timeout_seconds`, `asr_max_retries`
  * `cache_dir`

* `AudioTranscriber` with:

  ```python
  class AudioTranscriber:
      def __init__(self, cfg: AudioConfig): ...
      def transcribe(self, m: Message) -> None: ...
  ```

**Subtasks**

1. Define `AudioConfig` with defaults:

   * `sample_rate = 16000`
   * `channels = 1`
   * `chunk_seconds = 120`
   * `chunk_overlap_seconds = 0.25`

2. Wire config into `__init__`.

3. In `transcribe`, assert `m.kind == "voice"`; no-op for others (for now).

4. Add placeholder `m.derived["asr"]` structure with `pipeline_version` and `config_snapshot`.

**Verification & Tests**

* `test_audio_transcriber_smoke_imports` — instantiate with default config and dummy `Message`.
* `test_audio_transcriber_sets_empty_derived_asr` — `derived["asr"]` created after `transcribe()` on voice message.

---

## M3.2 — ffmpeg OPUS→WAV Conversion (16 kHz mono) with Timeout/Retries

**File:** `src/audio_transcriber.py`

**Objective**
Convert WhatsApp OPUS (and similar) audio to normalized WAV using ffmpeg with a timeout and retry policy; handle failures gracefully.

**Deliverables**

* `_to_wav(m: Message) -> Path | None` method.

**Behavior**

* Input: `Message` with `media_filename` pointing to original audio.
* Output: path to 16kHz mono WAV in temp or cache dir.
* On repeated ffmpeg failure/timeouts:

  * `m.status="failed"`
  * `m.status_reason="ffmpeg_failed"` or `"timeout_ffmpeg"`
  * `m.content_text="[AUDIO CONVERSION FAILED]"` (if empty).
  * `m.partial=False`.

**Subtasks**

1. Use `subprocess.run` with `cfg.ffmpeg_bin`, forcing `-ar 16000 -ac 1 -f wav`.
2. Implement retry loop up to `cfg.ffmpeg_max_retries`.
3. Capture stderr tail into `m.derived["asr"]["ffmpeg_log_tail"]` (trim to last 2KB).
4. Clean up temp files on failure.

**Verification & Tests**

* Corrupted OPUS file in `tests/fixtures/voice_asr_failure/`.
* `test_ffmpeg_conversion_success_creates_wav`.
* `test_ffmpeg_failure_sets_status_and_placeholder`.

---

## M3.3 — VAD Wrapper & Speech Metrics (no hard gate)

**File:** `src/utils/vad.py` & `src/audio_transcriber.py`

**Objective**  
Implement VAD over normalized WAV to compute speech metrics and optional segments.  
VAD may flag “mostly silence” but **must not** skip ASR entirely; ASR still runs on all chunks.

**Behavior**

* After `_to_wav`, if `cfg.enable_vad` (or equivalent), call `run_vad(wav_path, cfg)`.
* Always attach `vad_stats` under `derived["asr"]["vad"]`:

  * `speech_ratio`, `speech_seconds`, `total_seconds`, `segments`.

* You may compute a helper flag using the VAD thresholds, e.g.:

  ```python
  derived["asr"]["vad"]["is_mostly_silence"] = (
      speech_ratio < cfg.vad_min_speech_ratio
      or speech_seconds < cfg.vad_min_speech_seconds
  )


* **Do not** set `m.status`, `m.status_reason`, or `m.content_text` based on VAD alone.
  Those are driven by the ASR outcomes (see M3.6 and M3.8).

* Even when `is_mostly_silence` is `True`, the message must still flow through:

  * Chunking (M3.4)
  * ASR per chunk (M3.5/M3.6)
  * Error mapping & partial logic (M3.8)

**Deliverables**

* `src/utils/vad.py`:

  ```python
  class VadStats:
      speech_ratio: float
      speech_seconds: float
      total_seconds: float
      segments: list[tuple[float, float]]

  def run_vad(wav_path: Path, cfg) -> VadStats: ...
  ```

* In `AudioTranscriber.transcribe`:

  * After `_to_wav`, call `run_vad` when `cfg.enable_vad` is true.
  * Attach the resulting `VadStats` under `m.derived["asr"]["vad"]`.
  * Do **not** early-return or mark the message as `skipped` based on VAD; continue into chunking + ASR.

**Verification & Tests**

* Fixture: `tests/fixtures/voice_nonspeech/`.
* `test_vad_stats_recorded_for_nonspeech_audio` — VAD runs and populates `derived["asr"]["vad"]` for mostly-silent audio; message still proceeds to ASR; `m.status` is determined by ASR outcome.
* `test_vad_stats_recorded_for_speech_audio` — VAD runs on a short speech clip and records reasonable `speech_ratio` / `speech_seconds`.
---

## M3.4 — Chunking Strategy (120s, 0.25s Overlap) & Metadata

**File:** `src/audio_transcriber.py`

**Objective**
Chunk normalized WAV audio into fixed windows with overlap, emit deterministic chunk WAVs, and produce a stable manifest that feeds ASR.

**Deliverables**

* `_chunk_wav(wav_path: Path, cfg) -> list[dict]` with:

  * `chunk_index` (0-based), `start_sec`, `end_sec`, `duration_sec`
  * `wav_chunk_path` (16 kHz mono, deterministic filename) and/or sample `offsets`
  * optional `num_samples` to aid sanity checks

* Attach manifest to `derived["asr"]["chunks"]` before ASR runs.

**Behavior**

* Inputs are the 16 kHz mono WAV produced by `_to_wav`; do not change sample rate/channels here.
* Defaults: `cfg.chunk_seconds = 120.0`, `cfg.chunk_overlap_seconds = 0.25` (clamp overlap to `< chunk_seconds`).
* Chunk loop:
  * start at `0.0`; `end = min(start + chunk_seconds, total_seconds)`
  * advance `start = end - chunk_overlap_seconds`
  * stop when `start >= total_seconds` (skip zero/negative durations)
* Write chunks via Python slicing (`wave`/`soundfile`), not another `ffmpeg` call.
* Place chunk files under a deterministic directory (e.g., `cfg.tmp_dir / "chunks"`) named `chunk_{i:04d}.wav` so reruns are identical.
* Manifest ordering must be stable (sorted by `chunk_index`); round floats (e.g., 3dp) for determinism.

**Verification & Tests**

* Synthetic ~5-minute audio in `voice_multi/` or stubbed duration.
* `test_chunking_respects_length_and_overlap`.
* `test_chunk_manifest_stable_order`.

---


## M3.5 — ASR Client Wrapper (Whisper/Provider Abstraction)

**File:** `src/utils/asr.py`

**Objective**
Abstract ASR provider calls behind a clean interface with timeout/retry behavior per chunk and deterministic error mapping.

**Deliverables**

* `AsrChunkResult` (dataclass or TypedDict) including:
  * `status` ∈ `{"ok","error"}` (enum or Literal)
  * `text` (empty string on failure), `language` (optional)
  * `duration_sec`, `start_sec`, `end_sec`
  * `error` (str | None), `provider_meta` (dict for raw payloads)
* `AsrClient` with:

  ```python
  def __init__(self, cfg): ...
  def transcribe_chunk(self, wav_path: Path, start_sec: float, end_sec: float) -> AsrChunkResult: ...
  ```

**Behavior**

* Support provider/model knobs in `cfg` (e.g., `cfg.asr_provider`, `cfg.asr_model`, `cfg.asr_language`).
* Enforce per-chunk timeout (`cfg.asr_timeout_seconds`) and retry (`cfg.asr_max_retries`, default 1 retry after the first failure).
* Normalize provider responses into `AsrChunkResult` with deterministic defaults:
  * On success: `status="ok"`, `error=None`, `text` is stripped, `language` best-effort from provider.
  * On failure: `status="error"`, `text=""`, `error` contains a concise message; raise only after retries exhausted so caller can map status (M3.8).
* Do not mutate global state; pure call per chunk.
* Include light logging hooks (debug-level) to aid tests but avoid noisy stdout/stderr by default.

**Verification & Tests**

* Mocked ASR in tests:

  * `test_asr_chunk_success_flow`.
  * `test_asr_chunk_error_raises`.

---

---

## M3.6 — Chunk Loop, Transcript Assembly & Derived Payload

**File:** `src/audio_transcriber.py`

**Objective**
Wire chunking and ASR to produce the final transcript, attach it to `Message`, and populate `derived["asr"]` with chunk-level results.

**Behavior**

* Only process `kind="voice"` with a resolved `media_filename`; others return untouched.
* Input: chunk manifest from `_chunk_wav`; call `AsrClient.transcribe_chunk` for each chunk in order.
* Transcript assembly:
  * Use the per-chunk `text` in order; join with `"\n"` (deterministic).
  * If `m.content_text` was empty, set it to the joined transcript; otherwise append with a separator (e.g., `\n`).
* Derived payload:
  * Initialize `m.derived["asr"]` if missing.
  * Store `provider`, `model`, `language` (best effort), `total_duration_seconds`, and `chunks`.
  * Each chunk entry records `chunk_index`, `start_sec`, `end_sec`, `duration_sec`, `status`, `text`, `error` (if any), `language` (if any), and `wav_chunk_path`.
* Status discipline (full mapping in M3.8):
  * If all chunks return `status="ok"` → `m.status="ok"`, `m.partial=False`.
  * Do not decide partial/failed here; defer to M3.8 for error mapping and `status_reason`.
* Determinism: preserve manifest order; avoid nondeterministic logging; do not mutate `chunks` after assembly other than adding ASR results.

**Verification & Tests**

* Fixture `tests/fixtures/voice_multi/`.
* Mocked ASR returning `f"chunk-{i}"`:

  * `test_long_voice_chunk_and_join`.
  * `test_derived_asr_structure`.

---

## M3.7 — Caching (cache/audio/{hash}.json) & Idempotent Re-Runs

**File:** `src/audio_transcriber.py`, `src/utils/hashing.py`, `src/utils/cost.py`

**Objective**
Add content-addressed cache so repeated runs don’t recompute ffmpeg/VAD/ASR, and store rich metadata for billing/metrics.

**Deliverables**

* `_make_cache_key(m: Message, cfg) -> str` based on:

  * audio file content hash,
  * core pipeline knobs (provider, model, chunk_seconds, overlap, VAD thresholds).

* `_load_cache(key: str) -> dict | None`

* `_write_cache(key: str, payload: dict) -> None`

* Cache file: `cfg.cache_dir / "audio" / f"{key}.json"`.

**Behavior**

* Cache key must change if audio content or core ASR/VAD/chunking knobs change; include schema/versioning fields if needed for forward-compat.
* Cache payload should capture everything needed to hydrate the message without re-running work:
  * final transcript, `status`, `status_reason`, `partial`
  * `derived["asr"]` including chunks, vad, provider/model/language, cost estimates
  * any human-readable placeholders used on failure
* On cache hit:
  * short-circuit ffmpeg/VAD/ASR/chunking; apply cached transcript/status/derived to `Message`
  * keep deterministic ordering and default fields; do not mutate cached payload
* On cache miss:
  * run normal pipeline; before returning, write payload JSON atomically (tmp + rename) with UTF-8 and stable key order.
* Cache directory is created if missing; avoid crashing if cache is unwritable—log and continue without cache.
* Cost helpers (`utils/cost.py`) may be invoked to include estimated/actual cost fields in payload.

**Verification & Tests**

* `test_cache_write_and_read_roundtrip`.
* `test_cache_hit_skips_work`.
* `test_cache_respects_config_changes`.

---

## M3.8 — Error Mapping, Partial Transcripts & Status Discipline

**File:** `src/audio_transcriber.py`

**Objective**
Map all failure/partial cases to clear `status`, `status_reason`, and `partial` semantics, grounded in chunk outcomes and ffmpeg/VAD stages.

**StatusReason codes used** (must match the global enum):

* `"ffmpeg_failed"`, `"timeout_ffmpeg"`
* `"vad_no_speech"`
* `"asr_failed"`, `"timeout_asr"`
* `"asr_partial"`
* `"audio_unsupported_format"`

**Behavior**

* If ffmpeg conversion failed or timed out (no WAV):

  * `m.status="failed"`, `m.status_reason="ffmpeg_failed"` or `"timeout_ffmpeg"`.
  * `m.content_text = m.content_text or "[FFMPEG CONVERSION FAILED]"`.
  * `m.partial=False`; skip ASR entirely.

* If audio unsupported (pre-check):

  * `m.status="failed"`, `m.status_reason="audio_unsupported_format"`.
  * `m.content_text = m.content_text or "[UNSUPPORTED AUDIO FORMAT]"`.
  * `m.partial=False`; skip ASR.

* If **all** chunks fail in ASR:

  * `m.status="failed"`, `m.status_reason="asr_failed"` or `"timeout_asr"`.
  * `m.content_text = m.content_text or "[AUDIO TRANSCRIPTION FAILED]"`.
  * `m.partial=False`.

* If **some** chunks succeed, some fail:

  * Build transcript from successful chunks only.
  * `m.status="partial"`, `m.status_reason="asr_partial"`, `m.partial=True`.

* If all chunks succeed:

  * `m.status="ok"`, `m.status_reason=None`, `m.partial=False`.

* VAD observation:

  * Never sets `status`/`status_reason`; may set `derived["asr"]["vad"]["is_mostly_silence"]`.

* Always populate:

  * `derived["asr"]["error_summary"]` with counts (ok/error), last error message, timeout flags.
  * Per-chunk `status`/`error` already recorded in `derived["asr"]["chunks"]`.

**Verification & Tests**

* Fixture `tests/fixtures/voice_asr_failure/`.
* `test_asr_full_failure_sets_failed_status`.
* `test_asr_partial_failure_sets_partial_status`.


---

## M3.9 — Cost Estimation & Billing Metadata (`src/utils/cost.py`)

**Objective**
Estimate cost per audio message based on provider/model and seconds transcribed; write this into cache and `derived["asr"]`.

**Deliverables**

* `estimate_asr_cost(seconds: float, provider: str, model: str, billing: str) -> float`.
* `COST_TABLE` mapping `(provider, model, billing)` to `$ / minute` or similar.
* Optional helper to bundle totals per run (`accumulate_costs(messages: list[Message]) -> dict`).

**Behavior**

* Rates are deterministic constants checked in code/tests (no network lookups).
* Billing unit should handle per-minute rounding rules per provider (e.g., ceiling to nearest 30s/min).
* Cost must be written into `m.derived["asr"]["cost"]` (per message) and mirrored into cache payload.
* No side effects beyond returning numeric cost; caller owns formatting/currency symbols.
* Changing provider/model or billing plan must change cache key (see M3.7 rules).

**Verification & Tests**

* `test_cost_estimate_basic`.
* `test_cost_written_to_cache`.

---

## M3.10 — Audio CLI Smoke Test & README

**File:** `scripts/transcribe_audio.py`, `README_M3.md`

**Objective**
Provide a small CLI to transcribe all voice messages in a folder for manual inspection and document behavior.

**Deliverables**

* `scripts/transcribe_audio.py`:

  * Args: `--root`, `--no-cache` optional.
  * Pipeline:

    * Use M1 parser to get `Message[]`.
    * Use M2 resolver to attach `media_filename`.
    * Instantiate `AudioTranscriber(cfg)` and call `transcribe(m)` for each `kind="voice"`.
    * Emit summary: `N_ok, N_partial, N_failed, N_skipped`.

* `README_M3.md`:

  * Summarize pipeline: ffmpeg, VAD, chunking, ASR, caching.
  * Document `status_reason` codes and cache JSON schema.
  * Clarify that VAD is used for metrics/segmentation only and is not a hard no-speech gate; ASR is still run on all audio.

**Verification & Tests**

* `test_smoke_cli_audio_transcriber` — run CLI against tiny synthetic fixture with mocked ASR.

---

## M3 — Acceptance Criteria

* For a long voice message fixture (`voice_multi/`):

  * Audio converted to 16 kHz mono WAV.
  * Chunked into deterministic 120s windows with 0.25s overlap.
  * ASR called once per chunk, joined into final transcript.
  * Cache JSON at `cache/audio/{hash}.json` contains all required fields (incl. VAD stats & cost).

* For corrupted/bad files (`voice_asr_failure/`):

  * ffmpeg/ASR failures do **not** crash the run.
  * Messages marked `status="failed"` or `status="partial"` with correct `status_reason`, human-readable placeholders present.


* For non-speech audio (`voice_nonspeech/`):

  * VAD (if enabled) records low `speech_ratio` / `speech_seconds` under `derived["asr"]["vad"]`.
  * ASR is still invoked over the chunks. It is acceptable for the final transcript to be empty or a short `[No discernible speech]` placeholder, depending on ASR behavior.
  * `m.status` is driven by ASR outcome (`"ok"`, `"partial"`, or `"failed"`), not by VAD alone; there is no requirement to mark such messages as `"skipped"`.


* Caching is idempotent and deterministic:

  * Re-running on same root & config doesn’t invoke ffmpeg/ASR again.
  * Changing core config knobs changes cache key and forces recomputation.

* All M3 tests pass; M1/M2 tests remain green.

---

## M3 — Test Plan (Quick List)

* `test_audio_transcriber_smoke_imports`
* `test_audio_transcriber_sets_empty_derived_asr`
* `test_ffmpeg_conversion_success_creates_wav`
* `test_ffmpeg_failure_sets_status_and_placeholder`
* `test_vad_stats_recorded_for_nonspeech_audio`
* `test_vad_stats_recorded_for_speech_audio`
* `test_chunking_respects_length_and_overlap`
* `test_chunk_manifest_stable_order`
* `test_asr_chunk_success_flow`
* `test_asr_chunk_error_raises`
* `test_long_voice_chunk_and_join`
* `test_derived_asr_structure`
* `test_cache_write_and_read_roundtrip`
* `test_cache_hit_skips_work`
* `test_cache_respects_config_changes`
* `test_asr_full_failure_sets_failed_status`
* `test_asr_partial_failure_sets_partial_status`
* `test_cost_estimate_basic`
* `test_cost_written_to_cache`
* `test_smoke_cli_audio_transcriber`

---

## M3 — Running & Commit Guidelines

**Run**

```bash
pytest -q
python scripts/transcribe_audio.py --root tests/fixtures/
```

**PR**

* One M3.x task per PR (≤ ~300 LOC, ≤ 5 files).
* Title: `feat(audio): M3.x <short description>`.
* Body:

  * Which parts of the pipeline were implemented (ffmpeg/VAD/chunking/ASR/cache/cost).
  * Which fixtures were used.
  * Exact tests run (paste `pytest` command + CLI smoke if relevant).

---





# M5 — Renderer (Text View & Later MD→PDF)

**Milestone Goal**
Provide human-friendly views of the chat where voice messages appear as **transcribed text** in-line, plus a lightweight **transcript preview** powering the UI. Later, add a Markdown renderer as the basis for MD→PDF with fonts.

All M5 tasks consume `Message[]` **after M1–M3** and must be **pure, deterministic writers** (no side effects beyond the output files they own).

---

## M5.1 — Text Renderer (`chat_with_audio.txt`)

**Objective**
Take a fully processed `Message[]` (after M1–M3) and render a single deterministic UTF-8 text file:

```text
YYYY-MM-DD HH:MM:SS - Sender: content_text_or_caption
```

where `content_text` for `kind="voice"` already contains the ASR transcript from M3.

**Code surface (expected files)**

* `src/writers/text_renderer.py`   — pure renderer for `Message[]`.
* `scripts/render_txt.py`          — CLI wrapper.
* `tests/test_text_renderer.py`    — unit & golden tests.
* `tests/fixtures/chat_with_audio/` — small end-to-end fixture.

---

### API & Options

**File:** `src/writers/text_renderer.py`

Expose a small, explicit API:

```python
from dataclasses import dataclass
from pathlib import Path
from typing import Literal
from src.schema.message import Message

@dataclass
class TextRenderOptions:
    hide_system: bool = False
    show_status: bool = False
    flatten_multiline: bool = False  # False = indent continuation lines

def render_messages_to_txt(
    messages: list[Message],
    out_path: Path,
    options: TextRenderOptions | None = None,
) -> dict:
    """
    Render messages to a deterministic UTF-8 text file.

    Returns a summary dict, e.g.:
      {
        "total": 523,
        "text": 410,
        "voice": 72,
        "media": 31,
        "system": 10,
      }
    """
```

* If `options is None`, use `TextRenderOptions()` defaults.
* Writer must open file as:

  ```python
  open(out_path, "w", encoding="utf-8", newline="\n")
  ```

  to enforce **LF `\n` only** across platforms.

---

### Timestamp & Ordering

* Input: any iterable of `Message` instances (typically loaded from `messages.jsonl`).
* **Sort** by `msg.idx` ascending before rendering (defensive).
* `ts_human` is derived **only** from `msg.ts` (ISO string) as:

  ```text
  YYYY-MM-DD HH:MM:SS
  ```

  * 24-hour clock, zero-padded, no timezone suffix.
  * Implementation may reuse helpers from `src/utils/dates.py` but must be deterministic and locale-independent.

---

### Rendering rules

For each `Message` in `idx` order:

1. **Skip caption-merge “tails”**

   * If `status=="skipped"` **and** `status_reason=="merged_into_previous_media"` → **omit** this message completely (its text lives in the media caption).

2. **Base line (header)**

   First physical line for a message is always:

   ```text
   {ts_human} - {sender}: {first_body_line}{status_suffix?}
   ```

   Where:

   * `ts_human` – as defined above.
   * `sender` – raw `msg.sender` string (no normalization).
   * `first_body_line` – computed from `body` (see below).
   * `status_suffix` – only when `options.show_status=True` (see **Status suffix**).

3. **Body selection**

   Compute a logical `body` string as:

   1. If `msg.kind=="system"` → handled separately (see below).
   2. Else, if `msg.content_text` is non-empty → `body = msg.content_text`.
   3. Else, if `msg.caption` is non-empty → `body = msg.caption`.
   4. Else, fallback by `kind`:

      * `kind=="voice"`

        * If `msg.status=="failed"` → `"[AUDIO TRANSCRIPTION FAILED]"` (respecting M3).
        * Else → `"[UNTRANSCRIBED VOICE NOTE]"`.

      * `kind=="image"` → `f"[IMAGE: {msg.media_hint or 'unknown'}]"`.

      * `kind=="video"` → `f"[VIDEO: {msg.media_hint or 'unknown'}]"`.

      * `kind=="document"` → `f"[DOCUMENT: {msg.media_hint or 'unknown'}]"`.

      * `kind=="sticker"` → `"[STICKER]"`.

      * `kind=="unknown"` → `"[UNKNOWN MESSAGE]"`.

   * For any `status=="skipped"` with a reason **other than** `merged_into_previous_media`, render a generic placeholder:

     ```text
     body = f"[SKIPPED: {msg.status_reason or 'reason_unknown'}]"
     ```

4. **System messages**

   For `kind=="system"`:

   * If `options.hide_system` → **skip** rendering this message entirely.
   * Else:

     ```text
     {ts_human} - SYSTEM: {system_body}
     ```

     Where:

     * If `msg.content_text` is non-empty → `system_body = msg.content_text`.
     * Else if `msg.raw_block` is non-empty → `system_body = msg.raw_block`.
     * Else → `system_body = "[SYSTEM MESSAGE]"`.

5. **Multiline handling**

   After computing `body` (or `system_body`), handle newlines:

   * Let `lines = body.splitlines()` (empty list treated as `[""]`).

   * If `options.flatten_multiline` is **True**:

     * `flat = " ".join(l.strip() for l in lines if l.strip() != "")`
       (collapse multiple whitespace; drop purely empty lines).
     * Use `flat` as `first_body_line` in the header; **no continuation lines**.

   * If `options.flatten_multiline` is **False** (default):

     * First physical line:

       ```text
       {ts_human} - {sender_or_SYSTEM}: {lines[0]}{status_suffix?}
       ```

     * For each subsequent line `lines[1:]`, emit an additional physical line:

       ```text
           {line}
       ```

       (4 spaces, then the raw continuation text, including blanks).

     * `status_suffix` (when enabled) attaches to the **first** line only.

6. **Status suffix (optional)**

   When `options.show_status` is **True**, append `status_suffix` to the **first** physical line for the message:

   ```text
   [status={msg.status}{", reason=" + msg.status_reason if msg.status_reason else ""}]
   ```

   Examples:

   * `status="ok", status_reason=None` → `[status=ok]`
   * `status="partial", status_reason="asr_partial"` → `[status=partial, reason=asr_partial]`
   * `status="failed", status_reason="ffmpeg_failed"` → `[status=failed, reason=ffmpeg_failed]`

---

### CLI: `scripts/render_txt.py`

**Arguments**

* `--messages` (required): path to a `messages.jsonl` produced after M3, containing serialized `Message` records.
* `--out` (required): path to `chat_with_audio.txt`.
* `--hide-system` (optional flag): maps to `TextRenderOptions.hide_system=True`.
* `--show-status` (optional flag): maps to `TextRenderOptions.show_status=True`.
* `--flatten-multiline` (optional flag): maps to `TextRenderOptions.flatten_multiline=True`.

**Behavior**

1. Load `Message[]` from the JSONL file.
2. Sort by `idx` (defensive).
3. Build `TextRenderOptions` from CLI flags.
4. Call `render_messages_to_txt(...)` and capture the returned summary dict.
5. Print a tiny summary to stdout, e.g.:

   ```text
   Rendered 523 messages (text=410, voice=72, media=31, system=10) to chat_with_audio.txt
   ```

---

### Determinism

Given the same `messages.jsonl` and flags:

* `chat_with_audio.txt` must be **byte-for-byte identical** across runs and machines:

  * Same ordering by `idx`.
  * Identical timestamp formatting.
  * Identical newline style (`\n` only).
  * Identical placeholder strings & status suffixes.

---

### Verification & Tests

**Fixtures**

* `tests/fixtures/chat_with_audio/`:

  * `_chat.txt` with:

    * normal text messages (including multiline),
    * `PTT-...opus (file attached)` lines,
    * image/video/document lines,
    * system messages,
    * at least one `status="skipped", status_reason="merged_into_previous_media"` row.

  * `messages.jsonl` representing the output *after* M1–M3 (ASR can be mocked to simple `"chunk-0"` text).

  * `expected_basic.txt` — golden for default options.

  * `expected_hide_system.txt` — golden with `--hide-system`.

  * `expected_show_status.txt` — golden with `--show-status`.

  * `expected_multiline_indent.txt` — golden for multiline behavior.

**Tests: `tests/test_text_renderer.py`**

* `test_text_renderer_basic`
  Renders fixture `messages.jsonl` with default options and asserts content matches `expected_basic.txt`.

* `test_text_renderer_skips_merged_caption_rows`
  Asserts that `status="skipped", status_reason="merged_into_previous_media"` rows never appear in output.

* `test_text_renderer_hide_system_flag`
  With `hide_system=True` (or `--hide-system`), system lines are omitted, all others unchanged (compare against `expected_hide_system.txt`).

* `test_text_renderer_untranscribed_voice_placeholder`
  A voice message with empty `content_text` and non-failed status renders `[UNTRANSCRIBED VOICE NOTE]`.

* `test_text_renderer_multiline_indent_behavior`
  Messages containing `\n` in `content_text` are rendered with a single header line and indented continuation lines (or flattened when `flatten_multiline=True`).

* `test_text_renderer_show_status_flag`
  With `show_status=True`, first line per message ends with `[status=...]` and optional `reason`, matching `expected_show_status.txt`.

* `test_text_renderer_timestamp_format_and_newlines`
  Asserts that each line begins with `\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}` and that output only contains `\n` newlines (no `\r\n`).

* `test_text_renderer_skipped_non_merged_are_rendered_with_placeholder`
  A message with `status="skipped"` and other `status_reason` is still rendered with `[SKIPPED: ...]` body.

---

### Acceptance Criteria (M5.1)

Running:

```bash
python scripts/render_txt.py \
    --messages tests/fixtures/chat_with_audio/messages.jsonl \
    --out /tmp/chat_with_audio.txt
```

with default flags produces a deterministic text file that:

* Contains all non-merged messages in `idx` order.
* Shows ASR transcripts in place of raw filenames for `kind="voice"` where M3 succeeded.
* Uses clear placeholders for any remaining untranslated/failed media.
* Uses **exactly** `YYYY-MM-DD HH:MM:SS` timestamps and `\n` newlines.
* Produces the expected summary line and passes all `test_text_renderer.py` tests.
* Adding M5.1 does **not** change behavior or tests for M1–M3.

---

## M5.2 — Transcript Preview Writer (`preview_transcripts.txt`)

**Objective**
Provide a compact, append-friendly **preview format for voice notes** that can be tailed by the UI and tools, without re-parsing full JSONL or the large text file.

**Code surface (expected files)**

* `src/writers/text_renderer.py`        — add preview helpers alongside M5.1.
* `scripts/render_preview.py`           — optional CLI wrapper for offline generation.
* `tests/test_preview_renderer.py`      — unit tests.
* Reuse `tests/fixtures/chat_with_audio/messages.jsonl` + small additional goldens.

---

### Preview line format

**File:** `src/writers/text_renderer.py`

Expose a pure formatter:

```python
def format_preview_line(msg: Message, max_chars: int = 120) -> str:
    """
    Return a single-line UTF-8 string (no trailing newline) summarizing a voice message.

    Format (example):
      2025-11-17 21:10:02 | idx=42 | sender=Alice | status=ok | provider=whisper_openai | text="Hello this is a vo..."
    """
```

Rules:

* Only intended for `msg.kind=="voice"`. If called with other kinds, either:

  * raise `ValueError`, **or**
  * document as undefined; tests should only exercise voice messages.

* Fields and order:

  ```text
  {ts_human} | idx={idx} | sender={sender} | status={status_and_reason} | provider={provider_or_dash} | text="{excerpt}"
  ```

  Where:

  * `ts_human` — same format as in M5.1 (`YYYY-MM-DD HH:MM:SS`).

  * `idx` — `msg.idx`.

  * `sender` — raw `msg.sender` with any `|` replaced by space to keep parsing simple.

  * `status_and_reason`:

    * If `msg.status_reason` is present → `"{status}/{status_reason}"`
      e.g. `"partial/asr_partial"`, `"failed/asr_failed"`.
    * Else → just `msg.status` (e.g. `"ok"`).

  * `provider_or_dash`:

    * `msg.derived["asr"].get("provider")` if present, else `"-"`.

  * `excerpt`:

    1. Base text:

       * If `msg.content_text` is non-empty → use it.
       * Else fall back to the same logic as M5.1 for voice placeholders (`[UNTRANSCRIBED VOICE NOTE]`, `[AUDIO TRANSCRIPTION FAILED]`, etc.).

    2. Normalize:

       * Replace all internal newlines with spaces.
       * Collapse runs of whitespace to a single space.
       * Strip leading/trailing spaces.

    3. Truncate:

       * If `len(excerpt) > max_chars`:

         * keep the first `max_chars` characters,
         * append a Unicode ellipsis `…` (U+2026).

    4. Escape:

       * Escape `"` as `\"` inside the quoted text.
       * Do **not** escape non-ASCII; keep Unicode as is.

* The returned string **must not** contain `\n` or `\r`.

---

### Batch writer (optional helper)

Optionally expose a convenience helper:

```python
from pathlib import Path

def write_transcript_preview(
    messages: list[Message],
    out_path: Path,
    max_chars: int = 120,
) -> None:
    """
    Overwrite preview_transcripts.txt with one line per voice message,
    sorted by idx ascending.
    """
```

* Filters `kind=="voice"` messages.
* Sorts by `idx`.
* Writes each line as `format_preview_line(msg, max_chars)` + `\n`.
* Uses `encoding="utf-8", newline="\n"`.

This helper can be used by scripts or by M6 (sequential mode). The concurrent pipeline in M6.1 may instead call `format_preview_line(...)` from each worker and append to the file in a thread-safe way.

---

### CLI: `scripts/render_preview.py` (optional but recommended)

* Arguments:

  * `--messages` (required): path to `messages.M3.jsonl`.
  * `--out` (required): path to `preview_transcripts.txt`.
  * `--max-chars` (optional): override default `120`.

* Behavior:

  1. Load messages from JSONL.
  2. Filter `kind=="voice"`.
  3. Call `write_transcript_preview(...)`.
  4. Print summary, e.g.:

     ```text
     Wrote transcript preview for 72 voice messages to preview_transcripts.txt
     ```

---

### Verification & Tests

**Fixtures**

* Reuse `tests/fixtures/chat_with_audio/messages.jsonl`.
* Add `tests/fixtures/chat_with_audio/preview_expected.txt` as a golden.

**Tests: `tests/test_preview_renderer.py`**

* `test_preview_line_basic_ok_status`
  For a simple voice message with `status="ok"` and short transcript, assert `format_preview_line` includes correct `ts_human`, `idx`, `sender`, `status=ok`, `provider`, and full text inside quotes without truncation.

* `test_preview_line_partial_and_failed_show_status_reason`
  For messages with `status="partial", status_reason="asr_partial"` and `status="failed", status_reason="asr_failed"`, assert the `status` field shows `"partial/asr_partial"` and `"failed/asr_failed"` respectively.

* `test_preview_line_truncation_and_escaping`
  For a long transcript (> `max_chars`) containing quotes and newlines, assert:

  * internal newlines are replaced by spaces,
  * text is truncated and ends with `…`,
  * internal `"` are escaped as `\"`,
  * no `\n` appears in the returned string.

* `test_write_transcript_preview_orders_by_idx_and_overwrites`
  Using a small synthetic list of `Message` objects with mixed ordering and kinds:

  * Confirm that file contains only `kind=="voice"` messages in ascending `idx`.
  * Confirm repeated calls overwrite the file deterministically.

---

### Acceptance Criteria (M5.2)

* `format_preview_line` produces a **single-line, parseable** summary for each voice message, with:

  * consistent field order,
  * clear status and provider fields,
  * reasonably short, truncated excerpts.

* `write_transcript_preview` creates a deterministic `preview_transcripts.txt` that:

  * is stable across runs,
  * can be tailed by the UI to show progress,
  * passes all `test_preview_renderer.py` tests.

* Optional CLI `render_preview.py` runs successfully on the `chat_with_audio` fixture and matches the golden preview file.

---

## M5.3 — Markdown Renderer (`chat_with_audio.md`) — Skeleton

**Objective**
Provide a richer, structured **Markdown** view of the conversation suitable for human reading and later MD→PDF conversion (M5.4, deferred).

**Note:** M5.3 is a **skeleton spec**. It defines the contract and surface area; detailed implementation and golden fixtures can be filled in when you’re ready to build MD→PDF.

**Code surface (expected files)**

* `src/writers/markdown_renderer.py`   — Markdown renderer for `Message[]`.
* `scripts/render_md.py`               — CLI wrapper.
* `tests/test_markdown_renderer.py`    — initial tests & golden snapshots.
* `tests/fixtures/chat_with_audio_md/` — small fixture & expected `.md`.

---

### High-level behavior

1. **Grouping by day**

   * Group messages by **calendar date** derived from `msg.ts` (same TZ semantics as M1).
   * For each date in order, emit a heading:

     ```md
     ## 2025-11-17
     ```

2. **Per-message format**

   Within each date section, render messages in `idx` order. For now, a simple skeleton:

   * **Text messages**:

     ```md
     - 21:10:02 **Alice:** Hello, this is a message
     ```

   * **Voice messages** (with ASR):

     ```md
     - 21:10:05 **Alice (voice):**
       > This is the transcribed text of the voice note...
     ```

     * If `status` is not `"ok"` (e.g. partial/failed), add a small badge:

       ```md
       > ⚠️ status=partial (reason=asr_partial)
       ```

   * **Images / Videos / Documents**:

     ```md
     - 21:11:00 **Bob:** [IMAGE: IMG-20251117-WA0001.jpg]
     ```

     (Same placeholder logic as M5.1; `caption` may be rendered on the next indented line.)

   * **System messages**:

     ```md
     - 21:12:00 **SYSTEM:** Alice created group "Family"
     ```

     * Optionally hidden with a `--hide-system` flag similar to M5.1.

3. **Multiline & formatting**

   * Use standard Markdown conventions:

     * Paragraphs in `content_text` become paragraphs following the bullet.
     * Voice transcripts are rendered as **blockquotes** (`>` prefixed lines).
     * Keep Markdown control characters minimal; escape where necessary.

4. **Determinism**

   * Same determinism guarantees as M5.1:

     * deterministic ordering,
     * consistent headings & time format,
     * UTF-8 with `\n` newlines,
     * stable placeholders and badges.

---

### CLI: `scripts/render_md.py` (skeleton)

* Arguments:

  * `--messages` (required): path to `messages.M3.jsonl`.
  * `--out` (required): path to `chat_with_audio.md`.
  * `--hide-system` (optional): hide system messages.

* Behavior:

  1. Load `Message[]`, sort by `idx`.
  2. Call `render_messages_to_markdown(messages, out_path, options)` (API to be finalized).
  3. Print basic summary: number of dates, messages, voice notes, etc.

---

### Verification & Tests (initial skeleton)

* `tests/fixtures/chat_with_audio_md/`:

  * Minimal `messages.jsonl` fixture (can share with M5.1).
  * `expected.md` — small golden file showing:

    * at least 2 dates,
    * text, voice, image, system examples.

* `tests/test_markdown_renderer.py` (initial tests):

  * `test_markdown_renderer_basic_structure` — headings per date, bullets per message, basic voice/image placeholders.
  * `test_markdown_renderer_voice_blockquote_and_status_badge` — ensure voice transcripts are blockquoted and partial/failed statuses show a warning badge.
  * `test_markdown_renderer_hide_system_flag` — system messages omitted when flag is set.

**Acceptance (M5.3 skeleton)**

* `render_md.py` runs successfully on the small fixture.
* `chat_with_audio.md` is deterministic and passes the initial snapshot tests.
* Detailed styling (fonts, MD→PDF specifics) is explicitly deferred to **M5.4** and does not block completion of M5.3.

---

> **Summary:**
> M5 now has:
>
> * A robust, configurable **text renderer** (`chat_with_audio.txt`) with explicit timestamp, newline, and status semantics.
> * A reusable **transcript preview** formatter (`preview_transcripts.txt`) for UI and tooling.
> * A **Markdown renderer skeleton** (`chat_with_audio.md`) that defines the structure needed for future MD→PDF work.


# M6 Upstream Contracts (Prerequisites for Orchestrator/UI)

**Purpose**
Before implementing M6 (pipeline runner, UI, concurrency), upstream steps (M1–M3 + M5.1) must satisfy a minimal set of contracts. These contracts are stricter than “tests are green” and are what the M6 runner and UI rely on.

M6 assumes:

### M6C — Contract Hardening Tasks (pre-M6)

> Hardening items to complete before building the M6 runner/UI.

**M6C.1 — Standardized Outputs per Run**

* Emit `messages.M1.jsonl`, `messages.M2.jsonl`, `messages.M3.jsonl`, `chat_with_audio.txt`, optional `preview_transcripts.txt`, `run_manifest.json`, `metrics.json` into `run_dir`.
* Missing `preview_transcripts.txt` is treated as “no preview yet” (empty), not an error.
* Provide deterministic helper/emitter functions to write these files.

**M6C.2 — Schema & Enum Invariants**

* Validate JSONL writers serialize `Message` exactly (contiguous idx, stable ISO ts, enums constrained to schema).
* Add a pre-flight schema check step for runner/UI; fail fast on drift.

**M6C.3 — Stage Contract Audit**

* M1: caption tails are `status="skipped", status_reason="merged_into_previous_media"`.
* M2: filename fast path sets `media_filename` when file exists; unresolved/ambiguous map to proper `status_reason`.
* M3: status/status_reason per global enum; bad audio must not crash the run.

**M6C.4 — Manifest & Metrics Stubs**

* Define `run_manifest.json` shape (e.g., in `src/pipeline/manifest.py`) capturing inputs/outputs/counts/timestamps.
* Define `metrics.json` summary (counts, cost, durations); add a minimal writer invoked after pipeline steps.

**M6C.5 — Contract Runner/CLI**

* Add a thin runner/CLI to orchestrate M1→M3→M5.1/M5.2 and write all contract files to `run_dir` deterministically (UTF-8, LF).

---

### 1. Required Files per Run

For each pipeline run, `run_dir` must contain:

* `messages.M1.jsonl` — M1 output (`Message[]`).
* `messages.M2.jsonl` — M2 output (`Message[]` with media annotations).
* `messages.M3.jsonl` — M3 output (`Message[]` with ASR for voice notes).
* `chat_with_audio.txt` — M5.1 text renderer output.
* `run_manifest.json` — `RunManifest` as defined in `src/pipeline/manifest.py`.
* `metrics.json` — per-run metrics summary (counts, cost, durations).
* Optionally `preview_transcripts.txt` — transcript preview lines for voice notes.

The M6 UI must treat missing `preview_transcripts.txt` as “no preview yet” (empty list), not as an error.

---

### 2. Message Schema Invariants (All Stages)

All JSONL files (`messages.M1/M2/M3.jsonl`) must serialize `schema.message.Message` exactly:

* Required top-level fields:

  * `idx: int` — unique, 0..N-1 without gaps per file.
  * `ts: str` — ISO 8601 `YYYY-MM-DDTHH:MM:SS` (no timezone suffix).
  * `sender: str`
  * `kind: Kind` where `Kind ∈ {"text","voice","image","video","document","sticker","system","unknown"}`
  * `content_text: str` (may be empty, but must exist)
  * `raw_line: str`
  * `raw_block: str`
  * `media_hint: str | null`
  * `media_filename: str | null`
  * `caption: str | null`
  * `derived: dict` (default `{}`)
  * `status: Status` where `Status ∈ {"ok","partial","failed","skipped"}`
  * `partial: bool`
  * `status_reason: StatusReason | null` where `StatusReason` is one of the global enum strings.
  * `errors: list[str]`

* Invariants:

  * `idx` values are contiguous and strictly increasing when sorted.
  * `ts` is parseable by `parse_ts` and stable across stages (M1→M3 must not rewrite timestamps).
  * `kind`, `status`, and `status_reason` **never** use values outside the enums defined in `src/schema/message.py`.
  * Unknown situations must use existing enums (`kind="unknown"` or `status_reason="unresolved_media"`), not new strings.

If schema changes are required, they are done in `src/schema/message.py` and accompanied by a schema version bump and test updates.

---

### 3. Stage-Specific Contracts

#### M1 — Parser

* `messages.M1.jsonl` contains one `Message` per logical WhatsApp message.
* `idx` is assigned in parse order and stable across runs.
* All timestamps are normalized to ISO strings via M1’s date utilities.
* Caption-merge tails are marked:

  * Merged caption messages have `status="skipped", status_reason="merged_into_previous_media"`.
  * The corresponding media message carries the caption in `caption`.

M1 heuristics (locale detection, system lines, edge-case header parsing) may be incomplete, but **must not** crash and must still produce a well-formed `Message[]`.

#### M2 — Media Resolver

* `messages.M2.jsonl` is the same shape as M1 but with media fields possibly updated:

  * For messages with concrete WhatsApp filenames (`IMG-... (file attached)`, `PTT-...`, etc.), resolver **must** set `media_filename` to the actual file path if that file exists under `root`.
  * For placeholder-only messages (`<Media omitted>`, etc.) it is acceptable for `media_filename` to remain `None`.

* Status semantics:

  * Resolved media: `status="ok"`, `status_reason=None`.
  * Unresolved media: `status="ok"`, `status_reason="unresolved_media"`.
  * Ambiguous media: `status="ok"`, `status_reason="ambiguous_media"` and a row in `exceptions.csv`.

Advanced ladder heuristics (hints, WA#### range, mtime scoring, clock drift, hashing) may be partial; worst-case behavior is “unresolved/ambiguous but never crash.”

#### M3 — Audio Pipeline

* `messages.M3.jsonl` is derived from `messages.M2.jsonl` with ASR annotations for `kind="voice"` messages.

For each `Message` with `kind="voice"`:

* If audio file is supported and ASR fully succeeds:

  * `status="ok"`, `status_reason=None` (or a non-error reason if appropriate).
  * `content_text` contains the transcript if it was previously empty.
  * `derived["asr"]` exists and includes at least:

    ```json
    {
      "pipeline_version": "…",
      "provider": "whisper_openai" | "whisper_local" | "google_stt",
      "model": "…",
      "total_duration_seconds": <float>,
      "chunks": [ ... ]
    }
    ```

* If ASR partially succeeds:

  * `status="partial"`, `status_reason="asr_partial"`, `partial=true`.
  * `content_text` contains the concatenated successful chunk texts.
  * `derived["asr"]["error_summary"]` summarizes failure counts.

* If all chunks fail or the format is unsupported:

  * `status="failed"`, with `status_reason ∈ {"ffmpeg_failed","timeout_ffmpeg","asr_failed","timeout_asr","audio_unsupported_format"}`.
  * If `content_text` is empty, it must be set to a human-friendly placeholder, e.g. `[AUDIO TRANSCRIPTION FAILED]`.
  * `derived["asr"]["error_summary"]` present.

Non-voice messages must **not** be modified in ways that violate M1/M2 invariants (idx, ts, sender, kind, etc.).

---

### 4. Renderer (M5.1) Contracts

M5.1 text renderer:

* Accepts `Message[]` loaded from `messages.M3.jsonl`.
* Produces `chat_with_audio.txt` with:

  * All non-merged messages in ascending `idx` order.
  * `YYYY-MM-DD HH:MM:SS - Sender: body` on the first line per message.
  * `\n` newlines only.
  * Placeholders for any remaining untranscribed/failed media exactly as specified in the M5.1 section.

The renderer must be **pure** (no mutations of `Message[]`) and deterministic.

---

### 5. Debugging & Failure Behavior

* If any step (M1–M3–M5) fails to produce its output, `run_manifest.json` must:

  * Mark that step `status="failed"`.
  * Include a short error summary in `summary["error"]`.

* M6 runner and UI:

  * Use `run_manifest.json` and `metrics.json` to present failures.
  * Never crash due to missing preview files; they treat them as “no data yet”.

With these contracts respected, M6 can assume that:

* Sequential and concurrent runs produce deterministic outputs.
* Failures are visible and debug-friendly.
* The UI can safely render run status and transcript previews without knowing the internal details of M1–M3.

---

# M6 — Orchestrator, Concurrency, Resume, Metrics & UI

**Milestone Goal**
Provide a **single, resumable pipeline** and a **small local UI** to run M1–M3 + M5 end-to-end for a given WhatsApp export, with:

* **Concurrency** for expensive stages (audio transcription).
* **Resume & idempotence** across runs (re-use caches & intermediate JSONL).
* **Metrics & cost summaries** per run.
* **Exceptions handled gracefully** (bad files/messages never crash the pipeline).
* A **double-clickable launcher** on Windows that opens a Streamlit UI in the browser.

M6 does **not** depend on M4 (image/PDF enrichment). If M4 is added later, it should plug into the same orchestration structure as an additional pipeline step.

---

## Code Surface (expected files)

Core pipeline:

* `src/pipeline/config.py`      — `PipelineConfig`, CLI helpers, path resolution.
* `src/pipeline/manifest.py`    — `RunManifest` structure, read/write, helpers.
* `src/pipeline/metrics.py`     — `RunMetrics` aggregation helpers.
* `src/pipeline/status.py`      — high-level status helpers for UI (list runs, load summaries).
* `src/pipeline/runner.py`      — `run_pipeline(cfg)`, orchestration + concurrency + metrics wiring.
* `src/utils/asr.py`            — provider-agnostic ASR client + provider backends (M6.2, M6.5).
* `src/audio_transcriber.py`    — glue between M3 and ASR abstraction.
* `scripts/run_pipeline.py`     — one-shot pipeline runner (no UI).
* `scripts/ui_app.py`           — Streamlit UI app (localhost web UI).
* `scripts/WhatsAppTranscriberUI.bat` — Windows launcher (double-click → UI + logs).

Config & docs:

* `config/asr.yaml`             — ASR provider/model defaults & per-provider settings.
* `README_M6_PIPELINE.md`       — pipeline runner usage, concurrency/resume semantics.
* `README_M6_UI.md`             — UI usage, launcher instructions, provider notes.
* `README_M5_RENDERING.md`      — rendering/RTL notes (see M6.8).

Tests & fixtures (module-level):

* Pipeline core:

  * `tests/test_pipeline_config.py`
  * `tests/test_pipeline_manifest.py`
  * `tests/test_pipeline_runner_sequential.py`
  * `tests/test_pipeline_runner_concurrent.py`
  * `tests/test_pipeline_resume.py`
  * `tests/test_pipeline_metrics.py`
  * `tests/test_run_pipeline_cli_smoke.py`
* ASR & audio:

  * `tests/test_asr_client_whisper.py`
  * `tests/test_asr_client_google.py`
  * `tests/test_asr_provider_error_mapping.py`
  * `tests/test_asr_error_mapping_realistic.py`
  * `tests/test_audio_chunking_hardening.py`
  * `tests/test_derived_asr_provider_model.py`
* Manifest & metrics schema:

  * `tests/test_manifest_schema_basic.py`
  * `tests/test_metrics_schema_basic.py`
  * `tests/test_manifest_and_metrics_golden.py`
* UI & status:

  * `tests/test_status_helpers.py`
  * `tests/test_ui_app_imports_and_layout.py`
* Rendering (RTL/Arabic):

  * `tests/test_text_renderer_arabic_content.py`
  * `tests/test_markdown_renderer_arabic_content.py`
  * (optional) `tests/test_renderers_utf8_and_newlines.py`
* Fixtures:

  * `tests/fixtures/pipeline_small_chat/` (tiny end-to-end chat fixture)

> M6 changes **must not** break the contracts/tests for M1–M3 or M5.1. Any new behavior lives behind new functions/CLIs and config flags.

---

## M6.1 — Pipeline Runner & `run_manifest.json` (Orchestration, Concurrency, Resume, Metrics)

**Objective**
Create a single **pipeline runner** that:

1. Runs M1→M2→M3→M5.1 in a deterministic sequence.
2. Exposes knobs for concurrency (`max_workers_audio`), ASR provider/model, sampling, etc.
3. Writes and updates `run_manifest.json` and `metrics.json` as a first-class contract.
4. Supports **resume** by reusing intermediate outputs and ASR caches.

**Files**

* `src/pipeline/config.py`
* `src/pipeline/manifest.py`
* `src/pipeline/metrics.py`
* `src/pipeline/runner.py`
* `scripts/run_pipeline.py`
* Tests:

  * `tests/test_pipeline_config.py`
  * `tests/test_pipeline_manifest.py`
  * `tests/test_pipeline_runner_sequential.py`
  * `tests/test_pipeline_runner_concurrent.py`
  * `tests/test_pipeline_resume.py`
  * `tests/test_pipeline_metrics.py`
  * `tests/test_run_pipeline_cli_smoke.py`
  * Fixture: `tests/fixtures/pipeline_small_chat/`

### Deliverables

1. **`PipelineConfig` dataclass & CLI**

   * Holds:

     * `root`, `run_id`, `run_dir`
     * `chat_file`
     * `max_workers_audio`
     * `asr_provider`, `asr_model`, `asr_language`
     * `sample_limit` / `sample_every` (optional)
     * `force_rerun` or `resume` flag
   * `scripts/run_pipeline.py` parses CLI args and instantiates `PipelineConfig`.

2. **`RunManifest` orchestration structure**

   * `RunManifest` contains:

     * `schema_version`
     * `run_id`, `root`, `chat_file`
     * `start_time`, `end_time`
     * `steps: dict[StepName, StepProgress]` with:

       * `status ∈ {"pending","running","ok","failed","skipped"}`
       * `total`, `done`
     * `summary` with at least `messages_total`, `voice_total`, `error`.
   * Helper functions:

     * `init_manifest(cfg)` — create and write initial manifest with all steps `pending`.
     * `update_step(manifest, step_name, **fields)` — update status/progress and re-write.

3. **Runner orchestration & resume**

   * `run_pipeline(cfg)`:

     1. Validates upstream contracts (presence of required files for prior runs).
     2. Creates or loads `run_manifest.json`.
     3. Steps:

        * `M1_parse` — call existing M1 script/module, write `messages.M1.jsonl`.
        * `M2_media` — call M2 resolver, write `messages.M2.jsonl` + `exceptions.csv`.
        * `M3_audio` — call `AudioTranscriber` on voice messages from M2 (respect concurrency).
        * `M5_text` — call text renderer, write `chat_with_audio.txt` and optional `preview_transcripts.txt`.
     4. For each step:

        * Skips step if `status=="ok"` and outputs exist **and** resume is enabled.
        * Otherwise runs step, updates manifest + metrics.

   * Resume semantics:

     * For M3, `AudioTranscriber` must skip messages whose `derived["asr"]` already matches current pipeline version/provider/model.

4. **Metrics aggregation**

   * `RunMetrics` collects:

     * message/voice counts
     * per-status counts for voice (`ok/partial/failed`)
     * media resolved/unresolved/ambiguous
     * `audio_seconds_total`
     * `asr_cost_total_usd`
     * `wall_clock_seconds`
   * `run_pipeline` updates metrics incrementally and writes `metrics.json` at end.

### Subtasks

1. Implement `PipelineConfig` + CLI parsing.
2. Implement `RunManifest` and helpers, including JSON (de)serialization.
3. Implement `RunMetrics` and helpers.
4. Implement `run_pipeline(cfg)` orchestration for sequential M1→M2→M3→M5.1.
5. Implement concurrency in M3 (thread/process pool) controlled by `max_workers_audio`.
6. Implement resume logic (skip completed steps, skip already-ASR’d messages).
7. Wire metrics + manifest updates.

### Verification & Tests

* `test_pipeline_config_root_paths`
  Config resolves `root`, `run_dir`, and `chat_file` correctly (no trailing slashes, deterministic run IDs).
* `test_pipeline_manifest_initial_structure`
  `init_manifest` populates all steps as `pending` with `total=0`, `done=0`.
* `test_pipeline_runner_sequential_happy_path`
  With `max_workers_audio=1`, small fixture run produces all expected outputs and step statuses are `ok`.
* `test_pipeline_runner_concurrent_matches_sequential`
  Running with `max_workers_audio=1` vs `4` yields byte-for-byte identical `messages.M3.jsonl` and `chat_with_audio.txt`.
* `test_pipeline_resume_skips_completed_steps`
  Re-running with same config skips steps already marked `ok` and reuses `messages.M3.jsonl`.
* `test_pipeline_metrics_populated`
  After a successful run, `metrics.json` has non-zero counts consistent with fixture.
* `test_run_pipeline_cli_smoke`
  CLI wrapper runs end-to-end on fixture without crashing.

### Acceptance (M6.1)

* Single CLI command:

  ```bash
  python scripts/run_pipeline.py --root tests/fixtures/pipeline_small_chat
  ```

  produces a run directory with valid manifest, metrics, and deterministic M3/M5 outputs.
* Increasing `max_workers_audio` from 1 to N only affects **performance**, not outputs.
* Killing the process mid-M3 and re-running with same config reuses already-transcribed messages and completes successfully.

---

## M6.2 — ASR Provider Abstraction (Whisper vs Google)

**Objective**
Introduce a **provider-agnostic ASR client** so that M3 (audio pipeline) and M6 (runner/UI) can choose between:

* Whisper (OpenAI API or local),
* Google Speech-to-Text (cloud),

without changing pipeline or UI code. Ensure provider/model info is reflected in `derived["asr"]`, `metrics.json`, and `RunManifest`.

**Files**

* `src/utils/asr.py`
* `src/audio_transcriber.py`
* `src/pipeline/config.py`   (add `asr_provider`, `asr_model` defaults)
* `src/pipeline/metrics.py`
* `config/asr.yaml`
* Tests:

  * `tests/test_asr_client_whisper.py`
  * `tests/test_asr_client_google.py`
  * `tests/test_derived_asr_provider_model.py`
  * `tests/test_pipeline_metrics.py`

### Deliverables

1. **Provider-agnostic `AsrClient`**

   * Interface:

     ```python
     class AsrClient:
         def __init__(self, provider_name: str, model: str | None, language: str | Literal["auto"]):
             ...

         def transcribe_chunk(self, wav_path: str, start_sec: float, end_sec: float) -> AsrChunkResult:
             ...
     ```

   * Uses provider implementations (whisper, google, etc.) but exposes a single normalized `AsrChunkResult`.

2. **Provider interface & concrete backends**

   * Abstract interface:

     ```python
     class AsrProvider(Protocol):
         def transcribe_chunk(..., language_hint: str | Literal["auto"]) -> AsrChunkResult: ...
     ```

   * Backends:

     * `WhisperBackend` (OpenAI, local stub)
     * `GoogleSttBackend`
     * `NoopBackend` (for tests/dry runs)

3. **Config wiring**

   * `config/asr.yaml` defines default provider/model per environment.
   * `PipelineConfig` exposes `asr_provider`, `asr_model`.
   * `run_pipeline` passes provider/model into `AudioTranscriber` → `AsrClient`.

4. **Derived metadata & metrics**

   * `derived["asr"]` for each voice message contains:

     * `provider`
     * `model`
     * `pipeline_version`
     * `total_duration_seconds`
   * `metrics.json` includes:

     * `asr_provider`, `asr_model`
     * provider-specific cost totals, if available.

### Subtasks

1. Define `AsrProvider` protocol + `AsrChunkResult`.
2. Implement `AsrClient` that chooses provider based on config.
3. Implement Whisper + Google providers with stub methods (real integration in M6.5).
4. Update `AudioTranscriber` to depend on `AsrClient`.
5. Wire provider/model into `derived["asr"]` and `metrics.json`.

### Verification & Tests

* `test_asr_client_whisper`
  With a mocked Whisper backend, ensure `AsrClient` calls the right provider and produces normalized results.
* `test_asr_client_google`
  Same for Google backend.
* `test_derived_asr_provider_model`
  After a run, each voice message’s `derived["asr"]` has correct `provider` and `model`, and metrics reflect them.
* `test_pipeline_metrics_provider_counts` (inside `test_pipeline_metrics.py`)
  Aggregates counts per `asr_provider` and per `status`.

### Acceptance (M6.2)

* `AsrClient` is the **only** ASR entrypoint used by `AudioTranscriber`.
* Changing provider/model in config changes `derived["asr"]` and `metrics.json` but not overall pipeline shape.
* Tests and metrics do not depend on live network calls (all providers mocked).

---

## M6.3 — Streamlit UI (Status Panel & Transcript Preview)

**Objective**
Provide a minimal Streamlit UI to:

* Configure and launch runs (export folder, chat file, ASR provider, sample mode).
* List existing runs and show per-run status.
* Preview transcripts of voice notes from `preview_transcripts.txt`.

**Files**

* `scripts/ui_app.py`
* `src/pipeline/status.py`
* `README_M6_UI.md`
* Tests:

  * `tests/test_status_helpers.py`
  * `tests/test_ui_app_imports_and_layout.py`

### Deliverables

1. **Status helper functions**

   In `src/pipeline/status.py`:

   * `list_runs(root: str) -> list[RunSummary]`

     * Finds `run_*` directories under `root`.
     * Loads `run_manifest.json` and `metrics.json` if present.
     * Returns a small summary (run_id, chat_file, status, message counts, started/finished timestamps).

   * `load_run_summary(run_dir: str) -> RunSummary`

   * `load_transcript_preview(run_dir: str) -> list[str]`

     * Reads `preview_transcripts.txt` if present; returns empty list otherwise.

2. **Streamlit layout**

   `scripts/ui_app.py`:

   * Left panel — **Run Configuration**

     * Export folder input.
     * “Scan” button → populate chat files dropdown.
     * Chat file dropdown.
     * ASR provider dropdown (`whisper_openai`, `whisper_local`, `google_stt`).
     * Sample mode checkbox / numeric input (e.g. “limit to first N messages”).
     * **Run** button that calls `run_pipeline(cfg)`.

   * Right panel — **Runs & Details**

     * Table of existing runs (from `list_runs`).
     * Selecting a run shows:

       * Run overview (status, provider, duration, cost, counts).
       * Step-wise status table from `RunManifest`.
       * A transcript preview area showing lines from `preview_transcripts.txt`.

3. **UI behavior**

   * UI must not crash if manifests/metrics/preview are missing or invalid:

     * Display a warning banner instead.
   * UI must never mutate `run_manifest.json` or `metrics.json` directly; only the runner writes them.

### Subtasks

1. Implement `RunSummary` dataclass and helper functions.
2. Implement Streamlit app layout (config panel + runs panel + preview).
3. Wire **Run** button to launch `run_pipeline` in a background thread/process.
4. Add minimal logging to console (so launcher shows logs).

### Verification & Tests

* `test_status_helpers_list_runs`
  With a small fixture root, returns the expected runs with correct summary fields.
* `test_status_helpers_load_run_summary`
  Loads a single run’s manifest/metrics and populates summary without crashing when fields are missing.
* `test_status_helpers_transcript_preview_parses_file`
  Reads a sample `preview_transcripts.txt` and returns correct lines (UTF-8).
* `test_ui_app_imports_and_layout`
  Importing `scripts/ui_app.py` constructs the Streamlit layout without executing `run_pipeline` or hitting the filesystem hard.

### Acceptance (M6.3)

* Running `streamlit run scripts/ui_app.py`:

  * Shows configuration controls, runs table, and transcript preview.
  * Can launch at least one pipeline run end-to-end (small fixture) and update UI status.

---

## M6.4 — Windows Launcher & Packaging

**Objective**
Make it **one double-click** on Windows to open the UI, with logs visible and correct working directory.

**Files**

* `scripts/WhatsAppTranscriberUI.bat`
* (Optional) `scripts/launcher.py`
* `README_M6_UI.md` (launcher section)
* Tests:

  * `tests/test_launcher_imports.py` (if `launcher.py` exists)

### Deliverables

1. **Batch launcher**

   * `WhatsAppTranscriberUI.bat`:

     * Activates the correct virtualenv or uses `python` on PATH.

     * `cd` to repo root.

     * Runs:

       ```bat
       python -m streamlit run scripts/ui_app.py
       ```

     * Keeps console open so logs remain visible.

2. **Optional Python helper**

   * `scripts/launcher.py` (optional) with helpers like `get_repo_root()`:

     * Resolves repo root robustly regardless of how the batch file is invoked.
   * Batch script can call:

     ```bat
     python scripts/launcher.py
     ```

     which then starts Streamlit.

3. **Docs**

   * README section showing:

     * How to run the UI via CLI and via double-click.
     * Where logs go and how to debug if Streamlit fails to start.

### Subtasks

1. Implement batch launcher for Windows.
2. (Optional) Implement `launcher.py` for path handling.
3. Document usage and troubleshooting.

### Verification & Tests

* If `launcher.py` exists:

  * `test_launcher_imports`
    Import and call a small helper (e.g., `get_repo_root()`) to ensure no path logic breaks.

**Acceptance (M6.4)**

* On your machine, you can **double-click one file** and end up at the Streamlit UI without touching CLI.
* Console logs remain visible for debugging, matching your mental model: "I double-click, browser opens, I see the steps and output."

### M6.4.1 — Credential Storage & UI Improvements (Completed)

**Completed:** 2025-01-20

**Problem:**
- Users couldn't save API keys (OpenAI, Google) in the UI - both failed silently
- Root causes:
  1. Old WSL Streamlit process running (started Nov 19) conflicted with Windows batch file
  2. Generic error messages ("Failed to save", "File not found") provided no debugging info
  3. Path normalization missing (quotes, spaces, env vars not handled)
  4. No indication which Python was running the UI

**Solution:**

1. **Enhanced `src/utils/credentials.py`:**
   - Added `_normalize_path()` helper (strips quotes, expands env vars/~)
   - Changed `save_credential()` to raise detailed exceptions instead of generic bool
   - `save_google_credentials_path()` now validates file exists BEFORE keyring save
   - Returns normalized path so UI can show exactly what Python checked

2. **Improved `scripts/ui_app.py`:**
   - Shows Python executable at top of API Keys section (verify correct Python)
   - Specific exception handling with detailed messages:
     - `ValueError` → "Invalid input: ..."
     - `FileNotFoundError` → Shows both normalized path AND original input
     - `RuntimeError` → Shows actual keyring error
   - Success messages show normalized paths saved

3. **Enhanced `scripts/launcher.py`:**
   - Added `--server.runOnSave=true` flag so code changes auto-reload
   - Added `--server.fileWatcherType=auto` for filesystem watching
   - Prevents stale code caching issues

4. **Process cleanup:**
   - Documented zombie process debugging via Chrome DevTools MCP
   - Proper cleanup of conflicting Streamlit instances

**Files Changed (3):**
- `src/utils/credentials.py` (~25 LOC)
- `scripts/ui_app.py` (~35 LOC)
- `scripts/launcher.py` (~2 LOC)

**Result:**
- Users can now save credentials and see exactly why if it fails
- Code changes auto-reload without restarting batch file
- No more zombie Streamlit processes conflicting with launcher

---

## M6.5 — ASR Provider Integration & Error Mapping Hardening

**Objective**
Build on **M6.2** to hook `AsrClient` up to *real* provider backends (Whisper, Google), with robust env/config handling, language hints (incl. Arabic), and deterministic error → `StatusReason` mapping used by M3 + M6 metrics/UI.

**Files**

* `src/utils/asr.py`
* `src/audio_transcriber.py`
* `src/pipeline/config.py`
* `config/asr.yaml`
* `README.md` or `README_M6_PIPELINE.md`
* Tests:

  * `tests/test_asr_client_whisper.py`

    * `test_asr_client_whisper_basic`
  * `tests/test_asr_client_google.py`

    * `test_asr_client_google_basic`
  * `tests/test_asr_provider_error_mapping.py`
  * `tests/test_asr_language_hints_plumbing.py`

### Deliverables

1. **Config + env validation**

   * Extend `config/asr.yaml` with provider-specific env keys and language knobs, e.g.:

     ```yaml
     default_provider: whisper_openai
     providers:
       whisper_openai:
         model: whisper-1
         timeout_seconds: 30
         max_retries: 2
         billing: "openai_whisper_v1"
         env_key: "OPENAI_API_KEY"
         default_language: "auto"
       google_stt:
         model: "google-default"
         timeout_seconds: 30
         max_retries: 2
         billing: "google_stt_standard"
         env_key: "GOOGLE_APPLICATION_CREDENTIALS"
         default_language: "auto"
     ```

   * Add helper:

     ```python
     def resolve_asr_config(provider_name: str) -> AsrProviderConfig: ...
     ```

     which validates required env var is present and raises a clear `ConfigError` if not.

2. **Language hints plumbed end-to-end**

   * Extend `PipelineConfig` / `AudioConfig` with `asr_language: str | Literal["auto"] = "auto"`.
   * CLI flag `--asr-language` flows into `AsrClient` and provider backends.
   * `derived["asr"]` always includes:

     ```python
     {
       "provider": "...",
       "model": "...",
       "language_hint": "auto|ar|en|...",
       "detected_language": "...",  # optional, if provider returns it
     }
     ```

3. **Provider backends wired to real APIs (behind mocks in tests)**

   * `WhisperBackend`:

     * Uses `OPENAI_API_KEY`.
     * Implements `transcribe_chunk(...)` with timeout + retries from config.
     * Normalizes responses to `AsrChunkResult`.

   * `GoogleSttBackend`:

     * Uses `GOOGLE_APPLICATION_CREDENTIALS`.
     * Reads audio bytes and calls Google STT client.
     * Same `transcribe_chunk(...)` signature and normalization.

   * **No live HTTP** in tests — everything mocked at backend level.

4. **Deterministic error → `StatusReason` mapping**

   * Introduce:

     ```python
     AsrErrorKind = Literal["timeout", "auth", "quota", "client", "server", "unknown"]
     ```

   * Helper:

     ```python
     def map_asr_error_to_status_reason(kind: AsrErrorKind) -> StatusReason:
         # timeout -> "timeout_asr"
         # others -> "asr_failed"
     ```

   * `AudioTranscriber` uses this helper so:

     * Timeouts → `status_reason="timeout_asr"`.
     * Other fatal errors → `status_reason="asr_failed"`.

   * `derived["asr"]["error_summary"]` contains:

     ```python
     {
       "chunks_ok": int,
       "chunks_error": int,
       "last_error_kind": "timeout|auth|quota|client|server|unknown",
       "last_error_message": "short provider-specific message",
     }
     ```

5. **Docs**

   * README section explaining:

     * How to configure `config/asr.yaml`.
     * Required env vars per provider.
     * How `--asr-provider`, `--asr-model`, `--asr-language` interact.
     * How errors surface via `status_reason` and `error_summary`.

### Subtasks

1. Extend `config/asr.yaml` and add `resolve_asr_config(...)`.
2. Add `asr_language` to `PipelineConfig` / `AudioConfig`; plumb CLI → config → `AsrClient` → backends.
3. Implement real Whisper + Google backends.
4. Add `AsrErrorKind` + `map_asr_error_to_status_reason(...)`.
5. Update `AudioTranscriber` to use error mapping consistently.
6. Ensure `derived["asr"]` mentions provider/model/language_hint/error_summary.
7. Write tests + docs.

### Verification & Tests

* `test_asr_client_whisper_basic`
  With mocked Whisper backend:

  * `AsrClient` selects proper provider/model/language_hint.
  * Returned `AsrChunkResult` has correct metadata.
* `test_asr_client_google_basic`
  Same, for Google backend.
* `test_asr_provider_error_mapping`
  For each `AsrErrorKind`, assert correct `StatusReason` and ensure `AudioTranscriber` maps to expected `status`/`status_reason`.
* `test_asr_language_hints_plumbing`
  With `--asr-language=ar`, confirm:

  * Backend receives `"ar"`.
  * `derived["asr"]["language_hint"] == "ar"`.

### Acceptance (M6.5)

* Changing `--asr-provider`, `--asr-model`, or `--asr-language`:

  * Affects `derived["asr"]` and `metrics.json` exactly as expected.
* Missing env vars for a provider fail fast with a clear error.
* Timeouts vs other provider errors are visible via `status_reason` and `error_summary`.
* No tests make live API calls; everything is mocked.

---

## M6.6 — Audio Error Handling & Chunking Hardening

**Objective**
Close edge-cases where WAV parsing/chunking or ASR orchestration can silently misbehave (e.g. 0-length WAV, no chunks), and guarantee that every failure path produces a deterministic `status`, `status_reason`, and placeholder — never a crash or silent no-op.

**Files**

* `src/audio_transcriber.py`
* `src/utils/asr.py`
* Tests:

  * `tests/test_audio_chunking_hardening.py`

    * `test_chunking_failure_sets_failed_status`
    * `test_chunk_manifest_non_empty_for_valid_audio`
    * `test_asr_chunking_error_sets_error_summary`
  * `tests/test_asr_error_mapping_realistic.py`

### Deliverables

1. **Chunking invariants**

   * `_chunk_wav(wav_path, cfg)`:

     * For valid audio:

       * Returns a **non-empty** list of chunks with strictly increasing `start_sec` / `end_sec`.
     * For invalid/degenerate audio (0-length, unreadable WAV):

       * Raises a dedicated `ChunkingError` (or equivalent).

   * Invariant:

     > `AudioTranscriber.transcribe` must never proceed to ASR with an empty chunk list.

2. **Transcribe-level failure handling**

   * In `AudioTranscriber.transcribe(m)`:

     * If `_to_wav` fails → `status_reason ∈ {"ffmpeg_failed","timeout_ffmpeg"}` (existing behavior).

     * If `_chunk_wav` raises `ChunkingError`:

       * Set `status="failed"`, `status_reason ∈ {"asr_failed","audio_unsupported_format"}`.
       * If `content_text` empty, set placeholder, e.g. `[AUDIO TRANSCRIPTION FAILED (chunking)]`.
       * `derived["asr"]["error_summary"]` with `chunks_ok=0`, `chunks_error=0`, `last_error_kind="chunking"`.

     * If ASR is called but every chunk errors:

       * Already handled via M3.x logic; assert via tests in this milestone.

3. **Realistic ASR error scenarios**

   * Simulate via mocks:

     * Some chunks succeed, last chunk times out.
     * First chunk fails with provider `quota`/`auth` error.
     * Truncated WAV where provider returns “invalid audio”.

   * Ensure:

     * Mixed success/failure → `status="partial"`, `status_reason="asr_partial"`.
     * All fatal at ASR level → `status="failed"`, `status_reason` from M6.5 mapping.

4. **Logging / derived metadata**

   * Ensure `derived["asr"]` always contains:

     * `total_duration_seconds` (0 for chunking failures).
     * A `chunks` list (possibly empty) and `error_summary` for failures.

### Subtasks

1. Introduce `ChunkingError` and use inside `_chunk_wav`.
2. Harden `_chunk_wav` to:

   * Compute duration deterministically.
   * Raise `ChunkingError` for `total_seconds <= 0` or I/O issues.
3. Update `AudioTranscriber.transcribe`:

   * Catch `ChunkingError`, set failed status + placeholder + error_summary.
   * Guard against empty chunk lists.
4. Add realistic ASR error simulations in tests.

### Verification & Tests

* `test_chunking_failure_sets_failed_status`
  For a 0-length WAV fixture, `_chunk_wav` raises and `transcribe` sets `status="failed"` with correct `status_reason` and placeholder text.
* `test_chunk_manifest_non_empty_for_valid_audio`
  For normal audio, `_chunk_wav` returns a non-empty, ordered chunk list.
* `test_asr_error_mapping_realistic`
  Simulates:

  * Mixed chunk success + timeout → `partial/asr_partial`.
  * All chunks timeout → `failed/timeout_asr`.
* `test_asr_chunking_error_sets_error_summary`
  Chunking failures write meaningful `derived["asr"]["error_summary"]`.

### Acceptance (M6.6)

* No code path leaves a `kind="voice"` message in limbo:

  * Either ASR-annotated, or
  * Marked failed with clear `status_reason` and placeholder.
* Zero-length / truncated audio never crashes the pipeline or yields silent empty transcripts.
* New tests pass; no regressions in existing M3/M6 tests.

---

## M6.7 — Manifest & Metrics Schema (Run-Level)

**Objective**
Formalize the **run-level contract** for `run_manifest.json` and `metrics.json` so that M6 runner + UI (and future tools) can rely on a stable, versioned schema.

**Files**

* `src/pipeline/manifest.py`
* `src/pipeline/metrics.py`
* `schema/run_manifest.schema.json`
* `schema/metrics.schema.json`
* `README_M6_PIPELINE.md`
* Tests:

  * `tests/test_manifest_schema_basic.py`
  * `tests/test_metrics_schema_basic.py`
  * `tests/test_manifest_and_metrics_golden.py`

### Deliverables

1. **Typed models for manifest + metrics**

   * Refine `RunManifest` with:

     * `schema_version`
     * `run_id`, `root`, `chat_file`
     * `start_time`, `end_time`
     * `steps: dict[StepName, StepProgress]`
     * `summary` including:

       * `messages_total`
       * `voice_total`
       * `error: str | None`

   * `RunMetrics` with:

     * `schema_version`
     * `messages_total`
     * `voice_total`, `voice_ok`, `voice_partial`, `voice_failed`
     * `media_resolved`, `media_unresolved`, `media_ambiguous`
     * `asr_provider`, `asr_model`, `asr_language`
     * `audio_seconds_total`
     * `asr_cost_total_usd`
     * `wall_clock_seconds`

2. **JSON Schemas**

   * `schema/run_manifest.schema.json`
   * `schema/metrics.schema.json`

   Helpers:

   ```python
   def validate_manifest(data: dict) -> None: ...
   def validate_metrics(data: dict) -> None: ...
   ```

   used in tests (and optionally behind a debug flag in runner).

3. **Versioning policy**

   * `MANIFEST_SCHEMA_VERSION` and `METRICS_SCHEMA_VERSION` constants.
   * MAJOR/MINOR/PATCH rules similar to `Message.schema_version`.
   * Both `run_manifest.json` and `metrics.json` must include `schema_version`.

4. **Golden fixtures**

   * Under `tests/fixtures/pipeline_small_chat/`:

     * `expected_run_manifest.json`
     * `expected_metrics.json`
   * Snapshot tests compare actual to expected, ignoring volatile fields (e.g. timestamps) via normalization.

### Subtasks

1. Refine `RunManifest` and `RunMetrics` dataclasses + serializers.
2. Author JSON schemas.
3. Implement `validate_manifest` / `validate_metrics`.
4. Generate goldens from known fixture run.
5. Document schema & versioning rules.

### Verification & Tests

* `test_manifest_schema_basic`
  Validates `expected_run_manifest.json` against `run_manifest.schema.json`.
* `test_metrics_schema_basic`
  Validates `expected_metrics.json` against `metrics.schema.json`.
* `test_manifest_and_metrics_golden`
  Runs pipeline on fixture, normalizes volatile fields, and compares manifest/metrics to goldens.

### Acceptance (M6.7)

* All manifests/metrics written by `run_pipeline`:

  * Conform to their schemas.
  * Include `schema_version`.
* M6 UI only depends on documented fields; adding new optional fields is backwards compatible.
* Golden tests fail loudly on breaking changes unless schema version/goldens are deliberately updated.

---

## M6.8 — Rendering RTL/Arabic Friendliness

**Objective**
Improve **text** and **Markdown** renderers so mixed eArabic/English chats render predictably in LTR environments while keeping determinism. Add optional bidi controls for advanced use, but default behavior must remain backward-compatible.

**Files**

* `src/writers/text_renderer.py`
* `src/writers/markdown_renderer.py`
* `README_M5_RENDERING.md`
* Tests:

  * `tests/test_text_renderer_arabic_content.py`

    * `test_text_renderer_arabic_content_preserved`
    * `test_text_renderer_bidi_marks_mode`
  * `tests/test_markdown_renderer_arabic_content.py`

    * `test_markdown_renderer_arabic_placeholder`
  * (optional) `tests/test_renderers_utf8_and_newlines.py`

### Deliverables

1. **RTL-aware render options (text renderer)**

   * Extend `TextRenderOptions` with:

     ```python
     RtlMode = Literal["none", "bidi_marks"]

     @dataclass
     class TextRenderOptions:
         ...
         rtl_mode: RtlMode = "none"
     ```

   * `rtl_mode=="none"`:

     * Preserve current behavior exactly.

   * `rtl_mode=="bidi_marks"`:

     * Detect Arabic characters (e.g. `\u0600-\u06FF`) and wrap the entire body for those messages with:

       ```python
       RLE = "\u202B"  # Right-to-Left Embedding
       PDF = "\u202C"  # Pop Directional Formatting
       ```

     * Helper:

       ```python
       def wrap_rtl_segments(text: str, rtl_mode: RtlMode) -> str: ...
       ```

     * Apply just before writing out each message line.

2. **RTL-aware Markdown skeleton**

   * Similar `MarkdownRenderOptions` with `rtl_mode`.
   * When `rtl_mode=="bidi_marks"`:

     * Apply `wrap_rtl_segments` to:

       * text messages,
       * voice transcript blockquotes,
       * media captions.

3. **UTF-8 and determinism**

   * Both renderers write files with:

     ```python
     open(out_path, "w", encoding="utf-8", newline="\n")
     ```

   * For given `messages.M3.jsonl` and `rtl_mode`, output must be byte-for-byte deterministic.

   * `rtl_mode` affects **only** output text, never `Message` objects.

4. **Docs**

   * `README_M5_RENDERING.md` explains:

     * RTL issues in many editors/terminals.
     * When to use `rtl_mode="bidi_marks"`.
     * Examples of output for each mode.

### Subtasks

1. Add `RtlMode` + `rtl_mode` to text renderer options.
2. Implement `wrap_rtl_segments` and wire into text renderer.
3. Add equivalent options to Markdown renderer.
4. Add/extend tests with Arabic/English mixed fixtures.
5. Write/update rendering docs.

### Verification & Tests

* `test_text_renderer_arabic_content_preserved`
  With default options, Arabic codepoints are preserved and output matches existing golden.
* `test_text_renderer_bidi_marks_mode`
  With `rtl_mode="bidi_marks"`, Arabic-containing messages are wrapped with `\u202B...\u202C` and non-Arabic messages are unchanged.
* `test_markdown_renderer_arabic_placeholder`
  Arabic content appears intact in Markdown output; bidi marks present as expected when enabled.
* `test_renderers_utf8_and_newlines`
  Asserts outputs are valid UTF-8 with only `\n` newlines.

### Acceptance (M6.8)

* Arabic-heavy chats produce readable, stable `chat_with_audio.txt` / `.md` in both modes.
* Toggling `rtl_mode` only changes bidi markers, not the underlying JSONL or pipeline logic.
* RTL tests pass; no regressions in existing M5 renderer tests.

---

## M6 — Overall Acceptance Criteria

* **Single command / single click** usage:

  * CLI:

    ```bash
    python scripts/run_pipeline.py --root /path/to/export --asr-provider whisper_openai
    ```

  * UI:

    * Double-click `WhatsAppTranscriberUI.bat` → configure run → click **Run**.

* **Concurrency**:

  * Increasing `max_workers_audio` from 1 to N does **not** change any outputs:

    * `messages.M3.jsonl`
    * `chat_with_audio.txt`
    * `run_manifest.json`
    * `metrics.json`

* **Resume & caching**:

  * Stopping the process mid-M3 and re-running with same config:

    * Reuses already-transcribed messages (identified via `derived["asr"]` / cache key).
    * Completes without duplicating work.
    * Leaves `run_manifest.json` consistent.

* **Failure surfaces are visible, not fatal**:

  * Bad chat file / missing export folder:

    * CLI returns non-zero exit code, manifest marks step as `failed`, and error summary is present.
  * Bad audio / unsupported format:

    * Messages are marked with `status="failed"` and appropriate `status_reason` (`ffmpeg_failed`, `audio_unsupported_format`, `asr_failed`, `timeout_asr`).
    * Renderer shows placeholder text but never crashes.

* **Contracts honored**:

  * All JSONL outputs obey `Message` schema invariants.
  * Required per-run files exist: `messages.M1/M2/M3.jsonl`, `chat_with_audio.txt`, `run_manifest.json`, `metrics.json`.
  * `preview_transcripts.txt` is optional and treated as “no data yet” when missing.

* **UI behavior**:

  * UI lists runs from `run_manifest.json` / `metrics.json`.
  * UI never crashes due to missing/invalid manifests or previews; it shows clear warnings instead.
  * Transcript previews match `preview_transcripts.txt`.

---

**Key tests (exhaustive for M6)**
*All of these should exist and stay green for M6 to be considered “done.”*

---

**Pipeline & runner**

* `tests/test_pipeline_config.py` — pipeline config parsing, root/chat/run_dir resolution, CLI → config mapping.

  * `test_pipeline_config_root_paths`
* `tests/test_pipeline_manifest.py` — `RunManifest` structure, step status transitions, JSON (de)serialization.

  * `test_pipeline_manifest_initial_structure`
* `tests/test_pipeline_runner_sequential.py` — happy-path sequential M1→M2→M3→M5.1 orchestration on a small chat.

  * `test_pipeline_runner_sequential_happy_path`
* `tests/test_pipeline_runner_concurrent.py` — concurrency in M3, ensuring multi-worker runs are byte-for-byte identical to sequential.

  * `test_pipeline_runner_concurrent_matches_sequential`
* `tests/test_pipeline_resume.py` — resume semantics, skipping completed steps/messages without corrupting outputs.

  * `test_pipeline_resume_skips_completed_steps`
* `tests/test_pipeline_metrics.py` — `RunMetrics` aggregation, counts/costs consistency with fixture data.

  * `test_pipeline_metrics_populated`
  * `test_pipeline_metrics_provider_counts`
* `tests/test_run_pipeline_cli_smoke.py` — end-to-end CLI smoke test; basic failure modes don’t crash the process.

  * `test_run_pipeline_cli_smoke`

---

**ASR providers & error handling**

* `tests/test_asr_client_whisper.py` — Whisper backend wiring into `AsrClient`, including model/provider selection and normalized results.

  * `test_asr_client_whisper`
  * `test_asr_client_whisper_basic`
* `tests/test_asr_client_google.py` — Google STT backend wiring into `AsrClient`, same guarantees as Whisper.

  * `test_asr_client_google`
  * `test_asr_client_google_basic`
* `tests/test_asr_provider_error_mapping.py` — deterministic mapping from provider error kinds → global `StatusReason` enums.

  * `test_asr_provider_error_mapping`
* `tests/test_asr_language_hints_plumbing.py` — `--asr-language` propagation from CLI → config → backend → `derived["asr"].language_hint`.

  * `test_asr_language_hints_plumbing`
* `tests/test_asr_error_mapping_realistic.py` — realistic mixed-success scenarios (timeouts, quota, auth) mapped to `ok/partial/failed` + correct `status_reason`.

  * `test_asr_error_mapping_realistic`
* `tests/test_audio_chunking_hardening.py` — chunking invariants: non-empty chunks for valid audio, `ChunkingError` for degenerate WAVs, placeholder + `error_summary` on failure.

  * `test_chunking_failure_sets_failed_status`
  * `test_chunk_manifest_non_empty_for_valid_audio`
  * `test_asr_chunking_error_sets_error_summary`
* `tests/test_derived_asr_provider_model.py` — `derived["asr"]` and `metrics.json` always include provider/model and stay in sync with config.

  * `test_derived_asr_provider_model`

---

**Manifest & metrics schema**

* `tests/test_manifest_schema_basic.py` — `run_manifest.json` shape validation against `run_manifest.schema.json`.

  * `test_manifest_schema_basic`
* `tests/test_metrics_schema_basic.py` — `metrics.json` shape validation against `metrics.schema.json`.

  * `test_metrics_schema_basic`
* `tests/test_manifest_and_metrics_golden.py` — golden comparison of manifest/metrics for `pipeline_small_chat` (with normalization of volatile fields).

  * `test_manifest_and_metrics_golden`

---

**UI & status**

* `tests/test_status_helpers.py` — listing runs, loading summaries, and preview lines from `run_dir` without crashing on missing/partial files.

  * `test_status_helpers_list_runs`
  * `test_status_helpers_load_run_summary`
  * `test_status_helpers_transcript_preview_parses_file`
* `tests/test_ui_app_imports_and_layout.py` — Streamlit app imports cleanly and builds the expected layout without side effects.

  * `test_ui_app_imports_and_layout`

---

**Rendering / RTL**

* `tests/test_text_renderer_arabic_content.py` — Arabic text preserved in text renderer; bidi-marks mode wraps Arabic messages correctly and deterministically.

  * `test_text_renderer_arabic_content_preserved`
  * `test_text_renderer_bidi_marks_mode`
* `tests/test_markdown_renderer_arabic_content.py` — same guarantees for Markdown renderer (Arabic content + bidi marks where enabled).

  * `test_markdown_renderer_arabic_placeholder`
* `tests/test_renderers_utf8_and_newlines.py` *(optional but recommended)* — all renderers write UTF-8 with `\n` newlines only.

  * `test_renderers_utf8_and_newlines`

---

**Launcher (if implemented)**

* `tests/test_launcher_imports.py` — Windows launcher helper (`launcher.py`) imports and resolves repo root / entrypoint without path errors.

  * `test_launcher_imports`


# Dev Notes (for Claude Code & Codex)

* Keep PRs to ≤5 files; if you touch more, split.
* `src/schema/message.py` is **the** schema; update there only, bump `schema_version` when shape changes.
* Update `CHANGELOG.md` whenever data shapes change.
* Prefer append-only changes to CSV columns; if you must reorder, bump a major.
* Each PR should add or update exactly the tests listed for its task.

```

