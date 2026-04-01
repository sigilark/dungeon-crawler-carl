import argparse
import json
import os
import sys

import archive
from config import ANTHROPIC_API_KEY
from display import print_achievement
from generator import generate
from storage import resolve_audio_path
from synthesis import play_audio_sequence, synthesize_achievement


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="achievement",
        description="Satirical Achievement Reward System",
    )
    parser.add_argument(
        "--trigger",
        type=str,
        default=None,
        metavar="EVENT",
        help='Context for the achievement (e.g. "spilled coffee again")',
    )
    parser.add_argument(
        "--raw",
        action="store_true",
        help="Print raw JSON only — suitable for piping",
    )
    parser.add_argument(
        "--speak",
        action="store_true",
        help="Generate achievement, print to terminal, and play audio",
    )
    parser.add_argument(
        "--speak-only",
        action="store_true",
        help="Generate achievement and play audio only — no terminal output",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="List all archived achievements",
    )
    parser.add_argument(
        "--replay",
        type=int,
        default=None,
        metavar="ID",
        help="Replay an archived achievement by ID (with audio)",
    )
    return parser.parse_args()


def _list_achievements() -> None:
    """Display all archived achievements in a compact table."""
    entries = archive.load_all()
    if not entries:
        print("\nNo achievements archived yet.\n")
        return

    print(f"\n  {'ID':>4}  {'Timestamp':<20} {'Title':<30} Trigger")
    print("  " + "\u2500" * 78)
    for e in entries:
        ts = e["timestamp"][:19].replace("T", " ")
        title = e["title"][:28]
        trigger = (e.get("trigger") or "random")[:30]
        print(f"  {e['id']:>4}  {ts:<20} {title:<30} {trigger}")
    print()


def main() -> None:
    args = parse_args()

    # --list mode
    if args.list:
        _list_achievements()
        sys.exit(0)

    # --replay mode
    if args.replay is not None:
        entry = archive.get(args.replay)
        if not entry:
            print(f"\nNo achievement found with ID {args.replay}\n", file=sys.stderr)
            sys.exit(1)

        print_achievement(entry)

        if entry.get("audio_files"):
            resolved = [str(resolve_audio_path(f)) for f in entry["audio_files"]]
            play_audio_sequence(resolved)
        elif os.environ.get("ELEVENLABS_API_KEY"):
            audio_files = synthesize_achievement(entry)
            play_audio_sequence(audio_files)
        else:
            print("  (No audio \u2014 set ELEVENLABS_API_KEY to enable)\n")
        sys.exit(0)

    # Normal generation mode
    if not ANTHROPIC_API_KEY:
        print(
            "\nSetup required:\n"
            "  1. Copy .env.example to .env\n"
            "  2. Add your Anthropic API key\n"
            "  3. Run again\n",
            file=sys.stderr,
        )
        sys.exit(1)

    if (args.speak or args.speak_only) and not os.environ.get("ELEVENLABS_API_KEY"):
        print(
            "\nElevenLabs API key not found. "
            "Set ELEVENLABS_API_KEY in your environment.\n",
            file=sys.stderr,
        )
        sys.exit(1)

    try:
        achievement = generate(trigger=args.trigger)
    except OSError as e:
        print(f"\nConfiguration error: {e}\n", file=sys.stderr)
        sys.exit(1)
    except ValueError as e:
        print(f"\nGeneration error: {e}\n", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"\nAPI error: {e}\n", file=sys.stderr)
        sys.exit(1)

    if args.raw:
        print(json.dumps(achievement, ensure_ascii=False))
        sys.exit(0)

    if not args.speak_only:
        print_achievement(achievement)

    audio_files: list[str] = []
    if args.speak or args.speak_only:
        audio_files = synthesize_achievement(achievement)
        play_audio_sequence(audio_files)

    archive.save(
        achievement=achievement,
        trigger=args.trigger,
        audio_files=audio_files,
    )


if __name__ == "__main__":
    main()
