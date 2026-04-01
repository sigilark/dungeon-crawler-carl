from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

SAMPLE_ACHIEVEMENT = {
    "title": "Corporate Houdini",
    "description": "New Achievement! You vanished for 120 minutes. Your Reward!",
    "reward": "Unlocked: Nobody noticed.",
}

SAMPLE_ARCHIVE_ENTRY = {
    "id": 1,
    "timestamp": "2026-04-01T15:00:00",
    "title": "Corporate Houdini",
    "description": "New Achievement! You vanished for 120 minutes. Your Reward!",
    "reward": "Unlocked: Nobody noticed.",
    "trigger": "took a long lunch",
    "audio_files": [],
}


@pytest.fixture
def tmp_archive(tmp_path, monkeypatch):
    """Redirect archive to temp SQLite DB."""
    db_path = tmp_path / "test.db"
    import config

    monkeypatch.setattr(config, "DB_PATH", db_path)
    monkeypatch.setattr(config, "STORAGE_MODE", "local")

    import importlib

    import archive

    archive._DB_INIT = False
    importlib.reload(archive)
    return db_path


@pytest.fixture
def client(tmp_archive):
    """TestClient with isolated archive."""
    from server import app

    return TestClient(app)


@patch("server.synthesize_achievement", return_value=[])
@patch("server.generate", return_value=SAMPLE_ACHIEVEMENT)
def test_generate_returns_achievement(mock_gen, mock_synth, client):
    """POST /api/generate returns achievement data."""
    res = client.post("/api/generate", json={"trigger": "took a long lunch"})
    assert res.status_code == 200
    data = res.json()
    assert data["title"] == "Corporate Houdini"
    assert data["trigger"] == "took a long lunch"
    assert "id" in data
    assert "timestamp" in data
    assert "audio_urls" in data


@patch("server.synthesize_achievement", return_value=[])
@patch("server.generate", return_value=SAMPLE_ACHIEVEMENT)
def test_generate_without_trigger(mock_gen, mock_synth, client):
    """POST /api/generate works with null trigger."""
    res = client.post("/api/generate", json={})
    assert res.status_code == 200
    data = res.json()
    assert data["trigger"] is None


@patch("server.synthesize_achievement", return_value=[])
@patch("server.generate", side_effect=ValueError("parse failed"))
def test_generate_claude_error(mock_gen, mock_synth, client):
    """POST /api/generate returns 502 on Claude API failure."""
    res = client.post("/api/generate", json={"trigger": "test"})
    assert res.status_code == 502
    assert "Generation failed" in res.json()["detail"]


@patch("server.synthesize_achievement", return_value=[])
@patch("server.generate", side_effect=OSError("no key"))
def test_generate_config_error(mock_gen, mock_synth, client):
    """POST /api/generate returns 500 on missing config."""
    res = client.post("/api/generate", json={"trigger": "test"})
    assert res.status_code == 500
    assert "Configuration error" in res.json()["detail"]


@patch("server.synthesize_achievement", side_effect=Exception("ElevenLabs down"))
@patch("server.generate", return_value=SAMPLE_ACHIEVEMENT)
def test_generate_synthesis_failure_still_returns(mock_gen, mock_synth, client):
    """POST /api/generate returns achievement even if synthesis fails."""
    res = client.post("/api/generate", json={"trigger": "test"})
    assert res.status_code == 200
    data = res.json()
    assert data["title"] == "Corporate Houdini"
    assert data["audio_urls"] == []


@patch("server.synthesize_achievement", return_value=[])
@patch("server.generate", return_value=SAMPLE_ACHIEVEMENT)
def test_achievements_list(mock_gen, mock_synth, client):
    """GET /api/achievements returns archived entries."""
    client.post("/api/generate", json={"trigger": "first"})
    client.post("/api/generate", json={"trigger": "second"})

    res = client.get("/api/achievements")
    assert res.status_code == 200
    data = res.json()
    assert len(data) == 2
    # Most recent first
    assert data[0]["trigger"] == "second"
    assert data[1]["trigger"] == "first"


def test_achievements_list_empty(client):
    """GET /api/achievements returns empty list when no achievements."""
    res = client.get("/api/achievements")
    assert res.status_code == 200
    assert res.json() == []


@patch("server.synthesize_achievement", return_value=[])
@patch("server.generate", return_value=SAMPLE_ACHIEVEMENT)
def test_get_achievement_by_id(mock_gen, mock_synth, client):
    """GET /api/achievements/{id} returns single entry."""
    client.post("/api/generate", json={"trigger": "test"})

    res = client.get("/api/achievements/1")
    assert res.status_code == 200
    assert res.json()["id"] == 1
    assert res.json()["title"] == "Corporate Houdini"


def test_get_achievement_not_found(client):
    """GET /api/achievements/{id} returns 404 for missing ID."""
    res = client.get("/api/achievements/999")
    assert res.status_code == 404


def test_serve_audio_not_found(client):
    """GET /audio/{filename} returns 404 for missing file."""
    res = client.get("/audio/nonexistent.wav")
    assert res.status_code == 404


def test_serve_audio_exists(client, tmp_path, monkeypatch):
    """GET /audio/{filename} serves existing audio file."""
    import config

    output_dir = tmp_path / "output"
    output_dir.mkdir()
    monkeypatch.setattr(config, "OUTPUT_DIR", output_dir)

    # Reload server to pick up new OUTPUT_DIR
    import importlib

    import server

    importlib.reload(server)
    test_client = TestClient(server.app)

    test_file = output_dir / "test_audio.wav"
    test_file.write_bytes(b"RIFF" + b"\x00" * 100)

    res = test_client.get("/audio/test_audio.wav")
    assert res.status_code == 200
    assert res.headers["content-type"] == "audio/wav"


def test_serve_audio_path_traversal(client):
    """GET /audio/ rejects path traversal attempts."""
    res = client.get("/audio/../../../etc/passwd")
    assert res.status_code == 404


def test_root_redirects(client):
    """GET / redirects to /static/index.html."""
    res = client.get("/", follow_redirects=False)
    assert res.status_code == 307
    assert "/static/index.html" in res.headers["location"]


@patch("server.synthesize_achievement", return_value=["/fake/path/20260401_opener.wav", "/fake/path/20260401_reward.wav"])
@patch("server.generate", return_value=SAMPLE_ACHIEVEMENT)
def test_generate_returns_audio_urls(mock_gen, mock_synth, client):
    """POST /api/generate converts file paths to /audio/ URLs."""
    res = client.post("/api/generate", json={"trigger": "test"})
    data = res.json()
    assert data["audio_urls"] == [
        "/audio/20260401_opener.wav",
        "/audio/20260401_reward.wav",
    ]
