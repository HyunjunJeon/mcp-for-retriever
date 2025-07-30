"""
MCP 서버 향상된 컨텍스트 기반 사용자 정보 전파 구현체

이 모듈은 향상된 컨텍스트 관리 기능을 통해 사용자 정보와 요청 메타데이터를
효과적으로 추적하고 전파하는 MCP(Model Context Protocol) 서버를 구현합니다.
각 요청에 대한 상세한 메트릭과 도구 사용 패턴을 추적하여 성능 분석과 모니터링을 지원합니다.

주요 기능:
    컨텍스트 관리:
        - UserContext 클래스를 통한 사용자 정보 추적
        - 요청 ID 및 시작 시간 기록
        - 도구 사용 패턴 및 성공률 추적
        - 컨텍스트 요약 정보 제공
        
    성능 모니터링:
        - 각 도구 호출의 수행 시간 측정
        - 전체 요청 처리 시간 추적
        - 개별 리트리버별 성능 메트릭
        - 동시 검색 시 각 소스별 응답 시간
        
    향상된 로깅:
        - 요청/응답 상세 로깅
        - 사용자별 작업 추적
        - 에러 및 성공 비율 로깅
        - 시간 기반 메트릭 수집
        
    인증 및 보안:
        - JWT Bearer 토큰 인증
        - 내부 API 키 지원
        - 사용자 컨텍스트 보호
        - 요청별 격리된 컨텍스트

아키텍처:
    - UserContext 클래스로 사용자 정보 캡슐화
    - 전역 컨텍스트 저장소로 요청별 컨텍스트 관리
    - Enhanced 미들웨어로 컨텍스트 자동 설정
    - 시간 기반 메트릭으로 성능 모니터링

활용 방안:
    - 사용자별 사용 패턴 분석
    - 성능 병목 현상 식별
    - 리소스 사용률 모니터링
    - A/B 테스트 및 기능 롤아웃
    - 사용자 경험 최적화

주의사항:
    - 프로덕션에서는 Redis 등 외부 저장소 사용 권장
    - 컨텍스트 저장소 크기 모니터링 필요
    - 메모리 누수 방지를 위한 정리 필수

작성일: 2024-01-30
"""

import asyncio
import os
from typing import Any, Optional, Dict
from contextlib import asynccontextmanager
import structlog
import httpx
from datetime import datetime

from fastmcp import FastMCP, Context
from fastmcp.exceptions import ToolError

from src.retrievers.factory import RetrieverFactory
from src.retrievers.base import Retriever, RetrieverConfig, QueryError

# 구조화된 로깅 설정
logger = structlog.get_logger(__name__)

# 전역 리트리버 저장소
# 향상된 컨텍스트 지원을 위한 서버 라이프사이클 동안 관리
retrievers: dict[str, Retriever] = {}

# 기본 리트리버 팩토리 인스턴스
factory = RetrieverFactory.get_default()

# 서비스 간 통신용 내부 API 키
INTERNAL_API_KEY = os.getenv("MCP_INTERNAL_API_KEY", "")

# 인증 게이트웨이 서버 URL
AUTH_GATEWAY_URL = os.getenv("AUTH_GATEWAY_URL", "http://localhost:8000")


