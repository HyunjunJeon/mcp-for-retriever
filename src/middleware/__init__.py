"""
MCP 서버용 미들웨어 컴포넌트 모음

이 패키지는 MCP(Model Context Protocol) 서버에서 사용하는 다양한 미들웨어들을 제공합니다.
각 미들웨어는 HTTP 요청 처리 파이프라인의 특정 단계에서 횡단 관심사(Cross-cutting Concerns)를 처리합니다.

미들웨어 컴포넌트:
    AuthMiddleware: JWT 토큰 기반 인증 및 권한 검증
        - Bearer 토큰 추출 및 검증
        - 사용자 컨텍스트 설정
        - 역할 기반 접근 제어
        
    LoggingMiddleware: 구조화된 요청/응답 로깅
        - 요청 ID 생성 및 추적
        - 성능 메트릭 수집
        - 에러 로깅 및 스택 트레이스
        
    RateLimitMiddleware: API 호출 빈도 제한
        - 사용자별/IP별 요청 제한
        - 슬라이딩 윈도우 알고리즘
        - Redis 기반 분산 제한
        
    ValidationMiddleware: 요청 데이터 검증
        - 입력 데이터 스키마 검증
        - 데이터 타입 변환 및 정규화
        - 보안 필터링 (XSS, SQL Injection 방지)
        
    MetricsMiddleware: 애플리케이션 성능 메트릭 수집
        - 응답 시간 측정
        - 요청 수 카운팅
        - 에러율 추적
        
    ErrorHandlerMiddleware: 전역 예외 처리
        - 예외 타입별 응답 포맷팅
        - 스택 트레이스 로깅
        - 사용자 친화적 에러 메시지

사용 패턴:
    ```python
    from fastapi import FastAPI
    from src.middleware import (
        AuthMiddleware,
        LoggingMiddleware,
        RateLimitMiddleware
    )
    
    app = FastAPI()
    
    # 미들웨어 순서가 중요함 (LIFO 순서로 실행)
    app.add_middleware(ErrorHandlerMiddleware)
    app.add_middleware(MetricsMiddleware)
    app.add_middleware(AuthMiddleware)
    app.add_middleware(RateLimitMiddleware)
    app.add_middleware(LoggingMiddleware)
    ```

실행 순서:
    요청: LoggingMiddleware → RateLimitMiddleware → AuthMiddleware → MetricsMiddleware → ErrorHandlerMiddleware → 엔드포인트
    응답: 엔드포인트 → ErrorHandlerMiddleware → MetricsMiddleware → AuthMiddleware → RateLimitMiddleware → LoggingMiddleware

작성일: 2024-01-30
"""

from .auth import AuthMiddleware
from .logging import LoggingMiddleware
from .rate_limit import RateLimitMiddleware
from .validation import ValidationMiddleware
from .metrics import MetricsMiddleware
from .error_handler import ErrorHandlerMiddleware

__all__ = [
    "AuthMiddleware",
    "LoggingMiddleware", 
    "RateLimitMiddleware",
    "ValidationMiddleware",
    "MetricsMiddleware",
    "ErrorHandlerMiddleware"
]