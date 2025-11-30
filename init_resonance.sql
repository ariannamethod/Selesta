-- Resonance Database Schema
-- Used by resonance_rotation.py to initialize fresh databases

CREATE TABLE IF NOT EXISTS resonance_notes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
    content TEXT NOT NULL,
    context TEXT,
    source TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_source ON resonance_notes(source);
CREATE INDEX IF NOT EXISTS idx_timestamp ON resonance_notes(timestamp);

-- Insert initial system note
INSERT INTO resonance_notes (content, context, source) VALUES
('Fresh resonance database initialized. This is the beginning of a new memory cycle.', 'system', 'resonance_rotation');