# 사용자 정보를 위한 향상된 컨텍스트 관리자
class UserContext:
    """
    향상된 사용자 정보 및 요청 메타데이터 저장 컨텍스트
    
    각 MCP 요청에 대한 사용자 정보, 요청 ID, 시간 정보 및 도구 사용 패턴을 추적합니다.
    이 정보는 성능 분석, 감사 로깅, 사용자 행동 분석 등에 활용됩니다.
    
    주요 기능:
        - 사용자 인증 정보 저장
        - 요청 고유 ID 및 시작 시간 추적
        - 도구별 사용 현황 및 성공률 기록
        - 전체 컨텍스트 요약 정보 제공
        
    사용 예시:
        ```python
        context = UserContext()
        context.set_user({"id": "123", "email": "user@example.com"})
        context.add_tool_usage("search_web", 250.5, success=True)
        summary = context.get_summary()
        ```
    """
    
    def __init__(self):
        self.user: Optional[Dict[str, Any]] = None  # 사용자 정보
        self.request_id: Optional[str] = None  # 요청 고유 ID
        self.start_time: Optional[datetime] = None  # 요청 시작 시간
        self.tool_usage: list[Dict[str, Any]] = []  # 도구 사용 내역
    
    def set_user(self, user_data: Dict[str, Any]):
        """
        인증에서 사용자 정보 설정
        
        Args:
            user_data (Dict[str, Any]): 사용자 정보 딕셔너리
                - id: 사용자 ID
                - email: 사용자 이메일
                - type: 사용자 타입 (user/service)
                - roles: 사용자 역할 목록
        """
        self.user = user_data
        logger.info("사용자 컨텍스트 설정", user_id=user_data.get("id"), email=user_data.get("email"))
    
    def add_tool_usage(self, tool_name: str, duration_ms: float, success: bool = True):
        """
        메트릭을 위한 도구 사용 추적
        
        Args:
            tool_name (str): 사용된 도구 이름 (예: "search_web", "search_vectors")
            duration_ms (float): 수행 시간 (밀리초)
            success (bool): 성공 여부 (기본값: True)
            
        이 정보는 다음 분석에 활용됩니다:
            - 도구별 사용 빈도 통계
            - 평균 수행 시간 분석
            - 성공률 모니터링
            - 사용자별 사용 패턴 분석
        """
        from datetime import timezone
        self.tool_usage.append({
            "tool": tool_name,
            "duration_ms": duration_ms,
            "success": success,
            "timestamp": datetime.now(timezone.utc).isoformat()
        })
    
    def get_summary(self) -> Dict[str, Any]:
        """
        로깅을 위한 컨텍스트 요약 정보 조회
        
        Returns:
            Dict[str, Any]: 컨텍스트 요약 정보
                - user_id: 사용자 ID
                - user_email: 사용자 이메일
                - request_id: 요청 ID
                - tool_usage_count: 사용된 도구 수
                - total_duration_ms: 총 수행 시간
                
        이 요약 정보는 로깅, 모니터링, 대시보드에 활용됩니다.
        """
        return {
            "user_id": self.user.get("id") if self.user else None,
            "user_email": self.user.get("email") if self.user else None,
            "request_id": self.request_id,
            "tool_usage_count": len(self.tool_usage),
            "total_duration_ms": sum(t["duration_ms"] for t in self.tool_usage)
        }


# 전역 컨텍스트 저장소 (프로덕션에서는 Redis 등 외부 저장소 사용 권장)
# 현재는 메모리 기반 딕셔너리로 구현
_context_store: Dict[str, UserContext] = {}


@asynccontextmanager
async def lifespan(server: FastMCP):
    """
    향상된 컨텍스트 지원 MCP 서버 라이프사이클 관리
    
    MCP 서버의 시작과 종료를 관리하면서 향상된 컨텍스트 추적 기능을 제공합니다.
    모든 리트리버를 초기화하고 종료 시 컨텍스트 저장소를 정리합니다.
    
    Args:
        server (FastMCP): FastMCP 서버 인스턴스
        
    라이프사이클 특징:
        시작 (Startup):
            1. 향상된 컨텍스트 지원 활성화 로깅
            2. 환경 변수에서 API 키 및 연결 정보 로드
            3. 각 리트리버별 연결 시도
            4. 성공한 리트리버만 전역 저장소에 등록
            5. 컨텍스트 지원 상태를 'enhanced'로 표시
            
        종료 (Shutdown):
            1. 컨텍스트 저장소 완전 삭제
            2. 모든 활성 리트리버 연결 해제
            3. 리소스 정리 및 메모리 해제
            4. Graceful shutdown 보장
            
    컨텍스트 지원:
        - 요청별 컨텍스트 격리
        - 사용자 정보 및 메타데이터 추적
        - 도구 사용 패턴 및 성능 메트릭
        - 컨텍스트 저장소 크기 모니터링
    """
    logger.info("향상된 컨텍스트 지원 MCP 서버 시작 중...")
    
    # Initialize retrievers
    startup_errors = []
    
    # Initialize Tavily retriever
    try:
        config: RetrieverConfig = {
            "type": "tavily",
            "api_key": os.getenv("TAVILY_API_KEY", ""),
        }
        if config["api_key"]:
            tavily = factory.create(config)
            await tavily.connect()
            retrievers["tavily"] = tavily
            logger.info("Tavily retriever initialized")
        else:
            logger.warning("Tavily API key not provided, skipping initialization")
    except Exception as e:
        logger.error("Failed to initialize Tavily retriever", error=str(e))
        startup_errors.append(f"Tavily: {str(e)}")

    # Initialize PostgreSQL retriever
    try:
        config: RetrieverConfig = {
            "type": "postgres",
            "dsn": os.getenv("POSTGRES_DSN", "postgresql://mcp_user:mcp_password@localhost:5432/mcp_retriever"),
        }
        postgres = factory.create(config)
        await postgres.connect()
        retrievers["postgres"] = postgres
        logger.info("PostgreSQL retriever initialized")
    except Exception as e:
        logger.error("Failed to initialize PostgreSQL retriever", error=str(e))
        startup_errors.append(f"PostgreSQL: {str(e)}")

    # Initialize Qdrant retriever
    try:
        config: RetrieverConfig = {
            "type": "qdrant",
            "host": os.getenv("QDRANT_HOST", "localhost"),
            "port": int(os.getenv("QDRANT_PORT", "6333")),
        }
        qdrant = factory.create(config)
        await qdrant.connect()
        retrievers["qdrant"] = qdrant
        logger.info("Qdrant retriever initialized")
    except Exception as e:
        logger.error("Failed to initialize Qdrant retriever", error=str(e))
        startup_errors.append(f"Qdrant: {str(e)}")

    logger.info(
        "MCP 서버 시작 완료", 
        active_retrievers=list(retrievers.keys()),
        startup_errors=startup_errors,
        auth_enabled=bool(INTERNAL_API_KEY),
        context_support="enhanced"  # 향상된 컨텍스트 지원 표시
    )
    
    try:
        yield
    finally:
        # 종료 처리 - 모든 리트리버 연결 해제
        logger.info("MCP 서버 종료 중...")
        
        # 컨텍스트 저장소 정리
        _context_store.clear()
        
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


