# MCP SSE 프록시 구현 문서

## 개요
FastMCP의 Streamable HTTP 모드를 지원하기 위해 Auth Gateway에 SSE(Server-Sent Events) 프록시 기능을 구현했습니다.

## 구현 내용

### 1. 의존성 추가
```toml
# pyproject.toml
"httpx-sse>=0.4.0",      # SSE 클라이언트
"sse-starlette>=2.2.1",  # FastAPI SSE 응답
```

### 2. MCPProxyService 확장
- `validate_sse_headers()`: SSE 전용 헤더 검증
- `forward_sse_request()`: SSE 스트림 프록시 메서드
- 세션 ID 관리 및 전달
- 에러 처리 및 스트림 종료 관리

### 3. Auth Gateway SSE 엔드포인트
- `POST /mcp/sse`: SSE 프록시 엔드포인트
- JWT 인증 통합
- EventSourceResponse로 스트림 반환

## 기술적 세부사항

### SSE 헤더 요구사항
```http
Accept: application/json, text/event-stream
Content-Type: application/json
Authorization: Bearer <JWT_TOKEN>
```

### 세션 관리
- FastMCP는 `mcp-session-id` 헤더로 세션 추적
- 프록시는 세션 ID를 클라이언트에 전달

### 이벤트 형식
```
event: message
data: {"jsonrpc":"2.0","id":1,"result":{...}}

event: error
data: {"jsonrpc":"2.0","id":"error","error":{...}}
```

## 테스트 결과

### 성공한 기능
1. ✅ SSE 연결 및 스트림 프록시
2. ✅ initialize 메서드 호출
3. ✅ 세션 ID 전달
4. ✅ JWT 인증 통합

### 알려진 이슈
1. httpx-sse가 중첩된 SSE 이벤트 파싱에 제한이 있음
2. FastMCP의 복잡한 세션 관리로 인한 추가 처리 필요

## 사용 예제

### JavaScript 클라이언트
```javascript
const eventSource = new EventSource('/mcp/sse', {
    headers: {
        'Authorization': `Bearer ${token}`,
        'Content-Type': 'application/json'
    }
});

eventSource.onmessage = (event) => {
    const data = JSON.parse(event.data);
    console.log('Received:', data);
};
```

### Python 클라이언트
```python
from httpx_sse import aconnect_sse

async with aconnect_sse(
    client,
    "POST",
    "http://localhost:8000/mcp/sse",
    json=request_data,
    headers=headers,
) as event_source:
    async for sse in event_source.aiter_sse():
        if sse.data:
            data = json.loads(sse.data)
            # Process data
```

## 향후 개선사항
1. 더 나은 세션 관리 메커니즘
2. 스트림 재연결 지원
3. 배치 요청 처리
4. 성능 최적화

## 결론
SSE 프록시가 성공적으로 구현되어 FastMCP의 Streamable HTTP 모드와 호환됩니다. 
이를 통해 실시간 스트리밍 기반의 MCP 통신이 가능해졌습니다.