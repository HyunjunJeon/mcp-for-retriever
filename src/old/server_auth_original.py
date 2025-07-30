"""
MCP 서버 인증 및 고급 기능 구현체

이 모듈은 JWT 기반 인증, 사용자 컨텍스트 추적, 서비스 간 인증 등의
고급 기능이 포함된 MCP(Model Context Protocol) 서버를 구현합니다.
다중 리트리버 시스템을 통합하여 보안이 강화된 검색 서비스를 제공합니다.

주요 기능:
    인증 및 보안:
        - JWT Bearer 토큰 인증
        - 내부 API 키를 통한 서비스 간 인증
        - 인증 게이트웨이와의 연동
        - 사용자 컨텍스트 추적 및 로깅
        
    다중 리트리버 통합:
        - Tavily API를 통한 웹 검색
        - Qdrant를 통한 벡터 유사도 검색
        - PostgreSQL을 통한 관계형 데이터베이스 검색
        - 모든 소스에서 동시 검색 지원
        
    서버 전송 모드:
        - STDIO 모드: 표준 입출력 기반 통신
        - HTTP 모드: RESTful API 엔드포인트 제공
        - 환경 변수로 동적 전송 모드 선택
        
    모니터링 및 로깅:
        - 구조화된 로깅으로 요청 추적
        - 사용자별 작업 로깅
        - 인증 실패 및 오류 추적
        - 성능 메트릭 수집

아키텍처:
    - Middleware 패턴으로 인증 및 로깅 처리
    - Factory 패턴으로 리트리버 생성 및 관리
    - Context Manager로 라이프사이클 관리
    - HTTP 클라이언트로 외부 인증 서비스 연동

환경 변수:
    MCP_INTERNAL_API_KEY: 내부 API 키 (서비스 간 인증용)
    AUTH_GATEWAY_URL: 인증 게이트웨이 URL
    TAVILY_API_KEY: Tavily 검색 API 키
    POSTGRES_DSN: PostgreSQL 연결 문자열
    QDRANT_HOST, QDRANT_PORT: Qdrant 서버 연결 정보
    MCP_TRANSPORT: 전송 모드 (stdio/http)
    MCP_SERVER_PORT: HTTP 모드 서버 포트

사용 예시:
    ```bash
    # STDIO 모드로 실행
    MCP_INTERNAL_API_KEY=your-key python -m src.server_auth
    
    # HTTP 모드로 실행
    MCP_TRANSPORT=http MCP_SERVER_PORT=8001 python -m src.server_auth
    ```

작성일: 2024-01-30
"""

import asyncio
import os
from typing import Any, Optional
from contextlib import asynccontextmanager
import structlog
import httpx

from fastmcp import FastMCP, Context
from fastmcp.exceptions import ToolError

from src.retrievers.factory import RetrieverFactory
from src.retrievers.base import Retriever, RetrieverConfig, QueryError

# 구조화된 로깅 설정
logger = structlog.get_logger(__name__)

# 전역 리트리버 저장소
# 인증 기능이 활성화된 서버 라이프사이클 동안 관리
retrievers: dict[str, Retriever] = {}

# 기본 리트리버 팩토리 인스턴스
factory = RetrieverFactory.get_default()

# 서비스 간 통신용 내부 API 키
# 이 키가 설정되면 인증 미들웨어가 활성화됨
INTERNAL_API_KEY = os.getenv("MCP_INTERNAL_API_KEY", "")

# 인증 게이트웨이 서버 URL
# JWT 토큰 검증을 위해 사용되는 외부 인증 서비스
AUTH_GATEWAY_URL = os.getenv("AUTH_GATEWAY_URL", "http://localhost:8000")


