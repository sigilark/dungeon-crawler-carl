"""
Shareable achievement card — renders a high-DPI PNG image of an achievement.
Dark theme with gold accents, matching the web UI aesthetic.
Rendered at 3x scale for sharp text on retina/high-DPI displays.
"""

import textwrap
from datetime import datetime
from io import BytesIO

import cairosvg
from PIL import Image, ImageDraw, ImageFont

from config import PROJECT_ROOT

BADGE_DIR = PROJECT_ROOT / "static" / "badges"

# Colors matching the web UI
BG_COLOR = (26, 26, 46)  # #1a1a2e
CARD_BG = (22, 33, 62)  # #16213e
GOLD = (240, 192, 64)  # #f0c040
TEXT_COLOR = (224, 224, 224)  # #e0e0e0
DIM_TEXT = (136, 136, 136)  # #888888
BORDER_COLOR = (240, 192, 64)  # #f0c040
DIVIDER_COLOR = (51, 51, 51)  # #333333

# Rarity tier colors — used for border, badge tint, title, and REWARD label.
# Must match the CSS variables in static/index.html (.rarity-bronze, etc.)
RARITY_COLORS = {
    "bronze": (205, 127, 50),  # #cd7f32
    "silver": (192, 192, 192),  # #c0c0c0
    "gold": (240, 192, 64),  # #f0c040
    "legendary": (255, 110, 199),  # #ff6ec7
}

# Render at 3x for crisp text — final image is 2400px wide
SCALE = 3
CARD_WIDTH = 800 * SCALE
CARD_PADDING = 40 * SCALE
INNER_WIDTH = CARD_WIDTH - (CARD_PADDING * 2)
BORDER = 3 * SCALE


def _s(val: int) -> int:
    """Scale a value by the render multiplier."""
    return val * SCALE


def _load_badge(badge_id: str, size: int, tint: tuple[int, int, int] = GOLD) -> Image.Image | None:
    """Load an SVG badge, render at given size, and tint to the specified color."""
    svg_path = BADGE_DIR / f"{badge_id}.svg"
    if not svg_path.exists():
        return None
    png_data = cairosvg.svg2png(url=str(svg_path), output_width=size, output_height=size)
    badge = Image.open(BytesIO(png_data)).convert("RGBA")
    # Tint — replace black pixels with the specified color
    pixels = badge.load()
    for y in range(badge.height):
        for x in range(badge.width):
            _r, _g, _b, a = pixels[x, y]
            if a > 0:
                pixels[x, y] = (tint[0], tint[1], tint[2], a)
    return badge


def _get_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    """Get a monospace font at scaled size, falling back to default."""
    scaled = size * SCALE
    font_names = [
        "Courier New Bold" if bold else "Courier New",
        "DejaVu Sans Mono Bold" if bold else "DejaVu Sans Mono",
        "monospace",
    ]
    for name in font_names:
        try:
            return ImageFont.truetype(name, scaled)
        except OSError:
            continue
    return ImageFont.load_default(scaled)


