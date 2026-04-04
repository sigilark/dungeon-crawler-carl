import json
import re

import anthropic

from config import ANTHROPIC_API_KEY, MAX_TOKENS, MODEL, SYSTEM_PROMPT

BANNED_NUMBERS = re.compile(r"\b847\b|\b47\b")
BANNED_PHRASES = re.compile(
    r"The dungeon\s+\w+|The sponsors\s+\w+|The security team\s+\w+"
    r"|has been logged|has been noted|has been recorded|has been documented|has been flagged",
    re.IGNORECASE,
)
MAX_RETRIES = 5


def generate(trigger: str | None = None) -> dict:
    """
    Generate a satirical achievement.
    trigger: optional context string (e.g. "spilled coffee again")
    Returns dict with keys: title, description, reward
    """
    if not ANTHROPIC_API_KEY:
        raise OSError("ANTHROPIC_API_KEY is not set. Copy .env.example to .env and add your key.")

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    if trigger:
        user_message = f"Generate a satirical achievement for this event: {trigger}"
    else:
        user_message = "Generate a random satirical achievement."

    def call_api() -> str:
        response = client.messages.create(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_message}],
        )
        return response.content[0].text.strip()

    def strip_markdown(text: str) -> str:
        """Strip markdown code fences from JSON response."""
        text = text.strip()
        match = re.search(r"```(?:json)?\s*(.*?)\s*```", text, re.DOTALL)
        return match.group(1) if match else text

    def has_banned_content(achievement: dict) -> bool:
        """Check if any field contains banned numbers or phrases."""
        text = " ".join(str(v) for v in achievement.values())
        desc_and_reward = achievement.get("description", "") + " " + achievement.get("reward", "")
        return bool(BANNED_NUMBERS.search(text)) or bool(BANNED_PHRASES.search(desc_and_reward))

    for attempt in range(MAX_RETRIES):
        raw = call_api()
        try:
            achievement = json.loads(strip_markdown(raw))
        except json.JSONDecodeError:
            if attempt < MAX_RETRIES - 1:
                continue
            raise ValueError(
                f"Failed to parse achievement JSON after {MAX_RETRIES} attempts.\nRaw response:\n{raw}"
            ) from None
        if not has_banned_content(achievement):
            return achievement
        # Banned content found — retry

    # All retries still have issues; fix what we can
    for key in ("title", "description", "reward"):
        if key in achievement:
            achievement[key] = BANNED_NUMBERS.sub("48", achievement[key])
            # Strip sentences containing banned phrases
            sentences = re.split(r"(?<=[.!?])\s+", achievement[key])
            achievement[key] = " ".join(s for s in sentences if not BANNED_PHRASES.search(s))
    return achievement
