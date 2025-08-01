"""
Sentry 오류 추적 및 성능 모니터링 통합

이 모듈은 MCP 서버에 Sentry 오류 모니터링과 성능 추적 기능을 통합합니다.
실시간 오류 발생 알림, 성능 저하 감지, 사용자 세션 추적 등을 제공합니다.

주요 기능:
    오류 추적:
        - 예외 자동 캡처 및 Sentry로 전송
        - 스택 트레이스와 컨텍스트 정보 포함
        - 오류 빈도 및 심각도 분류
        - 사용자 컸하트 및 환경 정보

    성능 모니터링:
        - 요청/응답 시간 추적
        - 데이터베이스 쿼리 성능
        - 외부 API 호출 모니터링
        - 사용자 세션 및 행동 추적

    통합 라이브러리:
        - FastAPI 웹 프레임워크
        - SQLAlchemy ORM
        - HTTPX HTTP 클라이언트
        - Python 로깅 시스템
        - Asyncio 비동기 작업
"""

import os
from typing import Optional, Dict, Any
import structlog
import sentry_sdk
from sentry_sdk.integrations.fastapi import FastApiIntegration
from sentry_sdk.integrations.sqlalchemy import SqlalchemyIntegration
from sentry_sdk.integrations.httpx import HttpxIntegration
from sentry_sdk.integrations.logging import LoggingIntegration
from sentry_sdk.integrations.asyncio import AsyncioIntegration
from sentry_sdk import (
    set_user,
    set_tag,
    set_context,
    capture_exception,
    capture_message,
)

logger = structlog.get_logger(__name__)


