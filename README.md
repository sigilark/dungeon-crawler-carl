# The Dungeon Intercom

The omnipresent announcement system of a reality-show dungeon. Describe what you did, and the intercom delivers a snarky achievement announcement — complete with title, biting description, and a reward that hurts. Speaks it aloud using a cloned voice with robotic AI effects while billions of alien viewers watch.

Inspired by the dungeon announcer from the *Dungeon Crawler Carl* book series.

---

## Project Phases

| Phase | Status | Description |
|-------|--------|-------------|
| 1 | ✅ Complete | CLI generation — achievements printed to terminal |
| 2 | ✅ Complete | ElevenLabs voice synthesis with AI audio effects |
| 3 | ✅ Complete | Achievement archive (SQLite/DynamoDB), audio caching (local/S3), `--list`, `--replay` |
| 4 | ✅ Complete | Web UI via FastAPI + SSE streaming + parallel TTS + shareable cards |

---

## Directory Structure

```
dungeon_crawler_carl/
├── main.py               # CLI entry point
├── generator.py          # Claude API achievement generation
├── config.py             # Env vars, constants, system prompt
├── display.py            # Terminal formatting
├── voice.py              # ElevenLabs TTS + AI audio effects
├── player.py             # Audio playback via pygame
├── synthesis.py          # Audio synthesis pipeline (sequential + parallel)
├── archive.py            # Achievement persistence (SQLite local, DynamoDB cloud)
├── storage.py            # S3 download helper for CLI replay
├── card.py               # Shareable achievement card PNG renderer
├── server.py             # FastAPI web server with SSE streaming
├── static/index.html     # Web UI (single-page app)
├── Dockerfile            # Production container
├── cdk/                  # AWS CDK infrastructure (ECS Fargate + DynamoDB + S3)
├── finetune.py           # XTTS v2 fine-tuning script (experimental)
├── reference_audio/      # Voice reference samples
├── transcripts/          # Transcript files
├── output/               # Generated audio files
├── tests/                # Unit tests (64 tests)
├── ruff.toml             # Linting config
├── requirements.txt      # Production dependencies
├── .env.example          # Environment variable template
├── CHANGELOG.md
└── README.md
```

---

## Setup

### 1. Clone and create virtual environment

```bash
git clone https://github.com/dayelostraco/dungeon-crawler-carl.git
cd dungeon-crawler-carl
python -m venv .venv
source .venv/bin/activate
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Configure environment

```bash
cp .env.example .env
```

Edit `.env` and add your API keys:

```
ANTHROPIC_API_KEY=your_anthropic_key_here
ELEVENLABS_API_KEY=your_elevenlabs_key_here
```

### 4. ElevenLabs voice setup

Create a voice on [ElevenLabs](https://elevenlabs.io) by uploading your reference audio samples. Optionally set the voice ID in `.env`:

```
ELEVENLABS_VOICE_ID=your_voice_id_here
```

---

## Web UI

### Start the server

```bash
uvicorn server:app --reload
# Open http://localhost:8000
```

### Features

- Dark-themed dungeon aesthetic with gold accents
- Text input — describe what you did, crawler
- **SSE streaming** — achievement card appears in ~5s, audio follows ~6s later
- **Parallel TTS** — 5 audio segments synthesized simultaneously
- **Shareable achievement cards** — download a high-DPI PNG to share
- Achievement history with click-to-replay (cached audio, no re-synthesis)
- Progressive status: "Summoning achievement..." → "Synthesizing audio..." → "Playing..."

---

## CLI Usage

```bash
# Random achievement
python main.py

# Context-aware
python main.py --trigger "pushed to production on a Friday at 4:59pm"

# With voice
python main.py --trigger "took a 2 hour lunch and nobody noticed" --speak

# Audio only
python main.py --speak-only

# Browse history
python main.py --list

# Replay with cached audio
python main.py --replay 1

# Raw JSON
python main.py --raw
```

### Example output

```
╔══════════════════════════════════════════════════╗
║  ACHIEVEMENT UNLOCKED                            ║
╚══════════════════════════════════════════════════╝

  ★  Corporate Houdini

  New Achievement! You vanished for 120 minutes and the
  dungeon did not notice. Your Reward!

  REWARD  Princess Donut has reviewed your absence and
          rated it: forgettable.

