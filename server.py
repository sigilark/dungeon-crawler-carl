"""
Achievement Intercom — Web UI Server

Usage:
    uvicorn server:app --reload
    Open http://localhost:8000
"""

import logging
import os
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import archive
from config import OUTPUT_DIR, S3_BUCKET, STORAGE_MODE
from generator import generate
from synthesis import synthesize_achievement

logger = logging.getLogger("achievement-intercom")

app = FastAPI(title="Achievement Intercom")

STATIC_DIR = Path(__file__).parent / "static"
STATIC_DIR.mkdir(exist_ok=True)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


class GenerateRequest(BaseModel):
    trigger: str | None = None


def _audio_urls(audio_files: list[str]) -> list[str]:
    """Convert audio references to URLs for the frontend.

    Local mode: /audio/{filename} (served by this app).
    Cloud mode: presigned S3 GET URLs (1-hour expiry, served by S3 directly).
    """
    if STORAGE_MODE == "cloud":
        import boto3

        s3 = boto3.client("s3")
        return [
            s3.generate_presigned_url(
                "get_object",
                Params={"Bucket": S3_BUCKET, "Key": f},
                ExpiresIn=3600,
            )
            for f in audio_files
            if f
        ]
    return [f"/audio/{Path(f).name}" for f in audio_files if f]


def _entry_response(entry: dict) -> dict:
    """Format an archive entry for the API response."""
    return {
        "id": entry["id"],
        "timestamp": entry["timestamp"],
        "title": entry["title"],
        "description": entry["description"],
        "reward": entry["reward"],
        "trigger": entry.get("trigger"),
        "audio_urls": _audio_urls(entry.get("audio_files", [])),
    }


@app.get("/")
def root():
    return RedirectResponse(url="/static/index.html")


@app.post("/api/generate")
def api_generate(req: GenerateRequest):
    try:
        achievement = generate(trigger=req.trigger)
    except OSError as e:
        raise HTTPException(status_code=500, detail=f"Configuration error: {e}") from None
    except ValueError as e:
        raise HTTPException(status_code=502, detail=f"Generation failed: {e}") from None
    except Exception as e:
        logger.exception("Achievement generation failed")
        raise HTTPException(status_code=502, detail=f"API error: {e}") from None

    try:
        audio_files = synthesize_achievement(achievement)
    except OSError as e:
        # Missing ElevenLabs key — return achievement without audio
        logger.warning("Voice synthesis skipped: %s", e)
        audio_files = []
    except Exception:
        logger.exception("Voice synthesis failed")
        audio_files = []

    entry = archive.save(
        achievement=achievement,
        trigger=req.trigger,
        audio_files=audio_files,
    )
    return _entry_response(entry)


@app.get("/api/achievements")
def api_achievements():
    entries = archive.load_all()
    return [_entry_response(e) for e in reversed(entries)]


@app.get("/api/achievements/{entry_id}")
def api_achievement(entry_id: int):
    entry = archive.get(entry_id)
    if not entry:
        raise HTTPException(status_code=404, detail="Achievement not found")

    if entry.get("audio_files"):
        existing = [f for f in entry["audio_files"] if os.path.exists(f)]
        if not existing:
            try:
                entry["audio_files"] = synthesize_achievement(entry)
            except Exception:
                logger.exception("Re-synthesis failed for entry %d", entry_id)
                entry["audio_files"] = []

    return _entry_response(entry)


@app.get("/audio/{filename}")
def serve_audio(filename: str):
    safe_name = Path(filename).name
    file_path = OUTPUT_DIR / safe_name
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Audio file not found")
    media_type = "audio/wav" if file_path.suffix == ".wav" else "audio/mpeg"
    return FileResponse(str(file_path), media_type=media_type)
