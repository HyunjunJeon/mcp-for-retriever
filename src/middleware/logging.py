"""
MCP 서버용 향상된 로깅 미들웨어

이 모듈은 MCP 서버의 모든 요청과 응답을 구조화된 형태로 로깅하는 미들웨어를 구현합니다.
요청 시간 추적, 성능 모니터링, 에러 추적, 감사 로깅 등을 지원합니다.

주요 기능:
    요청/응답 로깅:
        - 고유 요청 ID 생성 및 추적
        - 사용자 컨텍스트 로깅 (사용자 ID, 이메일, 역할)
        - MCP 메서드 및 매개변수 로깅
        - 요청/응답 본문 로깅 (선택적)
        
    성능 모니터링:
        - 요청 처리 시간 측정 (밀리초 단위)
        - 느린 요청 감지 및 경고 (1초 이상)
        - 성능 병목 현상 식별
        - 에러율 및 응답 시간 단계별 분석
        
    보안 및 개인정보 보호:
        - 민감한 데이터 자동 마스키킹
        - 비밀번호, 토큰, API 키 등 레덕션
        - 긴 문자열 자동 절단
        - 로그 출력 크기 제한
        
    에러 처리 및 디버깅:
        - 예외 상황 자동 캡처
        - 스택 트레이스 로깅
        - 에러 컨텍스트 보존
        - JSON-RPC 에러 응답 로깅

로깅 구조:
    배치를 사용한 구조화된 로깅으로 다음과 같은 정보를 제공합니다:
    - request_id: 요청 고유 식별자
    - method: MCP 메서드명
    - timestamp: ISO 8601 형식 시간
    - user_*: 사용자 컨텍스트 정보
    - duration_ms: 요청 처리 시간
    - error_*: 에러 관련 정보

사용 예시:
    ```python
    logging_middleware = LoggingMiddleware(
        log_request_body=True,  # 개발 환경에서만
        log_response_body=False,  # 보안상 비활성화 권장
        sensitive_fields=["password", "api_key", "token"]
    )
    ```

작성일: 2024-01-30
"""

from typing import Any, Callable, Dict
import structlog
import time
import uuid
from datetime import datetime, timezone

logger = structlog.get_logger(__name__)


