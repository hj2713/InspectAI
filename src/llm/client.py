"""LLM client wrapper supporting multiple providers.

Supported providers:
- bytez: Bytez API (default)
- openai: OpenAI GPT models
- gemini: Google Gemini models

This wrapper centralizes calls to LLMs and makes it easier to switch providers.
"""
from __future__ import annotations

import os
import requests
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
        elif self.provider == "gemini":
            api_key = os.getenv("GEMINI_API_KEY")
            if not api_key:
                raise ValueError("GEMINI_API_KEY environment variable is not set")
            self.gemini_api_key = api_key
            self.client = None  # Gemini uses direct HTTP requests
        else:
            raise ValueError(f"Unknown provider: {self.provider}. Supported: 'bytez', 'openai', 'gemini'")

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
        
        elif self.provider == "gemini":
            return self._chat_gemini(messages, model, temperature, max_tokens)
        
        else:  # openai
            resp = self.client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens
            )
            return resp.choices[0].message.content.strip()
    
    def _chat_gemini(self, messages: List[Dict[str, str]], model: str, temperature: float, max_tokens: int) -> str:
        """Send a chat request to Google Gemini API.
        
        Args:
            messages: list of messages in the form [{"role": "user"|"system", "content": "..."}, ...]
            model: Gemini model name (e.g., "gemini-2.0-flash")
            temperature: Sampling temperature
            max_tokens: Maximum tokens in response
            
        Returns:
            The assistant's response text
        """
        # Convert messages to Gemini format
        # Gemini uses "contents" with "parts" structure
        contents = []
        system_instruction = None
        
        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            
            # Handle system messages - Gemini uses systemInstruction
            if role == "system":
                system_instruction = content
                continue
            
            # Map roles: user -> user, assistant -> model
            gemini_role = "model" if role == "assistant" else "user"
            contents.append({
                "role": gemini_role,
                "parts": [{"text": content}]
            })
        
        # If no user messages, create one from system instruction
        if not contents and system_instruction:
            contents.append({
                "role": "user",
                "parts": [{"text": system_instruction}]
            })
            system_instruction = None
        
        # Build request payload
        payload = {
            "contents": contents,
            "generationConfig": {
                "temperature": temperature,
                "maxOutputTokens": max_tokens
            }
        }
        
        # Add system instruction if present
        if system_instruction:
            payload["systemInstruction"] = {
                "parts": [{"text": system_instruction}]
            }
        
        # Make API request
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
        headers = {
            "x-goog-api-key": self.gemini_api_key,
            "Content-Type": "application/json"
        }
        
        response = requests.post(url, headers=headers, json=payload, timeout=60)
        
        if response.status_code != 200:
            raise Exception(f"Gemini API Error: {response.status_code} - {response.text}")
        
        data = response.json()
        
        # Extract text from response
        try:
            candidates = data.get("candidates", [])
            if candidates:
                parts = candidates[0].get("content", {}).get("parts", [])
                if parts:
                    return parts[0].get("text", "").strip()
            raise Exception("No response content from Gemini")
        except (KeyError, IndexError) as e:
            raise Exception(f"Failed to parse Gemini response: {e} - {data}")
