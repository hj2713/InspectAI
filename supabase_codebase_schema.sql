-- Codebase Indexing Schema for InspectAI
-- This schema stores parsed code structure for intelligent PR reviews
-- Each project is isolated via project_id column

-- ============================================
-- Table 1: Projects (Company/Repo Registration)
-- ============================================
CREATE TABLE IF NOT EXISTS indexed_projects (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    
    -- GitHub identifiers
    repo_full_name TEXT NOT NULL,          -- e.g., "company/repo-name"
    repo_id BIGINT,                         -- GitHub repo ID
    installation_id BIGINT,                 -- GitHub App installation ID
    
    -- Indexing status
    indexing_status TEXT DEFAULT 'pending', -- pending, indexing, completed, failed
    last_indexed_at TIMESTAMPTZ,
    last_commit_sha TEXT,                   -- Last indexed commit
    
    -- Statistics
    total_files INTEGER DEFAULT 0,
    total_symbols INTEGER DEFAULT 0,
    total_calls INTEGER DEFAULT 0,
    total_dependencies INTEGER DEFAULT 0,
    
    -- Metadata
    default_branch TEXT DEFAULT 'main',
    languages JSONB DEFAULT '[]',           -- ["python", "java", "cpp"]
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    
    UNIQUE(repo_full_name)
);

-- Index for quick lookups
CREATE INDEX IF NOT EXISTS idx_projects_repo ON indexed_projects(repo_full_name);
CREATE INDEX IF NOT EXISTS idx_projects_installation ON indexed_projects(installation_id);

