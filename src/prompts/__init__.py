"""Structured prompt system for high-quality LLM code reviews.

This module provides:
- PromptBuilder: Constructs structured prompts with context and examples
- Few-shot examples: Pre-built examples for each language and issue type
- Output schemas: Consistent JSON format for findings
"""

from .prompt_builder import PromptBuilder, StructuredContext, DiffChange
from .example_selector import ExampleSelector

__all__ = [
    "PromptBuilder",
    "StructuredContext",
    "DiffChange",
    "ExampleSelector"
]
