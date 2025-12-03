"""Feedback System - Customer feedback loop for learning from reactions.

This module implements:
1. Storing review comments in Supabase with embeddings
2. Syncing GitHub reactions (thumbs up/down)
3. Filtering new comments based on past feedback
4. Learning from user explanations
"""
import os
import logging
import hashlib
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
import asyncio

# Try to import supabase - graceful fallback if not installed
try:
    from supabase import create_client, Client
    SUPABASE_AVAILABLE = True
except ImportError:
    SUPABASE_AVAILABLE = False
    create_client = None
    Client = None

# Try to import openai
try:
    import openai
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False
    openai = None

logger = logging.getLogger(__name__)


class FeedbackSystem:
    """Manages customer feedback loop for continuous improvement."""
    
    def __init__(self):
        """Initialize Supabase client and OpenAI."""
        self.enabled = False
        self.client = None
        
        # Check if supabase is available
        if not SUPABASE_AVAILABLE:
            logger.warning("supabase-py not installed. Feedback system disabled.")
            return
        
        supabase_url = os.getenv("SUPABASE_URL")
        supabase_key = os.getenv("SUPABASE_KEY")
        
        if not supabase_url or not supabase_key:
            logger.warning("Supabase credentials not found. Feedback system disabled.")
            return
        
        try:
            self.client = create_client(supabase_url, supabase_key)
            self.enabled = True
            logger.info("Feedback system initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize Supabase client: {e}")
            self.client = None
        
        # OpenAI for embeddings
        if OPENAI_AVAILABLE and openai:
            openai.api_key = os.getenv("OPENAI_API_KEY") or os.getenv("GEMINI_API_KEY")
    
    def get_embedding(self, text: str) -> Optional[List[float]]:
        """Generate embedding for text using OpenAI.
        
        Args:
            text: Text to embed
            
        Returns:
            List of floats (embedding vector) or None on error
        """
        if not self.enabled:
            return None
        
        if not OPENAI_AVAILABLE or not openai:
            return None
        
        try:
            # Use OpenAI if available, otherwise skip embeddings
            if os.getenv("OPENAI_API_KEY"):
                response = openai.embeddings.create(
                    model="text-embedding-ada-002",
                    input=text[:8000]  # Limit to 8K chars
                )
                return response.data[0].embedding
            else:
                logger.warning("OpenAI API key not found. Embeddings disabled.")
                return None
        except Exception as e:
            logger.error(f"Error generating embedding: {e}")
            return None
    
    async def store_comment(
        self,
        repo_full_name: str,
        pr_number: int,
        file_path: str,
        line_number: int,
        comment_body: str,
        category: str,
        severity: str,
        github_comment_id: Optional[int] = None,
        command_type: str = "review"
    ) -> Optional[str]:
        """Store a review comment in Supabase.
        
        Args:
            repo_full_name: Repository name (owner/repo)
            pr_number: Pull request number
            file_path: File path where comment was posted
            line_number: Line number of comment
            comment_body: Comment text
            category: Category of issue (e.g., "Logic Error")
            severity: Severity level (critical/high/medium/low)
            github_comment_id: GitHub comment ID
            command_type: Command that generated comment (review/bugs/refactor)
            
        Returns:
            Comment UUID or None on error
        """
        if not self.enabled:
            return None
        
        try:
            # Generate embedding
            embedding = self.get_embedding(comment_body)
            
            # Insert into database
            result = self.client.table("review_comments").insert({
                "repo_full_name": repo_full_name,
                "pr_number": pr_number,
                "file_path": file_path,
                "line_number": line_number,
                "comment_body": comment_body,
                "category": category,
                "severity": severity,
                "embedding": embedding,
                "github_comment_id": github_comment_id,
                "command_type": command_type
            }).execute()
            
            comment_id = result.data[0]["id"] if result.data else None
            logger.info(f"Stored comment {comment_id} for {repo_full_name}#{pr_number}")
            return comment_id
            
        except Exception as e:
            logger.error(f"Error storing comment: {e}")
            return None
    
    async def sync_github_reactions(
        self,
        github_client,
        repo_full_name: str,
        days_back: int = 7
    ) -> int:
        """Sync reactions from GitHub for recent comments.
        
        Args:
            github_client: GitHub API client
            repo_full_name: Repository name
            days_back: How many days back to sync
            
        Returns:
            Number of reactions synced
        """
        if not self.enabled:
            return 0
        
        try:
            # Get recent comments from our database
            cutoff_date = (datetime.now() - timedelta(days=days_back)).isoformat()
            result = self.client.table("review_comments")\
                .select("id, github_comment_id")\
                .eq("repo_full_name", repo_full_name)\
                .gte("posted_at", cutoff_date)\
                .not_.is_("github_comment_id", "null")\
                .execute()
            
            if not result.data:
                return 0
            
            reactions_synced = 0
            
            for comment in result.data:
                try:
                    # Fetch reactions from GitHub
                    reactions = github_client.get_comment_reactions(
                        comment["github_comment_id"]
                    )
                    
                    # Store each reaction
                    for reaction in reactions:
                        self.client.table("comment_feedback").upsert({
                            "comment_id": comment["id"],
                            "user_login": reaction["user"]["login"],
                            "reaction_type": self._normalize_reaction(reaction["content"])
                        }, on_conflict="comment_id,user_login,reaction_type").execute()
                        reactions_synced += 1
                        
                except Exception as e:
                    logger.error(f"Error syncing reactions for comment {comment['id']}: {e}")
                    continue
            
            logger.info(f"Synced {reactions_synced} reactions for {repo_full_name}")
            return reactions_synced
            
        except Exception as e:
            logger.error(f"Error in sync_github_reactions: {e}")
            return 0
    
    def _normalize_reaction(self, github_reaction: str) -> str:
        """Normalize GitHub reaction types to our schema.
        
        Args:
            github_reaction: GitHub reaction (+1, -1, laugh, etc.)
            
        Returns:
            Normalized reaction type
        """
        reaction_map = {
            "+1": "thumbs_up",
            "-1": "thumbs_down",
            "laugh": "laugh",
            "confused": "confused",
            "heart": "heart",
            "hooray": "hooray",
            "rocket": "rocket",
            "eyes": "eyes"
        }
        return reaction_map.get(github_reaction, "thumbs_up")
    
    async def filter_by_feedback(
        self,
        comments: List[Dict[str, Any]],
        repo_full_name: str
    ) -> List[Dict[str, Any]]:
        """Filter comments based on past feedback from similar comments.
        
        Args:
            comments: List of new comments to filter
            repo_full_name: Repository name for context
            
        Returns:
            Filtered list of comments
        """
        if not self.enabled or not comments:
            return comments
        
        filtered = []
        stats = {
            "total": len(comments),
            "filtered": 0,
            "boosted": 0
        }
        
        for comment in comments:
            # Get embedding for this comment
            embedding = self.get_embedding(comment.get("description", ""))
            
            if not embedding:
                # No embedding, keep comment unchanged
                filtered.append(comment)
                continue
            
            try:
                # Find similar past comments using Supabase function
                result = self.client.rpc(
                    "match_similar_comments",
                    {
                        "query_embedding": embedding,
                        "match_threshold": 0.85,  # 85% similarity
                        "match_count": 5,
                        "repo_filter": repo_full_name
                    }
                ).execute()
                
                if not result.data:
                    # No similar comments, keep as-is
                    filtered.append(comment)
                    continue
                
                # Analyze feedback on similar comments
                total_positive = sum(row["positive_feedback_count"] for row in result.data)
                total_negative = sum(row["negative_feedback_count"] for row in result.data)
                
                # Decision logic
                if total_negative > total_positive and total_negative >= 2:
                    # Similar comments were downvoted - filter out
                    logger.info(
                        f"Filtering comment '{comment.get('category')}' "
                        f"(similar to {total_negative} downvoted comments)"
                    )
                    stats["filtered"] += 1
                    continue
                
                elif total_positive > total_negative and total_positive >= 2:
                    # Similar comments were upvoted - boost confidence
                    original_confidence = comment.get("confidence", 0.7)
                    comment["confidence"] = min(original_confidence * 1.2, 1.0)
                    logger.info(
                        f"Boosting comment '{comment.get('category')}' "
                        f"(similar to {total_positive} upvoted comments)"
                    )
                    stats["boosted"] += 1
                
                filtered.append(comment)
                
            except Exception as e:
                logger.error(f"Error in feedback filtering: {e}")
                # On error, keep the comment
                filtered.append(comment)
        
        logger.info(
            f"Feedback filter: {stats['total']} total, "
            f"{stats['filtered']} filtered, {stats['boosted']} boosted"
        )
        
        return filtered
    
    async def record_filter_stats(
        self,
        repo_full_name: str,
        pr_number: int,
        command_type: str,
        total_generated: int,
        filtered_count: int,
        boosted_count: int
    ):
        """Record feedback filter statistics.
        
        Args:
            repo_full_name: Repository name
            pr_number: PR number
            command_type: Command type (review/bugs/refactor)
            total_generated: Total comments generated
            filtered_count: Number filtered by feedback
            boosted_count: Number boosted by feedback
        """
        if not self.enabled:
            return
        
        try:
            self.client.table("feedback_filter_stats").insert({
                "repo_full_name": repo_full_name,
                "pr_number": pr_number,
                "command_type": command_type,
                "total_comments_generated": total_generated,
                "comments_filtered_by_feedback": filtered_count,
                "comments_boosted_by_feedback": boosted_count
            }).execute()
        except Exception as e:
            logger.error(f"Error recording filter stats: {e}")


# Global instance
_feedback_system = None


def get_feedback_system() -> FeedbackSystem:
    """Get or create the global feedback system instance."""
    global _feedback_system
    if _feedback_system is None:
        _feedback_system = FeedbackSystem()
    return _feedback_system
