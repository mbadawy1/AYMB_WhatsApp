# WhatsApp Pipeline (M1–M5 Progress)

Unified notes for the WhatsApp chat pipeline through M5.2. All commands assume repo root with `PYTHONPATH=.`.

## Milestone Overview

- **M1 — Parser & Schema**: Message model, timestamp detect/parse, header split, multiline join, kind classification, caption merge, schema validation.
- **M2 — Media Resolver**: Media indexing + scoring (hints, ext priority, WA seq, mtime), filename fast path, ambiguity/unresolved logging to `exceptions.csv`.
- **M3 — Audio Pipeline**: ffmpeg → WAV, VAD metrics (no gating), chunking (120s, 0.25s overlap), ASR stub per chunk, status mapping, caching with cost.
- **M5.1 — Text Renderer**: Deterministic `chat_with_audio.txt` writer with system/hide/status/flatten options.
- **M5.2 — Transcript Preview**: Single-line voice previews + batch writer and CLI.

Current branch: `feat/m1-1-project-skeleton`. Tests: `pytest -q` (104 passing).

## CLIs

- **Parse (M1)**  
  `python scripts/parse_chat.py --root /path/to/export`  
  Outputs JSONL to stdout; set `VALIDATE_SCHEMA=true` to enforce schema during parse.

- **Resolve media (M2)**  
  `python scripts/resolve_media.py --root /path/to/export`  
  Resolves media placeholders, writes JSONL to stdout, and `exceptions.csv` for unresolved/ambiguous cases.

- **Transcribe audio (M3)**  
  `python scripts/transcribe_audio.py --root /path/to/export [--no-cache]`  
  Parses → resolves media → runs audio pipeline; prints voice status summary.

- **Render chat text (M5.1)**  
  `python scripts/render_txt.py --messages path/to/messages.jsonl --out chat_with_audio.txt [--hide-system --show-status --flatten-multiline]`

- **Render preview lines (M5.2)**  
  `python scripts/render_preview.py --messages path/to/messages.jsonl --out preview_transcripts.txt [--max-chars 120]`

- **Full pipeline (M6.1 runner)**  
  `python scripts/run_pipeline.py --root /path/to/export [--run-id demo --run-dir runs/demo --max-workers-audio 4]`  
  Executes M1→M2→M3→M5 sequentially with resume-aware manifests/metrics written to the run directory (messages.M1/M2/M3.jsonl, chat_with_audio.txt, preview_transcripts.txt, run_manifest.json, metrics.json).

## WhatsApp Message Schema (M1 core)

Fields and enums live in `src/schema/message.py`. Schema is the single source of truth; update there and in `schema/message.schema.json` if the shape changes.

## Audio Pipeline (M3) Highlights

- ffmpeg: 16 kHz mono WAV, retries/timeouts, status_reason on failure.
- VAD: metrics only (`derived["asr"]["vad"]`); never gates ASR.
- Chunking: deterministic 120s windows, 0.25s overlap, stable filenames.
- ASR: stub client per chunk; transcript assembly; status/partial mapping.
- Cache: `cache/audio/{hash}.json` keyed by media hash + config; includes transcript, status, derived asr, cost.
- Cost: `derived["asr"]["cost"]` via table-driven rates.

## Renderers (M5.1–M5.2)

- `render_messages_to_txt`: deterministic text output; skips caption tails; placeholders for media/voice/system with options to hide system, show status, flatten multiline.
- `format_preview_line`: single-line summary for voice messages (timestamp, idx, sender, status[/reason], provider, excerpt with truncation/escaping).
- `write_transcript_preview`: writes `preview_transcripts.txt` for all voice messages in idx order.

## Testing

Run all tests:

```bash
PYTHONPATH=. pytest -q
```

Key suites: parser, media resolver, audio pipeline (ffmpeg/VAD/chunking/ASR/cache/cost), text renderer, preview renderer, CLIs.

## Guardrails

- Keep changes ≤ ~300 LOC and ≤ 5 files per PR.
- Do not alter schema outside `src/schema/message.py`; bump version if fields change.
- Preserve determinism (ordering, timestamps, newline style, placeholders).
- Update docs when behavior changes; this README is the consolidated source for milestones and CLIs.
