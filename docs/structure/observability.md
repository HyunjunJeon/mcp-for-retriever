# Observability 모듈 구조

관찰성 모듈은 분산 추적, 메트릭 수집, 에러 추적을 통해 시스템의 상태를 모니터링합니다.

## 모듈 구조

```mermaid
graph TD
    observability[observability/]
    observability --> telemetry[telemetry.py<br/>OpenTelemetry 설정]
    observability --> sentry_integration[sentry_integration.py<br/>Sentry 통합]
    observability --> init[__init__.py<br/>공개 인터페이스]
    
    telemetry --> tracer[Tracer<br/>분산 추적]
    telemetry --> meter[Meter<br/>메트릭]
    telemetry --> exporters[Exporters<br/>데이터 전송]
    
    sentry_integration --> error_capture[Error Capture<br/>에러 추적]
    sentry_integration --> performance[Performance<br/>성능 모니터링]
```

## 주요 컴포넌트

### 1. telemetry.py - OpenTelemetry 설정

```mermaid
classDiagram
    class TelemetrySetup {
        -service_name: str
        -service_version: str
        -otlp_endpoint: str
        -tracer_provider: TracerProvider
        -meter_provider: MeterProvider
        +setup() void
        +get_tracer() Tracer
        +get_meter() Meter
        +create_custom_metrics() void
        +shutdown() void
    }
    
    class CustomMetrics {
        +request_counter: Counter
        +request_duration: Histogram
        +active_users: UpDownCounter
        +retriever_status: Gauge
        +error_counter: Counter
    }
    
    TelemetrySetup --> CustomMetrics
```

#### OpenTelemetry 아키텍처

```mermaid
graph LR
    subgraph "Instrumentation"
        auto[자동 계측]
        manual[수동 계측]
    end
    
    subgraph "Telemetry API"
        traces[Traces]
        metrics[Metrics]
        logs[Logs]
    end
    
    subgraph "Telemetry SDK"
        processor[Processor]
        exporter[Exporter]
    end
    
    subgraph "Backends"
        jaeger[Jaeger]
        prometheus[Prometheus]
        otlp[OTLP Collector]
    end
    
    auto --> traces
    manual --> metrics
    traces --> processor
    metrics --> processor
    processor --> exporter
    exporter --> jaeger
    exporter --> prometheus
    exporter --> otlp
```

#### 자동 계측 라이브러리

```python
# 자동으로 계측되는 라이브러리
INSTRUMENTED_LIBRARIES = {
    "FastAPI": FastAPIInstrumentor,
    "HTTPX": HTTPXClientInstrumentor,
    "AsyncPG": AsyncPGInstrumentor,
    "Redis": RedisInstrumentor
}
```

#### 커스텀 메트릭

```python
# MCP 작업을 위한 커스텀 메트릭
CUSTOM_METRICS = {
    "mcp.requests.total": Counter,      # 총 요청 수
    "mcp.request.duration": Histogram,   # 요청 처리 시간
    "mcp.users.active": UpDownCounter,   # 활성 사용자 수
    "mcp.retriever.status": Gauge,       # 리트리버 상태
    "mcp.errors.total": Counter          # 에러 수
}
```

### 2. sentry_integration.py - Sentry 통합

```mermaid
classDiagram
    class SentryIntegration {
        -dsn: str
        -environment: str
        -release: str
        -traces_sample_rate: float
        -profiles_sample_rate: float
        +setup() void
        +set_user_context(user_id, email, username) void
        +set_request_context(request_id, method, tool_name) void
        +capture_error(error, level, extra_context) void
        +create_transaction(name, op) Transaction
        +add_breadcrumb(message, category, level, data) void
        +flush(timeout) void
        +shutdown() void
    }
    
    class DataSanitizer {
        -sensitive_keys: List[str]
        +sanitize_data(data) Any
        +before_send(event, hint) Optional[dict]
        +before_send_transaction(event, hint) Optional[dict]
    }
    
    SentryIntegration --> DataSanitizer
```

#### Sentry 데이터 흐름

```mermaid
sequenceDiagram
    participant App
    participant Sentry
    participant Filter
    participant Backend
    
    App->>Sentry: capture_exception()
    Sentry->>Filter: before_send()
    Filter->>Filter: 민감정보 제거
    Filter->>Filter: 이벤트 필터링
    Filter-->>Sentry: 처리된 이벤트
    Sentry->>Backend: 전송
    
    App->>Sentry: set_context()
    Sentry->>Sentry: 컨텍스트 저장
    
    App->>Sentry: add_breadcrumb()
    Sentry->>Sentry: 브레드크럼 추가
```

#### 민감정보 처리

```python
SENSITIVE_PATTERNS = {
    "headers": ["authorization", "cookie", "x-api-key"],
    "data": ["password", "token", "api_key", "secret"],
    "user": ["email", "phone", "ssn"]
}
```

### 3. 통합 미들웨어

```mermaid
graph TD
    Request[요청] --> MW[ObservabilityMiddleware]
    
    MW --> StartSpan[스팬 시작]
    StartSpan --> SetAttrs[속성 설정]
    SetAttrs --> SetBaggage[Baggage 설정]
    
    SetBaggage --> Handler[핸들러 실행]
    
    Handler --> Success{성공?}
    Success -->|Yes| RecordSuccess[성공 기록]
    Success -->|No| RecordError[에러 기록]
    
    RecordSuccess --> EndSpan[스팬 종료]
    RecordError --> CaptureError[Sentry 캡처]
    CaptureError --> EndSpan
    
    EndSpan --> Response[응답]
```

