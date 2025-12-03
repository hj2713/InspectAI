-- InspectAI Feedback System Schema
-- Run this in your Supabase SQL Editor: https://qwwvadfeyhlzjzjpvnto.supabase.co

-- Enable pgvector extension for similarity search
CREATE EXTENSION IF NOT EXISTS vector;

-- Table 1: Store all review comments we've posted
CREATE TABLE IF NOT EXISTS review_comments (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    repo_full_name TEXT NOT NULL,
    pr_number INTEGER NOT NULL,
    file_path TEXT,
    line_number INTEGER,
    comment_body TEXT NOT NULL,
    category TEXT, -- "Logic Error", "Security", "Performance", etc.
    severity TEXT CHECK (severity IN ('critical', 'high', 'medium', 'low')),
    embedding VECTOR(1536), -- OpenAI text-embedding-ada-002 dimensions
    posted_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    github_comment_id BIGINT UNIQUE, -- Link to GitHub comment ID
    command_type TEXT, -- "review", "bugs", "refactor"
    
    -- Indexes for fast queries
    CONSTRAINT valid_severity CHECK (severity IN ('critical', 'high', 'medium', 'low'))
);

-- Table 2: Store user feedback (reactions from GitHub)
CREATE TABLE IF NOT EXISTS comment_feedback (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    comment_id UUID REFERENCES review_comments(id) ON DELETE CASCADE,
    user_login TEXT NOT NULL, -- GitHub username
    reaction_type TEXT CHECK (reaction_type IN (
        'thumbs_up', 'thumbs_down', 'laugh', 'confused', 
        'heart', 'hooray', 'rocket', 'eyes'
    )),
    explanation TEXT, -- User's written explanation (from reply comment)
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    
    -- Prevent duplicate reactions from same user
    UNIQUE(comment_id, user_login, reaction_type)
);

-- Table 3: Feedback filter stats (for monitoring)
CREATE TABLE IF NOT EXISTS feedback_filter_stats (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    repo_full_name TEXT NOT NULL,
    pr_number INTEGER NOT NULL,
    command_type TEXT,
    total_comments_generated INTEGER DEFAULT 0,
    comments_filtered_by_feedback INTEGER DEFAULT 0,
    comments_boosted_by_feedback INTEGER DEFAULT 0,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Indexes for fast similarity search and queries
CREATE INDEX IF NOT EXISTS idx_review_comments_embedding ON review_comments 
    USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 100);

CREATE INDEX IF NOT EXISTS idx_review_comments_repo_pr ON review_comments (repo_full_name, pr_number);
CREATE INDEX IF NOT EXISTS idx_review_comments_posted_at ON review_comments (posted_at DESC);
CREATE INDEX IF NOT EXISTS idx_comment_feedback_comment_id ON comment_feedback (comment_id);
CREATE INDEX IF NOT EXISTS idx_comment_feedback_reaction ON comment_feedback (comment_id, reaction_type);

-- Function: Find similar comments based on embedding similarity
CREATE OR REPLACE FUNCTION match_similar_comments(
    query_embedding VECTOR(1536),
    match_threshold FLOAT DEFAULT 0.85,
    match_count INT DEFAULT 5,
    repo_filter TEXT DEFAULT NULL
)
RETURNS TABLE (
    id UUID,
    comment_body TEXT,
    category TEXT,
    severity TEXT,
    similarity FLOAT,
    positive_feedback_count BIGINT,
    negative_feedback_count BIGINT
)
LANGUAGE plpgsql
AS $$
BEGIN
    RETURN QUERY
    SELECT
        rc.id,
        rc.comment_body,
        rc.category,
        rc.severity,
        1 - (rc.embedding <=> query_embedding) AS similarity,
        COUNT(CASE WHEN cf.reaction_type = 'thumbs_up' THEN 1 END) AS positive_feedback_count,
        COUNT(CASE WHEN cf.reaction_type = 'thumbs_down' THEN 1 END) AS negative_feedback_count
    FROM review_comments rc
    LEFT JOIN comment_feedback cf ON rc.id = cf.comment_id
    WHERE 
        (repo_filter IS NULL OR rc.repo_full_name = repo_filter)
        AND rc.embedding IS NOT NULL
        AND 1 - (rc.embedding <=> query_embedding) > match_threshold
    GROUP BY rc.id, rc.comment_body, rc.category, rc.severity, rc.embedding
    ORDER BY rc.embedding <=> query_embedding
    LIMIT match_count;