──────────────────────────────────────────────────
```

---

## Voice Synthesis

Voice synthesis uses the [ElevenLabs API](https://elevenlabs.io) with a post-processing AI effect chain via [pedalboard](https://github.com/spotify/pedalboard):

### Audio pipeline

1. Text split into 5 segments: **opener** | **title** | **body** | **closer** | **reward**
2. Each segment synthesized via ElevenLabs (parallel in web, sequential in CLI)
3. AI effects applied per-segment:
   - **Chorus** (2Hz, 25% depth) — synthetic shimmer
   - **Pitch shift** (-1.0 semitone) — gravitas
   - **Bitcrush** (11-bit) — digital grit
   - **Reverb** (25% room, 20% wet) — AI-booth ambiance
4. Segment-specific processing:
   - **"New Achievement!"** — +5dB boost
   - **Title** — +3dB boost
   - **Body** — 1.15x speed, +3dB
   - **"Your Reward!"** — volume crescendo (40% → 220%)
5. TTS text expansion: `+/-` symbols expanded to "plus"/"minus" for correct speech

---

## Achievement Archive

Achievements auto-save with dual-backend persistence:

| Mode | Metadata | Audio | Use case |
|------|----------|-------|----------|
| `STORAGE_MODE=local` (default) | SQLite | Local filesystem | Dev, CLI, Docker |
| `STORAGE_MODE=cloud` | DynamoDB | S3 (presigned URLs) | Production AWS |

---

## Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `ANTHROPIC_API_KEY` | Yes | — | Anthropic API key for Claude |
| `ELEVENLABS_API_KEY` | For voice | — | ElevenLabs API key for TTS |
| `ELEVENLABS_VOICE_ID` | No | built-in default | ElevenLabs voice ID |
| `MODEL` | No | `claude-opus-4-5` | Claude model |
| `MAX_TOKENS` | No | `400` | Max tokens for generation |
| `STORAGE_MODE` | No | `local` | `local` (SQLite) or `cloud` (DynamoDB+S3) |
| `DYNAMODB_TABLE` | Cloud only | `achievements` | DynamoDB table name |
| `S3_BUCKET` | Cloud only | `achievement-intercom-audio` | S3 bucket for audio |
| `DB_PATH` | No | `./achievements.db` | SQLite database path |
| `OUTPUT_DIR` | No | `./output` | Audio output directory |

---

## AWS Deployment

Deploys to ECS Fargate behind an ALB at `achievement.sigilark.com` using AWS CDK.

### Architecture

```
Internet → ALB (HTTPS) → ECS Fargate (0.5 vCPU, 1GB) → Container (uvicorn :8000)
                                                        ↳ DynamoDB (achievement metadata)
                                                        ↳ S3 (audio cache, presigned URLs)
                                                        ↳ Secrets Manager (API keys)
```

### Deploy

```bash
# Create secrets first (one-time)
aws secretsmanager create-secret --name achievement-intercom/anthropic-api-key --secret-string "key"
aws secretsmanager create-secret --name achievement-intercom/elevenlabs-api-key --secret-string "key"
aws secretsmanager create-secret --name achievement-intercom/elevenlabs-voice-id --secret-string "id"

# Deploy
cd cdk
pip install -r requirements.txt
cdk bootstrap   # first time only
cdk deploy
```

### Local Docker test

```bash
docker build -t dungeon-intercom .
docker run -p 8000:8000 --env-file .env dungeon-intercom
```

---

## Development

### Run tests

```bash
pip install pytest pytest-mock "moto[dynamodb,s3]"
python -m pytest tests/ -v
```

### Lint

```bash
pip install ruff
ruff check .
```

### Fine-tuning (experimental)

Local XTTS v2 voice cloning experimentation:

```bash
python finetune.py --prepare   # Segment audio with Whisper
python finetune.py --train     # Fine-tune XTTS v2 model
python finetune.py --test      # Test fine-tuned model
```

Requires Python 3.11 and additional dependencies: `TTS`, `faster-whisper`, `torch<2.6`, `transformers>=4.40,<4.45`.
