"""LangChain Integration for the Multi-Agent Code Review System.

This module provides LangChain-based implementations of the agents,
enabling advanced features like:
- Chain composition
- Memory integration  
- Tool usage
- Streaming responses

Usage:
    from src.langchain.agents import LangChainCodeAnalysisAgent
    
    agent = LangChainCodeAnalysisAgent(config)
    result = agent.process(code)
"""
import os
from typing import Any, Dict, List, Optional

from langchain_openai import ChatOpenAI
from langchain.schema import HumanMessage, SystemMessage, AIMessage
from langchain.memory import ConversationBufferMemory
from langchain.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain.chains import LLMChain

from ..agents.base_agent import BaseAgent
from ..utils.logger import get_logger

logger = get_logger(__name__)


class LangChainBaseAgent(BaseAgent):
    """Base class for LangChain-powered agents."""
    
    def initialize(self) -> None:
        """Initialize LangChain components."""
        cfg = self.config or {}
        
        # Initialize the LLM
        self.llm = ChatOpenAI(
            model=cfg.get("model", "gpt-4"),
            temperature=cfg.get("temperature", 0.2),
            max_tokens=cfg.get("max_tokens", 1024),
            api_key=os.getenv("OPENAI_API_KEY")
        )
        
        # Initialize memory
        self.memory = ConversationBufferMemory(
            memory_key="chat_history",
            return_messages=True
        )
        
        # Will be set by subclasses
        self.chain = None
        
        logger.info(f"Initialized LangChain agent with model: {cfg.get('model', 'gpt-4')}")
    
    def cleanup(self) -> None:
        """Cleanup resources."""
        if self.memory:
            self.memory.clear()


class LangChainCodeAnalysisAgent(LangChainBaseAgent):
    """LangChain-powered code analysis agent."""
    
    def initialize(self) -> None:
        """Initialize with code analysis chain."""
        super().initialize()
        
        system_prompt = """You are a senior software engineer and code reviewer.
Your task is to analyze code and provide:
1. A brief summary of what the code does
2. A numbered list of specific suggestions for improvement
3. Focus on: readability, types, documentation, edge cases, and bugs

Be concise but thorough. Each suggestion should be actionable."""
        
        prompt = ChatPromptTemplate.from_messages([
            ("system", system_prompt),
            MessagesPlaceholder(variable_name="chat_history"),
            ("human", "{input}")
        ])
        
        self.chain = LLMChain(
            llm=self.llm,
            prompt=prompt,
            memory=self.memory,
            verbose=self.config.get("verbose", False)
        )
    
    def process(self, code: str) -> Dict[str, Any]:
        """Analyze code using LangChain."""
        user_input = f"Analyze this code:\n\n```\n{code}\n```"
        
        try:
            response = self.chain.invoke({"input": user_input})
            analysis = response.get("text", str(response))
            
            # Extract suggestions
            suggestions = self._extract_suggestions(analysis)
            
            return {
                "status": "ok",
                "analysis": analysis,
                "suggestions": suggestions
            }
        except Exception as e:
            logger.error(f"Analysis failed: {e}")
            return {"status": "error", "error": str(e)}
    
    def _extract_suggestions(self, analysis: str) -> List[str]:
        """Extract numbered suggestions from analysis."""
        suggestions = []
        for line in analysis.splitlines():
            line = line.strip()
            if line and (line[0].isdigit() or line.startswith("-")):
                cleaned = line.lstrip("0123456789.-) ").strip()
                if cleaned:
                    suggestions.append(cleaned)
        return suggestions


