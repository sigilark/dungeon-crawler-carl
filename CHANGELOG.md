# Changelog

All notable changes to this project will be documented in this file.

## [1.5.1] - 2026-04-06

### Model & Performance
- Switched from Claude Sonnet 4.5 → Sonnet 4.6 (via Opus 4.6 experiment)
- Generation latency: 15-20s → 6-10s (eliminated 5x retry penalty)
- Retry rate: 100% (Sonnet 4.5) → ~1 retry avg (Sonnet 4.6)
- Cost per achievement: ~$0.05 → ~$0.02

### Prompt Engineering
- **Streisand effect fix**: removed all negative instructions from prompt (banned numbers, banned phrases). Code-level enforcement catches them silently via regex + retry.
- **Verbatim copying fix**: model was reproducing prompt example quotes character-for-character. Added 3+ example flavors per reward format.
- **Number fixation fix**: removed "good numbers" list from prompt (model fixated on listed values). Positive guidance only.
- DCC references balanced as "rare seasoning" (~1 in 5 rewards) — Donut, Mordecai, sponsors, Borant as Easter eggs, not crutches
- Content-based rarity ranges: trigger absurdity sets floor/ceiling, model picks within range
- Daily Challenge triggers auto-skew rarity UP (silver minimum)
- Stat reward numbers constrained to -10 to +10 range (larger only when the big number IS the joke)

### Observability
- Generator retry logging: logs which specific number/phrase triggered each retry attempt
- CloudWatch dashboard: CrawlLog-Operations with API latency, requests, errors, ECS resources, DynamoDB capacity, retry log query

### Security
- Docker base image upgraded from Python 3.11-slim to 3.12-slim
- Trivy + bandit security scans added to CI, results in GitHub Security tab (SARIF upload)
- Docker CVEs fixed: jaraco.context (CVE-2026-23949), wheel (CVE-2026-24049) via setuptools upgrade
- 0 Python CVEs in production image, 0 bandit findings

### Infrastructure
- Deleted unused `resynthesise_all.py` one-off script
- Distribution check script now uses varied triggers (was same message 20x, causing artificial clustering)

## [1.5.0] - 2026-04-04

### Animated Card Reveal
- Achievement cards slide up with an overshoot bounce animation
- Content elements (header, title, description, reward) stagger in sequentially
- Gold rarity: pulsing gold glow + golden sparkle particles on reveal
- Legendary rarity: bright pink/purple glow + colored sparkle particles
- All CSS-only animations, no JavaScript libraries required

### API Rate Limiting
- `/api/generate`: 3 per minute, 20 per hour per IP
- `/api/achievements/{id}/card.png`: 3 per minute, 20 per hour per IP
- Returns 429 Too Many Requests when exceeded
- In-memory storage via slowapi (resets on container restart)

### Infrastructure
- Deploy concurrency group added to CI — back-to-back pushes queue instead of failing
- Concurrency groups added to 5 other repos (glyphon-web, mcart-api/infra/db/web)

### Code Quality
- 209 tests (was 196), 90% coverage
- Code comments for non-obvious patterns (DynamoDB counter, silence threshold, text wrapping, schema backfill)
- RUNBOOK updated with daily challenge and retry log monitoring

## [1.4.0] - 2026-04-04

### Rarity Tiers
- Achievements assigned Bronze/Silver/Gold/Legendary rarity based on event absurdity
- Web UI: rarity-colored card borders with glow effects (Gold/Legendary), colored dots in history
- Card PNG renderer: rarity-colored borders, badge tints, accent colors, and rarity label
- Audio: Gold/Legendary get louder opener (+7dB), boosted title (+5dB), and slower body delivery (1.05x vs 1.15x)
- Stored in DB with backfill for older entries

### Daily Challenge
- New daily prompt banner on homepage — one challenge per day from a pool of 31 prompts
- Deterministic by date (no backend needed), click to pre-fill trigger with `[Daily Challenge]` prefix
- Admin endpoint: `GET /api/admin/daily-challenge` — tracks participation counts by date

### Content Quality
- "Your mom" jokes added as rare reward format and woven into descriptions (~1 in 6)
- Banned content enforcement: generator retries up to 5 times if output contains "The dungeon [verb]", "The sponsors [verb]", or numbers 47/847
- Fallback strips offending sentences if all retries exhausted
- Streisand effect fix: removed all negative instructions (banned numbers/phrases) from prompt — positive guidance only, code enforces silently
- Retry logging added to monitor enforcement frequency in CloudWatch

