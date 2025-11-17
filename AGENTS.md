# AGENTS.md — Orchestrator & Tasks (M1–M3 Focus)

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


## CURRENT FOCUS

- Milestone: M3 — Audio Pipeline
- Task: M3.2 — ffmpeg OPUS→WAV conversion
- Branch: feat/m3-2-ffmpeg-opus-to-wav
- Status: In Progress



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
Chunk WAV audio into fixed windows with overlap and produce a deterministic chunk manifest.

**Deliverables**

* `_chunk_wav(wav_path: Path, cfg) -> list[dict]` with:

  * `chunk_index`, `start_sec`, `end_sec`
  * `wav_chunk_path` or `offsets`

* Attach manifest to `derived["asr"]["chunks"]`.

**Verification & Tests**

* Synthetic ~5-minute audio in `voice_multi/` or stubbed duration.
* `test_chunking_respects_length_and_overlap`.
* `test_chunk_manifest_stable_order`.

---

## M3.5 — ASR Client Wrapper (Whisper/Provider Abstraction)

**File:** `src/utils/asr.py`

**Objective**
Abstract ASR provider calls behind a clean interface with timeout/retry behavior per chunk.

**Deliverables**

* `AsrChunkResult` (dataclass or TypedDict).
* `AsrClient` with:

  ```python
  def __init__(self, cfg): ...
  def transcribe_chunk(self, wav_path: Path, start_sec: float, end_sec: float) -> AsrChunkResult: ...
  ```

**Verification & Tests**

* Mocked ASR in tests:

  * `test_asr_chunk_success_flow`.
  * `test_asr_chunk_error_raises`.

---

## M3.6 — Chunk Loop, Transcript Assembly & Derived Payload

**File:** `src/audio_transcriber.py`

**Objective**
Wire chunking and ASR to produce final transcript, attach to `Message`, and populate `derived["asr"]`.

**Behavior**

* For `kind="voice"` messages (VAD is informational only; ASR is always run on supported audio):
  * Loop over chunk manifest, call `AsrClient.transcribe_chunk`.

  * Assemble final transcript: newline-join of chunk texts.

  * Set:

    * `m.content_text` to transcript (if previously empty) or append with separator.
    * `m.status="ok"` if all chunks succeed.
    * `m.partial=False` unless chunks fail (see M3.8).

  * Extend `derived["asr"]` with:

    * `provider`, `model`, `language`,
    * `total_duration_seconds`,
    * `chunks` array (index/start/end/text/duration/status).

**Verification & Tests**

* Fixture `tests/fixtures/voice_multi/`.
* Mocked ASR returning `f"chunk-{i}"`:

  * `test_long_voice_chunk_and_join`.
  * `test_derived_asr_structure`.

---

## M3.7 — Caching (cache/audio/{hash}.json) & Idempotent Re-Runs

**File:** `src/audio_transcriber.py`, `src/utils/hashing.py`, `src/utils/cost.py`

**Objective**
Add content-addressed cache so repeated runs don’t recompute ASR, and store rich metadata for billing/metrics.

**Deliverables**

* `_make_cache_key(m: Message, cfg) -> str` based on:

  * audio file content hash,
  * core pipeline knobs (provider, model, chunk_seconds, overlap, VAD thresholds).

* `_load_cache(key: str) -> dict | None`

* `_write_cache(key: str, payload: dict) -> None`

* Cache file: `cfg.cache_dir / "audio" / f"{key}.json"`.

**Verification & Tests**

* `test_cache_write_and_read_roundtrip`.
* `test_cache_hit_skips_work`.
* `test_cache_respects_config_changes`.

---

## M3.8 — Error Mapping, Partial Transcripts & Status Discipline

**File:** `src/audio_transcriber.py`

**Objective**
Map all failure/partial cases to clear `status`, `status_reason`, and `partial` semantics.

**StatusReason codes used** (must match the global enum):

* `"ffmpeg_failed"`, `"timeout_ffmpeg"`
* `"vad_no_speech"`
* `"asr_failed"`, `"timeout_asr"`
* `"asr_partial"`
* `"audio_unsupported_format"`

**Behavior**

* If **all** chunks fail:

  * `m.status="failed"`, `m.status_reason="asr_failed"` or `"timeout_asr"`.
  * `m.content_text="[AUDIO TRANSCRIPTION FAILED]"` (if empty).
  * `m.partial=False`.

