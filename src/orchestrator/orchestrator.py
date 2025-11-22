"""Orchestrator Agent for coordinating multiple agents."""
from typing import Any, Dict, List

from ..agents.base_agent import BaseAgent
from ..agents.research_agent import ResearchAgent
from ..agents.code_analysis_agent import CodeAnalysisAgent
from ..agents.code_generation_agent import CodeGenerationAgent

class OrchestratorAgent:
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.agents = self._initialize_agents()
        
    def _initialize_agents(self) -> Dict[str, BaseAgent]:
        """Initialize all required agents."""
        return {
            "research": ResearchAgent(self.config.get("research", {})),
            "analysis": CodeAnalysisAgent(self.config.get("analysis", {})),
            "generation": CodeGenerationAgent(self.config.get("generation", {}))
        }
    
    def process_task(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """
        Process a complex task by coordinating multiple agents.
        
        Args:
            task: Dict containing task specifications and requirements
            
        Returns:
            Dict containing combined results from all involved agents
        """
        task_type = task.get("type")
        if task_type == "code_improvement":
            # Expected input shape: {"code": str, "requirements": [str]}
            input_data = task.get("input", {})
            code = input_data.get("code", "")
            requirements = input_data.get("requirements", [])

            # Step 1: analyze code
            analysis = self.agents["analysis"].process(code)

            # Step 2: optionally research topics mentioned in suggestions (best-effort)
            # We'll collect any short research results if user asked for it via task
            research_results = None
            if input_data.get("research", False):
                # pick top suggestion or use requirements as query
                query = "; ".join(requirements) if requirements else (analysis.get("suggestions") and analysis.get("suggestions")[0])
                if query:
                    research_results = self.agents["research"].process(query)

            # Step 3: generate new code using suggestions
            generation_spec = {"code": code, "suggestions": analysis.get("suggestions", []), "requirements": requirements}
            generation = self.agents["generation"].process(generation_spec)

            return {
                "status": "ok",
                "analysis": analysis,
                "research": research_results,
                "generation": generation,
            }

        # fallback: unknown task
        return {"status": "error", "error": f"unknown task type: {task_type}"}
    
    def cleanup(self) -> None:
        """Cleanup all agents and resources."""
        for agent in self.agents.values():
            agent.cleanup()