### UI Improvements
- Random trigger suggestions rotate placeholder text from 20 funny examples
- Generate button disabled when input is empty (prevents empty submissions)
- Input validation: Enter key blocked when empty, button stays disabled after generation clears input

### Infrastructure
- CI actions bumped to v5/v6 (checkout@v5, setup-python@v6, setup-node@v5) for Node.js 24 compat
- Dockerfile updated with `system_prompt.txt` and `reward_classifier.py`

### Testing
- 196 tests (was 164): cloud mode coverage, CLI paths, rarity audio, daily challenge endpoint

## [1.3.0] - 2026-04-03

### Security
- Fixed XSS vulnerability in shared achievement route — `html.escape()` applied to title and description before interpolation into OG meta tags
- Added input validation to `/api/achievements` endpoint — `page_size` clamped to 1-100, `page` clamped to >= 0

### Reward Format Analytics (Issue #28)
- New `reward_classifier.py` — regex-based classifier with 13 format categories (loot, stat_boost, skill_unlock, pet, quest, care_package, borant_notice, crafting_material, sponsor, system_message, anti_reward, commentary_donut, commentary_mordecai) plus "other"
- `reward_format` column added to SQLite schema and DynamoDB items — classified on save, backfilled on load for older entries
- New admin endpoint: `GET /api/admin/reward-distribution` — returns total count, per-format counts, and percentages
- API responses now include `reward_format` field

### Prompt Regression Testing (Issue #27)
- New script: `scripts/check_reward_distribution.py` — generates N achievements and validates:
  - No single reward format exceeds 40% of total
  - No number repeats more than 3 times across samples
  - Banned numbers (47, 847) never appear
- Supports `--dry-run` (check existing DB) and `--count N` (generate fresh samples)

### Code Quality
- Extracted 112-line system prompt from `config.py` into `system_prompt.txt` — config.py is now 30 lines
- CI: added `libcairo2-dev` to system dependencies so card rendering tests run

### Testing
- 164 tests (was 138): reward classifier tests, distribution checker tests, admin endpoint tests, input validation tests

### Documentation
- README: updated directory structure, added reward analytics/regression testing/system deps sections, fixed repo URL
- RUNBOOK: added reward format drift troubleshooting section, fixed repo URL

## [1.2.0] - 2026-04-02

### Prompt Overhaul — Reward Variety & DCC Universe Depth

#### Reward System
- Expanded from 4 reward formats to 10+ tangible formats — items, stats, skills, and pets now dominate
- New common formats:
  - Dungeon loot with a twist ("Cracked Mana Vial. It is 11% full. The 11% is mostly sadness.")
  - Useless items — irreverent potions and boxes that don't work ("Potion of Mild Optimism. It expired in 2019.")
  - Stat boosts that hurt — sounds like a buff, isn't ("+6 to Meeting Attendance. This cannot be undone.")
  - Skill unlocks that are useless — passive skills the dungeon is proud of
  - Terrible Pet Menagerie assignments — worse than nothing
  - New quests that are worse than the achievement ("Do Better. Reward: unknown. Timer: always.")
  - Viewer care packages with wrong contents
  - Borant Corporation legal notices — alien corporate paperwork
  - Crafting materials with no known recipe ("Compressed Regret. Tier-2. No one knows what it makes.")
- Rare punchline formats (≤1 in 5): sponsor reads, brutal system messages, anti-rewards, Princess Donut commentary
- Added Mordecai commentary as a rare format — dry, resigned, unsurprised
- Anti-reward example updated to match tone ("None. You did the bare minimum and we do not want to reward that.")

#### Number Variety
- Explicit instruction to vary numbers every time — single digits, decimals, hundreds, thousands
- Never repeat the same number twice in a row

#### Examples
- All 5 examples updated to showcase new reward formats: dungeon loot, painful stat boost, useless skill, terrible pet, crafting materials
- Removed examples that only demonstrated old formats (system messages, sponsor reads)

## [1.1.0] - 2026-04-02

### Renamed to "The Crawl Log"
- App renamed from "The Dungeon Intercom" to "The Crawl Log" — your personal dungeon crawl log
- Domain: achievement.sigilark.com → crawl.sigilark.com
- Subtitle: "congratulations, you're still alive. for now."

### Badge System
- 54 Lucide SVG icons (MIT) — Claude picks a contextual badge for each achievement
- Badges displayed on web card, history list, and share PNG (gold-tinted via cairosvg)
- Categories: death, combat, rewards, dungeon, food, work, funny