def render_card(achievement: dict) -> bytes:
    """
    Render an achievement as a shareable high-DPI PNG card.
    Returns PNG bytes.
    """
    title = achievement.get("title", "Unknown Achievement")
    badge_id = achievement.get("badge", "")
    rarity = achievement.get("rarity", "bronze")
    description = achievement.get("description", "")
    reward = achievement.get("reward", "")
    trigger = achievement.get("trigger", "")
    timestamp = achievement.get("timestamp", "")

    # Rarity determines border and accent color
    accent = RARITY_COLORS.get(rarity, RARITY_COLORS["bronze"])

    # Strip announcer tags from description for display
    desc_clean = description
    if desc_clean.lower().startswith("new achievement!"):
        desc_clean = desc_clean[len("new achievement!") :].strip()
    if desc_clean.lower().endswith("your reward!"):
        desc_clean = desc_clean[: -len("your reward!")].strip()

    # Fonts (base sizes, scaled internally by _get_font)
    font_header = _get_font(14, bold=True)
    font_title = _get_font(28, bold=True)
    font_body = _get_font(18)
    font_label = _get_font(16, bold=True)
    font_reward = _get_font(18)
    font_trigger = _get_font(13)
    font_watermark = _get_font(12)

    # Wrap text
    trigger_lines = textwrap.wrap(f'"{trigger}"', width=58) if trigger else []
    desc_lines = textwrap.wrap(desc_clean, width=52)
    reward_lines = textwrap.wrap(reward, width=48)

    # Calculate card height dynamically (all values scaled)
    line_height_trigger = _s(20)
    line_height_body = _s(26)
    line_height_reward = _s(26)
    card_height = (
        CARD_PADDING
        + _s(30)  # header badge
        + (len(trigger_lines) * line_height_trigger + _s(10) if trigger_lines else 0)  # trigger
        + _s(20)  # gap
        + _s(36)  # title
        + _s(20)  # gap
        + len(desc_lines) * line_height_body  # description
        + _s(24)  # gap
        + _s(2)  # divider
        + _s(20)  # gap
        + _s(24)  # REWARD label
        + len(reward_lines) * line_height_reward  # reward
        + _s(30)  # gap
        + _s(16)  # watermark
        + CARD_PADDING
    )

    # Create image with rarity-colored border
    img_width = CARD_WIDTH + BORDER * 2
    img_height = card_height + BORDER * 2
    img = Image.new("RGB", (img_width, img_height), accent)
    card = Image.new("RGB", (CARD_WIDTH, card_height), CARD_BG)
    img.paste(card, (BORDER, BORDER))

    draw = ImageDraw.Draw(img)
    x = CARD_PADDING + BORDER
    y = CARD_PADDING + BORDER

    # Header badge
    badge_text = "ACHIEVEMENT UNLOCKED"
    bbox = draw.textbbox((0, 0), badge_text, font=font_header)
    badge_w = bbox[2] - bbox[0] + _s(16)
    badge_h = bbox[3] - bbox[1] + _s(10)
    draw.rectangle([x, y, x + badge_w, y + badge_h], fill=accent)
    draw.text((x + _s(8), y + _s(4)), badge_text, fill=BG_COLOR, font=font_header)

    # Rarity label — right of the header badge
    rarity_label = rarity.upper()
    draw.text((x + badge_w + _s(10), y + _s(4)), rarity_label, fill=accent, font=font_header)

    # Date — right-aligned on the same line as the badge
    if timestamp:
        try:
            dt = datetime.fromisoformat(timestamp)
            date_str = dt.strftime("%b %d, %Y")
        except (ValueError, TypeError):
            date_str = ""
        if date_str:
            date_bbox = draw.textbbox((0, 0), date_str, font=font_watermark)
            date_w = date_bbox[2] - date_bbox[0]
            draw.text(
                (x + INNER_WIDTH - date_w, y + _s(4)), date_str, fill=DIM_TEXT, font=font_watermark
            )

    y += badge_h + _s(10)

    # Trigger text (what the user entered)
    if trigger_lines:
        for line in trigger_lines:
            draw.text((x, y), line, fill=DIM_TEXT, font=font_trigger)
            y += line_height_trigger
        y += _s(10)
    else:
        y += _s(10)

    # Title with badge (or star fallback)
    badge_size = _s(28)
    badge_img = _load_badge(badge_id, badge_size, tint=accent) if badge_id else None
    if badge_img:
        img.paste(badge_img, (x, y + _s(2)), badge_img)
        draw.text((x + badge_size + _s(8), y), title, fill=accent, font=font_title)
    else:
        draw.text((x, y), f"\u2605  {title}", fill=accent, font=font_title)
    y += _s(36) + _s(20)

    # Description
    for line in desc_lines:
        draw.text((x, y), line, fill=TEXT_COLOR, font=font_body)
        y += line_height_body
    y += _s(24)

    # Divider
    draw.line([(x, y), (x + INNER_WIDTH, y)], fill=DIVIDER_COLOR, width=_s(2))
    y += _s(2) + _s(20)

    # Reward
    draw.text((x, y), "REWARD", fill=accent, font=font_label)
    y += _s(24)
    for line in reward_lines:
        draw.text((x + _s(4), y), line, fill=TEXT_COLOR, font=font_reward)
        y += line_height_reward
    y += _s(14)

    # Watermark
    draw.text(
        (x, y),
        "The Crawl Log \u2022 crawl.sigilark.com",
        fill=DIM_TEXT,
        font=font_watermark,
    )

    # Export PNG
    buf = BytesIO()
    img.save(buf, format="PNG", dpi=(216, 216))  # 72 * 3 = 216 DPI
    return buf.getvalue()
