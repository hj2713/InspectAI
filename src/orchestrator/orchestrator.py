"""Enhanced Orchestrator Agent with multiple task types and async support.

This orchestrator coordinates multiple agents to handle various code review tasks:
- code_improvement: Analyze and improve code quality
- bug_fix: Detect and fix bugs
- security_audit: Analyze security vulnerabilities
- test_generation: Generate test cases
- full_review: Comprehensive review (all of the above)
- pr_review: Review a GitHub Pull Request
"""
import asyncio
import uuid
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, List, Optional

from ..agents.base_agent import BaseAgent
from ..agents.research_agent import ResearchAgent
from ..agents.code_analysis_agent import CodeAnalysisAgent
from ..agents.code_generation_agent import CodeGenerationAgent
from ..agents.bug_detection_agent import BugDetectionAgent
from ..agents.security_agent import SecurityAnalysisAgent
from ..agents.test_generation_agent import TestGenerationAgent
from ..agents.documentation_agent import DocumentationAgent
from ..agents.pr_description_generator import PRDescriptionGenerator
from ..memory.agent_memory import AgentMemory, SharedMemory
from ..utils.logger import get_logger, AgentLogger
from ..utils.error_handler import safe_agent_execution, create_partial_success_result, GracefulErrorHandler

logger = get_logger(__name__)


