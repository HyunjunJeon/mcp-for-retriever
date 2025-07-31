#!/usr/bin/env python3
"""Qdrant 메모리 모드 테스트"""

import asyncio
import os
from src.retrievers.qdrant_memory import QdrantMemoryRetriever
from qdrant_client.models import Distance

async def test_qdrant_memory():
    """Qdrant 메모리 모드 테스트"""
    print("=== Qdrant 메모리 모드 테스트 ===\n")
    
    # 1. 메모리 모드 리트리버 생성
    config = {
        "host": ":memory:",  # 자동으로 메모리 모드 설정됨
        "embedding_dim": 384
    }
    
    retriever = QdrantMemoryRetriever(config)
    
    try:
        # 2. 연결
        print("1. Qdrant 메모리 모드 연결...")
        await retriever.connect()
        print("   ✅ 연결 성공\n")
        
        # 3. 컬렉션 생성
        collection_name = "test_collection"
        print(f"2. 컬렉션 '{collection_name}' 생성...")
        await retriever.create_collection(
            collection_name=collection_name,
            vector_size=384,
            distance=Distance.COSINE
        )
        print("   ✅ 컬렉션 생성 성공\n")
        
        # 4. 문서 추가
        print("3. 문서 추가...")
        documents = [
            {
                "id": 1,  # 정수 ID
                "text": "Python은 다목적 프로그래밍 언어입니다.",
                "metadata": {"category": "programming", "language": "korean"}
            },
            {
                "id": 2,
                "text": "Machine Learning은 인공지능의 한 분야입니다.",
                "metadata": {"category": "ai", "language": "korean"}
            },
            {
                "id": "550e8400-e29b-41d4-a716-446655440000",  # UUID 문자열
                "text": "FastAPI는 현대적인 웹 API 프레임워크입니다.",
                "metadata": {"category": "web", "language": "korean"}
            }
        ]
        
        await retriever.upsert(
            collection=collection_name,
            documents=documents
        )
        print(f"   ✅ {len(documents)}개 문서 추가 성공\n")
        
        # 5. 벡터 검색
        print("4. 벡터 검색 테스트...")
        query = "프로그래밍 언어"
        results = []
        async for result in retriever.retrieve(
            query=query,
            collection=collection_name,
            limit=5
        ):
            results.append(result)
        
        print(f"   쿼리: '{query}'")
        print(f"   ✅ {len(results)}개 결과 검색됨")
        for i, result in enumerate(results, 1):
            print(f"   {i}. ID: {result['id']}, Score: {result['score']:.3f}")
            print(f"      Text: {result['text'][:50]}...")
        print()
        
        # 6. 문서 삭제
        print("5. 문서 삭제 테스트...")
        await retriever.delete(
            collection=collection_name,
            ids=[1]  # 정수 ID 삭제
        )
        print("   ✅ 문서 ID 1 삭제 성공\n")
        
        # 7. 삭제 확인을 위한 재검색
        print("6. 삭제 확인...")
        results_after = []
        async for result in retriever.retrieve(
            query=query,
            collection=collection_name,
            limit=5
        ):
            results_after.append(result)
        
        print(f"   삭제 후 검색 결과: {len(results_after)}개")
        deleted = not any(r['id'] == '1' for r in results_after)
        print(f"   ✅ ID 1 문서 {'삭제됨' if deleted else '여전히 존재'}")
        
    except Exception as e:
        print(f"❌ 오류 발생: {e}")
        import traceback
        traceback.print_exc()
    
    finally:
        # 8. 연결 해제
        await retriever.disconnect()
        print("\n✅ 테스트 완료 - 메모리 모드는 자동으로 정리됩니다.")


if __name__ == "__main__":
    asyncio.run(test_qdrant_memory())