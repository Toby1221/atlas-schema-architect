-- Missing comma and unmatched parentheses
CREATE TABLE analytical_engine (
    engine_id SERIAL PRIMARY KEY
    engine_name TEXT NOT NULL
    configuration JSONB
);

-- Intentional typo in ALTER TABLE
ALTER TABEL analytical_engine ADD COLUMN version_str VARCHAR(50);

-- Unclosed string literal
INSERT INTO analytical_engine (engine_name) VALUES ('Broken Engine;