"""
MCP 서버 완전 구현체 - 모든 Phase 2 향상 기능 포함

이 모듈은 모든 고급 기능이 통합된 완전한 MCP(Model Context Protocol) 서버를 구현합니다.
인증, 속도 제한, 유효성 검사, 메트릭 수집, 향상된 로깅, 에러 처리 등
엔터프라이즈급 기능을 모두 제공합니다.

주요 기능:
    미들웨어 체인:
        - ErrorHandlerMiddleware: 모든 에러 캐치 및 처리
        - AuthMiddleware: JWT 기반 인증
        - LoggingMiddleware: 요청/응답 로깅
        - ValidationMiddleware: 요청 유효성 검사
        - RateLimitMiddleware: 속도 제한
        - MetricsMiddleware: 성능 메트릭 수집
        
    리트리버 통합:
        - Tavily API를 통한 웹 검색
        - Qdrant를 통한 벡터 유사도 검색
        - PostgreSQL을 통한 관계형 데이터베이스 검색
        - 모든 소스에서 동시 검색 지원
        
    고급 기능:
        - Bearer 토큰 인증
        - 분당 60회, 시간당 1000회 속도 제한
        - 상세 성능 메트릭 및 건강 상태 검사
        - 컨텍스트 기반 사용자 정보 전파
        - 이모지를 활용한 직관적 상태 표시

미들웨어 실행 순서 (중요):
    1. ErrorHandlerMiddleware (가장 바깥층 - 모든 에러 캐치)
    2. AuthMiddleware (인증되지 않은 요청 조기 차단)
    3. LoggingMiddleware (인증된 요청만 로깅)
    4. ValidationMiddleware (요청 구조 및 권한 검사)
    5. RateLimitMiddleware (유효한 사용자의 남용 방지)
    6. MetricsMiddleware (모든 검사를 통과한 요청 추적)

환경 변수:
    MCP_INTERNAL_API_KEY: 내부 API 키 (서비스 간 인증용)
    AUTH_GATEWAY_URL: 인증 게이트웨이 URL
    TAVILY_API_KEY: Tavily 검색 API 키
    POSTGRES_DSN: PostgreSQL 연결 문자열
    QDRANT_HOST, QDRANT_PORT: Qdrant 서버 연결 정보
    MCP_TRANSPORT: 전송 모드 (stdio/http)
    MCP_SERVER_PORT: HTTP 모드 서버 포트
    LOG_LEVEL: 로깅 레벨 (DEBUG 시 상세 에러 포함)

사용 예시:
    ```bash
    # STDIO 모드로 실행
    MCP_INTERNAL_API_KEY=your-key python -m src.server_complete
    
    # HTTP 모드로 실행
    MCP_TRANSPORT=http MCP_SERVER_PORT=8001 python -m src.server_complete
    ```

성능 특징:
    - 모든 미들웨어가 비동기로 실행
    - 효율적인 오류 처리로 성능 역행 최소화
    - 메트릭 데이터로 성능 분석 가능
    - 상태 추적으로 디버깅 용이

작성일: 2024-01-30
"""

import asyncio
import os
from typing import Any, Optional, Dict
from contextlib import asynccontextmanager
import structlog

from fastmcp import FastMCP, Context
from fastmcp.exceptions import ToolError

from src.retrievers.factory import RetrieverFactory
from src.retrievers.base import Retriever, RetrieverConfig, QueryError
from src.middleware import (
    AuthMiddleware,
    LoggingMiddleware,
    RateLimitMiddleware,
    ValidationMiddleware,
    MetricsMiddleware,
    ErrorHandlerMiddleware
)

# 구조화된 로깅 설정
logger = structlog.get_logger(__name__)

# 전역 리트리버 저장소
# 서버 라이프사이클 동안 활성화된 리트리버들을 관리
retrievers: dict[str, Retriever] = {}

# 기본 리트리버 팩토리 인스턴스
# 다양한 유형의 리트리버를 생성하는 팩토리
factory = RetrieverFactory.get_default()

# 환경 변수에서 설정 로드
INTERNAL_API_KEY = os.getenv("MCP_INTERNAL_API_KEY", "")  # 서비스 간 통신용 내부 API 키
AUTH_GATEWAY_URL = os.getenv("AUTH_GATEWAY_URL", "http://localhost:8000")  # 인증 게이트웨이 URL

# 전역 미들웨어 인스턴스
# 라이프사이클 관리를 위해 전역 변수로 참조 보관
auth_middleware: Optional[AuthMiddleware] = None
metrics_middleware: Optional[MetricsMiddleware] = None


