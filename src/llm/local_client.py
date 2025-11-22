"""Local LLM client using open source models from Hugging Face.

This implementation uses CodeLlama-7b-Instruct, which is good for code tasks
and can run on consumer hardware. First use will download the model (~4GB).
"""
from typing import List, Dict, Any, Optional
import torch
from transformers import AutoModelForCausalLM, AutoTokenizer, pipeline

from .device_info import print_device_info

DEFAULT_MODEL = "TinyLlama/TinyLlama-1.1B-Chat-v1.0"  # Smaller model that runs well on CPU
DEVICE = "cuda" if torch.cuda.is_available() else "cpu"

class LocalLLMClient:
    def __init__(
        self,
        model_name: str = DEFAULT_MODEL,
        default_temperature: float = 0.2,
        default_max_tokens: int = 1024
    ):
        self.model_name = model_name
        self.default_temperature = default_temperature
        self.default_max_tokens = default_max_tokens
        self._initialize_model()

    def _initialize_model(self):
        """Load model and tokenizer from Hugging Face."""
        print_device_info()  # Show what compute device we'll use
        print(f"\nLoading model {self.model_name} on {DEVICE}...")
        # On CUDA we can use float16 and device_map for faster performance.
        # On CPU we avoid device_map (and float16) to prevent accelerate/device_map requirements.
        if DEVICE == "cuda":
            self.model = AutoModelForCausalLM.from_pretrained(
                self.model_name,
                torch_dtype=torch.float16,
                device_map="auto",
            )
            self.tokenizer = AutoTokenizer.from_pretrained(self.model_name)
            self.pipe = pipeline(
                "text-generation",
                model=self.model,
                tokenizer=self.tokenizer,
                torch_dtype=torch.float16,
                device_map="auto",
            )
        else:
            # CPU path: load model into CPU memory without device_map and use float32
            self.model = AutoModelForCausalLM.from_pretrained(
                self.model_name,
                torch_dtype=torch.float32,
                device_map=None,
                low_cpu_mem_usage=False,
            )
            self.tokenizer = AutoTokenizer.from_pretrained(self.model_name)
            # For CPU, set pipeline device to -1
            self.pipe = pipeline(
                "text-generation",
                model=self.model,
                tokenizer=self.tokenizer,
                device=-1,
            )
        print("Model loaded successfully!")

    def _format_messages(self, messages: List[Dict[str, str]]) -> str:
        """Format chat messages into a single prompt string."""
        formatted = []
        for msg in messages:
            role = msg["role"]
            content = msg["content"]
            if role == "system":
                formatted.append(f"<system>{content}</system>")
            elif role == "user":
                formatted.append(f"<user>{content}</user>")
            elif role == "assistant":
                formatted.append(f"<assistant>{content}</assistant>")
        return "\n".join(formatted) + "\n<assistant>"

    def chat(
        self,
        messages: List[Dict[str, str]],
        model: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None
    ) -> str:
        """Generate a response using the local model."""
        temperature = self.default_temperature if temperature is None else temperature
        max_tokens = self.default_max_tokens if max_tokens is None else max_tokens

        prompt = self._format_messages(messages)
        sequences = self.pipe(
            prompt,
            do_sample=True,
            temperature=temperature,
            max_new_tokens=max_tokens,
            num_return_sequences=1,
            eos_token_id=self.tokenizer.eos_token_id,
        )
        
        # Extract generated text and clean up
        generated = sequences[0]["generated_text"]
        # Remove the input prompt to get just the response
        response = generated[len(prompt):].strip()
        # Remove any partial/incomplete assistant tags
        if "<assistant>" in response:
            response = response[:response.rfind("<assistant>")]
        return response.strip()