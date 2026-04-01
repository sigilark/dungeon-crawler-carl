# Changelog

All notable changes to this project will be documented in this file.

## [0.6.0] - 2026-04-01

### Changed — Persistence Migration
- `archive.py` — rewritten with dual backend: SQLite (local/container) and DynamoDB (cloud/production)
  - SQLite replaces flat JSON file — handles concurrent writes, works in containers without EFS
  - DynamoDB backend with atomic auto-increment IDs and PAY_PER_REQUEST billing
  - Same public API (`save`, `load_all`, `get`) regardless of backend
- `voice.py` — adds S3 upload in cloud mode: synthesize locally, upload WAV, return S3 key
- `server.py` — `_audio_urls()` returns presigned S3 GET URLs (1hr expiry) in cloud mode
- `storage.py` (new) — `resolve_audio_path()` helper downloads S3 audio to temp dir for CLI playback
- `config.py` — new env vars: `STORAGE_MODE`, `DYNAMODB_TABLE`, `S3_BUCKET`, `DB_PATH`
- CDK stack — replaced EFS with DynamoDB table + S3 bucket, updated IAM grants
- 64 tests (was 57): 16 archive tests (9 SQLite + 7 DynamoDB via moto)
- New dependency: `boto3`

## [0.5.0] - 2026-04-01

### Added — AWS Deployment
- `Dockerfile` — production container based on python:3.11-slim with libsndfile
- `requirements.txt` — pinned production dependencies
- `cdk/` — AWS CDK (Python) infrastructure stack:
  - VPC with 2 AZs, public + private subnets, NAT gateway
  - EFS filesystem with access point for persistent audio cache and archive
  - ECS Fargate service (0.5 vCPU, 1GB RAM) behind Application Load Balancer
  - Secrets Manager integration for API keys
  - CloudWatch log group with 30-day retention
  - Docker image auto-built and pushed to ECR via CDK

### Changed
- `config.py` — `OUTPUT_DIR` and `ARCHIVE_FILE` now configurable via env vars for container/EFS compatibility
- `voice.py` — effect output switched from MP3 to WAV to fix garbled audio in browser playback

## [0.4.0] - 2026-04-01

### Added — Phase 4: Web UI
- `server.py` — FastAPI web server with REST API endpoints
  - `POST /api/generate` — generate achievement with audio synthesis
  - `GET /api/achievements` — list all archived achievements
  - `GET /api/achievements/{id}` — get/replay single achievement
  - `GET /audio/{filename}` — serve cached audio files
- `static/index.html` — single-page web app (vanilla HTML/CSS/JS)
  - Dark theme with gold accents and game-style achievement card
  - Text input for trigger events with Generate button
  - Automatic audio playback with correct segment pauses via Web Audio
  - Achievement history list with click-to-replay
  - Loading state with pulsing animation during generation
  - Enter key to submit
- New dependencies: `fastapi`, `uvicorn[standard]`

## [0.3.0] - 2026-04-01

### Added — Phase 3: Achievement Archive
- `archive.py` — JSON-based achievement log with save, load, and lookup
- `--list` flag to browse all archived achievements in a compact table
- `--replay N` flag to replay any past achievement by ID with cached audio
- Audio caching — synthesized files are stored and reused on replay without re-calling ElevenLabs
- Every generated achievement is automatically archived with timestamp, trigger, and audio file paths
- 9 new archive unit tests

## [0.2.0] - 2026-04-01

### Added — Phase 2: Voice Synthesis
- `voice.py` — ElevenLabs API integration for text-to-speech with cloned voices
- `player.py` — pygame-based audio playback with MP3 support
- `--speak` flag — generate, print, and play achievement audio
- `--speak-only` flag — audio-only mode, no terminal output
- AI audio effect chain via Spotify's pedalboard library:
  - Chorus (2.0Hz, 25% depth) for synthetic shimmer
  - Pitch shift (-1.0 semitone) for depth
  - Bitcrush (11-bit) for digital grit
  - Reverb (25% room, 20% wet) for AI-booth ambiance
- Description split into 5 audio segments with distinct processing:
  - "New Achievement!" — +5dB gain boost
  - Title — +3dB gain boost
  - Body — 1.15x playback speed
  - "Your Reward!" — volume crescendo (40% to 220%)
  - Reward — normal level after 0.6s pause
- Pre-synthesis of all segments before playback for seamless delivery
- `finetune.py` — experimental XTTS v2 fine-tuning script (Whisper data prep + GPT training)

### Changed
- System prompt rewritten — snarkier, more biting tone with varied reward formats
- Descriptions shortened to 20-35 words for punchier TTS delivery
- "Reward!" changed to "Your Reward!" for better cadence
- `generator.py` now handles markdown-wrapped JSON responses from Claude

## [0.1.0] - 2026-04-01

### Added — Phase 1: CLI Generation
- `main.py` — CLI entry point with `--trigger` and `--raw` flags
- `generator.py` — Claude API integration for achievement generation with JSON retry
- `config.py` — environment variable loading, path constants, system prompt
- `display.py` — terminal formatting with Unicode box-drawing characters
- System prompt defining the Achievement Intercom persona
- 34 unit tests across all Phase 1 modules
- Reference audio samples and transcripts for future voice cloning
- Build prompts in `prompts/` directory
