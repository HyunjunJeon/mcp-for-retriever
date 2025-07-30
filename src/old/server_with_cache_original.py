"""
MCP 서버 Redis 캐싱 통합 구현체

이 모듈은 Redis 캐싱이 통합된 MCP(Model Context Protocol) 서버를 구현합니다.
모든 검색 작업에 대해 캐싱을 지원하여 성능을 향상시키고, 캐시 무효화 및
통계 조회 기능을 제공합니다.

주요 기능:
    Redis 캐싱 통합:
        - 웹 검색 결과 캐싱 (5분 TTL)
        - 벡터 검색 결과 캐싱 (15분 TTL)
        - 데이터베이스 검색 결과 캐싱 (10분 TTL)
        - 동시 검색 결과 캐싱 (5분 TTL)
        
    캐시 관리 도구:
        - invalidate_cache: 특정 패턴의 캐시 무효화
        - cache_stats: 캐시 통계 및 설정 조회
        - use_cache 파라미터로 캐시 우회 가능
        - 리트리버별 독립적 캐시 네임스페이스
        
    성능 최적화:
        - 중복 검색 요청 방지
        - 응답 시간 대폭 단축
        - 네트워크 부하 감소
        - 외부 API 호출 최소화
        
    캐싱 전략:
        - TTL 기반 자동 만료
        - 패턴 기반 선택적 무효화
        - 리트리버별 독립적 캐시 관리
        - 캐시 히트/미스 추적 가능

아키텍처:
    - CachedRetriever 기반 리트리버 래핑
    - Redis를 통한 분산 캐싱
    - 비동기 캐시 작업 처리
    - 데코레이터 기반 캐싱 적용

환경 변수:
    REDIS_URL: Redis 연결 URL (기본: redis://localhost:6379/0)
    TAVILY_API_KEY: Tavily 검색 API 키
    POSTGRES_DSN: PostgreSQL 연결 문자열
    QDRANT_HOST, QDRANT_PORT: Qdrant 서버 연결 정보

사용 예시:
    ```bash
    # Redis와 함께 실행
    docker run -d -p 6379:6379 redis:alpine
    python -m src.server_with_cache
    
    # 캐시 통계 조회
    mcp call cache_stats
    
    # 캐시 무효화
    mcp call invalidate_cache --retriever_name tavily
    ```

성능 이점:
    - 동일 검색에 대해 즉시 응답 (캐시 히트 시)
    - 외부 API 비용 절감
    - 네트워크 지연 최소화
    - 시스템 부하 분산

작성일: 2024-01-30
"""

import asyncio
from typing import Any, Optional
from contextlib import asynccontextmanager
import structlog

from fastmcp import FastMCP, Context
from fastmcp.exceptions import ToolError

from src.retrievers.factory import RetrieverFactory
from src.retrievers.base import RetrieverConfig, QueryError
from src.retrievers.cached_base import CachedRetriever
from src.cache import cached

# 구조화된 로깅 설정
logger = structlog.get_logger(__name__)

# 전역 캐시 리트리버 저장소
# CachedRetriever로 래핑된 리트리버들을 관리
retrievers: dict[str, CachedRetriever] = {}

# 기본 리트리버 팩토리 인스턴스
# 캐싱이 적용된 리트리버 생성을 위해 사용
factory = RetrieverFactory.get_default()