### Shareable Links
- `/a/{id}` deep links with Open Graph meta tags for rich social previews
- OG image uses the achievement card PNG with badge, trigger, date
- Share button uses Web Share API on mobile, clipboard on desktop
- Play button for audio on shared links and history replays

### Model & Cost
- Switched from Claude Opus 4.5 to Claude Sonnet 4.5 (~75% cheaper, comparable quality)
- API cost per achievement: ~$0.01 (was ~$0.04)

### Infrastructure
- CloudWatch billing alarm at $75/month threshold
- FastAPI Swagger docs at `/docs`

### Documentation
- RUNBOOK.md: operations guide — health checks, logs, redeploy, clear data, secrets, DR
- README updated for all v1.1.0 changes

### Testing
- 138 tests (was 116): badge rendering, OG tags, pagination edges, archive badge field,
  config prompt validation, Swagger availability

### UI Polish
- Achievement date in history list
- Server-side pagination (10 per page)
- Play/Share button spacing on mobile
- Input field maxlength 200 characters

## [1.0.0] - 2026-04-02

### Production Release
- **Live at https://crawl.sigilark.com**

### Audio Pipeline Overhaul
- Segments concatenated into single MP3 with baked-in dramatic pauses (~139KB)
  - Eliminates mobile autoplay issues (one play() call, not five)
  - Faster download: one HTTP request instead of five
  - Sample-accurate pause timing between segments
- ElevenLabs native speed control (`el_speed` parameter) replaces librosa time_stretch
  - Description at 1.15x native speed — clean, no artifacts
  - All other segments at natural 1.0x
- "REWARD?" TTS text override — caps for energy, question mark for inflection
- MP3 output via pydub (was WAV) — 10x smaller files
- 500ms pause between description and "REWARD?" for dramatic pacing
- Reverted to `eleven_multilingual_v2` model (turbo model degraded quality)

### Web UI Improvements
- Achievement date displayed on card and shareable PNG
- Trigger text shown on card (what the user typed)
- Mobile responsive layout (stacked under 640px, larger touch targets)
- History limited to 20 most recent with "Show all" link
- Shared Audio element for mobile playback gesture chain

### Infrastructure
- **CI/CD pipeline** — GitHub Actions: lint → test → docker → auto-deploy on push to main
- **VPC Gateway Endpoints** for DynamoDB and S3 (free, ~50-100ms faster)
- **CloudFront CDN** for S3 audio delivery (edge-cached, free at low volume)
- ECS Fargate bumped to 1 vCPU / 2GB RAM
- ALB idle timeout increased to 120s for SSE streams
- x86_64 Fargate (ARM64 had pedalboard library compat issues)
- Public subnets, no NAT gateway (saves ~$32/month)

### Code Quality
- 115 tests (was 102): added synthesis integration tests, TTS expansion tests
- Fixed cloud audio re-synthesis bug (os.path.exists on S3 keys)
- Fixed replay for achievements with empty audio_files
- TTS text expansion: parenthetical numbers `one (1)` → `one`
- Prompt tuning: reduced viewer count references, enabled crawler mortality humor

## [0.7.0] - 2026-04-01

### Added
- **SSE streaming** — achievement card appears in ~5s, audio follows ~6s later (was ~30s blocking)
- **Parallel TTS synthesis** — 5 audio segments synthesized simultaneously via ThreadPoolExecutor
- **Shareable achievement cards** — high-DPI PNG renderer (`card.py`) with download button
- **`/health` endpoint** — lightweight health check (ALB no longer queries archive)
- **TTS text expansion** — `+/-` symbols expanded to "plus"/"minus" for correct speech
- `archive.update_audio()` for updating audio files after streaming synthesis

### Changed
- **Renamed to "The Crawl Log"** — full Dungeon Crawler Carl universe integration
- **System prompt rewritten** — dungeon announcer persona with crawlers, sponsors, Princess Donut,
  alien viewers, loot boxes, and dungeon bureaucracy
- Reward format diversified — reduced "Unlocked:" bias, added dungeon loot, sponsor reads,
  stat penalties, system messages, and Princess Donut commentary
- Parenthetical asides reduced to ~1 in 6 achievements
- Sponsor reads and fine print capped at 10 words max
- Description audio boosted +3dB to match title level
- `synthesis.py` refactored — shared `_parse_segments()`, sequential + parallel functions
- Dockerfile updated with missing modules (`synthesis.py`, `storage.py`)

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
