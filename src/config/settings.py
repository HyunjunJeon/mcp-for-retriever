"""
서버 설정 클래스

통합 MCP 서버의 모든 설정을 관리하는 클래스입니다.
프로파일 기반 설정과 환경 변수 오버라이드를 지원합니다.

주요 기능:
    - 사전 정의된 프로파일 (BASIC, AUTH, CONTEXT, CACHED, COMPLETE)
    - 환경 변수를 통한 세밀한 제어
    - 기능 플래그 시스템
    - 컴포넌트별 설정 관리
"""

import os
from dataclasses import dataclass, field
from typing import Optional, Dict, Any
from enum import Enum
import structlog

logger = structlog.get_logger(__name__)


class ServerProfile(Enum):
    """
    서버 프로파일 열거형

    각 프로파일은 특정 사용 사례에 최적화된 기능 조합을 제공합니다.
    """

    BASIC = "basic"  # 기본 서버 (인증 없음, 캐싱 없음)
    AUTH = "auth"  # 인증 활성화 서버
    CONTEXT = "context"  # 컨텍스트 추적 서버
    CACHED = "cached"  # 캐싱 활성화 서버
    COMPLETE = "complete"  # 모든 기능 활성화 서버
    CUSTOM = "custom"  # 사용자 정의 설정


@dataclass
class AuthConfig:
    """
    인증 설정

    JWT 기반 인증과 내부 API 키 인증을 위한 설정입니다.
    """

    internal_api_key: Optional[str] = None
    auth_gateway_url: str = "http://localhost:8000"
    jwt_secret_key: Optional[str] = None
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 30
    jwt_refresh_token_expire_days: int = 7
    require_auth: bool = True

    @classmethod
    def from_env(cls) -> "AuthConfig":
        """환경 변수에서 인증 설정 로드"""
        return cls(
            internal_api_key=os.getenv("MCP_INTERNAL_API_KEY"),
            auth_gateway_url=os.getenv("AUTH_GATEWAY_URL", "http://localhost:8000"),
            jwt_secret_key=os.getenv("JWT_SECRET_KEY"),
            jwt_algorithm=os.getenv("JWT_ALGORITHM", "HS256"),
            jwt_access_token_expire_minutes=int(
                os.getenv("JWT_ACCESS_TOKEN_EXPIRE_MINUTES", "30")
            ),
            jwt_refresh_token_expire_days=int(
                os.getenv("JWT_REFRESH_TOKEN_EXPIRE_DAYS", "7")
            ),
            require_auth=os.getenv("MCP_REQUIRE_AUTH", "true").lower() == "true",
        )


@dataclass
class CacheConfig:
    """
    캐싱 설정

    Redis 기반 캐싱을 위한 설정입니다.
    리트리버별로 독립적인 TTL을 설정할 수 있습니다.
    """

    redis_url: str = "redis://localhost:6379/0"
    cache_ttl_web: int = 300  # 5분 (웹 검색)
    cache_ttl_vector: int = 900  # 15분 (벡터 검색)
    cache_ttl_db: int = 600  # 10분 (DB 검색)
    cache_ttl_all: int = 300  # 5분 (통합 검색)
    enable_cache_stats: bool = True

    @classmethod
    def from_env(cls) -> "CacheConfig":
        """환경 변수에서 캐시 설정 로드"""
        return cls(
            redis_url=os.getenv("REDIS_URL", "redis://localhost:6379/0"),
            cache_ttl_web=int(os.getenv("CACHE_TTL_WEB", "300")),
            cache_ttl_vector=int(os.getenv("CACHE_TTL_VECTOR", "900")),
            cache_ttl_db=int(os.getenv("CACHE_TTL_DB", "600")),
            cache_ttl_all=int(os.getenv("CACHE_TTL_ALL", "300")),
            enable_cache_stats=os.getenv("ENABLE_CACHE_STATS", "true").lower()
            == "true",
        )


