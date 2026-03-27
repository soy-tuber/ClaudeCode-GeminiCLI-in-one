-- memory.db setup for Claude Code
-- Run: sqlite3 ~/.claude/memory.db < setup.sql
-- Note: services table lives in ~/Projects/Schedule/infra.db
--       (auto-updated by infra_sync.py via cron)

CREATE TABLE IF NOT EXISTS memories (
    id INTEGER PRIMARY KEY,
    project TEXT NOT NULL,
    category TEXT,
    title TEXT NOT NULL,
    content TEXT NOT NULL,
    keywords TEXT,
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS rules (
    id INTEGER PRIMARY KEY,
    scope TEXT NOT NULL,
    category TEXT NOT NULL,
    rule TEXT NOT NULL,
    severity TEXT DEFAULT 'error',
    keywords TEXT,
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS sessions (
    id INTEGER PRIMARY KEY,
    session_id TEXT NOT NULL UNIQUE,
    project_path TEXT,
    started_at TEXT,
    summary TEXT,
    key_actions TEXT,
    files_modified TEXT
);

-- FTS5 virtual table for cross-table full-text search
CREATE VIRTUAL TABLE IF NOT EXISTS memory_fts USING fts5(
    source_table,
    source_id,
    text,
    tokenize='unicode61'
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_memories_project ON memories(project);
CREATE INDEX IF NOT EXISTS idx_memories_category ON memories(category);
CREATE INDEX IF NOT EXISTS idx_memories_keywords ON memories(keywords);
CREATE INDEX IF NOT EXISTS idx_rules_scope ON rules(scope);
CREATE INDEX IF NOT EXISTS idx_rules_category ON rules(category);
CREATE INDEX IF NOT EXISTS idx_rules_keywords ON rules(keywords);
CREATE INDEX IF NOT EXISTS idx_sessions_project ON sessions(project_path);

-- =============================================================================
-- infra.db schema (for reference — created by infra_sync.py)
-- Run separately: sqlite3 ~/Projects/Schedule/infra.db
-- =============================================================================
--
-- CREATE TABLE IF NOT EXISTS services (
--     id INTEGER PRIMARY KEY AUTOINCREMENT,
--     port INTEGER,              -- app listening port (e.g. 8535)
--     caddy_port INTEGER,        -- Caddy reverse proxy port (e.g. 9535)
--     tunnel_port INTEGER,       -- port Cloudflare Tunnel routes to (app or caddy)
--     app_name TEXT NOT NULL,
--     hostname TEXT,              -- public hostname (e.g. dticket2.patentllm.org)
--     directory TEXT,
--     framework TEXT,             -- Streamlit / FastAPI / Flask / Gunicorn / Caddy
--     systemd_unit TEXT,
--     systemd_scope TEXT DEFAULT 'system',  -- 'system' or 'user'
--     status TEXT DEFAULT 'unknown',        -- 'active' or 'stopped'
--     is_listening INTEGER DEFAULT 0,       -- 1 if ss -tlnp confirms LISTEN
--     notes TEXT,
--     updated_at TEXT
-- );