END;
$$;

-- Table 4: Vector Documents (for code indexing, replaces ChromaDB)
CREATE TABLE IF NOT EXISTS vector_documents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    content TEXT NOT NULL,
    metadata JSONB DEFAULT '{}',
    repo_id TEXT NOT NULL,
    doc_type TEXT DEFAULT 'general',
    embedding VECTOR(1536),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Indexes for vector_documents
CREATE INDEX IF NOT EXISTS idx_vector_documents_repo ON vector_documents (repo_id);
CREATE INDEX IF NOT EXISTS idx_vector_documents_type ON vector_documents (doc_type);
CREATE INDEX IF NOT EXISTS idx_vector_documents_created ON vector_documents (created_at DESC);
CREATE INDEX IF NOT EXISTS idx_vector_documents_embedding ON vector_documents 
    USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 100);

-- Function: Match vector documents by similarity
CREATE OR REPLACE FUNCTION match_vector_documents(
    query_embedding VECTOR(1536),
    match_threshold FLOAT DEFAULT 0.7,
    match_count INT DEFAULT 5,
    repo_filter TEXT DEFAULT NULL
)
RETURNS TABLE (
    id UUID,
    content TEXT,
    metadata JSONB,
    similarity FLOAT
)
LANGUAGE plpgsql
AS $$
BEGIN
    RETURN QUERY
    SELECT
        vd.id,
        vd.content,
        vd.metadata,
        1 - (vd.embedding <=> query_embedding) AS similarity
    FROM vector_documents vd
    WHERE 
        (repo_filter IS NULL OR vd.repo_id = repo_filter)
        AND vd.embedding IS NOT NULL
        AND 1 - (vd.embedding <=> query_embedding) > match_threshold
    ORDER BY vd.embedding <=> query_embedding
    LIMIT match_count;
END;
$$;

-- Function: Get feedback summary for a comment
CREATE OR REPLACE FUNCTION get_comment_feedback_summary(comment_uuid UUID)
RETURNS TABLE (
    thumbs_up_count BIGINT,
    thumbs_down_count BIGINT,
    total_reactions BIGINT,
    sentiment_score FLOAT
)
LANGUAGE plpgsql
AS $$
BEGIN
    RETURN QUERY
    SELECT
        COUNT(CASE WHEN reaction_type = 'thumbs_up' THEN 1 END) AS thumbs_up_count,
        COUNT(CASE WHEN reaction_type = 'thumbs_down' THEN 1 END) AS thumbs_down_count,
        COUNT(*) AS total_reactions,
        (COUNT(CASE WHEN reaction_type = 'thumbs_up' THEN 1 END)::FLOAT - 
         COUNT(CASE WHEN reaction_type = 'thumbs_down' THEN 1 END)::FLOAT) / 
        GREATEST(COUNT(*)::FLOAT, 1) AS sentiment_score
    FROM comment_feedback
    WHERE comment_id = comment_uuid;
END;
$$;

-- Sample queries to test after setup:

-- 1. Find all comments with negative feedback
-- SELECT rc.*, COUNT(cf.id) as negative_count
-- FROM review_comments rc
-- JOIN comment_feedback cf ON rc.id = cf.comment_id
-- WHERE cf.reaction_type = 'thumbs_down'
-- GROUP BY rc.id
-- ORDER BY negative_count DESC;

-- 2. Get feedback stats by repo
-- SELECT 
--     repo_full_name,
--     COUNT(DISTINCT rc.id) as total_comments,
--     COUNT(cf.id) as total_feedback,
--     COUNT(CASE WHEN cf.reaction_type = 'thumbs_up' THEN 1 END) as positive,
--     COUNT(CASE WHEN cf.reaction_type = 'thumbs_down' THEN 1 END) as negative
-- FROM review_comments rc
-- LEFT JOIN comment_feedback cf ON rc.id = cf.comment_id
-- GROUP BY repo_full_name;

