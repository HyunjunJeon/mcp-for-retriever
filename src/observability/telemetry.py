"""
OpenTelemetry 기반 텔레메트리 설정 및 구성

이 모듈은 MCP 서버의 관찰 가능성을 위한 OpenTelemetry 기반 텔레메트리 시스템을 구현합니다.
분산 추적, 메트릭 수집, 로그 집계를 통해 시스템의 상태와 성능을 모니터링합니다.

주요 기능:
    분산 추적 (Distributed Tracing):
        - 스패(Span) 생성 및 관리
        - 추적 컨텍스트 전파
        - OTLP 및 콘솔 익스포터 지원
        - Jaeger/Zipkin 호환성
        
    메트릭 수집 (Metrics Collection):
        - Prometheus 메트릭 오엄수집
        - 커스텀 메트릭 정의
        - 카운터, 히스토그램, 게이지 지원
        - OTLP 메트릭 익스포터
        
    자동 계측:
        - FastAPI 요청/응답 추적
        - HTTPX 클라이언트 호출 추적
        - AsyncPG 데이터베이스 연산 추적
        - Redis 캐시 연산 추적
        
    컨텍스트 전파:
        - Baggage API를 통한 메타데이터 전파
        - W3C Trace Context 표준 지원
        - 마이크로서비스간 컨텍스트 전달

아키텍처:
    - 싱글톤 패턴으로 전역 텔레메트리 인스턴스 관리
    - 다양한 내보내기(Exporter) 지원 (OTLP, Prometheus, Console)
    - 리소스 기반 서비스 식별
    - Graceful shutdown 지원

환경 변수:
    - OTEL_EXPORTER_OTLP_ENDPOINT: OTLP 콜렉터 엔드포인트
    - ENVIRONMENT: 배포 환경 (development, staging, production)
    - OTEL_SERVICE_NAME: 서비스 이름 오버라이드

작성일: 2024-01-30
"""

import os
from typing import Optional, Dict, Any
import structlog

from opentelemetry import trace, metrics, baggage
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import (
    BatchSpanProcessor,
    ConsoleSpanExporter,
)
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.resources import Resource, SERVICE_NAME, SERVICE_VERSION
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.prometheus import PrometheusMetricReader
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from opentelemetry.instrumentation.asyncpg import AsyncPGInstrumentor
from opentelemetry.instrumentation.redis import RedisInstrumentor
from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator
from opentelemetry.propagate import set_global_textmap

logger = structlog.get_logger(__name__)