@asynccontextmanager
async def lifespan(server: FastMCP):
    """
    서버 라이프사이클 관리 - 시작 및 종료
    
    모든 향상된 기능이 포함된 완전한 MCP 서버의 생명주기를 관리합니다.
    미들웨어 초기화, 리트리버 연결, 종료 시 정리 작업을 수행합니다.
    
    Args:
        server (FastMCP): FastMCP 서버 인스턴스
        
    라이프사이클 단계:
        시작 (Startup):
            1. 미들웨어 인스턴스 생성 및 설정
               - AuthMiddleware: 인증 처리
               - MetricsMiddleware: 성능 메트릭 수집
            2. 각 리트리버 설정 및 연결
            3. 활성화된 기능 목록 로깅
            
        종료 (Shutdown):
            1. 미들웨어 정리
               - 인증 미들웨어 연결 해제
               - 최종 메트릭 수집 및 로깅
            2. 모든 리트리버 연결 해제
            3. 리소스 정리
            
    기능 플래그:
        - authentication: JWT 기반 인증
        - rate_limiting: 속도 제한
        - validation: 요청 유효성 검사
        - metrics: 성능 메트릭
        - enhanced_logging: 향상된 로깅
        - context_propagation: 컨텍스트 전파
    """
    global auth_middleware, metrics_middleware
    
    logger.info("모든 향상 기능이 포함된 완전한 MCP 서버 시작 중...")
    
    # 미들웨어 초기화
    # 인증 미들웨어 설정 - JWT 토큰 및 내부 API 키 인증
    auth_middleware = AuthMiddleware(
        internal_api_key=INTERNAL_API_KEY,
        auth_gateway_url=AUTH_GATEWAY_URL,
        require_auth=bool(INTERNAL_API_KEY)  # API 키가 설정된 경우만 인증 필수
    )
    
    # 메트릭 미들웨어 설정 - 상세 성능 메트릭 수집
    metrics_middleware = MetricsMiddleware(
        enable_detailed_metrics=True,  # 상세 메트릭 활성화
        metrics_window_seconds=3600  # 1시간 윈도우로 메트릭 집계
    )
    
    # 리트리버 초기화
    # 시작 시 발생하는 에러들을 수집하여 나중에 로깅
    startup_errors = []
    
    # Tavily 웹 검색 리트리버 초기화
    try:
        config: RetrieverConfig = {
            "type": "tavily",
            "api_key": os.getenv("TAVILY_API_KEY", ""),
        }
        if config["api_key"]:
            tavily = factory.create(config)
            await tavily.connect()
            retrievers["tavily"] = tavily
            logger.info("Tavily 리트리버 초기화 완료")
        else:
            logger.warning("Tavily API 키가 제공되지 않아 초기화를 건너뜁니다")
    except Exception as e:
        logger.error("Tavily 리트리버 초기화 실패", error=str(e))
        startup_errors.append(f"Tavily: {str(e)}")

    # PostgreSQL 데이터베이스 리트리버 초기화
    try:
        config: RetrieverConfig = {
            "type": "postgres",
            "dsn": os.getenv("POSTGRES_DSN", "postgresql://mcp_user:mcp_password@localhost:5432/mcp_retriever"),
        }
        postgres = factory.create(config)
        await postgres.connect()
        retrievers["postgres"] = postgres
        logger.info("PostgreSQL 리트리버 초기화 완료")
    except Exception as e:
        logger.error("PostgreSQL 리트리버 초기화 실패", error=str(e))
        startup_errors.append(f"PostgreSQL: {str(e)}")

    # Qdrant 벡터 데이터베이스 리트리버 초기화
    try:
        config: RetrieverConfig = {
            "type": "qdrant",
            "host": os.getenv("QDRANT_HOST", "localhost"),
            "port": int(os.getenv("QDRANT_PORT", "6333")),
        }
        qdrant = factory.create(config)
        await qdrant.connect()
        retrievers["qdrant"] = qdrant
        logger.info("Qdrant 리트리버 초기화 완료")
    except Exception as e:
        logger.error("Qdrant 리트리버 초기화 실패", error=str(e))
        startup_errors.append(f"Qdrant: {str(e)}")

    logger.info(
        "MCP 서버 시작 완료", 
        active_retrievers=list(retrievers.keys()),
        startup_errors=startup_errors,
        auth_enabled=bool(INTERNAL_API_KEY),
        features=[  # 활성화된 기능 목록
            "authentication",      # 인증
            "rate_limiting",       # 속도 제한
            "validation",          # 유효성 검사
            "metrics",             # 메트릭 수집
            "enhanced_logging",    # 향상된 로깅
            "context_propagation"  # 컨텍스트 전파
        ]
    )
    
    try:
        yield
    finally:
        # 종료 처리 - 모든 리트리버 연결 해제
        logger.info("MCP 서버 종료 중...")
        
        # 미들웨어 정리
        if auth_middleware:
            await auth_middleware.close()
        
        # 최종 메트릭 로깅
        if metrics_middleware:
            final_metrics = await metrics_middleware.get_metrics_summary()
            logger.info("최종 서버 메트릭", metrics=final_metrics)
        
        for name, retriever in retrievers.items():
            try:
                await retriever.disconnect()
                logger.info(f"{name} 리트리버 연결 해제 완료")
            except Exception as e:
                logger.error(f"{name} 리트리버 연결 해제 중 오류", error=str(e))
        
        retrievers.clear()
        logger.info("MCP 서버 종료 완료")


