"""Timestamp detection and parsing for WhatsApp chat exports.

Auto-detects timestamp format (12h/24h, EN/AR locales) and parses to ISO 8601.
Implements deterministic scoring with early-line weighting.
"""

import re
from datetime import datetime
from typing import Any, Optional

# Unicode whitespace variants commonly observed in WhatsApp exports.
UNICODE_SPACE_MAP = {
    "\u202f": " ",  # narrow no-break space
    "\u00a0": " ",  # non-breaking space
    "\u200f": "",  # RTL mark (remove)
}


def _normalize_whitespace(text: str) -> str:
    """Replace WhatsApp-specific unicode spaces/marks with ASCII equivalents."""
    for src, replacement in UNICODE_SPACE_MAP.items():
        text = text.replace(src, replacement)
    return text


def normalize_timestamp_text(text: str) -> str:
    """Public helper to normalize timestamp-containing strings."""
    return _normalize_whitespace(text)


# Format candidates include both month-first (US) and day-first (intl) layouts.
# Order matters: AM/PM variants checked first to avoid false positives.
FORMAT_CANDIDATES = [
    {
        "name": "12h_EN",
        "regex": re.compile(r"(\d{1,2}/\d{1,2}/\d{2,4}, \d{1,2}:\d{2} [AP]M)"),
        "strptime_patterns": ["%m/%d/%y, %I:%M %p", "%m/%d/%Y, %I:%M %p"],
    },
    {
        "name": "12h_EN_alt",
        "regex": re.compile(r"(\d{1,2}/\d{1,2}/\d{2,4}, \d{1,2}:\d{2}:\d{2} [AP]M)"),
        "strptime_patterns": ["%m/%d/%y, %I:%M:%S %p", "%m/%d/%Y, %I:%M:%S %p"],
    },
    {
        "name": "12h_DMY",
        "regex": re.compile(r"(\d{1,2}/\d{1,2}/\d{2,4}, \d{1,2}:\d{2} [AP]M)"),
        "strptime_patterns": ["%d/%m/%y, %I:%M %p", "%d/%m/%Y, %I:%M %p"],
    },
    {
        "name": "12h_DMY_alt",
        "regex": re.compile(r"(\d{1,2}/\d{1,2}/\d{2,4}, \d{1,2}:\d{2}:\d{2} [AP]M)"),
        "strptime_patterns": ["%d/%m/%y, %I:%M:%S %p", "%d/%m/%Y, %I:%M:%S %p"],
    },
    {
        "name": "24h_EN",
        "regex": re.compile(r"(\d{1,2}/\d{1,2}/\d{2,4}, \d{1,2}:\d{2})(?! [AP]M)"),
        "strptime_patterns": ["%m/%d/%y, %H:%M", "%m/%d/%Y, %H:%M"],
    },
    {
        "name": "24h_EN_alt",
        "regex": re.compile(r"(\d{1,2}/\d{1,2}/\d{2,4}, \d{2}:\d{2}:\d{2})(?! [AP]M)"),
        "strptime_patterns": ["%m/%d/%y, %H:%M:%S", "%m/%d/%Y, %H:%M:%S"],
    },
    {
        "name": "24h_DMY",
        "regex": re.compile(r"(\d{1,2}/\d{1,2}/\d{2,4}, \d{1,2}:\d{2})(?! [AP]M)"),
        "strptime_patterns": ["%d/%m/%y, %H:%M", "%d/%m/%Y, %H:%M"],
    },
    {
        "name": "24h_DMY_alt",
        "regex": re.compile(r"(\d{1,2}/\d{1,2}/\d{2,4}, \d{2}:\d{2}:\d{2})(?! [AP]M)"),
        "strptime_patterns": ["%d/%m/%y, %H:%M:%S", "%d/%m/%Y, %H:%M:%S"],
    },
]


def _match_strptime_pattern(ts_fragment: str, patterns: list[str]) -> Optional[str]:
    """Return first strptime pattern that successfully parses fragment."""
    for pattern in patterns:
        try:
            datetime.strptime(ts_fragment.strip(), pattern)
            return pattern
        except ValueError:
            continue
    return None


def detect_datetime_format(lines: list[str]) -> dict[str, Any]:
    """Auto-detect WhatsApp timestamp format from sample lines.

    Analyzes first ~200 non-empty lines, scores regex candidates with
    early-line weighting, and returns the winning format.

    Args:
        lines: List of lines from WhatsApp chat export (typically first 200)

    Returns:
        Format dictionary with keys:
            - regex: Compiled regex pattern for timestamp matching
            - strptime_pattern: Python datetime format string
            - tz_placeholder: Timezone info (currently None)
            - name: Format name (e.g., "24h_EN", "12h_EN")

    Raises:
        ValueError: If no format candidates match any lines
    """
    # Sample first 200 non-empty lines
    sample_lines = [_normalize_whitespace(line.strip()) for line in lines if line.strip()][:200]

    if not sample_lines:
        raise ValueError("No non-empty lines provided for format detection")

    # Score each candidate
    candidate_scores: dict[str, float] = {}
    candidate_patterns: dict[str, str] = {}

    for candidate in FORMAT_CANDIDATES:
        name = candidate["name"]
        regex = candidate["regex"]
        strptime_patterns = candidate["strptime_patterns"]
        score = 0.0
        pattern_hits: dict[str, float] = {}

        for idx, line in enumerate(sample_lines):
            match = regex.search(line)
            if not match:
                continue

            timestamp_fragment = match.group(1)
            selected_pattern = _match_strptime_pattern(timestamp_fragment, strptime_patterns)
            if not selected_pattern:
                continue

            weight = 2.0 if idx < 50 else 1.0
            score += weight
            pattern_hits[selected_pattern] = pattern_hits.get(selected_pattern, 0.0) + weight

        candidate_scores[name] = score
        candidate_patterns[name] = (
            max(pattern_hits, key=pattern_hits.get) if pattern_hits else strptime_patterns[0]
        )

    # Find winner (highest score)
    winner_name = max(candidate_scores, key=candidate_scores.get)
    winner_score = candidate_scores[winner_name]

    if winner_score == 0:
        raise ValueError("No timestamp format detected. Ensure lines contain WhatsApp timestamps.")

    # Build format dict for winner
    winner_candidate = next(candidate for candidate in FORMAT_CANDIDATES if candidate["name"] == winner_name)
    strptime_fmt = candidate_patterns[winner_name]

    return {
        "name": winner_name,
        "regex": winner_candidate["regex"],
        "strptime_pattern": strptime_fmt,
        "tz_placeholder": None,  # Future: timezone handling
    }


def parse_ts(s: str, fmt: dict[str, Any]) -> str:
    """Parse timestamp string to ISO 8601 format.

    Args:
        s: Timestamp string to parse (e.g., "7/8/25, 14:23")
        fmt: Format dictionary from detect_datetime_format()

    Returns:
        ISO 8601 timestamp string: "YYYY-MM-DDTHH:MM:SS"

    Raises:
        ValueError: If timestamp cannot be parsed with the given format
    """
    strptime_pattern = fmt["strptime_pattern"]

    normalized = _normalize_whitespace(s.strip())

    try:
        dt = datetime.strptime(normalized, strptime_pattern)
        # Return ISO 8601 format
        return dt.strftime("%Y-%m-%dT%H:%M:%S")
    except ValueError as e:
        raise ValueError(
            f"Failed to parse timestamp '{s}' with pattern '{strptime_pattern}': {e}"
        ) from e
