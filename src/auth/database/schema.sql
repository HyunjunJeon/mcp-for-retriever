-- 세밀한 리소스 권한 테이블
CREATE TABLE IF NOT EXISTS resource_permissions (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
    role_name VARCHAR(50),
    resource_type VARCHAR(50) NOT NULL CHECK (resource_type IN ('vector_db', 'database', 'web_search')),
    resource_name VARCHAR(255) NOT NULL,
    actions TEXT[] NOT NULL,
    conditions JSONB,
    granted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    granted_by INTEGER REFERENCES users(id),
    expires_at TIMESTAMP,
    UNIQUE(user_id, resource_type, resource_name)
);

-- 인덱스 생성
CREATE INDEX idx_resource_permissions_user_id ON resource_permissions(user_id);
CREATE INDEX idx_resource_permissions_role_name ON resource_permissions(role_name);
CREATE INDEX idx_resource_permissions_resource_type ON resource_permissions(resource_type);
CREATE INDEX idx_resource_permissions_resource_name ON resource_permissions(resource_name);

-- 권한 감사 로그 테이블
CREATE TABLE IF NOT EXISTS permission_audit_log (
    id SERIAL PRIMARY KEY,
    action VARCHAR(50) NOT NULL, -- GRANT, REVOKE, CHECK
    user_id INTEGER REFERENCES users(id),
    target_user_id INTEGER REFERENCES users(id),
    resource_type VARCHAR(50),
    resource_name VARCHAR(255),
    actions TEXT[],
    result BOOLEAN,
    reason TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 인덱스 생성
CREATE INDEX idx_permission_audit_log_user_id ON permission_audit_log(user_id);
CREATE INDEX idx_permission_audit_log_target_user_id ON permission_audit_log(target_user_id);
CREATE INDEX idx_permission_audit_log_created_at ON permission_audit_log(created_at);

-- 샘플 데이터 (예시)
-- guest 역할: 권한 없음
-- user 역할: public 스키마 읽기, users collection 읽기
INSERT INTO resource_permissions (role_name, resource_type, resource_name, actions) VALUES
    ('user', 'database', 'public.*', ARRAY['read']),
    ('user', 'vector_db', 'users.*', ARRAY['read']);

-- power_user 역할: 모든 collection 읽기, analytics 스키마 읽기/쓰기
INSERT INTO resource_permissions (role_name, resource_type, resource_name, actions) VALUES
    ('power_user', 'vector_db', '*', ARRAY['read']),
    ('power_user', 'database', 'analytics.*', ARRAY['read', 'write']);

-- admin은 코드에서 하드코딩된 전체 권한을 가지므로 별도 설정 불필요