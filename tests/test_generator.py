import json
from unittest.mock import MagicMock, patch

import pytest

SAMPLE_ACHIEVEMENT = {
    "title": "Baptism by Arabica",
    "description": "New Achievement! You hydrated your keyboard. Reward!",
    "reward": "+5 to Perceived Momentum",
}


def _mock_response(text: str) -> MagicMock:
    """Build a mock Anthropic response with the given text content."""
    block = MagicMock()
    block.text = text
    response = MagicMock()
    response.content = [block]
    return response


@patch("generator.ANTHROPIC_API_KEY", "sk-test")
@patch("generator.anthropic.Anthropic")
def test_generate_with_trigger(mock_cls):
    """generate() with a trigger sends context-aware user message."""
    from generator import generate

    client = MagicMock()
    mock_cls.return_value = client
    client.messages.create.return_value = _mock_response(json.dumps(SAMPLE_ACHIEVEMENT))

    result = generate(trigger="spilled coffee")

    assert result == SAMPLE_ACHIEVEMENT
    call_kwargs = client.messages.create.call_args[1]
    assert "spilled coffee" in call_kwargs["messages"][0]["content"]


@patch("generator.ANTHROPIC_API_KEY", "sk-test")
@patch("generator.anthropic.Anthropic")
def test_generate_random(mock_cls):
    """generate() without a trigger sends a random-achievement message."""
    from generator import generate

    client = MagicMock()
    mock_cls.return_value = client
    client.messages.create.return_value = _mock_response(json.dumps(SAMPLE_ACHIEVEMENT))

    result = generate(trigger=None)

    assert result == SAMPLE_ACHIEVEMENT
    call_kwargs = client.messages.create.call_args[1]
    assert "random" in call_kwargs["messages"][0]["content"].lower()


@patch("generator.ANTHROPIC_API_KEY", "sk-test")
@patch("generator.anthropic.Anthropic")
def test_generate_retries_on_bad_json(mock_cls):
    """generate() retries when the first response is not valid JSON."""
    from generator import generate

    client = MagicMock()
    mock_cls.return_value = client
    client.messages.create.side_effect = [
        _mock_response("this is not json"),
        _mock_response(json.dumps(SAMPLE_ACHIEVEMENT)),
    ]

    result = generate()
    assert result == SAMPLE_ACHIEVEMENT
    assert client.messages.create.call_count == 2


@patch("generator.ANTHROPIC_API_KEY", "sk-test")
@patch("generator.anthropic.Anthropic")
def test_generate_raises_after_max_failures(mock_cls):
    """generate() raises ValueError after MAX_RETRIES consecutive JSON parse failures."""
    from generator import generate

    client = MagicMock()
    mock_cls.return_value = client
    client.messages.create.side_effect = [
        _mock_response("bad json 1"),
        _mock_response("bad json 2"),
        _mock_response("bad json 3"),
        _mock_response("bad json 4"),
        _mock_response("bad json 5"),
    ]

    with pytest.raises(ValueError, match="Failed to parse"):
        generate()


@patch("generator.ANTHROPIC_API_KEY", "sk-test")
@patch("generator.anthropic.Anthropic")
def test_generate_retries_on_banned_numbers(mock_cls):
    """generate() retries when response contains banned numbers 47 or 847."""
    from generator import generate

    banned = {
        "title": "Floor 47 Incident",
        "description": "New Achievement! You fell 847 times. Your Reward!",
        "reward": "+47 to Shame",
    }
    clean = SAMPLE_ACHIEVEMENT

    client = MagicMock()
    mock_cls.return_value = client
    client.messages.create.side_effect = [
        _mock_response(json.dumps(banned)),
        _mock_response(json.dumps(clean)),
    ]

    result = generate()
    assert result == clean
    assert client.messages.create.call_count == 2


