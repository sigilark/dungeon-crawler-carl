"""
Shareable achievement card — renders a PNG image of an achievement.
Dark theme with gold accents, matching the web UI aesthetic.
"""

import textwrap
from io import BytesIO
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

# Colors matching the web UI
BG_COLOR = (26, 26, 46)        # #1a1a2e
CARD_BG = (22, 33, 62)         # #16213e
GOLD = (240, 192, 64)          # #f0c040
TEXT_COLOR = (224, 224, 224)    # #e0e0e0
DIM_TEXT = (136, 136, 136)     # #888888
BORDER_COLOR = (240, 192, 64)  # #f0c040
DIVIDER_COLOR = (51, 51, 51)   # #333333

CARD_WIDTH = 800
CARD_PADDING = 40
INNER_WIDTH = CARD_WIDTH - (CARD_PADDING * 2)


def _get_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    """Get a monospace font, falling back to default if not available."""
    font_names = [
        "Courier New Bold" if bold else "Courier New",
        "DejaVu Sans Mono Bold" if bold else "DejaVu Sans Mono",
        "monospace",
    ]
    for name in font_names:
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default(size)


def render_card(achievement: dict) -> bytes:
    """
    Render an achievement as a shareable PNG card.
    Returns PNG bytes.
    """
    title = achievement.get("title", "Unknown Achievement")
    description = achievement.get("description", "")
    reward = achievement.get("reward", "")

    # Strip announcer tags from description for display
    desc_clean = description
    if desc_clean.lower().startswith("new achievement!"):
        desc_clean = desc_clean[len("new achievement!"):].strip()
    if desc_clean.lower().endswith("your reward!"):
        desc_clean = desc_clean[: -len("your reward!")].strip()

    # Fonts
    font_header = _get_font(14, bold=True)
    font_title = _get_font(28, bold=True)
    font_body = _get_font(18)
    font_label = _get_font(16, bold=True)
    font_reward = _get_font(18)
    font_watermark = _get_font(12)

    # Wrap text
    desc_lines = textwrap.wrap(desc_clean, width=52)
    reward_lines = textwrap.wrap(reward, width=48)

    # Calculate card height dynamically
    line_height_body = 26
    line_height_reward = 26
    card_height = (
        CARD_PADDING          # top padding
        + 30                  # header badge
        + 20                  # gap
        + 36                  # title
        + 20                  # gap
        + len(desc_lines) * line_height_body  # description
        + 24                  # gap
        + 2                   # divider
        + 20                  # gap
        + len(reward_lines) * line_height_reward  # reward
        + 30                  # gap
        + 16                  # watermark
        + CARD_PADDING        # bottom padding
    )

    # Create image with border
    border = 3
    img_width = CARD_WIDTH + border * 2
    img_height = card_height + border * 2
    img = Image.new("RGB", (img_width, img_height), BORDER_COLOR)
    card = Image.new("RGB", (CARD_WIDTH, card_height), CARD_BG)
    img.paste(card, (border, border))

    draw = ImageDraw.Draw(img)
    x = CARD_PADDING + border
    y = CARD_PADDING + border

    # Header badge
    badge_text = "ACHIEVEMENT UNLOCKED"
    bbox = draw.textbbox((0, 0), badge_text, font=font_header)
    badge_w = bbox[2] - bbox[0] + 16
    badge_h = bbox[3] - bbox[1] + 10
    draw.rectangle([x, y, x + badge_w, y + badge_h], fill=GOLD)
    draw.text((x + 8, y + 4), badge_text, fill=BG_COLOR, font=font_header)
    y += badge_h + 20

    # Title with star
    draw.text((x, y), f"\u2605  {title}", fill=GOLD, font=font_title)
    y += 36 + 20

    # Description
    for line in desc_lines:
        draw.text((x, y), line, fill=TEXT_COLOR, font=font_body)
        y += line_height_body
    y += 24

    # Divider
    draw.line([(x, y), (x + INNER_WIDTH, y)], fill=DIVIDER_COLOR, width=2)
    y += 2 + 20

    # Reward
    draw.text((x, y), "REWARD", fill=GOLD, font=font_label)
    y += 24
    for line in reward_lines:
        draw.text((x + 4, y), line, fill=TEXT_COLOR, font=font_reward)
        y += line_height_reward
    y += 14

    # Watermark
    draw.text(
        (x, y),
        "The Dungeon Intercom \u2022 achievement.sigilark.com",
        fill=DIM_TEXT,
        font=font_watermark,
    )

    # Export PNG
    buf = BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()