-- ============================================
-- Table 2: Code Files
-- ============================================
CREATE TABLE IF NOT EXISTS code_files (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES indexed_projects(id) ON DELETE CASCADE,
    
    -- File info
    file_path TEXT NOT NULL,                -- e.g., "src/auth/validator.py"
    language TEXT NOT NULL,                 -- python, java, cpp
    
    -- Content hash for change detection
    content_hash TEXT,                      -- SHA256 of file content
    
    -- Statistics
    line_count INTEGER DEFAULT 0,
    symbol_count INTEGER DEFAULT 0,
    
    -- Timestamps
    last_indexed_at TIMESTAMPTZ DEFAULT NOW(),
    
    UNIQUE(project_id, file_path)
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_files_project ON code_files(project_id);
CREATE INDEX IF NOT EXISTS idx_files_path ON code_files(file_path);
CREATE INDEX IF NOT EXISTS idx_files_language ON code_files(language);

-- ============================================
-- Table 3: Code Symbols (Functions, Classes, Variables)
-- ============================================
CREATE TABLE IF NOT EXISTS code_symbols (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES indexed_projects(id) ON DELETE CASCADE,
    file_id UUID NOT NULL REFERENCES code_files(id) ON DELETE CASCADE,
    
    -- Symbol identification
    symbol_name TEXT NOT NULL,              -- e.g., "validate_token"
    symbol_type TEXT NOT NULL,              -- function, class, method, variable, constant
    qualified_name TEXT,                    -- e.g., "auth.validator.validate_token"
    
    -- Location
    start_line INTEGER NOT NULL,
    end_line INTEGER NOT NULL,
    
    -- Signature/Details
    signature TEXT,                         -- e.g., "def validate_token(token: str) -> bool"
    parameters JSONB DEFAULT '[]',          -- [{"name": "token", "type": "str"}]
    return_type TEXT,                       -- e.g., "bool"
    
    -- Documentation
    docstring TEXT,
    
    -- Parent (for methods inside classes)
    parent_symbol_id UUID REFERENCES code_symbols(id) ON DELETE CASCADE,
    
    -- Modifiers
    is_public BOOLEAN DEFAULT true,
    is_static BOOLEAN DEFAULT false,
    is_async BOOLEAN DEFAULT false,
    
    -- Timestamps
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Indexes for fast queries
CREATE INDEX IF NOT EXISTS idx_symbols_project ON code_symbols(project_id);
CREATE INDEX IF NOT EXISTS idx_symbols_file ON code_symbols(file_id);
CREATE INDEX IF NOT EXISTS idx_symbols_name ON code_symbols(symbol_name);
CREATE INDEX IF NOT EXISTS idx_symbols_type ON code_symbols(symbol_type);
CREATE INDEX IF NOT EXISTS idx_symbols_qualified ON code_symbols(qualified_name);

-- ============================================
-- Table 4: Dependencies (Imports)
-- ============================================
CREATE TABLE IF NOT EXISTS code_imports (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES indexed_projects(id) ON DELETE CASCADE,
    file_id UUID NOT NULL REFERENCES code_files(id) ON DELETE CASCADE,
    
    -- Import details
    import_statement TEXT NOT NULL,         -- e.g., "from auth import validate_token"
    imported_module TEXT NOT NULL,          -- e.g., "auth"
    imported_names JSONB DEFAULT '[]',      -- ["validate_token", "User"]
    is_relative BOOLEAN DEFAULT false,      -- Relative import (from . import x)
    
    -- Resolved target (if internal)
    resolved_file_id UUID REFERENCES code_files(id) ON DELETE SET NULL,
    is_external BOOLEAN DEFAULT false,      -- External package (not in repo)
    
    -- Location
    line_number INTEGER,
    
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_imports_project ON code_imports(project_id);
CREATE INDEX IF NOT EXISTS idx_imports_file ON code_imports(file_id);
CREATE INDEX IF NOT EXISTS idx_imports_module ON code_imports(imported_module);

-- ============================================
-- Table 5: Call Graph (Function Calls)
-- ============================================
CREATE TABLE IF NOT EXISTS code_calls (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES indexed_projects(id) ON DELETE CASCADE,
    
    -- Caller (who makes the call)
    caller_file_id UUID NOT NULL REFERENCES code_files(id) ON DELETE CASCADE,
    caller_symbol_id UUID REFERENCES code_symbols(id) ON DELETE CASCADE,
    
    -- Callee (who is being called)
    callee_name TEXT NOT NULL,              -- Function/method name being called
    callee_symbol_id UUID REFERENCES code_symbols(id) ON DELETE SET NULL,
    
    -- Location
    call_line INTEGER NOT NULL,
    
    -- Call type
    call_type TEXT DEFAULT 'function',      -- function, method, constructor
    
    created_at TIMESTAMPTZ DEFAULT NOW(),
    
    UNIQUE(project_id, caller_file_id, callee_name, call_line)
);

-- Indexes for impact analysis
CREATE INDEX IF NOT EXISTS idx_calls_project ON code_calls(project_id);
CREATE INDEX IF NOT EXISTS idx_calls_caller_file ON code_calls(caller_file_id);
CREATE INDEX IF NOT EXISTS idx_calls_caller_symbol ON code_calls(caller_symbol_id);
CREATE INDEX IF NOT EXISTS idx_calls_callee ON code_calls(callee_symbol_id);
CREATE INDEX IF NOT EXISTS idx_calls_callee_name ON code_calls(callee_name);

-- ============================================
-- Table 6: Indexing Jobs (Background Processing)
-- ============================================
CREATE TABLE IF NOT EXISTS indexing_jobs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES indexed_projects(id) ON DELETE CASCADE,
    
    -- Job details
    job_type TEXT NOT NULL,                 -- full, incremental, file
    status TEXT DEFAULT 'pending',          -- pending, running, completed, failed
    
    -- Progress
    total_files INTEGER DEFAULT 0,
    processed_files INTEGER DEFAULT 0,
    
    -- Timing
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    
    -- Error tracking
    error_message TEXT,
    
    -- Metadata
    triggered_by TEXT,                      -- webhook, manual, scheduled
    commit_sha TEXT,
    
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Index for job queries
CREATE INDEX IF NOT EXISTS idx_jobs_project ON indexing_jobs(project_id);
CREATE INDEX IF NOT EXISTS idx_jobs_status ON indexing_jobs(status);

-- ============================================
-- Function: Get Symbol Impact (Who calls this?)
-- ============================================
CREATE OR REPLACE FUNCTION get_symbol_impact(
    p_project_id UUID,
    p_symbol_name TEXT
)
RETURNS TABLE (
    caller_file TEXT,
    caller_function TEXT,
    call_line INTEGER,
    caller_file_id UUID
) AS $$
BEGIN
    RETURN QUERY
    SELECT 
        cf.file_path as caller_file,
        cs.symbol_name as caller_function,
        cc.call_line,
        cc.caller_file_id
    FROM code_calls cc
    JOIN code_files cf ON cc.caller_file_id = cf.id
    LEFT JOIN code_symbols cs ON cc.caller_symbol_id = cs.id
    WHERE cc.project_id = p_project_id
      AND cc.callee_name = p_symbol_name
    ORDER BY cf.file_path, cc.call_line;
END;
$$ LANGUAGE plpgsql;

-- ============================================
-- Function: Get Symbol Dependencies (What does this call?)
-- ============================================
CREATE OR REPLACE FUNCTION get_symbol_dependencies(
    p_project_id UUID,
    p_symbol_id UUID
)
RETURNS TABLE (
    callee_name TEXT,
    callee_file TEXT,
    call_line INTEGER
) AS $$
BEGIN
    RETURN QUERY
    SELECT 
        cc.callee_name,
        cf.file_path as callee_file,
        cc.call_line
    FROM code_calls cc
    LEFT JOIN code_symbols cs ON cc.callee_symbol_id = cs.id
    LEFT JOIN code_files cf ON cs.file_id = cf.id
    WHERE cc.project_id = p_project_id
      AND cc.caller_symbol_id = p_symbol_id
    ORDER BY cc.call_line;
END;
$$ LANGUAGE plpgsql;

-- ============================================
-- Function: Get File Dependents (What files import this?)
-- ============================================
CREATE OR REPLACE FUNCTION get_file_dependents(
    p_project_id UUID,
    p_file_path TEXT
)
RETURNS TABLE (
    dependent_file TEXT,
    import_statement TEXT,
    line_number INTEGER
) AS $$
BEGIN
    RETURN QUERY
    SELECT 
        cf.file_path as dependent_file,
        ci.import_statement,
        ci.line_number
    FROM code_imports ci
    JOIN code_files cf ON ci.file_id = cf.id
    JOIN code_files target ON ci.resolved_file_id = target.id
    WHERE ci.project_id = p_project_id
      AND target.file_path = p_file_path
    ORDER BY cf.file_path;
END;
$$ LANGUAGE plpgsql;

-- ============================================
-- Function: Get Changed Symbols Impact Summary
-- ============================================
CREATE OR REPLACE FUNCTION get_change_impact(
    p_project_id UUID,
    p_file_path TEXT,
    p_changed_lines INTEGER[]
)
RETURNS TABLE (
    symbol_name TEXT,
    symbol_type TEXT,
    start_line INTEGER,
    end_line INTEGER,
    caller_count BIGINT,
    impact_level TEXT
) AS $$
BEGIN
    RETURN QUERY
    SELECT 
        cs.symbol_name,
        cs.symbol_type,
        cs.start_line,
        cs.end_line,
        COUNT(DISTINCT cc.id) as caller_count,
        CASE 
            WHEN COUNT(DISTINCT cc.id) > 10 THEN 'HIGH'
            WHEN COUNT(DISTINCT cc.id) > 3 THEN 'MEDIUM'
            ELSE 'LOW'
        END as impact_level
    FROM code_symbols cs
    JOIN code_files cf ON cs.file_id = cf.id
    LEFT JOIN code_calls cc ON cc.callee_symbol_id = cs.id
    WHERE cs.project_id = p_project_id
      AND cf.file_path = p_file_path
      AND (
          cs.start_line = ANY(p_changed_lines)
          OR cs.end_line = ANY(p_changed_lines)
          OR EXISTS (
              SELECT 1 FROM unnest(p_changed_lines) AS changed_line
              WHERE changed_line BETWEEN cs.start_line AND cs.end_line
          )
      )
    GROUP BY cs.id, cs.symbol_name, cs.symbol_type, cs.start_line, cs.end_line
    ORDER BY caller_count DESC;
END;
$$ LANGUAGE plpgsql;

-- ============================================
-- Trigger: Update project updated_at
-- ============================================
CREATE OR REPLACE FUNCTION update_project_timestamp()
RETURNS TRIGGER AS $$
BEGIN
    UPDATE indexed_projects 
    SET updated_at = NOW() 
    WHERE id = NEW.project_id;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Apply trigger to symbol changes
DROP TRIGGER IF EXISTS trigger_update_project_on_symbol ON code_symbols;
CREATE TRIGGER trigger_update_project_on_symbol
    AFTER INSERT OR UPDATE ON code_symbols
    FOR EACH ROW EXECUTE FUNCTION update_project_timestamp();

-- ============================================
-- Row Level Security (Optional but Recommended)
-- ============================================
-- Uncomment these if you want RLS enabled

-- ALTER TABLE indexed_projects ENABLE ROW LEVEL SECURITY;
-- ALTER TABLE code_files ENABLE ROW LEVEL SECURITY;
-- ALTER TABLE code_symbols ENABLE ROW LEVEL SECURITY;
-- ALTER TABLE code_imports ENABLE ROW LEVEL SECURITY;
-- ALTER TABLE code_calls ENABLE ROW LEVEL SECURITY;
-- ALTER TABLE indexing_jobs ENABLE ROW LEVEL SECURITY;

-- ============================================
-- Sample Queries for Reference
-- ============================================

-- Find all callers of a function:
-- SELECT * FROM get_symbol_impact('project-uuid', 'validate_token');

-- Find what a function depends on:
-- SELECT * FROM get_symbol_dependencies('project-uuid', 'symbol-uuid');

-- Find files that import a specific file:
-- SELECT * FROM get_file_dependents('project-uuid', 'src/auth/validator.py');

-- Get impact of changed lines:
-- SELECT * FROM get_change_impact('project-uuid', 'src/auth/validator.py', ARRAY[10,11,12,15]);

-- Get all functions in a file:
-- SELECT symbol_name, signature, start_line, end_line 
-- FROM code_symbols cs
-- JOIN code_files cf ON cs.file_id = cf.id
-- WHERE cf.file_path = 'src/auth/validator.py' AND cs.symbol_type = 'function';
