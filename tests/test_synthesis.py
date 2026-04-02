from unittest.mock import patch

from synthesis import (
    SEGMENT_DESCRIPTION,
    SEGMENT_OPENER,
    SEGMENT_REWARD,
    SEGMENT_TITLE,
    SEGMENT_YOUR_REWARD,
    _parse_segments,
)

FULL_ACHIEVEMENT = {
    "title": "Corporate Houdini",
    "description": "New Achievement! You vanished for 120 minutes. Your Reward!",
    "reward": "Nobody noticed.",
}

NO_OPENER_ACHIEVEMENT = {
    "title": "Test",
    "description": "You did something. Your Reward!",
    "reward": "Nothing.",
}

NO_CLOSER_ACHIEVEMENT = {
    "title": "Test",
    "description": "New Achievement! You did something.",
    "reward": "Nothing.",
}

BARE_ACHIEVEMENT = {
    "title": "",
    "description": "Just a description.",
    "reward": "Just a reward.",
}


def test_parse_segments_full():
    """Full achievement parses into 5 segments in correct order."""
    segments = _parse_segments(FULL_ACHIEVEMENT)
    hints = [s[1]["filename_hint"] for s in segments]
    assert hints == [
        SEGMENT_OPENER,
        SEGMENT_TITLE,
        SEGMENT_DESCRIPTION,
        SEGMENT_YOUR_REWARD,
        SEGMENT_REWARD,
    ]


def test_parse_segments_opener_text():
    segments = _parse_segments(FULL_ACHIEVEMENT)
    opener = segments[0]
    assert opener[0] == "New Achievement!"
    assert opener[1]["gain_db"] == 5.0


def test_parse_segments_title_text():
    segments = _parse_segments(FULL_ACHIEVEMENT)
    title = segments[1]
    assert title[0] == "Corporate Houdini"
    assert title[1]["gain_db"] == 3.0


def test_parse_segments_body_text():
    segments = _parse_segments(FULL_ACHIEVEMENT)
    body = segments[2]
    assert body[0] == "You vanished for 120 minutes."
    assert "speed" not in body[1]  # natural speed, no override
    assert body[1]["gain_db"] == 3.0


def test_parse_segments_closer_text():
    segments = _parse_segments(FULL_ACHIEVEMENT)
    closer = segments[3]
    assert closer[0] == "REWARD?"  # TTS override — caps for energy, question mark for inflection
    assert closer[1]["volume_ramp"] is True


def test_parse_segments_reward_text():
    segments = _parse_segments(FULL_ACHIEVEMENT)
    reward = segments[4]
    assert reward[0] == "Nobody noticed."
    assert reward[1]["filename_hint"] == SEGMENT_REWARD


def test_parse_segments_no_opener():
    """Missing 'New Achievement!' skips opener segment."""
    segments = _parse_segments(NO_OPENER_ACHIEVEMENT)
    hints = [s[1]["filename_hint"] for s in segments]
    assert SEGMENT_OPENER not in hints
    assert hints[0] == SEGMENT_TITLE


def test_parse_segments_no_closer():
    """Missing 'Your Reward!' skips closer segment."""
    segments = _parse_segments(NO_CLOSER_ACHIEVEMENT)
    hints = [s[1]["filename_hint"] for s in segments]
    assert SEGMENT_YOUR_REWARD not in hints


def test_parse_segments_no_title():
    """Empty title skips title segment."""
    segments = _parse_segments(BARE_ACHIEVEMENT)
    hints = [s[1]["filename_hint"] for s in segments]
    assert SEGMENT_TITLE not in hints


def test_parse_segments_bare_minimum():
    """Bare achievement produces only body + reward."""
    segments = _parse_segments(BARE_ACHIEVEMENT)
    hints = [s[1]["filename_hint"] for s in segments]
    assert hints == [SEGMENT_DESCRIPTION, SEGMENT_REWARD]


@patch("synthesis.synthesize", side_effect=lambda text, **kw: f"/output/{kw['filename_hint']}.wav")
def test_synthesize_achievement_returns_ordered_paths(mock_synth):
    from synthesis import synthesize_achievement

    paths = synthesize_achievement(FULL_ACHIEVEMENT)
    assert len(paths) == 5
    assert "opener" in paths[0]
    assert "title" in paths[1]
    assert "description" in paths[2]
    assert "your_reward" in paths[3]
    assert "reward" in paths[4]
    assert mock_synth.call_count == 5
