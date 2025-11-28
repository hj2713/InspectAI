"""Simple LLM client wrapper using OpenAI's chat completion API.

This wrapper centralizes calls to the LLM and makes it easier to mock in
tests. It expects `OPENAI_API_KEY` to be available in the environment (we
create a `.env` file earlier).
"""
from __future__ import annotations

import os
from typing import List, Dict, Any, Optional

from openai import OpenAI
try:
    from bytez import Bytez
except ImportError:
    Bytez = None


class LLMClient:
    def __init__(self, default_model: str = "ibm-granite/granite-4.0-h-tiny", default_temperature: float = 0.2, default_max_tokens: int = 1024, provider: str = "bytez"):
        self.default_model = default_model
        self.default_temperature = default_temperature
        self.default_max_tokens = default_max_tokens
        self.provider = provider
        
        # Map "local" to "bytez" since they use the same API
        if self.provider == "local":
            self.provider = "bytez"
        
        if self.provider == "bytez":
            if Bytez is None:
                raise ImportError("bytez package is not installed. Please install it with `pip install bytez`.")
            api_key = os.getenv("BYTEZ_API_KEY")
            if not api_key:
                raise ValueError("BYTEZ_API_KEY environment variable is not set")
            self.client = Bytez(api_key)
        elif self.provider == "openai":
            api_key = os.getenv("OPENAI_API_KEY")
            if not api_key:
                raise ValueError("OPENAI_API_KEY environment variable is not set")
            self.client = OpenAI(api_key=api_key)
        else:
            raise ValueError(f"Unknown provider: {self.provider}. Supported: 'bytez', 'openai'")

    def chat(self, messages: List[Dict[str, str]], model: Optional[str] = None, temperature: Optional[float] = None, max_tokens: Optional[int] = None) -> str:
        """Send a chat-style request and return the assistant content.

        Args:
            messages: list of messages in the form [{"role": "user"|"system", "content": "..."}, ...]
        """
        model = model or self.default_model
        temperature = self.default_temperature if temperature is None else temperature
        max_tokens = self.default_max_tokens if max_tokens is None else max_tokens

        if self.provider == "bytez":
            # Convert messages to string prompt for Bytez with role labels
            prompt_parts = []
            for msg in messages:
                role = msg.get("role", "user").capitalize()
                content = msg.get("content", "")
                prompt_parts.append(f"{role}: {content}")
            prompt_parts.append("Assistant:") # Prompt for completion
            prompt = "\n".join(prompt_parts)
            
            m = self.client.model(model)
            resp = m.run(prompt)
            
            # Handle Bytez Response object
            if hasattr(resp, 'error') and resp.error:
                raise Exception(f"Bytez API Error: {resp.error}")
            
            if hasattr(resp, 'output') and resp.output:
                return resp.output

            # Handle response assuming it might be a dict with 'output' or direct string
            if isinstance(resp, dict) and 'output' in resp:
                return resp['output']
            return str(resp)
        else:
            resp = self.client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens
            )
            return resp.choices[0].message.content.strip()
