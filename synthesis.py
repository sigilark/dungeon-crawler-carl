"""
Audio synthesis pipeline — splits achievement text into segments,
synthesizes each via ElevenLabs, and applies per-segment audio effects.

This module is the shared core used by both the CLI (main.py) and
the web server (server.py).
"""

import re
import time
from pathlib import Path

from voice import synthesize

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
PAUSE_BEFORE_TITLE = 0.3   # brief beat after "New Achievement!"
PAUSE_AFTER_TITLE = 0.4    # let the title land before the description
PAUSE_BEFORE_REWARD = 0.6  # dramatic pause before the reward punchline


def synthesize_achievement(achievement: dict) -> list[str]:
    """
    Split an achievement into audio segments and synthesize each one.

    Segments (in order):
      1. "New Achievement!" — opener, boosted +5dB for punch
      2. Title — achievement name, boosted +3dB
      3. Body — description text at 1.15x speed for snappier delivery
      4. "Your Reward!" — closer with volume crescendo (40% → 220%)
      5. Reward text — the punchline, normal level

    Returns list of absolute file path strings to the generated WAV files.
    """
    desc = achievement["description"]
    audio_files: list[str] = []

    # --- Parse segments from description text ---
    opener = None
    body = desc
    closer = None

    opener_match = re.match(
        r"(New Achievement!)\s*(.*)", body, flags=re.IGNORECASE | re.DOTALL
    )
    if opener_match:
        opener = opener_match.group(1).strip()
        body = opener_match.group(2).strip()

    closer_match = re.split(r"(Your Reward!)\s*$", body, flags=re.IGNORECASE)
    if len(closer_match) >= 2:
        body = closer_match[0].strip()
        closer = closer_match[1].strip()

    title = achievement.get("title", "")

    # --- Synthesize each segment ---
    if opener:
        audio_files.append(str(synthesize(
            opener,
            filename_hint=SEGMENT_OPENER,
            gain_db=5.0,  # +5dB ≈ 1.8x volume — punchy announcement
        )))

    if title:
        audio_files.append(str(synthesize(
            title,
            filename_hint=SEGMENT_TITLE,
            gain_db=3.0,  # +3dB ≈ 1.4x volume — prominent but not as loud as opener
        )))

    audio_files.append(str(synthesize(
        body,
        filename_hint=SEGMENT_DESCRIPTION,
        speed=1.15,  # 15% faster — keeps the description from dragging
        gain_db=3.0,  # +3dB — match the title level so it doesn't sound quiet after the opener
    )))

    if closer:
        audio_files.append(str(synthesize(
            closer,
            filename_hint=SEGMENT_YOUR_REWARD,
            volume_ramp=True,  # crescendo from 40% to 220% volume
        )))

    audio_files.append(str(synthesize(
        achievement["reward"],
        filename_hint=SEGMENT_REWARD,
    )))

    return audio_files


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
        elif f"_{SEGMENT_REWARD}" in name and f"_{SEGMENT_YOUR_REWARD}" not in name:
            time.sleep(PAUSE_BEFORE_REWARD)
            play(Path(path_str))
        else:
            play(Path(path_str))
