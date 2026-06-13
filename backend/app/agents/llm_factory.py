"""LLM Factory — unified LLM abstraction for multi-model switching.

Every Agent gets its LLM client through this factory, so we can:
- Change models per agent without touching agent code
- Track token usage
- Fall back gracefully when an API is unavailable

Supported backends:
- openai    — OpenAI-compatible API (GPT-4o, GPT-4o-mini, DeepSeek via proxy)
- deepseek  — DeepSeek native API (V3, R1)
- anthropic — Claude models
"""

import os
from typing import Optional, Dict, Any, Literal
from dataclasses import dataclass, field


Provider = Literal["openai", "deepseek", "anthropic"]


@dataclass
class ModelConfig:
    """Configuration for a single LLM call."""
    provider: Provider = "openai"
    model: str = ""
    api_key: str = ""
    base_url: str = ""
    temperature: float = 0.3
    max_tokens: int = 2048
    json_mode: bool = False           # request structured JSON output
    extra_headers: Dict[str, str] = field(default_factory=dict)


class LLMFactory:
    """Factory that returns the right async client for a given config.

    Usage:
        factory = LLMFactory()
        result = await factory.generate(
            system_prompt="You are...",
            user_prompt="User says...",
            config=ModelConfig(provider="deepseek", model="deepseek-chat"),
        )
    """

    def __init__(self):
        self._clients: Dict[str, Any] = {}

    # ── Public API ──────────────────────────────────────────

    async def generate(
        self,
        system_prompt: str,
        user_prompt: str,
        config: Optional[ModelConfig] = None,
        *,
        messages: Optional[list] = None,
    ) -> Dict[str, Any]:
        """Generate a completion. Returns {text, provider, model, usage}.

        Pass either (system_prompt + user_prompt) or a full `messages` list.
        """
        if config is None:
            config = self._default_config()

        if messages is None:
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ]

        if config.provider == "anthropic":
            return await self._call_anthropic(messages, config)
        else:
            # openai / deepseek both use the OpenAI-compatible API
            return await self._call_openai_compatible(messages, config)

    async def generate_json(
        self,
        system_prompt: str,
        user_prompt: str,
        config: Optional[ModelConfig] = None,
    ) -> Dict[str, Any]:
        """Generate a JSON completion (guaranteed structured output)."""
        if config is None:
            config = self._default_config()
        config.json_mode = True
        return await self.generate(system_prompt, user_prompt, config)

    def get_config_for_agent(
        self,
        agent_name: str,
        *,
        provider: Optional[Provider] = None,
        model: Optional[str] = None,
    ) -> ModelConfig:
        """Build a ModelConfig tailored to a specific agent.

        Each agent can be assigned a different model via env vars:
          <AGENT>_LLM_PROVIDER, <AGENT>_LLM_MODEL
        Falls back to global LLM_PROVIDER / LLM_MODEL / OPENAI_MODEL.
        """
        env_prefix = agent_name.upper()

        p = (
            provider
            or os.getenv(f"{env_prefix}_LLM_PROVIDER")
            or os.getenv("LLM_PROVIDER", "openai")
        )
        m = (
            model
            or os.getenv(f"{env_prefix}_LLM_MODEL")
            or os.getenv("OPENAI_MODEL", "gpt-4o-mini")
        )

        api_key = ""
        base_url = ""
        if p == "openai":
            api_key = os.getenv("OPENAI_API_KEY", "")
            base_url = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
        elif p == "deepseek":
            api_key = os.getenv("DEEPSEEK_API_KEY", os.getenv("OPENAI_API_KEY", ""))
            base_url = os.getenv(
                "DEEPSEEK_BASE_URL",
                "https://api.deepseek.com/v1",
            )
        elif p == "anthropic":
            api_key = os.getenv("ANTHROPIC_API_KEY", "")
            base_url = ""

        return ModelConfig(
            provider=p,
            model=m,
            api_key=api_key,
            base_url=base_url,
        )

    # ── Backend implementations ─────────────────────────────

    async def _call_openai_compatible(
        self, messages: list, config: ModelConfig
    ) -> Dict[str, Any]:
        import json
        from openai import AsyncOpenAI

        client = AsyncOpenAI(
            api_key=config.api_key,
            base_url=config.base_url,
        )

        kwargs: Dict[str, Any] = {
            "model": config.model,
            "messages": messages,
            "temperature": config.temperature,
            "max_tokens": config.max_tokens,
        }

        if config.json_mode:
            kwargs["response_format"] = {"type": "json_object"}

        response = await client.chat.completions.create(**kwargs)
        choice = response.choices[0]
        text = choice.message.content or ""

        usage = {}
        if response.usage:
            usage = {
                "prompt_tokens": response.usage.prompt_tokens,
                "completion_tokens": response.usage.completion_tokens,
                "total_tokens": response.usage.total_tokens,
            }

        return {
            "text": text,
            "provider": config.provider,
            "model": config.model,
            "usage": usage,
        }

    async def _call_anthropic(
        self, messages: list, config: ModelConfig
    ) -> Dict[str, Any]:
        import anthropic

        client = anthropic.AsyncAnthropic(api_key=config.api_key)

        # Anthropic doesn't support system message in the messages list
        system = ""
        user_messages = []
        for m in messages:
            if m["role"] == "system":
                system = m["content"]
            else:
                user_messages.append(m)

        response = await client.messages.create(
            model=config.model or "claude-sonnet-4-20250514",
            system=system,
            messages=user_messages,
            max_tokens=config.max_tokens,
            temperature=config.temperature,
        )

        text = response.content[0].text if response.content else ""
        usage = {}
        if hasattr(response, "usage"):
            usage = {
                "input_tokens": response.usage.input_tokens,
                "output_tokens": response.usage.output_tokens,
                "total_tokens": response.usage.input_tokens + response.usage.output_tokens,
            }

        return {
            "text": text,
            "provider": "anthropic",
            "model": config.model,
            "usage": usage,
        }

    def _default_config(self) -> ModelConfig:
        """Return the default model config from environment."""
        return self.get_config_for_agent("default")


# ── Singleton ───────────────────────────────────────────────

llm_factory = LLMFactory()