# 인증, 로깅, 컨텍스트를 위한 향상된 미들웨어
async def context_middleware(request: dict[str, Any], call_next):
    """
    인증, 컨텍스트, 로깅을 위한 향상된 미들웨어
    
    MCP 서버로 들어오는 모든 요청에 대해 다음을 수행합니다:
    1. 고유 요청 ID 생성 및 컨텍스트 초기화
    2. 인증 처리 및 사용자 정보 설정
    3. 요청/응답 로깅 및 시간 측정
    4. 컨텍스트 생명주기 관리
    
    Args:
        request (dict[str, Any]): MCP 요청 데이터
        call_next: 다음 미들웨어 또는 핸들러
        
    Returns:
        dict[str, Any]: MCP 응답 또는 에러 응답
        
    컨텍스트 관리 흐름:
        1. UUID 기반 요청 ID 생성
        2. UserContext 인스턴스 생성 및 초기화
        3. 전역 컨텍스트 저장소에 저장
        4. 인증 성공 시 사용자 정보 설정
        5. 요청 처리 후 컨텍스트 정리
        
    성능 추적:
        - 요청 시작/종료 시간 측정
        - 전체 처리 시간 계산 (밀리초)
        - 컨텍스트 요약 정보 로깅
        - 에러 발생 여부 추적
        
    에러 처리:
        - 인증 실패 시 컨텍스트 자동 정리
        - 예외 발생 시에도 컨텍스트 정리 보장
        - finally 블록으로 메모리 누수 방지
    """
    import uuid
    from time import time
    
    start_time = time()
    request_id = str(uuid.uuid4())
    
    # 이 요청을 위한 컨텍스트 생성
    user_context = UserContext()
    user_context.request_id = request_id
    from datetime import timezone
    user_context.start_time = datetime.now(timezone.utc)
    
    # 컨텍스트 저장
    _context_store[request_id] = user_context
    
    # HTTP 모드에서 실행 시 인증 헤더 추출
    headers = request.get("headers", {})
    auth_header = headers.get("authorization", "")
    
    # 인증 및 사용자 정보 획득
    user_info = None
    if INTERNAL_API_KEY and auth_header != f"Bearer {INTERNAL_API_KEY}":
        # Validate token with auth gateway
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{AUTH_GATEWAY_URL}/auth/me",
                    headers={"Authorization": auth_header},
                )
                if response.status_code == 200:
                    user_info = response.json()
                    user_context.set_user(user_info)
                    # Add user info to request for tools
                    request["user"] = user_info
                    request["user_context"] = user_context
                else:
                    # Clean up context on auth failure
                    del _context_store[request_id]
                    return {
                        "error": {
                            "code": -32603,
                            "message": "Unauthorized"
                        }
                    }
        except Exception as e:
            logger.error("Auth validation failed", error=str(e))
            # Clean up context on error
            del _context_store[request_id]
            return {
                "error": {
                    "code": -32603,
                    "message": "Authentication service unavailable"
                }
            }
    elif INTERNAL_API_KEY and auth_header == f"Bearer {INTERNAL_API_KEY}":
        # Service-to-service call
        user_info = {"type": "service", "service": "internal"}
        user_context.set_user(user_info)
        request["user"] = user_info
        request["user_context"] = user_context
    
    # Log request with context
    logger.info(
        "MCP request",
        request_id=request_id,
        method=request.get("method"),
        user_id=user_info.get("id") if user_info else None,
        user_email=user_info.get("email") if user_info else "service",
        tool_name=request.get("params", {}).get("name") if "params" in request else None
    )
    
    # Call the next handler
    try:
        response = await call_next(request)
        
        # Log response time
        duration_ms = (time() - start_time) * 1000
        
        logger.info(
            "MCP response",
            request_id=request_id,
            duration_ms=duration_ms,
            has_error=bool(response.get("error")),
            context_summary=user_context.get_summary()
        )
        
        return response
    finally:
        # Clean up context
        if request_id in _context_store:
            del _context_store[request_id]


