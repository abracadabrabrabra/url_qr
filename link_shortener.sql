CREATE TABLE users (
    id BIGSERIAL PRIMARY KEY,
    email VARCHAR(255) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    created_at TIMESTAMP DEFAULT NOW(),
    is_active BOOLEAN DEFAULT true
);

CREATE TABLE links (
    short_key VARCHAR(30) PRIMARY KEY,
    original_url TEXT NOT NULL,
    user_id BIGINT REFERENCES users(id) ON DELETE SET NULL,
    created_at TIMESTAMP DEFAULT NOW(),
    expires_at TIMESTAMP,
    clicks_count INTEGER DEFAULT 0,
    is_active BOOLEAN DEFAULT true,
    deleted_at TIMESTAMP
);

CREATE INDEX idx_links_user_id ON links(user_id);
CREATE INDEX idx_links_active ON links(short_key) WHERE is_active = true;

CREATE TABLE visits (
    id BIGSERIAL PRIMARY KEY,
    short_key VARCHAR(30) REFERENCES links(short_key) ON DELETE CASCADE,
    visited_at TIMESTAMP DEFAULT NOW(),
    ip_address INET,
    user_agent TEXT,
    referer TEXT,
    geo_country VARCHAR(2),
    device_type VARCHAR(20),
    browser VARCHAR(20)
);

CREATE INDEX idx_visits_short_key ON visits(short_key);
CREATE INDEX idx_visits_visited_at ON visits(visited_at);

CREATE TABLE refresh_tokens (
    id BIGSERIAL PRIMARY KEY,
    token_hash VARCHAR(255) NOT NULL UNIQUE,
    user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    expires_at TIMESTAMP NOT NULL,
    revoked BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT NOW(),
    last_used_at TIMESTAMP,
    user_agent TEXT,
    ip_address VARCHAR(50)
);

CREATE  INDEX idx_refresh_tokens_user_id ON refresh_tokens(user_id);
CREATE  INDEX idx_refresh_tokens_token_hash ON refresh_tokens(token_hash);
CREATE  INDEX idx_refresh_tokens_expires_at ON refresh_tokens(expires_at);

CREATE TABLE password_reset_tokens (
    id BIGSERIAL PRIMARY KEY,
    token_hash VARCHAR(255) NOT NULL UNIQUE,
    user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    expires_at TIMESTAMP NOT NULL,
    used BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT NOW(),
    ip_address VARCHAR(45),
    user_agent TEXT
);

CREATE INDEX idx_reset_tokens_user_id ON password_reset_tokens(user_id);
CREATE INDEX idx_reset_tokens_token_hash ON password_reset_tokens(token_hash);
CREATE INDEX idx_reset_tokens_expires_at ON password_reset_tokens(expires_at);

CREATE OR REPLACE FUNCTION update_link_status()
RETURNS TRIGGER AS $$
BEGIN
    IF NEW.expires_at IS NOT NULL AND NEW.expires_at < NOW() THEN
        NEW.is_active := false;
        IF NEW.deleted_at IS NULL THEN
            NEW.deleted_at := NOW();
        END IF;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER update_link_status_trigger
    BEFORE INSERT OR UPDATE OF expires_at ON links
    FOR EACH ROW
    EXECUTE FUNCTION update_link_status();
