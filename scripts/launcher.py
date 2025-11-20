#!/usr/bin/env python3
"""
Windows launcher helper for WhatsApp Transcriber UI.

Provides robust path resolution and Streamlit startup,
regardless of how the batch file is invoked.
"""

import os
import sys
import subprocess
from pathlib import Path


def get_repo_root() -> Path:
    """
    Find the repository root by looking for marker files.

    Searches upward from this script's location for common repo markers
    (.git, pyproject.toml, AGENTS.md) to robustly determine the root.

    Returns:
        Path to the repository root directory.

    Raises:
        FileNotFoundError: If repo root cannot be determined.
    """
    # Start from this script's directory
    current = Path(__file__).resolve().parent

    # Markers that indicate repo root
    markers = [".git", "pyproject.toml", "AGENTS.md"]

    # Search upward
    for _ in range(10):  # Limit search depth
        for marker in markers:
            if (current / marker).exists():
                return current

        parent = current.parent
        if parent == current:
            # Reached filesystem root
            break
        current = parent

    raise FileNotFoundError(
        "Could not find repository root. "
        "Ensure the script is located within the project directory."
    )


def get_venv_python() -> str:
    """
    Get the path to the virtualenv Python executable if available.

    Checks common virtualenv locations relative to the repo root.
    Falls back to system Python if no venv is found.

    Returns:
        Path to Python executable.
    """
    repo_root = get_repo_root()

    # Common virtualenv locations
    venv_paths = [
        repo_root / "venv" / "Scripts" / "python.exe",  # Windows venv
        repo_root / ".venv" / "Scripts" / "python.exe",  # Windows .venv
        repo_root / "venv" / "bin" / "python",  # Unix venv
        repo_root / ".venv" / "bin" / "python",  # Unix .venv
    ]

    for venv_python in venv_paths:
        if venv_python.exists():
            return str(venv_python)

    # Fall back to system Python
    return sys.executable


def launch_streamlit() -> int:
    """
    Launch the Streamlit UI application.

    Changes to the repo root directory and starts the Streamlit server.

    Returns:
        Exit code from the Streamlit process.
    """
    repo_root = get_repo_root()
    ui_script = repo_root / "scripts" / "ui_app.py"

    if not ui_script.exists():
        print(f"Error: UI script not found at {ui_script}", file=sys.stderr)
        return 1

    # Change to repo root for correct relative paths
    os.chdir(repo_root)

    python_exe = get_venv_python()

    # Build the command
    cmd = [
        python_exe,
        "-m", "streamlit",
        "run",
        str(ui_script),
        "--server.headless", "false",  # Open browser automatically
        "--server.runOnSave", "true",  # Auto-reload when files change
        "--server.fileWatcherType", "auto",  # Use filesystem watcher
    ]

    print(f"Starting WhatsApp Transcriber UI...")
    print(f"Working directory: {repo_root}")
    print(f"Python: {python_exe}")
    print(f"Command: {' '.join(cmd)}")
    print("-" * 50)

    try:
        # Run Streamlit, inheriting stdin/stdout/stderr for logs
        result = subprocess.run(cmd)
        return result.returncode
    except KeyboardInterrupt:
        print("\nShutting down...")
        return 0
    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        print("Make sure Streamlit is installed: pip install streamlit", file=sys.stderr)
        return 1


def main() -> int:
    """Main entry point for the launcher."""
    return launch_streamlit()


if __name__ == "__main__":
    sys.exit(main())
