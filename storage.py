"""
Storage helper — resolves audio references to local paths.

In local mode, audio_files entries are already local paths.
In cloud mode, they're S3 keys that need to be downloaded for CLI playback.
"""

import tempfile
from pathlib import Path

from config import S3_BUCKET, STORAGE_MODE


def resolve_audio_path(audio_ref: str) -> Path:
    """
    Resolve an audio reference to a local file path.

    Local mode: returns the path as-is (it's already a local file).
    Cloud mode: downloads from S3 to a temp file and returns the local path.
    """
    if STORAGE_MODE != "cloud" or not audio_ref.startswith("audio/"):
        return Path(audio_ref)

    import boto3

    s3 = boto3.client("s3")
    local_path = Path(tempfile.gettempdir()) / Path(audio_ref).name
    if not local_path.exists():
        s3.download_file(S3_BUCKET, audio_ref, str(local_path))
    return local_path
