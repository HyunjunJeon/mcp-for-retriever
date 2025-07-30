"""
Qdrant 벡터 데이터베이스 리트리버 구현

이 모듈은 Qdrant 벡터 데이터베이스를 사용하여 벡터 유사도 검색 기능을 제공합니다.
Qdrant는 고성능 벡터 검색 엔진으로, 대규모 임베딩 데이터를 효율적으로 처리합니다.

주요 기능:
    - 벡터 유사도 검색 (Cosine, Euclidean, Dot Product)
    - 컨렉션 관리 (CRUD 작업)
    - 비동기 배치 처리
    - 필터링 및 메타데이터 검색
    - 임베딩 함수 통합 (플레이스홀더)

환경 변수:
    QDRANT_HOST: Qdrant 서버 호스트 (기본값: localhost)
    QDRANT_PORT: Qdrant 서버 포트 (기본값: 6333)
    QDRANT_API_KEY: API 키 (선택사항)

작성일: 2024-01-30
"""

from typing import AsyncIterator, Any, Optional, Callable
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct

from src.retrievers.base import (
    Retriever,
    RetrieverHealth,
    ConnectionError,
    QueryError,
    QueryResult,
    RetrieverConfig,
)


class QdrantRetriever(Retriever):
    """
    Qdrant 벡터 데이터베이스를 사용하는 리트리버 구현체
    
    Qdrant를 통해 고차원 벡터 공간에서 유사한 벡터를 검색합니다.
    텍스트를 임베딩으로 변환한 후 코사인 유사도 등의 거리 메트릭을
    사용하여 가장 유사한 결과를 찾습니다.
    
    Attributes:
        host (str): Qdrant 서버 호스트
        port (int): Qdrant 서버 포트
        api_key (Optional[str]): API 인증 키
        timeout (int): 요청 타임아웃 (초)
        embedding_model (str): 임베딩 모델 이름
        embedding_dim (int): 임베딩 차원 크기
    """
    
    def __init__(self, config: RetrieverConfig):
        """
        Qdrant 리트리버 초기화
        
        설정 정보를 받아 Qdrant 클라이언트를 초기화합니다.
        
        Args:
            config: 설정 딕셔너리
                - host (str): Qdrant 서버 호스트 (필수)
                - port (int): Qdrant 서버 포트 (기본값: 6333)
                - api_key (str): API 인증 키 (선택사항)
                - timeout (int): 요청 타임아웃 (초 단위, 기본값: 30)
                - embedding_model (str): 임베딩 모델 이름 (기본값: "text-embedding-ada-002")
                    - OpenAI: "text-embedding-ada-002", "text-embedding-3-small"
                    - Cohere: "embed-english-v3.0", "embed-multilingual-v3.0"
                - embedding_dim (int): 임베딩 차원 크기 (기본값: 1536)
                    - OpenAI Ada-002: 1536
                    - OpenAI 3-small: 1536
                    - Cohere: 1024
                
        Raises:
            ValueError: host가 제공되지 않은 경우
        """
        super().__init__(config)
        
        # 설정 추출 및 검증
        self.host = config.get("host")
        if not self.host:
            raise ValueError("host is required for QdrantRetriever")
        
        self.port = config.get("port", 6333)
        self.api_key = config.get("api_key")
        self.timeout = config.get("timeout", 30)
        self.embedding_model = config.get("embedding_model", "text-embedding-ada-002")
        self.embedding_dim = config.get("embedding_dim", 1536)
        
        # 클라이언트와 임베딩 함수는 connect() 시 생성
        self._client: Optional[QdrantClient] = None
        self._embed_text: Optional[Callable] = None
    
    async def connect(self) -> None:
        """
        Qdrant 서버에 연결
        
        Qdrant 클라이언트를 생성하고 연결을 테스트합니다.
        gRPC 또는 HTTP 프로토콜을 사용하여 통신합니다.
        
        Raises:
            ConnectionError: Qdrant 연결 실패 시
                - 네트워크 오류
                - 잘못된 호스트/포트
                - 인증 실패
        """
        try:
            # Qdrant 클라이언트 생성
            self._client = QdrantClient(
                host=self.host,
                port=self.port,
                api_key=self.api_key,
                timeout=self.timeout
            )
            
            # 연결 테스트 (컨렉션 목록 조회)
            await self._test_connection()
            
            # 임베딩 함수 초기화 (실제 구현에서는 실제 임베딩 서비스 사용)
            self._embed_text = self._create_embedding_function()
            
            self._connected = True
            self._log_operation("connect", status="success")
            
        except Exception as e:
            self._connected = False
            self._log_operation("connect", status="failed", error=str(e))
            raise ConnectionError(
                f"Failed to connect to Qdrant: {e}", "QdrantRetriever"
            )
    
    async def disconnect(self) -> None:
        """
        Qdrant 연결 종료
        
        클라이언트 연결을 닫고 리소스를 정리합니다.
        모든 핑들링된 연결이 안전하게 종료됩니다.
        """
        if self._client:
            await self._client.close()
            self._client = None
        
        self._embed_text = None
        self._connected = False
        self._log_operation("disconnect")
    
    async def retrieve(
        self, query: str, limit: int = 10, **kwargs: Any
    ) -> AsyncIterator[QueryResult]:
        """
        Qdrant에서 유사한 벡터 검색
        
        주어진 텍스트를 임베딩으로 변환한 후 벡터 공간에서
        가장 유사한 벡터들을 검색합니다. kNN (k-Nearest Neighbors)
        알고리즘을 사용하여 효율적으로 검색합니다.
        
        Args:
            query (str): 검색할 텍스트 쿼리
            limit (int): 반환할 최대 결과 수 (기본값: 10)
            **kwargs: 추가 검색 매개변수
                - collection (str): 검색할 컨렉션 이름 (필수)
                - score_threshold (float): 최소 유사도 점수 (0.0 ~ 1.0)
                - filter (dict): Qdrant 필터 조건
                    - must: 필수 조건
                    - should: 선택 조건
                    - must_not: 제외 조건
                
        Yields:
            QueryResult: 검색 결과 딕셔너리
                - id: 벡터 ID
                - score: 유사도 점수
                - text: 원본 텍스트
                - source: 소스 이름 ("qdrant")
                - 기타 메타데이터 필드
            
        Raises:
            ConnectionError: 연결되지 않은 경우
            QueryError: 검색 실패 시
                - 컨렉션이 없는 경우
                - 임베딩 실패
                - 필터 오류
        """
        if not self._connected:
            raise ConnectionError("Not connected to Qdrant", "QdrantRetriever")
        
        collection = kwargs.get("collection")
        if not collection:
            raise QueryError("Collection name is required", "QdrantRetriever")
        
        try:
            # 쿼리 텍스트를 임베딩으로 변환
            query_vector = await self._embed_text(query)
            
            # 벡터 검색 수행
            results = await self._client.search(
                collection_name=collection,
                query_vector=query_vector,
                limit=limit,
                score_threshold=kwargs.get("score_threshold"),
                query_filter=kwargs.get("filter")
            )
            
            # 결과 필터링 및 yield
            score_threshold = kwargs.get("score_threshold", 0.0)
            for result in results:
                if result.score >= score_threshold:
                    yield self._format_result(result)
                    
        except Exception as e:
            self._log_operation("retrieve", status="failed", error=str(e))
            raise QueryError(f"Search failed: {e}", "QdrantRetriever")
    
    async def health_check(self) -> RetrieverHealth:
        """
        Qdrant 서비스 상태 확인
        
        Qdrant 서버의 상태와 컨렉션 정보를 확인합니다.
        
        Returns:
            RetrieverHealth: 현재 상태 정보
                - healthy: 정상 작동 여부
                - service_name: "QdrantRetriever"
                - details: 연결 상태, 호스트 정보, 컨렉션 수
                - error: 에러 메시지 (문제 발생 시)
        """
        if not self._connected:
            return RetrieverHealth(
                healthy=False,
                service_name="QdrantRetriever",
                details={"connected": False},
                error="Not connected"
            )
        
        try:
            # 컨렉션 정보 조회
            collections_info = await self._client.get_collections()
            collections_count = len(collections_info.collections)
            
            return RetrieverHealth(
                healthy=True,
                service_name="QdrantRetriever",
                details={
                    "connected": True,
                    "host": f"{self.host}:{self.port}",
                    "collections_count": collections_count,
                }
            )
            
        except Exception as e:
            return RetrieverHealth(
                healthy=False,
                service_name="QdrantRetriever",
                details={"connected": self._connected},
                error=str(e)
            )
    
    async def create_collection(
        self,
        collection_name: str,
        vector_size: Optional[int] = None,
        distance: Distance = Distance.COSINE
    ) -> None:
        """
        Qdrant에 새 컨렉션 생성
        
        벡터 데이터를 저장할 새로운 컨렉션을 생성합니다.
        컨렉션은 동일한 차원의 벡터들을 저장하는 컨테이너입니다.
        
        Args:
            collection_name (str): 컨렉션 이름
            vector_size (Optional[int]): 벡터 차원 크기 (기본값: embedding_dim)
            distance (Distance): 거리 메트릭 (기본값: COSINE)
                - COSINE: 코사인 유사도 (각도 기반)
                - EUCLIDEAN: 유클리드 거리 (직선 거리)
                - DOT: 내적 (Dot Product)
            
        Raises:
            ConnectionError: 연결되지 않은 경우
            QueryError: 컨렉션 생성 실패 시
                - 이미 존재하는 컨렉션
                - 잘못된 매개변수
        """
        if not self._connected:
            raise ConnectionError("Not connected to Qdrant", "QdrantRetriever")
        
        try:
            vector_size = vector_size or self.embedding_dim
            
            await self._client.create_collection(
                collection_name=collection_name,
                vectors_config=VectorParams(
                    size=vector_size,
                    distance=distance
                )
            )
            
            self._log_operation(
                "create_collection",
                collection=collection_name,
                vector_size=vector_size
            )
            
        except Exception as e:
            raise QueryError(f"Failed to create collection: {e}", "QdrantRetriever")
    
    async def upsert(
        self,
        collection: str,
        documents: list[dict[str, Any]]
    ) -> None:
        """
        컨렉션에 문서 삽입 또는 업데이트
        
        텍스트를 임베딩으로 변환한 후 Qdrant에 저장합니다.
        동일한 ID가 이미 존재하면 업데이트하고, 없으면 새로 삽입합니다.
        
        Args:
            collection (str): 컨렉션 이름
            documents (list[dict[str, Any]]): 문서 리스트
                각 문서는 다음 필드를 포함해야 함:
                - id (str/int): 문서 고유 ID
                - text (str): 임베딩할 텍스트
                - metadata (dict, 선택): 추가 메타데이터
            
        Raises:
            ConnectionError: 연결되지 않은 경우
            QueryError: 업서트 실패 시
                - 컨렉션이 없는 경우
                - 임베딩 실패
                - 필수 필드 누락
        """
        if not self._connected:
            raise ConnectionError("Not connected to Qdrant", "QdrantRetriever")
        
        try:
            points = []
            for doc in documents:
                # 텍스트를 임베딩으로 변환
                vector = await self._embed_text(doc["text"])
                
                # Qdrant 포인트 생성
                point = PointStruct(
                    id=doc["id"],
                    vector=vector,
                    payload={
                        "text": doc["text"],
                        **doc.get("metadata", {})
                    }
                )
                points.append(point)
            
            # 배치 업서트 (효율성을 위해 한 번에 처리)
            await self._client.upsert(
                collection_name=collection,
                points=points
            )
            
            self._log_operation(
                "upsert",
                collection=collection,
                count=len(documents)
            )
            
        except Exception as e:
            raise QueryError(f"Failed to upsert documents: {e}", "QdrantRetriever")
    
    async def delete(
        self,
        collection: str,
        ids: list[str]
    ) -> None:
        """
        ID로 벡터 삭제
        
        지정된 ID의 벡터들을 컨렉션에서 삭제합니다.
        삭제는 즉시 적용되며 복구할 수 없습니다.
        
        Args:
            collection (str): 컨렉션 이름
            ids (list[str]): 삭제할 벡터 ID 리스트
            
        Raises:
            ConnectionError: 연결되지 않은 경우
            QueryError: 삭제 실패 시
                - 컨렉션이 없는 경우
                - 잘못된 ID 형식
        """
        if not self._connected:
            raise ConnectionError("Not connected to Qdrant", "QdrantRetriever")
        
        try:
            await self._client.delete(
                collection_name=collection,
                points_selector=ids
            )
            
            self._log_operation(
                "delete",
                collection=collection,
                count=len(ids)
            )
            
        except Exception as e:
            raise QueryError(f"Failed to delete vectors: {e}", "QdrantRetriever")
    
    async def _test_connection(self) -> None:
        """
        Qdrant 연결 테스트
        
        컨렉션 목록을 조회하여 연결 상태를 확인합니다.
        
        Raises:
            Exception: 연결 테스트 실패 시
        """
        if not self._client:
            raise Exception("Client not initialized")
        
        # 컨렉션 목록 조회로 연결 확인
        await self._client.get_collections()
    
    def _create_embedding_function(self) -> Callable:
        """
        텍스트 임베딩 함수 생성
        
        텍스트를 벡터로 변환하는 함수를 생성합니다.
        실제 구현에서는 OpenAI, Cohere, HuggingFace 등의
        임베딩 API를 사용해야 합니다.
        
        Returns:
            Callable: 텍스트를 임베딩으로 변환하는 비동기 함수
                - 입력: 텍스트 문자열
                - 출력: 임베딩 벡터 (실수 리스트)
        """
        # 플레이스홀더 - 실제 구현에서는 실제 임베딩 서비스 사용
        async def embed_text(text: str) -> list[float]:
            # 임베딩 생성 시뮤레이션
            # 실제 구현 예시:
            # - OpenAI: openai.embeddings.create(model="text-embedding-ada-002", input=text)
            # - Cohere: cohere.embed(texts=[text], model="embed-english-v3.0")
            return [0.0] * self.embedding_dim
        
        return embed_text
    
    def _format_result(self, result: Any) -> QueryResult:
        """
        Qdrant 검색 결과를 표준 형식으로 변환
        
        Qdrant의 결과 형식을 MCP 서버의 표준 결과 형식으로
        변환합니다. 모든 리트리버가 동일한 형식을 사용하도록 합니다.
        
        Args:
            result: Qdrant 검색 결과 객체
                - id: 벡터 ID
                - score: 유사도 점수
                - payload: 메타데이터
            
        Returns:
            QueryResult: 표준화된 결과 딕셔너리
                - id: 결과 ID
                - score: 유사도 점수 (0.0 ~ 1.0)
                - text: 원본 텍스트
                - source: 데이터 출처 ("qdrant" 고정)
                - 기타 메타데이터 필드
        """
        payload = result.payload or {}
        
        return {
            "id": str(result.id),
            "score": float(result.score),
            "text": payload.get("text", ""),
            "source": "qdrant",
            # text 필드를 제외한 모든 payload 필드 포함
            **{k: v for k, v in payload.items() if k != "text"}
        }