* If **some** chunks succeed, some fail:

  * Build transcript from successful chunks only.
  * `m.status="partial"`, `m.status_reason="asr_partial"`, `m.partial=True`.

* Always populate:

  * `derived["asr"]["error_summary"]` with counts and last error message.

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


# M6 — Orchestrator, Concurrency, Resume, Metrics & UI

**Milestone Goal**
Provide a **single, resumable pipeline** and a **small local UI** to run M1–M3 + M5 end-to-end for a given WhatsApp export, with:

* **Concurrency** for expensive stages (audio transcription).
* **Resume & idempotence** across runs (re-use caches & intermediate JSONL).
* **Metrics & cost summaries** per run.
* **Exceptions handled gracefully** (bad files/messages never crash the pipeline).
* A **double-clickable launcher** on Windows that opens a Streamlit UI in the browser.

M6 does **not** depend on M4 (image/PDF enrichment). If M4 is added later, it will slot into the same orchestration structure as an additional pipeline step.

---

## Code Surface (expected files)

New / primary modules:

* `src/pipeline/config.py`      — `PipelineConfig`, helpers for paths & defaults.
* `src/pipeline/manifest.py`    — `RunManifest` structure, read/write helpers.
* `src/pipeline/runner.py`      — `run_pipeline(cfg)`, orchestration + concurrency + metrics.
* `src/pipeline/status.py`      — small helpers for status/metrics aggregation (re-used by tests/UI).
* `config/asr.yaml`             — ASR provider/model defaults & per-provider settings.

ASR abstraction (extends existing M3 code):

* `src/utils/asr.py`            — `AsrClient` + provider backends (Whisper, Google).
* `src/audio_transcriber.py`    — updated to consume `AsrClient` via `AudioConfig.asr_provider`.

CLIs:

* `scripts/run_pipeline.py`     — one-shot pipeline runner (no UI).
* `scripts/ui_app.py`           — Streamlit UI app (localhost web UI).
* `scripts/WhatsAppTranscriberUI.bat` — Windows launcher (double-click → UI + logs).

Docs:

* `README_M6_PIPELINE.md`       — pipeline runner usage, concurrency/resume semantics.
* `README_M6_UI.md`             — UI usage, launcher instructions, provider notes.

Tests & fixtures:

* `tests/test_pipeline_config.py`
* `tests/test_pipeline_manifest.py`
* `tests/test_pipeline_runner_sequential.py`
* `tests/test_pipeline_runner_concurrent.py`
* `tests/test_pipeline_resume.py`
* `tests/test_pipeline_metrics.py`
* `tests/test_run_pipeline_cli_smoke.py`
* `tests/test_asr_client_whisper.py`
* `tests/test_asr_client_google.py`
* `tests/test_derived_asr_provider_model.py`
* `tests/test_status_helpers.py`
* `tests/fixtures/pipeline_small_chat/` (tiny end-to-end chat fixture)

> M6 changes **must not** break the contracts/tests for M1–M3 or M5.1 (renderer). All new behavior lives behind new functions/CLIs and config flags.

---

## M6.1 — Pipeline Runner & `run_manifest.json` (Orchestration, Concurrency, Resume, Metrics)

**Objective**
Create a single **pipeline runner** that:

1. Runs M1→M2→M3→M5.1 in a deterministic sequence.
2. Uses **concurrency** for per-voice ASR work.
3. Supports **resume** by reusing intermediate JSONL files and caches.
4. Maintains a **`run_manifest.json`** file for live status and run metadata.
5. Aggregates **per-run metrics** (counts, durations, costs) in a machine-readable form.

**Files**

* `src/pipeline/config.py`
* `src/pipeline/manifest.py`
* `src/pipeline/runner.py`
* `src/pipeline/status.py`
* `scripts/run_pipeline.py`
* `tests/test_pipeline_config.py`
* `tests/test_pipeline_manifest.py`
* `tests/test_pipeline_runner_sequential.py`
* `tests/test_pipeline_runner_concurrent.py`
* `tests/test_pipeline_resume.py`
* `tests/test_pipeline_metrics.py`
* `tests/test_run_pipeline_cli_smoke.py`
* `tests/fixtures/pipeline_small_chat/` (chat, media, voice fixtures)

---

### Deliverables

