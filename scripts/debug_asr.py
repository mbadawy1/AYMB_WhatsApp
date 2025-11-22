#!/usr/bin/env python3
"""ASR Error Debugging Tool

Usage:
    python scripts/debug_asr.py <run_id> [options]
    python scripts/debug_asr.py <run_id> --message-idx 6
    python scripts/debug_asr.py <run_id> --show-all-failures
    python scripts/debug_asr.py <run_id> --export-csv failures.csv

Examples:
    # Show all voice message failures for a run
    python scripts/debug_asr.py aymb-1

    # Inspect specific message by index
    python scripts/debug_asr.py aymb-1 --message-idx 55

    # Show all failures with detailed logs
    python scripts/debug_asr.py aymb-1 --show-all-failures --verbose

    # Export all failures to CSV
    python scripts/debug_asr.py aymb-1 --export-csv asr_errors.csv
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Optional
import csv


def load_messages(run_id: str, root_dir: Optional[Path] = None) -> list[dict]:
    """Load messages.M3.jsonl from a run directory."""
    if root_dir is None:
        root_dir = Path.cwd()

    # Try both messages.M3.jsonl and messages.jsonl
    run_dir = root_dir / "runs" / run_id

    # First try M3-specific file
    messages_file = run_dir / "messages.M3.jsonl"
    if not messages_file.exists():
        # Fall back to messages.jsonl
        messages_file = run_dir / "messages.jsonl"

    if not messages_file.exists():
        print(f"❌ Run not found: {run_id}", file=sys.stderr)
        print(f"   Expected: {run_dir / 'messages.M3.jsonl'}", file=sys.stderr)
        print(f"   Or: {run_dir / 'messages.jsonl'}", file=sys.stderr)
        sys.exit(1)

    messages = []
    with messages_file.open("r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                messages.append(json.loads(line))

    return messages


def classify_error_pattern(msg: dict) -> str:
    """Classify the error pattern for a failed voice message."""
    derived = msg.get("derived", {})
    asr = derived.get("asr", {})
    error_summary = asr.get("error_summary", {})

    # Check backend type
    provider = asr.get("provider", "unknown")

    # Check for stub backend in provider name
    if "stub" in provider.lower():
        return "STUB_BACKEND"

    # Check error kind
    error_kind = error_summary.get("last_error_kind")
    error_msg = (error_summary.get("last_error_message") or "").lower()

    if error_kind == "chunking":
        return "CHUNKING_ERROR"
    elif error_kind == "timeout":
        return "TIMEOUT"
    elif error_kind == "auth":
        return "AUTH_ERROR"
    elif error_kind == "quota":
        return "QUOTA_EXCEEDED"
    elif error_kind == "client":
        return "CLIENT_ERROR"
    elif error_kind == "server":
        return "SERVER_ERROR"

    # Check status_reason for ffmpeg errors
    status_reason = msg.get("status_reason", {})
    if status_reason:
        code = status_reason.get("code", "")
        if code == "timeout_ffmpeg":
            return "FFMPEG_TIMEOUT"
        elif code == "ffmpeg_failed":
            return "FFMPEG_ERROR"
        elif code == "audio_unsupported_format":
            return "UNSUPPORTED_FORMAT"

    # Check for simulated failure
    if "simulated_failure" in error_msg:
        return "SIMULATED_FAILURE"

    # Check for missing module
    if "no module named" in error_msg:
        return "MISSING_DEPENDENCY"

    return "UNKNOWN_ERROR"


def format_error_summary(msg: dict, verbose: bool = False) -> str:
    """Format a human-readable error summary for a voice message."""
    idx = msg.get("idx", "?")
    ts = msg.get("ts", "unknown")
    sender = msg.get("sender", "unknown")
    status = msg.get("status", "unknown")
    media_filename = msg.get("media_filename", "unknown")

    derived = msg.get("derived", {})
    asr = derived.get("asr", {})
    error_summary = asr.get("error_summary", {})

    pattern = classify_error_pattern(msg)
    provider = asr.get("provider", "unknown")
    model = asr.get("model", "unknown")

    chunks_ok = error_summary.get("chunks_ok", 0)
    chunks_error = error_summary.get("chunks_error", 0)
    error_kind = error_summary.get("last_error_kind", "unknown")
    error_msg = error_summary.get("last_error_message", "")

    # Build summary
    lines = [
        f"\n{'='*70}",
        f"Message idx={idx} | {ts} | {sender}",
        f"{'='*70}",
        f"Status: {status}",
        f"Media: {Path(media_filename).name if media_filename else 'N/A'}",
        f"Error Pattern: {pattern}",
        f"Provider: {provider}",
        f"Model: {model}",
        f"Chunks: {chunks_ok} OK, {chunks_error} failed",
        f"Error Kind: {error_kind}",
    ]

    if error_msg:
        lines.append(f"Error Message: {error_msg[:300]}{'...' if len(error_msg) > 300 else ''}")

    # Add recommendations
    lines.append(f"\n🔍 Diagnosis:")
    if pattern == "STUB_BACKEND":
        lines.append("  → Using stub backend (simulated ASR)")
        lines.append("  → Set OPENAI_API_KEY or GOOGLE_APPLICATION_CREDENTIALS")
    elif pattern == "SIMULATED_FAILURE":
        lines.append("  → Stub backend simulating failure")
        lines.append("  → Set API key to use real provider")
    elif pattern == "MISSING_DEPENDENCY":
        lines.append("  → Python package not installed")
        if "google.cloud" in error_msg:
            lines.append("  → Run: pip install google-cloud-speech")
        elif "openai" in error_msg:
            lines.append("  → Run: pip install openai")
    elif pattern == "AUTH_ERROR":
        lines.append("  → Authentication failed")
        lines.append("  → Check API key: OPENAI_API_KEY or GOOGLE_APPLICATION_CREDENTIALS")
        lines.append("  → For Google: Ensure env var points to valid JSON key file")
        lines.append("  → For OpenAI: Verify API key format (sk-...)")
    elif pattern == "QUOTA_EXCEEDED":
        lines.append("  → API quota or rate limit exceeded")
        lines.append("  → Wait and retry, or check billing settings")
        lines.append("  → For Google: Check GCP quotas dashboard")
        lines.append("  → For OpenAI: Check usage dashboard")
    elif pattern == "TIMEOUT":
        lines.append("  → Request timed out")
        lines.append("  → Try shorter chunks or increase timeout settings")
        lines.append("  → Check network connectivity")
    elif pattern == "CLIENT_ERROR":
        lines.append("  → Invalid request (4xx error)")
        lines.append("  → Check audio format, model name, or API parameters")
        if "model" in error_msg.lower() or "config" in error_msg.lower():
            lines.append("  → Model configuration issue - may need full resource path")
    elif pattern == "SERVER_ERROR":
        lines.append("  → Provider server error (5xx)")
        lines.append("  → Retry later or contact provider support")
    elif pattern == "CHUNKING_ERROR":
        lines.append("  → Failed to chunk audio file")
        lines.append("  → Check ffmpeg logs below for audio format issues")
    elif pattern == "FFMPEG_ERROR":
        lines.append("  → Failed to convert audio to WAV")
        lines.append("  → Check ffmpeg installation and audio file format")
    elif pattern == "FFMPEG_TIMEOUT":
        lines.append("  → ffmpeg conversion timed out")
        lines.append("  → Audio file may be too large or corrupted")

    # Verbose mode: show detailed metadata
    if verbose:
        lines.append(f"\n📊 Detailed Metadata:")

        # VAD stats
        vad = asr.get("vad", {})
        if vad:
            lines.append(f"  VAD:")
            lines.append(f"    Speech ratio: {vad.get('speech_ratio', 0):.2%}")
            lines.append(f"    Speech duration: {vad.get('speech_seconds', 0):.1f}s / {vad.get('total_seconds', 0):.1f}s")
            lines.append(f"    Mostly silence: {vad.get('is_mostly_silence', False)}")

        # ffmpeg logs
        ffmpeg_log = asr.get("ffmpeg_log_tail", "")
        if ffmpeg_log:
            lines.append(f"  ffmpeg log (last 500 chars):")
            for log_line in ffmpeg_log[-500:].splitlines():
                lines.append(f"    {log_line}")

        # Chunk details
        chunks = asr.get("chunks", [])
        if chunks:
            lines.append(f"  Chunks ({len(chunks)} total):")
            for i, chunk in enumerate(chunks[:5]):  # Show first 5
                status_icon = "✓" if chunk["status"] == "ok" else "✗"
                chunk_error = chunk.get("error", "")[:100] if chunk["status"] == "error" else ""
                lines.append(
                    f"    {status_icon} Chunk {i}: [{chunk.get('start_sec', 0):.1f}s - {chunk.get('end_sec', 0):.1f}s] "
                    f"{chunk['status']}"
                )
                if chunk_error:
                    lines.append(f"      Error: {chunk_error}")
            if len(chunks) > 5:
                lines.append(f"    ... ({len(chunks) - 5} more chunks)")

        # Cost
        cost = asr.get("cost", 0.0)
        if cost:
            lines.append(f"  Estimated cost: ${cost:.4f}")

    return "\n".join(lines)


def export_failures_csv(messages: list[dict], output_path: Path) -> None:
    """Export all failures to a CSV file."""
    failures = [msg for msg in messages if msg.get("kind") == "voice" and msg.get("status") == "failed"]

    with output_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=[
            "idx", "ts", "sender", "media_filename", "pattern", "provider", "model",
            "error_kind", "error_message", "chunks_ok", "chunks_error"
        ])
        writer.writeheader()

        for msg in failures:
            derived = msg.get("derived", {})
            asr = derived.get("asr", {})
            error_summary = asr.get("error_summary", {})
            media_filename = msg.get("media_filename", "")

            writer.writerow({
                "idx": msg.get("idx", ""),
                "ts": msg.get("ts", ""),
                "sender": msg.get("sender", ""),
                "media_filename": Path(media_filename).name if media_filename else "",
                "pattern": classify_error_pattern(msg),
                "provider": asr.get("provider", ""),
                "model": asr.get("model", ""),
                "error_kind": error_summary.get("last_error_kind", ""),
                "error_message": error_summary.get("last_error_message", "")[:500],
                "chunks_ok": error_summary.get("chunks_ok", 0),
                "chunks_error": error_summary.get("chunks_error", 0),
            })

    print(f"✅ Exported {len(failures)} failures to {output_path}")


def main():
    parser = argparse.ArgumentParser(
        description="Debug ASR transcription failures",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )
    parser.add_argument("run_id", help="Run ID (e.g., aymb-1)")
    parser.add_argument("--message-idx", type=int, help="Show specific message by index")
    parser.add_argument("--show-all-failures", action="store_true", help="Show all failed voice messages")
    parser.add_argument("--export-csv", type=Path, help="Export failures to CSV file")
    parser.add_argument("--verbose", "-v", action="store_true", help="Show detailed metadata")
    parser.add_argument("--root-dir", type=Path, help="Root directory (default: current directory)")

    args = parser.parse_args()

    # Load messages
    messages = load_messages(args.run_id, args.root_dir)

    # Export CSV mode
    if args.export_csv:
        export_failures_csv(messages, args.export_csv)
        return

    # Single message mode
    if args.message_idx is not None:
        msg = next((m for m in messages if m.get("idx") == args.message_idx), None)
        if not msg:
            print(f"❌ Message idx={args.message_idx} not found", file=sys.stderr)
            sys.exit(1)

        if msg.get("kind") != "voice":
            print(f"⚠️  Message idx={args.message_idx} is not a voice message (kind={msg.get('kind')})")
            sys.exit(0)

        print(format_error_summary(msg, verbose=args.verbose))
        return

    # Show all failures mode
    if args.show_all_failures:
        failures = [msg for msg in messages if msg.get("kind") == "voice" and msg.get("status") == "failed"]

        if not failures:
            print(f"✅ No voice message failures found in {args.run_id}")
            sys.exit(0)

        print(f"\n🔍 Found {len(failures)} failed voice message(s) in {args.run_id}")
        for msg in failures:
            print(format_error_summary(msg, verbose=args.verbose))
        return

    # Default: summary statistics
    voice_messages = [msg for msg in messages if msg.get("kind") == "voice"]
    failures = [msg for msg in voice_messages if msg.get("status") == "failed"]
    partials = [msg for msg in voice_messages if msg.get("status") == "partial"]
    successes = [msg for msg in voice_messages if msg.get("status") == "ok"]

    print(f"\n📊 ASR Summary for {args.run_id}")
    print(f"{'='*70}")
    print(f"Total voice messages: {len(voice_messages)}")
    print(f"  ✓ Success: {len(successes)}")
    print(f"  ⚠ Partial: {len(partials)}")
    print(f"  ✗ Failed: {len(failures)}")

    if failures:
        print(f"\n🔍 Failure breakdown:")
        patterns = {}
        for msg in failures:
            pattern = classify_error_pattern(msg)
            patterns[pattern] = patterns.get(pattern, 0) + 1

        for pattern, count in sorted(patterns.items(), key=lambda x: x[1], reverse=True):
            print(f"  {pattern}: {count}")

        print(f"\nℹ️  Run with --show-all-failures to see detailed diagnostics")
        print(f"ℹ️  Run with --message-idx <idx> to inspect a specific message")
        print(f"ℹ️  Run with --export-csv <file> to export to CSV")


if __name__ == "__main__":
    main()