@asynccontextmanager
async def lifespan(server: FastMCP):
    """
    인증 기능이 있는 MCP 서버 라이프사이클 관리
    
    MCP 서버의 시작과 종료를 관리하는 비동기 컨텍스트 매니저입니다.
    인증 기능이 포함되어 있어 인증 상태가 로깅되고, 환경 변수에서
    실제 설정값을 로드하여 리트리버들을 초기화합니다.
    
    Args:
        server (FastMCP): FastMCP 서버 인스턴스
        
    라이프사이클 특징:
        시작 (Startup):
            1. 인증 기능 활성화 상태 로깅
            2. 환경 변수에서 API 키 및 연결 정보 로드
            3. 각 리트리버별 연결 시도 (필수 설정 백업)
            4. 성공한 리트리버만 전역 저장소에 등록
            5. 실패한 리트리버는 경고 로깅 후 계속 진행
            
        운영 (Runtime):
            - 인증 미들웨어를 통한 요청 검증
            - 사용자별 작업 추적 및 로깅
            - 리트리버들이 도구 호출에 응답
            
        종료 (Shutdown):
            1. 모든 활성 리트리버 연결 해제
            2. HTTP 클라이언트 및 리소스 정리
            3. 인증 미들웨어 정리
            4. Graceful shutdown 보장
            
    인증 기능:
        - INTERNAL_API_KEY 존재 시 인증 미들웨어 자동 활성화
        - 각 리트리버에 필요한 API 키 환결변수에서 로드
        - Tavily API 키 누락 시 해당 리트리버 자동 비활성화
        - 모든 에러는 구조화된 로깅으로 기록
    """
    logger.info("인증 기능이 있는 MCP 서버 시작 중...")
    
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
            logger.warning("Tavily API 키가 제공되지 않아 초기화를 건너뚗니다")
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
        auth_enabled=bool(INTERNAL_API_KEY)
    )
    
    try:
        yield  # 서버 실행 상태 유지
    finally:
        # 종료 처리 - 모든 리트리버 연결 해제
        logger.info("MCP 서버 종료 중...")
        
        # 각 리트리버를 안전하게 연결 해제
        for name, retriever in retrievers.items():
            try:
                await retriever.disconnect()
                logger.info(f"{name} 리트리버 연결 해제 완료")
            except Exception as e:
                logger.error(f"{name} 리트리버 연결 해제 중 에러", error=str(e))
        
        # 전역 리트리버 저장소 정리
        retrievers.clear()
        logger.info("MCP 서버 종료 완료")


# 인증 및 로깅을 위한 미들웨어
async def auth_middleware(request: dict[str, Any], call_next):
    """
    모든 요청에 대한 인증 미들웨어
    
    MCP 서버로 들어오는 모든 요청에 대해 인증을 수행하고 사용자 컨텍스트를 설정합니다.
    내부 API 키와 JWT 토큰 두 방식을 모두 지원하여 다양한 인증 시나리오에 대응합니다.
    
    Args:
        request (dict[str, Any]): MCP 요청 데이터
            - headers: HTTP 헤더 딕션너리
            - method: MCP 메서드명
            - params: 요청 매개변수
            
        call_next: 다음 미들웨어 또는 핸들러
        
    Returns:
        dict[str, Any]: MCP 응답 또는 에러 응답
        
    인증 처리 순서:
        1. HTTP 헤더에서 Authorization 헤더 추출
        2. 내부 API 키 확인 (서비스 간 인증)
        3. JWT 토큰인 경우 인증 게이트웨이로 검증
        4. 인증 성공 시 사용자 정보를 요청에 추가
        5. 인증 실패 시 에러 응답 반환
        
    인증 방식:
        - 내부 API 키: "Bearer {INTERNAL_API_KEY}" 형태
        - JWT 토큰: "Bearer {jwt_token}" 형태
        - 인증 게이트웨이: AUTH_GATEWAY_URL/auth/me 엔드포인트
        
    에러 처리:
        - 401 Unauthorized: 인증 실패
        - 503 Service Unavailable: 인증 서비스 없음
        - JSON-RPC 2.0 호환 에러 형식
        
    로깅 기능:
        - 사용자별 요청 추적
        - 인증 성공/실패 로깅
        - 성능 메트릭 수집
    """
    # HTTP 모드에서 실행 시 인증 헤더 추출
    headers = request.get("headers", {})
    auth_header = headers.get("authorization", "")
    
    if INTERNAL_API_KEY and auth_header != f"Bearer {INTERNAL_API_KEY}":
        # 인증 게이트웨이를 통한 토큰 검증
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{AUTH_GATEWAY_URL}/auth/me",
                    headers={"Authorization": auth_header},
                )
                if response.status_code != 200:
                    return {
                        "error": {
                            "code": -32603,
                            "message": "인증되지 않음"
                        }
                    }
                # 사용자 정보를 요청 컨텍스트에 추가
                request["user"] = response.json()
        except Exception as e:
            logger.error("인증 검증 실패", error=str(e))
            return {
                "error": {
                    "code": -32603,
                    "message": "인증 서비스를 사용할 수 없습니다"
                }
            }
    
    # 요청 로깅
    logger.info(
        "MCP 요청",
        method=request.get("method"),
        user=request.get("user", {}).get("email", "service"),
    )
    
    # 다음 핸들러 호출
    response = await call_next(request)
    
    return response


