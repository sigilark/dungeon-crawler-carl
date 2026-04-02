import importlib
from pathlib import Path


def test_defaults_without_env(monkeypatch):
    """Config uses correct defaults for MODEL and MAX_TOKENS when env vars are absent."""
    monkeypatch.delenv("MODEL", raising=False)
    monkeypatch.delenv("MAX_TOKENS", raising=False)

    import config

    importlib.reload(config)

    assert config.MODEL == "claude-sonnet-4-5"
    assert config.MAX_TOKENS == 400


def test_env_vars_override(monkeypatch):
    """Config picks up env var overrides."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-key")
    monkeypatch.setenv("MODEL", "claude-sonnet-4-5-20250514")
    monkeypatch.setenv("MAX_TOKENS", "800")

    import config

    importlib.reload(config)

    assert config.ANTHROPIC_API_KEY == "sk-test-key"
    assert config.MODEL == "claude-sonnet-4-5-20250514"
    assert config.MAX_TOKENS == 800


def test_project_paths():
    """All configured paths are rooted in the project directory."""
    import config

    importlib.reload(config)

    assert config.PROJECT_ROOT == Path(config.__file__).parent
    assert config.REFERENCE_AUDIO_DIR == config.PROJECT_ROOT / "reference_audio"
    assert config.TRANSCRIPTS_DIR == config.PROJECT_ROOT / "transcripts"
    assert config.OUTPUT_DIR == config.PROJECT_ROOT / "output"
    assert config.ARCHIVE_FILE == config.PROJECT_ROOT / "achievements.json"


def test_directories_created():
    """Output, reference_audio, and transcripts dirs are created on import."""
    import config

    importlib.reload(config)

    assert config.OUTPUT_DIR.is_dir()
    assert config.REFERENCE_AUDIO_DIR.is_dir()
    assert config.TRANSCRIPTS_DIR.is_dir()


def test_system_prompt_present():
    """System prompt is a non-empty string with key phrases."""
    import config

    importlib.reload(config)

    assert isinstance(config.SYSTEM_PROMPT, str)
    assert len(config.SYSTEM_PROMPT) > 100
    assert "Crawl Log" in config.SYSTEM_PROMPT
    assert "New Achievement!" in config.SYSTEM_PROMPT
    assert "Your Reward!" in config.SYSTEM_PROMPT
    assert '"title"' in config.SYSTEM_PROMPT
    assert '"description"' in config.SYSTEM_PROMPT
    assert '"reward"' in config.SYSTEM_PROMPT