## 추적 컨텍스트 전파

### W3C Trace Context

```mermaid
graph LR
    subgraph "HTTP Headers"
        traceparent[traceparent<br/>버전-추적ID-스팬ID-플래그]
        tracestate[tracestate<br/>벤더별 추가 정보]
    end
    
    subgraph "컨텍스트 정보"
        trace_id[Trace ID<br/>128-bit]
        span_id[Span ID<br/>64-bit]
        flags[Trace Flags<br/>8-bit]
    end
    
    traceparent --> trace_id
    traceparent --> span_id
    traceparent --> flags
```

### Baggage 전파

```python
# 사용자 정보를 Baggage로 전파
baggage.set_baggage("user.id", user_id)
baggage.set_baggage("user.type", user_type)
baggage.set_baggage("tenant.id", tenant_id)
```

## 메트릭 수집

### Prometheus 메트릭 형식

```promql
# 카운터
mcp_requests_total{method="tools/call", tool="search_web", status="success"} 1234

# 히스토그램
mcp_request_duration_seconds_bucket{le="0.1"} 456
mcp_request_duration_seconds_bucket{le="0.5"} 789
mcp_request_duration_seconds_sum 123.45
mcp_request_duration_seconds_count 1000

# 게이지
mcp_retriever_status{retriever="tavily", status="connected"} 1
mcp_active_users 42
```

### 메트릭 엔드포인트

```python
@app.get("/metrics")
async def metrics():
    """Prometheus 메트릭 엔드포인트"""
    return Response(
        generate_latest(),
        media_type="text/plain; version=0.0.4"
    )
```

## 에러 추적

### 에러 분류

```mermaid
graph TD
    Error[에러 발생]
    Error --> Type{에러 유형}
    
    Type -->|Expected| Expected[예상된 에러]
    Type -->|Unexpected| Unexpected[예상치 못한 에러]
    
    Expected --> Business[비즈니스 에러]
    Expected --> Validation[검증 에러]
    Expected --> RateLimit[속도 제한]
    
    Unexpected --> System[시스템 에러]
    Unexpected --> Integration[통합 에러]
    
    Business --> Log[로그만]
    Validation --> Log
    RateLimit --> Log
    
    System --> Sentry[Sentry 전송]
    Integration --> Sentry
```

### 에러 컨텍스트

```python
# 에러와 함께 캡처되는 컨텍스트
ERROR_CONTEXT = {
    "user": {
        "id": "user-123",
        "email": "user@example.com",
        "role": "user"
    },
    "request": {
        "id": "req-456",
        "method": "tools/call",
        "tool": "search_web"
    },
    "system": {
        "version": "1.0.0",
        "environment": "production",
        "host": "mcp-server-01"
    }
}
```

## 성능 모니터링

### 트랜잭션 추적

```python
# Sentry 성능 트랜잭션
with sentry_sdk.start_transaction(
    op="mcp.request",
    name="tools/call:search_web"
) as transaction:
    with transaction.start_child(
        op="retriever.search",
        description="Tavily search"
    ) as span:
        # 검색 실행
        results = await retriever.retrieve(query)
```

### 성능 메트릭

- **응답 시간**: P50, P75, P95, P99
- **처리량**: 초당 요청 수 (RPS)
- **에러율**: 실패한 요청 비율
- **포화도**: CPU, 메모리 사용률

## 대시보드 및 알림

### Grafana 대시보드

```mermaid
graph LR
    subgraph "대시보드"
        overview[Overview]
        requests[Requests]
        errors[Errors]
        performance[Performance]
    end
    
    subgraph "패널"
        rps[RPS 그래프]
        latency[레이턴시 히스토그램]
        error_rate[에러율 게이지]
        active_users[활성 사용자]
    end
    
    overview --> rps
    requests --> latency
    errors --> error_rate
    performance --> active_users
```

### 알림 규칙

```yaml
alerts:
  - name: HighErrorRate
    condition: rate(mcp_errors_total[5m]) > 0.05
    severity: warning
    
  - name: HighLatency
    condition: histogram_quantile(0.95, mcp_request_duration_seconds) > 1
    severity: warning
    
  - name: RetrieverDown
    condition: mcp_retriever_status == 0
    severity: critical
```

## 환경 변수 설정

```bash
# OpenTelemetry
OTEL_SERVICE_NAME=mcp-retriever
OTEL_SERVICE_VERSION=1.0.0
OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4317
OTEL_EXPORTER_OTLP_HEADERS=api-key=your-key
OTEL_SDK_DISABLED=false

# Sentry
SENTRY_DSN=https://xxx@xxx.ingest.sentry.io/xxx
SENTRY_ENVIRONMENT=production
SENTRY_RELEASE=1.0.0
SENTRY_TRACES_SAMPLE_RATE=0.1
SENTRY_PROFILES_SAMPLE_RATE=0.1

# 메트릭
PROMETHEUS_PORT=9090
METRICS_PREFIX=mcp
```

## 문제 해결

### 추적이 표시되지 않을 때

1. OTLP 엔드포인트 연결 확인
2. 샘플링 비율 확인
3. 서비스 이름 설정 확인

### 메트릭이 수집되지 않을 때

1. Prometheus 스크레이프 설정 확인
2. 메트릭 엔드포인트 접근성 확인
3. 메트릭 이름 규칙 확인

### Sentry 이벤트가 전송되지 않을 때

1. DSN 설정 확인
2. 네트워크 연결 확인
3. before_send 필터 확인