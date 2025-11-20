"""Tests for UI app imports and basic structure."""

from __future__ import annotations

import sys
from pathlib import Path
import os
from unittest.mock import patch, MagicMock

import pytest


class SessionState(dict):
    """Simple dict with attribute access to mimic Streamlit session state."""

    def __getattr__(self, item):
        return self[item]

    def __setattr__(self, key, value):
        self[key] = value


def _make_mock_streamlit():
    mock = MagicMock()
    mock.set_page_config = MagicMock()
    mock.title = MagicMock()
    mock.session_state = SessionState()

    def _columns(spec):
        count = spec if isinstance(spec, int) else len(spec)

        def _make_col():
            col = MagicMock()
            col.__enter__.return_value = None
            col.__exit__.return_value = False
            return col

        return tuple(_make_col() for _ in range(count))

    mock.columns.side_effect = _columns
    mock.header = MagicMock()
    mock.subheader = MagicMock()
    mock.divider = MagicMock()
    mock.metric = MagicMock()
    mock.caption = MagicMock()
    mock.table = MagicMock()
    mock.text_area = MagicMock()
    mock.json = MagicMock()
    mock.info = MagicMock()
    mock.warning = MagicMock()
    mock.error = MagicMock()
    mock.success = MagicMock()
    mock.rerun = MagicMock()

    class _Expander:
        def __enter__(self):
            return None

        def __exit__(self, exc_type, exc, tb):
            return False

    mock.expander.side_effect = lambda *args, **kwargs: _Expander()

    mock.button.side_effect = lambda *a, **k: False
    mock.text_input.side_effect = lambda label, value="", **k: value
    def _selectbox(label, options, **kwargs):
        opts = list(options) if not isinstance(options, list) else options
        return opts[0] if opts else None

    mock.selectbox.side_effect = _selectbox
    mock.checkbox.side_effect = lambda *a, **k: False
    mock.number_input.side_effect = lambda label, **k: k.get("min_value", 1)
    def _slider(label, *args, **kwargs):
        if "value" in kwargs:
            return kwargs["value"]
        if "min_value" in kwargs:
            return kwargs["min_value"]
        return 1

    mock.slider.side_effect = _slider

    return mock


def test_ui_app_imports_without_error(monkeypatch):
    """Importing ui_app should not raise errors."""
    mock_st = _make_mock_streamlit()
    with patch.dict(os.environ, {"STREAMLIT_DISABLE_AUTORUN": "1"}), patch.dict(sys.modules, {"streamlit": mock_st}):
        import importlib
        import scripts.ui_app as ui_app
        importlib.reload(ui_app)

        ui_app.main()

        assert mock_st.set_page_config.called
        assert mock_st.title.called


def test_status_module_imports():
    """Status helpers should import without error."""
    from src.pipeline.status import (
        RunSummary,
        StepStatus,
        list_runs,
        load_run_summary,
        load_transcript_preview,
    )

    # Verify classes and functions exist
    assert RunSummary is not None
    assert StepStatus is not None
    assert callable(list_runs)
    assert callable(load_run_summary)
    assert callable(load_transcript_preview)


def test_scan_chat_files_function(monkeypatch):
    """scan_chat_files should work for valid directories."""
    mock_st = _make_mock_streamlit()

    with patch.dict(os.environ, {"STREAMLIT_DISABLE_AUTORUN": "1"}), patch.dict(sys.modules, {"streamlit": mock_st}):
        import importlib
        import scripts.ui_app as ui_app
        importlib.reload(ui_app)

        # Test with non-existent directory
        result = ui_app.scan_chat_files("/nonexistent/path")
        assert result == []


def test_config_imports():
    """Pipeline config should import correctly."""
    from src.pipeline.config import PipelineConfig

    # Create minimal config
    cfg = PipelineConfig(root=Path("/tmp"))
    assert cfg.root == Path("/tmp").resolve()
    # Default provider may vary based on config
    assert cfg.asr_provider in ["whisper", "whisper_openai"]


def test_runner_imports():
    """Pipeline runner should import correctly."""
    from src.pipeline.runner import run_pipeline

    assert callable(run_pipeline)
