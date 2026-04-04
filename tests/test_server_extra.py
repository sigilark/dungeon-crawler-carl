"""Additional server tests — OG tags, pagination edges, deep links, badges."""

import importlib
import json
from unittest.mock import patch

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


@patch("server.synthesize_achievement_parallel", return_value=[])
@patch("server.generate", return_value=SAMPLE_ACHIEVEMENT)
def test_shared_achievement_has_og_tags(mock_gen, mock_synth, client):
    """GET /a/{id} returns HTML with OG meta tags for the achievement."""
    # Create an achievement first
    client.post("/api/generate", json={"trigger": "test"})

    res = client.get("/a/1")
    assert res.status_code == 200
    html = res.text
    assert "og:title" in html
    assert "Corporate Houdini" in html
    assert "og:image" in html
    assert "card.png" in html


@patch("server.synthesize_achievement_parallel", return_value=[])
@patch("server.generate", return_value=SAMPLE_ACHIEVEMENT)
def test_shared_achievement_missing_id(mock_gen, mock_synth, client):
    """GET /a/{id} for non-existent ID still returns page (no OG tags)."""
    res = client.get("/a/999")
    assert res.status_code == 200
    # Should still return the HTML page, just without OG overrides
    assert "The Crawl Log" in res.text


def test_pagination_page_beyond_range(client):
    """Requesting a page beyond available data returns empty items."""
    res = client.get("/api/achievements?page=100&page_size=10")
    data = res.json()
    assert data["items"] == []
    assert data["page"] == 100
    assert data["total"] == 0


@patch("server.synthesize_achievement_parallel", return_value=[])
@patch("server.generate", return_value=SAMPLE_ACHIEVEMENT)
def test_pagination_page_size_one(mock_gen, mock_synth, client):
    """page_size=1 returns one item per page with correct total_pages."""
    client.post("/api/generate", json={"trigger": "a"})
    client.post("/api/generate", json={"trigger": "b"})
    client.post("/api/generate", json={"trigger": "c"})

    res = client.get("/api/achievements?page=0&page_size=1")
    data = res.json()
    assert len(data["items"]) == 1
    assert data["total"] == 3
    assert data["total_pages"] == 3


@patch("server.synthesize_achievement_parallel", return_value=[])
@patch("server.generate", return_value=SAMPLE_ACHIEVEMENT)
def test_achievement_response_includes_badge(mock_gen, mock_synth, client):
    """API responses include the badge field."""
    res = client.post("/api/generate", json={"trigger": "test"})
    # Parse SSE
    for block in res.text.split("\n\n"):
        if "achievement" in block and "data:" in block:
            data_line = next(line for line in block.split("\n") if line.startswith("data:"))
            data = json.loads(data_line[6:])
            assert data["badge"] == "ghost"
            break


def test_health_endpoint(client):
    """GET /health returns ok status."""
    res = client.get("/health")
    assert res.status_code == 200
    assert res.json() == {"status": "ok"}


def test_swagger_docs_available(client):
    """FastAPI Swagger docs are accessible."""
    res = client.get("/docs")
    assert res.status_code == 200
    assert "swagger" in res.text.lower() or "openapi" in res.text.lower()


@patch("server.synthesize_achievement_parallel", return_value=[])
@patch("server.generate", return_value=SAMPLE_ACHIEVEMENT)
def test_reward_distribution_endpoint(mock_gen, mock_synth, client):
    """GET /api/admin/reward-distribution returns format stats."""
    client.post("/api/generate", json={"trigger": "a"})
    client.post("/api/generate", json={"trigger": "b"})

    res = client.get("/api/admin/reward-distribution")
    assert res.status_code == 200
    data = res.json()
    assert data["total"] == 2
    assert "counts" in data
    assert "percentages" in data


@patch("server.synthesize_achievement_parallel", return_value=[])
@patch("server.generate", return_value=SAMPLE_ACHIEVEMENT)
def test_achievement_response_includes_reward_format(mock_gen, mock_synth, client):
    """API responses include the reward_format field."""
    client.post("/api/generate", json={"trigger": "test"})
    res = client.get("/api/achievements")
    data = res.json()
    assert data["items"][0]["reward_format"] is not None


def test_page_size_clamped(client):
    """page_size is clamped to max 100."""
    res = client.get("/api/achievements?page_size=999")
    data = res.json()
    assert data["page_size"] == 100


def test_negative_page_clamped(client):
    """Negative page is clamped to 0."""
    res = client.get("/api/achievements?page=-5")
    data = res.json()
    assert data["page"] == 0


@patch("server.synthesize_achievement_parallel", return_value=[])
@patch("server.generate", return_value=SAMPLE_ACHIEVEMENT)
def test_daily_challenge_stats_endpoint(mock_gen, mock_synth, client):
    """GET /api/admin/daily-challenge returns participation stats."""
    # Generate a daily challenge achievement
    client.post(
        "/api/generate",
        json={"trigger": "[Daily Challenge] Do something questionable"},
    )
    # Generate a normal achievement
    client.post("/api/generate", json={"trigger": "normal trigger"})

    res = client.get("/api/admin/daily-challenge")
    assert res.status_code == 200
    data = res.json()
    assert data["total_participations"] == 1
    assert data["days_active"] == 1
    assert len(data["by_date"]) == 1


def test_daily_challenge_stats_empty(client):
    """GET /api/admin/daily-challenge returns zeros when no challenges."""
    res = client.get("/api/admin/daily-challenge")
    assert res.status_code == 200
    data = res.json()
    assert data["total_participations"] == 0
    assert data["days_active"] == 0
