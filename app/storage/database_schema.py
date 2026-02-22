"""
SQLite数据库表结构定义
拆分自 database.py，保持文件≤500行
"""

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS messages (
    id TEXT PRIMARY KEY,
    channel_id TEXT NOT NULL,
    message_id INTEGER NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    content TEXT DEFAULT '',
    filtered_content TEXT DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    data JSON
);
CREATE INDEX IF NOT EXISTS idx_messages_status ON messages(status);
CREATE INDEX IF NOT EXISTS idx_messages_channel ON messages(channel_id);
CREATE INDEX IF NOT EXISTS idx_messages_created ON messages(created_at);

CREATE VIRTUAL TABLE IF NOT EXISTS messages_fts USING fts5(
    content, filtered_content, content='messages', content_rowid='rowid'
);

CREATE TABLE IF NOT EXISTS channels (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    channel_id TEXT UNIQUE NOT NULL,
    channel_name TEXT,
    channel_title TEXT,
    config JSON,
    created_at TEXT,
    updated_at TEXT
);

CREATE TABLE IF NOT EXISTS channel_checkpoints (
    channel_id TEXT PRIMARY KEY,
    last_message_id INTEGER,
    updated_at TEXT
);

CREATE TABLE IF NOT EXISTS channel_status (
    channel_id TEXT PRIMARY KEY,
    status TEXT,
    details JSON,
    updated_at TEXT
);

CREATE TABLE IF NOT EXISTS channel_stats (
    channel_id TEXT PRIMARY KEY,
    stats JSON,
    updated_at TEXT
);

CREATE TABLE IF NOT EXISTS channel_counters (
    channel_id TEXT,
    counter_name TEXT,
    value INTEGER DEFAULT 0,
    expires_at TEXT,
    PRIMARY KEY (channel_id, counter_name)
);

CREATE TABLE IF NOT EXISTS text_fingerprints (
    message_id TEXT PRIMARY KEY,
    simhash INTEGER,
    normalized_text TEXT,
    text_length INTEGER,
    created_at TEXT,
    expires_at TEXT
);

CREATE TABLE IF NOT EXISTS text_lsh_buckets (
    band_index INTEGER,
    segment TEXT,
    message_id TEXT,
    expires_at TEXT,
    PRIMARY KEY (band_index, segment, message_id)
);

CREATE TABLE IF NOT EXISTS media_fingerprints (
    message_id TEXT PRIMARY KEY,
    phash TEXT,
    dhash TEXT,
    whash TEXT,
    average_hash TEXT,
    original_id TEXT,
    created_at TEXT,
    expires_at TEXT
);

CREATE TABLE IF NOT EXISTS media_lsh_buckets (
    bucket_key TEXT,
    payload TEXT,
    expires_at TEXT,
    PRIMARY KEY (bucket_key, payload)
);

CREATE TABLE IF NOT EXISTS media_sizes (
    file_size INTEGER,
    message_id TEXT,
    expires_at TEXT,
    PRIMARY KEY (file_size, message_id)
);

CREATE TABLE IF NOT EXISTS dup_detections (
    message_id TEXT PRIMARY KEY,
    system_detected INTEGER,
    similarity_score REAL,
    user_confirmed INTEGER,
    user_id TEXT,
    detection_time TEXT,
    feedback_time TEXT,
    expires_at TEXT
);

CREATE TABLE IF NOT EXISTS dup_feedback_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    message_id TEXT,
    created_at TEXT
);

CREATE TABLE IF NOT EXISTS sessions (
    token TEXT PRIMARY KEY,
    data JSON,
    last_activity TEXT,
    expires_at TEXT
);

CREATE TABLE IF NOT EXISTS system_configs (
    key TEXT PRIMARY KEY,
    value TEXT,
    config_type TEXT,
    description TEXT,
    is_active INTEGER DEFAULT 1,
    created_at TEXT,
    updated_at TEXT
);

CREATE TABLE IF NOT EXISTS admins (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE,
    password_hash TEXT,
    is_active INTEGER DEFAULT 1,
    is_super_admin INTEGER DEFAULT 0,
    last_login TEXT,
    created_at TEXT,
    updated_at TEXT
);

CREATE TABLE IF NOT EXISTS locks (
    lock_name TEXT PRIMARY KEY,
    identifier TEXT,
    expires_at TEXT
);

CREATE TABLE IF NOT EXISTS cache (
    key TEXT PRIMARY KEY,
    value JSON,
    expires_at TEXT
);

CREATE TABLE IF NOT EXISTS login_attempts (
    identifier TEXT PRIMARY KEY,
    attempts INTEGER DEFAULT 0,
    expires_at TEXT
);

CREATE TABLE IF NOT EXISTS stats_global (
    key TEXT PRIMARY KEY DEFAULT 'global',
    total INTEGER DEFAULT 0,
    pending INTEGER DEFAULT 0,
    approved INTEGER DEFAULT 0,
    rejected INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS stats_channels (
    channel_id TEXT PRIMARY KEY,
    total INTEGER DEFAULT 0,
    pending INTEGER DEFAULT 0,
    approved INTEGER DEFAULT 0,
    rejected INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS stats_rejection (
    reason TEXT PRIMARY KEY,
    count INTEGER DEFAULT 0
);
"""

FTS_TRIGGERS = """
CREATE TRIGGER IF NOT EXISTS messages_ai AFTER INSERT ON messages BEGIN
    INSERT INTO messages_fts(rowid, content, filtered_content)
    VALUES (NEW.rowid, NEW.content, NEW.filtered_content);
END;
CREATE TRIGGER IF NOT EXISTS messages_ad AFTER DELETE ON messages BEGIN
    INSERT INTO messages_fts(messages_fts, rowid, content, filtered_content)
    VALUES ('delete', OLD.rowid, OLD.content, OLD.filtered_content);
END;
CREATE TRIGGER IF NOT EXISTS messages_au AFTER UPDATE ON messages BEGIN
    INSERT INTO messages_fts(messages_fts, rowid, content, filtered_content)
    VALUES ('delete', OLD.rowid, OLD.content, OLD.filtered_content);
    INSERT INTO messages_fts(rowid, content, filtered_content)
    VALUES (NEW.rowid, NEW.content, NEW.filtered_content);
END;
"""
