"""Additional card tests — badges, dates, triggers on share PNG."""

from io import BytesIO

from PIL import Image

from card import render_card


def test_card_with_badge():
    """Card renders with a badge icon (no crash, valid PNG)."""
    data = render_card(
        {
            "title": "Test",
            "badge": "skull",
            "description": "Test desc.",
            "reward": "Test reward.",
        }
    )
    img = Image.open(BytesIO(data))
    assert img.format == "PNG"
    assert img.width >= 2400


def test_card_with_invalid_badge():
    """Card falls back to star when badge SVG doesn't exist."""
    data = render_card(
        {
            "title": "Test",
            "badge": "nonexistent-icon",
            "description": "Test desc.",
            "reward": "Test reward.",
        }
    )
    img = Image.open(BytesIO(data))
    assert img.format == "PNG"


def test_card_with_date():
    """Card renders with a date string."""
    data = render_card(
        {
            "title": "Test",
            "description": "Test desc.",
            "reward": "Test reward.",
            "timestamp": "2026-04-02T10:30:00",
        }
    )
    img = Image.open(BytesIO(data))
    assert img.format == "PNG"


def test_card_with_trigger():
    """Card renders with trigger text."""
    data = render_card(
        {
            "title": "Test",
            "description": "Test desc.",
            "reward": "Test reward.",
            "trigger": "spilled coffee on the keyboard",
        }
    )
    img = Image.open(BytesIO(data))
    assert img.format == "PNG"
    # Card should be taller due to trigger text
    no_trigger = render_card(
        {
            "title": "Test",
            "description": "Test desc.",
            "reward": "Test reward.",
        }
    )
    img_no = Image.open(BytesIO(no_trigger))
    assert img.height > img_no.height


def test_card_with_all_fields():
    """Card renders with every field populated."""
    data = render_card(
        {
            "title": "Corporate Houdini",
            "badge": "ghost",
            "description": "New Achievement! You vanished. Your Reward!",
            "reward": "Nobody noticed.",
            "trigger": "took a 2 hour lunch",
            "timestamp": "2026-04-02T10:30:00",
        }
    )
    img = Image.open(BytesIO(data))
    assert img.format == "PNG"
    assert img.width >= 2400
    assert img.height > 500


def test_card_rarity_bronze():
    """Bronze rarity card renders with bronze-tinted border."""
    data = render_card(
        {
            "title": "Test",
            "badge": "snail",
            "rarity": "bronze",
            "description": "Test desc.",
            "reward": "Test reward.",
        }
    )
    img = Image.open(BytesIO(data))
    # Check top-left border pixel is bronze-ish (205, 127, 50)
    r, g, b = img.getpixel((0, 0))[:3]
    assert r > 150 and g < 180 and b < 100


def test_card_rarity_legendary():
    """Legendary rarity card renders with pink border."""
    data = render_card(
        {
            "title": "Test",
            "badge": "skull",
            "rarity": "legendary",
            "description": "Test desc.",
            "reward": "Test reward.",
        }
    )
    img = Image.open(BytesIO(data))
    # Check border pixel is legendary pink (255, 110, 199)
    r, _g, b = img.getpixel((0, 0))[:3]
    assert r > 200 and b > 150


def test_card_rarity_defaults_to_bronze():
    """Card without rarity field defaults to bronze."""
    data = render_card(
        {
            "title": "Test",
            "description": "Test desc.",
            "reward": "Test reward.",
        }
    )
    img = Image.open(BytesIO(data))
    r, g, b = img.getpixel((0, 0))[:3]
    assert r > 150 and g < 180 and b < 100