1. **Run directory layout**

   For each pipeline invocation, create a new `run_dir`, e.g.:

   ```text
   runs/
     2025-11-17T2110__my_chat/
       messages.M1.jsonl
       messages.M2.jsonl
       messages.M3.jsonl
       chat_with_audio.txt
       run_manifest.json
       preview_transcripts.txt      # optional, see below
       metrics.json
       logs/
         m1_parse.log
         m2_media.log
         m3_audio.log
         m5_render.log
   ```

2. **`PipelineConfig`**

   `src/pipeline/config.py`:

   ```python
   from dataclasses import dataclass
   from pathlib import Path
   from typing import Optional, Literal

   AsrProvider = Literal["whisper_openai", "whisper_local", "google_stt"]

   @dataclass
   class PipelineConfig:
       root: Path                # WhatsApp export folder
       chat_file: Path           # concrete _chat.txt file
       run_dir: Path             # runs/<run_id>/
       asr_provider: AsrProvider = "whisper_openai"
       asr_model: Optional[str] = None  # provider-specific default if None
       sample_voices: Optional[int] = None  # limit # of voice messages for test runs
       max_workers_audio: int = 4        # concurrency for ASR
       overwrite_existing: bool = False  # if False, reuse existing step outputs
   ```

   Helpers for:

   * **Run id creation** (`create_run_id(chat_file) -> str`).
   * **Path helpers** (`get_messages_path(cfg, stage)`, `get_manifest_path(cfg)`, etc.).

3. **`RunManifest` & helpers**

   `src/pipeline/manifest.py`:

   ```python
   from dataclasses import dataclass, field
   from typing import Dict, Literal, Optional
   from pathlib import Path

   StepName = Literal["M1_parse", "M2_media", "M3_audio", "M5_render"]
   StepStatus = Literal["pending", "running", "ok", "failed"]

   @dataclass
   class StepProgress:
       status: StepStatus = "pending"
       total: int = 0
       done: int = 0
       errors: int = 0

   @dataclass
   class RunManifest:
       run_id: str
       root: str
       chat_file: str
       start_time: str
       end_time: Optional[str] = None
       current_step: Optional[StepName] = None
       steps: Dict[StepName, StepProgress] = field(default_factory=dict)
       summary: dict = field(default_factory=dict)
   ```

   Functions:

   * `init_manifest(cfg: PipelineConfig) -> RunManifest`
   * `load_manifest(path: Path) -> RunManifest`
   * `save_manifest(manifest: RunManifest, path: Path) -> None`
   * `update_step(manifest, step, **kwargs)` (e.g. `status`, `total`, `done`).

   Behavior:

   * Manifest is **overwritten atomically** on each update (write to temp file then rename).
   * `current_step` always points to the currently active step or `None` when done.

