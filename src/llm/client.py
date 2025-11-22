"""Simple LLM client wrapper using OpenAI's chat completion API.

This wrapper centralizes calls to the LLM and makes it easier to mock in
tests. It expects `OPENAI_API_KEY` to be available in the environment (we
create a `.env` file earlier).
"""
from __future__ import annotations

import os
from typing import List, Dict, Any, Optional

from openai import OpenAI


class LLMClient:
    def __init__(self, default_model: str = "gpt-4", default_temperature: float = 0.2, default_max_tokens: int = 1024):
        self.default_model = default_model
        self.default_temperature = default_temperature
        self.default_max_tokens = default_max_tokens
        # configure API key from env; main usually loads .env
        self.client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    def chat(self, messages: List[Dict[str, str]], model: Optional[str] = None, temperature: Optional[float] = None, max_tokens: Optional[int] = None) -> str:
        """Send a chat-style request and return the assistant content.

        Args:
            messages: list of messages in the form [{"role": "user"|"system", "content": "..."}, ...]
        """
        model = model or self.default_model
        temperature = self.default_temperature if temperature is None else temperature
        max_tokens = self.default_max_tokens if max_tokens is None else max_tokens

        resp = self.client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens
        )
        return resp.choices[0].message.content.strip()
