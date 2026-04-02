import os
import re
from datetime import datetime
from pathlib import Path

import numpy as np
import soundfile as sf
from elevenlabs.client import ElevenLabs
from elevenlabs.types import VoiceSettings
from pedalboard import Bitcrush, Chorus, Pedalboard, PitchShift, Reverb
from pedalboard.io import AudioFile

from config import OUTPUT_DIR, S3_BUCKET, STORAGE_MODE

ELEVENLABS_API_KEY: str = os.environ.get("ELEVENLABS_API_KEY", "")
VOICE_ID: str = os.environ.get("ELEVENLABS_VOICE_ID", "dHd5gvgSOzSfduK4CvEg")

# Module-level singleton
_client: ElevenLabs | None = None

# AI voice effect chain — tuned iteratively for a "robotic announcer" feel.
# Values landed between two extremes: too subtle to hear (v1) and
# too distorted to understand (v2). These are the sweet spot.
_fx = Pedalboard(
    [
        Chorus(  # Synthetic shimmer / doubling effect
            rate_hz=2.0,  # modulation speed — 2Hz gives a gentle wobble
            depth=0.25,  # 25% pitch variation — audible but not warbling
            mix=0.4,  # 40% wet — noticeable without drowning the voice
            centre_delay_ms=7.0,  # 7ms base delay — short enough to sound cohesive
        ),
        PitchShift(semitones=-1.0),  # Drop 1 semitone — adds gravitas without sounding unnatural
        Bitcrush(bit_depth=11),  # 11-bit — subtle digital grit, not lo-fi (8-bit was too much)
        Reverb(  # Metallic "AI booth" ambiance
            room_size=0.25,  # small room — tight, not cavernous
            damping=0.6,  # absorbs highs — prevents tinny ringing
            wet_level=0.2,  # 20% reverb — present but not washy
            dry_level=0.8,  # 80% dry signal preserved
        ),
    ]
)


def _get_client() -> ElevenLabs:
    """Return the cached ElevenLabs client."""
    global _client
    if _client is None:
        if not ELEVENLABS_API_KEY:
            raise OSError("ELEVENLABS_API_KEY is not set. Add it to your environment.")
        _client = ElevenLabs(api_key=ELEVENLABS_API_KEY)
    return _client


def _slugify(text: str) -> str:
    """Turn a hint string into a filesystem-safe slug."""
    slug = re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")
    return slug[:40] if slug else "clip"


def _apply_ai_effect(
    input_path: Path,
    output_path: Path,
    volume_ramp: bool = False,
    speed: float = 1.0,
    gain_db: float = 0.0,
) -> None:
    """Apply robotic AI voice effect to an audio file. Outputs WAV for clean playback."""
    with AudioFile(str(input_path)) as f:
        audio = f.read(f.frames)
        sr = f.samplerate

    processed = _fx(audio, sr)

    if speed != 1.0:
        import librosa

        mono = processed[0] if processed.ndim > 1 else processed
        stretched = librosa.effects.time_stretch(mono, rate=speed)
        processed = stretched[np.newaxis, :]

    if gain_db != 0.0:
        gain_linear = 10 ** (gain_db / 20)
        processed = processed * gain_linear

    if volume_ramp:
        # Linear crescendo across the clip — used for "Your Reward!" to build energy.
        # 0.4 (40%) start is quiet enough to feel like a buildup.
        # 2.2 (220%) end clips to ±1.0 but that's intentional — it maxes out the
        # dynamic range for the final syllable. Tuned with the user to "go higher".
        num_samples = processed.shape[1]
        ramp = np.linspace(0.4, 2.2, num_samples).astype(np.float32)
        processed = processed * ramp[np.newaxis, :]

    processed = np.clip(processed, -1.0, 1.0)

    # Write as WAV to avoid MP3 double-encoding artifacts
    mono = processed[0] if processed.ndim > 1 else processed
    sf.write(str(output_path), mono, sr, format="WAV")


def _expand_for_tts(text: str) -> str:
    """Expand symbols and patterns that TTS engines misread."""
    # "-7" → "minus 7", "+3" → "plus 3" (stat boosts/penalties in rewards)
    text = re.sub(r"(?<!\w)\+(\d)", r"plus \1", text)
    text = re.sub(r"(?<!\w)-(\d)", r"minus \1", text)
    # "one (1)" → "one" — remove parenthetical number duplicates
    text = re.sub(r"(\w+)\s*\(\d+\)", r"\1", text)
    return text


def synthesize(
    text: str,
    filename_hint: str = "",
    volume_ramp: bool = False,
    speed: float = 1.0,
    el_speed: float = 1.0,
    gain_db: float = 0.0,
    keep_local: bool = False,
) -> Path | str:
    """
    Synthesize text using the ElevenLabs cloned voice with AI effect.
    text: the string to speak
    filename_hint: short slug used in the output filename
    volume_ramp: if True, audio builds from low to high volume
    speed: playback speed multiplier (1.0 = normal, 1.15 = slightly faster)
    keep_local: if True, skip S3 upload even in cloud mode (for concatenation)
    Returns Path (local) or str (S3 key) to the generated MP3 file.
    """
    text = _expand_for_tts(text)
    client = _get_client()

    slug = _slugify(filename_hint) if filename_hint else "clip"
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    raw_path = OUTPUT_DIR / f"{timestamp}_{slug}_raw.mp3"
    processed_wav = OUTPUT_DIR / f"{timestamp}_{slug}_processed.wav"
    out_path = OUTPUT_DIR / f"{timestamp}_{slug}.mp3"

    # Turbo model — ~40% faster synthesis with comparable quality
    voice_settings = VoiceSettings(speed=el_speed) if el_speed != 1.0 else None
    audio = client.text_to_speech.convert(
        voice_id=VOICE_ID,
        text=text,
        model_id="eleven_multilingual_v2",
        voice_settings=voice_settings,
    )

    with open(raw_path, "wb") as f:
        for chunk in audio:
            f.write(chunk)

    # Apply effects to WAV (lossless processing), then encode final output as MP3 (10x smaller)
    _apply_ai_effect(
        raw_path,
        processed_wav,
        volume_ramp=volume_ramp,
        speed=speed,
        gain_db=gain_db,
    )
    raw_path.unlink()

    _encode_mp3(processed_wav, out_path)
    processed_wav.unlink()

    if STORAGE_MODE == "cloud" and not keep_local:
        return _upload_to_s3(out_path)

    return out_path


def upload_to_s3(local_path: Path) -> str:
    """Public wrapper for S3 upload — used by concatenation pipeline."""
    return _upload_to_s3(local_path)


def _encode_mp3(wav_path: Path, mp3_path: Path) -> None:
    """Encode a WAV file to MP3 for smaller file size (~10x reduction)."""
    from pydub import AudioSegment

    audio = AudioSegment.from_wav(str(wav_path))
    audio.export(str(mp3_path), format="mp3", bitrate="128k")


def _upload_to_s3(local_path: Path) -> str:
    """Upload a local audio file to S3 and delete the local copy. Returns the S3 key."""
    import boto3

    s3 = boto3.client("s3")
    s3_key = f"audio/{local_path.name}"
    content_type = "audio/mpeg" if local_path.suffix == ".mp3" else "audio/wav"
    s3.upload_file(str(local_path), S3_BUCKET, s3_key, ExtraArgs={"ContentType": content_type})
    local_path.unlink()
    return s3_key
