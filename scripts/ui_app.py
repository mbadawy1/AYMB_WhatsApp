#!/usr/bin/env python
"""Streamlit UI for WhatsApp transcript pipeline."""

from __future__ import annotations

import os
import sys
import threading
from pathlib import Path

# Bootstrap repo root for imports
repo_root = Path(__file__).resolve().parents[1]
if str(repo_root) not in sys.path:
    sys.path.insert(0, str(repo_root))

import streamlit as st

from src.pipeline.config import PipelineConfig
from src.pipeline.runner import run_pipeline
from src.pipeline.status import list_runs, load_run_summary, load_transcript_preview
from src.utils.asr import _load_asr_config
from src.utils.credentials import (
    load_credentials_to_env,
    save_openai_key,
    get_openai_key,
    delete_openai_key,
    save_google_credentials_path,
    get_google_credentials_path,
    delete_google_credentials_path,
    get_credential_status,
    OPENAI_KEY,
    GOOGLE_CREDENTIALS_KEY,
)


def get_provider_options(provider_key: str) -> dict:
    """Load provider-specific options from config/asr.yaml."""
    config = _load_asr_config()
    providers = config.get("providers", {})
    provider_cfg = providers.get(provider_key, {})

    return {
        "models": provider_cfg.get("available_models", []),
        "default_model": provider_cfg.get("model", ""),
        "languages": provider_cfg.get("languages", []),
        "default_language": provider_cfg.get("default_language", "auto"),
        "api_versions": provider_cfg.get("api_versions", []),
        "default_api_version": provider_cfg.get("default_api_version", ""),
    }


def scan_chat_files(export_folder: str) -> list[str]:
    """Find chat files in export folder."""
    folder = Path(export_folder)
    if not folder.exists():
        return []

    files = []
    # Look for common patterns
    for pattern in ["_chat.txt", "*.txt", "WhatsApp Chat*.txt"]:
        files.extend(folder.glob(pattern))

    # Deduplicate and sort
    unique = sorted(set(str(f) for f in files if f.is_file()))
    return unique


def run_pipeline_background(cfg: PipelineConfig):
    """Run pipeline in background thread."""
    try:
        st.session_state.running = True
        run_pipeline(cfg)
    except Exception as e:
        st.error(f"Pipeline failed: {e}")
    finally:
        st.session_state.running = False