class LangChainCodeGenerationAgent(LangChainBaseAgent):
    """LangChain-powered code generation agent."""
    
    def initialize(self) -> None:
        """Initialize with code generation chain."""
        super().initialize()
        
        system_prompt = """You are an expert programmer who generates high-quality code.
Given existing code and improvement suggestions, you will:
1. Implement all suggested improvements
2. Maintain the original functionality
3. Follow best practices and coding standards
4. Add appropriate documentation

Return only the improved code wrapped in ```python``` blocks."""
        
        prompt = ChatPromptTemplate.from_messages([
            ("system", system_prompt),
            MessagesPlaceholder(variable_name="chat_history"),
            ("human", "{input}")
        ])
        
        self.chain = LLMChain(
            llm=self.llm,
            prompt=prompt,
            memory=self.memory,
            verbose=self.config.get("verbose", False)
        )
    
    def process(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """Generate improved code using LangChain."""
        code = input_data.get("code", "")
        suggestions = input_data.get("suggestions", [])
        requirements = input_data.get("requirements", [])
        
        suggestions_text = "\n".join(f"- {s}" for s in suggestions)
        requirements_text = "\n".join(f"- {r}" for r in requirements)
        
        user_input = f"""Improve this code based on the suggestions:

Original code:
```
{code}
```

Suggestions:
{suggestions_text}

Additional requirements:
{requirements_text}"""
        
        try:
            response = self.chain.invoke({"input": user_input})
            result = response.get("text", str(response))
            
            # Extract code from response
            generated_code = self._extract_code(result)
            
            return {
                "status": "ok",
                "generated_code": generated_code,
                "raw": result
            }
        except Exception as e:
            logger.error(f"Generation failed: {e}")
            return {"status": "error", "error": str(e)}
    
    def _extract_code(self, response: str) -> str:
        """Extract code from markdown code blocks."""
        import re
        pattern = r"```(?:python)?\s*\n(.*?)```"
        matches = re.findall(pattern, response, re.DOTALL)
        return "\n\n".join(matches) if matches else response


class LangChainBugDetectionAgent(LangChainBaseAgent):
    """LangChain-powered bug detection agent."""
    
    def initialize(self) -> None:
        """Initialize with bug detection chain."""
        super().initialize()
        
        system_prompt = """You are an expert bug hunter and debugger.
Analyze code to find bugs, errors, and potential issues.

For each bug found, provide:
1. Severity (critical, high, medium, low)
2. Location in the code
3. Description of the problem
4. Suggested fix

Format each bug clearly and be thorough but avoid false positives."""
        
        prompt = ChatPromptTemplate.from_messages([
            ("system", system_prompt),
            MessagesPlaceholder(variable_name="chat_history"),
            ("human", "{input}")
        ])
        
        self.chain = LLMChain(
            llm=self.llm,
            prompt=prompt,
            memory=self.memory,
            verbose=self.config.get("verbose", False)
        )
    
    def process(self, code: str) -> Dict[str, Any]:
        """Detect bugs using LangChain."""
        user_input = f"Find all bugs in this code:\n\n```\n{code}\n```"
        
        try:
            response = self.chain.invoke({"input": user_input})
            analysis = response.get("text", str(response))
            
            return {
                "status": "ok",
                "raw_analysis": analysis,
                "bugs": [],  # Would need parsing
                "bug_count": 0
            }
        except Exception as e:
            logger.error(f"Bug detection failed: {e}")
            return {"status": "error", "error": str(e)}


class LangChainSecurityAgent(LangChainBaseAgent):
    """LangChain-powered security analysis agent."""
    
    def initialize(self) -> None:
        """Initialize with security analysis chain."""
        super().initialize()
        
        system_prompt = """You are a security expert specializing in code security analysis.
Analyze code for security vulnerabilities including:
- SQL Injection
- XSS
- Command Injection
- Path Traversal
- Hardcoded credentials
- Authentication issues
- And other OWASP Top 10 vulnerabilities

For each vulnerability:
1. Category
2. Severity (critical, high, medium, low)
3. Location
4. Description
5. Remediation steps"""
        
        prompt = ChatPromptTemplate.from_messages([
            ("system", system_prompt),
            MessagesPlaceholder(variable_name="chat_history"),
            ("human", "{input}")
        ])
        
        self.chain = LLMChain(
            llm=self.llm,
            prompt=prompt,
            memory=self.memory,
            verbose=self.config.get("verbose", False)
        )
    
    def process(self, code: str) -> Dict[str, Any]:
        """Perform security analysis using LangChain."""
        user_input = f"Perform a security audit on this code:\n\n```\n{code}\n```"
        
        try:
            response = self.chain.invoke({"input": user_input})
            analysis = response.get("text", str(response))
            
            return {
                "status": "ok",
                "raw_analysis": analysis,
                "vulnerabilities": [],
                "vulnerability_count": 0,
                "risk_score": 0.0
            }
        except Exception as e:
            logger.error(f"Security analysis failed: {e}")
            return {"status": "error", "error": str(e)}


# Factory function to create LangChain agents
def create_langchain_agent(agent_type: str, config: Dict[str, Any]) -> BaseAgent:
    """Factory function to create LangChain-powered agents.
    
    Args:
        agent_type: Type of agent (analysis, generation, bug_detection, security)
        config: Agent configuration
        
    Returns:
        LangChain-powered agent instance
    """
    agents = {
        "analysis": LangChainCodeAnalysisAgent,
        "generation": LangChainCodeGenerationAgent,
        "bug_detection": LangChainBugDetectionAgent,
        "security": LangChainSecurityAgent,
    }
    
    agent_class = agents.get(agent_type)
    if not agent_class:
        raise ValueError(f"Unknown agent type: {agent_type}")
    
    return agent_class(config)
