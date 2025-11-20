"""Tests for the launcher module."""

import sys
from pathlib import Path

import pytest


def test_launcher_module_imports():
    """Verify that the launcher module can be imported without errors."""
    # Add scripts to path for import
    scripts_dir = Path(__file__).parent.parent / "scripts"
    if str(scripts_dir) not in sys.path:
        sys.path.insert(0, str(scripts_dir))

    import launcher

    assert hasattr(launcher, "get_repo_root")
    assert hasattr(launcher, "get_venv_python")
    assert hasattr(launcher, "launch_streamlit")
    assert hasattr(launcher, "main")


def test_get_repo_root_returns_path():
    """Verify get_repo_root returns a valid Path object."""
    scripts_dir = Path(__file__).parent.parent / "scripts"
    if str(scripts_dir) not in sys.path:
        sys.path.insert(0, str(scripts_dir))

    from launcher import get_repo_root

    repo_root = get_repo_root()

    assert isinstance(repo_root, Path)
    assert repo_root.exists()
    assert repo_root.is_dir()


def test_get_repo_root_finds_markers():
    """Verify get_repo_root finds expected marker files."""
    scripts_dir = Path(__file__).parent.parent / "scripts"
    if str(scripts_dir) not in sys.path:
        sys.path.insert(0, str(scripts_dir))

    from launcher import get_repo_root

    repo_root = get_repo_root()

    # At least one of these markers should exist
    markers = [".git", "pyproject.toml", "AGENTS.md"]
    found = any((repo_root / marker).exists() for marker in markers)

    assert found, f"No marker files found in {repo_root}"


def test_get_repo_root_contains_scripts():
    """Verify get_repo_root returns directory containing scripts/."""
    scripts_dir = Path(__file__).parent.parent / "scripts"
    if str(scripts_dir) not in sys.path:
        sys.path.insert(0, str(scripts_dir))

    from launcher import get_repo_root

    repo_root = get_repo_root()

    assert (repo_root / "scripts").exists()
    assert (repo_root / "scripts" / "launcher.py").exists()


def test_get_venv_python_returns_string():
    """Verify get_venv_python returns a string path."""
    scripts_dir = Path(__file__).parent.parent / "scripts"
    if str(scripts_dir) not in sys.path:
        sys.path.insert(0, str(scripts_dir))

    from launcher import get_venv_python

    python_exe = get_venv_python()

    assert isinstance(python_exe, str)
    assert len(python_exe) > 0


def test_batch_file_exists():
    """Verify the batch launcher file exists."""
    repo_root = Path(__file__).parent.parent
    batch_file = repo_root / "scripts" / "WhatsAppTranscriberUI.bat"

    assert batch_file.exists(), f"Batch file not found at {batch_file}"


def test_batch_file_has_correct_content():
    """Verify the batch file contains expected content."""
    repo_root = Path(__file__).parent.parent
    batch_file = repo_root / "scripts" / "WhatsAppTranscriberUI.bat"

    content = batch_file.read_text()

    # Check for key elements
    assert "@echo off" in content
    assert "launcher.py" in content
    assert "PYTHON_EXE" in content
    assert "pause" in content.lower()
