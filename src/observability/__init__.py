"""
MCP 서버 관찰 가능성 및 모니터링 시스템

이 패키지는 MCP(Model Context Protocol) 서버의 운영과 관리를 위한
관찰 가능성(Observability) 컴포넌트들을 제공합니다.
분산 추적, 메트릭 수집, 오류 모니터링, 성능 분석 등을 지원합니다.

주요 구성 요소:
    TelemetrySetup: OpenTelemetry 기반 텔레메트리 시스템 설정
        - 분산 추적 (Distributed Tracing)
        - 메트릭 수집 (Metrics Collection)
        - 로그 집계 (Log Aggregation)
        - 리소스 정보 수집

    get_tracer: 추적 인스턴스 제공
        - 스팬(Span) 생성 및 관리
        - 추적 컨텍스트 전파
        - 커스텀 속성 및 이벤트 추가

    SentryIntegration: Sentry 오류 모니터링 통합
        - 실시간 오류 추적
        - 성능 모니터링
        - 릴리스 추적
        - 사용자 컨텍스트 수집

관찰 가능성의 세 가지 기둥:
    1. 로그 (Logs): 시스템 이벤트의 시계열 기록
    2. 메트릭 (Metrics): 시스템 성능의 수치적 측정
    3. 추적 (Traces): 분산 시스템에서의 요청 경로 추적

사용 예시:
    ```python
    from src.observability import TelemetrySetup, get_tracer, SentryIntegration

    # 텔레메트리 설정
    telemetry = TelemetrySetup(service_name="mcp-server")
    telemetry.setup()

    # Sentry 오류 모니터링 설정
    sentry = SentryIntegration(dsn="your-sentry-dsn")
    sentry.setup()

    # 추적 사용
    tracer = get_tracer(__name__)
    with tracer.start_as_current_span("operation"):
        # 추적할 작업 수행
        pass
    ```

통합 환경:
    - Jaeger/Zipkin을 통한 분산 추적 시각화
    - Prometheus를 통한 메트릭 수집
    - Grafana를 통한 대시보드 구성
    - Sentry를 통한 오류 알림
"""

from .telemetry import TelemetrySetup, get_tracer
from .sentry_integration import SentryIntegration

__all__ = ["TelemetrySetup", "get_tracer", "SentryIntegration"]