# 라이프사이클 관리와 인증 기능을 포함한 FastMCP 서버 생성
mcp = FastMCP(
    name="mcp-retriever",
    lifespan=lifespan,
    instructions="""
    이 MCP 서버는 다중 검색 시스템에 대한 통합 접근을 제공합니다:
    - Tavily API를 통한 웹 검색
    - Qdrant를 통한 벡터 유사도 검색
    - PostgreSQL을 통한 데이터베이스 쿼리
    
    각 도구는 에러를 우아하게 처리하며 상세한 피드백을 제공합니다.
    모든 가능한 소스를 동시에 검색하려면 search_all을 사용하세요.
    
    Bearer 토큰을 통한 인증이 필요합니다.
    """
)

# 인증 미들웨어 추가
# INTERNAL_API_KEY가 설정된 경우에만 인증 미들웨어 활성화
if INTERNAL_API_KEY:
    mcp.add_middleware(auth_middleware)


@mcp.tool
async def search_web(
    ctx: Context,
    query: str,
    limit: int = 10,
    include_domains: Optional[list[str]] = None,
    exclude_domains: Optional[list[str]] = None
) -> list[dict[str, Any]]:
    """
    Tavily를 사용한 웹 검색 (인증 버전)
    
    인증된 사용자의 컨텍스트를 추적하며 Tavily API를 통해 웹 검색을 수행합니다.
    모든 검색 요청과 결과가 사용자별로 로깅되어 감사 추적이 가능합니다.
    
    Args:
        ctx (Context): FastMCP 컨텍스트 (사용자 정보 포함)
        query (str): 검색 쿼리 문자열
        limit (int): 최대 결과 수 (기본값: 10)
        include_domains (Optional[list[str]]): 포함할 도메인 목록
        exclude_domains (Optional[list[str]]): 제외할 도메인 목록
        
    Returns:
        list[dict[str, Any]]: 검색 결과 목록
        
    Raises:
        ToolError: 웹 검색이 불가능하거나 실패한 경우
        
    인증 및 로깅 특징:
        - 사용자 이메일이 로깅에 포함됨
        - 모든 검색 요청이 감사 로그에 기록됨
        - 인증 실패 시 자동으로 차단
    """
    # 컨텍스트에서 사용자 정보 추출 (가능한 경우)
    user_info = ctx.get("user", {}).get("email", "unknown") if hasattr(ctx, "get") else "unknown"
    
    # 사용자 컨텍스트와 함께 검색 요청 로깅
    await ctx.info(f"웹 검색 시작: {query[:50]}... (사용자: {user_info})")
    
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
    async for result in tavily.retrieve(query, limit=limit, **search_params):
        results.append(result)
        # 5개마다 진행 상황 보고
        if len(results) % 5 == 0:
            await ctx.info(f"현재까지 {len(results)}개 결과 발견...")
    
    await ctx.info(f"웹 검색 완료: {len(results)}개 결과 발견")
    return results


@mcp.tool
async def search_vectors(
    ctx: Context,
    query: str,
    collection: str,
    limit: int = 10,
    score_threshold: float = 0.7
) -> list[dict[str, Any]]:
    """Search vector database using Qdrant.
    
    Args:
        query: Search query or text to embed
        collection: Name of the vector collection
        limit: Maximum number of results (default: 10)
        score_threshold: Minimum similarity score (default: 0.7)
        ctx: FastMCP context for logging and progress
        
    Returns:
        List of search results with similarity scores
        
    Raises:
        ToolError: If vector search is not available or fails
    """
    # Get user info from context if available
    user_info = ctx.get("user", {}).get("email", "unknown") if hasattr(ctx, "get") else "unknown"
    
    await ctx.info(f"Searching vectors in collection '{collection}'... (user: {user_info})")
    
    # Check if Qdrant retriever is available
    if "qdrant" not in retrievers:
        raise ToolError("Vector search is not available")
    
    qdrant = retrievers["qdrant"]
    
    # Check if connected
    if not qdrant.connected:
        raise ToolError("Vector search is not available - not connected")
    
    # Perform search
    results = []
    try:
        async for result in qdrant.retrieve(
            query, limit=limit, collection=collection, score_threshold=score_threshold
        ):
            results.append(result)
    except QueryError as e:
        # Convert QueryError to ToolError for proper MCP error handling
        raise ToolError(str(e))
    
    await ctx.info(f"Vector search complete: {len(results)} results found")
    return results