@asynccontextmanager
async def lifespan(server: FastMCP):
    """
    캐싱 지원이 포함된 서버 라이프사이클 관리
    
    Redis 캐싱이 통합된 MCP 서버의 시작과 종료를 관리합니다.
    각 리트리버에 대해 독립적인 캐시 설정을 적용하고,
    서비스별로 최적화된 TTL을 설정합니다.
    
    Args:
        server (FastMCP): FastMCP 서버 인스턴스
        
    캐싱 설정:
        Tavily (웹 검색):
            - TTL: 5분 (자주 변경되는 웹 콘텐츠)
            - 네임스페이스: "tavily"
            
        PostgreSQL (데이터베이스):
            - TTL: 10분 (상대적으로 안정적인 데이터)
            - 네임스페이스: "postgres"
            
        Qdrant (벡터 검색):
            - TTL: 15분 (임베딩 기반 검색은 변경 빈도 낮음)
            - 네임스페이스: "qdrant"
            
    라이프사이클:
        시작:
            1. Redis 연결 정보 설정
            2. 각 리트리버에 캐싱 설정 적용
            3. 리트리버 연결 및 초기화
            4. 캐시 상태 로깅
            
        종료:
            1. 캐시 연결 정리
            2. 리트리버 연결 해제
            3. 메모리 정리
    """
    logger.info("캐싱이 적용된 MCP 서버 시작 중...")
    
    # 캐싱이 적용된 리트리버 초기화
    # 시작 시 발생하는 에러들을 수집하여 나중에 로깅
    startup_errors = []
    
    # Tavily 웹 검색 리트리버 초기화 (캐싱 적용)
    try:
        config: RetrieverConfig = {
            "type": "tavily",
            "api_key": "placeholder",  # 실제 환경에서는 환경 변수로 대체
            "use_cache": True,  # 캐싱 활성화
            "cache_ttl": 300,  # 5분 캐시 유지 (웹 콘텐츠는 자주 변경됨)
            "redis_url": "redis://localhost:6379/0"  # Redis 연결 URL
        }
        tavily = factory.create(config)
        await tavily.connect()
        retrievers["tavily"] = tavily
        logger.info("Tavily 리트리버 초기화 완료 (캐싱 활성화)")
    except Exception as e:
        logger.error("Tavily 리트리버 초기화 실패", error=str(e))
        startup_errors.append(f"Tavily: {str(e)}")

    # PostgreSQL 데이터베이스 리트리버 초기화 (캐싱 적용)
    try:
        config: RetrieverConfig = {
            "type": "postgres",
            "dsn": "placeholder",  # 실제 환경에서는 환경 변수로 대체
            "use_cache": True,  # 캐싱 활성화
            "cache_ttl": 600,  # 10분 캐시 유지 (DB 데이터는 상대적으로 안정적)
            "redis_url": "redis://localhost:6379/0"  # Redis 연결 URL
        }
        postgres = factory.create(config)
        await postgres.connect()
        retrievers["postgres"] = postgres
        logger.info("PostgreSQL 리트리버 초기화 완료 (캐싱 활성화)")
    except Exception as e:
        logger.error("PostgreSQL 리트리버 초기화 실패", error=str(e))
        startup_errors.append(f"PostgreSQL: {str(e)}")

    # Qdrant 벡터 데이터베이스 리트리버 초기화 (캐싱 적용)
    try:
        config: RetrieverConfig = {
            "type": "qdrant",
            "host": "localhost",
            "port": 6333,
            "use_cache": True,  # 캐싱 활성화
            "cache_ttl": 900,  # 15분 캐시 유지 (벡터 임베딩은 변경 빈도 낮음)
            "redis_url": "redis://localhost:6379/0"  # Redis 연결 URL
        }
        qdrant = factory.create(config)
        await qdrant.connect()
        retrievers["qdrant"] = qdrant
        logger.info("Qdrant 리트리버 초기화 완료 (캐싱 활성화)")
    except Exception as e:
        logger.error("Qdrant 리트리버 초기화 실패", error=str(e))
        startup_errors.append(f"Qdrant: {str(e)}")

    logger.info(
        "캐싱이 적용된 MCP 서버 시작 완료", 
        active_retrievers=list(retrievers.keys()),
        startup_errors=startup_errors
    )
    
    try:
        yield
    finally:
        # 종료 처리
        logger.info("MCP 서버 종료 중...")
        
        for name, retriever in retrievers.items():
            try:
                await retriever.disconnect()
                logger.info(f"{name} 리트리버 연결 해제 완료")
            except Exception as e:
                logger.error(f"{name} 리트리버 연결 해제 중 오류", error=str(e))
        
        retrievers.clear()
        logger.info("MCP 서버 종료 완료")


# 캐싱 기능이 포함된 FastMCP 서버 생성
mcp = FastMCP(
    name="mcp-retriever-cached",
    lifespan=lifespan,
    instructions="""
    이 MCP 서버는 Redis 캐싱이 통합된 다중 검색 시스템을 제공합니다:
    - Tavily API를 통한 웹 검색 (5분 캐시)
    - Qdrant를 통한 벡터 유사도 검색 (15분 캐시)
    - PostgreSQL을 통한 데이터베이스 쿼리 (10분 캐시)
    
    invalidate_cache 도구를 사용하여 캐시를 무효화할 수 있습니다.
    search_all을 사용하면 모든 소스에서 자동 캐싱과 함께 동시 검색이 가능합니다.
    """
)


