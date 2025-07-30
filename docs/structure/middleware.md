# Middleware 모듈 구조

미들웨어 스택은 모든 MCP 요청을 처리하는 파이프라인을 구성합니다.

## 모듈 구조

```mermaid
graph TD
    middleware[middleware/]
    middleware --> auth[auth.py<br/>인증 검증]
    middleware --> logging[logging.py<br/>요청/응답 로깅]
    middleware --> rate_limit[rate_limit.py<br/>속도 제한]
    middleware --> validation[validation.py<br/>입력 검증]
    middleware --> metrics[metrics.py<br/>메트릭 수집]
    middleware --> error_handler[error_handler.py<br/>에러 처리]
    middleware --> observability[observability.py<br/>분산 추적]
```

## 미들웨어 실행 순서

```mermaid
graph LR
    Request[요청] --> MW1[Observability<br/>추적 시작]
    MW1 --> MW2[Authentication<br/>인증 확인]
    MW2 --> MW3[Logging<br/>요청 로깅]
    MW3 --> MW4[Validation<br/>입력 검증]
    MW4 --> MW5[RateLimit<br/>속도 제한]
    MW5 --> MW6[Metrics<br/>메트릭 수집]
    MW6 --> MW7[ErrorHandler<br/>에러 처리]
    MW7 --> Handler[핸들러<br/>비즈니스 로직]
    
    Handler --> MW7R[ErrorHandler<br/>에러 캡처]
    MW7R --> MW6R[Metrics<br/>메트릭 기록]
    MW6R --> MW5R[RateLimit<br/>사용량 업데이트]
    MW5R --> MW4R[Validation<br/>응답 검증]
    MW4R --> MW3R[Logging<br/>응답 로깅]
    MW3R --> MW2R[Authentication<br/>컨텍스트 정리]
    MW2R --> MW1R[Observability<br/>추적 종료]
    MW1R --> Response[응답]
```

## 각 미들웨어 상세

### 1. auth.py - 인증 미들웨어

```mermaid
classDiagram
    class AuthMiddleware {
        -jwt_service: JWTService
        -user_service: UserService
        -internal_api_key: str
        -public_methods: List[str]
        +__call__(request, call_next)
        -_extract_token(request) str
        -_validate_jwt(token) dict
        -_validate_api_key(token) bool
        -_check_permissions(user, method) bool
    }
    
    class AuthenticationError {
        +code = -32040
        +message: str
    }
    
    class AuthorizationError {
        +code = -32041
        +message: str
    }
```

**주요 기능:**
- Bearer 토큰 추출
- JWT 토큰 검증
- 내부 API 키 검증
- 사용자 컨텍스트 주입
- 메서드별 권한 확인

### 2. logging.py - 로깅 미들웨어

```mermaid
graph TD
    subgraph "LoggingMiddleware"
        request_log[요청 로깅]
        response_log[응답 로깅]
        error_log[에러 로깅]
        
        subgraph "민감정보 처리"
            sanitize[민감정보 제거]
            redact[토큰 마스킹]
            truncate[대용량 데이터 축약]
        end
    end
    
    request_log --> sanitize
    response_log --> sanitize
    sanitize --> redact
    redact --> truncate
```

**주요 기능:**
- 구조화된 로깅 (structlog)
- 민감정보 자동 제거
- 요청/응답 시간 측정
- 대용량 페이로드 축약
- 요청 ID 추적

### 3. rate_limit.py - 속도 제한 미들웨어

```mermaid
graph LR
    subgraph "RateLimitMiddleware"
        bucket[Token Bucket]
        config[설정]
        
        subgraph "제한 정책"
            per_user[사용자별]
            per_ip[IP별]
            per_method[메서드별]
        end
    end
    
    subgraph "알고리즘"
        check[토큰 확인]
        consume[토큰 소비]
        refill[토큰 충전]
    end
    
    bucket --> check
    check --> consume
    refill --> bucket
```

**Token Bucket 알고리즘:**
```python
class TokenBucket:
    capacity: int = 60      # 버킷 크기
    refill_rate: float = 1.0  # 초당 충전율
    burst_size: int = 10    # 버스트 허용량
```

**주요 기능:**
- 사용자별 속도 제한
- 버스트 트래픽 허용
- 분/시간 단위 제한
- 우아한 제한 (Graceful degradation)

### 4. validation.py - 검증 미들웨어

```mermaid
classDiagram
    class ValidationMiddleware {
        -validators: Dict[str, Validator]
        +__call__(request, call_next)
        -_validate_jsonrpc(request)
        -_validate_method(method)
        -_validate_params(method, params)
        -_validate_permissions(user, method)
    }
    
    class Validator {
        <<interface>>
        +validate(data: Any) bool
    }
    
    class SchemaValidator {
        -schema: Dict
        +validate(data: Any) bool
    }
    
    class TypeValidator {
        -expected_type: Type
        +validate(data: Any) bool
    }
    
    Validator <|-- SchemaValidator
    Validator <|-- TypeValidator
```

**검증 단계:**
1. JSON-RPC 형식 검증
2. 메서드 존재 여부 확인
3. 매개변수 타입 검증
4. 필수 매개변수 확인
5. 권한 검증 (RBAC)