class TelemetrySetup:
    """
    OpenTelemetry 계측 설정 및 관리 클래스
    
    MCP 서버의 관찰 가능성을 위한 전체적인 텔레메트리 시스템을 설정하고 관리합니다.
    분산 추적, 메트릭 수집, 라이브러리 자동 계측을 통합적으로 제공합니다.
    
    주요 기능:
        초기화 및 설정:
            - 서비스 리소스 정의
            - 추적 및 메트릭 프로바이더 설정
            - 내보내기(Exporter) 구성
            - 전역 전파 설정
            
        자동 계측:
            - FastAPI 웹 프레임워크 계측
            - HTTPX HTTP 클라이언트 계측
            - AsyncPG PostgreSQL 데이터베이스 계측
            - Redis 캐시 계측
            
        커스턴 메트릭:
            - MCP 요청 수 및 응답 시간
            - 활성 사용자 수
            - 리트리버 연결 상태
            - 에러 수 및 유형별 분류
    """
    
    def __init__(
        self,
        service_name: str = "mcp-retriever",
        service_version: str = "1.0.0",
        otlp_endpoint: Optional[str] = None,
        enable_console_export: bool = False,
        enable_prometheus: bool = True,
        custom_attributes: Optional[Dict[str, Any]] = None
    ):
        """
        텔레메트리 시스템 초기화
        
        Args:
            service_name (str): 서비스 이름
                예: "mcp-retriever", "auth-gateway"
                리소스 식별자로 사용됨
                
            service_version (str): 서비스 버전
                예: "1.0.0", "2.1.0-beta"
                배포 버전 추적용
                
            otlp_endpoint (Optional[str]): OTLP 콜렉터 엔드포인트
                예: "localhost:4317", "https://api.honeycomb.io"
                None이면 OTEL_EXPORTER_OTLP_ENDPOINT 환경변수 사용
                
            enable_console_export (bool): 콘솔로 스패 출력 여부
                True: 개발 환경에서 디버깅용
                False: production 환경 기본값
                
            enable_prometheus (bool): Prometheus 메트릭 오엄 여부
                True: /metrics 엔드포인트에서 메트릭 제공
                False: Prometheus 비활성화
                
            custom_attributes (Optional[Dict[str, Any]]): 추가 리소스 속성
                예: {"region": "us-east-1", "cluster": "prod"}
                
        초기화 과정:
            - 설정값 저장 및 검증
            - 환경변수에서 OTLP 엔드포인트 확인
            - 프로바이더 인스턴스 초기 상태 설정
            - 커스텀 리소스 속성 도입
        """
        self.service_name = service_name
        self.service_version = service_version
        self.otlp_endpoint = otlp_endpoint or os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT")
        self.enable_console_export = enable_console_export
        self.enable_prometheus = enable_prometheus
        self.custom_attributes = custom_attributes or {}
        
        self._tracer_provider: Optional[TracerProvider] = None
        self._meter_provider: Optional[MeterProvider] = None
        self._tracer: Optional[trace.Tracer] = None
        self._meter: Optional[metrics.Meter] = None
    
    def setup(self):
        """
        OpenTelemetry 프로바이더 및 계측 설정
        
        텔레메트리 시스템의 모든 구성 요소를 초기화하고 활성화합니다.
        이 메서드는 애플리케이션 시작 시 한 번만 호출되어야 합니다.
        
        설정 순서:
            1. 리소스 생성: 서비스 메타데이터 정의
            2. 추적 설정: TracerProvider 및 Exporter 구성
            3. 메트릭 설정: MeterProvider 및 Reader 구성
            4. 전파 설정: W3C Trace Context 표준 설정
            5. 라이브러리 계측: 자동 계측 활성화
            
        옵션별 기능:
            - OTLP 엔드포인트 설정 시 Jaeger/OTEL Collector 연동
            - Prometheus 활성화 시 /metrics 엔드포인트 제공
            - 콘솔 내보내기 활성화 시 디버깅 지원
            
        에러 처리:
            - OTLP 연결 실패 시 에러 로깅 후 계속 진행
            - 계측 라이브러리 연동 실패 시 graceful degradation
        """
        logger.info(
            "Setting up OpenTelemetry",
            service_name=self.service_name,
            service_version=self.service_version,
            otlp_endpoint=self.otlp_endpoint
        )
        
        # 리소스 생성
        resource = Resource.create({
            SERVICE_NAME: self.service_name,
            SERVICE_VERSION: self.service_version,
            "deployment.environment": os.getenv("ENVIRONMENT", "development"),
            **self.custom_attributes
        })
        
        # 추적 설정
        self._setup_tracing(resource)
        
        # 메트릭 설정
        self._setup_metrics(resource)
        
        # 전파 설정
        set_global_textmap(TraceContextTextMapPropagator())
        
        # 라이브러리 계측
        self._instrument_libraries()
        
        logger.info("OpenTelemetry setup complete")
    
    def _setup_tracing(self, resource: Resource):
        """Setup tracing provider and exporters."""
        self._tracer_provider = TracerProvider(resource=resource)
        
        # Add console exporter if enabled
        if self.enable_console_export:
            console_exporter = ConsoleSpanExporter()
            self._tracer_provider.add_span_processor(
                BatchSpanProcessor(console_exporter)
            )
        
        # Add OTLP exporter if endpoint is configured
        if self.otlp_endpoint:
            try:
                otlp_exporter = OTLPSpanExporter(
                    endpoint=self.otlp_endpoint,
                    insecure=True  # Use secure=False for local development
                )
                self._tracer_provider.add_span_processor(
                    BatchSpanProcessor(otlp_exporter)
                )
                logger.info(f"OTLP trace exporter configured: {self.otlp_endpoint}")
            except Exception as e:
                logger.error(f"Failed to setup OTLP trace exporter: {e}")
        
        # Set as global tracer provider
        trace.set_tracer_provider(self._tracer_provider)
        self._tracer = trace.get_tracer(self.service_name, self.service_version)
    
    def _setup_metrics(self, resource: Resource):
        """Setup metrics provider and exporters."""
        readers = []
        
        # Add Prometheus reader if enabled
        if self.enable_prometheus:
            prometheus_reader = PrometheusMetricReader()
            readers.append(prometheus_reader)
            logger.info("Prometheus metrics enabled at /metrics")
        
        # Add OTLP exporter if endpoint is configured
        if self.otlp_endpoint:
            try:
                otlp_exporter = OTLPMetricExporter(
                    endpoint=self.otlp_endpoint,
                    insecure=True
                )
                readers.append(otlp_exporter)
                logger.info(f"OTLP metric exporter configured: {self.otlp_endpoint}")
            except Exception as e:
                logger.error(f"Failed to setup OTLP metric exporter: {e}")
        
        if readers:
            self._meter_provider = MeterProvider(
                resource=resource,
                metric_readers=readers
            )
            metrics.set_meter_provider(self._meter_provider)
            self._meter = metrics.get_meter(self.service_name, self.service_version)
    
    def _instrument_libraries(self):
        """Instrument third-party libraries."""
        # Instrument FastAPI
        FastAPIInstrumentor().instrument(
            tracer_provider=self._tracer_provider,
            excluded_urls="/health,/metrics"
        )
        
        # Instrument HTTPX
        HTTPXClientInstrumentor().instrument(
            tracer_provider=self._tracer_provider
        )
        
        # Instrument AsyncPG
        AsyncPGInstrumentor().instrument(
            tracer_provider=self._tracer_provider
        )
        
        # Instrument Redis
        RedisInstrumentor().instrument(
            tracer_provider=self._tracer_provider
        )
        
        logger.info("Instrumented libraries: FastAPI, HTTPX, AsyncPG, Redis")
    
    def get_tracer(self) -> trace.Tracer:
        """Get the configured tracer."""
        if not self._tracer:
            raise RuntimeError("Telemetry not setup. Call setup() first.")
        return self._tracer
    
    def get_meter(self) -> metrics.Meter:
        """Get the configured meter."""
        if not self._meter:
            raise RuntimeError("Telemetry not setup. Call setup() first.")
        return self._meter
    
    def create_custom_metrics(self):
        """Create custom metrics for the application."""
        meter = self.get_meter()
        
        # Request counter by tool
        self.request_counter = meter.create_counter(
            name="mcp.requests.total",
            description="Total number of MCP requests",
            unit="1"
        )
        
        # Request duration histogram
        self.request_duration = meter.create_histogram(
            name="mcp.request.duration",
            description="MCP request duration",
            unit="ms"
        )
        
        # Active users gauge
        self.active_users = meter.create_up_down_counter(
            name="mcp.users.active",
            description="Number of active users",
            unit="1"
        )
        
        # Retriever connection status
        self.retriever_status = meter.create_gauge(
            name="mcp.retriever.status",
            description="Retriever connection status (1=connected, 0=disconnected)",
            unit="1"
        )
        
        # Error counter by type
        self.error_counter = meter.create_counter(
            name="mcp.errors.total",
            description="Total number of errors by type",
            unit="1"
        )
        
        logger.info("Custom metrics created")
    
    def shutdown(self):
        """Shutdown telemetry providers."""
        if self._tracer_provider:
            self._tracer_provider.shutdown()
        if self._meter_provider:
            self._meter_provider.shutdown()
        logger.info("OpenTelemetry shutdown complete")


