from __future__ import annotations

import os
import requests
import logging
from typing import List, Dict, Any, Optional

from openai import OpenAI
try:
    from bytez import Bytez
except ImportError:
    Bytez = None

# Set up logging
logger = logging.getLogger(__name__)


# class LLMClient:
    def __init__(self, default_model: str = "ibm-granite/granite-4.0-h-tiny", default_temperature: float = 0.2, default_max_tokens: int = 1024, provider: str = "bytez"):
        self.default_model = default_model
        self.default_temperature = default_temperature
        self.default_max_tokens = default_max_tokens
        self.provider = provider
        
        logger.info(f"[LLMClient] Initializing with provider: {provider}, model: {default_model}")
        
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
            logger.info("[LLMClient] Bytez client initialized successfully")
        elif self.provider == "openai":
            api_key = os.getenv("OPENAI_API_KEY")
            if not api_key:
                raise ValueError("OPENAI_API_KEY environment variable is not set")
            self.client = OpenAI(api_key=api_key)
            logger.info("[LLMClient] OpenAI client initialized successfully")
        elif self.provider == "gemini":
            api_key = os.getenv("GEMINI_API_KEY")
            if not api_key:
                raise ValueError("GEMINI_API_KEY environment variable is not set")
            self.gemini_api_key = api_key
            self.client = None  # Gemini uses direct HTTP requests
            logger.info("[LLMClient] Gemini client initialized successfully")
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

        logger.info(f"[LLMClient.chat] Provider: {self.provider}, Model: {model}")
        logger.info(f"[LLMClient.chat] Temperature: {temperature}, Max tokens: {max_tokens}")
        logger.info(f"[LLMClient.chat] Number of messages: {len(messages)}")
        
        # Log first message preview (truncated)
        if messages:
            first_content = messages[0].get("content", "")[:200]
            logger.debug(f"[LLMClient.chat] First message preview: {first_content}...")

        if self.provider == "bytez":
            # Convert messages to string prompt for Bytez with role labels
            prompt_parts = []
            for msg in messages:
                role = msg.get("role", "user").capitalize()
                content = msg.get("content", "")
                prompt_parts.append(f"{role}: {content}")
            prompt_parts.append("Assistant:") # Prompt for completion
            prompt = "\n".join(prompt_parts)
            
            logger.info(f"[LLMClient.chat] Calling Bytez API...")
            m = self.client.model(model)
            resp = m.run(prompt)
            
            # Handle Bytez Response object
            if hasattr(resp, 'error') and resp.error:
                logger.error(f"[LLMClient.chat] Bytez API Error: {resp.error}")
                raise Exception(f"Bytez API Error: {resp.error}")
            
            if hasattr(resp, 'output') and resp.output:
                logger.info(f"[LLMClient.chat] Bytez response received, length: {len(resp.output)}")
                logger.debug(f"[LLMClient.chat] Bytez response preview: {resp.output[:500]}...")
                return resp.output

            # Handle response assuming it might be a dict with 'output' or direct string
            if isinstance(resp, dict) and 'output' in resp:
                logger.info(f"[LLMClient.chat] Bytez dict response received")
                return resp['output']
            logger.warning(f"[LLMClient.chat] Bytez unexpected response type: {type(resp)}")
            return str(resp)
        
        elif self.provider == "gemini":
            return self._chat_gemini(messages, model, temperature, max_tokens)
        
        else:  # openai
            logger.info(f"[LLMClient.chat] Calling OpenAI API...")
            resp = self.client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens
            )
            result = resp.choices[0].message.content.strip()
            logger.info(f"[LLMClient.chat] OpenAI response received, length: {len(result)}")
            logger.debug(f"[LLMClient.chat] OpenAI response preview: {result[:500]}...")
            return result
    
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
        logger.info(f"[LLMClient._chat_gemini] Preparing request for model: {model}")
        
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
                logger.debug(f"[LLMClient._chat_gemini] System instruction length: {len(content)}")
                continue
            
            # Map roles: user -> user, assistant -> model
            gemini_role = "model" if role == "assistant" else "user"
            contents.append({
                "role": gemini_role,
                "parts": [{"text": content}]
            })
        
        logger.info(f"[LLMClient._chat_gemini] Contents count: {len(contents)}, Has system instruction: {system_instruction is not None}")
        
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
        
        logger.info(f"[LLMClient._chat_gemini] Sending request to Gemini API...")
        logger.debug(f"[LLMClient._chat_gemini] URL: {url}")
        
        try:
            response = requests.post(url, headers=headers, json=payload, timeout=60)
            logger.info(f"[LLMClient._chat_gemini] Response status code: {response.status_code}")
        except requests.exceptions.Timeout:
            logger.error("[LLMClient._chat_gemini] Request timed out after 60 seconds")
            raise Exception("Gemini API request timed out")
        except requests.exceptions.RequestException as e:
            logger.error(f"[LLMClient._chat_gemini] Request failed: {e}")
            raise
        
        if response.status_code != 200:
            logger.error(f"[LLMClient._chat_gemini] API Error: {response.status_code} - {response.text[:500]}")
            raise Exception(f"Gemini API Error: {response.status_code} - {response.text}")
        
        data = response.json()
        logger.debug(f"[LLMClient._chat_gemini] Response data keys: {data.keys()}")
        
        # Extract text from response
        try:
            candidates = data.get("candidates", [])
            logger.info(f"[LLMClient._chat_gemini] Number of candidates: {len(candidates)}")
            
            if candidates:
                parts = candidates[0].get("content", {}).get("parts", [])
                logger.info(f"[LLMClient._chat_gemini] Number of parts: {len(parts)}")
                
                if parts:
                    result = parts[0].get("text", "").strip()
                    logger.info(f"[LLMClient._chat_gemini] Response received, length: {len(result)}")
                    logger.debug(f"[LLMClient._chat_gemini] Response preview: {result[:500]}...")
                    return result
            
            logger.error(f"[LLMClient._chat_gemini] No response content. Full response: {data}")
            raise Exception("No response content from Gemini")
        except (KeyError, IndexError) as e:
            logger.error(f"[LLMClient._chat_gemini] Failed to parse response: {e} - {data}")
            raise Exception(f"Failed to parse Gemini response: {e} - {data}")
            raise Exception(f"Failed to parse Gemini response: {e} - {data}")