@dataclass
class RateLimitConfig:
    """
    속도 제한 설정

    API 남용 방지를 위한 속도 제한 설정입니다.
    """

    requests_per_minute: int = 60
    requests_per_hour: int = 1000
    burst_size: int = 10

    @classmethod
    def from_env(cls) -> "RateLimitConfig":
        """환경 변수에서 속도 제한 설정 로드"""
        return cls(
            requests_per_minute=int(os.getenv("RATE_LIMIT_PER_MINUTE", "60")),
            requests_per_hour=int(os.getenv("RATE_LIMIT_PER_HOUR", "1000")),
            burst_size=int(os.getenv("RATE_LIMIT_BURST", "10")),
        )


@dataclass
class LoggingConfig:
    """
    로깅 설정

    구조화된 로깅과 디버깅을 위한 설정입니다.
    """

    log_level: str = "INFO"
    log_request_body: bool = False
    log_response_body: bool = False
    use_emoji: bool = True
    sensitive_fields: list[str] = field(
        default_factory=lambda: ["password", "token", "api_key", "secret", "auth"]
    )

    @classmethod
    def from_env(cls) -> "LoggingConfig":
        """환경 변수에서 로깅 설정 로드"""
        return cls(
            log_level=os.getenv("LOG_LEVEL", "INFO"),
            log_request_body=os.getenv("LOG_REQUEST_BODY", "false").lower() == "true",
            log_response_body=os.getenv("LOG_RESPONSE_BODY", "false").lower() == "true",
            use_emoji=os.getenv("USE_EMOJI", "true").lower() == "true",
            sensitive_fields=os.getenv(
                "SENSITIVE_FIELDS", "password,token,api_key,secret,auth"
            ).split(","),
        )


@dataclass
class RetrieverConfig:
    """
    리트리버 설정

    각 리트리버(Tavily, Qdrant, PostgreSQL)의 연결 정보입니다.
    """

    tavily_api_key: Optional[str] = None
    postgres_dsn: str = (
        "postgresql://mcp_user:mcp_password@localhost:5432/mcp_retriever"
    )
    qdrant_host: str = "localhost"
    qdrant_port: int = 6333
    qdrant_grpc_port: int = 6334

    @classmethod
    def from_env(cls) -> "RetrieverConfig":
        """환경 변수에서 리트리버 설정 로드"""
        return cls(
            tavily_api_key=os.getenv("TAVILY_API_KEY"),
            postgres_dsn=os.getenv(
                "POSTGRES_DSN",
                "postgresql://mcp_user:mcp_password@localhost:5432/mcp_retriever",
            ),
            qdrant_host=os.getenv("QDRANT_HOST", "localhost"),
            qdrant_port=int(os.getenv("QDRANT_PORT", "6333")),
            qdrant_grpc_port=int(os.getenv("QDRANT_GRPC_PORT", "6334")),
        )