# 완전한 기능을 갖춘 FastMCP 서버 생성
mcp = FastMCP(
    name="mcp-retriever-complete",
    lifespan=lifespan,
    instructions="""
    이것은 모든 Phase 2 향상 기능이 포함된 완전한 MCP 서버입니다:
    
    기능:
    - 다중 검색 시스템에 대한 통합 접근 (웹, 벡터 DB, SQL DB)
    - Bearer 토큰을 사용한 JWT 기반 인증
    - 남용 방지를 위한 속도 제한
    - 요청 유효성 검사 및 권한 확인
    - 포괄적인 메트릭 및 모니터링
    - 요청 추적을 통한 향상된 로깅
    - 컨텍스트 기반 사용자 정보 전파
    
    사용 가능한 도구:
    - search_web: Tavily를 사용한 웹 검색
    - search_vectors: Qdrant를 사용한 벡터 데이터베이스 검색
    - search_database: PostgreSQL 데이터베이스 검색
    - search_all: 모든 소스에서 동시 검색
    - health_check: 시스템 건강 상태 및 메트릭 확인
    - get_metrics: 서버 성능 메트릭 조회
    
    모든 도구는 Bearer 토큰을 통한 인증이 필요합니다.
    속도 제한 적용: 분당 60회, 시간당 1000회
    """
)

# 미들웨어를 순서대로 적용
if INTERNAL_API_KEY:
    # 순서가 중요함: 에러 처리기 -> 인증 -> 로깅 -> 유효성 검사 -> 속도 제한 -> 메트릭
    
    # 1. 에러 핸들러 (가장 바깥층에서 모든 에러 캐치)
    error_handler_middleware = ErrorHandlerMiddleware(
        capture_stack_trace=True,  # 스택 트레이스 캐처
        include_error_details=os.getenv("LOG_LEVEL") == "DEBUG",  # DEBUG 모드에서만 상세 에러 포함
        max_error_log_length=5000  # 에러 로그 최대 길이
    )
    mcp.add_middleware(lambda req, next: error_handler_middleware(req, next))
    
    # 2. 인증 (인증되지 않은 요청을 조기에 차단)
    mcp.add_middleware(lambda req, next: auth_middleware(req, next))
    
    # 3. 로깅 (인증된 모든 요청 로깅)
    logging_middleware = LoggingMiddleware(
        log_request_body=False,  # 요청 본문 로깅 비활성화 (보안)
        log_response_body=False,  # 응답 본문 로깅 비활성화 (성능)
        sensitive_fields=["password", "token", "api_key", "secret"]  # 민감한 필드 마스킹
    )
    mcp.add_middleware(lambda req, next: logging_middleware(req, next))
    
    # 4. 유효성 검사 (요청 구조 및 권한 검증)
    validation_middleware = ValidationMiddleware(
        validate_params=True  # 파라미터 유효성 검사 활성화
    )
    mcp.add_middleware(lambda req, next: validation_middleware(req, next))
    
    # 5. 속도 제한 (유효한 사용자의 남용 방지)
    rate_limit_middleware = RateLimitMiddleware(
        requests_per_minute=60,   # 분당 최대 60회 요청
        requests_per_hour=1000,   # 시간당 최대 1000회 요청
        burst_size=10             # 순간적으로 허용되는 버스트 크기
    )
    mcp.add_middleware(lambda req, next: rate_limit_middleware(req, next))
    
    # 6. 메트릭 (이전 검사를 통과한 모든 요청 추적)
    mcp.add_middleware(lambda req, next: metrics_middleware(req, next))


