"""
프로덕션 환경 설정 프로파일

실제 운영 환경을 위한 보안 강화 설정입니다.
최소 권한 원칙과 보안 모범 사례를 따릅니다.
"""

from ..settings import (
    ServerConfig,
    ServerProfile,
    AuthConfig,
    CacheConfig,
    RateLimitConfig,
    LoggingConfig,
    RetrieverConfig,
)

# 프로덕션 환경 설정
PROD_CONFIG = ServerConfig(
    name="mcp-retriever-prod",
    profile=ServerProfile.COMPLETE,
    transport="http",  # 실제로는 리버스 프록시 뒤에서 HTTPS 사용
    port=8001,
    # 프로덕션 필수 기능
    features={
        "auth": True,  # 필수
        "context": True,  # 사용자 추적
        "cache": True,  # 성능 최적화
        "rate_limit": True,  # 필수
        "metrics": True,  # 모니터링
        "validation": True,  # 필수
        "error_handler": True,  # 필수
        "enhanced_logging": True,  # 감사 로그
    },
    # 프로덕션 인증 설정 (엄격)
    auth_config=AuthConfig(
        internal_api_key=None,  # 환경 변수에서 로드 필수 (Vault 권장)
        auth_gateway_url="https://auth-gateway.internal:8000",
        jwt_secret_key=None,  # 환경 변수에서 로드 필수 (Vault 권장)
        jwt_algorithm="HS256",
        jwt_access_token_expire_minutes=15,  # 짧은 만료 시간
        jwt_refresh_token_expire_days=3,  # 짧은 리프레시 토큰
        require_auth=True,  # 필수
    ),
    # 프로덕션 캐시 설정 (최적화)
    cache_config=CacheConfig(
        redis_url="rediss://redis-cluster.internal:6379/0",  # TLS 사용
        cache_ttl_web=300,  # 5분
        cache_ttl_vector=1800,  # 30분 (안정적인 데이터)
        cache_ttl_db=900,  # 15분
        cache_ttl_all=300,  # 5분
        enable_cache_stats=True,
    ),
    # 프로덕션 속도 제한 (엄격)
    rate_limit_config=RateLimitConfig(
        requests_per_minute=60,
        requests_per_hour=1000,
        burst_size=10,
    ),
    # 프로덕션 로깅 (보안)
    logging_config=LoggingConfig(
        log_level="WARNING",  # 중요한 이벤트만
        log_request_body=False,  # 절대 비활성화
        log_response_body=False,  # 절대 비활성화
        use_emoji=False,  # 프로덕션에서는 비활성화
        sensitive_fields=[
            "password",
            "token",
            "api_key",
            "secret",
            "auth",
            "authorization",
            "cookie",
            "session",
            "credit_card",
            "ssn",
            "email",
            "phone",
        ],
    ),
    # 프로덕션 리트리버 설정
    retriever_config=RetrieverConfig(
        tavily_api_key=None,  # 환경 변수에서 로드 (Vault 권장)
        postgres_dsn="postgresql://mcp_user:${DB_PASSWORD}@postgres-primary.internal:5432/mcp_retriever?sslmode=require",
        qdrant_host="qdrant-cluster.internal",
        qdrant_port=6333,
        qdrant_grpc_port=6334,
    ),
)
