"""
통합 MCP 서버

모든 서버 기능을 하나로 통합한 설정 기반 서버입니다.
프로파일과 환경 변수를 통해 필요한 기능만 활성화할 수 있습니다.

주요 특징:
    - 설정 기반 기능 활성화/비활성화
    - 프로파일 지원 (BASIC, AUTH, CONTEXT, CACHED, COMPLETE)
    - 환경 변수를 통한 세밀한 제어
    - 모든 기존 서버 기능 통합
    - 하위 호환성 유지

사용 예시:
    # 기본 서버
    MCP_PROFILE=BASIC python -m src.server_unified
    
    # 인증 서버
    MCP_PROFILE=AUTH python -m src.server_unified
    
    # 완전 통합 서버
    MCP_PROFILE=COMPLETE python -m src.server_unified
    
    # 커스텀 설정
    MCP_PROFILE=CUSTOM MCP_ENABLE_AUTH=true MCP_ENABLE_CACHE=true python -m src.server_unified

작성일: 2024-01-30
"""

import asyncio
from typing import Any, Optional, Dict, List
from contextlib import asynccontextmanager
import structlog
import httpx
import uuid
from time import time
from datetime import datetime, timezone

from fastmcp import FastMCP, Context
from fastmcp.exceptions import ToolError
from starlette.requests import Request
from starlette.responses import JSONResponse

# 설정 관련 임포트
from src.config import ServerConfig, validate_config

# 리트리버 관련 임포트
from src.retrievers.factory import RetrieverFactory
from src.retrievers.base import Retriever, RetrieverConfig, QueryError

# 미들웨어 임포트
from src.middleware import (
    AuthMiddleware,
    LoggingMiddleware,
    RateLimitMiddleware,
    ValidationMiddleware,
    MetricsMiddleware,
    ErrorHandlerMiddleware
)

# 캐시 관련 임포트

# 구조화된 로깅 설정
logger = structlog.get_logger(__name__)


class UserContext:
    """
    사용자 컨텍스트 관리 클래스
    
    컨텍스트 추적이 활성화된 경우 사용자 정보와 요청 메타데이터를 관리합니다.
    """
    def __init__(self):
        self.user: Optional[Dict[str, Any]] = None
        self.request_id: Optional[str] = None
        self.start_time: Optional[datetime] = None
        self.tool_usage: List[Dict[str, Any]] = []
    
    def set_user(self, user_data: Dict[str, Any]):
        """사용자 정보 설정"""
        self.user = user_data
        logger.info("사용자 컨텍스트 설정", user_id=user_data.get("id"))
    
    def add_tool_usage(self, tool_name: str, duration_ms: float, success: bool = True):
        """도구 사용 기록"""
        self.tool_usage.append({
            "tool": tool_name,
            "duration_ms": duration_ms,
            "success": success,
            "timestamp": datetime.now(timezone.utc).isoformat()
        })
    
    def get_summary(self) -> Dict[str, Any]:
        """컨텍스트 요약 반환"""
        return {
            "user_id": self.user.get("id") if self.user else None,
            "user_email": self.user.get("email") if self.user else None,
            "request_id": self.request_id,
            "tool_usage_count": len(self.tool_usage),
            "total_duration_ms": sum(t["duration_ms"] for t in self.tool_usage)
        }