@patch("generator.ANTHROPIC_API_KEY", "sk-test")
@patch("generator.anthropic.Anthropic")
def test_generate_replaces_banned_after_exhausting_retries(mock_cls):
    """generate() replaces banned numbers with 48 if all retries still contain them."""
    from generator import generate

    banned = {
        "title": "Test",
        "description": "New Achievement! You waited 47 hours. Your Reward!",
        "reward": "+847 to Nothing",
    }

    client = MagicMock()
    mock_cls.return_value = client
    client.messages.create.return_value = _mock_response(json.dumps(banned))

    result = generate()
    assert "47" not in result["description"]
    assert "847" not in result["reward"]
    assert "48" in result["description"]
    assert "48" in result["reward"]


@patch("generator.ANTHROPIC_API_KEY", "sk-test")
@patch("generator.anthropic.Anthropic")
def test_generate_retries_on_banned_phrases(mock_cls):
    """generate() retries when description contains 'The dungeon...' pattern."""
    from generator import generate

    banned = {
        "title": "Test",
        "description": "New Achievement! The dungeon respects your commitment. Your Reward!",
        "reward": "+5 to Nothing",
    }
    clean = SAMPLE_ACHIEVEMENT

    client = MagicMock()
    mock_cls.return_value = client
    client.messages.create.side_effect = [
        _mock_response(json.dumps(banned)),
        _mock_response(json.dumps(clean)),
    ]

    result = generate()
    assert result == clean
    assert client.messages.create.call_count == 2


@patch("generator.ANTHROPIC_API_KEY", "sk-test")
@patch("generator.anthropic.Anthropic")
def test_generate_strips_banned_phrases_after_exhausting_retries(mock_cls):
    """generate() strips sentences with banned phrases if all retries fail."""
    from generator import generate

    banned = {
        "title": "Test",
        "description": "New Achievement! You did something. The dungeon respects your effort. Your Reward!",
        "reward": "A prize.",
    }

    client = MagicMock()
    mock_cls.return_value = client
    client.messages.create.return_value = _mock_response(json.dumps(banned))

    result = generate()
    assert "The dungeon" not in result["description"]
    assert "New Achievement!" in result["description"]
    assert "Your Reward!" in result["description"]


@patch("generator.ANTHROPIC_API_KEY", "sk-test")
@patch("generator.anthropic.Anthropic")
def test_generate_retries_on_sponsors_phrase(mock_cls):
    """generate() retries when description contains 'The sponsors...' pattern."""
    from generator import generate

    banned = {
        "title": "Test",
        "description": "New Achievement! The sponsors are thrilled. Your Reward!",
        "reward": "Nothing.",
    }
    clean = SAMPLE_ACHIEVEMENT

    client = MagicMock()
    mock_cls.return_value = client
    client.messages.create.side_effect = [
        _mock_response(json.dumps(banned)),
        _mock_response(json.dumps(clean)),
    ]

    result = generate()
    assert result == clean


@patch("generator.ANTHROPIC_API_KEY", "")
def test_generate_missing_api_key():
    """generate() raises EnvironmentError when API key is empty."""
    from generator import generate

    with pytest.raises(EnvironmentError, match="ANTHROPIC_API_KEY"):
        generate()


@patch("generator.ANTHROPIC_API_KEY", "sk-test")
@patch("generator.anthropic.Anthropic")
def test_generate_uses_system_prompt(mock_cls):
    """generate() passes the system prompt to the API call."""
    from generator import generate

    client = MagicMock()
    mock_cls.return_value = client
    client.messages.create.return_value = _mock_response(json.dumps(SAMPLE_ACHIEVEMENT))

    generate()

    call_kwargs = client.messages.create.call_args[1]
    assert "Crawl Log" in call_kwargs["system"]


@patch("generator.ANTHROPIC_API_KEY", "sk-test")
@patch("generator.anthropic.Anthropic")
def test_generate_passes_model_and_max_tokens(mock_cls):
    """generate() passes MODEL and MAX_TOKENS from config."""
    from generator import MAX_TOKENS, MODEL, generate

    client = MagicMock()
    mock_cls.return_value = client
    client.messages.create.return_value = _mock_response(json.dumps(SAMPLE_ACHIEVEMENT))

    generate()

    call_kwargs = client.messages.create.call_args[1]
    assert call_kwargs["model"] == MODEL
    assert call_kwargs["max_tokens"] == MAX_TOKENS