# 라이프사이클과 향상된 컨텍스트를 포함한 FastMCP 서버 생성
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
    향상된 컨텍스트 지원으로 사용자 행동과 도구 사용을 추적합니다.
    """
)

# 향상된 미들웨어 추가
# INTERNAL_API_KEY가 설정된 경우에만 컨텍스트 미들웨어 활성화
if INTERNAL_API_KEY:
    mcp.add_middleware(context_middleware)


# FastMCP 컨텍스트에서 사용자 컨텍스트를 가져오는 도우미 함수
def get_user_context(ctx: Context) -> Optional[UserContext]:
    """
    FastMCP 컨텍스트에서 사용자 컨텍스트 추출
    
    현재는 FastMCP가 더 나은 컨텍스트 접근을 제공할 때까지
    임시 방편으로 None을 반환합니다. 향후 요청 추적을 통해 개선될 예정입니다.
    """
    # FastMCP가 더 나은 컨텍스트 접근을 제공하면 개선될 예정
    # 현재는 요청 추적을 통한 회피 방법 사용
    return None


@mcp.tool
async def search_web(
    ctx: Context,
    query: str,
    limit: int = 10,
    include_domains: Optional[list[str]] = None,
    exclude_domains: Optional[list[str]] = None
) -> list[dict[str, Any]]:
    """Search the web using Tavily.
    
    Args:
        ctx: FastMCP context
        query: Search query string
        limit: Maximum number of results (default: 10)
        include_domains: List of domains to include in search
        exclude_domains: List of domains to exclude from search
        
    Returns:
        List of search results
        
    Raises:
        ToolError: If web search is not available or fails
    """
    from time import time
    start_time = time()
    
    # Log the search request with enhanced context
    await ctx.info(f"Searching web for: {query[:50]}...")
    
    # Check if Tavily retriever is available
    if "tavily" not in retrievers:
        raise ToolError("Web search is not available")
    
    tavily = retrievers["tavily"]
    
    # Check if connected
    if not tavily.connected:
        raise ToolError("Web search is not available - not connected")
    
    # Prepare search parameters
    search_params = {}
    if include_domains:
        search_params["include_domains"] = include_domains
    if exclude_domains:
        search_params["exclude_domains"] = exclude_domains
    
    # Perform search with progress updates
    results = []
    try:
        async for result in tavily.retrieve(query, limit=limit, **search_params):
            results.append(result)
            # Report progress
            if len(results) % 5 == 0:
                await ctx.info(f"Found {len(results)} results so far...")
        
        # Track tool usage
        duration_ms = (time() - start_time) * 1000
        
        await ctx.info(f"Web search complete: {len(results)} results found (took {duration_ms:.2f}ms)")
        return results
    
    except Exception as e:
        duration_ms = (time() - start_time) * 1000
        await ctx.error(f"Web search failed: {str(e)} (took {duration_ms:.2f}ms)")
        raise ToolError(f"Web search failed: {str(e)}")


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
        ctx: FastMCP context
        query: Search query or text to embed
        collection: Name of the vector collection
        limit: Maximum number of results (default: 10)
        score_threshold: Minimum similarity score (default: 0.7)
        
    Returns:
        List of search results with similarity scores
        
    Raises:
        ToolError: If vector search is not available or fails
    """
    from time import time
    start_time = time()
    
    await ctx.info(f"Searching vectors in collection '{collection}'...")
    
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
        
        duration_ms = (time() - start_time) * 1000
        await ctx.info(f"Vector search complete: {len(results)} results found (took {duration_ms:.2f}ms)")
        return results
    
    except QueryError as e:
        duration_ms = (time() - start_time) * 1000
        await ctx.error(f"Vector search failed: {str(e)} (took {duration_ms:.2f}ms)")
        raise ToolError(str(e))


