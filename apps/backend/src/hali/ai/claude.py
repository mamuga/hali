import json

import structlog
from anthropic import AsyncAnthropic

from hali.config import Settings

log = structlog.get_logger()
LANGUAGES = ["sw", "so", "am", "om", "ar", "en"]
LIVELIHOODS = ["farmer", "pastoralist", "fisherfolk", "urban"]


class ClaudeService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.client = AsyncAnthropic(api_key=settings.anthropic_api_key) if settings.anthropic_api_key else None

    async def json_prompt(self, prompt: str) -> dict:
        if self.client is None:
            log.warning("claude_disabled", reason="missing_anthropic_api_key")
            return {}
        message = await self.client.messages.create(
            model=self.settings.anthropic_model,
            max_tokens=1200,
            temperature=0.2,
            messages=[{"role": "user", "content": prompt}],
        )
        text = "".join(block.text for block in message.content if hasattr(block, "text"))
        return json.loads(text)