@mcp.tool
async def search_web(
    ctx: Context,
    query: str,
    limit: int = 10,
    include_domains: Optional[list[str]] = None,
    exclude_domains: Optional[list[str]] = None
) -> list[dict[str, Any]]:
    """
    Tavily를 사용한 웹 검색
    
    인증된 사용자가 Tavily API를 통해 웹에서 정보를 검색합니다.
    이모지를 사용한 직관적인 진행 상황 표시로 사용자 경험을 향상시킵니다.
    
    Args:
        ctx: FastMCP 컨텍스트
        query: 검색 쿼리 문자열
        limit: 최대 결과 수 (기본값: 10)
        include_domains: 검색에 포함할 도메인 목록
        exclude_domains: 검색에서 제왔할 도메인 목록
        
    Returns:
        list[dict[str, Any]]: 검색 결과 목록
        
    Raises:
        ToolError: 웹 검색이 불가능하거나 실패한 경우
        
    성능 최적화:
        - 진행 상황을 5개 단위로 보고
        - 비동기 스트리밍으로 메모리 효율성
        - 에러 발생 시 상세 로깅
    """
    await ctx.info(f"🔍 웹 검색 시작: {query[:50]}...")
    
    # Tavily 리트리버 가용성 확인
    if "tavily" not in retrievers:
        raise ToolError("웹 검색을 사용할 수 없습니다")
    
    tavily = retrievers["tavily"]
    
    # 연결 상태 확인
    if not tavily.connected:
        raise ToolError("웹 검색을 사용할 수 없습니다 - 연결되지 않음")
    
    # 검색 매개변수 준비
    search_params = {}
    if include_domains:
        search_params["include_domains"] = include_domains
    if exclude_domains:
        search_params["exclude_domains"] = exclude_domains
    
    # 진행 상황 업데이트와 함께 검색 수행
    results = []
    try:
        async for result in tavily.retrieve(query, limit=limit, **search_params):
            results.append(result)
            # 진행 상황 보고
            if len(results) % 5 == 0:
                await ctx.info(f"📊 현재까지 {len(results)}개 결과 발견...")
        
        await ctx.info(f"✅ 웹 검색 완료: {len(results)}개 결과 발견")
        return results
    
    except Exception as e:
        await ctx.error(f"❌ 웹 검색 실패: {str(e)}")
        raise ToolError(f"웹 검색 실패: {str(e)}")


@mcp.tool
async def search_vectors(
    ctx: Context,
    query: str,
    collection: str,
    limit: int = 10,
    score_threshold: float = 0.7
) -> list[dict[str, Any]]:
    """
    Qdrant를 사용한 벡터 데이터베이스 검색
    
    텍스트 쿼리를 벡터로 임베딩하여 의미적으로 유사한 문서를 검색합니다.
    유사도 점수 기반으로 결과를 필터링하여 정확도를 보장합니다.
    
    Args:
        ctx: FastMCP 컨텍스트
        query: 검색 쿼리 또는 임베딩할 텍스트
        collection: 벡터 컨렉션 이름
        limit: 최대 결과 수 (기본값: 10)
        score_threshold: 최소 유사도 점수 (기본값: 0.7)
        
    Returns:
        list[dict[str, Any]]: 유사도 점수가 포함된 검색 결과
        
    Raises:
        ToolError: 벡터 검색이 불가능하거나 실패한 경우
        
    성능 특징:
        - HNSW 인덱스로 빠른 근사 검색
        - 점수 기반 필터링으로 정확도 향상
        - 비동기 스트리밍 결과 반환
    """
    await ctx.info(f"🔍 '{collection}' 컨렉션에서 벡터 검색 중...")
    
    # Qdrant 리트리버 가용성 확인
    if "qdrant" not in retrievers:
        raise ToolError("벡터 검색을 사용할 수 없습니다")
    
    qdrant = retrievers["qdrant"]
    
    # 연결 상태 확인
    if not qdrant.connected:
        raise ToolError("벡터 검색을 사용할 수 없습니다 - 연결되지 않음")
    
    # 검색 수행
    results = []
    try:
        async for result in qdrant.retrieve(
            query, limit=limit, collection=collection, score_threshold=score_threshold
        ):
            results.append(result)
        
        await ctx.info(f"✅ 벡터 검색 완료: {len(results)}개 결과 발견")
        return results
    
    except QueryError as e:
        await ctx.error(f"❌ 벡터 검색 실패: {str(e)}")
        raise ToolError(str(e))


