"""Integration tests for the synthesis pipeline — tests the full flow
from _parse_segments through _synth_segment with mocked voice.synthesize."""

from pathlib import Path
from unittest.mock import patch

from synthesis import (
    SEGMENT_DESCRIPTION,
    SEGMENT_OPENER,
    SEGMENT_REWARD,
    SEGMENT_TITLE,
    SEGMENT_YOUR_REWARD,
    _parse_segments,
    _synth_segment,
    concatenate_audio,
)

FULL_ACHIEVEMENT = {
    "title": "Test Title",
    "description": "New Achievement! You did something impressive. Your Reward!",
    "reward": "The dungeon is mildly impressed.",
}

LEGENDARY_ACHIEVEMENT = {
    "title": "Test Title",
    "rarity": "legendary",
    "description": "New Achievement! You did something incredible. Your Reward!",
    "reward": "Legendary prize.",
}


def test_parse_segments_produces_correct_count():
    """Full achievement with all parts produces 5 segments."""
    segments = _parse_segments(FULL_ACHIEVEMENT)
    assert len(segments) == 5


def test_parse_segments_hint_order():
    """Segments are in the correct playback order."""
    segments = _parse_segments(FULL_ACHIEVEMENT)
    hints = [s[1]["filename_hint"] for s in segments]
    assert hints == [
        SEGMENT_OPENER,
        SEGMENT_TITLE,
        SEGMENT_DESCRIPTION,
        SEGMENT_YOUR_REWARD,
        SEGMENT_REWARD,
    ]


def test_description_has_el_speed():
    """Description segment uses ElevenLabs native speed control."""
    segments = _parse_segments(FULL_ACHIEVEMENT)
    desc = next(s for s in segments if s[1]["filename_hint"] == SEGMENT_DESCRIPTION)
    assert desc[1]["el_speed"] == 1.15


def test_legendary_opener_has_extra_gain():
    """Gold/Legendary opener gets +7dB instead of +5dB."""
    segments = _parse_segments(LEGENDARY_ACHIEVEMENT)
    opener = next(s for s in segments if s[1]["filename_hint"] == SEGMENT_OPENER)
    assert opener[1]["gain_db"] == 7.0


def test_legendary_title_has_extra_gain():
    """Gold/Legendary title gets +5dB instead of +3dB."""
    segments = _parse_segments(LEGENDARY_ACHIEVEMENT)
    title = next(s for s in segments if s[1]["filename_hint"] == SEGMENT_TITLE)
    assert title[1]["gain_db"] == 5.0


def test_legendary_description_slower():
    """Gold/Legendary description uses 1.05x speed instead of 1.15x."""
    segments = _parse_segments(LEGENDARY_ACHIEVEMENT)
    desc = next(s for s in segments if s[1]["filename_hint"] == SEGMENT_DESCRIPTION)
    assert desc[1]["el_speed"] == 1.05


def test_bronze_uses_default_gains():
    """Bronze rarity uses default gain levels."""
    segments = _parse_segments(FULL_ACHIEVEMENT)
    opener = next(s for s in segments if s[1]["filename_hint"] == SEGMENT_OPENER)
    title = next(s for s in segments if s[1]["filename_hint"] == SEGMENT_TITLE)
    assert opener[1]["gain_db"] == 5.0
    assert title[1]["gain_db"] == 3.0


def test_closer_uses_reward_override():
    """Closer TTS text is 'REWARD?' not the original 'Your Reward!'."""
    segments = _parse_segments(FULL_ACHIEVEMENT)
    closer = next(s for s in segments if s[1]["filename_hint"] == SEGMENT_YOUR_REWARD)
    assert closer[0] == "REWARD?"


def test_closer_has_volume_ramp():
    """Closer segment has volume ramp enabled."""
    segments = _parse_segments(FULL_ACHIEVEMENT)
    closer = next(s for s in segments if s[1]["filename_hint"] == SEGMENT_YOUR_REWARD)
    assert closer[1]["volume_ramp"] is True


def test_synth_segment_calls_synthesize():
    """_synth_segment calls voice.synthesize for normal segments."""
    with patch("synthesis.synthesize", return_value=Path("/output/test.mp3")) as mock:
        result = _synth_segment("Hello", {"filename_hint": "test", "gain_db": 3.0})
        assert result == "/output/test.mp3"
        mock.assert_called_once_with("Hello", keep_local=True, filename_hint="test", gain_db=3.0)


def test_synth_segment_skips_synthesize_for_static():
    """_synth_segment copies static clip without calling synthesize."""
    import tempfile

    # Create a temp file to act as static clip
    with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
        f.write(b"fake audio data")
        static_path = Path(f.name)

    with patch("synthesis.synthesize") as mock:
        result = _synth_segment(None, {"filename_hint": "test", "static_clip": static_path})
        mock.assert_not_called()
        assert "test" in result
        assert result.endswith(".mp3")

    # Clean up
    Path(result).unlink(missing_ok=True)
    static_path.unlink(missing_ok=True)


def test_concatenate_audio_produces_mp3(tmp_path):
    """concatenate_audio produces a valid MP3 from segment files."""
    from pydub import AudioSegment
    from pydub.generators import Sine

    import config

    original_output = config.OUTPUT_DIR
    config.OUTPUT_DIR = tmp_path

    # Create fake segment files
    files = []
    for hint in ["opener", "title", "description", "your_reward", "reward"]:
        tone = Sine(440).to_audio_segment(duration=500)
        path = tmp_path / f"test_{hint}.mp3"
        tone.export(str(path), format="mp3")
        files.append(str(path))

    with patch("synthesis.STORAGE_MODE", "local"):
        result = concatenate_audio(files)

    assert result.endswith(".mp3")
    assert Path(result).exists()

    # Verify it's longer than any single segment (pauses added)
    combined = AudioSegment.from_file(result)
    assert len(combined) > 2500  # 5 x 500ms segments + pauses

    config.OUTPUT_DIR = original_output
