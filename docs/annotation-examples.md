# 한글 주석 작성 예시 및 가이드

## 주석 작성 원칙

1. **명확성**: 코드가 "무엇을" 하는지보다 "왜" 그렇게 하는지 설명
2. **간결성**: 불필요하게 장황하지 않게 작성
3. **일관성**: 동일한 스타일과 용어 사용
4. **유용성**: 실제로 도움이 되는 정보 포함

## 파일 레벨 독스트링 예시

### Before (영문)
```python
"""Base retriever interface for all data sources."""
```

### After (한글)
```python
"""
리트리버 기본 인터페이스 모듈

이 모듈은 모든 데이터 소스(웹, 벡터 DB, RDB 등)에서 정보를 검색하는
통합 인터페이스를 정의합니다. 

주요 구성요소:
    - Retriever: 추상 기본 클래스로 모든 리트리버가 구현해야 하는 인터페이스
    - RetrieverConfig: 리트리버 설정을 위한 기본 클래스
    - RetrieverType: 지원되는 리트리버 타입 열거형

사용 예제:
    ```python
    from src.retrievers.base import Retriever, RetrieverConfig
    
    class MyRetriever(Retriever[MyConfig]):
        async def retrieve(self, query: str) -> AsyncIterator[Dict[str, Any]]:
            # 구현
            yield {"result": "data"}
    ```

작성일: 2024-01-XX
"""
```

## 클래스 독스트링 예시

### Before (영문)
```python
class Retriever(ABC, Generic[T]):
    """Abstract base class for all retrievers."""
```

### After (한글)
```python
class Retriever(ABC, Generic[T]):
    """
    모든 리트리버의 추상 기본 클래스
    
    이 클래스는 다양한 데이터 소스에서 정보를 검색하는 통합된 인터페이스를
    제공합니다. 모든 구체적인 리트리버 구현체는 이 클래스를 상속받아
    필수 메서드들을 구현해야 합니다.
    
    제네릭 타입 T는 RetrieverConfig의 서브클래스여야 하며, 각 리트리버의
    특정 설정을 정의합니다.
    
    속성:
        config (T): 리트리버의 설정 객체
        _connected (bool): 데이터 소스 연결 상태
        
    주요 메서드:
        connect(): 데이터 소스에 연결
        disconnect(): 연결 종료
        retrieve(): 쿼리 실행 및 결과 반환
        health_check(): 서비스 상태 확인
        
    사용 예제:
        ```python
        async with MyRetriever(config) as retriever:
            async for result in retriever.retrieve("검색어"):
                print(result)
        ```
    """
```

## 메서드 독스트링 예시

### Before (영문)
```python
async def retrieve(self, query: str, **kwargs) -> AsyncIterator[Dict[str, Any]]:
    """Retrieve information based on the query."""
```

### After (한글)
```python
async def retrieve(self, query: str, **kwargs) -> AsyncIterator[Dict[str, Any]]:
    """
    주어진 쿼리로 정보를 검색하고 결과를 스트리밍으로 반환
    
    이 메서드는 데이터 소스에서 쿼리와 관련된 정보를 비동기적으로 검색합니다.
    결과는 AsyncIterator로 반환되어 대용량 결과도 메모리 효율적으로 처리할 수 있습니다.
    
    Args:
        query (str): 검색할 쿼리 문자열
        **kwargs: 리트리버별 추가 매개변수
            - limit (int): 반환할 최대 결과 수
            - filters (dict): 필터링 조건
            - timeout (float): 검색 타임아웃 (초)
    
    Yields:
        Dict[str, Any]: 검색 결과 딕셔너리
            - id (str): 결과 고유 식별자
            - content (str): 검색된 내용
            - score (float): 관련성 점수 (0.0 ~ 1.0)
            - metadata (dict): 추가 메타데이터
    
    Raises:
        RetrieverError: 검색 중 오류 발생 시
        ConnectionError: 데이터 소스 연결 실패 시
        TimeoutError: 검색 시간 초과 시
        
    Example:
        ```python
        async for result in retriever.retrieve("파이썬 비동기"):
            if result['score'] > 0.8:
                print(f"높은 관련성: {result['content']}")
        ```
    """
```