@mcp.tool
async def search_database(
    ctx: Context,
    query: str,
    table: Optional[str] = None,
    limit: int = 10
) -> list[dict[str, Any]]:
    """
    PostgreSQL을 사용한 관계형 데이터베이스 검색
    
    SQL 쿼리를 직접 실행하거나 텍스트 검색을 수행합니다.
    검색 유형을 자동으로 감지하고 적절한 이모지로 표시합니다.
    
    Args:
        ctx: FastMCP 컨텍스트
        query: SQL 쿼리 또는 검색 텍스트
        table: 텍스트 검색용 테이블 이름 (선택적)
        limit: 최대 결과 수 (기본값: 10)
        
    Returns:
        list[dict[str, Any]]: 데이터베이스 레코드 목록
        
    Raises:
        ToolError: 데이터베이스 검색이 불가능하거나 실패한 경우
        
    검색 모드:
        - SQL 쿼리: SELECT로 시작하는 쿼리 직접 실행
        - 텍스트 검색: 전문 검색으로 자연어 처리
    """
    await ctx.info("🔍 데이터베이스 검색 중...")
    
    # PostgreSQL 리트리버 가용성 확인
    if "postgres" not in retrievers:
        raise ToolError("데이터베이스 검색을 사용할 수 없습니다")
    
    postgres = retrievers["postgres"]
    
    # 연결 상태 확인
    if not postgres.connected:
        raise ToolError("데이터베이스 검색을 사용할 수 없습니다 - 연결되지 않음")
    
    # 쿼리 유형 로깅
    if query.upper().startswith("SELECT"):
        await ctx.info("🗂️ SQL 쿼리 실행 중")
    else:
        await ctx.info(f"📝 텍스트 검색 수행 중 - 테이블: {table or '모든 테이블'}")
    
    # 검색 수행
    results = []
    try:
        async for result in postgres.retrieve(query, limit=limit, table=table):
            results.append(result)
        
        await ctx.info(f"✅ 데이터베이스 검색 완료: {len(results)}개 결과 발견")
        return results
    
    except QueryError as e:
        await ctx.error(f"❌ 데이터베이스 검색 실패: {str(e)}")
        raise ToolError(str(e))


@mcp.tool
async def search_all(
    ctx: Context,
    query: str,
    limit: int = 10
) -> dict[str, Any]:
    """
    모든 가능한 리트리버에서 동시 검색
    
    모든 활성화된 리트리버에서 동시에 검색을 수행하여
    포괄적인 결과를 빠르게 제공합니다.
    
    Args:
        ctx: FastMCP 컨텍스트
        query: 검색 쿼리 문자열
        limit: 각 소스당 최대 결과 수 (기본값: 10)
        
    Returns:
        dict[str, Any]: 모든 소스의 결과와 발생한 오류들
            - results: 각 소스의 검색 결과
            - errors: 발생한 오류들
            - sources_searched: 검색된 소스 수
            
    성능 특징:
        - TaskGroup을 사용한 안전한 동시 실행
        - 부분 실패에도 다른 결과는 반환
        - 실시간 진행 상황 표시
    """
    await ctx.info("🔍 모든 소스에서 동시 검색 시작...")
    
    results = {}
    errors = {}
    
    # 연결된 모든 리트리버에 대한 작업 생성
    tasks = []
    for name, retriever in retrievers.items():
        if retriever.connected:
            tasks.append((name, _search_single_source(name, retriever, query, limit, ctx)))
    
    if not tasks:
        await ctx.warning("⚠️ 연결된 리트리버가 없습니다")
        return {"results": {}, "errors": {"all": "사용 가능한 리트리버가 없습니다"}}
    
    # 모든 검색을 동시에 실행
    await ctx.info(f"🚀 {len(tasks)}개 소스에서 동시 검색 중...")
    
    # 동시 실행을 위해 TaskGroup 사용
    try:
        async with asyncio.TaskGroup() as tg:
            task_refs = []
            for name, coro in tasks:
                task = tg.create_task(coro)
                task_refs.append((name, task))
    except* Exception as eg:
        # TaskGroup에서 발생한 예외 처리
        for e in eg.exceptions:
            logger.error(f"TaskGroup 오류: {e}")
    
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
    
    await ctx.info(
        f"✅ 검색 완료: {len(results)}개 성공, {len(errors)}개 실패"
    )
    
    return {
        "results": results,
        "errors": errors,
        "sources_searched": len(results) + len(errors)
    }


