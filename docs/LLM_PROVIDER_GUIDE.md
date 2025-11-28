# LLM Provider Configuration Guide

## 🎯 Single Source of Truth

The ENTIRE project uses a **centralized LLM factory** pattern. You only need to configure the provider in ONE place, and it affects all 12 specialized agents automatically.

---

## 🔧 Quick Setup

### Option 1: Using Environment Variables (Recommended for Production)

```bash
# .env file
export LLM_PROVIDER="openai"  # or "bytez" or "local"
export LLM_MODEL="gpt-4"       # Optional: override model
export OPENAI_API_KEY="sk-..."  # For OpenAI
# OR
export BYTEZ_API_KEY="..."     # For Bytez/Local
```

### Option 2: Using Config File (For Development)

Edit `config/default_config.py`:

```python
# Change this ONE line:
DEFAULT_PROVIDER = "openai"  # or "bytez" or "local"

# For OpenAI:
OPENAI_MODEL = "gpt-4"

# For Bytez/Local:
QWEN_MODEL_NAME = "qwen2.5-coder"
```

---

## 📋 Provider Options

| Provider   | Use Case                    | Requires         | Model Examples                    |
| ---------- | --------------------------- | ---------------- | --------------------------------- |
| `"openai"` | Production, best quality    | `OPENAI_API_KEY` | gpt-4, gpt-3.5-turbo, gpt-4-turbo |
| `"bytez"`  | Testing, cost-effective     | `BYTEZ_API_KEY`  | Any Bytez-hosted model            |
| `"local"`  | Local/self-hosted via Bytez | `BYTEZ_API_KEY`  | qwen2.5-coder, llama, etc.        |

---

## 🚀 How It Works

### Architecture

```
┌─────────────────────────────────────┐
│  config/default_config.py           │
│  DEFAULT_PROVIDER = "openai"        │  ← Change ONCE
└─────────────────────────────────────┘
                 │
                 ↓
┌─────────────────────────────────────┐
│  src/llm/factory.py                 │
│  get_llm_client()                   │  ← Central factory
└─────────────────────────────────────┘
                 │
                 ↓
┌─────────────────────────────────────┐
│  ALL 12 Specialized Agents          │  ← Automatically
│  - NamingReviewer                   │     use global
│  - QualityReviewer                  │     provider
│  - LogicErrorDetector               │
│  ... etc ...                        │
└─────────────────────────────────────┘
```

### Code Flow

Every specialized agent uses this pattern:

```python
# OLD WAY (REMOVED) - DON'T DO THIS:
# from ...llm.client import LLMClient
# self.client = LLMClient(provider="openai")  # ❌ Couples agent to provider

# NEW WAY (CORRECT) - ALL AGENTS DO THIS:
from ...llm import get_llm_client_from_config

cfg = self.config or {}
self.client = get_llm_client_from_config(cfg)  # ✅ Uses global config
```

The factory automatically:

1. Reads `LLM_PROVIDER` env variable OR `DEFAULT_PROVIDER` from config
2. Selects appropriate model for the provider
3. Creates configured LLMClient
4. Returns client ready to use

---

## 🎛️ Priority Order

The system checks configuration in this order:

1. **Environment Variables** (highest priority)
   - `LLM_PROVIDER`
   - `LLM_MODEL`
2. **Config File**
   - `DEFAULT_PROVIDER`
   - `OPENAI_MODEL` or `QWEN_MODEL_NAME`
3. **Defaults** (lowest priority)
   - Provider: "openai"
   - Model: "gpt-4"

---

## 📝 Examples

### Switching from Qwen to OpenAI

**Before:**

```python
# config/default_config.py
DEFAULT_PROVIDER = "local"
```

**After (change ONE line):**

```python
# config/default_config.py
DEFAULT_PROVIDER = "openai"
```

**Result:** All 12 agents now use OpenAI automatically! 🎉

### Using Different Models per Agent (Advanced)

You can still override per-agent if needed:

```python
# config/default_config.py
ORCHESTRATOR_CONFIG = {
    "analysis": {
        "model": "gpt-4",  # Override: use GPT-4 for code review
        "temperature": 0.2
    },
    "security": {
        "model": "gpt-3.5-turbo",  # Override: use cheaper model for security
        "temperature": 0.1
    }
}
```

But provider is still global!

---

## 🧪 Testing Different Providers

```bash
# Test with OpenAI
export LLM_PROVIDER="openai"
export OPENAI_API_KEY="sk-..."
python -m src.cli review test.py --type full_review

# Test with Bytez
export LLM_PROVIDER="bytez"
export BYTEZ_API_KEY="..."
python -m src.cli review test.py --type full_review

# Compare results!
```

---

## 🐛 Debugging

Check current configuration:

```python
from src.llm import get_llm_info

info = get_llm_info()
print(info)
# {
#   "provider": "openai",
#   "model": "gpt-4",
#   "config_source": "environment",
#   "openai_key_set": True,
#   "bytez_key_set": False
# }
```

---

## ✅ Benefits of This Approach

1. **Single Source of Truth**: Change provider in ONE place
2. **Consistency**: All agents use same provider/model
3. **Flexibility**: Easy to switch providers for testing
4. **Production Ready**: Environment variables for deployment
5. **No Code Changes**: Just change config, no code edits needed

---

## 🚨 Common Mistakes (Now Prevented)

❌ **WRONG** - Don't create clients directly:

```python
from src.llm.client import LLMClient
client = LLMClient(provider="openai")  # Couples code to provider
```

✅ **CORRECT** - Use factory:

```python
from src.llm import get_llm_client
client = get_llm_client()  # Uses global config
```

❌ **WRONG** - Don't hardcode provider in agent:

```python
def initialize(self):
    self.client = LLMClient(provider="openai")  # Forces OpenAI only
```

✅ **CORRECT** - Use factory with config:

```python
def initialize(self):
    from ...llm import get_llm_client_from_config
    self.client = get_llm_client_from_config(self.config)  # Uses global
```

---

**Bottom Line**: Change `DEFAULT_PROVIDER` once → entire project adapts automatically! 🚀