# Global telemetry instance
_telemetry: Optional[TelemetrySetup] = None


def get_telemetry() -> TelemetrySetup:
    """
    전역 텔레메트리 인스턴스 조회
    
    싱글톤 패턴으로 전역에서 단일한 TelemetrySetup 인스턴스를 공유합니다.
    최초 호출 시 인스턴스를 생성하고 이후에는 동일한 인스턴스를 반환합니다.
    
    Returns:
        TelemetrySetup: 전역 텔레메트리 인스턴스
            - 기본 설정으로 초기화됨
            - setup() 메서드를 호출하여 활성화 필요
            
    사용 패턴:
        - 애플리케이션 전반에서 동일한 텔레메트리 설정 공유
        - 다양한 모듈에서 일관된 관찰 가능성 제공
        - 리소스 효율적 관리
    """
    global _telemetry
    if not _telemetry:
        _telemetry = TelemetrySetup()
    return _telemetry


def get_tracer(name: Optional[str] = None) -> trace.Tracer:
    """
    추적 인스턴스 조회
    
    전역 텔레메트리 설정에서 추적기를 가져옵니다.
    아직 설정되지 않땘다면 자동으로 초기화를 수행합니다.
    
    Args:
        name (Optional[str]): 추적기 이름
            None: 전역 텔레메트리의 기본 추적기 사용
            문자열: 특정 이름의 추적기 생성
            예: "__main__", "src.retriever.tavily"
            
    Returns:
        trace.Tracer: OpenTelemetry 추적기 인스턴스
            - 스패(Span) 생성 및 관리 기능
            - 컨텍스트 매개자 및 이벤트 추가 기능
            
    사용 예시:
        ```python
        tracer = get_tracer(__name__)
        with tracer.start_as_current_span("database_query"):
            # 추적하고 싶은 작업 수행
            result = await db.query("SELECT * FROM users")
        ```
        
    예외 처리:
        - 텔레메트리 설정 실패 시 자동 초기화 시도
        - 설정 실패 시 RuntimeError 발생
    """
    telemetry = get_telemetry()
    if not telemetry._tracer:
        telemetry.setup()
    
    if name:
        return trace.get_tracer(name)
    return telemetry.get_tracer()


