"""
개발 환경 설정 프로파일

로컬 개발에 최적화된 설정입니다.
디버깅과 빠른 반복 개발을 위해 대부분의 보안 기능이 완화되어 있습니다.
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

# 개발 환경 설정
DEV_CONFIG = ServerConfig(
    name="mcp-retriever-dev",
    profile=ServerProfile.COMPLETE,
    transport="http",
    port=8001,
    # 개발 환경에서는 모든 기능 활성화 (테스트 목적)
    features={
        "auth": True,
        "context": True,
        "cache": True,
        "rate_limit": False,  # 개발 중에는 속도 제한 비활성화
        "metrics": True,
        "validation": True,
        "error_handler": True,
        "enhanced_logging": True,
    },
    # 개발용 인증 설정 (보안 완화)
    auth_config=AuthConfig(
        internal_api_key="dev-api-key-for-testing-only",
        auth_gateway_url="http://localhost:8000",
        jwt_secret_key="dev-secret-key-do-not-use-in-production",
        jwt_algorithm="HS256",
        jwt_access_token_expire_minutes=60,  # 개발 중 긴 만료 시간
        jwt_refresh_token_expire_days=7,
        require_auth=True,  # 인증 필수 - 잘못된 토큰은 항상 거부
    ),
    # 개발용 캐시 설정 (짧은 TTL)
    cache_config=CacheConfig(
        redis_url="redis://localhost:6379/0",
        cache_ttl_web=60,  # 1분 (빠른 테스트)
        cache_ttl_vector=120,  # 2분
        cache_ttl_db=90,  # 1.5분
        cache_ttl_all=60,  # 1분
        enable_cache_stats=True,
    ),
    # 개발용 속도 제한 (관대함) - 검증 통과를 위해 수정
    rate_limit_config=RateLimitConfig(
        requests_per_minute=100,
        requests_per_hour=6000,  # 100 * 60 = 6000
        burst_size=50,
    ),
    # 개발용 로깅 (상세)
    logging_config=LoggingConfig(
        log_level="DEBUG",
        log_request_body=True,
        log_response_body=True,
        use_emoji=True,
        sensitive_fields=["password", "token"],  # 최소한의 마스킹
    ),
    # 개발용 리트리버 설정
    retriever_config=RetrieverConfig(
        tavily_api_key=None,  # 환경 변수에서 로드
        postgres_dsn="postgresql://mcp_user:mcp_password@localhost:5432/mcp_retriever_dev",
        qdrant_host="localhost",
        qdrant_port=6333,
        qdrant_grpc_port=6334,
    ),
)