@mcp.tool
async def search_web(
    query: str,
    ctx: Context,
    limit: int = 10,
    include_domains: Optional[list[str]] = None,
    exclude_domains: Optional[list[str]] = None,
    use_cache: bool = True
) -> list[dict[str, Any]]:
    """
    Tavily를 사용한 웹 검색 (캐싱 지원)
    
    Redis 캐싱을 통해 동일한 검색 요청에 대해 빠른 응답을 제공합니다.
    캐시 히트 시 외부 API 호출 없이 즉시 결과를 반환하여 성능을 대폭 향상시킵니다.
    
    Args:
        query: 검색 쿼리 문자열
        limit: 최대 결과 수 (기본값: 10)
        include_domains: 검색에 포함할 도메인 목록
        exclude_domains: 검색에서 제외할 도메인 목록
        use_cache: 캐시된 결과 사용 여부 (기본값: True)
            - True: 캐시에서 결과 확인 후 없으면 API 호출
            - False: 무조건 API 호출하여 최신 데이터 획득
        ctx: FastMCP 컨텍스트
        
    Returns:
        list[dict[str, Any]]: 검색 결과 목록
        
    Raises:
        ToolError: 웹 검색이 불가능하거나 실패한 경우
        
    캐싱 전략:
        - TTL: 5분 (웹 콘텐츠는 단시간에 변경될 수 있음)
        - 키 구성: query + limit + domains 조합
        - 캐시 무효화: invalidate_cache 도구 사용
    """
    await ctx.info(f"웹 검색 시작: {query[:50]}... (캐시 사용: {use_cache})")
    
    if "tavily" not in retrievers:
        raise ToolError("웹 검색을 사용할 수 없습니다")
    
    tavily = retrievers["tavily"]
    if not tavily.connected:
        raise ToolError("웹 검색을 사용할 수 없습니다 - 연결되지 않음")
    
    # 요청에 따라 일시적으로 캐시 비활성화
    # use_cache=False로 설정 시 이 검색에 대해서만 캐시를 우회
    original_use_cache = tavily._use_cache
    if not use_cache:
        tavily._use_cache = False
    
    try:
        search_params = {}
        if include_domains:
            search_params["include_domains"] = include_domains
        if exclude_domains:
            search_params["exclude_domains"] = exclude_domains
        
        results = []
        async for result in tavily.retrieve(query, limit=limit, **search_params):
            results.append(result)
        
        await ctx.info(f"웹 검색 완료: {len(results)}개 결과")
        return results
    finally:
        tavily._use_cache = original_use_cache


@mcp.tool
async def search_vectors(
    query: str,
    collection: str,
    ctx: Context,
    limit: int = 10,
    score_threshold: float = 0.7,
    use_cache: bool = True
) -> list[dict[str, Any]]:
    """
    벡터 데이터베이스 검색 (캐싱 지원)
    
    벡터 임베딩 기반 검색 결과를 Redis에 캐싱하여 중복 계산을 방지합니다.
    임베딩 생성은 비용이 많이 드므로 캐싱의 효과가 큭니다.
    
    Args:
        query: 검색 쿼리 또는 임베딩할 텍스트
        collection: 벡터 컨렉션 이름
        limit: 최대 결과 수 (기본값: 10)
        score_threshold: 최소 유사도 점수 (기본값: 0.7)
        use_cache: 캐시된 결과 사용 여부 (기본값: True)
            - True: 동일 쿼리에 대해 캐시 사용
            - False: 임베딩 재생성 및 새로운 검색
        ctx: FastMCP 컨텍스트
        
    Returns:
        list[dict[str, Any]]: 유사도 점수가 포함된 검색 결과
        
    Raises:
        ToolError: 벡터 검색이 불가능하거나 실패한 경우
        
    캐싱 전략:
        - TTL: 15분 (임베딩은 변경 빈도가 낮음)
        - 키 구성: query + collection + score_threshold
        - 임베딩 비용 절감으로 성능 대폭 향상
    """
    await ctx.info(f"'{collection}' 컨렉션에서 벡터 검색 중 (캐시 사용: {use_cache})")
    
    if "qdrant" not in retrievers:
        raise ToolError("벡터 검색을 사용할 수 없습니다")
    
    qdrant = retrievers["qdrant"]
    if not qdrant.connected:
        raise ToolError("벡터 검색을 사용할 수 없습니다 - 연결되지 않음")
    
    # 요청에 따라 일시적으로 캐시 비활성화
    # 임베딩 재생성이 필요한 경우 use_cache=False 사용
    original_use_cache = qdrant._use_cache
    if not use_cache:
        qdrant._use_cache = False
    
    try:
        results = []
        async for result in qdrant.retrieve(
            query, limit=limit, collection=collection, score_threshold=score_threshold
        ):
            results.append(result)
        
        await ctx.info(f"벡터 검색 완료: {len(results)}개 결과")
        return results
    except QueryError as e:
        raise ToolError(str(e))
    finally:
        qdrant._use_cache = original_use_cache


