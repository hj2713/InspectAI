"""Codebase Indexer Package.

This package provides AST-based codebase indexing for intelligent PR reviews.

Features:
- Language parsers (Python, Java, C++)
- Background async indexing
- Impact analysis
- Context enrichment for reviews

Usage:
    from src.indexer import trigger_repo_indexing, get_enriched_context
    
    # Trigger indexing on webhook install
    await trigger_repo_indexing(
        repo_full_name="owner/repo",
        github_client=client,
        installation_id=12345
    )
    
    # Get context for review
    context = await get_enriched_context(
        repo_full_name="owner/repo",
        file_path="src/auth.py",
        diff_patch=diff_content
    )
"""

from .code_parser import (
    CodeParserFactory,
    ParsedFile,
    ParsedSymbol,
    ParsedImport,
    ParsedCall,
    PythonParser,
    JavaParser,
    CppParser,
)

from .indexer import (
    CodebaseIndexer,
    get_codebase_indexer,
)

from .background_indexer import (
    BackgroundIndexer,
    get_background_indexer,
    trigger_repo_indexing,
    ScheduledReindexer,
    get_scheduled_reindexer,
    start_scheduled_reindexing,
    stop_scheduled_reindexing,
)

from .context_enricher import (
    ContextEnricher,
    get_context_enricher,
    get_enriched_context,
)

__all__ = [
    # Parser
    "CodeParserFactory",
    "ParsedFile",
    "ParsedSymbol",
    "ParsedImport", 
    "ParsedCall",
    "PythonParser",
    "JavaParser",
    "CppParser",
    
    # Indexer
    "CodebaseIndexer",
    "get_codebase_indexer",
    
    # Background Indexer
    "BackgroundIndexer",
    "get_background_indexer",
    "trigger_repo_indexing",
    
    # Scheduled Reindexer
    "ScheduledReindexer",
    "get_scheduled_reindexer",
    "start_scheduled_reindexing",
    "stop_scheduled_reindexing",
    
    # Context Enricher
    "ContextEnricher",
    "get_context_enricher",
    "get_enriched_context",
]
