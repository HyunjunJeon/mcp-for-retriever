"""Qdrant 메모리 모드 테스트 설정"""

import pytest
import os
from typing import Dict, Any
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams


@pytest.fixture
def qdrant_memory_config() -> Dict[str, Any]:
    """Qdrant 메모리 모드 설정"""
    return {
        "host": ":memory:",  # 메모리 모드
        "port": 6333,  # 무시됨
        "embedding_dim": 384,  # 테스트용 작은 차원
        "embedding_model": "test-model"
    }


@pytest.fixture
async def qdrant_memory_client():
    """테스트용 Qdrant 메모리 클라이언트"""
    client = QdrantClient(":memory:")
    yield client
    # 메모리 모드는 자동으로 정리됨


@pytest.fixture
def mock_embedding_function():
    """테스트용 임베딩 함수"""
    import numpy as np
    
    async def embed_text(text: str) -> list[float]:
        """간단한 해시 기반 임베딩 생성"""
        # 텍스트를 해시하여 시드로 사용
        seed = hash(text) % (2**32)
        np.random.seed(seed)
        # 정규화된 벡터 생성
        vector = np.random.randn(384)
        vector = vector / np.linalg.norm(vector)
        return vector.tolist()
    
    return embed_text


@pytest.fixture
def test_collection_name():
    """테스트용 컬렉션 이름 생성"""
    import uuid
    return f"test_collection_{uuid.uuid4().hex[:8]}"


@pytest.fixture
async def setup_test_collection(qdrant_memory_client, test_collection_name):
    """테스트 컬렉션 생성"""
    await qdrant_memory_client.create_collection(
        collection_name=test_collection_name,
        vectors_config=VectorParams(
            size=384,
            distance=Distance.COSINE
        )
    )
    return test_collection_name