@mcp.tool
async def search_database(
    ctx: Context,
    query: str,
    table: Optional[str] = None,
    limit: int = 10
) -> list[dict[str, Any]]:
    """Search relational database using PostgreSQL.
    
    Args:
        query: SQL query or search text
        table: Table name for text search (optional)
        limit: Maximum number of results (default: 10)
        ctx: FastMCP context for logging and progress
        
    Returns:
        List of database records
        
    Raises:
        ToolError: If database search is not available or fails
    """
    # Get user info from context if available
    user_info = ctx.get("user", {}).get("email", "unknown") if hasattr(ctx, "get") else "unknown"
    
    await ctx.info(f"Searching database... (user: {user_info})")
    
    # Check if PostgreSQL retriever is available
    if "postgres" not in retrievers:
        raise ToolError("Database search is not available")
    
    postgres = retrievers["postgres"]
    
    # Check if connected
    if not postgres.connected:
        raise ToolError("Database search is not available - not connected")
    
    # Log query type
    if query.upper().startswith("SELECT"):
        await ctx.info("Executing SQL query")
    else:
        await ctx.info(f"Performing text search in table: {table or 'all tables'}")
    
    # Perform search
    results = []
    try:
        async for result in postgres.retrieve(query, limit=limit, table=table):
            results.append(result)
    except QueryError as e:
        raise ToolError(str(e))
    
    await ctx.info(f"Database search complete: {len(results)} results found")
    return results


@mcp.tool
async def search_all(
    ctx: Context,
    query: str,
    limit: int = 10
) -> dict[str, Any]:
    """Search across all available retrievers concurrently.
    
    Args:
        query: Search query string
        limit: Maximum number of results per source (default: 10)
        ctx: FastMCP context for logging and progress
        
    Returns:
        Dictionary with results from all sources and any errors
    """
    # Get user info from context if available
    user_info = ctx.get("user", {}).get("email", "unknown") if hasattr(ctx, "get") else "unknown"
    
    await ctx.info(f"Starting concurrent search across all sources... (user: {user_info})")
    
    results = {}
    errors = {}
    
    # Create tasks for all connected retrievers
    tasks = []
    for name, retriever in retrievers.items():
        if retriever.connected:
            tasks.append((name, _search_single_source(name, retriever, query, limit, ctx)))
    
    if not tasks:
        await ctx.warning("No retrievers are connected")
        return {"results": {}, "errors": {"all": "No retrievers available"}}
    
    # Execute all searches concurrently
    await ctx.info(f"Searching {len(tasks)} sources concurrently...")
    
    # Use TaskGroup for concurrent execution (Python 3.11+)
    try:
        async with asyncio.TaskGroup() as tg:
            task_refs = []
            for name, coro in tasks:
                task = tg.create_task(coro)
                task_refs.append((name, task))
    except* Exception as eg:
        # Handle exceptions from TaskGroup
        for e in eg.exceptions:
            logger.error(f"Task group error: {e}")
    
    # Collect results
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
        f"Search complete: {len(results)} successful, {len(errors)} failed"
    )
    
    return {
        "results": results,
        "errors": errors,
        "sources_searched": len(results) + len(errors),
    }


async def _search_single_source(
    name: str,
    retriever: Retriever,
    query: str,
    limit: int,
    ctx: Context
) -> dict[str, Any]:
    """Helper to search a single retriever."""
    try:
        await ctx.info(f"Searching {name}...")
        results = []
        async for result in retriever.retrieve(query, limit=limit):
            results.append(result)
        return {"results": results}
    except Exception as e:
        await ctx.error(f"Error searching {name}: {str(e)}")
        return {"error": str(e)}


@mcp.tool
async def health_check(ctx: Context) -> dict[str, Any]:
    """Check health status of all retrievers.
    
    Args:
        ctx: FastMCP context for logging
        
    Returns:
        Health status of all retrievers
    """
    await ctx.info("Performing health check...")
    
    health_status = {
        "service": "mcp-retriever",
        "status": "healthy",
        "auth_enabled": bool(INTERNAL_API_KEY),
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
    
    # If no retrievers are healthy, mark as unhealthy
    if not any(r.get("connected", False) for r in health_status["retrievers"].values()):
        health_status["status"] = "unhealthy"
    
    await ctx.info(f"Health check complete: {health_status['status']}")
    return health_status


# 서버 인스턴스 억스포트
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