## 인라인 주석 예시

### Before (영문)
```python
# Check if already connected
if self._connected:
    return

# Create connection with retry logic
for attempt in range(self.config.retry_attempts):
    try:
        # Attempt connection
        await self._create_connection()
        break
    except Exception as e:
        if attempt == self.config.retry_attempts - 1:
            raise
        # Wait before retry
        await asyncio.sleep(self.config.retry_delay * (2 ** attempt))
```

### After (한글)
```python
# 이미 연결되어 있는지 확인
if self._connected:
    return

# 재시도 로직을 포함한 연결 생성
# 지수 백오프(exponential backoff)를 사용하여 재시도 간격을 점진적으로 증가
for attempt in range(self.config.retry_attempts):
    try:
        # 데이터 소스에 연결 시도
        await self._create_connection()
        break
    except Exception as e:
        if attempt == self.config.retry_attempts - 1:
            # 마지막 시도에서도 실패하면 예외를 상위로 전파
            raise
        # 재시도 전 대기 (2^attempt 초씩 증가)
        # 예: 1초, 2초, 4초, 8초...
        await asyncio.sleep(self.config.retry_delay * (2 ** attempt))
```

## 복잡한 로직 설명 예시

### Before (영문)
```python
def _calculate_rate_limit(self, user_id: str, current_time: float) -> bool:
    bucket = self.buckets.get(user_id)
    if not bucket:
        bucket = TokenBucket(self.config.capacity, self.config.refill_rate)
        self.buckets[user_id] = bucket
    
    tokens_to_add = (current_time - bucket.last_update) * bucket.refill_rate
    bucket.tokens = min(bucket.capacity, bucket.tokens + tokens_to_add)
    bucket.last_update = current_time
    
    if bucket.tokens >= 1:
        bucket.tokens -= 1
        return True
    return False
```

### After (한글)
```python
def _calculate_rate_limit(self, user_id: str, current_time: float) -> bool:
    """
    토큰 버킷 알고리즘을 사용한 요청 속도 제한 계산
    
    토큰 버킷 알고리즘은 일정한 속도로 토큰이 충전되는 버킷을 사용하여
    버스트 트래픽을 허용하면서도 평균 처리율을 제한합니다.
    """
    # 사용자별 토큰 버킷 조회 또는 생성
    bucket = self.buckets.get(user_id)
    if not bucket:
        # 처음 요청하는 사용자의 경우 새 버킷 생성
        # capacity: 버킷의 최대 토큰 수 (버스트 크기)
        # refill_rate: 초당 충전되는 토큰 수
        bucket = TokenBucket(self.config.capacity, self.config.refill_rate)
        self.buckets[user_id] = bucket
    
    # 마지막 업데이트 이후 충전될 토큰 수 계산
    # 경과 시간 * 충전율 = 새로 추가될 토큰 수
    tokens_to_add = (current_time - bucket.last_update) * bucket.refill_rate
    
    # 토큰 충전 (최대 용량을 초과하지 않도록 제한)
    bucket.tokens = min(bucket.capacity, bucket.tokens + tokens_to_add)
    bucket.last_update = current_time
    
    # 요청 처리 가능 여부 확인
    if bucket.tokens >= 1:
        # 토큰이 있으면 1개 소비하고 요청 허용
        bucket.tokens -= 1
        return True
    
    # 토큰이 부족하면 요청 거부
    return False
```

## 비즈니스 로직 설명 예시

