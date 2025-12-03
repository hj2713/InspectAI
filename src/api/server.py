
import os
import logging
from contextlib import asynccontextmanager
from typing import Any, Dict, List, Optional
import uvicorn
import asyncio
from fastapi import FastAPI, Request, BackgroundTasks, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

# Import webhook router
from src.api.webhooks import router as webhook_router
from src.utils.logger import setup_logging

# Initialize logging at module load time
setup_logging(log_level=os.getenv("LOG_LEVEL", "INFO"))
logger = logging.getLogger(__name__)

# Global orchestrator instance
_orchestrator = None


class ReviewRequest(BaseModel):
    """Request model for code review."""
    code: str = Field(..., description="Source code to review")
    task_type: str = Field(
        default="code_improvement",
        description="Type of review: code_improvement, bug_fix, security_audit, test_generation, documentation, full_review"
    )
    requirements: List[str] = Field(default=[], description="Additional requirements")
    framework: str = Field(default="pytest", description="Test framework for test generation")


class PRReviewRequest(BaseModel):
    """Request model for PR review."""
    repo_url: str = Field(..., description="GitHub repository URL or owner/repo format")
    pr_number: int = Field(..., description="Pull request number")
    post_comment: bool = Field(default=False, description="Whether to post a comment on the PR")


class TaskResponse(BaseModel):
    """Response model for review tasks."""
    status: str
    task_id: Optional[str] = None
    error: Optional[str] = None
    results: Optional[Dict[str, Any]] = None


def get_orchestrator():
    """Get or create the orchestrator instance."""
    global _orchestrator
    
    if _orchestrator is None:
        from src.orchestrator.orchestrator import OrchestratorAgent
        from config.default_config import ORCHESTRATOR_CONFIG
        import copy
        
        config = copy.deepcopy(ORCHESTRATOR_CONFIG)
        
        # Add configs for new agents
        if "bug_detection" not in config:
            config["bug_detection"] = {"model": "gpt-4", "temperature": 0.1, "max_tokens": 1024}
        if "security" not in config:
            config["security"] = {"model": "gpt-4", "temperature": 0.1, "max_tokens": 1024}
        if "test_generation" not in config:
            config["test_generation"] = {"model": "gpt-4", "temperature": 0.3, "max_tokens": 2048}
        if "documentation" not in config:
            config["documentation"] = {"model": "gpt-4", "temperature": 0.3, "max_tokens": 2048}
        
        from config.default_config import DEFAULT_PROVIDER, GEMINI_MODEL, BYTEZ_MODEL, OPENAI_MODEL
        provider = os.getenv("LLM_PROVIDER", DEFAULT_PROVIDER)
        
        # Set model based on provider
        model_map = {
            "gemini": GEMINI_MODEL,
            "bytez": BYTEZ_MODEL,
            "openai": OPENAI_MODEL
        }
        
        for key in config:
            if isinstance(config[key], dict):
                config[key]["provider"] = provider
                config[key]["model"] = model_map.get(provider, GEMINI_MODEL)
        
        _orchestrator = OrchestratorAgent(config)
    
    return _orchestrator


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application lifespan."""
    from dotenv import load_dotenv
    load_dotenv()
    
    # Startup
    yield
    
    # Shutdown
    global _orchestrator
    if _orchestrator:
        _orchestrator.cleanup()
        _orchestrator = None


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(
        title="Multi-Agent Code Review API",
        description="""
        A multi-agent system for automated code review, debugging, and improvement.
        
        ## Features
        - **Code Review**: Analyze code for quality, bugs, and security issues
        - **Bug Detection**: Identify and suggest fixes for bugs
        - **Security Audit**: Find security vulnerabilities
        - **Test Generation**: Automatically generate test cases
        - **PR Review**: Review GitHub Pull Requests
        """,
        version="1.0.0",
        lifespan=lifespan
    )
    
    # Add CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    
    # Include webhook router for GitHub integration
    app.include_router(webhook_router, prefix="/webhooks", tags=["webhooks"])
    
    @app.get("/")
    async def root():
        """Root endpoint with API information."""
        return {
            "name": "Multi-Agent Code Review API",
            "version": "1.0.0",
            "docs": "/docs",
            "health": "/health",
            "webhooks": "/webhooks/github"
        }
    
    @app.on_event("startup")
    async def startup_event():
        """Initialize background tasks."""
        logger.info("Starting up InspectAI server...")
        
        # Schedule Vector Store cleanup
        async def cleanup_loop():
            while True:
                try:
                    # Wait for 1 hour
                    await asyncio.sleep(3600)
                    
                    # Run cleanup
                    from src.memory.vector_store import VectorStore
                    # Instantiate VectorStore for cleanup (safe as it uses file locking/DB)
                    store = VectorStore()
                    cleaned = store.cleanup_inactive_repos(retention_hours=24)
                    if cleaned > 0:
                        logger.info(f"Cleanup job removed {cleaned} inactive repositories")
                        
                except Exception as e:
                    logger.error(f"Error in cleanup loop: {e}")
                    await asyncio.sleep(300)  # Retry after 5 mins on error

        asyncio.create_task(cleanup_loop())
    
    @app.get("/health")
    async def health():
        """Health check endpoint."""
        return {"status": "healthy"}
    
    @app.post("/review", response_model=TaskResponse)
    async def review_code(request: ReviewRequest):
        """
        Review code using the multi-agent system.
        
        Supported task types:
        - `code_improvement`: General code quality improvements
        - `bug_fix`: Bug detection and fixing
        - `security_audit`: Security vulnerability analysis
        - `test_generation`: Generate test cases
        - `documentation`: Generate documentation
        - `full_review`: Comprehensive review (all of the above)
        """
        try:
            orchestrator = get_orchestrator()
            
            task = {
                "type": request.task_type,
                "input": {
                    "code": request.code,
                    "requirements": request.requirements,
                    "framework": request.framework
                }
            }
            
            result = await orchestrator.process_task_async(task)
            
            return TaskResponse(
                status=result.get("status", "error"),
                task_id=result.get("task_id"),
                error=result.get("error"),
                results=result
            )
            
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))
    
    @app.post("/pr-review", response_model=TaskResponse)
    async def review_pr(request: PRReviewRequest):
        """
        Review a GitHub Pull Request.
        
        Requires `GITHUB_TOKEN` environment variable for private repos
        and posting comments.
        """
        try:
            orchestrator = get_orchestrator()
            
            task = {
                "type": "pr_review",
                "input": {
                    "repo_url": request.repo_url,
                    "pr_number": request.pr_number,
                    "post_comments": request.post_comment
                }
            }
            
            result = await orchestrator.process_task_async(task)
            
            return TaskResponse(
                status=result.get("status", "error"),
                task_id=result.get("task_id"),
                error=result.get("error"),
                results=result
            )
            
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))
    
    @app.get("/tasks")
    async def list_task_types():
        """List all supported task types."""
        return {
            "task_types": [
                {
                    "name": "code_improvement",
                    "description": "Analyze and improve code quality"
                },
                {
                    "name": "bug_fix",
                    "description": "Detect and fix bugs in code"
                },
                {
                    "name": "security_audit",
                    "description": "Analyze code for security vulnerabilities"
                },
                {
                    "name": "test_generation",
                    "description": "Generate test cases for code"
                },
                {
                    "name": "documentation",
                    "description": "Generate documentation for code"
                },
                {
                    "name": "full_review",
                    "description": "Comprehensive review combining all agents"
                },
                {
                    "name": "pr_review",
                    "description": "Review a GitHub Pull Request"
                }
            ]
        }
    
    return app

app = create_app()