4. **Pipeline runner**

   `src/pipeline/runner.py` exposes:

   ```python
   def run_pipeline(cfg: PipelineConfig) -> None:
       ...
   ```

   Responsibilities:

   * Ensure `run_dir` exists; create `logs/`.

   * Initialize `RunManifest` and write to `run_manifest.json`.

   * Execute steps **in order**:

     1. **M1_parse**

        * If `messages.M1.jsonl` exists and `overwrite_existing=False` and manifest says `ok`, **reuse**.
        * Otherwise invoke M1 logic (reuse `parse_chat.py` internals), write M1 JSONL, update manifest with `total`/`done` (# messages).
        * Log to `logs/m1_parse.log` and stdout.

     2. **M2_media**

        * Same pattern with `messages.M2.jsonl`.
        * Reuse M1 output as input; run resolver; write M2 JSONL and `exceptions.csv`, update step totals.

     3. **M3_audio**

        * Determine list of `kind="voice"` messages from M2 output.
        * Process them with **concurrency** (see below) using `AudioTranscriber` + `AsrClient`.
        * Incrementally update `done` and metrics after each voice note.
        * Write full `messages.M3.jsonl` on success; handle resume (if some messages already have `derived["asr"]` with current pipeline version, skip them).

     4. **M5_render**

        * Invoke text renderer (M5.1) on `messages.M3.jsonl`, producing `chat_with_audio.txt`.
        * Update `M5_render` step in manifest.

   * On any **fatal error** inside a step:

     * Mark that step `status="failed"`, set `current_step=None`, record error summary in `manifest.summary["error"]`.
     * Re-raise or exit non-zero from CLI.

5. **Concurrency for M3 (audio)**

   In `run_pipeline`:

   * Use `ThreadPoolExecutor` or `ProcessPoolExecutor` (configurable) for voice messages:

     ```python
     with ThreadPoolExecutor(max_workers=cfg.max_workers_audio) as ex:
         for m in voice_messages:
             ex.submit(process_one_voice, m, ...)
     ```

   * `process_one_voice`:

     * Calls `AudioTranscriber.transcribe(m)` (which uses `AsrClient`).
     * Writes progress in a **thread-safe** way:

       * Increase `done` count for `M3_audio` in manifest.
       * Append preview line to `preview_transcripts.txt` when new transcript becomes available.

   * Determinism:

     * Although processing order is concurrent, final `messages.M3.jsonl` must be written in **sorted order by `idx`**.
     * Manifest only tracks counts; no ordering assumptions.

6. **Resume behavior**

   * Step-level resume:

     * If `messages.M1.jsonl`/`M2`/`M3` exist and corresponding manifest step is `ok`, and `overwrite_existing=False`, skip recomputing that step.

   * Within M3:

     * When re-running, inspect `messages.M2.jsonl` and existing `messages.M3.jsonl` (if present).
     * For any voice message there that already has `derived["asr"]["pipeline_version"] == CURRENT_VERSION` and `status` not in `{"failed"}`, skip re-transcribing.
     * Concurrency pool only schedules **missing** or outdated messages.

7. **Metrics aggregation**

   * At the end of `run_pipeline`, compute a `metrics.json` in `run_dir`, e.g.:

     ```json
     {
       "messages_total": 523,
       "voice_total": 72,
       "voice_ok": 60,
       "voice_partial": 8,
       "voice_failed": 4,
       "voice_skipped_vad": 0,
       "media_resolved": 380,
       "media_unresolved": 30,
       "media_ambiguous": 20,
       "asr_provider": "whisper_openai",
       "asr_model": "whisper-1",
       "audio_seconds_total": 1832.5,
       "asr_cost_total_usd": 3.72,
       "wall_clock_seconds": 217.3
     }
     ```

   * Expose metrics to `RunManifest.summary["metrics"]` for UI consumption.

8. **CLI wrapper**

   `scripts/run_pipeline.py`:

   * Arguments:

     ```text
     --root        (export folder, required)
     --chat-file   (path to specific chat .txt; optional if root has only one)
     --asr-provider (whisper_openai|whisper_local|google_stt)
     --asr-model   (optional; provider default if omitted)
     --sample-voices N   (optional; pass to cfg.sample_voices)
     --max-workers-audio N
     --run-dir     (optional override for runs/<run_id>/)
     --overwrite-existing
     ```

   * Prints:

     * Step transitions:

       ```text
       [M1] Parsed 523 messages from _chat.txt
       [M2] Media resolved: resolved=380, unresolved=30, ambiguous=20
       [M3] Transcribing 72 voice notes with whisper_openai (4 workers)...
       [M5] Rendered 523 messages → chat_with_audio.txt
       ```

     * Final summary based on metrics.

---

### Subtasks

1. Implement `PipelineConfig` & helpers (paths, run_id).
2. Implement `RunManifest` structure + read/write helpers.
3. Implement `run_pipeline` sequential flow (no concurrency), reusing M1/M2/M3/M5 internals.
4. Add concurrency around M3 (audio) with deterministic final output.
5. Implement basic resume semantics (step-level + audio-level).
6. Implement metrics aggregation & `metrics.json`.
7. Implement `scripts/run_pipeline.py` CLI with argparse, wiring to `run_pipeline`.
8. Add logging to both **stdout** and `logs/*.log`.
9. Wire `preview_transcripts.txt` writing for newly completed voice messages.
10. Document behavior in `README_M6_PIPELINE.md`.

---

### Verification & Tests

Fixtures:

* `tests/fixtures/pipeline_small_chat/`:

  * Small `_chat.txt` with:

    * A few text messages.
    * Some media placeholders.
    * 3–5 voice notes.
  * Minimal media tree with 1–2 resolvable voice files.

Tests:

* `test_pipeline_config_root_paths`
  `PipelineConfig` derives `run_dir`, messages paths, manifest path correctly.

* `test_pipeline_manifest_initial_structure`
  `init_manifest` populates `steps` with all step names as `pending`, `total=0`, `done=0`.

* `test_pipeline_runner_sequential_happy_path`
  Force `max_workers_audio=1`, run pipeline on small fixture, assert:

  * All step statuses become `ok`.
  * `messages.M1/M2/M3.jsonl`, `chat_with_audio.txt`, `metrics.json` exist.

* `test_pipeline_runner_concurrent_matches_sequential`
  Run pipeline twice:

  * Once with `max_workers_audio=1`.
  * Once with `max_workers_audio=4`.

  Compare resulting `messages.M3.jsonl` and `chat_with_audio.txt` byte-for-byte.

* `test_pipeline_resume_skips_completed_steps`

  * First run: full pipeline.
  * Second run: modify manifest to mark M1/M2 as `ok`, M3 as `pending`, delete `messages.M3.jsonl` only.
  * Assert second run reuses M1/M2 and only recomputes M3/M5.

* `test_pipeline_metrics_populated`
  Ensure `metrics.json` has required keys and non-trivial values.

* `test_run_pipeline_cli_smoke`

  * Invoke `scripts/run_pipeline.py` via `subprocess`.
  * Exit code 0, manifests & outputs present, logs non-empty.

**Acceptance (M6.1)**

* Running:

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

without changing pipeline or UI code. Ensure provider/model info and cost are reflected in `derived["asr"]`, `metrics.json`, and `RunManifest`.

**Files**

* `src/utils/asr.py`         (significant update)
* `src/audio_transcriber.py` (small integration changes)
* `config/asr.yaml`
* `src/pipeline/config.py`   (add `asr_provider`, `asr_model` defaults)
* `src/pipeline/runner.py`   (plumb provider/model into `AudioConfig`)
* `tests/test_asr_client_whisper.py`
* `tests/test_asr_client_google.py`
* `tests/test_derived_asr_provider_model.py`

---

### Deliverables

1. **Config file for providers**

   `config/asr.yaml`:

   ```yaml
   default_provider: whisper_openai
   providers:
     whisper_openai:
       model: whisper-1
       timeout_seconds: 30
       max_retries: 2
       billing: "openai_whisper_v1"
     google_stt:
       model: "default-google-model"
       timeout_seconds: 30
       max_retries: 2
       billing: "google_stt_standard"
   ```

2. **ASR abstractions**

   In `src/utils/asr.py`:

   * `AsrChunkResult` dataclass / TypedDict:

     ```python
     @dataclass
     class AsrChunkResult:
         text: str
         start_sec: float
         end_sec: float
         language: Optional[str]
         confidence: Optional[float]
         provider: str
         model: str
         raw: dict  # small, provider-specific snippet (no full responses)
     ```

   * Provider backend protocol:

     ```python
     class AsrBackend:
         def transcribe_chunk(self, wav_path: Path, start_sec: float, end_sec: float) -> AsrChunkResult:
             ...
     ```

   * `WhisperBackend(AsrBackend)`:

     * Uses OpenAI Whisper API or local Whisper executable depending on config.
     * Handles timeout/retries.
     * Normalizes responses into `AsrChunkResult`.

   * `GoogleSttBackend(AsrBackend)`:

     * Uses Google Speech-to-Text client.
     * Also handles timeout/retries.
     * Normalizes responses into `AsrChunkResult`.

   * `AsrClient`:

     ```python
     class AsrClient:
         def __init__(self, provider: str, model: Optional[str], timeout: float, max_retries: int, billing_key: str):
             ...
         def transcribe_chunk(self, wav_path: Path, start_sec: float, end_sec: float) -> AsrChunkResult:
             ...
     ```

     * Dispatches to appropriate backend based on `provider`.

3. **Integration with `AudioTranscriber`**

   * Extend `AudioConfig` (M3) to include:

     ```python
     asr_provider: str
     asr_model: str
     asr_timeout_seconds: float
     asr_max_retries: int
     asr_billing_key: str
     ```

   * In `AudioTranscriber.__init__`, create a single `AsrClient` using these settings.

   * In the chunk loop, call `asr_client.transcribe_chunk(...)` and attach:

     ```python
     derived["asr"]["provider"] = asr_result.provider
     derived["asr"]["model"] = asr_result.model
     ```

4. **Cost estimation integration**

   * `src/utils/cost.py` already provides `estimate_asr_cost(seconds, provider, model, billing)` from M3.9.
   * Ensure `AsrClient` passes the correct `billing_key` for each provider/model so M3 can compute cost per message.
   * M6.1 metrics aggregation then sums these per-message costs.

5. **Pipeline config integration**

   * `PipelineConfig` should load ASR defaults from `config/asr.yaml` when `asr_provider` or `asr_model` is `None`.
   * `run_pipeline` passes ASR settings into `AudioTranscriber` via `AudioConfig`.

---

### Subtasks

1. Implement `config/asr.yaml` and loader function to get defaults.
2. Implement `AsrChunkResult`, `AsrBackend` protocol.
3. Implement `WhisperBackend` stub with minimal, testable behavior (mocked in tests).
4. Implement `GoogleSttBackend` stub with minimal, testable behavior (also mocked).
5. Implement `AsrClient` dispatcher and retry/timeout logic.
6. Extend `AudioConfig` and `AudioTranscriber` to use `AsrClient` (no provider-specific code inside `AudioTranscriber`).
7. Plumb `asr_provider` + `asr_model` from `PipelineConfig` → `AudioConfig`.
8. Ensure `derived["asr"]` always contains `provider` and `model`.
9. Ensure `cost.py` and M3 cost logic are called with correct billing key.
10. Document provider usage & environment variables (keys) in `README_M6_PIPELINE.md` or `README_M3.md`.

---

### Verification & Tests

* `test_asr_client_whisper_basic`
  With a mocked Whisper backend, ensure:

  * `AsrClient` calls the correct backend.
  * Returns normalized `AsrChunkResult`.
  * Retries on failure up to `max_retries`.

* `test_asr_client_google_basic`
  Same pattern for Google STT backend with mocks.

* `test_audio_transcriber_records_provider_model`
  For a dummy voice message, after transcription:

  * `msg.derived["asr"]["provider"]` and `["model"]` match `PipelineConfig` settings.
  * `metrics.json` summarises the same provider/model.

* `test_cost_estimation_uses_billing_key`
  For both Whisper and Google configs, ensure per-message cost uses the correct billing table entry.

**Acceptance (M6.2)**

* Changing `--asr-provider` and/or `--asr-model` on `run_pipeline.py` reflects correctly in:

  * `derived["asr"].provider/model` per voice message.
  * `metrics.json["asr_provider"]` / `["asr_model"]`.
  * Total cost computed from the provider’s billing configuration.

* Pipeline behavior (status/partial/failure logic) is unchanged except for provider/model selection.

---

## M6.3 — Streamlit UI (Local Web App)

**Objective**
Provide a **local web UI** (Streamlit) that sits on top of `run_pipeline(cfg)` and `RunManifest` to:

1. Configure runs (export folder, chat file, ASR provider, sample mode).
2. Start a pipeline run.
3. Show **live step progress** (M1–M3–M5).
4. Show a **transcript preview** as voice notes are processed.
5. Provide links to open/download the final outputs.

**Files**

* `scripts/ui_app.py`
* `src/pipeline/status.py` (helpers reused between tests/UI)
* `README_M6_UI.md`
* `tests/test_status_helpers.py`
* (Optional) `tests/test_ui_helpers_manifest_parsing.py`

---

### Deliverables

1. **Streamlit app layout**

   `scripts/ui_app.py` should define:

   * A **Run Configuration** section:

     * **Export folder** text input.
     * **Scan** button → discovers chat text files in folder.
     * **Chat file** dropdown populated from scan results.
     * **ASR provider** dropdown (`whisper_openai`, `whisper_local`, `google_stt`).
     * **Sample mode** checkbox + numeric input (`sample_voices`).
     * **Run** button that creates a `PipelineConfig` and triggers `run_pipeline`.

   * A **Run Status** section:

     * Dropdown or text input for `run_id` (default to latest run).
     * Summary of pipeline steps (M1–M3–M5) with progress bars & counts from manifest.
     * Aggregated metrics (total messages, voice ok/partial/failed, cost, elapsed time).

   * A **Transcript Preview** section:

     * Table showing latest N voice notes:

       | Time | Sender | Provider | Status | Excerpt |

     * Data source: `preview_transcripts.txt` or `messages.M3.jsonl`.

   * An **Outputs** section:

     * Buttons/links to open/download:

       * `chat_with_audio.txt`
       * `messages.M3.jsonl`
       * `exceptions.csv`
       * `metrics.json`

2. **Run launching**

   * Use either:

     * A background **thread** inside the Streamlit process, or
     * Spawn a separate `run_pipeline.py` **subprocess** from the UI.

   * The UI **must not block** while pipeline runs; it should rely on polling `run_manifest.json` and preview files to show progress.

3. **Manifest & preview reading helpers**

   `src/pipeline/status.py`:

   * `list_runs(runs_root: Path) -> list[str]`
     Returns sorted list of `run_id` directories.

   * `load_run_summary(run_dir: Path) -> dict`
     Reads `run_manifest.json` and `metrics.json`, merges into a simple dict structure for display.

   * `load_transcript_preview(run_dir: Path, limit: int = 20) -> list[dict]`
     Reads `preview_transcripts.txt` (or `messages.M3.jsonl` as fallback) and returns last `limit` rows (for UI table).

4. **UI behavior & refresh**

   * Streamlit’s rerun behavior should periodically refresh status:

     * E.g. wrap status display in `st.autorefresh` or rely on Streamlit’s default behavior when the user interacts.
     * Reads most recent manifest & preview files each render.

   * When a new run starts, the UI shows:

     * Step statuses turning from `pending` → `running` → `ok`.
     * Voice note preview table gradually filling as `preview_transcripts.txt` grows.

5. **Error surfacing**

   * If `run_manifest.summary["error"]` exists, display it clearly in the UI:

     * e.g., red `st.error("Run failed: <message>")`.

---

### Subtasks

1. Implement `src/pipeline/status.py` helpers (`list_runs`, `load_run_summary`, `load_transcript_preview`).
2. Implement `scripts/ui_app.py` Streamlit layout (sections described above).
3. Wire `Run` button to start a new `run_pipeline` invocation (thread/subprocess).
4. Implement a simple **run history** selector (most recent run id preselected).
5. Implement transcript preview using `preview_transcripts.txt` or `messages.M3.jsonl` fallback.
6. Add download/open buttons for outputs (using Streamlit file download mechanisms).
7. Document how to start the UI in `README_M6_UI.md`.

---

### Verification & Tests

Logic-level tests (no real browser automation):

* `test_status_helpers_list_runs`
  Creates a temporary `runs/` folder with 2–3 dummy run dirs and asserts `list_runs()` returns them in expected order.

* `test_status_helpers_load_run_summary`
  Given a synthetic `run_manifest.json` + `metrics.json`, ensure `load_run_summary` produces structured summary with step names and basic metrics.

* `test_status_helpers_transcript_preview_parses_file`
  Given a small `preview_transcripts.txt`, ensure preview list has expected fields (time, sender, excerpt).

UI smoke (optional, minimal):

* `test_ui_app_imports_and_layout`
  Import `scripts.ui_app` in tests to ensure no top-level exceptions (e.g. missing imports). Optionally, verify that certain widget labels exist via Streamlit’s testing utilities if available.

Manual acceptance (for you):

* Run:

  ```bash
  streamlit run scripts/ui_app.py
  ```

* In browser:

  * Choose export folder & chat file.
  * Select ASR provider.
  * Click **Run** and observe:

    * Step progress updates.
    * Transcript preview populates as voice notes finish.
    * Links to open final `chat_with_audio.txt` and metrics.

---

## M6.4 — Launcher (`.bat` / optional `.exe`) & Docs

**Objective**
Provide a **double-click entry point** on Windows that:

1. Opens a console window for logs.
2. Activates the Python environment.
3. Launches the Streamlit UI (`ui_app.py`).
4. Leaves the console open so you can see logs/errors if anything goes wrong.

Later (optional), package a `.exe` that wraps this behavior.

**Files**

* `scripts/WhatsAppTranscriberUI.bat`
* (Optional) `scripts/launcher.py` (Python wrapper for PyInstaller)
* `README_M6_UI.md` (updated with launcher instructions)

---

### Deliverables

1. **Batch launcher**

   `scripts/WhatsAppTranscriberUI.bat`:

   ```bat
   @echo off
   REM Adjust paths as needed for your environment
   cd /d C:\path\to\your\repo

   REM Activate venv (if used)
   call venv\Scripts\activate

   REM Run Streamlit UI
   streamlit run scripts\ui_app.py

   REM Keep console open so logs are visible
   pause
   ```

   Behavior:

   * Double-clicking this file:

     * Opens a console.
     * Runs Streamlit.
     * Opens browser to `http://localhost:8501`.
     * Keeps console open after exit (`pause`), so you see any errors.

2. **Optional Python launcher (for `.exe`)**

   `scripts/launcher.py`:

   * A small script that:

     * Locates repo root.
     * Ensures environment variables (like `OPENAI_API_KEY`, `GOOGLE_APPLICATION_CREDENTIALS`) are present or emits a friendly error.
     * Calls `streamlit run scripts/ui_app.py` via `subprocess`.

   * Used as the **entry point** for PyInstaller if/when you package an `.exe`.

3. **Docs**

   Update `README_M6_UI.md` with:

   * How to run UI via:

     * `streamlit run scripts/ui_app.py` (dev mode).
     * Double-clicking `WhatsAppTranscriberUI.bat`.

   * Basic troubleshooting (e.g. port in use, missing keys).

---

### Subtasks

1. Create `WhatsAppTranscriberUI.bat` with working paths for your repo layout.
2. (Optional) Implement `scripts/launcher.py` and test it via `python scripts/launcher.py`.
3. Update `README_M6_UI.md` with exact instructions and screenshots/notes if needed.
4. (If you later use PyInstaller) create a separate task/PR for packaging `launcher.py` into `.exe`.

---

### Verification & Tests

Automated tests for `.bat` are not necessary; rely on **manual smoke**:

* Double-click `scripts/WhatsAppTranscriberUI.bat`:

  * Console opens.
  * Streamlit UI opens in browser.
  * If you close the browser tab, console still shows logs.
  * If something fails (e.g., missing `streamlit`), error is visible in console.

If `scripts/launcher.py` exists:

* `test_launcher_imports`
  Import and call a small helper (e.g., `get_repo_root()`) to ensure no path logic breaks.

**Acceptance (M6.4)**

* On your machine, you can **double-click one file** and end up at the Streamlit UI without touching CLI.
* Console logs remain visible for debugging, matching your mental model: “I double-click, browser opens, I see the steps and output.”

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

  * M3 audio transcription runs concurrently when `max_workers_audio > 1`.
  * Outputs (JSONL, text) remain deterministic vs single-threaded run.

* **Resume**:

  * Step-level reuse of existing JSONL outputs.
  * Per-voice reuse based on `derived["asr"]["pipeline_version"]`.
  * Killing the process and re-running completes without re-doing work already done.

* **Metrics**:

  * `metrics.json` contains meaningful counts, durations, and cost.
  * `RunManifest.summary["metrics"]` reflects the same.

* **Exceptions**:

  * Bad audio files/media do not crash pipeline; they are handled via existing M3 status/status_reason semantics.
  * Pipeline only fails “hard” for genuine infra/logic problems (e.g., file not found, schema mismatch), which are captured in manifest and visible in UI/logs.

* **UI**:

  * Shows:

    * Step progress.
    * Live transcript previews (from preview file).
    * Correct ASR provider/model and cost summary.

  * Allows **provider switching** (Whisper vs Google) per run without code changes.

---

## M6 — Test Plan (Quick List)

* `test_pipeline_config_root_paths`
* `test_pipeline_manifest_initial_structure`
* `test_pipeline_runner_sequential_happy_path`
* `test_pipeline_runner_concurrent_matches_sequential`
* `test_pipeline_resume_skips_completed_steps`
* `test_pipeline_metrics_populated`
* `test_run_pipeline_cli_smoke`
* `test_asr_client_whisper_basic`
* `test_asr_client_google_basic`
* `test_audio_transcriber_records_provider_model`
* `test_cost_estimation_uses_billing_key`
* `test_status_helpers_list_runs`
* `test_status_helpers_load_run_summary`
* `test_status_helpers_transcript_preview_parses_file`
* `test_ui_app_imports_and_layout` (lightweight)
* Manual: double-click `WhatsAppTranscriberUI.bat` and run a full pipeline end-to-end from UI.

---

# Dev Notes (for Claude Code & Codex)

* Keep PRs to ≤5 files; if you touch more, split.
* `src/schema/message.py` is **the** schema; update there only, bump `schema_version` when shape changes.
* Update `CHANGELOG.md` whenever data shapes change.
* Prefer append-only changes to CSV columns; if you must reorder, bump a major.
* Each PR should add or update exactly the tests listed for its task.

```

