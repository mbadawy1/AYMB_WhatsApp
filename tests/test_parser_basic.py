"""Tests for basic WhatsApp timestamp detection and parsing.

Validates M1.2 functionality:
- Auto-detection of 24h/12h formats
- Correct ISO 8601 parsing
- Deterministic behavior
- Edge case handling
"""

from pathlib import Path

import pytest

from src.parser_agent import ParserAgent
from src.schema.message import Message
from src.utils.dates import detect_datetime_format, parse_ts


@pytest.fixture
def header_lines():
    """Load header cases fixture."""
    fixture_path = Path(__file__).parent / "fixtures/text_only/header_cases.txt"
    with open(fixture_path, encoding="utf-8") as f:
        return f.readlines()


@pytest.fixture
def multiline_lines():
    """Load multiline cases fixture."""
    fixture_path = Path(__file__).parent / "fixtures/text_only/multiline.txt"
    with open(fixture_path, encoding="utf-8") as f:
        return f.readlines()


@pytest.fixture
def kind_lines():
    """Load kind detection fixture."""
    fixture_path = Path(__file__).parent / "fixtures/text_only/kinds.txt"
    with open(fixture_path, encoding="utf-8") as f:
        return [line.strip() for line in f.readlines()]


@pytest.fixture
def caption_lines():
    """Load caption merge fixture."""
    fixture_path = Path(__file__).parent / "fixtures/text_only/caption_merge.txt"
    with open(fixture_path, encoding="utf-8") as f:
        return f.readlines()


@pytest.fixture
def system_lines():
    """Load system lines fixture."""
    fixture_path = Path(__file__).parent / "fixtures/text_only/system_lines.txt"
    with open(fixture_path, encoding="utf-8") as f:
        return f.readlines()


class TestDatetimeFormatDetection:
    """Tests for detect_datetime_format function."""

    @pytest.fixture
    def sample_24h_lines(self):
        """Load sample 24h format chat file."""
        fixture_path = Path(__file__).parent / "fixtures/text_only/sample_24h.txt"
        with open(fixture_path, encoding="utf-8") as f:
            return f.readlines()

    @pytest.fixture
    def sample_12h_lines(self):
        """Load sample 12h format chat file."""
        fixture_path = Path(__file__).parent / "fixtures/text_only/sample_12h.txt"
        with open(fixture_path, encoding="utf-8") as f:
            return f.readlines()

    def test_detect_datetime_format_24h(self, sample_24h_lines):
        """Test detection of 24-hour timestamp format."""
        fmt = detect_datetime_format(sample_24h_lines)

        # Verify correct format detected
        assert fmt["name"] == "24h_EN"
        assert fmt["regex"] is not None
        assert fmt["strptime_pattern"] == "%m/%d/%y, %H:%M"
        assert "regex" in fmt
        assert "strptime_pattern" in fmt
        assert "tz_placeholder" in fmt

        # Verify we can parse a timestamp from the file
        sample_ts = "7/8/25, 14:23"
        parsed = parse_ts(sample_ts, fmt)
        assert parsed == "2025-07-08T14:23:00"

    def test_detect_datetime_format_12h(self, sample_12h_lines):
        """Test detection of 12-hour (AM/PM) timestamp format."""
        fmt = detect_datetime_format(sample_12h_lines)

        # Verify correct format detected
        assert fmt["name"] == "12h_EN"
        assert fmt["regex"] is not None
        assert fmt["strptime_pattern"] == "%m/%d/%y, %I:%M %p"
        assert "regex" in fmt
        assert "strptime_pattern" in fmt
        assert "tz_placeholder" in fmt

        # Verify we can parse a timestamp from the file
        sample_ts = "7/8/25, 2:23 PM"
        parsed = parse_ts(sample_ts, fmt)
        assert parsed == "2025-07-08T14:23:00"

    def test_detect_deterministic(self, sample_24h_lines):
        """Test that detection is deterministic (same input = same output)."""
        fmt1 = detect_datetime_format(sample_24h_lines)
        fmt2 = detect_datetime_format(sample_24h_lines)

        assert fmt1["name"] == fmt2["name"]
        assert fmt1["strptime_pattern"] == fmt2["strptime_pattern"]

    def test_detect_empty_lines_ignored(self):
        """Test that empty lines are ignored during detection."""
        lines = [
            "",
            "  ",
            "7/8/25, 14:23 - Alice: Hello",
            "",
            "7/8/25, 14:24 - Bob: Hi",
            "  ",
        ]
        fmt = detect_datetime_format(lines)
        assert fmt["name"] in ["24h_EN", "24h_EN_alt"]

    def test_detect_no_matches_raises(self):
        """Test that ValueError is raised when no formats match."""
        lines = [
            "This is not a WhatsApp message",
            "No timestamps here",
            "Just random text",
        ]
        with pytest.raises(ValueError, match="No timestamp format detected"):
            detect_datetime_format(lines)

    def test_detect_empty_input_raises(self):
        """Test that ValueError is raised for empty input."""
        with pytest.raises(ValueError, match="No non-empty lines"):
            detect_datetime_format([])

        with pytest.raises(ValueError, match="No non-empty lines"):
            detect_datetime_format(["", "  ", "\n"])

    def test_detect_handles_narrow_nbsp(self):
        """Ensure detection works when timestamps include narrow spaces."""
        lines = [
            "7/7/25, 1:37\u202fPM - Alice: Hello there",
            "7/7/25, 1:38\u202fPM - Bob: Hi!",
        ]
        fmt = detect_datetime_format(lines)

        assert fmt["name"].startswith("12h")
        parsed = parse_ts("7/7/25, 1:37\u202fPM", fmt)
        assert parsed == "2025-07-07T13:37:00"


