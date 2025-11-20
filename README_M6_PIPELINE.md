# ASR Pipeline Configuration

This document covers the ASR (Automatic Speech Recognition) provider configuration and error handling.

## Configuration

### Config File

ASR providers are configured in `config/asr.yaml`:

```yaml
default_provider: whisper_openai
providers:
  whisper_openai:
    model: whisper-1
    timeout_seconds: 30
    max_retries: 2
    billing: openai_whisper_v1
    env_key: OPENAI_API_KEY
    require_env: false
    default_language: auto

  google_stt:
    model: google-default
    timeout_seconds: 30
    max_retries: 2
    billing: google_stt_standard
    env_key: GOOGLE_APPLICATION_CREDENTIALS
    require_env: true
    default_language: auto
```

### Auto-Detect Backend

The system automatically selects the appropriate backend based on API key availability:

- **If API key is set in environment** → Uses real backend (e.g., `whisper_openai_real`)
- **If no API key** → Falls back to stub backend for testing

This means:
- Tests continue working without API keys (use stubs)
- Production automatically uses real APIs when keys are configured
- No manual `backend` field editing required

The system logs which backend was selected:
```
INFO:src.utils.asr:ASR: Using real backend 'whisper_openai_real' for 'whisper_openai' (API key found)
```
or
```
INFO:src.utils.asr:ASR: Using stub backend 'whisper_stub' for 'whisper_openai' (no API key)
```

### API Key Setup

The UI provides a secure way to store API keys using Windows Credential Manager:

1. Open the Streamlit UI
2. Expand the "🔑 API Keys" section
3. Enter your credentials:
   - **OpenAI**: Your API key (starts with `sk-...`)
   - **Google**: Path to your service account JSON file
4. Click "Save" - credentials are stored securely in Windows Credential Manager
5. Credentials persist across sessions and auto-load on startup

### Environment Variables

Alternatively, you can set credentials via environment variables:

| Provider | Required Variable | Description |
|----------|-------------------|-------------|
| Whisper (OpenAI) | `OPENAI_API_KEY` | Your OpenAI API key |
| Google STT | `GOOGLE_APPLICATION_CREDENTIALS` | Path to service account JSON file |

If credentials are saved in the UI, they automatically set these environment variables on startup.

## UI Provider Selection

The Streamlit UI displays user-friendly provider names and dynamically loads provider-specific options from `config/asr.yaml`:

| Display Name | Config Key |
|-------------|------------|
| Whisper (OpenAI) | `whisper_openai` |
| Whisper (Local) | `whisper_local` |
| Google Speech-to-Text | `google_stt` |

### Provider-Specific Options

When you select a provider, the UI shows relevant dropdowns:

**Whisper (OpenAI):**
- Model: `whisper-1`, `whisper-large-v3`
- Language: Auto detect, English, Arabic, Spanish

**Google Speech-to-Text:**
- Model: `chirp-3` (latest), `chirp-2`, `chirp-1`
- Language: Arabic (Egypt), Arabic (Saudi Arabia), English (US/UK), Spanish
- API Version: `v2` (recommended), `v1`

### Extending Languages

To add more languages, edit `config/asr.yaml`:

```yaml
google_stt:
  languages:
    - code: ar-EG
      label: Arabic (Egypt)
    - code: fr-FR
      label: French (France)
    # Add more BCP-47 codes as needed
```

## CLI Options

### Provider Selection

```bash
# Use specific provider
python -m src.pipeline.runner --asr-provider whisper_openai

# Use specific model
python -m src.pipeline.runner --asr-model whisper-1

# Set language hint
python -m src.pipeline.runner --asr-language ar
```

### Language Hints

Language hints use ISO-639-1 codes:

| Code | Language |
|------|----------|
| `auto` | Auto-detect (default) |
| `en` | English |
| `ar` | Arabic |
| `es` | Spanish |
| `fr` | French |
| `de` | German |
| `zh` | Chinese |

For Google STT, ISO codes are automatically converted to BCP-47 format (e.g., `ar` → `ar-SA`).

## Error Handling

### Error Kinds

The system classifies ASR errors into distinct kinds:

| Error Kind | Description | Retryable |
|------------|-------------|-----------|
| `timeout` | Request timed out | Yes |
| `auth` | Authentication failed (invalid API key) | No |
| `quota` | Rate limit or quota exceeded | No |
| `client` | Client error (bad request) | No |
| `server` | Server error (5xx) | Yes |
| `unknown` | Unclassified error | No |

### Status Reasons

Errors are mapped to `StatusReason` codes:

- **Timeout errors** → `timeout_asr`
- **All other errors** → `asr_failed`

### Error Summary

After transcription, each message includes an error summary in `derived["asr"]["error_summary"]`:

```json
{
  "chunks_ok": 5,
  "chunks_error": 1,
  "last_error_kind": "timeout",
  "last_error_message": "Request timeout after 30 seconds"
}
```

## Derived ASR Metadata

The `derived["asr"]` structure includes:

```json
{
  "pipeline_version": "m3.10",
  "provider": "whisper_openai",
  "model": "whisper-1",
  "language_hint": "ar",
  "billing_plan": "per_minute",
  "total_duration_seconds": 45.5,
  "chunks": [...],
  "error_summary": {
    "chunks_ok": 3,
    "chunks_error": 0,
    "last_error_kind": null,
    "last_error_message": null
  },
  "cost": 0.045
}
```

## Troubleshooting

### Missing API Key

```
AsrConfigError: Provider 'whisper_openai' requires environment variable 'OPENAI_API_KEY'
```

**Solution:** Set the required environment variable:
```bash
export OPENAI_API_KEY="your-key-here"
```

### Unknown Provider

```
AsrConfigError: Unknown ASR provider 'invalid_provider'
```

**Solution:** Use a valid provider name from `config/asr.yaml`.

### Package Not Installed

```
AsrConfigError: openai package not installed. Run: pip install openai
```

**Solution:** Install the required package:
```bash
pip install openai                    # For Whisper
pip install google-cloud-speech       # For Google STT
```

### Timeout Errors

If you're getting frequent timeouts:

1. Increase `timeout_seconds` in config
2. Check your network connection
3. Consider using smaller audio chunks

### Quota/Rate Limit

If you're hitting rate limits:

1. Reduce concurrent requests
2. Add delays between requests
3. Upgrade your API plan

## Testing

Run ASR-related tests:

```bash
# All ASR tests
pytest tests/test_asr*.py -v

# Specific test files
pytest tests/test_asr_provider_error_mapping.py -v
pytest tests/test_asr_language_hints_plumbing.py -v
pytest tests/test_asr_client_whisper.py -v
pytest tests/test_asr_client_google.py -v
```
