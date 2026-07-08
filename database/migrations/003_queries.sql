-- DDL for storing user queries and session turns

CREATE TABLE IF NOT EXISTS queries (
    query_id VARCHAR(100) PRIMARY KEY,
    session_id VARCHAR(100) NOT NULL REFERENCES sessions(session_id),
    user_id VARCHAR(100) REFERENCES users(user_id),
    query_text TEXT NOT NULL,
    refined_query TEXT,
    response_text TEXT,
    domain VARCHAR(50),
    language VARCHAR(10),
    ambiguity_type VARCHAR(50),
    latency_ms INTEGER,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);