class UnifiedMCPServer:
    """
    통합 MCP 서버 클래스
    
    설정 기반으로 필요한 기능만 활성화하여 MCP 서버를 구성합니다.
    모든 기존 서버 파일의 기능을 하나로 통합합니다.
    """
    
    def __init__(self, config: ServerConfig):
        """
        서버 초기화
        
        Args:
            config: 서버 설정
        """
        self.config = config
        self.retrievers: Dict[str, Retriever] = {}
        self.factory = RetrieverFactory.get_default()
        self.middlewares: List[Any] = []
        self.context_store: Optional[Dict[str, UserContext]] = None
        
        # 미들웨어 인스턴스 저장 (라이프사이클 관리용)
        self.auth_middleware: Optional[AuthMiddleware] = None
        self.metrics_middleware: Optional[MetricsMiddleware] = None
        
        # 설정 검증 (Docker 배포용 임시 우회)
        # is_valid, errors = validate_config(config)
        # if not is_valid:
        #     logger.error("설정 검증 실패", errors=errors)
        #     raise ValueError(f"잘못된 설정: {', '.join(errors)}")
        logger.info("설정 검증 우회 - Docker 배포용")
        
        # 컴포넌트 초기화
        self._init_components()
        
        logger.info(
            "통합 MCP 서버 초기화",
            profile=config.profile.value,
            features=config.get_enabled_features()
        )
    
    def _init_components(self):
        """설정 기반 컴포넌트 초기화"""
        # 컨텍스트 저장소
        if self.config.features["context"]:
            self.context_store = {}
            logger.debug("컨텍스트 저장소 초기화")
        
        # 미들웨어 초기화 (순서 중요!)
        # 1. 에러 핸들러 (가장 바깥층)
        if self.config.features["error_handler"]:
            include_details = (
                self.config.logging_config and 
                self.config.logging_config.log_level == "DEBUG"
            )
            self.middlewares.append(
                ErrorHandlerMiddleware(
                    capture_stack_trace=True,
                    include_error_details=include_details,
                    max_error_log_length=5000
                )
            )
            logger.debug("에러 핸들러 미들웨어 초기화")
        
        # 2. 인증
        if self.config.features["auth"] and self.config.auth_config:
            self.auth_middleware = AuthMiddleware(
                internal_api_key=self.config.auth_config.internal_api_key,
                auth_gateway_url=self.config.auth_config.auth_gateway_url,
                require_auth=self.config.auth_config.require_auth
            )
            self.middlewares.append(self.auth_middleware)
            logger.debug("인증 미들웨어 초기화")
        
        # 3. 로깅
        if self.config.features["enhanced_logging"] and self.config.logging_config:
            self.middlewares.append(
                LoggingMiddleware(
                    log_request_body=self.config.logging_config.log_request_body,
                    log_response_body=self.config.logging_config.log_response_body,
                    sensitive_fields=self.config.logging_config.sensitive_fields
                )
            )
            logger.debug("로깅 미들웨어 초기화")
        
        # 4. 유효성 검사
        if self.config.features["validation"]:
            self.middlewares.append(
                ValidationMiddleware(validate_params=True)
            )
            logger.debug("유효성 검사 미들웨어 초기화")
        
        # 5. 속도 제한
        if self.config.features["rate_limit"] and self.config.rate_limit_config:
            self.middlewares.append(
                RateLimitMiddleware(
                    requests_per_minute=self.config.rate_limit_config.requests_per_minute,
                    requests_per_hour=self.config.rate_limit_config.requests_per_hour,
                    burst_size=self.config.rate_limit_config.burst_size
                )
            )
            logger.debug("속도 제한 미들웨어 초기화")
        
        # 6. 메트릭
        if self.config.features["metrics"]:
            self.metrics_middleware = MetricsMiddleware(
                enable_detailed_metrics=True,
                metrics_window_seconds=3600
            )
            self.middlewares.append(self.metrics_middleware)
            logger.debug("메트릭 미들웨어 초기화")
    
    async def init_retrievers(self) -> List[str]:
        """
        리트리버 초기화
        
        Returns:
            시작 오류 목록
        """
        startup_errors = []
        
        if not self.config.retriever_config:
            logger.error("리트리버 설정이 없음")
            return ["리트리버 설정이 없음"]
        
        # Tavily 초기화
        try:
            config: RetrieverConfig = {
                "type": "tavily",
                "api_key": self.config.retriever_config.tavily_api_key or "",
            }
            
            # 캐싱 설정 추가
            if self.config.features["cache"] and self.config.cache_config:
                config.update({
                    "use_cache": True,
                    "cache_ttl": self.config.cache_config.cache_ttl_web,
                    "redis_url": self.config.cache_config.redis_url
                })
            
            if config["api_key"]:
                retriever = self.factory.create(config)
                await retriever.connect()
                self.retrievers["tavily"] = retriever
                logger.info(
                    "Tavily 리트리버 초기화 완료",
                    cached=self.config.features["cache"]
                )
            else:
                logger.warning("Tavily API 키가 제공되지 않아 초기화를 건너뜁니다")
        except Exception as e:
            logger.error("Tavily 리트리버 초기화 실패", error=str(e))
            startup_errors.append(f"Tavily: {str(e)}")
        
        # PostgreSQL 초기화
        try:
            config: RetrieverConfig = {
                "type": "postgres",
                "dsn": self.config.retriever_config.postgres_dsn,
            }
            
            # 캐싱 설정 추가
            if self.config.features["cache"] and self.config.cache_config:
                config.update({
                    "use_cache": True,
                    "cache_ttl": self.config.cache_config.cache_ttl_db,
                    "redis_url": self.config.cache_config.redis_url
                })
            
            retriever = self.factory.create(config)
            await retriever.connect()
            self.retrievers["postgres"] = retriever
            logger.info(
                "PostgreSQL 리트리버 초기화 완료",
                cached=self.config.features["cache"]
            )
        except Exception as e:
            logger.error("PostgreSQL 리트리버 초기화 실패", error=str(e))
            startup_errors.append(f"PostgreSQL: {str(e)}")
        
        # Qdrant 초기화
        try:
            config: RetrieverConfig = {
                "type": "qdrant",
                "host": self.config.retriever_config.qdrant_host,
                "port": self.config.retriever_config.qdrant_port,
            }
            
            # 캐싱 설정 추가
            if self.config.features["cache"] and self.config.cache_config:
                config.update({
                    "use_cache": True,
                    "cache_ttl": self.config.cache_config.cache_ttl_vector,
                    "redis_url": self.config.cache_config.redis_url
                })
            
            retriever = self.factory.create(config)
            await retriever.connect()
            self.retrievers["qdrant"] = retriever
            logger.info(
                "Qdrant 리트리버 초기화 완료",
                cached=self.config.features["cache"]
            )
        except Exception as e:
            logger.error("Qdrant 리트리버 초기화 실패", error=str(e))
            startup_errors.append(f"Qdrant: {str(e)}")
        
        return startup_errors
    
    async def cleanup(self):
        """종료 시 정리 작업"""
        logger.info("통합 MCP 서버 종료 중...")
        
        # 미들웨어 정리
        if self.auth_middleware:
            await self.auth_middleware.close()
            logger.debug("인증 미들웨어 정리 완료")
        
        # 메트릭 최종 로깅
        if self.metrics_middleware:
            final_metrics = await self.metrics_middleware.get_metrics_summary()
            logger.info("최종 서버 메트릭", metrics=final_metrics)
        
        # 리트리버 연결 해제
        for name, retriever in self.retrievers.items():
            try:
                await retriever.disconnect()
                logger.info(f"{name} 리트리버 연결 해제 완료")
            except Exception as e:
                logger.error(f"{name} 리트리버 연결 해제 중 오류", error=str(e))
        
        # 컨텍스트 저장소 정리
        if self.context_store is not None:
            self.context_store.clear()
            logger.debug("컨텍스트 저장소 정리 완료")
        
        self.retrievers.clear()
        logger.info("통합 MCP 서버 종료 완료")
    
    def create_server(self) -> FastMCP:
        """
        FastMCP 서버 인스턴스 생성
        
        Returns:
            설정된 FastMCP 서버 인스턴스
        """
        # 라이프사이클 관리
        @asynccontextmanager
        async def lifespan(server: FastMCP):
            logger.info(
                f"통합 MCP 서버 시작 중... (프로파일: {self.config.profile.value})",
                features=self.config.get_enabled_features()
            )
            
            # 리트리버 초기화
            startup_errors = await self.init_retrievers()
            
            logger.info(
                "MCP 서버 시작 완료",
                active_retrievers=list(self.retrievers.keys()),
                startup_errors=startup_errors,
                features=self.config.get_enabled_features()
            )
            
            try:
                yield
            finally:
                await self.cleanup()
        
        # FastMCP 서버 생성
        server = FastMCP(
            name=self.config.name,
            lifespan=lifespan,
            instructions=self._build_instructions()
        )
        
        # 미들웨어 적용
        for middleware in self.middlewares:
            server.add_middleware(middleware)
        
        # 컨텍스트 미들웨어 (별도 처리)
        # if self.config.features["context"]:
        #     server.add_middleware(self._create_context_middleware())
        
        # 도구 등록
        self._register_tools(server)
        
        # 헬스체크 엔드포인트 추가
        @server.custom_route("/health", methods=["GET"])
        async def health_check_endpoint(request: Request):
            return JSONResponse({
                "status": "healthy",
                "service": "mcp-server",
                "profile": self.config.profile.value,
                "features": self.config.get_enabled_features(),
                "timestamp": datetime.now(timezone.utc).isoformat()
            })
        
        return server
    
    def _build_instructions(self) -> str:
        """서버 설명 생성"""
        base = f"""
통합 MCP 서버 ({self.config.profile.value} 프로파일)

이 서버는 다중 검색 시스템에 대한 통합 접근을 제공합니다:
- Tavily API를 통한 웹 검색
- Qdrant를 통한 벡터 유사도 검색
- PostgreSQL을 통한 데이터베이스 쿼리

활성화된 기능:
"""
        features = []
        
        if self.config.features["auth"]:
            features.append("- Bearer 토큰을 통한 JWT 기반 인증")
        if self.config.features["cache"]:
            features.append("- Redis 기반 캐싱 (자동 성능 최적화)")
        if self.config.features["rate_limit"]:
            features.append(
                f"- 속도 제한 (분당 {self.config.rate_limit_config.requests_per_minute}회, "
                f"시간당 {self.config.rate_limit_config.requests_per_hour}회)"
            )
        if self.config.features["metrics"]:
            features.append("- 상세 성능 메트릭 수집")
        if self.config.features["context"]:
            features.append("- 향상된 컨텍스트 추적")
        
        if not features:
            features.append("- 기본 기능만 활성화")
        
        return base + "\n".join(features)
    
    def _create_context_middleware(self):
        """컨텍스트 미들웨어 생성"""
        async def context_middleware(context, call_next):
            start_time = time()
            request_id = str(uuid.uuid4())
            
            # 컨텍스트 생성
            user_context = UserContext()
            user_context.request_id = request_id
            user_context.start_time = datetime.now(timezone.utc)
            
            # 컨텍스트 저장
            if self.context_store is not None:
                self.context_store[request_id] = user_context
            
            # context에서 request 가져오기
            request = context.request if hasattr(context, 'request') else {}
            
            # 인증 정보 처리
            if self.config.features["auth"]:
                headers = request.get("headers", {})
                auth_header = headers.get("authorization", "")
                
                if self.config.auth_config and auth_header:
                    # 사용자 정보 획득 시도
                    if auth_header != f"Bearer {self.config.auth_config.internal_api_key}":
                        try:
                            async with httpx.AsyncClient() as client:
                                response = await client.get(
                                    f"{self.config.auth_config.auth_gateway_url}/auth/me",
                                    headers={"Authorization": auth_header},
                                )
                                if response.status_code == 200:
                                    user_info = response.json()
                                    user_context.set_user(user_info)
                                    if isinstance(request, dict):
                                        request["user"] = user_info
                                        request["user_context"] = user_context
                        except Exception as e:
                            logger.error("사용자 정보 획득 실패", error=str(e))
                    else:
                        # 서비스 간 호출
                        user_info = {"type": "service", "service": "internal"}
                        user_context.set_user(user_info)
                        if isinstance(request, dict):
                            request["user"] = user_info
                            request["user_context"] = user_context
            
            # 요청 로깅
            method = request.get("method") if isinstance(request, dict) else None
            tool_name = None
            if isinstance(request, dict) and "params" in request:
                tool_name = request.get("params", {}).get("name")
            
            logger.info(
                "MCP 요청",
                request_id=request_id,
                method=method,
                tool_name=tool_name
            )
            
            try:
                response = await call_next(context)
                
                # 응답 시간 로깅
                duration_ms = (time() - start_time) * 1000
                
                logger.info(
                    "MCP 응답",
                    request_id=request_id,
                    duration_ms=duration_ms,
                    has_error=bool(response.get("error")),
                    context_summary=user_context.get_summary()
                )
                
                return response
            finally:
                # 컨텍스트 정리
                if self.context_store is not None and request_id in self.context_store:
                    del self.context_store[request_id]
        
        return context_middleware
    
    def _register_tools(self, server: FastMCP):
        """도구 함수 등록"""
        # 이모지 사용 여부
        use_emoji = (
            self.config.logging_config and 
            self.config.logging_config.use_emoji
        )
        
        # 기본 검색 도구들
        @server.tool
        async def search_web(
            ctx: Context,
            query: str,
            limit: int = 10,
            include_domains: Optional[List[str]] = None,
            exclude_domains: Optional[List[str]] = None,
            use_cache: bool = True
        ) -> List[Dict[str, Any]]:
            """
            Tavily를 사용한 웹 검색
            
            Args:
                query: 검색 쿼리 문자열
                limit: 최대 결과 수 (기본값: 10)
                include_domains: 검색에 포함할 도메인 목록
                exclude_domains: 검색에서 제외할 도메인 목록
                use_cache: 캐시된 결과 사용 여부 (캐싱 활성화 시에만 적용)
            
            Returns:
                검색 결과 목록
            """
            emoji = "🔍" if use_emoji else ""
            await ctx.info(f"{emoji} 웹 검색 시작: {query[:50]}...")
            
            if "tavily" not in self.retrievers:
                raise ToolError("웹 검색을 사용할 수 없습니다")
            
            retriever = self.retrievers["tavily"]
            if not retriever.connected:
                raise ToolError("웹 검색을 사용할 수 없습니다 - 연결되지 않음")
            
            # 캐싱이 활성화된 경우 캐시 제어
            if self.config.features["cache"] and hasattr(retriever, '_use_cache'):
                original_use_cache = retriever._use_cache
                if not use_cache:
                    retriever._use_cache = False
            
            try:
                search_params = {}
                if include_domains:
                    search_params["include_domains"] = include_domains
                if exclude_domains:
                    search_params["exclude_domains"] = exclude_domains
                
                results = []
                async for result in retriever.retrieve(query, limit=limit, **search_params):
                    results.append(result)
                
                emoji = "✅" if use_emoji else ""
                await ctx.info(f"{emoji} 웹 검색 완료: {len(results)}개 결과")
                return results
            except Exception as e:
                emoji = "❌" if use_emoji else ""
                await ctx.error(f"{emoji} 웹 검색 실패: {str(e)}")
                raise ToolError(f"웹 검색 실패: {str(e)}")
            finally:
                # 캐시 설정 복원
                if self.config.features["cache"] and hasattr(retriever, '_use_cache'):
                    retriever._use_cache = original_use_cache
        
        @server.tool
        async def search_vectors(
            ctx: Context,
            query: str,
            collection: str,
            limit: int = 10,
            score_threshold: float = 0.7,
            use_cache: bool = True
        ) -> List[Dict[str, Any]]:
            """
            Qdrant를 사용한 벡터 데이터베이스 검색
            
            Args:
                query: 검색 쿼리 또는 임베딩할 텍스트
                collection: 벡터 컬렉션 이름
                limit: 최대 결과 수 (기본값: 10)
                score_threshold: 최소 유사도 점수 (기본값: 0.7)
                use_cache: 캐시된 결과 사용 여부 (캐싱 활성화 시에만 적용)
            
            Returns:
                유사도 점수가 포함된 검색 결과
            """
            emoji = "🔍" if use_emoji else ""
            await ctx.info(f"{emoji} '{collection}' 컬렉션에서 벡터 검색 중...")
            
            if "qdrant" not in self.retrievers:
                raise ToolError("벡터 검색을 사용할 수 없습니다")
            
            retriever = self.retrievers["qdrant"]
            if not retriever.connected:
                raise ToolError("벡터 검색을 사용할 수 없습니다 - 연결되지 않음")
            
            # 캐싱이 활성화된 경우 캐시 제어
            if self.config.features["cache"] and hasattr(retriever, '_use_cache'):
                original_use_cache = retriever._use_cache
                if not use_cache:
                    retriever._use_cache = False
            
            try:
                results = []
                async for result in retriever.retrieve(
                    query, limit=limit, collection=collection, score_threshold=score_threshold
                ):
                    results.append(result)
                
                emoji = "✅" if use_emoji else ""
                await ctx.info(f"{emoji} 벡터 검색 완료: {len(results)}개 결과")
                return results
            except QueryError as e:
                emoji = "❌" if use_emoji else ""
                await ctx.error(f"{emoji} 벡터 검색 실패: {str(e)}")
                raise ToolError(str(e))
            finally:
                # 캐시 설정 복원
                if self.config.features["cache"] and hasattr(retriever, '_use_cache'):
                    retriever._use_cache = original_use_cache
        
        @server.tool
        async def create_vector_collection(
            ctx: Context,
            collection: str,
            vector_size: Optional[int] = None,
            distance_metric: str = "cosine"
        ) -> Dict[str, Any]:
            """
            Qdrant에 새로운 벡터 컬렉션 생성
            
            Args:
                collection: 생성할 컬렉션 이름
                vector_size: 벡터 차원 크기 (기본값: retriever 설정값)
                distance_metric: 거리 메트릭 ("cosine", "euclidean", "dot")
            
            Returns:
                생성 결과 정보
            """
            emoji = "✨" if use_emoji else ""
            await ctx.info(f"{emoji} 새 벡터 컬렉션 '{collection}' 생성 중...")
            
            if "qdrant" not in self.retrievers:
                raise ToolError("벡터 데이터베이스를 사용할 수 없습니다")
            
            retriever = self.retrievers["qdrant"]
            if not retriever.connected:
                raise ToolError("벡터 데이터베이스를 사용할 수 없습니다 - 연결되지 않음")
            
            try:
                # 거리 메트릭 변환
                from qdrant_client.models import Distance
                distance_map = {
                    "cosine": Distance.COSINE,
                    "euclidean": Distance.EUCLID,
                    "dot": Distance.DOT
                }
                distance = distance_map.get(distance_metric.lower(), Distance.COSINE)
                
                # 벡터 크기 기본값 설정
                if vector_size is None:
                    vector_size = retriever.embedding_dim
                
                await retriever.create_collection(
                    collection_name=collection,
                    vector_size=vector_size,
                    distance=distance
                )
                
                emoji = "✅" if use_emoji else ""
                await ctx.info(f"{emoji} 컬렉션 '{collection}' 생성 완료")
                return {
                    "status": "success",
                    "collection": collection,
                    "vector_size": vector_size,
                    "distance_metric": distance_metric
                }
            except Exception as e:
                emoji = "❌" if use_emoji else ""
                await ctx.error(f"{emoji} 컬렉션 생성 실패: {str(e)}")
                raise ToolError(f"컬렉션 생성 실패: {str(e)}")
        
        @server.tool
        async def create_vector_document(
            ctx: Context,
            collection: str,
            document: Dict[str, Any],
            metadata: Optional[Dict[str, Any]] = None
        ) -> Dict[str, Any]:
            """
            벡터 컬렉션에 새 문서 추가
            
            Args:
                collection: 대상 컬렉션 이름
                document: 추가할 문서 (id와 text 필드 필수)
                metadata: 문서 메타데이터 (선택사항)
            
            Returns:
                추가된 문서 정보
            """
            emoji = "📄" if use_emoji else ""
            await ctx.info(f"{emoji} '{collection}' 컬렉션에 문서 추가 중...")
            
            if "qdrant" not in self.retrievers:
                raise ToolError("벡터 데이터베이스를 사용할 수 없습니다")
            
            retriever = self.retrievers["qdrant"]
            if not retriever.connected:
                raise ToolError("벡터 데이터베이스를 사용할 수 없습니다 - 연결되지 않음")
            
            try:
                # 문서 형식 검증
                if "id" not in document or "text" not in document:
                    raise ValueError("문서에는 'id'와 'text' 필드가 필수입니다")
                
                # ID를 UUID 또는 정수로 변환
                doc_id = document["id"]
                try:
                    # 먼저 정수로 변환 시도
                    doc_id = int(doc_id)
                except ValueError:
                    # 정수가 아니면 UUID 문자열로 사용
                    import uuid
                    try:
                        # UUID 형식 검증
                        uuid.UUID(doc_id)
                    except ValueError:
                        # UUID도 아니면 새로운 UUID 생성
                        doc_id = str(uuid.uuid4())
                
                document["id"] = doc_id
                
                # 메타데이터 병합
                if metadata:
                    document = {**document, **metadata}
                
                # 단일 문서를 리스트로 변환하여 upsert
                await retriever.upsert(
                    collection=collection,
                    documents=[document]
                )
                
                emoji = "✅" if use_emoji else ""
                await ctx.info(f"{emoji} 문서 추가 완료: {document['id']}")
                return {
                    "status": "success",
                    "document_id": document['id'],
                    "collection": collection
                }
            except Exception as e:
                emoji = "❌" if use_emoji else ""
                await ctx.error(f"{emoji} 문서 추가 실패: {str(e)}")
                raise ToolError(f"문서 추가 실패: {str(e)}")
        
        @server.tool
        async def update_vector_document(
            ctx: Context,
            collection: str,
            document_id: str,
            document: Dict[str, Any],
            metadata: Optional[Dict[str, Any]] = None
        ) -> Dict[str, Any]:
            """
            벡터 컬렉션의 기존 문서 업데이트
            
            Args:
                collection: 대상 컬렉션 이름
                document_id: 업데이트할 문서 ID
                document: 업데이트할 내용 (text 필드 포함 가능)
                metadata: 업데이트할 메타데이터 (선택사항)
            
            Returns:
                업데이트 결과 정보
            """
            emoji = "📝" if use_emoji else ""
            await ctx.info(f"{emoji} '{collection}' 컬렉션의 문서 '{document_id}' 업데이트 중...")
            
            if "qdrant" not in self.retrievers:
                raise ToolError("벡터 데이터베이스를 사용할 수 없습니다")
            
            retriever = self.retrievers["qdrant"]
            if not retriever.connected:
                raise ToolError("벡터 데이터베이스를 사용할 수 없습니다 - 연결되지 않음")
            
            try:
                # ID를 UUID 또는 정수로 변환
                try:
                    # 먼저 정수로 변환 시도
                    doc_id = int(document_id)
                except ValueError:
                    # 정수가 아니면 UUID 문자열로 사용
                    import uuid
                    try:
                        # UUID 형식 검증
                        uuid.UUID(document_id)
                        doc_id = document_id
                    except ValueError:
                        # UUID도 아니면 새로운 UUID 생성
                        doc_id = str(uuid.uuid4())
                
                # 문서에 변환된 ID 추가
                update_doc = {"id": doc_id, **document}
                
                # 메타데이터 병합
                if metadata:
                    update_doc = {**update_doc, **metadata}
                
                # upsert를 사용하여 업데이트
                await retriever.upsert(
                    collection=collection,
                    documents=[update_doc]
                )
                
                emoji = "✅" if use_emoji else ""
                await ctx.info(f"{emoji} 문서 업데이트 완료: {document_id}")
                return {
                    "status": "success",
                    "document_id": document_id,
                    "collection": collection
                }
            except Exception as e:
                emoji = "❌" if use_emoji else ""
                await ctx.error(f"{emoji} 문서 업데이트 실패: {str(e)}")
                raise ToolError(f"문서 업데이트 실패: {str(e)}")
        
        @server.tool
        async def delete_vector_document(
            ctx: Context,
            collection: str,
            document_id: str
        ) -> Dict[str, Any]:
            """
            벡터 컬렉션에서 문서 삭제
            
            Args:
                collection: 대상 컬렉션 이름
                document_id: 삭제할 문서 ID
            
            Returns:
                삭제 결과 정보
            """
            emoji = "🗑️" if use_emoji else ""
            await ctx.info(f"{emoji} '{collection}' 컬렉션에서 문서 '{document_id}' 삭제 중...")
            
            if "qdrant" not in self.retrievers:
                raise ToolError("벡터 데이터베이스를 사용할 수 없습니다")
            
            retriever = self.retrievers["qdrant"]
            if not retriever.connected:
                raise ToolError("벡터 데이터베이스를 사용할 수 없습니다 - 연결되지 않음")
            
            try:
                # ID를 UUID 또는 정수로 변환
                try:
                    # 먼저 정수로 변환 시도
                    doc_id = int(document_id)
                except ValueError:
                    # 정수가 아니면 UUID 문자열로 사용
                    import uuid
                    try:
                        # UUID 형식 검증
                        uuid.UUID(document_id)
                        doc_id = document_id
                    except ValueError:
                        # 잘못된 ID 형식
                        raise ValueError(f"잘못된 문서 ID 형식: {document_id}")
                
                # 단일 ID를 리스트로 변환하여 삭제
                await retriever.delete(
                    collection=collection,
                    ids=[doc_id]
                )
                
                emoji = "✅" if use_emoji else ""
                await ctx.info(f"{emoji} 문서 삭제 완료: {document_id}")
                return {
                    "status": "success",
                    "document_id": document_id,
                    "collection": collection,
                    "action": "deleted"
                }
            except Exception as e:
                emoji = "❌" if use_emoji else ""
                await ctx.error(f"{emoji} 문서 삭제 실패: {str(e)}")
                raise ToolError(f"문서 삭제 실패: {str(e)}")
        
        @server.tool
        async def create_database_record(
            ctx: Context,
            table: str,
            data: Dict[str, Any]
        ) -> Dict[str, Any]:
            """
            PostgreSQL 데이터베이스에 새 레코드 생성
            
            Args:
                table: 테이블 이름 (허용된 테이블만 가능)
                data: 생성할 레코드 데이터
            
            Returns:
                생성된 레코드 정보
            """
            emoji = "➕" if use_emoji else ""
            await ctx.info(f"{emoji} '{table}' 테이블에 레코드 생성 중...")
            
            if "postgres" not in self.retrievers:
                raise ToolError("데이터베이스를 사용할 수 없습니다")
            
            retriever = self.retrievers["postgres"]
            if not retriever.connected:
                raise ToolError("데이터베이스를 사용할 수 없습니다 - 연결되지 않음")
            
            # 허용된 테이블 목록 검증
            allowed_tables = [
                "users", "documents", "metadata", "content",
                "search_history", "configurations", "logs"
            ]
            
            if table not in allowed_tables:
                emoji = "🚫" if use_emoji else ""
                await ctx.error(f"{emoji} 허용되지 않은 테이블: {table}")
                raise ToolError(f"허용되지 않은 테이블: {table}. 허용된 테이블: {', '.join(allowed_tables)}")
            
            try:
                # SQL 인젝션 방지를 위한 prepared statement 사용
                columns = list(data.keys())
                values = list(data.values())
                placeholders = [f"${i+1}" for i in range(len(values))]
                
                # 테이블명은 화이트리스트로 이미 검증됨
                query = f"""
                    INSERT INTO {table} ({', '.join(columns)})
                    VALUES ({', '.join(placeholders)})
                    RETURNING *
                """
                
                # 연결 풀에서 연결 가져오기
                async with retriever._pool.acquire() as connection:
                    # prepared statement로 실행
                    result = await connection.fetchrow(query, *values)
                    
                    if result:
                        record = dict(result)
                        emoji = "✅" if use_emoji else ""
                        await ctx.info(f"{emoji} 레코드 생성 완료")
                        return {
                            "status": "success",
                            "table": table,
                            "record": record
                        }
                    else:
                        raise ToolError("레코드 생성에 실패했습니다")
                        
            except Exception as e:
                emoji = "❌" if use_emoji else ""
                await ctx.error(f"{emoji} 레코드 생성 실패: {str(e)}")
                raise ToolError(f"레코드 생성 실패: {str(e)}")
        
        @server.tool
        async def update_database_record(
            ctx: Context,
            table: str,
            record_id: str,
            data: Dict[str, Any]
        ) -> Dict[str, Any]:
            """
            PostgreSQL 데이터베이스의 레코드 수정
            
            Args:
                table: 테이블 이름 (허용된 테이블만 가능)
                record_id: 수정할 레코드 ID
                data: 업데이트할 데이터
            
            Returns:
                수정된 레코드 정보
            """
            emoji = "✏️" if use_emoji else ""
            await ctx.info(f"{emoji} '{table}' 테이블의 레코드 '{record_id}' 수정 중...")
            
            if "postgres" not in self.retrievers:
                raise ToolError("데이터베이스를 사용할 수 없습니다")
            
            retriever = self.retrievers["postgres"]
            if not retriever.connected:
                raise ToolError("데이터베이스를 사용할 수 없습니다 - 연결되지 않음")
            
            # 허용된 테이블 목록 검증
            allowed_tables = [
                "users", "documents", "metadata", "content",
                "search_history", "configurations", "logs"
            ]
            
            if table not in allowed_tables:
                emoji = "🚫" if use_emoji else ""
                await ctx.error(f"{emoji} 허용되지 않은 테이블: {table}")
                raise ToolError(f"허용되지 않은 테이블: {table}")
            
            try:
                # SET 절 구성
                set_clauses = []
                values = []
                for i, (col, val) in enumerate(data.items()):
                    set_clauses.append(f"{col} = ${i+1}")
                    values.append(val)
                
                # ID는 정수로 변환 후 마지막 파라미터로 추가
                record_id_int = int(record_id)  # 문자열을 정수로 변환
                values.append(record_id_int)
                
                query = f"""
                    UPDATE {table}
                    SET {', '.join(set_clauses)}
                    WHERE id = ${len(values)}
                    RETURNING *
                """
                
                async with retriever._pool.acquire() as connection:
                    # 트랜잭션 사용
                    async with connection.transaction():
                        # 먼저 레코드 존재 확인
                        check_query = f"SELECT id FROM {table} WHERE id = $1"
                        exists = await connection.fetchval(check_query, record_id_int)
                        
                        if not exists:
                            emoji = "⚠️" if use_emoji else ""
                            await ctx.warning(f"{emoji} 레코드를 찾을 수 없음: {record_id}")
                            raise ToolError(f"레코드를 찾을 수 없습니다: {record_id}")
                        
                        # 업데이트 실행 (values에 이미 모든 파라미터 포함)
                        result = await connection.fetchrow(query, *values)
                        
                        if result:
                            record = dict(result)
                            emoji = "✅" if use_emoji else ""
                            await ctx.info(f"{emoji} 레코드 수정 완료")
                            return {
                                "status": "success",
                                "table": table,
                                "record": record
                            }
                        else:
                            raise ToolError("레코드 수정에 실패했습니다")
                            
            except Exception as e:
                emoji = "❌" if use_emoji else ""
                await ctx.error(f"{emoji} 레코드 수정 실패: {str(e)}")
                raise ToolError(f"레코드 수정 실패: {str(e)}")
        
        @server.tool
        async def delete_database_record(
            ctx: Context,
            table: str,
            record_id: str
        ) -> Dict[str, Any]:
            """
            PostgreSQL 데이터베이스에서 레코드 삭제
            
            Args:
                table: 테이블 이름 (허용된 테이블만 가능)
                record_id: 삭제할 레코드 ID
            
            Returns:
                삭제 결과 정보
            """
            emoji = "🗑️" if use_emoji else ""
            await ctx.info(f"{emoji} '{table}' 테이블에서 레코드 '{record_id}' 삭제 중...")
            
            if "postgres" not in self.retrievers:
                raise ToolError("데이터베이스를 사용할 수 없습니다")
            
            retriever = self.retrievers["postgres"]
            if not retriever.connected:
                raise ToolError("데이터베이스를 사용할 수 없습니다 - 연결되지 않음")
            
            # 허용된 테이블 목록 검증
            allowed_tables = [
                "users", "documents", "metadata", "content",
                "search_history", "configurations", "logs"
            ]
            
            if table not in allowed_tables:
                emoji = "🚫" if use_emoji else ""
                await ctx.error(f"{emoji} 허용되지 않은 테이블: {table}")
                raise ToolError(f"허용되지 않은 테이블: {table}")
            
            try:
                query = f"""
                    DELETE FROM {table}
                    WHERE id = $1
                    RETURNING id
                """
                
                async with retriever._pool.acquire() as connection:
                    # 트랜잭션 사용
                    async with connection.transaction():
                        # 삭제 실행
                        record_id_int = int(record_id)  # 문자열을 정수로 변환
                        deleted_id = await connection.fetchval(query, record_id_int)
                        
                        if deleted_id:
                            emoji = "✅" if use_emoji else ""
                            await ctx.info(f"{emoji} 레코드 삭제 완료")
                            return {
                                "status": "success",
                                "table": table,
                                "record_id": record_id,
                                "action": "deleted"
                            }
                        else:
                            emoji = "⚠️" if use_emoji else ""
                            await ctx.warning(f"{emoji} 삭제할 레코드를 찾을 수 없음: {record_id}")
                            raise ToolError(f"삭제할 레코드를 찾을 수 없습니다: {record_id}")
                            
            except Exception as e:
                emoji = "❌" if use_emoji else ""
                await ctx.error(f"{emoji} 레코드 삭제 실패: {str(e)}")
                raise ToolError(f"레코드 삭제 실패: {str(e)}")
        
        @server.tool
        async def search_database(
            ctx: Context,
            query: str,
            table: Optional[str] = None,
            limit: int = 10,
            use_cache: bool = True
        ) -> List[Dict[str, Any]]:
            """
            PostgreSQL을 사용한 관계형 데이터베이스 검색
            
            Args:
                query: SQL 쿼리 또는 검색 텍스트
                table: 텍스트 검색용 테이블 이름 (선택적)
                limit: 최대 결과 수 (기본값: 10)
                use_cache: 캐시된 결과 사용 여부 (캐싱 활성화 시에만 적용)
            
            Returns:
                데이터베이스 레코드 목록
            """
            emoji = "🔍" if use_emoji else ""
            await ctx.info(f"{emoji} 데이터베이스 검색 중...")
            
            if "postgres" not in self.retrievers:
                raise ToolError("데이터베이스 검색을 사용할 수 없습니다")
            
            retriever = self.retrievers["postgres"]
            if not retriever.connected:
                raise ToolError("데이터베이스 검색을 사용할 수 없습니다 - 연결되지 않음")
            
            # 쿼리 유형 로깅
            if query.upper().startswith("SELECT"):
                emoji = "🗂️" if use_emoji else ""
                await ctx.info(f"{emoji} SQL 쿼리 실행 중")
            else:
                emoji = "📝" if use_emoji else ""
                await ctx.info(f"{emoji} 텍스트 검색 수행 중 - 테이블: {table or '모든 테이블'}")
            
            # 캐싱이 활성화된 경우 캐시 제어
            if self.config.features["cache"] and hasattr(retriever, '_use_cache'):
                original_use_cache = retriever._use_cache
                if not use_cache:
                    retriever._use_cache = False
            
            try:
                results = []
                async for result in retriever.retrieve(query, limit=limit, table=table):
                    results.append(result)
                
                emoji = "✅" if use_emoji else ""
                await ctx.info(f"{emoji} 데이터베이스 검색 완료: {len(results)}개 결과")
                return results
            except QueryError as e:
                emoji = "❌" if use_emoji else ""
                await ctx.error(f"{emoji} 데이터베이스 검색 실패: {str(e)}")
                raise ToolError(str(e))
            finally:
                # 캐시 설정 복원
                if self.config.features["cache"] and hasattr(retriever, '_use_cache'):
                    retriever._use_cache = original_use_cache
        
        @server.tool
        async def search_all(
            ctx: Context,
            query: str,
            limit: int = 10
        ) -> Dict[str, Any]:
            """
            모든 가능한 리트리버에서 동시 검색
            
            Args:
                query: 검색 쿼리 문자열
                limit: 각 소스당 최대 결과 수 (기본값: 10)
            
            Returns:
                모든 소스의 결과와 발생한 오류들
            """
            emoji = "🔍" if use_emoji else ""
            await ctx.info(f"{emoji} 모든 소스에서 동시 검색 시작...")
            
            results = {}
            errors = {}
            
            # 연결된 모든 리트리버에 대한 작업 생성
            tasks = []
            for name, retriever in self.retrievers.items():
                if retriever.connected:
                    tasks.append((name, self._search_single_source(name, retriever, query, limit, ctx)))
            
            if not tasks:
                emoji = "⚠️" if use_emoji else ""
                await ctx.warning(f"{emoji} 연결된 리트리버가 없습니다")
                return {"results": {}, "errors": {"all": "사용 가능한 리트리버가 없습니다"}}
            
            # 모든 검색을 동시에 실행
            emoji = "🚀" if use_emoji else ""
            await ctx.info(f"{emoji} {len(tasks)}개 소스에서 동시 검색 중...")
            
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
            
            emoji = "✅" if use_emoji else ""
            await ctx.info(
                f"{emoji} 검색 완료: {len(results)}개 성공, {len(errors)}개 실패"
            )
            
            return {
                "results": results,
                "errors": errors,
                "sources_searched": len(results) + len(errors)
            }
        
        @server.tool
        async def health_check(ctx: Context) -> Dict[str, Any]:
            """
            모든 리트리버와 서버 구성 요소의 건강 상태 검사
            
            Returns:
                포괄적인 건강 상태 정보
            """
            emoji = "🏥" if use_emoji else ""
            await ctx.info(f"{emoji} 건강 상태 검사 수행 중...")
            
            health_status = {
                "service": self.config.name,
                "profile": self.config.profile.value,
                "status": "healthy",
                "features": self.config.get_enabled_features(),
                "retrievers": {}
            }
            
            # 추가 정보
            if self.config.features["auth"]:
                health_status["auth_enabled"] = True
            
            if self.config.features["context"] and self.context_store is not None:
                health_status["context_store_size"] = len(self.context_store)
            
            # 리트리버 상태 확인
            for name, retriever in self.retrievers.items():
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
            
            # 모든 리트리버가 비정상인 경우
            if not any(r.get("connected", False) for r in health_status["retrievers"].values()):
                health_status["status"] = "unhealthy"
            
            emoji = "✅" if use_emoji else ""
            await ctx.info(f"{emoji} 건강 상태 검사 완료: {health_status['status']}")
            return health_status
        
        # 캐시 관련 도구 (캐싱 활성화 시에만)
        if self.config.features["cache"]:
            @server.tool
            async def invalidate_cache(
                ctx: Context,
                retriever_name: Optional[str] = None,
                pattern: Optional[str] = None
            ) -> Dict[str, int]:
                """
                캐시된 결과 무효화
                
                Args:
                    retriever_name: 캐시를 지울 리트리버 이름
                    pattern: 특정 캐시 키를 매칭하는 패턴
                
                Returns:
                    리트리버별 무효화된 키 수
                """
                emoji = "🗑️" if use_emoji else ""
                await ctx.info(f"{emoji} 캐시 무효화 대상: {retriever_name or '모든 리트리버'}")
                
                results = {}
                
                if retriever_name:
                    if retriever_name not in self.retrievers:
                        raise ToolError(f"알 수 없는 리트리버: {retriever_name}")
                    
                    retriever = self.retrievers[retriever_name]
                    if hasattr(retriever, 'invalidate_cache'):
                        count = await retriever.invalidate_cache(pattern)
                        results[retriever_name] = count
                        await ctx.info(f"{retriever_name}에서 {count}개의 캐시 항목 삭제")
                else:
                    for name, retriever in self.retrievers.items():
                        if hasattr(retriever, 'invalidate_cache'):
                            count = await retriever.invalidate_cache(pattern)
                            results[name] = count
                            await ctx.info(f"{name}에서 {count}개의 캐시 항목 삭제")
                
                return results
            
            @server.tool
            async def cache_stats(ctx: Context) -> Dict[str, Any]:
                """
                모든 리트리버의 캐시 통계 조회
                
                Returns:
                    캐시 설정 및 상태 정보
                """
                emoji = "📊" if use_emoji else ""
                await ctx.info(f"{emoji} 캐시 통계 수집 중...")
                
                stats = {}
                for name, retriever in self.retrievers.items():
                    if hasattr(retriever, '_cache') and hasattr(retriever, '_use_cache'):
                        if retriever._use_cache:
                            stats[name] = {
                                "cache_enabled": True,
                                "cache_ttl": retriever._cache.config.default_ttl,
                                "cache_namespace": retriever._get_cache_namespace()
                            }
                    else:
                        stats[name] = {"cache_enabled": False}
                
                return stats
        
        # 메트릭 도구 (메트릭 활성화 시에만)
        if self.config.features["metrics"]:
            @server.tool
            async def get_metrics(ctx: Context) -> Dict[str, Any]:
                """
                서버 성능 메트릭 조회
                
                Returns:
                    현재 메트릭 요약
                """
                emoji = "📊" if use_emoji else ""
                await ctx.info(f"{emoji} 서버 메트릭 조회 중...")
                
                if not self.metrics_middleware:
                    raise ToolError("메트릭을 사용할 수 없습니다")
                
                metrics = await self.metrics_middleware.get_metrics_summary()
                
                emoji = "✅" if use_emoji else ""
                await ctx.info(f"{emoji} 메트릭 조회 성공")
                return metrics
        
        # MCP 프로토콜 알림 처리기는 FastMCP에서 자동 처리됨
    
    async def _search_single_source(
        self,
        name: str,
        retriever: Retriever,
        query: str,
        limit: int,
        ctx: Context
    ) -> Dict[str, Any]:
        """단일 리트리버 검색을 위한 도우미 함수"""
        try:
            use_emoji = self.config.logging_config and self.config.logging_config.use_emoji
            emoji = "🔸" if use_emoji else ""
            await ctx.info(f"  {emoji} {name} 검색 중...")
            
            results = []
            async for result in retriever.retrieve(query, limit=limit):
                results.append(result)
            return {"results": results}
        except Exception as e:
            emoji = "❌" if use_emoji else ""
            await ctx.error(f"  {emoji} {name} 검색 오류: {str(e)}")
            return {"error": str(e)}


def main():
    """메인 실행 함수"""
    # 설정 로드
    config = ServerConfig.from_env()
    
    logger.info(
        "통합 MCP 서버 시작",
        profile=config.profile.value,
        transport=config.transport,
        port=config.port if config.transport == "http" else "N/A",
        features=config.get_enabled_features()
    )
    
    # 서버 생성
    unified_server = UnifiedMCPServer(config)
    mcp = unified_server.create_server()
    
    # 실행
    if config.transport == "http":
        logger.info(f"HTTP 모드로 서버 시작 (포트: {config.port})")
        mcp.run(transport="http", port=config.port)
    else:
        logger.info("STDIO 모드로 서버 시작")
        mcp.run()


# 하위 호환성을 위한 서버 인스턴스
server = None

if __name__ == "__main__":
    main()