"""Feedback System - Customer feedback loop for learning from reactions.

This module implements:
1. Storing review comments in Supabase with embeddings
2. Syncing GitHub reactions (thumbs up/down)
3. Filtering new comments based on past feedback
4. Learning from user explanations

Embeddings: Uses free sentence-transformers (local) - no API key needed!
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

# Try to import sentence-transformers (FREE, local embeddings - no API key!)
try:
    from sentence_transformers import SentenceTransformer
    SENTENCE_TRANSFORMERS_AVAILABLE = True
except ImportError:
    SENTENCE_TRANSFORMERS_AVAILABLE = False
    SentenceTransformer = None

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
        
        # Initialize embedding model (FREE - runs locally!)
        self.embedding_model = None
        if SENTENCE_TRANSFORMERS_AVAILABLE:
            try:
                # Use all-MiniLM-L6-v2: fast, good quality, 384 dimensions
                # Other options: all-mpnet-base-v2 (better but slower)
                self.embedding_model = SentenceTransformer('all-MiniLM-L6-v2')
                logger.info("Loaded sentence-transformers model for FREE local embeddings")
            except Exception as e:
                logger.warning(f"Could not load embedding model: {e}")
                self.embedding_model = None
        else:
            logger.warning(
                "sentence-transformers not installed. Run: pip install sentence-transformers\n"
                "Embeddings will be disabled (feedback filtering won't use similarity)."
            )
    
    def get_embedding(self, text: str) -> Optional[List[float]]:
        """Generate embedding for text using sentence-transformers (FREE, local).
        
        Uses all-MiniLM-L6-v2 model which produces 384-dimensional embeddings.
        No API key required - runs entirely locally!
        
        Args:
            text: Text to embed
            
        Returns:
            List of floats (embedding vector) or None if unavailable
        """
        if not self.enabled:
            return None
        
        if not self.embedding_model:
            return None
        
        try:
            # Truncate text to reasonable length (model handles up to 256 tokens well)
            truncated_text = text[:2000]
            
            # Generate embedding locally - completely free!
            embedding = self.embedding_model.encode(truncated_text, convert_to_numpy=True)
            
            # Convert to list for JSON serialization
            return embedding.tolist()
            
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
    
    async def store_written_feedback(
        self,
        github_comment_id: int,
        user_login: str,
        explanation: str,
        reaction_type: Optional[str] = None
    ) -> bool:
        """Store written feedback from a user reply to an InspectAI comment.
        
        Users can reply to InspectAI comments with text explanations like:
        - "This isn't a real bug, it's intentional behavior"
        - "Good catch! Fixed in next commit"
        
        Args:
            github_comment_id: The original InspectAI comment ID being replied to
            user_login: GitHub username of the person providing feedback
            explanation: The text of their reply/feedback
            reaction_type: Optional reaction type if they also reacted
            
        Returns:
            True if stored successfully, False otherwise
        """
        if not self.enabled:
            logger.warning("Feedback system not enabled - cannot store written feedback")
            return False
        
        try:
            # Find the comment in our database by github_comment_id
            comment_result = self.client.table("review_comments")\
                .select("id")\
                .eq("github_comment_id", github_comment_id)\
                .execute()
            
            if not comment_result.data:
                logger.warning(f"Comment {github_comment_id} not found in database")
                return False
            
            comment_id = comment_result.data[0]["id"]
            
            # Infer sentiment from explanation if no reaction provided
            if not reaction_type:
                reaction_type = self._infer_sentiment_from_text(explanation)
            
            # Upsert feedback with explanation
            self.client.table("comment_feedback").upsert({
                "comment_id": comment_id,
                "user_login": user_login,
                "reaction_type": reaction_type,
                "explanation": explanation[:2000]  # Limit to 2000 chars
            }, on_conflict="comment_id,user_login,reaction_type").execute()
            
            logger.info(
                f"Stored written feedback from {user_login} for comment {github_comment_id}: "
                f"'{explanation[:50]}...' (sentiment: {reaction_type})"
            )
            return True
            
        except Exception as e:
            logger.error(f"Error storing written feedback: {e}")
            return False
    
    def _infer_sentiment_from_text(self, text: str) -> str:
        """Infer sentiment (thumbs_up/thumbs_down) from feedback text.
        
        Simple keyword-based inference. Future: Use LLM for better analysis.
        
        Args:
            text: Feedback text to analyze
            
        Returns:
            Inferred reaction type (thumbs_up or thumbs_down)
        """
        text_lower = text.lower()
        
        # Positive indicators
        positive_keywords = [
            "good catch", "thanks", "fixed", "helpful", "great", "nice", 
            "agree", "correct", "valid", "important", "true", "right",
            "yes", "exactly", "spot on", "you're right", "good point"
        ]
        
        # Negative indicators
        negative_keywords = [
            "not a bug", "intentional", "false positive", "wrong", "incorrect",
            "disagree", "no", "irrelevant", "not relevant", "doesn't apply",
            "not applicable", "ignore", "skip", "unnecessary", "by design",
            "expected", "on purpose", "supposed to"
        ]
        
        positive_score = sum(1 for kw in positive_keywords if kw in text_lower)
        negative_score = sum(1 for kw in negative_keywords if kw in text_lower)
        
        if negative_score > positive_score:
            return "thumbs_down"
        elif positive_score > 0:
            return "thumbs_up"
        else:
            # Default to neutral/negative if unclear (more conservative)
            return "thumbs_down"
    
    async def get_feedback_for_comment(
        self,
        github_comment_id: int
    ) -> Dict[str, Any]:
        """Get all feedback for a specific comment.
        
        Args:
            github_comment_id: GitHub comment ID
            
        Returns:
            Dict with feedback counts and explanations
        """
        if not self.enabled:
            return {"enabled": False}
        
        try:
            # Find comment in our database
            comment_result = self.client.table("review_comments")\
                .select("id")\
                .eq("github_comment_id", github_comment_id)\
                .execute()
            
            if not comment_result.data:
                return {"found": False}
            
            comment_id = comment_result.data[0]["id"]
            
            # Get all feedback for this comment
            feedback_result = self.client.table("comment_feedback")\
                .select("user_login, reaction_type, explanation, created_at")\
                .eq("comment_id", comment_id)\
                .execute()
            
            feedback = feedback_result.data or []
            
            return {
                "found": True,
                "thumbs_up": sum(1 for f in feedback if f["reaction_type"] == "thumbs_up"),
                "thumbs_down": sum(1 for f in feedback if f["reaction_type"] == "thumbs_down"),
                "explanations": [
                    {
                        "user": f["user_login"],
                        "text": f["explanation"],
                        "sentiment": f["reaction_type"]
                    }
                    for f in feedback if f.get("explanation")
                ]
            }
            
        except Exception as e:
            logger.error(f"Error getting feedback: {e}")
            return {"error": str(e)}
    
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
