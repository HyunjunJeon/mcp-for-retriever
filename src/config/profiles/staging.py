"""
스테이징 환경 설정 프로파일

프로덕션과 유사한 환경에서 테스트하기 위한 설정입니다.
보안은 강화되어 있지만 디버깅을 위한 일부 기능은 활성화되어 있습니다.
"""

from ..settings import (
    ServerConfig,
    ServerProfile,
    AuthConfig,
    CacheConfig,
    RateLimitConfig,
    LoggingConfig,
    RetrieverConfig
)

# 스테이징 환경 설정
STAGING_CONFIG = ServerConfig(
    name="mcp-retriever-staging",
    profile=ServerProfile.COMPLETE,
    transport="http",
    port=8001,
    
    # 스테이징에서는 프로덕션과 동일한 기능 활성화
    features={
        "auth": True,
        "context": True,
        "cache": True,
        "rate_limit": True,
        "metrics": True,
        "validation": True,
        "error_handler": True,
        "enhanced_logging": True,
    },
    
    # 스테이징용 인증 설정
    auth_config=AuthConfig(
        internal_api_key=None,  # 환경 변수에서 로드 필수
        auth_gateway_url="http://auth-gateway-staging:8000",
        jwt_secret_key=None,  # 환경 변수에서 로드 필수
        jwt_algorithm="HS256",
        jwt_access_token_expire_minutes=30,
        jwt_refresh_token_expire_days=7,
        require_auth=True,
    ),
    
    # 스테이징용 캐시 설정
    cache_config=CacheConfig(
        redis_url="redis://redis-staging:6379/0",
        cache_ttl_web=300,     # 5분
        cache_ttl_vector=900,  # 15분
        cache_ttl_db=600,      # 10분
        cache_ttl_all=300,     # 5분
        enable_cache_stats=True,
    ),
    
    # 스테이징용 속도 제한
    rate_limit_config=RateLimitConfig(
        requests_per_minute=120,   # 프로덕션의 2배
        requests_per_hour=2000,    # 프로덕션의 2배
        burst_size=20,
    ),
    
    # 스테이징용 로깅
    logging_config=LoggingConfig(
        log_level="INFO",
        log_request_body=False,
        log_response_body=False,
        use_emoji=False,  # 스테이징에서는 이모지 비활성화
        sensitive_fields=["password", "token", "api_key", "secret", "auth"],
    ),
    
    # 스테이징용 리트리버 설정
    retriever_config=RetrieverConfig(
        tavily_api_key=None,  # 환경 변수에서 로드
        postgres_dsn="postgresql://mcp_user:${DB_PASSWORD}@postgres-staging:5432/mcp_retriever_staging",
        qdrant_host="qdrant-staging",
        qdrant_port=6333,
        qdrant_grpc_port=6334,
    ),
)