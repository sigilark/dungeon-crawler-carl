"""Tests for server.py cloud mode — CDN URLs, presigned URLs, and re-synthesis error paths."""

import importlib
import sys
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

SAMPLE_ACHIEVEMENT = {
    "title": "Corporate Houdini",
    "badge": "ghost",
    "description": "New Achievement! You vanished for 120 minutes. Your Reward!",
    "reward": "Nobody noticed.",
}


@pytest.fixture
def tmp_archive(tmp_path, monkeypatch):
    import config

    monkeypatch.setattr(config, "DB_PATH", tmp_path / "test.db")
    monkeypatch.setattr(config, "STORAGE_MODE", "local")

    import archive

    archive._DB_INIT = False
    importlib.reload(archive)
    return tmp_path


@pytest.fixture
def client(tmp_archive):
    from server import app

    return TestClient(app)


def test_audio_urls_cdn_mode(monkeypatch):
    """CDN mode returns https://{CDN_DOMAIN}/{key} URLs."""
    import server

    monkeypatch.setattr(server, "STORAGE_MODE", "cloud")
    monkeypatch.setattr(server, "CDN_DOMAIN", "cdn.example.com")

    urls = server._audio_urls(["audio/test.mp3", "audio/test2.mp3"])
    assert urls == [
        "https://cdn.example.com/audio/test.mp3",
        "https://cdn.example.com/audio/test2.mp3",
    ]


def test_audio_urls_cdn_mode_filters_empty(monkeypatch):
    """CDN mode filters out empty strings from audio_files."""
    import server

    monkeypatch.setattr(server, "STORAGE_MODE", "cloud")
    monkeypatch.setattr(server, "CDN_DOMAIN", "cdn.example.com")

    urls = server._audio_urls(["audio/test.mp3", "", None])
    assert urls == ["https://cdn.example.com/audio/test.mp3"]


def test_audio_urls_presigned_mode(monkeypatch):
    """Cloud mode without CDN generates presigned S3 URLs."""
    import server

    monkeypatch.setattr(server, "STORAGE_MODE", "cloud")
    monkeypatch.setattr(server, "CDN_DOMAIN", "")
    monkeypatch.setattr(server, "S3_BUCKET", "test-bucket")

    mock_s3 = MagicMock()
    mock_s3.generate_presigned_url.return_value = "https://s3.amazonaws.com/signed-url"

    mock_boto3 = MagicMock()
    mock_boto3.client.return_value = mock_s3

    with patch.dict(sys.modules, {"boto3": mock_boto3}):
        urls = server._audio_urls(["audio/test.mp3"])

    assert urls == ["https://s3.amazonaws.com/signed-url"]
    mock_s3.generate_presigned_url.assert_called_once_with(
        "get_object",
        Params={"Bucket": "test-bucket", "Key": "audio/test.mp3"},
        ExpiresIn=3600,
    )


@patch("server.synthesize_achievement_parallel", return_value=[])
@patch("server.generate", return_value=SAMPLE_ACHIEVEMENT)
def test_generate_osError_on_synthesis(mock_gen, mock_synth, client):
    """Synthesis OSError is logged but achievement still streams."""
    mock_synth.side_effect = OSError("no ElevenLabs key")
    res = client.post("/api/generate", json={"trigger": "test"})
    assert res.status_code == 200
    assert "Corporate Houdini" in res.text
    assert '"audio_urls": []' in res.text


@patch("server.concatenate_audio", side_effect=Exception("concat failed"))
@patch("server.synthesize_achievement", return_value=["/fake/seg.mp3"])
@patch("server.synthesize_achievement_parallel", return_value=[])
@patch("server.generate", return_value=SAMPLE_ACHIEVEMENT)
def test_get_achievement_resynth_failure(mock_gen, mock_synth_p, mock_synth, mock_concat, client):
    """GET /api/achievements/{id} handles re-synthesis failure gracefully."""
    # Generate creates entry with empty audio (synth_parallel returns [])
    client.post("/api/generate", json={"trigger": "test"})

    # GET triggers re-synthesis since audio_files is empty
    res = client.get("/api/achievements/1")
    assert res.status_code == 200
    assert res.json()["audio_urls"] == []


@patch("server.synthesize_achievement_parallel", return_value=[])
@patch("server.generate", return_value=SAMPLE_ACHIEVEMENT)
def test_shared_achievement_xss_escaped(mock_gen, mock_synth, client):
    """OG tags escape HTML entities in title and description."""
    xss_achievement = {
        "title": '<script>alert("xss")</script>',
        "badge": "skull",
        "description": 'New Achievement! <img onerror="alert(1)"> Your Reward!',
        "reward": "hacked",
    }
    mock_gen.return_value = xss_achievement
    client.post("/api/generate", json={"trigger": "xss"})

    res = client.get("/a/1")
    assert res.status_code == 200
    # The escaped title should appear in OG tags
    assert "&lt;script&gt;" in res.text
    # The raw XSS payload should NOT appear in meta content attributes
    assert 'content="<script>' not in res.text
    assert 'content="<img onerror' not in res.text


@patch("server.synthesize_achievement_parallel", return_value=[])
@patch("server.generate", side_effect=RuntimeError("unexpected"))
def test_generate_generic_exception(mock_gen, mock_synth, client):
    """POST /api/generate returns 502 on unexpected exceptions."""
    res = client.post("/api/generate", json={"trigger": "test"})
    assert res.status_code == 502
    assert "API error" in res.json()["detail"]


@patch("server.synthesize_achievement_parallel", return_value=[])
@patch("server.generate", return_value=SAMPLE_ACHIEVEMENT)
def test_achievement_card_renders(mock_gen, mock_synth, client):
    """GET /api/achievements/{id}/card.png returns a PNG image."""
    client.post("/api/generate", json={"trigger": "test"})
    res = client.get("/api/achievements/1/card.png")
    assert res.status_code == 200
    assert res.headers["content-type"] == "image/png"
    assert res.content[:4] == b"\x89PNG"


def test_achievement_card_not_found(client):
    """GET /api/achievements/{id}/card.png returns 404 for missing ID."""
    res = client.get("/api/achievements/999/card.png")
    assert res.status_code == 404