### 5. metrics.py - 메트릭 미들웨어

```mermaid
graph TD
    subgraph "MetricsMiddleware"
        counters[카운터]
        histograms[히스토그램]
        gauges[게이지]
        
        subgraph "메트릭 유형"
            request_count[요청 수]
            request_duration[응답 시간]
            error_count[에러 수]
            active_requests[활성 요청]
            tool_usage[도구 사용량]
        end
    end
    
    counters --> request_count
    counters --> error_count
    histograms --> request_duration
    gauges --> active_requests
    counters --> tool_usage
```

**수집 메트릭:**
- 총 요청 수 (메서드별, 사용자별)
- 응답 시간 분포 (P50, P95, P99)
- 에러율 (타입별)
- 동시 요청 수
- 도구별 사용 통계

### 6. error_handler.py - 에러 처리 미들웨어

```mermaid
graph TD
    Error[에러 발생]
    Error --> Catch[에러 캐치]
    
    Catch --> Type{에러 타입?}
    Type -->|MCPError| Format1[JSON-RPC 에러 포맷]
    Type -->|ValidationError| Format2[검증 에러 포맷]
    Type -->|Exception| Format3[일반 에러 포맷]
    
    Format1 --> Log[에러 로깅]
    Format2 --> Log
    Format3 --> Log
    
    Log --> Response[에러 응답]
```

**에러 처리 전략:**
```python
ERROR_MAPPINGS = {
    AuthenticationError: -32040,
    AuthorizationError: -32041,
    ValidationError: -32602,
    RateLimitError: -32045,
    RetrieverError: -32603
}
```

### 7. observability.py - 관찰성 미들웨어

```mermaid
graph LR
    subgraph "ObservabilityMiddleware"
        tracing[분산 추적]
        error_tracking[에러 추적]
        performance[성능 모니터링]
        
        subgraph "통합"
            opentelemetry[OpenTelemetry]
            sentry[Sentry]
        end
    end
    
    tracing --> opentelemetry
    error_tracking --> sentry
    performance --> opentelemetry
    performance --> sentry
```

**주요 기능:**
- 분산 추적 컨텍스트 전파
- 자동 스팬 생성
- 에러 자동 캡처
- 성능 트랜잭션 추적
- Baggage를 통한 메타데이터 전파

## 미들웨어 설정

```python
class MiddlewareConfig:
    # 인증
    jwt_secret: str
    internal_api_key: str
    public_methods: List[str] = ["tools/list"]
    
    # 로깅
    log_level: str = "INFO"
    sanitize_keys: List[str] = ["password", "token", "api_key"]
    max_payload_size: int = 10000
    
    # 속도 제한
    rate_limit_per_minute: int = 60
    rate_limit_per_hour: int = 1000
    burst_size: int = 10
    
    # 메트릭
    enable_metrics: bool = True
    metrics_prefix: str = "mcp"
    
    # 관찰성
    enable_tracing: bool = True
    enable_sentry: bool = True
    trace_all_requests: bool = False
```

## 미들웨어 통합

```python
# server.py에서 미들웨어 스택 구성
def create_middleware_stack(handler):
    # 역순으로 래핑 (가장 바깥쪽부터)
    handler = ErrorHandlingMiddleware()(handler)
    handler = MetricsMiddleware()(handler)
    handler = RateLimitMiddleware(config)(handler)
    handler = ValidationMiddleware()(handler)
    handler = LoggingMiddleware()(handler)
    handler = AuthMiddleware(jwt_service, user_service)(handler)
    handler = ObservabilityMiddleware()(handler)
    return handler
```

## 커스텀 미들웨어 작성

### 미들웨어 인터페이스

```python
from typing import Callable, Dict, Any

class CustomMiddleware:
    """커스텀 미들웨어 템플릿"""
    
    def __init__(self, config: Any):
        self.config = config
        
    async def __call__(
        self, 
        request: Dict[str, Any], 
        call_next: Callable
    ) -> Dict[str, Any]:
        # 요청 전처리
        request = self.pre_process(request)
        
        try:
            # 다음 미들웨어 호출
            response = await call_next(request)
            
            # 응답 후처리
            response = self.post_process(response)
            
            return response
            
        except Exception as e:
            # 에러 처리
            return self.handle_error(e)
```

## 성능 고려사항

### 1. 비동기 처리
- 모든 미들웨어는 비동기로 구현
- I/O 작업 시 await 사용

### 2. 컨텍스트 전파
- 요청 객체를 통한 컨텍스트 전달
- 불필요한 복사 최소화

### 3. 조기 종료
- 인증 실패 시 즉시 반환
- 불필요한 미들웨어 실행 방지

### 4. 캐싱
- 권한 확인 결과 캐싱
- JWT 디코딩 결과 캐싱

## 모니터링 및 디버깅

### 로그 상관관계
```
request_id=abc123 method=tools/call user_id=user456 duration_ms=150
```

### 추적 정보
```
trace_id=0123456789abcdef span_id=fedcba9876543210
```

### 메트릭 대시보드
- Grafana를 통한 시각화
- Prometheus 메트릭 수집
- 실시간 에러율 모니터링