# WhatsApp Transcriber UI

This document covers how to run and use the WhatsApp Transcriber UI.

## Quick Start

### Windows (Double-Click)

The easiest way to launch the UI on Windows:

1. Navigate to the `scripts/` folder
2. **Double-click** `WhatsAppTranscriberUI.bat`
3. A console window will open showing startup logs
4. Your default browser will open to the Streamlit UI

The console window remains open so you can see logs and debug any issues.

### Custom Python Path

To use a specific Python installation (e.g., Anaconda), edit the `PYTHON_BIN` variable at the top of `WhatsAppTranscriberUI.bat`:

```bat
set PYTHON_BIN=C:\Users\YourName\anaconda3\python.exe
```

The launcher checks this first before falling back to venv or system Python.

### Command Line

#### From the repository root:

```bash
# Using streamlit directly
streamlit run scripts/ui_app.py

# Or using the launcher script
python scripts/launcher.py
```

#### With a specific port:

```bash
streamlit run scripts/ui_app.py --server.port 8502
```

## Requirements

- Python 3.8+
- Streamlit (`pip install streamlit`)
- All project dependencies installed (`pip install -r requirements.txt`)

## Files

| File | Description |
|------|-------------|
| `scripts/ui_app.py` | Main Streamlit application |
| `scripts/launcher.py` | Python helper for robust path resolution |
| `scripts/WhatsAppTranscriberUI.bat` | Windows batch launcher |

## Troubleshooting

### "Python not found" error

Ensure Python is installed and in your PATH:

```cmd
python --version
```

Or create a virtualenv in the project root:

```cmd
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```

### "Streamlit not found" error

Install Streamlit:

```bash
pip install streamlit
```

### UI doesn't open in browser

Try opening manually: `http://localhost:8501`

Or run with explicit browser opening:

```bash
streamlit run scripts/ui_app.py --server.headless false
```

### Port already in use

Another instance may be running. Either:
- Close the other instance
- Use a different port: `--server.port 8502`

### Console window closes immediately

If the batch file closes without showing logs:
1. Open a command prompt manually
2. Navigate to the project root
3. Run: `python scripts/launcher.py`
4. Check the error message

## Logs

Streamlit logs appear in the console window. For more verbose output:

```bash
streamlit run scripts/ui_app.py --logger.level debug
```

## Configuration

The UI reads configuration from:
- `config/pipeline.yaml` - Pipeline settings
- `config/asr.yaml` - ASR provider settings (if exists)
- Environment variables for API keys

## Architecture

```
scripts/
  WhatsAppTranscriberUI.bat  # Windows entry point
         |
         v
  launcher.py                # Finds repo root, resolves Python
         |
         v
  ui_app.py                  # Streamlit application
```

The launcher provides robust path resolution regardless of:
- Current working directory when invoked
- Whether invoked from Explorer, CMD, or PowerShell
- Virtualenv vs system Python
