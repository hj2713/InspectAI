"""Unit test for orchestrator using stubbed agents (no external API calls)."""
from src.orchestrator.orchestrator import OrchestratorAgent


class StubAgent:
    def __init__(self, value):
        self._value = value

    def process(self, data):
        return self._value

    def cleanup(self):
        return None


def test_orchestrator_code_improvement_flow():
    # Create an orchestrator with empty config, then replace agents with stubs
    orch = OrchestratorAgent({})
    # stubbed outputs for analysis and generation
    analysis_result = {"status": "ok", "analysis": "Looks fine.", "suggestions": ["Add type hints"]}
    generation_result = {"status": "ok", "generated_code": "def add(a: int, b: int) -> int:\n    \"\"\"Add two integers.\"\"\"\n    return a + b"}

    orch.agents = {
        "research": StubAgent({"status": "ok", "result": "research"}),
        "analysis": StubAgent(analysis_result),
        "generation": StubAgent(generation_result),
    }

    task = {"type": "code_improvement", "input": {"code": "def add(a,b): return a+b", "requirements": ["Add type hints"]}}
    out = orch.process_task(task)

    assert out["status"] == "ok"
    assert out["analysis"] == analysis_result
    assert out["generation"] == generation_result