```python
async def _apply_search_filters(self, results: List[Dict], filters: Dict) -> List[Dict]:
    """
    검색 결과에 비즈니스 필터 적용
    
    비즈니스 요구사항:
    1. 신뢰도 점수가 0.5 미만인 결과는 제외
    2. 중복된 콘텐츠는 가장 높은 점수의 결과만 유지
    3. 블랙리스트에 있는 도메인의 결과는 제외
    4. 사용자 권한에 따라 특정 카테고리 필터링
    """
    filtered_results = []
    seen_content_hashes = set()
    
    for result in results:
        # 신뢰도 점수 필터링
        # 너무 낮은 점수의 결과는 사용자에게 도움이 되지 않음
        if result.get('score', 0) < 0.5:
            continue
            
        # 중복 콘텐츠 제거
        # 동일한 내용이 여러 소스에서 나온 경우 최고 점수만 유지
        content_hash = hashlib.md5(result['content'].encode()).hexdigest()
        if content_hash in seen_content_hashes:
            continue
        seen_content_hashes.add(content_hash)
        
        # 블랙리스트 도메인 필터링
        # 신뢰할 수 없는 소스나 스팸 도메인 제외
        if self._is_blacklisted_domain(result.get('source_url')):
            continue
            
        # 사용자 권한 기반 카테고리 필터링
        # 예: 일반 사용자는 'internal' 카테고리 접근 불가
        if not self._has_category_access(filters.get('user_role'), result.get('category')):
            continue
            
        filtered_results.append(result)
    
    return filtered_results
```

## 성능 최적화 주석 예시

```python
async def batch_retrieve(self, queries: List[str]) -> Dict[str, List[Dict]]:
    """
    여러 쿼리를 배치로 처리하여 성능 최적화
    
    성능 최적화 전략:
    1. 동시성: asyncio.gather()로 병렬 처리
    2. 배치 크기: 메모리와 처리 시간의 균형을 위해 최대 50개씩 처리
    3. 캐싱: 동일한 쿼리는 캐시에서 즉시 반환
    4. 연결 재사용: 단일 연결로 모든 쿼리 처리
    """
    results = {}
    
    # 배치 크기로 쿼리 분할
    # 너무 많은 동시 요청은 메모리 부족이나 타임아웃을 유발할 수 있음
    batch_size = 50
    for i in range(0, len(queries), batch_size):
        batch = queries[i:i + batch_size]
        
        # 배치 내 쿼리들을 병렬로 처리
        # gather()는 모든 코루틴이 완료될 때까지 대기
        batch_tasks = [
            self._retrieve_with_cache(query) 
            for query in batch
        ]
        batch_results = await asyncio.gather(*batch_tasks, return_exceptions=True)
        
        # 결과 수집 및 에러 처리
        for query, result in zip(batch, batch_results):
            if isinstance(result, Exception):
                logger.error(f"배치 검색 실패: {query}", error=result)
                results[query] = []
            else:
                results[query] = result
    
    return results
```

## TODO/FIXME 주석 예시

```python
# TODO(2024-01-XX): 캐시 무효화 전략 구현 필요
# 현재는 TTL만 사용하지만, 데이터 변경 시 즉시 무효화 필요

# FIXME: 대용량 결과 처리 시 메모리 사용량 최적화 필요
# 현재 구현은 모든 결과를 메모리에 로드하므로 OOM 위험 있음

# NOTE: 이 메서드는 내부적으로만 사용됨
# 외부 API로 노출하지 않도록 주의

# HACK: 임시로 동기 함수를 비동기로 변환
# 추후 네이티브 비동기 라이브러리로 교체 예정
```

## 에러 처리 주석 예시

```python
try:
    response = await self.client.search(query)
except httpx.TimeoutException:
    # 외부 API 타임아웃은 일시적일 수 있으므로 재시도 가능
    logger.warning(f"검색 타임아웃: {query}")
    raise RetrieverError("검색 시간이 초과되었습니다. 잠시 후 다시 시도해주세요.")
except httpx.HTTPStatusError as e:
    # HTTP 에러 코드에 따른 처리
    if e.response.status_code == 429:
        # Rate limit 에러는 사용자에게 명확히 전달
        raise RetrieverError("API 호출 한도를 초과했습니다. 잠시 후 다시 시도해주세요.")
    elif e.response.status_code >= 500:
        # 서버 에러는 일시적일 수 있음
        raise RetrieverError("검색 서비스에 일시적인 문제가 발생했습니다.")
    else:
        # 기타 에러는 상세 정보와 함께 전달
        raise RetrieverError(f"검색 중 오류 발생: {e.response.status_code}")
except Exception as e:
    # 예상치 못한 에러는 로깅 후 일반적인 메시지로 전달
    logger.error(f"예상치 못한 검색 오류", error=e, query=query)
    raise RetrieverError("검색 중 알 수 없는 오류가 발생했습니다.")
```