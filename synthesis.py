"""
Audio synthesis pipeline — splits achievement text into segments,
synthesizes each via ElevenLabs, and applies per-segment audio effects.

This module is the shared core used by both the CLI (main.py) and
the web server (server.py).
"""

import re
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

from pydub import AudioSegment
from pydub.silence import detect_leading_silence

from config import OUTPUT_DIR, PROJECT_ROOT, STORAGE_MODE
from voice import synthesize, upload_to_s3

# Pre-recorded clips from the audiobook reference audio — used instead of
# ElevenLabs for "New Achievement!" and "Reward?" for authentic DCC delivery.
STATIC_AUDIO_DIR = PROJECT_ROOT / "static" / "audio"
CLIP_NEW_ACHIEVEMENT = STATIC_AUDIO_DIR / "new_achievement.mp3"
CLIP_REWARD = STATIC_AUDIO_DIR / "reward.mp3"

# Filename hints double as segment identifiers. The pause logic in both
# _play_audio_sequence() and the frontend JS (index.html) matches on these
# substrings to determine inter-segment timing. If you rename these, update
# both playback sites.
SEGMENT_OPENER = "opener"
SEGMENT_TITLE = "title"
SEGMENT_DESCRIPTION = "description"
SEGMENT_YOUR_REWARD = "your_reward"
SEGMENT_REWARD = "reward"

# Pause durations (seconds) — tuned for dramatic pacing
PAUSE_BEFORE_TITLE = 0.3  # brief beat after "New Achievement!"
PAUSE_AFTER_TITLE = 0.4  # let the title land before the description
PAUSE_BEFORE_CLOSER = 0.5  # space between description and "Your Reward!"
PAUSE_BEFORE_REWARD = 0.6  # dramatic pause before the reward punchline


def synthesize_achievement(achievement: dict) -> list[str]:
    """
    Split an achievement into audio segments and synthesize each one sequentially.

    Segments (in order):
      1. "New Achievement!" — opener, boosted +5dB for punch
      2. Title — achievement name, boosted +3dB
      3. Body — description text at 1.15x speed, +3dB
      4. "Your Reward!" — closer with volume crescendo (40% → 220%)
      5. Reward text — the punchline, normal level

    Returns list of absolute file path strings to the generated MP3 files.
    Used by the CLI. The web server uses synthesize_achievement_parallel() instead.
    """
    segments = _parse_segments(achievement)
    return [_synth_segment(text, kwargs) for text, kwargs in segments]


def _parse_segments(achievement: dict) -> list[tuple[str, dict]]:
    """Parse achievement text into a list of (text, synth_kwargs) tuples."""
    desc = achievement["description"]
    rarity = achievement.get("rarity", "bronze")
    segments: list[tuple[str, dict]] = []

    opener = None
    body = desc
    closer = None

    opener_match = re.match(r"(New Achievement!)\s*(.*)", body, flags=re.IGNORECASE | re.DOTALL)
    if opener_match:
        opener = opener_match.group(1).strip()
        body = opener_match.group(2).strip()

    closer_match = re.split(r"(Your Reward!)\s*$", body, flags=re.IGNORECASE)
    if len(closer_match) >= 2:
        body = closer_match[0].strip()
        closer = closer_match[1].strip()

    title = achievement.get("title", "")

    # Gold/Legendary get louder opener/title and slower body for gravitas.
    # The extra dB and reduced speed make rare achievements feel weightier in TTS.
    is_epic = rarity in ("gold", "legendary")
    opener_gain = 7.0 if is_epic else 5.0
    title_gain = 5.0 if is_epic else 3.0
    body_speed = 1.05 if is_epic else 1.15

    if opener:
        segments.append((opener, {"filename_hint": SEGMENT_OPENER, "gain_db": opener_gain}))
    if title:
        segments.append((title, {"filename_hint": SEGMENT_TITLE, "gain_db": title_gain}))
    segments.append(
        (body, {"filename_hint": SEGMENT_DESCRIPTION, "gain_db": 3.0, "el_speed": body_speed})
    )
    if closer:
        segments.append(("REWARD?", {"filename_hint": SEGMENT_YOUR_REWARD, "volume_ramp": True}))
    segments.append((achievement["reward"], {"filename_hint": SEGMENT_REWARD}))

    return segments


