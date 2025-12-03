"""Codebase Indexer - Stores parsed code in Supabase.

This module handles:
- Project registration and management
- Storing parsed symbols, imports, calls
- Querying for impact analysis
- Incremental updates
"""

import os
import logging
import asyncio
from typing import Dict, List, Optional, Any
from datetime import datetime
from dataclasses import asdict

logger = logging.getLogger(__name__)

# Import Supabase client
try:
    from supabase import create_client, Client
except ImportError:
    logger.error("supabase package not installed. Run: pip install supabase")
    create_client = None
    Client = None

from .code_parser import ParsedFile, ParsedSymbol, ParsedImport, ParsedCall


class CodebaseIndexer:
    """Manages codebase indexing in Supabase."""
    
    def __init__(self, supabase_url: str = None, supabase_key: str = None):
        """Initialize the indexer with Supabase credentials.
        
        Args:
            supabase_url: Supabase project URL (or from SUPABASE_URL env)
            supabase_key: Supabase API key (or from SUPABASE_KEY env)
        """
        self.supabase_url = supabase_url or os.getenv("SUPABASE_URL")
        self.supabase_key = supabase_key or os.getenv("SUPABASE_KEY")
        
        if not self.supabase_url or not self.supabase_key:
            logger.warning("Supabase credentials not configured. Indexing disabled.")
            self.client = None
        elif create_client is None:
            logger.error("Supabase client not available")
            self.client = None
        else:
            self.client = create_client(self.supabase_url, self.supabase_key)
            logger.info("CodebaseIndexer initialized with Supabase")
    
    # ============================================
    # Project Management
    # ============================================
    
    async def register_project(
        self,
        repo_full_name: str,
        repo_id: int = None,
        installation_id: int = None,
        default_branch: str = "main"
    ) -> Optional[str]:
        """Register a new project for indexing.
        
        Args:
            repo_full_name: Full repo name (e.g., "owner/repo")
            repo_id: GitHub repository ID
            installation_id: GitHub App installation ID
            default_branch: Default branch name
            
        Returns:
            Project UUID or None if failed
        """
        if not self.client:
            return None
        
        try:
            # Check if project already exists
            existing = self.client.table("indexed_projects") \
                .select("id") \
                .eq("repo_full_name", repo_full_name) \
                .execute()
            
            if existing.data:
                logger.info(f"Project {repo_full_name} already registered")
                return existing.data[0]["id"]
            
            # Create new project
            result = self.client.table("indexed_projects").insert({
                "repo_full_name": repo_full_name,
                "repo_id": repo_id,
                "installation_id": installation_id,
                "default_branch": default_branch,
                "indexing_status": "pending"
            }).execute()
            
            if result.data:
                project_id = result.data[0]["id"]
                logger.info(f"Registered project {repo_full_name} with ID {project_id}")
                return project_id
            
            return None
            
        except Exception as e:
            logger.error(f"Error registering project {repo_full_name}: {e}")
            return None
    
    async def get_project(self, repo_full_name: str) -> Optional[Dict]:
        """Get project by repo name.
        
        Args:
            repo_full_name: Full repo name
            
        Returns:
            Project data dict or None
        """
        if not self.client:
            return None
        
        try:
            result = self.client.table("indexed_projects") \
                .select("*") \
                .eq("repo_full_name", repo_full_name) \
                .execute()
            
            return result.data[0] if result.data else None
            
        except Exception as e:
            logger.error(f"Error getting project {repo_full_name}: {e}")
            return None
    
    async def update_project_status(
        self,
        project_id: str,
        status: str,
        commit_sha: str = None,
        stats: Dict = None
    ) -> bool:
        """Update project indexing status.
        
        Args:
            project_id: Project UUID
            status: New status (pending, indexing, completed, failed)
            commit_sha: Latest indexed commit SHA
            stats: Optional statistics to update
            
        Returns:
            Success boolean
        """
        if not self.client:
            return False
        
        try:
            update_data = {
                "indexing_status": status,
                "updated_at": datetime.utcnow().isoformat()
            }
            
            if status == "completed":
                update_data["last_indexed_at"] = datetime.utcnow().isoformat()
            
            if commit_sha:
                update_data["last_commit_sha"] = commit_sha
            
            if stats:
                update_data.update(stats)
            
            self.client.table("indexed_projects") \
                .update(update_data) \
                .eq("id", project_id) \
                .execute()
            
            return True
            
        except Exception as e:
            logger.error(f"Error updating project status: {e}")
            return False
    
    # ============================================
    # File Indexing
    # ============================================
    
    async def index_file(
        self,
        project_id: str,
        parsed_file: ParsedFile
    ) -> Optional[str]:
        """Index a parsed file into Supabase.
        
        Args:
            project_id: Project UUID
            parsed_file: ParsedFile object with symbols, imports, calls
            
        Returns:
            File UUID or None if failed
        """
        if not self.client:
            return None
        
        try:
            # Check if file exists (for incremental updates)
            existing = self.client.table("code_files") \
                .select("id, content_hash") \
                .eq("project_id", project_id) \
                .eq("file_path", parsed_file.file_path) \
                .execute()
            
            if existing.data:
                # File exists - check if changed
                if existing.data[0]["content_hash"] == parsed_file.content_hash:
                    logger.debug(f"File {parsed_file.file_path} unchanged, skipping")
                    return existing.data[0]["id"]
                
                # File changed - delete old data
                file_id = existing.data[0]["id"]
                await self._delete_file_data(file_id)
            else:
                file_id = None
            
            # Insert/Update file record
            file_data = {
                "project_id": project_id,
                "file_path": parsed_file.file_path,
                "language": parsed_file.language,
                "content_hash": parsed_file.content_hash,
                "line_count": parsed_file.line_count,
                "symbol_count": len(parsed_file.symbols),
                "last_indexed_at": datetime.utcnow().isoformat()
            }
            
            if file_id:
                # Update existing
                self.client.table("code_files") \
                    .update(file_data) \
                    .eq("id", file_id) \
                    .execute()
            else:
                # Insert new
                result = self.client.table("code_files") \
                    .insert(file_data) \
                    .execute()
                file_id = result.data[0]["id"]
            
            # Index symbols
            await self._index_symbols(project_id, file_id, parsed_file.symbols)
            
            # Index imports
            await self._index_imports(project_id, file_id, parsed_file.imports)
            
            # Index calls
            await self._index_calls(project_id, file_id, parsed_file.calls)
            
            logger.debug(f"Indexed file {parsed_file.file_path}: {len(parsed_file.symbols)} symbols, {len(parsed_file.calls)} calls")
            return file_id
            
        except Exception as e:
            logger.error(f"Error indexing file {parsed_file.file_path}: {e}")
            return None
    
    async def _delete_file_data(self, file_id: str):
        """Delete all data associated with a file (for re-indexing)."""
        try:
            # Delete in order (due to foreign keys)
            self.client.table("code_calls").delete().eq("caller_file_id", file_id).execute()
            self.client.table("code_imports").delete().eq("file_id", file_id).execute()
            self.client.table("code_symbols").delete().eq("file_id", file_id).execute()
        except Exception as e:
            logger.error(f"Error deleting file data: {e}")
    
    async def _index_symbols(
        self,
        project_id: str,
        file_id: str,
        symbols: List[ParsedSymbol]
    ):
        """Index symbols for a file."""
        if not symbols:
            return
        
        # Map parent names to IDs (for methods)
        parent_map = {}
        
        # First pass: Index non-methods (classes, functions)
        for symbol in symbols:
            if symbol.symbol_type != "method":
                symbol_data = {
                    "project_id": project_id,
                    "file_id": file_id,
                    "symbol_name": symbol.name,
                    "symbol_type": symbol.symbol_type,
                    "qualified_name": symbol.qualified_name,
                    "start_line": symbol.start_line,
                    "end_line": symbol.end_line,
                    "signature": symbol.signature,
                    "parameters": symbol.parameters,
                    "return_type": symbol.return_type,
                    "docstring": symbol.docstring,
                    "is_public": symbol.is_public,
                    "is_static": symbol.is_static,
                    "is_async": symbol.is_async
                }
                
                result = self.client.table("code_symbols").insert(symbol_data).execute()
                
                if result.data and symbol.symbol_type == "class":
                    parent_map[symbol.name] = result.data[0]["id"]
        
        # Second pass: Index methods with parent references
        for symbol in symbols:
            if symbol.symbol_type == "method":
                parent_id = parent_map.get(symbol.parent_name) if symbol.parent_name else None
                
                symbol_data = {
                    "project_id": project_id,
                    "file_id": file_id,
                    "symbol_name": symbol.name,
                    "symbol_type": symbol.symbol_type,
                    "qualified_name": symbol.qualified_name,
                    "start_line": symbol.start_line,
                    "end_line": symbol.end_line,
                    "signature": symbol.signature,
                    "parameters": symbol.parameters,
                    "return_type": symbol.return_type,
                    "docstring": symbol.docstring,
                    "parent_symbol_id": parent_id,
                    "is_public": symbol.is_public,
                    "is_static": symbol.is_static,
                    "is_async": symbol.is_async
                }
                
                self.client.table("code_symbols").insert(symbol_data).execute()
    
    async def _index_imports(
        self,
        project_id: str,
        file_id: str,
        imports: List[ParsedImport]
    ):
        """Index imports for a file."""
        if not imports:
            return
        
        for imp in imports:
            import_data = {
                "project_id": project_id,
                "file_id": file_id,
                "import_statement": imp.statement,
                "imported_module": imp.module,
                "imported_names": imp.names,
                "is_relative": imp.is_relative,
                "line_number": imp.line_number,
                "is_external": not imp.is_relative  # Simplified - can be improved
            }
            
            self.client.table("code_imports").insert(import_data).execute()
    
    async def _index_calls(
        self,
        project_id: str,
        file_id: str,
        calls: List[ParsedCall]
    ):
        """Index function calls for a file."""
        if not calls:
            return
        
        # Batch insert for efficiency
        call_data_list = []
        seen = set()  # Deduplicate
        
        for call in calls:
            key = (call.callee_name, call.line_number)
            if key in seen:
                continue
            seen.add(key)
            
            call_data_list.append({
                "project_id": project_id,
                "caller_file_id": file_id,
                "callee_name": call.callee_name,
                "call_line": call.line_number,
                "call_type": call.call_type
            })
        
        if call_data_list:
            # Insert in batches of 100
            batch_size = 100
            for i in range(0, len(call_data_list), batch_size):
                batch = call_data_list[i:i+batch_size]
                try:
                    self.client.table("code_calls").insert(batch).execute()
                except Exception as e:
                    # Some duplicates might fail - that's okay
                    logger.debug(f"Some calls already exist: {e}")
    
    # ============================================
    # Impact Analysis Queries
    # ============================================
    
    async def get_symbol_callers(
        self,
        project_id: str,
        symbol_name: str
    ) -> List[Dict]:
        """Get all callers of a symbol (function/method).
        
        Args:
            project_id: Project UUID
            symbol_name: Name of the symbol
            
        Returns:
            List of caller info dicts
        """
        if not self.client:
            return []
        
        try:
            result = self.client.rpc(
                "get_symbol_impact",
                {"p_project_id": project_id, "p_symbol_name": symbol_name}
            ).execute()
            
            return result.data or []
            
        except Exception as e:
            logger.error(f"Error getting symbol callers: {e}")
            return []
    
    async def get_file_dependents(
        self,
        project_id: str,
        file_path: str
    ) -> List[Dict]:
        """Get files that import/depend on a specific file.
        
        Args:
            project_id: Project UUID
            file_path: Path to the file
            
        Returns:
            List of dependent file info
        """
        if not self.client:
            return []
        
        try:
            result = self.client.rpc(
                "get_file_dependents",
                {"p_project_id": project_id, "p_file_path": file_path}
            ).execute()
            
            return result.data or []
            
        except Exception as e:
            logger.error(f"Error getting file dependents: {e}")
            return []
    
    async def get_change_impact(
        self,
        project_id: str,
        file_path: str,
        changed_lines: List[int]
    ) -> List[Dict]:
        """Get impact analysis for changed lines in a file.
        
        Args:
            project_id: Project UUID
            file_path: Path to the changed file
            changed_lines: List of line numbers that changed
            
        Returns:
            List of impacted symbols with caller counts
        """
        if not self.client:
            return []
        
        try:
            result = self.client.rpc(
                "get_change_impact",
                {
                    "p_project_id": project_id,
                    "p_file_path": file_path,
                    "p_changed_lines": changed_lines
                }
            ).execute()
            
            return result.data or []
            
        except Exception as e:
            logger.error(f"Error getting change impact: {e}")
            return []
    
    async def get_symbols_in_file(
        self,
        project_id: str,
        file_path: str
    ) -> List[Dict]:
        """Get all symbols defined in a file.
        
        Args:
            project_id: Project UUID
            file_path: Path to the file
            
        Returns:
            List of symbols
        """
        if not self.client:
            return []
        
        try:
            result = self.client.table("code_symbols") \
                .select("*, code_files!inner(file_path)") \
                .eq("project_id", project_id) \
                .eq("code_files.file_path", file_path) \
                .execute()
            
            return result.data or []
            
        except Exception as e:
            logger.error(f"Error getting symbols in file: {e}")
            return []
    
    async def get_project_stats(self, project_id: str) -> Dict:
        """Get indexing statistics for a project.
        
        Args:
            project_id: Project UUID
            
        Returns:
            Statistics dict
        """
        if not self.client:
            return {}
        
        try:
            # Get file count
            files = self.client.table("code_files") \
                .select("id", count="exact") \
                .eq("project_id", project_id) \
                .execute()
            
            # Get symbol count
            symbols = self.client.table("code_symbols") \
                .select("id", count="exact") \
                .eq("project_id", project_id) \
                .execute()
            
            # Get call count
            calls = self.client.table("code_calls") \
                .select("id", count="exact") \
                .eq("project_id", project_id) \
                .execute()
            
            return {
                "total_files": files.count or 0,
                "total_symbols": symbols.count or 0,
                "total_calls": calls.count or 0
            }
            
        except Exception as e:
            logger.error(f"Error getting project stats: {e}")
            return {}


# Singleton instance
_indexer_instance: Optional[CodebaseIndexer] = None


def get_codebase_indexer() -> CodebaseIndexer:
    """Get or create the singleton CodebaseIndexer instance."""
    global _indexer_instance
    
    if _indexer_instance is None:
        _indexer_instance = CodebaseIndexer()
    
    return _indexer_instance
