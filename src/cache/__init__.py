"""
MCP 서버용 캐싱 시스템 모듈

이 모듈은 MCP(Model Context Protocol) 서버의 성능 최적화를 위한
분산 캐싱 시스템을 제공합니다. Redis를 백엔드로 사용하여
검색 결과와 계산 결과를 효율적으로 캐싱합니다.

주요 컴포넌트:
    RedisCache: Redis 기반 분산 캐시 구현체
        - 비동기 Redis 클라이언트 사용
        - 네임스페이스 기반 캐시 격리
        - TTL 기반 자동 만료 관리
        - JSON 직렬화/역직렬화
        - 패턴 매칭 기반 캐시 무효화

    CacheConfig: 캐시 설정 모델
        - Redis 연결 설정
        - TTL 정책 관리
        - 키 접두사 설정
        - 압축 옵션 (향후 지원)

성능 이점:
    - 검색 API 호출 감소로 응답 시간 단축
    - 네트워크 트래픽 최소화
    - 데이터베이스 부하 경감
    - 동시 사용자 처리 능력 향상

사용 예시:
    ```python
    from src.cache import RedisCache, CacheConfig

    # 캐시 설정 및 초기화
    config = CacheConfig(
        redis_url="redis://localhost:6379/0",
        default_ttl=300,  # 5분 기본 TTL
        key_prefix="mcp_cache"
    )

    cache = RedisCache(config)
    await cache.connect()

    # 데이터 저장 및 조회
    await cache.set("search", "python_tutorial", results, ttl=600)
    cached_results = await cache.get("search", "python_tutorial")
    ```

아키텍처:
    - Repository 패턴: 데이터 접근 계층 추상화
    - Factory 패턴: 캐시 인스턴스 생성
    - Decorator 패턴: 자동 캐싱 기능
    - Observer 패턴: 캐시 이벤트 처리
"""

# Redis 기반 캐시 시스템의 핵심 컴포넌트들
from .redis_cache import RedisCache, CacheConfig

# 외부에서 사용 가능한 공개 API 정의
__all__ = ["RedisCache", "CacheConfig"]