@mcp.tool
async def search_database(
    query: str,
    ctx: Context,
    table: Optional[str] = None,
    limit: int = 10,
    use_cache: bool = True
) -> list[dict[str, Any]]:
    """
    데이터베이스 검색 (캐싱 지원)
    
    데이터베이스 쿼리 결과를 캐싱하여 동일한 쿼리에 대해 DB 부하를 줄입니다.
    복잡한 조인이나 집계 연산에 특히 효과적입니다.
    
    Args:
        query: SQL 쿼리 또는 검색 텍스트
        table: 텍스트 검색용 테이블 이름 (선택적)
        limit: 최대 결과 수 (기본값: 10)
        use_cache: 캐시된 결과 사용 여부 (기본값: True)
            - True: 캐시에서 결과 확인
            - False: DB에서 새로 조회
        ctx: FastMCP 컨텍스트
        
    Returns:
        list[dict[str, Any]]: 데이터베이스 레코드 목록
        
    Raises:
        ToolError: 데이터베이스 검색이 불가능하거나 실패한 경우
        
    캐싱 전략:
        - TTL: 10분 (구조화된 데이터는 상대적으로 안정적)
        - 키 구성: query + table + limit
        - 복잡한 쿼리에 대한 DB 부하 감소
    """
    await ctx.info(f"데이터베이스 검색 중 (캐시 사용: {use_cache})")
    
    if "postgres" not in retrievers:
        raise ToolError("데이터베이스 검색을 사용할 수 없습니다")
    
    postgres = retrievers["postgres"]
    if not postgres.connected:
        raise ToolError("데이터베이스 검색을 사용할 수 없습니다 - 연결되지 않음")
    
    # 요청에 따라 일시적으로 캐시 비활성화
    # 실시간 데이터가 필요한 경우 use_cache=False 사용
    original_use_cache = postgres._use_cache
    if not use_cache:
        postgres._use_cache = False
    
    try:
        results = []
        async for result in postgres.retrieve(query, limit=limit, table=table):
            results.append(result)
        
        await ctx.info(f"데이터베이스 검색 완료: {len(results)}개 결과")
        return results
    except QueryError as e:
        raise ToolError(str(e))
    finally:
        postgres._use_cache = original_use_cache


@mcp.tool
async def invalidate_cache(
    ctx: Context,
    retriever_name: Optional[str] = None,
    pattern: Optional[str] = None
) -> dict[str, int]:
    """
    캐시된 결과 무효화
    
    특정 리트리버 또는 모든 리트리버의 캐시를 선택적으로 무효화합니다.
    패턴 매칭을 통해 특정 키만 제거할 수도 있습니다.
    
    Args:
        retriever_name: 캐시를 지울 리트리버 이름 (tavily/qdrant/postgres)
                       None인 경우 모든 리트리버의 캐시 지움
        pattern: 특정 캐시 키를 매칭하는 패턴 (선택적)
                예: "*machine learning*" 패턴으로 관련 캐시만 제거
        ctx: FastMCP 컨텍스트
        
    Returns:
        dict[str, int]: 리트리버별 무효화된 키 수
        예: {"tavily": 15, "qdrant": 8, "postgres": 23}
        
    사용 예시:
        ```python
        # 특정 리트리버 캐시 지우기
        await invalidate_cache(retriever_name="tavily")
        
        # 모든 리트리버 캐시 지우기
        await invalidate_cache()
        
        # 특정 패턴의 캐시만 지우기
        await invalidate_cache(pattern="*Python*")
        ```
    """
    await ctx.info(f"캐시 무효화 대상: {retriever_name or '모든 리트리버'}")
    
    results = {}
    
    if retriever_name:
        # 특정 리트리버의 캐시만 지우기
        if retriever_name not in retrievers:
            raise ToolError(f"알 수 없는 리트리버: {retriever_name}")
        
        retriever = retrievers[retriever_name]
        if hasattr(retriever, 'invalidate_cache'):
            count = await retriever.invalidate_cache(pattern)
            results[retriever_name] = count
            await ctx.info(f"{retriever_name}에서 {count}개의 캐시 항목 삭제")
    else:
        # 모든 리트리버의 캐시 지우기
        for name, retriever in retrievers.items():
            if hasattr(retriever, 'invalidate_cache'):
                count = await retriever.invalidate_cache(pattern)
                results[name] = count
                await ctx.info(f"{name}에서 {count}개의 캐시 항목 삭제")
    
    return results