class SentryIntegration:
    """
    Sentry 오류 추적 및 성능 모니터링 관리 클래스

    MCP 서버의 오류 및 성능 데이터를 Sentry 플랫폼으로 수집하고 모니터링합니다.
    실시간 알림, 오류 그룹화, 성능 인사이트 등을 제공합니다.

    기능:
        - 자동 오류 및 예외 캡처
        - 사용자 컨텍스트 및 세션 추적
        - 성능 트랜잭션 모니터링
        - 사용자 정의 태그 및 컨텍스트
        - 다양한 Python 라이브러리 자동 통합
    """

    def __init__(
        self,
        dsn: Optional[str] = None,
        environment: Optional[str] = None,
        release: Optional[str] = None,
        traces_sample_rate: float = 0.1,
        profiles_sample_rate: float = 0.1,
        enable_performance: bool = True,
        custom_tags: Optional[Dict[str, str]] = None,
    ):
        """Initialize Sentry integration.

        Args:
            dsn: Sentry DSN (Data Source Name)
            environment: Environment name (e.g., production, staging)
            release: Release version
            traces_sample_rate: Sample rate for performance monitoring (0.0 to 1.0)
            profiles_sample_rate: Sample rate for profiling (0.0 to 1.0)
            enable_performance: Whether to enable performance monitoring
            custom_tags: Additional tags to attach to all events
        """
        self.dsn = dsn or os.getenv("SENTRY_DSN")
        self.environment = environment or os.getenv("ENVIRONMENT", "development")
        self.release = release or os.getenv("RELEASE_VERSION", "unknown")
        self.traces_sample_rate = traces_sample_rate
        self.profiles_sample_rate = profiles_sample_rate
        self.enable_performance = enable_performance
        self.custom_tags = custom_tags or {}

        self._initialized = False

    def setup(self):
        """Setup Sentry SDK with integrations."""
        if not self.dsn:
            logger.warning("Sentry DSN not configured, skipping Sentry setup")
            return

        logger.info(
            "Setting up Sentry",
            environment=self.environment,
            release=self.release,
            traces_sample_rate=self.traces_sample_rate,
        )

        # Configure integrations
        integrations = [
            FastApiIntegration(
                transaction_style="endpoint",
                failed_request_status_codes=[400, 401, 403, 404, 500],
            ),
            SqlalchemyIntegration(),
            HttpxIntegration(),
            AsyncioIntegration(),
            LoggingIntegration(
                level=None,  # Capture all levels
                event_level=None,  # Don't create events from logs
            ),
        ]

        # Initialize Sentry
        sentry_sdk.init(
            dsn=self.dsn,
            environment=self.environment,
            release=self.release,
            integrations=integrations,
            traces_sample_rate=self.traces_sample_rate
            if self.enable_performance
            else 0.0,
            profiles_sample_rate=self.profiles_sample_rate
            if self.enable_performance
            else 0.0,
            attach_stacktrace=True,
            send_default_pii=False,  # Don't send personally identifiable information
            before_send=self._before_send,
            before_send_transaction=self._before_send_transaction,
        )

        # Set global tags
        for key, value in self.custom_tags.items():
            set_tag(key, value)

        # Set service context
        set_context(
            "service",
            {
                "name": "mcp-retriever",
                "version": self.release,
                "environment": self.environment,
            },
        )

        self._initialized = True
        logger.info("Sentry setup complete")

    def _before_send(
        self, event: Dict[str, Any], hint: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """Process event before sending to Sentry.

        Args:
            event: The event to be sent
            hint: Additional information about the event

        Returns:
            Modified event or None to drop the event
        """
        # Filter out certain errors
        if "exc_info" in hint:
            exc_type, exc_value, tb = hint["exc_info"]

            # Don't send certain expected errors
            if exc_type.__name__ in ["asyncio.CancelledError", "KeyboardInterrupt"]:
                return None

            # Add custom fingerprinting for better grouping
            if exc_type.__name__ == "HTTPException":
                event["fingerprint"] = ["http-exception", str(exc_value.status_code)]

        # Sanitize sensitive data
        if "request" in event:
            request = event["request"]
            # Remove sensitive headers
            if "headers" in request:
                sensitive_headers = ["authorization", "cookie", "x-api-key"]
                for header in sensitive_headers:
                    request["headers"].pop(header, None)

            # Remove sensitive data from body
            if "data" in request:
                self._sanitize_data(request["data"])

        return event

    def _before_send_transaction(
        self, event: Dict[str, Any], hint: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """Process transaction before sending to Sentry.

        Args:
            event: The transaction event
            hint: Additional information

        Returns:
            Modified event or None to drop the transaction
        """
        # Don't send transactions for health checks
        if event.get("transaction", "").endswith("/health"):
            return None

        # Don't send transactions for metrics endpoint
        if event.get("transaction", "").endswith("/metrics"):
            return None

        return event

    def _sanitize_data(self, data: Any):
        """Recursively sanitize sensitive data."""
        if isinstance(data, dict):
            sensitive_keys = ["password", "token", "api_key", "secret", "auth"]
            for key in list(data.keys()):
                if any(sensitive in key.lower() for sensitive in sensitive_keys):
                    data[key] = "[REDACTED]"
                else:
                    self._sanitize_data(data[key])
        elif isinstance(data, list):
            for item in data:
                self._sanitize_data(item)

    def set_user_context(
        self, user_id: str, email: Optional[str] = None, username: Optional[str] = None
    ):
        """Set user context for error tracking.

        Args:
            user_id: User ID
            email: User email (optional)
            username: Username (optional)
        """
        if not self._initialized:
            return

        user_data = {"id": user_id}
        if email:
            user_data["email"] = email
        if username:
            user_data["username"] = username

        set_user(user_data)

    def set_request_context(
        self, request_id: str, method: str, tool_name: Optional[str] = None
    ):
        """Set request context for error tracking.

        Args:
            request_id: Unique request ID
            method: MCP method
            tool_name: Tool name if applicable
        """
        if not self._initialized:
            return

        set_tag("request_id", request_id)
        set_tag("mcp_method", method)
        if tool_name:
            set_tag("tool_name", tool_name)

    def capture_error(
        self,
        error: Exception,
        level: str = "error",
        extra_context: Optional[Dict[str, Any]] = None,
    ):
        """Capture an error with additional context.

        Args:
            error: The exception to capture
            level: Error level (debug, info, warning, error, fatal)
            extra_context: Additional context to attach
        """
        if not self._initialized:
            return

        with sentry_sdk.push_scope() as scope:
            scope.level = level

            if extra_context:
                for key, value in extra_context.items():
                    scope.set_context(key, value)

            capture_exception(error)

    def capture_message_event(
        self,
        message: str,
        level: str = "info",
        extra_context: Optional[Dict[str, Any]] = None,
    ):
        """Capture a message event.

        Args:
            message: The message to capture
            level: Message level
            extra_context: Additional context
        """
        if not self._initialized:
            return

        with sentry_sdk.push_scope() as scope:
            if extra_context:
                for key, value in extra_context.items():
                    scope.set_context(key, value)

            capture_message(message, level=level)

    def create_transaction(self, name: str, op: str = "mcp.request"):
        """Create a new transaction for performance monitoring.

        Args:
            name: Transaction name
            op: Operation type

        Returns:
            Transaction object
        """
        if not self._initialized or not self.enable_performance:
            return None

        return sentry_sdk.start_transaction(name=name, op=op)

    def add_breadcrumb(
        self,
        message: str,
        category: str = "mcp",
        level: str = "info",
        data: Optional[Dict[str, Any]] = None,
    ):
        """Add a breadcrumb for debugging.

        Args:
            message: Breadcrumb message
            category: Breadcrumb category
            level: Breadcrumb level
            data: Additional data
        """
        if not self._initialized:
            return

        sentry_sdk.add_breadcrumb(
            message=message, category=category, level=level, data=data
        )

    def flush(self, timeout: int = 2):
        """Flush pending events to Sentry.

        Args:
            timeout: Flush timeout in seconds
        """
        if self._initialized:
            sentry_sdk.flush(timeout=timeout)

    def shutdown(self):
        """Shutdown Sentry client."""
        if self._initialized:
            self.flush()
            logger.info("Sentry shutdown complete")


# Global Sentry instance
_sentry: Optional[SentryIntegration] = None


def get_sentry() -> SentryIntegration:
    """Get the global Sentry instance."""
    global _sentry
    if not _sentry:
        _sentry = SentryIntegration()
    return _sentry