class TestTimestampParsing:
    """Tests for parse_ts function."""

    def test_parse_24h_format(self):
        """Test parsing 24-hour format timestamps."""
        fmt = {
            "name": "24h_EN",
            "regex": None,
            "strptime_pattern": "%m/%d/%y, %H:%M",
            "tz_placeholder": None,
        }

        assert parse_ts("7/8/25, 14:23", fmt) == "2025-07-08T14:23:00"
        assert parse_ts("1/1/25, 00:00", fmt) == "2025-01-01T00:00:00"
        assert parse_ts("12/31/25, 23:59", fmt) == "2025-12-31T23:59:00"

    def test_parse_12h_format(self):
        """Test parsing 12-hour (AM/PM) format timestamps."""
        fmt = {
            "name": "12h_EN",
            "regex": None,
            "strptime_pattern": "%m/%d/%y, %I:%M %p",
            "tz_placeholder": None,
        }

        assert parse_ts("7/8/25, 2:23 PM", fmt) == "2025-07-08T14:23:00"
        assert parse_ts("7/8/25, 2:23 AM", fmt) == "2025-07-08T02:23:00"
        assert parse_ts("1/1/25, 12:00 AM", fmt) == "2025-01-01T00:00:00"
        assert parse_ts("12/31/25, 11:59 PM", fmt) == "2025-12-31T23:59:00"

    def test_parse_with_seconds(self):
        """Test parsing timestamps with seconds."""
        fmt = {
            "name": "24h_EN_alt",
            "regex": None,
            "strptime_pattern": "%m/%d/%y, %H:%M:%S",
            "tz_placeholder": None,
        }

        assert parse_ts("7/8/25, 14:23:45", fmt) == "2025-07-08T14:23:45"

    def test_parse_deterministic(self):
        """Test that parsing is deterministic."""
        fmt = {
            "name": "24h_EN",
            "regex": None,
            "strptime_pattern": "%m/%d/%y, %H:%M",
            "tz_placeholder": None,
        }

        ts = "7/8/25, 14:23"
        result1 = parse_ts(ts, fmt)
        result2 = parse_ts(ts, fmt)
        assert result1 == result2

    def test_parse_invalid_timestamp_raises(self):
        """Test that ValueError is raised for invalid timestamps."""
        fmt = {
            "name": "24h_EN",
            "regex": None,
            "strptime_pattern": "%m/%d/%y, %H:%M",
            "tz_placeholder": None,
        }

        with pytest.raises(ValueError, match="Failed to parse timestamp"):
            parse_ts("not a timestamp", fmt)

        with pytest.raises(ValueError, match="Failed to parse timestamp"):
            parse_ts("13/45/99, 99:99", fmt)

    def test_parse_whitespace_handling(self):
        """Test that whitespace is handled correctly."""
        fmt = {
            "name": "24h_EN",
            "regex": None,
            "strptime_pattern": "%m/%d/%y, %H:%M",
            "tz_placeholder": None,
        }

        # Leading/trailing whitespace should be stripped
        assert parse_ts("  7/8/25, 14:23  ", fmt) == "2025-07-08T14:23:00"