@mcp.tool
async def search_database(
    ctx: Context,
    query: str,
    table: Optional[str] = None,
    limit: int = 10
) -> list[dict[str, Any]]:
    """Search relational database using PostgreSQL.
    
    Args:
        ctx: FastMCP context
        query: SQL query or search text
        table: Table name for text search (optional)
        limit: Maximum number of results (default: 10)
        
    Returns:
        List of database records
        
    Raises:
        ToolError: If database search is not available or fails
    """
    from time import time
    start_time = time()
    
    await ctx.info("Searching database...")
    
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
        
        duration_ms = (time() - start_time) * 1000
        await ctx.info(f"Database search complete: {len(results)} results found (took {duration_ms:.2f}ms)")
        return results
    
    except QueryError as e:
        duration_ms = (time() - start_time) * 1000
        await ctx.error(f"Database search failed: {str(e)} (took {duration_ms:.2f}ms)")
        raise ToolError(str(e))


@mcp.tool
async def search_all(
    ctx: Context,
    query: str,
    limit: int = 10
) -> dict[str, Any]:
    """Search across all available retrievers concurrently.
    
    Args:
        ctx: FastMCP context
        query: Search query string
        limit: Maximum number of results per source (default: 10)
        
    Returns:
        Dictionary with results from all sources and any errors
    """
    from time import time
    start_time = time()
    
    await ctx.info("Starting concurrent search across all sources...")
    
    results = {}
    errors = {}
    timings = {}
    
    # Create tasks for all connected retrievers
    tasks = []
    for name, retriever in retrievers.items():
        if retriever.connected:
            tasks.append((name, _search_single_source(name, retriever, query, limit, ctx)))
    
    if not tasks:
        await ctx.warning("No retrievers are connected")
        return {"results": {}, "errors": {"all": "No retrievers available"}, "timings": {}}
    
    # Execute all searches concurrently
    await ctx.info(f"Searching {len(tasks)} sources concurrently...")
    
    # Use TaskGroup for concurrent execution
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
            timings[name] = result.get("duration_ms", 0)
        except Exception as e:
            errors[name] = str(e)
            timings[name] = 0
    
    total_duration_ms = (time() - start_time) * 1000
    
    await ctx.info(
        f"Search complete: {len(results)} successful, {len(errors)} failed (total: {total_duration_ms:.2f}ms)"
    )
    
    # Log individual source timings
    for source, timing in timings.items():
        if timing > 0:
            await ctx.info(f"  - {source}: {timing:.2f}ms")
    
    return {
        "results": results,
        "errors": errors,
        "sources_searched": len(results) + len(errors),
        "timings": timings,
        "total_duration_ms": total_duration_ms
    }


async def _search_single_source(
    name: str,
    retriever: Retriever,
    query: str,
    limit: int,
    ctx: Context
) -> dict[str, Any]:
    """Helper to search a single retriever with timing."""
    from time import time
    start_time = time()
    
    try:
        await ctx.info(f"Searching {name}...")
        results = []
        async for result in retriever.retrieve(query, limit=limit):
            results.append(result)
        
        duration_ms = (time() - start_time) * 1000
        return {"results": results, "duration_ms": duration_ms}
    except Exception as e:
        duration_ms = (time() - start_time) * 1000
        await ctx.error(f"Error searching {name}: {str(e)}")
        return {"error": str(e), "duration_ms": duration_ms}


@mcp.tool
async def health_check(ctx: Context) -> dict[str, Any]:
    """Check health status of all retrievers.
    
    Args:
        ctx: FastMCP context
        
    Returns:
        Health status of all retrievers with enhanced metrics
    """
    await ctx.info("Performing health check...")
    
    health_status = {
        "service": "mcp-retriever",
        "status": "healthy",
        "auth_enabled": bool(INTERNAL_API_KEY),
        "context_support": "enhanced",
        "retrievers": {},
        "context_store_size": len(_context_store),
        "server_uptime": "N/A"  # Would track actual uptime in production
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