class OrchestratorAgent:
    """Enhanced orchestrator that coordinates multiple specialized agents."""
    
    SUPPORTED_TASKS = [
        "code_improvement",
        "bug_fix",
        "security_audit",
        "test_generation",
        "documentation",
        "full_review",
        "pr_review",
        "pr_description"
    ]
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.agents: Dict[str, BaseAgent] = {}
        self.memory = AgentMemory(max_history=100)
        self.shared_memory = SharedMemory()
        self.logger = AgentLogger("orchestrator")
        self._executor = ThreadPoolExecutor(max_workers=4)
        
        # Initialize Vector Store for long-term memory (Supabase with ChromaDB fallback)
        try:
            from ..memory.supabase_vector_store import get_vector_store
            self.vector_store = get_vector_store()
            backend = "Supabase" if self.vector_store.supabase_enabled else (
                "ChromaDB" if self.vector_store.chromadb_enabled else "in-memory"
            )
            logger.info(f"Vector Store initialized with {backend} backend")
        except Exception as e:
            logger.warning(f"Failed to initialize Vector Store: {e}. Running without long-term memory.")
            self.vector_store = None
            
        self._initialize_agents()
    
    def _initialize_agents(self) -> None:
        """Initialize all required agents."""
        logger.info("Initializing agents...")
        
        agent_configs = {
            "research": (ResearchAgent, self.config.get("research", {})),
            "analysis": (CodeAnalysisAgent, self.config.get("analysis", {})),
            "generation": (CodeGenerationAgent, self.config.get("generation", {})),
            "bug_detection": (BugDetectionAgent, self.config.get("bug_detection", {})),
            "security": (SecurityAnalysisAgent, self.config.get("security", {})),
            "test_generation": (TestGenerationAgent, self.config.get("test_generation", {})),
            "documentation": (DocumentationAgent, self.config.get("documentation", {})),
            "pr_description": (PRDescriptionGenerator, self.config.get("pr_description", {})),
        }
        
        for name, (agent_class, agent_config) in agent_configs.items():
            try:
                self.agents[name] = agent_class(agent_config)
                logger.info(f"Initialized {name} agent")
            except Exception as e:
                logger.error(f"Failed to initialize {name} agent: {e}")
                raise
    
    def process_task(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """Process a task synchronously.
        
        Args:
            task: Dict containing:
                - type: Task type (see SUPPORTED_TASKS)
                - input: Task-specific input data
                
        Returns:
            Dict containing results from all involved agents
        """
        task_type = task.get("type")
        task_id = task.get("id", str(uuid.uuid4())[:8])
        
        self.logger.set_task_id(task_id)
        self.logger.task_start(task_type)
        
        # Store in memory
        self.memory.start_task(task_id, task_type, task.get("input", {}))
        
        if task_type not in self.SUPPORTED_TASKS:
            self.logger.error(f"Unknown task type: {task_type}")
            return {"status": "error", "error": f"Unknown task type: {task_type}. Supported: {self.SUPPORTED_TASKS}"}
        
        try:
            # Route to appropriate handler
            handler = getattr(self, f"_handle_{task_type}", None)
            if handler:
                result = handler(task.get("input", {}), task_id)
            else:
                result = {"status": "error", "error": f"No handler for {task_type}"}
            
            self.logger.task_complete(task_type, result.get("status", "unknown"))
            return result
            
        except Exception as e:
            logger.error(f"Task failed: {e}", exc_info=True)
            return {"status": "error", "error": str(e)}
    
    async def process_task_async(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """Process a task asynchronously.
        
        This allows for parallel execution of independent agent operations.
        """
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(self._executor, self.process_task, task)
    
    def _handle_code_improvement(self, input_data: Dict[str, Any], task_id: str) -> Dict[str, Any]:
        """Handle code improvement task."""
        code = input_data.get("code", "")
        requirements = input_data.get("requirements", [])
        
        # Step 1: Analyze code
        logger.info("Step 1: Analyzing code...")
        analysis = self._safe_execute_agent("analysis", code)
        if analysis.get("status") != "error":
            self.memory.add_task_result(task_id, "analysis", analysis)
        
        # Step 2: Optional research
        research_results = None
        if input_data.get("research", False):
            query = "; ".join(requirements) if requirements else (
                analysis.get("suggestions", [""])[0] if analysis.get("suggestions") else ""
            )
            if query:
                logger.info("Step 2: Researching...")
                research_results = self._safe_execute_agent("research", query)
                if research_results.get("status") != "error":
                    self.memory.add_task_result(task_id, "research", research_results)
        
        # Step 3: Generate improved code
        logger.info("Step 3: Generating improved code...")
        generation_spec = {
            "code": code,
            "suggestions": analysis.get("suggestions", []),
            "requirements": requirements
        }
        generation = self._safe_execute_agent("generation", generation_spec)
        if generation.get("status") != "error":
            self.memory.add_task_result(task_id, "generation", generation)
        
        return {
            "status": "ok",
            "task_id": task_id,
            "analysis": analysis,
            "research": research_results,
            "generation": generation
        }
    
    def _handle_bug_fix(self, input_data: Dict[str, Any], task_id: str) -> Dict[str, Any]:
        """Handle bug detection and fixing task."""
        code = input_data.get("code", "")
        
        # Step 1: Detect bugs
        logger.info("Step 1: Detecting bugs...")
        bug_report = self._safe_execute_agent("bug_detection", code)
        if bug_report.get("status") != "error":
            self.memory.add_task_result(task_id, "bug_detection", bug_report)
        
        if not bug_report.get("bugs"):
            return {
                "status": "ok",
                "task_id": task_id,
                "bug_report": bug_report,
                "message": "No bugs detected",
                "fixed_code": None
            }
        
        # Step 2: Generate fixed code
        logger.info("Step 2: Generating fixed code...")
        fix_suggestions = [
            f"Fix {b.get('severity', 'unknown')} bug: {b.get('description', '')} - {b.get('fix', '')}"
            for b in bug_report.get("bugs", [])
        ]
        
        generation_spec = {
            "code": code,
            "suggestions": fix_suggestions,
            "requirements": ["Fix all identified bugs while maintaining functionality"]
        }
        fixed_code = self._safe_execute_agent("generation", generation_spec)
        if fixed_code.get("status") != "error":
            self.memory.add_task_result(task_id, "generation", fixed_code)
        
        return {
            "status": "ok",
            "task_id": task_id,
            "bug_report": bug_report,
            "fixed_code": fixed_code
        }
    
    def _handle_security_audit(self, input_data: Dict[str, Any], task_id: str) -> Dict[str, Any]:
        """Handle security audit task."""
        code = input_data.get("code", "")
        
        # Step 1: Security analysis
        logger.info("Step 1: Running security analysis...")
        security_report = self._safe_execute_agent("security", code)
        if security_report.get("status") != "error":
            self.memory.add_task_result(task_id, "security", security_report)
        
        # Step 2: Generate secure code if vulnerabilities found
        secure_code = None
        if security_report.get("vulnerabilities"):
            logger.info("Step 2: Generating secure code...")
            remediation_requirements = [
                f"Fix {v.get('category', 'security')} vulnerability: {v.get('remediation', '')}"
                for v in security_report.get("vulnerabilities", [])
            ]
            
            generation_spec = {
                "code": code,
                "suggestions": remediation_requirements,
                "requirements": ["Implement secure coding practices", "Fix all security vulnerabilities"]
            }
            secure_code = self._safe_execute_agent("generation", generation_spec)
            if secure_code.get("status") != "error":
                self.memory.add_task_result(task_id, "generation", secure_code)
        
        return {
            "status": "ok",
            "task_id": task_id,
            "security_report": security_report,
            "risk_score": security_report.get("risk_score", 0),
            "secure_code": secure_code
        }
    
    def _handle_test_generation(self, input_data: Dict[str, Any], task_id: str) -> Dict[str, Any]:
        """Handle test generation task."""
        code = input_data.get("code", "")
        framework = input_data.get("framework", "pytest")
        coverage_focus = input_data.get("coverage_focus", ["happy_path", "edge_cases", "error_handling"])
        
        logger.info("Generating test cases...")
        test_result = self._safe_execute_agent("test_generation", {
            "code": code,
            "framework": framework,
            "coverage_focus": coverage_focus
        })
        if test_result.get("status") != "error":
            self.memory.add_task_result(task_id, "test_generation", test_result)
        
        return {
            "status": "ok",
            "task_id": task_id,
            "tests": test_result
        }
    
    def _handle_documentation(self, input_data: Dict[str, Any], task_id: str) -> Dict[str, Any]:
        """Handle documentation generation task."""
        code = input_data.get("code", "")
        doc_type = input_data.get("doc_type", "docstring")
        style = input_data.get("style", "google")
        
        logger.info(f"Generating {doc_type} documentation...")
        doc_result = self._safe_execute_agent("documentation", {
            "code": code,
            "doc_type": doc_type,
            "style": style
        })
        if doc_result.get("status") != "error":
            self.memory.add_task_result(task_id, "documentation", doc_result)
        
        return {
            "status": "ok",
            "task_id": task_id,
            "documentation": doc_result
        }
    
    def _handle_full_review(self, input_data: Dict[str, Any], task_id: str) -> Dict[str, Any]:
        """Handle comprehensive full review task (runs all agents).
        
        Uses graceful error handling - if one agent fails, others continue.
        """
        code = input_data.get("code", "")
        
        successful_agents = {}
        failed_agents = {}
        
        # Run all analyses with graceful error handling
        logger.info("Running full code review...")
        
        # 1. Code Analysis
        logger.info("Step 1/5: Code analysis...")
        analysis = self._safe_execute_agent("analysis", code)
        if analysis.get("status") == "error":
            failed_agents["analysis"] = analysis
        else:
            successful_agents["analysis"] = analysis
        
        # 2. Bug Detection
        logger.info("Step 2/5: Bug detection...")
        bug_report = self._safe_execute_agent("bug_detection", code)
        if bug_report.get("status") == "error":
            failed_agents["bug_detection"] = bug_report
        else:
            successful_agents["bug_detection"] = bug_report
        
        # 3. Security Audit
        logger.info("Step 3/5: Security audit...")
        security_report = self._safe_execute_agent("security", code)
        if security_report.get("status") == "error":
            failed_agents["security"] = security_report
        else:
            successful_agents["security"] = security_report
        
        # 4. Test Generation
        logger.info("Step 4/5: Test generation...")
        tests = self._safe_execute_agent("test_generation", {
            "code": code,
            "framework": input_data.get("framework", "pytest")
        })
        if tests.get("status") == "error":
            failed_agents["test_generation"] = tests
        else:
            successful_agents["test_generation"] = tests
        
        # 5. Generate improved code based on all findings from successful agents
        logger.info("Step 5/5: Generating improved code...")
        all_suggestions = []
        
        # Collect suggestions from successful agents only
        if "analysis" in successful_agents:
            all_suggestions.extend(successful_agents["analysis"].get("suggestions", []))
        if "bug_detection" in successful_agents:
            all_suggestions.extend([
                f"Fix bug: {b.get('description', '')}"
                for b in successful_agents["bug_detection"].get("bugs", [])
            ])
        if "security" in successful_agents:
            all_suggestions.extend([
                f"Fix security: {v.get('description', '')}"
                for v in successful_agents["security"].get("vulnerabilities", [])
            ])
        
        improved_code = self._safe_execute_agent("generation", {
            "code": code,
            "suggestions": all_suggestions,
            "requirements": input_data.get("requirements", [])
        })
        
        if improved_code.get("status") == "error":
            failed_agents["generation"] = improved_code
        else:
            successful_agents["generation"] = improved_code
        
        # Create result based on successes and failures
        if failed_agents:
            return create_partial_success_result(
                successful_agents,
                failed_agents,
                total_agents=5
            )
        
        return {
            "status": "ok",
            "task_id": task_id,
            **successful_agents
        }
    
    def _handle_pr_review(self, input_data: Dict[str, Any], task_id: str) -> Dict[str, Any]:
        """Handle GitHub Pull Request review task."""
        from ..github.client import GitHubClient
        
        repo_url = input_data.get("repo_url", "")
        pr_number = input_data.get("pr_number")
        post_comments = input_data.get("post_comments", False)
        
        if not repo_url or not pr_number:
            return {"status": "error", "error": "repo_url and pr_number are required"}
        
        logger.info(f"Reviewing PR #{pr_number} from {repo_url}")
        
        with GitHubClient() as github:
            # Get PR details
            pr = github.get_pull_request(repo_url, pr_number)
            
            results = {
                "status": "ok",
                "task_id": task_id,
                "pr": {
                    "number": pr.number,
                    "title": pr.title,
                    "author": pr.author,
                    "files_changed": len(pr.files)
                },
                "file_reviews": []
            }
            
            # Review each changed file
            for pr_file in pr.files:
                if pr_file.status == "removed":
                    continue
                
                # Get full file content
                try:
                    content = github.get_pr_file_content(repo_url, pr_number, pr_file.filename)
                except Exception as e:
                    logger.warning(f"Could not get content for {pr_file.filename}: {e}")
                    continue
                
                # Run analysis on the file
                file_review = {
                    "filename": pr_file.filename,
                    "status": pr_file.status,
                    "additions": pr_file.additions,
                    "deletions": pr_file.deletions
                }
                
                # Extract repo_id for Vector Store
                repo_id = repo_url.replace("https://github.com/", "").replace("http://github.com/", "").strip("/")
                
                # Retrieve context from Vector Store
                context = None
                if self.vector_store:
                    try:
                        # Search for relevant context for this PR/Repo
                        # For now, we just get general context. In future, we can be more specific.
                        context_results = self.vector_store.search(
                            query=f"Context for PR #{pr_number} in {repo_id}",
                            repo_id=repo_id,
                            n_results=3
                        )
                        if context_results:
                            context = "\n".join([r["content"] for r in context_results])
                            logger.info(f"Retrieved {len(context_results)} context items from Vector Store")
                    except Exception as e:
                        logger.warning(f"Failed to retrieve context: {e}")

                # Only analyze code files
                if self._is_code_file(pr_file.filename):
                    logger.info(f"Analyzing {pr_file.filename}...")
                    
                    file_review["analysis"] = self.agents["analysis"].process(content, context=context, filename=pr_file.filename)
                    file_review["bugs"] = self.agents["bug_detection"].process(content, context=context, filename=pr_file.filename)
                    file_review["security"] = self.agents["security"].process(content, context=context, filename=pr_file.filename)
                
                results["file_reviews"].append(file_review)
            
            # Generate overall review summary
            summary = self._generate_pr_summary(results["file_reviews"])
            results["summary"] = summary
            
            # Post comment if requested
            if post_comments:
                try:
                    github.post_pr_comment(repo_url, pr_number, summary)
                    results["comment_posted"] = True
                    logger.info("Posted review comment to PR")
                except Exception as e:
                    logger.error(f"Failed to post comment: {e}")
                    results["comment_posted"] = False
                    results["comment_error"] = str(e)
        
        return results
    
    def _is_code_file(self, filename: str) -> bool:
        """Check if a file is a code file worth analyzing."""
        code_extensions = {
            # Programming languages
            '.py', '.js', '.ts', '.jsx', '.tsx', '.java', '.c', '.cpp', '.h',
            '.cs', '.go', '.rs', '.rb', '.php', '.swift', '.kt', '.scala',
            # Web files
            '.html', '.htm', '.css', '.scss', '.sass', '.less',
            # Data/Config
            '.json', '.xml', '.yaml', '.yml', '.toml', '.ini',
            # Shell/Script
            '.sh', '.bash', '.zsh', '.fish', '.ps1', '.bat', '.cmd'
        }
        return any(filename.endswith(ext) for ext in code_extensions)
    
    def _generate_pr_summary(self, file_reviews: List[Dict[str, Any]]) -> str:
        """Generate a summary comment for PR review."""
        summary_parts = ["## 🤖 Multi-Agent Code Review Summary\n"]
        
        total_bugs = 0
        total_vulnerabilities = 0
        total_suggestions = 0
        
        for review in file_reviews:
            if "analysis" in review:
                total_suggestions += len(review["analysis"].get("suggestions", []))
            if "bugs" in review:
                total_bugs += review["bugs"].get("bug_count", 0)
            if "security" in review:
                total_vulnerabilities += review["security"].get("vulnerability_count", 0)
        
        # Overview stats
        summary_parts.append(f"**Files Reviewed:** {len(file_reviews)}\n")
        summary_parts.append(f"**Total Suggestions:** {total_suggestions}\n")
        summary_parts.append(f"**Bugs Found:** {total_bugs}\n")
        summary_parts.append(f"**Security Issues:** {total_vulnerabilities}\n\n")
        
        # Per-file details
        if any(r.get("bugs", {}).get("bugs") or r.get("security", {}).get("vulnerabilities") for r in file_reviews):
            summary_parts.append("### Issues Found\n\n")
            
            for review in file_reviews:
                filename = review["filename"]
                issues = []
                
                for bug in review.get("bugs", {}).get("bugs", []):
                    issues.append(f"- 🐛 **Bug** ({bug.get('severity', 'unknown')}): {bug.get('description', 'N/A')}")
                
                for vuln in review.get("security", {}).get("vulnerabilities", []):
                    issues.append(f"- 🔒 **Security** ({vuln.get('severity', 'unknown')}): {vuln.get('category', 'N/A')}")
                
                if issues:
                    summary_parts.append(f"**`{filename}`**\n")
                    summary_parts.extend(issues)
                    summary_parts.append("\n\n")
        
        summary_parts.append("---\n*Generated by Multi-Agent Code Review System*")
        
        return "".join(summary_parts)
    
    def _safe_execute_agent(self, agent_name: str, input_data: Any) -> Dict[str, Any]:
        """Safely execute an agent with graceful error handling.
        
        If the agent fails, logs the error and returns error dict instead of crashing.
        
        Args:
            agent_name: Name of the agent to execute
            input_data: Input data for the agent
            
        Returns:
            Agent result or error dict with status='error'
        """
        try:
            if agent_name not in self.agents:
                logger.error(f"Agent '{agent_name}' not found")
                return {
                    "status": "error",
                    "agent": agent_name,
                    "error_type": "AgentNotFound",
                    "error_message": f"The {agent_name} agent is not available",
                    "technical_details": f"Agent '{agent_name}' not initialized"
                }
            
            logger.info(f"Executing {agent_name} agent...")
            result = self.agents[agent_name].process(input_data)
            
            # Ensure result has status field
            if not isinstance(result, dict):
                result = {"status": "ok", "result": result}
            elif "status" not in result:
                result["status"] = "ok"
            
            return result
            
        except Exception as e:
            logger.error(f"Agent '{agent_name}' failed: {e}", exc_info=True)
            
            from ..utils.error_handler import get_user_friendly_error_message
            
            return {
                "status": "error",
                "agent": agent_name,
                "error_type": type(e).__name__,
                "error_message": get_user_friendly_error_message(e, agent_name),
                "technical_details": str(e)
            }
    
    async def run_parallel_agents(
        self,
        code: str,
        agents: List[str]
    ) -> Dict[str, Any]:
        """Run multiple agents in parallel on the same code.
        
        Args:
            code: Source code to analyze
            agents: List of agent names to run
            
        Returns:
            Dict with results from each agent
        """
        loop = asyncio.get_event_loop()
        
        async def run_agent(agent_name: str) -> tuple:
            agent = self.agents.get(agent_name)
            if not agent:
                return agent_name, {"error": f"Agent {agent_name} not found"}
            
            result = await loop.run_in_executor(
                self._executor,
                agent.process,
                code
            )
            return agent_name, result
        
        # Run all agents concurrently
        tasks = [run_agent(name) for name in agents]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        return {
            name: result if not isinstance(result, Exception) else {"error": str(result)}
            for name, result in results
        }
    
    def get_memory(self) -> AgentMemory:
        """Get the orchestrator's memory for inspection."""
        return self.memory
    
    def cleanup(self) -> None:
        """Cleanup all agents and resources."""
        logger.info("Cleaning up orchestrator...")
        for name, agent in self.agents.items():
            try:
                agent.cleanup()
            except Exception as e:
                logger.error(f"Error cleaning up {name}: {e}")
        
        self._executor.shutdown(wait=False)
        logger.info("Orchestrator cleanup complete")