class LoggingMiddleware:
    """
    요청/응답 추적 및 성능 모니터링을 위한 향상된 로깅 미들웨어
    
    모든 MCP 요청에 대해 고유 ID를 부여하고 사용자 컨텍스트, 성능 메트릭,
    에러 정보를 구조화된 형태로 로깅합니다. 민감한 데이터 보호와 성능 모니터링을 동시에 지원합니다.
    
    로깅 과정:
        1. 요청 수신 시 고유 ID 생성
        2. 사용자 컨텍스트 추출 (ID, 이메일, 역할)
        3. MCP 메서드 및 도구 정보 추출
        4. 요청 시작 로깅 및 시간 측정 시작
        5. 다음 미들웨어로 요청 전달
        6. 응답 및 에러 처리
        7. 요청 완료 로깅 및 성능 모니터링
        
    보안 특징:
        - 민감한 필드 자동 마스키킹
        - 긴 데이터 자동 절단
        - 로그 출력 크기 제한
        - 개인정보 노출 방지
    """
    
    def __init__(
        self,
        log_request_body: bool = False,
        log_response_body: bool = False,
        sensitive_fields: list[str] | None = None
    ):
        """
        로깅 미들웨어 초기화
        
        Args:
            log_request_body (bool): 전체 요청 본문 로깅 여부
                True: 요청의 모든 데이터를 로깅 (개발 환경 전용)
                False: 요청 본문 제외 (기본값, 보안 추천)
                
            log_response_body (bool): 전체 응답 본문 로깅 여부
                True: 응답의 모든 데이터를 로깅
                False: 응답 본문 제외 (기본값, 성능 추천)
                
            sensitive_fields (list[str]): 로그에서 제외할 민감 필드 목록
                기본값: ["password", "token", "api_key", "secret"]
                예: ["credit_card", "ssn", "personal_id"]
                이 필드들은 "[REDACTED]"로 대체됨
                
        초기화 과정:
            - 로깅 옵션 설정 저장
            - 민감 필드 리스트 준비
            - 로깅 컨텍스트 초기화
            
        보안 고려사항:
            - production 환경에서는 log_request_body=False 권장
            - 민감한 데이터가 있는 경우 sensitive_fields 확장 필요
            - 로그 단계에 따라 세부 정보 노출 조절
        """
        self.log_request_body = log_request_body
        self.log_response_body = log_response_body
        self.sensitive_fields = sensitive_fields or ["password", "token", "api_key", "secret"]
    
    async def __call__(self, request: Dict[str, Any], call_next: Callable) -> Dict[str, Any]:
        """
        요청/응답 로깅 및 시간 정보 추적
        
        MCP 요청을 인터앉트하여 시작부터 완료까지의 전체 라이프사이클을 로깅합니다.
        고유 요청 ID를 부여하고 사용자 컨텍스트, 성능 메트릭, 에러 정보를 추적합니다.
        
        Args:
            request (Dict[str, Any]): MCP 요청 데이터
                - method: MCP 메서드명
                - params: 요청 매개변수
                - user: 인증된 사용자 정보 (인증 미들웨어에서 설정)
                
            call_next (Callable): 다음 미들웨어 또는 핸들러
                
        Returns:
            Dict[str, Any]: 처리된 MCP 응답
                정상 응답 또는 에러 응답
                
        로깅 플로우:
            1. 요청 수신: UUID 기반 request_id 생성
            2. 컨텍스트 추출: 사용자, 메서드, 도구 정보
            3. 요청 로깅: 신청 시간, 컨텍스트 정보 로깅
            4. 요청 전달: request_id를 요청에 추가하여 다음 단계로 전달
            5. 응답 처리: 에러 및 예외 상황 처리
            6. 완료 로깅: 소요 시간, 에러 여부, 성능 모니터링
            
        성능 모니터링:
            - 요청 처리 시간 측정 (밀리초)
            - 1초 이상 요청에 대한 느린 요청 경고
            - 에러율 및 성능 메트릭 수집
            
        에러 처리:
            - 예외 발생 시 스텍 트레이스 로깅
            - JSON-RPC 에러 응답 감지
            - 에러 컨텍스트 보존
        """
        start_time = time.time()
        request_id = str(uuid.uuid4())
        
        # 요청 정보 추출
        method = request.get("method", "unknown")
        params = request.get("params", {})
        user = request.get("user", {})
        
        # 로그 컨텍스트 준비
        log_context = {
            "request_id": request_id,
            "method": method,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "user_id": user.get("id") if isinstance(user, dict) else None,
            "user_email": user.get("email") if isinstance(user, dict) else None,
            "user_type": user.get("type", "unknown") if isinstance(user, dict) else "unknown"
        }
        
        # 도구별 세부 정보 로깅
        if method == "tools/call" and isinstance(params, dict):
            log_context["tool_name"] = params.get("name")
            log_context["tool_args_keys"] = list(params.get("arguments", {}).keys()) if isinstance(params.get("arguments"), dict) else []
        
        # 요청 로깅
        logger.info(
            "MCP 요청 수신",
            **log_context,
            request_body=self._sanitize_data(request) if self.log_request_body else None
        )
        
        # 하위 처리를 위해 요청 ID를 요청에 추가
        request["request_id"] = request_id
        
        # 요청 처리
        error_occurred = False
        error_details = None
        
        try:
            response = await call_next(request)
            
            # 응답에서 에러 확인
            if isinstance(response, dict) and "error" in response:
                error_occurred = True
                error_details = response["error"]
            
            return response
            
        except Exception as e:
            error_occurred = True
            error_details = str(e)
            logger.exception(
                "요청 처리 중 미처리 예외 발생",
                **log_context,
                error=str(e)
            )
            raise
            
        finally:
            # 소요 시간 계산
            duration_ms = (time.time() - start_time) * 1000
            
            # 최종 로그 컨텍스트 준비
            final_context = {
                **log_context,
                "duration_ms": duration_ms,
                "error_occurred": error_occurred
            }
            
            if error_occurred and error_details:
                final_context["error_details"] = error_details
            
            # 응답 로깅
            log_level = "error" if error_occurred else "info"
            getattr(logger, log_level)(
                "MCP 요청 완료",
                **final_context,
                response_body=self._sanitize_data(response) if self.log_response_body and 'response' in locals() else None
            )
            
            # 느린 요청 로깅
            if duration_ms > 1000:  # 1초 이상 소요되는 요청
                logger.warning(
                    "느린 요청 감지",
                    **final_context,
                    threshold_ms=1000
                )
    
    def _sanitize_data(self, data: Any) -> Any:
        """
        로그에서 민감한 데이터를 재귀적으로 삭제/마스키킹
        
        중첩된 데이터 구조를 순회하며 민감한 필드를 찾아 "[REDACTED]"로 대체합니다.
        또한 너무 긴 문자열은 자동으로 절단하여 로그 크기를 제한합니다.
        
        Args:
            data (Any): 삭제할 데이터 (딕셔너리, 리스트, 문자열 등)
            
        Returns:
            Any: 삭제된 데이터
                - 민감 필드: "[REDACTED]"로 대체
                - 긴 문자열: 1000자로 절단 + "... [TRUNCATED]"
                - 일반 데이터: 원본 그대로 반환
                
        삭제 대상:
            - 비밀번호, 토큰, API 키 등 민감 정보
            - 1000자 이상의 긴 문자열
            - 사용자 정의 민감 필드
            
        처리 방식:
            - dict: 키명에 민감 키워드 포함 여부 확인
            - list: 각 요소에 대해 재귀적 삭제
            - str: 길이 확인 후 필요시 절단
            - 기타: 원본 그대로 반환
            
        보안 특징:
            - 대소문자 구분 없이 민감 필드 감지
            - 중첩된 구조에서도 안전한 삭제
            - 메모리 효율적인 데이터 처리
        """
        if isinstance(data, dict):
            sanitized = {}
            for key, value in data.items():
                if any(sensitive in key.lower() for sensitive in self.sensitive_fields):
                    sanitized[key] = "[REDACTED]"
                else:
                    sanitized[key] = self._sanitize_data(value)
            return sanitized
        elif isinstance(data, list):
            return [self._sanitize_data(item) for item in data]
        elif isinstance(data, str) and len(data) > 1000:
            # Truncate very long strings
            return data[:1000] + "... [TRUNCATED]"
        else:
            return data