"""Secure credential storage using Windows Credential Manager.

This module provides functions to securely store and retrieve API keys
using the system keyring (Windows Credential Manager on Windows).
"""

from __future__ import annotations

import logging
import os
from typing import Optional

import keyring

logger = logging.getLogger(__name__)

# Service name for credential storage
SERVICE_NAME = "whatsapp-transcriber"

# Credential keys
OPENAI_KEY = "OPENAI_API_KEY"
GOOGLE_CREDENTIALS_KEY = "GOOGLE_APPLICATION_CREDENTIALS"


def _normalize_path(path: str) -> str:
    """Normalize a file path by stripping whitespace/quotes and expanding variables.

    Args:
        path: Raw path string (may contain quotes, spaces, env vars)

    Returns:
        Normalized absolute path
    """
    if not path:
        return ""
    # Strip whitespace and surrounding quotes (single or double)
    cleaned = path.strip().strip('"').strip("'").strip()
    # Expand environment variables (%VAR% on Windows, $VAR on Unix)
    cleaned = os.path.expandvars(cleaned)
    # Expand user home directory (~)
    cleaned = os.path.expanduser(cleaned)
    return cleaned


def save_credential(key_name: str, value: str) -> bool:
    """Save a credential to the system keyring.

    Args:
        key_name: The credential identifier (e.g., 'OPENAI_API_KEY')
        value: The credential value to store

    Returns:
        True if saved successfully, False otherwise

    Raises:
        ValueError: If value is empty
        RuntimeError: If keyring operation fails (wraps underlying exception)
    """
    if not value or not value.strip():
        raise ValueError(f"Credential value for {key_name} cannot be empty")

    try:
        keyring.set_password(SERVICE_NAME, key_name, value)
        logger.info(f"Saved credential: {key_name}")
        return True
    except Exception as e:
        logger.error(f"Failed to save credential {key_name}: {e}")
        raise RuntimeError(f"Keyring error for {key_name}: {e}") from e


def get_credential(key_name: str) -> Optional[str]:
    """Retrieve a credential from the system keyring.

    Args:
        key_name: The credential identifier

    Returns:
        The credential value, or None if not found
    """
    try:
        value = keyring.get_password(SERVICE_NAME, key_name)
        return value
    except Exception as e:
        logger.error(f"Failed to get credential {key_name}: {e}")
        return None


def delete_credential(key_name: str) -> bool:
    """Delete a credential from the system keyring.

    Args:
        key_name: The credential identifier

    Returns:
        True if deleted successfully, False otherwise
    """
    try:
        keyring.delete_password(SERVICE_NAME, key_name)
        logger.info(f"Deleted credential: {key_name}")
        return True
    except keyring.errors.PasswordDeleteError:
        # Credential doesn't exist, that's fine
        return True
    except Exception as e:
        logger.error(f"Failed to delete credential {key_name}: {e}")
        return False


def has_credential(key_name: str) -> bool:
    """Check if a credential exists in the system keyring.

    Args:
        key_name: The credential identifier

    Returns:
        True if the credential exists, False otherwise
    """
    return get_credential(key_name) is not None


def load_credentials_to_env() -> dict[str, bool]:
    """Load saved credentials into environment variables.

    This should be called at app startup to make credentials
    available to the ASR providers.

    Returns:
        Dictionary of credential names to whether they were loaded
    """
    results = {}

    for key_name in [OPENAI_KEY, GOOGLE_CREDENTIALS_KEY]:
        value = get_credential(key_name)
        if value:
            os.environ[key_name] = value
            results[key_name] = True
            logger.info(f"Loaded credential to env: {key_name}")
        else:
            results[key_name] = False

    return results


def save_openai_key(api_key: str) -> bool:
    """Save OpenAI API key to credential store.

    Args:
        api_key: The OpenAI API key

    Returns:
        True if saved successfully
    """
    return save_credential(OPENAI_KEY, api_key)


def get_openai_key() -> Optional[str]:
    """Get OpenAI API key from credential store.

    Returns:
        The API key, or None if not found
    """
    return get_credential(OPENAI_KEY)


def delete_openai_key() -> bool:
    """Delete OpenAI API key from credential store.

    Returns:
        True if deleted successfully
    """
    return delete_credential(OPENAI_KEY)


def save_google_credentials_path(path: str) -> str:
    """Save Google service account JSON path to credential store.

    Args:
        path: Path to the service account JSON file

    Returns:
        The normalized path that was saved

    Raises:
        ValueError: If path is empty
        FileNotFoundError: If the file doesn't exist at the normalized path
        RuntimeError: If keyring operation fails
    """
    normalized = _normalize_path(path)

    if not normalized:
        raise ValueError("Google credentials path cannot be empty")

    # Check file exists at the normalized path
    if not os.path.exists(normalized):
        raise FileNotFoundError(
            f"Google credentials file not found at: {normalized}\n"
            f"(Original input: {path})"
        )

    # Save the normalized path
    save_credential(GOOGLE_CREDENTIALS_KEY, normalized)
    return normalized


def get_google_credentials_path() -> Optional[str]:
    """Get Google service account JSON path from credential store.

    Returns:
        The path, or None if not found
    """
    return get_credential(GOOGLE_CREDENTIALS_KEY)


def delete_google_credentials_path() -> bool:
    """Delete Google credentials path from credential store.

    Returns:
        True if deleted successfully
    """
    return delete_credential(GOOGLE_CREDENTIALS_KEY)


def get_credential_status() -> dict[str, bool]:
    """Get the configuration status of all credentials.

    Returns:
        Dictionary mapping credential names to whether they are configured
    """
    return {
        OPENAI_KEY: has_credential(OPENAI_KEY),
        GOOGLE_CREDENTIALS_KEY: has_credential(GOOGLE_CREDENTIALS_KEY),
    }