def record_metric(
    name: str,
    value: float,
    attributes: Optional[Dict[str, Any]] = None,
    metric_type: str = "counter"
):
    """
    커스텔 메트릭 기록
    
    애플리케이션에서 사용자 정의 메트릭을 기록합니다.
    지원되는 메트릭 유형에 따라 적절한 계측기를 생성하거나 사용합니다.
    
    Args:
        name (str): 메트릭 이름
            예: "mcp.request.count", "auth.login.success"
            도메인 기반 명명 규칙 추천
            
        value (float): 메트릭 값
            counter: 증가량 (양수)
            histogram: 측정값 (임의 실수)
            gauge: 현재 상태값 (임의 실수)
            
        attributes (Optional[Dict[str, Any]]): 메트릭 속성
            예: {"method": "POST", "status_code": 200}
            차원별 데이터 분석용
            
        metric_type (str): 메트릭 유형
            "counter": 누적 카운터 (기본값)
            "histogram": 값 분포 추적
            "gauge": 현재 상태 값 (제한적 지원)
            
    사용 예시:
        ```python
        # 요청 수 카운트
        record_metric(
            "http.requests.total",
            1,
            {"method": "GET", "status": "200"},
            "counter"
        )
        
        # 응답 시간 측정
        record_metric(
            "http.request.duration",
            response_time_ms,
            {"endpoint": "/api/search"},
            "histogram"
        )
        ```
        
    주의사항:
        - gauge 메트릭은 Observable Gauge로 콜백 기반 구현 필요
        - 대량의 카디널리티 속성은 성능에 영향 가능
        - 메트릭 이름은 전역에서 일관성 유지 필요
    """
    telemetry = get_telemetry()
    meter = telemetry.get_meter()
    
    if metric_type == "counter":
        counter = meter.create_counter(name)
        counter.add(value, attributes=attributes)
    elif metric_type == "histogram":
        histogram = meter.create_histogram(name)
        histogram.record(value, attributes=attributes)
    elif metric_type == "gauge":
        # For gauges, we use an observable gauge with a callback
        logger.warning(f"Gauge metrics require observable callback: {name}")


def set_baggage(key: str, value: str):
    """
    컨텍스트 전파를 위한 Baggage 항목 설정
    
    분산 시스템에서 스패 경계를 넘나 매개변수를 전파합니다.
    HTTP 헤더나 gRPC 메타데이터를 통해 마이크로서비스간 전달됩니다.
    
    Args:
        key (str): Baggage 키
            예: "user.id", "tenant.id", "trace.priority"
            
        value (str): Baggage 값
            모든 값은 문자열로 변환되어 전달
            
    사용 예시:
        ```python
        # 사용자 ID 전파
        set_baggage("user.id", "12345")
        set_baggage("user.role", "admin")
        
        # 다운스트림 서비스에서
        user_id = get_baggage("user.id")
        ```
        
    W3C Baggage 표준:
        - 키-값 쌍으로 HTTP 헤더에 인코딩
        - 자동으로 하위 스패에 전파
        - 서비스 경계를 넘나 전달
        
    주의사항:
        - 민감한 정보 전파 금지
        - 과도한 데이터로 성능 영향 가능
        - 클라이언트에 노출될 수 있음
    """
    baggage.set_baggage(key, value)


def get_baggage(key: str) -> str | None:
    """
    컨텍스트에서 Baggage 항목 조회
    
    현재 실행 컨텍스트에서 지정된 키의 Baggage 값을 가져옵니다.
    상위 스패이나 서비스에서 설정된 값을 하위에서 접근할 수 있습니다.
    
    Args:
        key (str): 조회할 Baggage 키
            예: "user.id", "session.id"
            
    Returns:
        Optional[str]: Baggage 값 또는 None
            - str: 해당 키의 값이 존재하는 경우
            - None: 키가 존재하지 않는 경우
            
    사용 예시:
        ```python
        # 사용자 컨텍스트 확인
        user_id = get_baggage("user.id")
        if user_id:
            logger.info("사용자 요청 처리", user_id=user_id)
        
        # 조건부 로직
        priority = get_baggage("trace.priority")
        if priority == "high":
            # 고우선 처리
            pass
        ```
        
    컨텍스트 전파:
        - 마이크로서비스간 자동 전달
        - HTTP 요청 헤더에 인코딩 전송
        - 비동기 작업도 컨텍스트 유지
    """
    result = baggage.get_baggage(key)
    return str(result) if result is not None else None