class TestIntegration:
    """Integration tests combining detection and parsing."""

    def test_end_to_end_24h(self):
        """Test full workflow: detect format, parse multiple timestamps (24h)."""
        lines = [
            "7/8/25, 14:23 - Alice: Hello",
            "7/8/25, 14:24 - Bob: Hi",
            "7/8/25, 15:00 - Alice: How are you?",
        ]

        fmt = detect_datetime_format(lines)
        assert fmt["name"] == "24h_EN"

        # Parse all timestamps
        timestamps = ["7/8/25, 14:23", "7/8/25, 14:24", "7/8/25, 15:00"]
        parsed = [parse_ts(ts, fmt) for ts in timestamps]

        assert parsed == [
            "2025-07-08T14:23:00",
            "2025-07-08T14:24:00",
            "2025-07-08T15:00:00",
        ]

    def test_end_to_end_12h(self):
        """Test full workflow: detect format, parse multiple timestamps (12h)."""
        lines = [
            "7/8/25, 2:23 PM - Alice: Hello",
            "7/8/25, 2:24 PM - Bob: Hi",
            "7/8/25, 3:00 PM - Alice: How are you?",
        ]

        fmt = detect_datetime_format(lines)
        assert fmt["name"] == "12h_EN"

        # Parse all timestamps
        timestamps = ["7/8/25, 2:23 PM", "7/8/25, 2:24 PM", "7/8/25, 3:00 PM"]
        parsed = [parse_ts(ts, fmt) for ts in timestamps]

        assert parsed == [
            "2025-07-08T14:23:00",
            "2025-07-08T14:24:00",
            "2025-07-08T15:00:00",
        ]


class TestHeaderSplit:
    """Tests for ParserAgent._split_header."""

    @pytest.fixture
    def parser(self, tmp_path):
        """Create a ParserAgent instance for testing."""
        return ParserAgent(root=str(tmp_path))

    def test_header_split_basic(self, parser, header_lines):
        """Test basic header split with sender and body."""
        fmt = detect_datetime_format(header_lines)
        ts, sender, body = parser._split_header(header_lines[0], fmt)

        assert ts == "7/8/25, 14:23"
        assert sender == "Alice"
        assert body == "Hello world"

    def test_header_split_colon_in_sender(self, parser, header_lines):
        """Ensure only the first ': ' is used for splitting."""
        fmt = detect_datetime_format(header_lines)
        ts, sender, body = parser._split_header(header_lines[2], fmt)

        assert ts == "7/8/25, 14:25"
        assert sender == "Bob"
        assert body == "Marley: Jamming"

    def test_header_split_non_header_continuation(self, parser, header_lines):
        """Lines without a leading timestamp should be treated as continuations."""
        fmt = detect_datetime_format(header_lines)
        ts, sender, body = parser._split_header(header_lines[-1], fmt)

        assert ts is None
        assert sender is None
        assert body == "Continuation without timestamp"


