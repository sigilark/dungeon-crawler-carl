"""
The Dungeon Intercom — Web UI Server

Usage:
    uvicorn server:app --reload
    Open http://localhost:8000
"""

import asyncio
import json
import logging
import os
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, RedirectResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import archive
from card import render_card
from config import OUTPUT_DIR, S3_BUCKET, STORAGE_MODE
from generator import generate
from synthesis import (
    concatenate_audio,
    synthesize_achievement,
    synthesize_achievement_parallel,
)

logger = logging.getLogger("achievement-intercom")

app = FastAPI(title="The Dungeon Intercom")

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


def _sse_event(event: str, data: dict) -> str:
    """Format a Server-Sent Event string."""
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/")
def root():
    return RedirectResponse(url="/static/index.html")


@app.post("/api/generate")
async def api_generate(req: GenerateRequest):
    """Generate achievement with SSE streaming: text first, then audio."""

    # Phase 1: Generate text via Claude (blocking, run in thread)
    loop = asyncio.get_event_loop()
    try:
        achievement = await loop.run_in_executor(None, generate, req.trigger)
    except OSError as e:
        raise HTTPException(status_code=500, detail=f"Configuration error: {e}") from None
    except ValueError as e:
        raise HTTPException(status_code=502, detail=f"Generation failed: {e}") from None
    except Exception as e:
        logger.exception("Achievement generation failed")
        raise HTTPException(status_code=502, detail=f"API error: {e}") from None

    # Save to archive immediately (with empty audio) to get an ID
    entry = archive.save(
        achievement=achievement,
        trigger=req.trigger,
        audio_files=[],
    )

    async def event_stream():
        # Event 1: Achievement text — card renders immediately
        yield _sse_event(
            "achievement",
            {
                "id": entry["id"],
                "timestamp": entry["timestamp"],
                "title": entry["title"],
                "description": entry["description"],
                "reward": entry["reward"],
                "trigger": entry.get("trigger"),
            },
        )

        # Phase 2: Synthesize audio in parallel, then concatenate into one file
        combined_file = []
        try:
            segment_files = await loop.run_in_executor(
                None, synthesize_achievement_parallel, achievement
            )
            combined_path = await loop.run_in_executor(None, concatenate_audio, segment_files)
            combined_file = [combined_path]
            archive.update_audio(entry["id"], combined_file)
        except OSError as e:
            logger.warning("Voice synthesis skipped: %s", e)
        except Exception:
            logger.exception("Voice synthesis failed")

        # Event 2: Single audio URL — one download, one play
        yield _sse_event(
            "audio",
            {
                "audio_urls": _audio_urls(combined_file),
            },
        )

        # Event 3: Done
        yield _sse_event("done", {})

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Transfer-Encoding": "chunked",
            "Connection": "keep-alive",
        },
    )


@app.get("/api/achievements")
def api_achievements():
    entries = archive.load_all()
    return [_entry_response(e) for e in reversed(entries)]


@app.get("/api/achievements/{entry_id}")
def api_achievement(entry_id: int):
    entry = archive.get(entry_id)
    if not entry:
        raise HTTPException(status_code=404, detail="Achievement not found")

    # Re-synthesize and concatenate if audio is missing or empty
    has_audio = entry.get("audio_files") and len(entry["audio_files"]) > 0
    if has_audio and STORAGE_MODE == "local":
        has_audio = any(os.path.exists(f) for f in entry["audio_files"])

    if not has_audio:
        try:
            segments = synthesize_achievement(entry)
            combined = concatenate_audio(segments)
            entry["audio_files"] = [combined]
            archive.update_audio(entry_id, entry["audio_files"])
        except Exception:
            logger.exception("Re-synthesis failed for entry %d", entry_id)
            entry["audio_files"] = []

    return _entry_response(entry)


@app.get("/api/achievements/{entry_id}/card.png")
def api_achievement_card(entry_id: int):
    """Render a shareable PNG image of an achievement."""
    entry = archive.get(entry_id)
    if not entry:
        raise HTTPException(status_code=404, detail="Achievement not found")
    png_bytes = render_card(entry)
    return Response(content=png_bytes, media_type="image/png")


@app.get("/audio/{filename}")
def serve_audio(filename: str):
    safe_name = Path(filename).name
    file_path = OUTPUT_DIR / safe_name
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Audio file not found")
    media_type = "audio/wav" if file_path.suffix == ".wav" else "audio/mpeg"
    return FileResponse(str(file_path), media_type=media_type)
