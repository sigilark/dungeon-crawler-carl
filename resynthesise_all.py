#!/usr/bin/env python3
"""
One-off script to re-synthesize audio for all existing achievements in prod.

Pulls every achievement from DynamoDB, re-runs the TTS + effects pipeline
(which now trims ElevenLabs silence), uploads the new combined MP3 to S3,
and updates the DynamoDB audio_files reference.

Usage:
    STORAGE_MODE=cloud ELEVENLABS_API_KEY=... python3 resynthesise_all.py

Optional:
    --dry-run   List achievements without re-synthesizing
    --start-id  Start from a specific achievement ID (for resuming)
"""

import argparse
import time

from archive import load_all, update_audio
from synthesis import concatenate_audio, synthesize_achievement_parallel


def main():
    parser = argparse.ArgumentParser(description="Re-synthesize audio for all achievements")
    parser.add_argument("--dry-run", action="store_true", help="List achievements without processing")
    parser.add_argument("--start-id", type=int, default=0, help="Skip achievements below this ID")
    args = parser.parse_args()

    entries = load_all()
    entries = [e for e in entries if e["id"] >= args.start_id]

    print(f"Found {len(entries)} achievements to process")

    if args.dry_run:
        for e in entries:
            print(f"  #{e['id']}: {e['title']}")
        return

    succeeded = 0
    failed = 0

    for i, entry in enumerate(entries, 1):
        entry_id = entry["id"]
        title = entry["title"]
        print(f"[{i}/{len(entries)}] #{entry_id}: {title} ... ", end="", flush=True)

        try:
            segments = synthesize_achievement_parallel(entry)
            combined = concatenate_audio(segments)
            update_audio(entry_id, [combined])
            succeeded += 1
            print("done")
        except Exception as exc:
            failed += 1
            print(f"FAILED: {exc}")

        # Brief pause to avoid hammering ElevenLabs rate limits
        if i < len(entries):
            time.sleep(1)

    print(f"\nComplete: {succeeded} succeeded, {failed} failed")


if __name__ == "__main__":
    main()