def main() -> None:
    """Render the Streamlit UI."""
    # Page config
    st.set_page_config(
        page_title="WhatsApp Transcriber",
        page_icon="💬",
        layout="wide",
    )

    st.title("WhatsApp Transcriber")

    # Initialize session state
    if "selected_run" not in st.session_state:
        st.session_state.selected_run = None
    if "chat_files" not in st.session_state:
        st.session_state.chat_files = []
    if "running" not in st.session_state:
        st.session_state.running = False
    if "credentials_loaded" not in st.session_state:
        # Load saved credentials into environment on first run
        load_credentials_to_env()
        st.session_state.credentials_loaded = True

    # Layout: two columns
    left_col, right_col = st.columns([1, 2])

    # ============================================
    # LEFT COLUMN: Configuration
    # ============================================
    with left_col:
        st.header("Configuration")

        # API Keys section (expandable)
        with st.expander("🔑 API Keys", expanded=False):
            # Show which Python is running (helps debug keyring issues)
            st.caption(f"Python: `{sys.executable}`")
            st.info("✨ Auto-reload test: If you see this message, the auto-reload feature is working!")
            st.divider()

            cred_status = get_credential_status()

            # OpenAI API Key
            st.subheader("OpenAI (Whisper)")
            openai_status = "✓ Configured" if cred_status[OPENAI_KEY] else "✗ Not set"
            st.caption(f"Status: {openai_status}")

            openai_key_input = st.text_input(
                "API Key",
                type="password",
                placeholder="sk-...",
                key="openai_key_input",
                help="Your OpenAI API key for Whisper transcription",
            )

            col1, col2 = st.columns(2)
            with col1:
                if st.button("Save", key="save_openai"):
                    if openai_key_input:
                        try:
                            save_openai_key(openai_key_input)
                            os.environ[OPENAI_KEY] = openai_key_input
                            st.success("✓ OpenAI key saved to Windows Credential Manager")
                            st.rerun()
                        except ValueError as e:
                            st.error(f"Invalid input: {e}")
                        except RuntimeError as e:
                            st.error(f"Keyring error: {e}")
                        except Exception as e:
                            st.error(f"Failed to save: {e}")
                    else:
                        st.warning("Enter a key first")
            with col2:
                if st.button("Clear", key="clear_openai"):
                    if delete_openai_key():
                        if OPENAI_KEY in os.environ:
                            del os.environ[OPENAI_KEY]
                        st.success("Cleared!")
                        st.rerun()

            st.divider()

            # Google Credentials
            st.subheader("Google (Speech-to-Text)")
            google_status = "✓ Configured" if cred_status[GOOGLE_CREDENTIALS_KEY] else "✗ Not set"
            st.caption(f"Status: {google_status}")

            # Show current path if configured
            current_google_path = get_google_credentials_path()
            if current_google_path:
                st.caption(f"Current: `{current_google_path}`")

            google_path_input = st.text_input(
                "Service Account JSON Path",
                placeholder="C:/Users/Dell/Documents/file.json",
                key="google_path_input",
                help="Windows path to your Google Cloud service account JSON file. Use forward slashes (/) or double backslashes (\\\\).",
            )

            col3, col4 = st.columns(2)
            with col3:
                if st.button("Save", key="save_google"):
                    if google_path_input:
                        try:
                            # save_google_credentials_path now does normalization and validation
                            normalized_path = save_google_credentials_path(google_path_input)
                            os.environ[GOOGLE_CREDENTIALS_KEY] = normalized_path
                            st.success(f"✓ Saved credentials path:\n`{normalized_path}`")
                            st.rerun()
                        except ValueError as e:
                            st.error(f"Invalid input: {e}")
                        except FileNotFoundError as e:
                            st.error(f"File not found:\n{e}")
                        except RuntimeError as e:
                            st.error(f"Keyring error: {e}")
                        except Exception as e:
                            st.error(f"Failed to save: {e}")
                    else:
                        st.warning("Enter a path first")
            with col4:
                if st.button("Clear", key="clear_google"):
                    if delete_google_credentials_path():
                        if GOOGLE_CREDENTIALS_KEY in os.environ:
                            del os.environ[GOOGLE_CREDENTIALS_KEY]
                        st.success("Cleared!")
                        st.rerun()

        st.divider()

    # Export folder
    export_folder = st.text_input(
        "Export Folder",
        value=str(repo_root),
        help="Path to WhatsApp export folder containing chat files",
    )

    # Scan button
    if st.button("📂 Scan for Chat Files"):
        st.session_state.chat_files = scan_chat_files(export_folder)
        if st.session_state.chat_files:
            st.success(f"Found {len(st.session_state.chat_files)} chat file(s)")
        else:
            st.warning("No chat files found")

    # Chat file dropdown
    chat_file = st.selectbox(
        "Chat File",
        options=st.session_state.chat_files or ["(scan folder first)"],
        help="Select the chat export file to process",
    )

    st.divider()

    # ASR provider - user-friendly names mapped to config keys
    ASR_PROVIDER_DISPLAY = {
        "Whisper (OpenAI)": "whisper_openai",
        "Whisper (Local)": "whisper_local",
        "Google Speech-to-Text": "google_stt",
    }
    asr_provider_display = st.selectbox(
        "ASR Provider",
        options=list(ASR_PROVIDER_DISPLAY.keys()),
        help="Speech-to-text provider for voice messages",
    )
    asr_provider = ASR_PROVIDER_DISPLAY[asr_provider_display]

    # Load provider-specific options
    provider_opts = get_provider_options(asr_provider)

    # ASR model dropdown (provider-specific)
    asr_model = None
    if provider_opts["models"]:
        default_idx = 0
        if provider_opts["default_model"] in provider_opts["models"]:
            default_idx = provider_opts["models"].index(provider_opts["default_model"])
        asr_model = st.selectbox(
            "Model",
            options=provider_opts["models"],
            index=default_idx,
            help="Transcription model to use",
        )

    # ASR language dropdown (provider-specific)
    asr_language = None
    if provider_opts["languages"]:
        # Build display labels and codes
        lang_labels = [lang["label"] for lang in provider_opts["languages"]]
        lang_codes = [lang["code"] for lang in provider_opts["languages"]]

        # Find default index
        default_idx = 0
        if provider_opts["default_language"] in lang_codes:
            default_idx = lang_codes.index(provider_opts["default_language"])

        selected_label = st.selectbox(
            "Language",
            options=lang_labels,
            index=default_idx,
            help="Language of the audio content",
        )
        asr_language = lang_codes[lang_labels.index(selected_label)]

    # API version dropdown (Google only)
    asr_api_version = None
    if provider_opts["api_versions"]:
        default_idx = 0
        if provider_opts["default_api_version"] in provider_opts["api_versions"]:
            default_idx = provider_opts["api_versions"].index(provider_opts["default_api_version"])
        asr_api_version = st.selectbox(
            "API Version",
            options=provider_opts["api_versions"],
            index=default_idx,
            help="API version to use (v2 recommended for latest features)",
        )

    st.divider()

    # Sample mode
    sample_mode = st.checkbox("Sample Mode", help="Limit messages for testing")
    sample_limit = None
    if sample_mode:
        sample_limit = st.number_input(
            "Message Limit",
            min_value=1,
            max_value=10000,
            value=100,
            help="Maximum messages to process",
        )

    # Max workers
    max_workers = st.slider(
        "Audio Workers",
        min_value=1,
        max_value=8,
        value=4,
        help="Concurrent audio transcription workers",
    )

    st.divider()

    # Run button
    run_disabled = (
        st.session_state.running
        or not chat_file
        or chat_file == "(scan folder first)"
    )

    if st.button("▶️ Run Pipeline", disabled=run_disabled, type="primary"):
        # Build config
        cfg = PipelineConfig(
            root=Path(export_folder),
            chat_file=Path(chat_file) if chat_file else None,
            asr_provider=asr_provider,
            asr_model=asr_model if asr_model else None,
            asr_language=asr_language if asr_language else None,
            asr_api_version=asr_api_version if asr_api_version else None,
            sample_limit=sample_limit,
            max_workers_audio=max_workers,
        )

        # Launch in background
        thread = threading.Thread(target=run_pipeline_background, args=(cfg,))
        thread.start()
        st.info("Pipeline started! Check runs table for progress.")
        st.rerun()

    if st.session_state.running:
        st.warning("⏳ Pipeline running...")

    # ============================================
    # RIGHT COLUMN: Runs & Details
    # ============================================
    with right_col:
        st.header("Runs")

    # Refresh button
    if st.button("🔄 Refresh"):
        st.rerun()

    # List runs
    try:
        runs = list_runs(export_folder)
    except Exception as e:
        st.error(f"Failed to list runs: {e}")
        runs = []

    if not runs:
        st.info("No runs found. Configure and run the pipeline to get started.")
    else:
        # Runs table
        run_options = [f"{r.run_id} ({r.status})" for r in runs]
        selected_idx = st.selectbox(
            "Select Run",
            options=range(len(run_options)),
            format_func=lambda i: run_options[i],
        )

        if selected_idx is not None:
            selected_run = runs[selected_idx]
            st.session_state.selected_run = selected_run.run_dir

            # Run overview
            st.subheader(f"Run: {selected_run.run_id}")

            # Status badge
            status_colors = {
                "ok": "🟢",
                "failed": "🔴",
                "running": "🟡",
                "pending": "⚪",
            }
            status_icon = status_colors.get(selected_run.status, "⚪")

            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("Status", f"{status_icon} {selected_run.status}")
                st.metric("Messages", selected_run.messages_total)
            with col2:
                st.metric("Voice Notes", selected_run.voice_total)
                st.metric("Audio (sec)", f"{selected_run.audio_seconds:.1f}")
            with col3:
                st.metric("ASR Cost", f"${selected_run.asr_cost_usd:.2f}")
                st.metric("Voice OK", f"{selected_run.voice_ok}/{selected_run.voice_total}")

            # Error display
            if selected_run.error:
                st.error(f"Error: {selected_run.error}")

            # Steps table
            st.subheader("Pipeline Steps")
            steps_data = []
            for step in selected_run.steps:
                steps_data.append({
                    "Step": step.name,
                    "Status": step.status,
                    "Progress": f"{step.done}/{step.total}",
                    "Started": step.started_at or "-",
                    "Ended": step.ended_at or "-",
                })
            st.table(steps_data)

            # Transcript preview
            st.subheader("Transcript Preview")
            preview_lines = load_transcript_preview(selected_run.run_dir)
            if preview_lines:
                # Show in scrollable text area
                preview_text = "\n".join(preview_lines[:100])  # Limit to 100 lines
                st.text_area(
                    "Preview",
                    value=preview_text,
                    height=300,
                    disabled=True,
                    label_visibility="collapsed",
                )
                if len(preview_lines) > 100:
                    st.caption(f"Showing 100 of {len(preview_lines)} lines")
            else:
                st.info("No transcript preview available")

            # Run metadata
            with st.expander("Run Details"):
                st.json({
                    "run_dir": selected_run.run_dir,
                    "root": selected_run.root,
                    "chat_file": selected_run.chat_file,
                    "start_time": selected_run.start_time,
                    "end_time": selected_run.end_time,
                })


if os.environ.get("STREAMLIT_DISABLE_AUTORUN") != "1":
    main()