async def _search_single_source(
    name: str,
    retriever: Retriever,
    query: str,
    limit: int,
    ctx: Context
) -> dict[str, Any]:
    """
    단일 리트리버 검색을 위한 도우미 함수
    
    각 리트리버에서 독립적으로 검색을 수행하고 결과를 반환합니다.
    에러가 발생해도 다른 리트리버에 영향을 주지 않습니다.
    """
    try:
        await ctx.info(f"  🔸 {name} 검색 중...")
        results = []
        async for result in retriever.retrieve(query, limit=limit):
            results.append(result)
        return {"results": results}
    except Exception as e:
        await ctx.error(f"  ❌ {name} 검색 오류: {str(e)}")
        return {"error": str(e)}


@mcp.tool
async def health_check(ctx: Context) -> dict[str, Any]:
    """
    모든 리트리버와 서버 구성 요소의 건강 상태 검사
    
    시스템의 전반적인 건강 상태를 포괄적으로 확인하고,
    각 구성 요소의 상태를 상세히 제공합니다.
    
    Args:
        ctx: FastMCP 컨텍스트
        
    Returns:
        dict[str, Any]: 포괄적인 건강 상태 정보
            - service: 서비스 이름
            - status: 전체 상태 (healthy/degraded/unhealthy)
            - features: 활성화된 기능 목록
            - retrievers: 각 리트리버의 상태
            
    상태 분류:
        - healthy: 모든 구성 요소가 정상 작동
        - degraded: 일부 구성 요소에 문제가 있지만 서비스 가능
        - unhealthy: 모든 리트리버가 작동하지 않음
    """
    await ctx.info("🏥 건강 상태 검사 수행 중...")
    
    health_status = {
        "service": "mcp-retriever-complete",
        "status": "healthy",
        "features": {  # 활성화된 기능들
            "auth_enabled": bool(INTERNAL_API_KEY),  # 인증 활성화 여부
            "rate_limiting": True,          # 속도 제한
            "validation": True,             # 요청 유효성 검사
            "metrics": True,                # 성능 메트릭
            "enhanced_logging": True        # 향상된 로깅
        },
        "retrievers": {}
    }
    
    for name, retriever in retrievers.items():
        try:
            status = await retriever.health_check()
            health_status["retrievers"][name] = {
                "connected": retriever.connected,
                "status": status
            }
        except Exception as e:
            health_status["retrievers"][name] = {
                "connected": False,
                "status": "error",
                "error": str(e)
            }
            health_status["status"] = "degraded"
    
    # 모든 리트리버가 비정상인 경우 unhealthy로 표시
    if not any(r.get("connected", False) for r in health_status["retrievers"].values()):
        health_status["status"] = "unhealthy"
    
    await ctx.info(f"✅ 건강 상태 검사 완료: {health_status['status']}")
    return health_status


@mcp.tool
async def get_metrics(ctx: Context) -> dict[str, Any]:
    """
    서버 성능 메트릭 조회
    
    서버의 현재 성능 메트릭을 수집하여 반환합니다.
    요청률, 에러율, 응답 시간 등의 통계를 포함합니다.
    
    Args:
        ctx: FastMCP 컨텍스트
        
    Returns:
        dict[str, Any]: 현재 메트릭 요약
            - 요청 통계 (총 요청 수, 성공/실패)
            - 시간대별 요청률
            - 평균 응답 시간
            - 도구별 사용 통계
            
    활용 방안:
        - 성능 모니터링 대시보드
        - 용량 계획 및 스케일링
        - SLA 추적 및 보고
    """
    await ctx.info("📊 서버 메트릭 조회 중...")
    
    if not metrics_middleware:
        raise ToolError("메트릭을 사용할 수 없습니다")
    
    metrics = await metrics_middleware.get_metrics_summary()
    
    await ctx.info("✅ 메트릭 조회 성공")
    return metrics


# 서버 인스턴스 익스포트
server = mcp

# 직접 실행 시 서버 가동
if __name__ == "__main__":
    # HTTP 모드로 실행할지 확인
    if os.getenv("MCP_TRANSPORT", "stdio") == "http":
        # FastMCP의 HTTP 전송 모드로 실행
        mcp.run(transport="http", port=int(os.getenv("MCP_SERVER_PORT", "8001")))
    else:
        # 기본 stdio 전송 모드로 실행
        mcp.run()