@mcp.tool
@cached(namespace="search_all", ttl=300)  # 동시 검색 결과도 5분간 캐싱
async def search_all(
    query: str,
    ctx: Context,
    limit: int = 10
) -> dict[str, Any]:
    """
    모든 소스에서 동시 검색 (캐싱 지원)
    
    이 도구의 결과는 5분간 캐싱되어 중복된 동시 검색을 방지합니다.
    모든 리트리버에서 동시에 검색하므로 각 리트리버의 개별 캐시도 함께 활용됩니다.
    
    Args:
        query: 검색 쿼리 문자열
        limit: 각 소스당 최대 결과 수
        ctx: FastMCP 컨텍스트
        
    Returns:
        dict[str, Any]: 모든 소스의 통합 결과
            - results: 각 소스의 검색 결과
            - errors: 발생한 오류들
            - sources_searched: 검색된 소스 수
            
    캐싱 효과:
        - 동일 쿼리에 대한 중복 검색 방지
        - 각 리트리버의 개별 캐시도 활용
        - 전체 결과도 동시에 캐싱
        - 네트워크 요청 최소화
    """
    await ctx.info("캐싱이 적용된 동시 검색 시작...")
    
    results = {}
    errors = {}
    
    # 연결된 모든 리트리버에 대한 작업 생성
    tasks = []
    for name, retriever in retrievers.items():
        if retriever.connected:
            tasks.append((name, _search_single_source(name, retriever, query, limit, ctx)))
    
    if not tasks:
        return {"results": {}, "errors": {"all": "사용 가능한 리트리버가 없습니다"}}
    
    # 동시 실행
    async with asyncio.TaskGroup() as tg:
        task_refs = []
        for name, coro in tasks:
            task = tg.create_task(coro)
            task_refs.append((name, task))
    
    # 결과 수집
    for name, task in task_refs:
        try:
            result = task.result()
            if "error" in result:
                errors[name] = result["error"]
            else:
                results[name] = result["results"]
        except Exception as e:
            errors[name] = str(e)
    
    await ctx.info(f"검색 완료: {len(results)}개 성공, {len(errors)}개 실패")
    
    return {
        "results": results,
        "errors": errors,
        "sources_searched": len(results) + len(errors),
    }


async def _search_single_source(
    name: str,
    retriever: CachedRetriever,
    query: str,
    limit: int,
    ctx: Context
) -> dict[str, Any]:
    """
    단일 리트리버 검색을 위한 도우미 함수
    
    각 리트리버에서 독립적으로 검색을 수행하고 결과를 반환합니다.
    캐싱은 각 리트리버 내부에서 처리됩니다.
    """
    try:
        results = []
        async for result in retriever.retrieve(query, limit=limit):
            results.append(result)
        return {"results": results}
    except Exception as e:
        await ctx.error(f"{name} 검색 오류: {str(e)}")
        return {"error": str(e)}


@mcp.tool
async def cache_stats(ctx: Context) -> dict[str, Any]:
    """
    모든 리트리버의 캐시 통계 조회
    
    각 리트리버의 캐시 설정과 상태 정보를 제공합니다.
    캐시 히트율, TTL 설정, 네임스페이스 정보 등을 포함합니다.
    
    Returns:
        dict[str, Any]: 캐시 히트/미스 통계 및 설정 정보
            각 리트리버별로:
            - cache_enabled: 캐시 활성화 여부
            - cache_ttl: 캐시 유효 시간 (초)
            - cache_namespace: 캐시 네임스페이스
            
    사용 예시:
        ```python
        stats = await cache_stats()
        # 결과:
        # {
        #   "tavily": {
        #     "cache_enabled": true,
        #     "cache_ttl": 300,
        #     "cache_namespace": "tavily:search"
        #   },
        #   ...
        # }
        ```
    """
    await ctx.info("캐시 통계 수집 중...")
    
    stats = {}
    for name, retriever in retrievers.items():
        if hasattr(retriever, '_cache') and retriever._use_cache:
            stats[name] = {
                "cache_enabled": True,
                "cache_ttl": retriever._cache.config.default_ttl,
                "cache_namespace": retriever._get_cache_namespace()
            }
        else:
            stats[name] = {"cache_enabled": False}
    
    return stats


# 서버 인스턴스 익스포트
server = mcp

# 직접 실행 시 서버 가동
if __name__ == "__main__":
    mcp.run()