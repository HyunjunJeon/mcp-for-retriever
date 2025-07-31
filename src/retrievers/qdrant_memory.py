"""
Qdrant 메모리 모드 리트리버 - 테스트 전용

이 모듈은 테스트를 위한 Qdrant 메모리 모드 구현을 제공합니다.
실제 Qdrant 서버 없이 인메모리에서 작동합니다.
"""

import numpy as np
from typing import AsyncIterator, Any, Optional, Callable
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct

from src.retrievers.qdrant import QdrantRetriever
from src.retrievers.base import RetrieverConfig


class QdrantMemoryRetriever(QdrantRetriever):
    """
    테스트용 Qdrant 메모리 모드 리트리버
    
    실제 Qdrant 서버 없이 메모리에서 작동하는 리트리버입니다.
    간단한 해시 기반 임베딩을 사용합니다.
    """
    
    def __init__(self, config: RetrieverConfig):
        """메모리 모드 리트리버 초기화"""
        # 메모리 모드 강제 설정
        config["host"] = ":memory:"
        config["embedding_dim"] = config.get("embedding_dim", 384)  # 테스트용 작은 차원
        super().__init__(config)
    
    def _create_embedding_function(self) -> Callable:
        """
        테스트용 해시 기반 임베딩 함수 생성
        
        Returns:
            Callable: 텍스트를 임베딩으로 변환하는 비동기 함수
        """
        async def embed_text(text: str) -> list[float]:
            # 텍스트를 해시하여 시드로 사용
            seed = hash(text) % (2**32)
            np.random.seed(seed)
            # 정규화된 벡터 생성
            vector = np.random.randn(self.embedding_dim)
            vector = vector / np.linalg.norm(vector)
            return vector.tolist()
        
        return embed_text