def _synth_segment(text: str | None, kwargs: dict) -> str:
    """Synthesize a single segment — either from a static clip or via ElevenLabs."""
    static_clip = kwargs.pop("static_clip", None)
    if static_clip:
        # Use pre-recorded audio file — just copy to output with timestamped name
        import shutil

        hint = kwargs.get("filename_hint", "clip")
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        out_path = OUTPUT_DIR / f"{timestamp}_{hint}.mp3"
        shutil.copy2(str(static_clip), str(out_path))
        return str(out_path)
    return str(synthesize(text, keep_local=True, **kwargs))


def synthesize_achievement_parallel(achievement: dict) -> list[str]:
    """
    Same as synthesize_achievement but runs all TTS calls in parallel.

    Uses ThreadPoolExecutor(5) — each voice.synthesize() call is I/O-bound
    (ElevenLabs API) + CPU-bound (pedalboard effects, which release the GIL).
    Reduces total synthesis time from ~25s to ~6s.

    Used by the web server for faster response. The CLI keeps using the
    sequential version to avoid thread overhead.
    """
    segments = _parse_segments(achievement)

    with ThreadPoolExecutor(max_workers=5) as executor:
        results = list(executor.map(lambda args: _synth_segment(*args), segments))

    return results


def _trim_silence(segment: AudioSegment, silence_thresh: int = -40) -> AudioSegment:
    """Strip leading and trailing silence from an audio segment."""
    lead = detect_leading_silence(segment, silence_threshold=silence_thresh)
    trail = detect_leading_silence(segment.reverse(), silence_threshold=silence_thresh)
    end = len(segment) - trail
    return segment[lead:end] if lead < end else segment


def concatenate_audio(audio_files: list[str]) -> str:
    """
    Stitch individual segment files into a single MP3 with silence gaps
    baked in for dramatic pacing. Returns path to the combined file.

    Each segment is trimmed of ElevenLabs' natural leading/trailing silence
    so only the explicit pause constants control inter-segment timing.

    Pause timing matches play_audio_sequence() and the frontend JS:
      opener → 300ms → title → 400ms → body → closer → 600ms → reward
    """
    combined = AudioSegment.empty()

    for path_str in audio_files:
        name = Path(path_str).name
        segment = _trim_silence(AudioSegment.from_file(path_str))

        if f"_{SEGMENT_TITLE}" in name:
            combined += AudioSegment.silent(duration=int(PAUSE_BEFORE_TITLE * 1000))
            combined += segment
            combined += AudioSegment.silent(duration=int(PAUSE_AFTER_TITLE * 1000))
        elif f"_{SEGMENT_YOUR_REWARD}" in name:
            combined += AudioSegment.silent(duration=int(PAUSE_BEFORE_CLOSER * 1000))
            combined += segment
        elif f"_{SEGMENT_REWARD}" in name:
            combined += AudioSegment.silent(duration=int(PAUSE_BEFORE_REWARD * 1000))
            combined += segment
        else:
            combined += segment

    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    out_path = OUTPUT_DIR / f"{timestamp}_combined.mp3"
    combined.export(str(out_path), format="mp3", bitrate="128k")

    # Clean up individual segment files — they're baked into the combined file
    for path_str in audio_files:
        Path(path_str).unlink(missing_ok=True)

    # Upload combined file to S3 in cloud mode
    if STORAGE_MODE == "cloud":
        return upload_to_s3(out_path)

    return str(out_path)


def play_audio_sequence(audio_files: list[str]) -> None:
    """
    Play a pre-synthesized audio sequence with dramatic pauses.

    Segment detection is based on filename hints (SEGMENT_* constants).
    Pause timing mirrors the frontend JS in static/index.html.
    """
    from player import play

    for path_str in audio_files:
        name = Path(path_str).name

        if f"_{SEGMENT_TITLE}" in name:
            time.sleep(PAUSE_BEFORE_TITLE)
            play(Path(path_str))
            time.sleep(PAUSE_AFTER_TITLE)
        elif f"_{SEGMENT_YOUR_REWARD}" in name:
            time.sleep(PAUSE_BEFORE_CLOSER)
            play(Path(path_str))
        elif f"_{SEGMENT_REWARD}" in name:
            time.sleep(PAUSE_BEFORE_REWARD)
            play(Path(path_str))
        else:
            play(Path(path_str))