@dataclass
class ServerConfig:
    """
    통합 서버 설정

    MCP 서버의 모든 설정을 관리하는 메인 클래스입니다.
    프로파일 기반 설정과 환경 변수 오버라이드를 지원합니다.

    사용 예시:
        # 프로파일 기반 생성
        config = ServerConfig.from_profile(ServerProfile.COMPLETE)

        # 환경 변수 기반 생성
        config = ServerConfig.from_env()

        # 특정 기능 활성화/비활성화
        config.features["cache"] = True
        config.cache_config = CacheConfig.from_env()
    """

    # 기본 설정
    name: str = "mcp-retriever"
    profile: ServerProfile = ServerProfile.BASIC
    transport: str = "stdio"  # stdio or http
    port: int = 8001

    # 기능 플래그
    features: Dict[str, bool] = field(
        default_factory=lambda: {
            "auth": False,  # 인증 기능
            "context": False,  # 컨텍스트 추적
            "cache": False,  # Redis 캐싱
            "rate_limit": False,  # 속도 제한
            "metrics": False,  # 성능 메트릭
            "validation": False,  # 요청 검증
            "error_handler": True,  # 에러 처리 (기본 활성화)
            "enhanced_logging": False,  # 향상된 로깅
        }
    )

    # 컴포넌트별 설정
    auth_config: Optional[AuthConfig] = None
    cache_config: Optional[CacheConfig] = None
    rate_limit_config: Optional[RateLimitConfig] = None
    logging_config: Optional[LoggingConfig] = None
    retriever_config: Optional[RetrieverConfig] = None

    @classmethod
    def from_profile(cls, profile: ServerProfile) -> "ServerConfig":
        """
        프로파일 기반 설정 생성

        각 프로파일은 특정 사용 사례에 맞는 기능 조합을 제공합니다.

        Args:
            profile: 서버 프로파일

        Returns:
            설정된 ServerConfig 인스턴스
        """
        config = cls(profile=profile)

        # 프로파일별 기능 설정
        if profile == ServerProfile.BASIC:
            # 기본 서버: 최소 기능만 활성화
            config.features.update(
                {
                    "auth": False,
                    "context": False,
                    "cache": False,
                    "rate_limit": False,
                    "metrics": False,
                    "validation": False,
                    "enhanced_logging": False,
                }
            )

        elif profile == ServerProfile.AUTH:
            # 인증 서버: 인증과 기본 미들웨어
            config.features.update(
                {
                    "auth": True,
                    "context": False,
                    "cache": False,
                    "rate_limit": False,
                    "metrics": False,
                    "validation": True,
                    "enhanced_logging": True,
                }
            )
            config.auth_config = AuthConfig.from_env()
            config.logging_config = LoggingConfig.from_env()

        elif profile == ServerProfile.CONTEXT:
            # 컨텍스트 서버: 인증 + 컨텍스트 추적
            config.features.update(
                {
                    "auth": True,
                    "context": True,
                    "cache": False,
                    "rate_limit": False,
                    "metrics": True,
                    "validation": True,
                    "enhanced_logging": True,
                }
            )
            config.auth_config = AuthConfig.from_env()
            config.logging_config = LoggingConfig.from_env()

        elif profile == ServerProfile.CACHED:
            # 캐싱 서버: 인증 + 캐싱
            config.features.update(
                {
                    "auth": True,
                    "context": False,
                    "cache": True,
                    "rate_limit": False,
                    "metrics": False,
                    "validation": True,
                    "enhanced_logging": True,
                }
            )
            config.auth_config = AuthConfig.from_env()
            config.cache_config = CacheConfig.from_env()
            config.logging_config = LoggingConfig.from_env()

        elif profile == ServerProfile.COMPLETE:
            # 완전 통합 서버: 모든 기능 활성화
            config.features.update(
                {
                    "auth": True,
                    "context": True,
                    "cache": True,
                    "rate_limit": True,
                    "metrics": True,
                    "validation": True,
                    "enhanced_logging": True,
                }
            )
            config.auth_config = AuthConfig.from_env()
            config.cache_config = CacheConfig.from_env()
            config.rate_limit_config = RateLimitConfig.from_env()
            config.logging_config = LoggingConfig.from_env()

        # 리트리버 설정은 모든 프로파일에서 공통
        config.retriever_config = RetrieverConfig.from_env()

        logger.info(
            "프로파일 기반 설정 생성",
            profile=profile.value,
            features=[k for k, v in config.features.items() if v],
        )

        return config

    @classmethod
    def from_env(cls) -> "ServerConfig":
        """
        환경 변수에서 설정 로드

        MCP_PROFILE 환경 변수로 기본 프로파일을 선택하고,
        개별 MCP_ENABLE_* 환경 변수로 기능을 오버라이드할 수 있습니다.

        Returns:
            환경 변수 기반 ServerConfig 인스턴스
        """
        # 프로파일 결정
        profile_name = os.getenv("MCP_PROFILE", "BASIC").upper()
        try:
            profile = ServerProfile[profile_name]
            config = cls.from_profile(profile)
        except KeyError:
            logger.warning(
                f"알 수 없는 프로파일: {profile_name}, CUSTOM 사용",
                profile=profile_name,
            )
            config = cls(profile=ServerProfile.CUSTOM)

        # 기본 설정 오버라이드
        config.name = os.getenv("MCP_SERVER_NAME", config.name)
        config.transport = os.getenv("MCP_TRANSPORT", config.transport)
        config.port = int(os.getenv("MCP_SERVER_PORT", str(config.port)))

        # 개별 기능 오버라이드
        for feature in config.features:
            env_key = f"MCP_ENABLE_{feature.upper()}"
            if env_value := os.getenv(env_key):
                config.features[feature] = env_value.lower() == "true"
                logger.debug(
                    f"기능 오버라이드: {feature}={config.features[feature]}",
                    env_key=env_key,
                    env_value=env_value,
                )

        # 활성화된 기능에 대한 설정 로드
        if config.features["auth"] and not config.auth_config:
            config.auth_config = AuthConfig.from_env()

        if config.features["cache"] and not config.cache_config:
            config.cache_config = CacheConfig.from_env()

        if config.features["rate_limit"] and not config.rate_limit_config:
            config.rate_limit_config = RateLimitConfig.from_env()

        if config.features["enhanced_logging"] and not config.logging_config:
            config.logging_config = LoggingConfig.from_env()

        # 리트리버 설정은 항상 로드
        if not config.retriever_config:
            config.retriever_config = RetrieverConfig.from_env()

        logger.info(
            "환경 변수 기반 설정 로드 완료",
            profile=config.profile.value,
            transport=config.transport,
            features=[k for k, v in config.features.items() if v],
        )

        return config

    def get_enabled_features(self) -> list[str]:
        """활성화된 기능 목록 반환"""
        return [feature for feature, enabled in self.features.items() if enabled]

    def validate(self) -> tuple[bool, list[str]]:
        """
        설정 유효성 검증

        Returns:
            (유효 여부, 오류 메시지 목록)
        """
        errors = []

        # 인증이 활성화되었지만 API 키가 없는 경우
        if self.features["auth"] and self.auth_config:
            if not self.auth_config.internal_api_key and self.auth_config.require_auth:
                errors.append(
                    "인증이 활성화되었지만 MCP_INTERNAL_API_KEY가 설정되지 않음"
                )

        # 캐싱이 활성화되었지만 Redis URL이 없는 경우
        if self.features["cache"] and self.cache_config:
            if not self.cache_config.redis_url:
                errors.append("캐싱이 활성화되었지만 REDIS_URL이 설정되지 않음")

        # 리트리버 설정 검증
        if self.retriever_config:
            if not self.retriever_config.tavily_api_key:
                logger.warning("Tavily API 키가 설정되지 않음 - 웹 검색 비활성화")

        # 포트 범위 검증
        if self.transport == "http":
            if not (1 <= self.port <= 65535):
                errors.append(f"잘못된 포트 번호: {self.port}")

        return len(errors) == 0, errors

    def to_dict(self) -> dict[str, Any]:
        """설정을 딕셔너리로 변환"""
        return {
            "name": self.name,
            "profile": self.profile.value,
            "transport": self.transport,
            "port": self.port,
            "features": self.features,
            "auth_config": self.auth_config.__dict__ if self.auth_config else None,
            "cache_config": self.cache_config.__dict__ if self.cache_config else None,
            "rate_limit_config": self.rate_limit_config.__dict__
            if self.rate_limit_config
            else None,
            "logging_config": self.logging_config.__dict__
            if self.logging_config
            else None,
            "retriever_config": self.retriever_config.__dict__
            if self.retriever_config
            else None,
        }