class TestMultilineJoiner:
    """Tests for ParserAgent._to_blocks."""

    @pytest.fixture
    def parser(self, tmp_path):
        """Create a ParserAgent instance for testing."""
        return ParserAgent(root=str(tmp_path))

    def test_multiline_join_preserves_newlines(self, parser, multiline_lines):
        """Continuation lines should be aggregated with newline preservation."""
        fmt = detect_datetime_format(multiline_lines)
        blocks = parser._to_blocks(multiline_lines, fmt)

        assert len(blocks) == 3

        first_block = blocks[0]
        assert first_block["ts"] == "7/8/25, 14:23"
        assert first_block["sender"] == "Alice"
        assert first_block["raw_line"] == "7/8/25, 14:23 - Alice: Hello there"
        assert first_block["raw_block"] == (
            "7/8/25, 14:23 - Alice: Hello there\n"
            "This is a continuation line\n"
            "And another line with emoji 😊"
        )
        assert first_block["content_text"] == (
            "Hello there\nThis is a continuation line\nAnd another line with emoji 😊"
        )

    def test_multiline_no_false_splits(self, parser, multiline_lines):
        """Non-header colons should not start a new block."""
        fmt = detect_datetime_format(multiline_lines)
        blocks = parser._to_blocks(multiline_lines, fmt)

        second_block = blocks[1]
        assert second_block["ts"] == "7/8/25, 14:24"
        assert second_block["sender"] == "Bob"
        assert "Still Bob talking" in second_block["raw_block"]
        assert second_block["content_text"].endswith("Still Bob talking: not a new header")


class TestKindClassification:
    """Tests for ParserAgent._classify."""

    @pytest.fixture
    def parser(self, tmp_path):
        """Create a ParserAgent instance for testing."""
        return ParserAgent(root=str(tmp_path))

    def test_kind_detection_file_attached_voice_and_image(self, parser, kind_lines):
        """File attached lines should map to correct kinds and empty content."""
        line_voice = kind_lines[0]
        kind, media_hint, content_text = parser._classify({"content_text": line_voice})
        assert kind == "voice"
        assert media_hint == "PTT-20250708-WA0028.opus"
        assert content_text == ""

        line_image = kind_lines[2]
        kind, media_hint, content_text = parser._classify({"content_text": line_image})
        assert kind == "image"
        assert media_hint == "IMG-20250726-WA0037.jpg"
        assert content_text == ""

    def test_kind_detection_media_placeholders(self, parser, kind_lines):
        """Media placeholders should clear content and set appropriate kinds."""
        kind, media_hint, content_text = parser._classify({"content_text": kind_lines[5]})
        assert kind == "image"
        assert media_hint == "image_omitted"
        assert content_text == ""

        kind, media_hint, content_text = parser._classify({"content_text": kind_lines[6]})
        assert kind == "video"
        assert media_hint == "video_omitted"
        assert content_text == ""

        kind, media_hint, content_text = parser._classify({"content_text": kind_lines[7]})
        assert kind == "unknown"
        assert media_hint == "media_omitted"
        assert content_text == ""

    def test_kind_detection_document(self, parser, kind_lines):
        """Document file attached should map to document kind."""
        kind, media_hint, content_text = parser._classify({"content_text": kind_lines[4]})
        assert kind == "document"
        assert media_hint == "DOC-20250728-WA0001.pdf"
        assert content_text == ""

    def test_text_falls_back_unknown_when_ambiguous(self, parser, kind_lines):
        """Ambiguous or normal text should remain text/unknown and keep content."""
        normal_line = kind_lines[10]
        kind, media_hint, content_text = parser._classify({"content_text": normal_line})
        assert kind == "text"
        assert media_hint is None
        assert content_text == normal_line

        weird_line = kind_lines[11]
        kind, media_hint, content_text = parser._classify({"content_text": weird_line})
        assert kind == "text"
        assert media_hint is None
        assert content_text == weird_line

    def test_kind_detection_voice_hint(self, parser, kind_lines):
        """Voice textual hints should map to voice with extracted duration."""
        kind, media_hint, content_text = parser._classify({"content_text": kind_lines[8]})
        assert kind == "voice"
        assert media_hint == "00:36"
        assert content_text == ""

        kind, media_hint, content_text = parser._classify({"content_text": kind_lines[9]})
        assert kind == "voice"
        assert media_hint == "audio_omitted"
        assert content_text == ""

    def test_system_lines_marked(self, parser, system_lines):
        """System phrases should be classified as system."""
        fmt = detect_datetime_format(system_lines)
        blocks = parser._to_blocks(system_lines, fmt)

        system_bodies = system_lines[:6]
        for body in system_bodies:
            kind, media_hint, content_text = parser._classify({"content_text": body})
            assert kind == "system"
            assert media_hint is None
            assert content_text == body.strip()

    def test_system_lines_do_not_split_messages(self, parser, system_lines):
        """Continuation after normal message should stay in same block."""
        fmt = detect_datetime_format(system_lines)
        blocks = parser._to_blocks(system_lines, fmt)
        normal_block = blocks[-1]
        assert "Another continuation line" in normal_block["raw_block"]


