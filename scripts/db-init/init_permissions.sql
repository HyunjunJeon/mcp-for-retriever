-- 세밀한 리소스 권한 초기화 스크립트
-- MCP Retriever 프로젝트의 역할별 기본 권한 설정

-- 기존 권한 삭제 (테스트용)
DELETE FROM resource_permissions WHERE role_name IS NOT NULL;

-- guest 역할: 권한 없음 (기본 권한만)

-- user 역할: public 스키마 읽기, users collection 읽기
INSERT INTO resource_permissions (role_name, resource_type, resource_name, actions) VALUES
    ('user', 'database', 'public.*', ARRAY['read']),
    ('user', 'vector_db', 'users.*', ARRAY['read']);

-- power_user 역할: 모든 collection 읽기, analytics 스키마 읽기/쓰기  
INSERT INTO resource_permissions (role_name, resource_type, resource_name, actions) VALUES
    ('power_user', 'vector_db', '*', ARRAY['read']),
    ('power_user', 'database', 'public.*', ARRAY['read']),
    ('power_user', 'database', 'analytics.*', ARRAY['read', 'write']);

-- admin은 코드에서 하드코딩된 전체 권한을 가지므로 별도 설정 불필요

-- 특정 사용자에게 추가 권한 부여 예시
-- INSERT INTO resource_permissions (user_id, resource_type, resource_name, actions, granted_by) VALUES
--     (1, 'vector_db', 'admin.logs', ARRAY['read'], 2),
--     (1, 'database', 'audit.*', ARRAY['read'], 2);

-- 권한 확인
SELECT 
    role_name,
    user_id,
    resource_type,
    resource_name,
    actions,
    granted_at
FROM resource_permissions
ORDER BY role_name, resource_type, resource_name;