class TestCaptionMerge:
    """Tests for ParserAgent._merge_captions."""

    @pytest.fixture
    def parser(self, tmp_path):
        """Create a ParserAgent instance for testing."""
        return ParserAgent(root=str(tmp_path))

    def test_caption_merge_positive(self, parser):
        """Consecutive media/text with same ts and sender should merge."""
        media_msg = Message(
            idx=0,
            ts="2025-07-08T14:23:00",
            sender="Alice",
            kind="image",
            content_text="",
            raw_line="media line",
            raw_block="media line",
        )
        caption_msg = Message(
            idx=1,
            ts="2025-07-08T14:23:00",
            sender="Alice",
            kind="text",
            content_text="caption text",
            raw_line="caption line",
            raw_block="caption line",
        )

        merged = parser._merge_captions([media_msg, caption_msg])

        assert merged[0].caption == "caption text"
        assert merged[0].content_text == ""
        assert merged[1].status == "skipped"
        assert merged[1].status_reason.code == "merged_into_previous_media"

    def test_caption_merge_negative_different_ts(self, parser):
        """Different timestamps should not merge captions."""
        media_msg = Message(
            idx=0,
            ts="2025-07-08T14:23:00",
            sender="Bob",
            kind="video",
            content_text="",
            raw_line="media line",
            raw_block="media line",
        )
        text_msg = Message(
            idx=1,
            ts="2025-07-08T14:24:00",
            sender="Bob",
            kind="text",
            content_text="should stay separate",
            raw_line="text line",
            raw_block="text line",
        )

        merged = parser._merge_captions([media_msg, text_msg])

        assert merged[0].caption is None
        assert merged[1].status == "ok"
        assert merged[1].status_reason is None


class TestParseIntegration:
    """Tests for ParserAgent.parse assembly."""

    @pytest.fixture
    def parser(self):
        """Parser pointed at fixture chat export."""
        fixture_root = Path(__file__).parent / "fixtures/text_only"
        return ParserAgent(root=str(fixture_root))
    
    def test_smoke_cli_invocation(self, tmp_path):
        """Ensure CLI runs and outputs JSONL."""
        fixture_root = Path(__file__).parent / "fixtures/text_only"
        cmd_path = Path(__file__).parent.parent / "scripts" / "parse_chat.py"
        assert cmd_path.exists()
        import subprocess, sys
        result = subprocess.run(
            [sys.executable, str(cmd_path), "--root", str(fixture_root)],
            capture_output=True,
            text=True,
            check=True,
        )
        lines = [ln for ln in result.stdout.splitlines() if ln.strip()]
        assert len(lines) >= 1

    def test_message_indexing_stable(self, parser):
        """Re-running parse should produce stable idx/order."""
        msgs1 = parser.parse()
        msgs2 = parser.parse()

        assert [m.idx for m in msgs1] == [0, 1, 2]
        assert [m.idx for m in msgs1] == [m.idx for m in msgs2]
        assert [m.sender for m in msgs1] == ["Alice", "Bob", "Alice"]

    def test_message_fields_defaults(self, parser):
        """Parsed messages should populate defaults; derived fields stay default."""
        msgs = parser.parse()
        first = msgs[0]

        assert first.media_hint is None
        assert first.media_filename is None
        assert first.caption is None
        assert first.derived == {}
        assert first.status == "ok"
        assert first.partial is False
        assert first.status_reason is None
        assert first.errors == []
