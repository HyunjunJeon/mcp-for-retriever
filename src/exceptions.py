"""
사용자 정의 예외 및 에러 처리 모듈

이 모듈은 MCP 서버의 모든 에러와 예외를 정의하고 처리합니다.
JSON-RPC 2.0 표준 에러 코드와 함께 사용자 정의 에러 코드를 제공합니다.

주요 구성요소:
    - ErrorCode: 표준 및 사용자 정의 에러 코드 열거형
    - MCPError: 모든 MCP 예외의 기본 클래스
    - 구체적인 예외 클래스들: 인증, 권한, 속도 제한 등
    - ErrorHandler: 중앙 집중식 에러 처리기

에러 코드 범위:
    - 표준 JSON-RPC: -32700 ~ -32603
    - 사용자 정의: -32000 ~ -32099

작성일: 2024-01-30
"""

from typing import Any, Dict, Optional
from enum import Enum
import asyncio


class ErrorCode(Enum):
    """
    MCP 에러 코드 열거형
    
    JSON-RPC 2.0 표준 에러 코드와 MCP 확장 에러 코드를 정의합니다.
    표준 코드는 JSON-RPC 스펙을 따르고, 사용자 정의 코드는 
    -32000 ~ -32099 범위를 사용합니다.
    """
    
    # 표준 JSON-RPC 에러 코드
    PARSE_ERROR = -32700          # JSON 파싱 에러
    INVALID_REQUEST = -32600      # 잘못된 요청 형식
    METHOD_NOT_FOUND = -32601     # 메서드를 찾을 수 없음
    INVALID_PARAMS = -32602       # 잘못된 매개변수
    INTERNAL_ERROR = -32603       # 내부 서버 에러
    
    # 사용자 정의 에러 코드 (-32000 ~ -32099 범위 사용)
    AUTHENTICATION_ERROR = -32001  # 인증 실패
    AUTHORIZATION_ERROR = -32002   # 권한 부족
    RATE_LIMIT_ERROR = -32003      # 요청 속도 제한 초과
    RETRIEVER_ERROR = -32004       # 리트리버 작업 실패
    VALIDATION_ERROR = -32005      # 입력값 검증 실패
    TIMEOUT_ERROR = -32006         # 작업 시간 초과
    RESOURCE_NOT_FOUND = -32007    # 리소스를 찾을 수 없음
    SERVICE_UNAVAILABLE = -32008   # 서비스 일시 중단


class MCPError(Exception):
    """
    모든 MCP 에러의 기본 예외 클래스
    
    JSON-RPC 2.0 형식의 에러 응답을 생성할 수 있도록 설계되었습니다.
    모든 MCP 관련 예외는 이 클래스를 상속받아야 합니다.
    
    Attributes:
        message (str): 에러 메시지
        code (ErrorCode): 에러 코드
        data (dict): 추가 에러 정보 (선택사항)
    """
    
    def __init__(
        self,
        message: str,
        code: ErrorCode = ErrorCode.INTERNAL_ERROR,
        data: Optional[Dict[str, Any]] = None
    ):
        """
        MCP 에러 초기화
        
        Args:
            message: 사용자에게 표시될 에러 메시지
            code: 에러 코드 (기본값: INTERNAL_ERROR)
            data: 디버깅에 유용한 추가 정보 (선택사항)
        """
        self.message = message
        self.code = code
        self.data = data or {}
        super().__init__(message)
    
    def to_dict(self) -> Dict[str, Any]:
        """
        에러를 JSON-RPC 에러 형식으로 변환
        
        JSON-RPC 2.0 스펙에 따라 error 객체를 생성합니다.
        data 필드는 값이 있을 때만 포함됩니다.
        
        Returns:
            Dict[str, Any]: JSON-RPC 에러 형식
                - code: 에러 코드 (숫자)
                - message: 에러 메시지
                - data: 추가 정보 (선택사항)
        """
        error_dict = {
            "code": self.code.value,
            "message": self.message
        }
        if self.data:
            error_dict["data"] = self.data
        return error_dict


class AuthenticationError(MCPError):
    """
    인증 실패 에러
    
    JWT 토큰 검증 실패, API 키 불일치, 만료된 토큰 등
    인증 관련 문제가 발생했을 때 사용됩니다.
    """
    
    def __init__(self, message: str = "Authentication failed", data: Optional[Dict[str, Any]] = None):
        """
        Args:
            message: 에러 메시지 (기본값: "Authentication failed")
            data: 추가 정보 (예: 실패 원인, 토큰 타입 등)
        """
        super().__init__(
            message=message,
            code=ErrorCode.AUTHENTICATION_ERROR,
            data=data
        )


class AuthorizationError(MCPError):
    """
    권한 부족 에러
    
    사용자가 특정 리소스나 도구에 접근할 권한이 없을 때 발생합니다.
    인증은 성공했지만 권한이 부족한 경우에 사용됩니다.
    """
    
    def __init__(self, message: str = "Permission denied", data: Optional[Dict[str, Any]] = None):
        """
        Args:
            message: 에러 메시지 (기본값: "Permission denied")
            data: 추가 정보 (예: 필요한 권한, 현재 역할 등)
        """
        super().__init__(
            message=message,
            code=ErrorCode.AUTHORIZATION_ERROR,
            data=data
        )


class RateLimitError(MCPError):
    """
    요청 속도 제한 초과 에러
    
    사용자가 허용된 요청 속도를 초과했을 때 발생합니다.
    재시도 가능 시간 정보를 포함할 수 있습니다.
    """
    
    def __init__(
        self,
        message: str = "Rate limit exceeded",
        retry_after: Optional[int] = None,
        data: Optional[Dict[str, Any]] = None
    ):
        """
        Args:
            message: 에러 메시지 (기본값: "Rate limit exceeded")
            retry_after: 재시도 가능 시간 (초 단위, 선택사항)
            data: 추가 정보 (예: 현재 할당량, 최대 할당량 등)
        """
        if data is None:
            data = {}
        if retry_after is not None:
            # 재시도 가능 시간을 기계가 읽을 수 있는 형식과 
            # 사람이 읽을 수 있는 형식으로 모두 제공
            data["retry_after"] = retry_after
            data["retry_after_human"] = f"{retry_after} seconds"
        
        super().__init__(
            message=message,
            code=ErrorCode.RATE_LIMIT_ERROR,
            data=data
        )


class RetrieverError(MCPError):
    """
    리트리버 작업 실패 에러
    
    데이터 소스에서 정보를 검색하는 동안 발생한 에러를 나타냅니다.
    연결 실패, 쿼리 실행 실패, API 에러 등을 포함합니다.
    """
    
    def __init__(
        self,
        message: str,
        retriever_name: Optional[str] = None,
        operation: Optional[str] = None,
        data: Optional[Dict[str, Any]] = None
    ):
        """
        Args:
            message: 에러 메시지
            retriever_name: 에러가 발생한 리트리버 이름 (선택사항)
            operation: 실패한 작업 이름 (예: "connect", "retrieve", 선택사항)
            data: 추가 정보 (예: 원본 에러, 쿼리 정보 등)
        """
        if data is None:
            data = {}
        if retriever_name:
            data["retriever"] = retriever_name
        if operation:
            data["operation"] = operation
        
        super().__init__(
            message=message,
            code=ErrorCode.RETRIEVER_ERROR,
            data=data
        )


class ValidationError(MCPError):
    """
    요청 검증 실패 에러
    
    입력 매개변수가 유효하지 않거나 필수 필드가 누락되었을 때 발생합니다.
    어떤 필드가 문제인지, 어떤 값이 잘못되었는지 정보를 포함할 수 있습니다.
    """
    
    def __init__(
        self,
        message: str,
        field: Optional[str] = None,
        value: Optional[Any] = None,
        data: Optional[Dict[str, Any]] = None
    ):
        """
        Args:
            message: 에러 메시지
            field: 검증에 실패한 필드 이름 (선택사항)
            value: 잘못된 값 (선택사항)
            data: 추가 정보 (예: 예상 형식, 제약 조건 등)
        """
        if data is None:
            data = {}
        if field:
            data["field"] = field
        if value is not None:
            # 긴 값은 100자로 잘라서 로그에 과도한 데이터 방지
            data["value"] = str(value)[:100]
        
        super().__init__(
            message=message,
            code=ErrorCode.VALIDATION_ERROR,
            data=data
        )


class TimeoutError(MCPError):
    """
    작업 시간 초과 에러
    
    비동기 작업이 지정된 시간 내에 완료되지 않았을 때 발생합니다.
    네트워크 요청, 데이터베이스 쿼리 등 다양한 작업에서 사용됩니다.
    """
    
    def __init__(
        self,
        message: str = "Operation timed out",
        operation: Optional[str] = None,
        timeout_seconds: Optional[float] = None,
        data: Optional[Dict[str, Any]] = None
    ):
        """
        Args:
            message: 에러 메시지 (기본값: "Operation timed out")
            operation: 타임아웃된 작업 이름 (선택사항)
            timeout_seconds: 타임아웃 시간 (초 단위, 선택사항)
            data: 추가 정보
        """
        if data is None:
            data = {}
        if operation:
            data["operation"] = operation
        if timeout_seconds:
            data["timeout_seconds"] = timeout_seconds
        
        super().__init__(
            message=message,
            code=ErrorCode.TIMEOUT_ERROR,
            data=data
        )


class ResourceNotFoundError(MCPError):
    """
    리소스를 찾을 수 없음 에러
    
    요청된 리소스(도구, 데이터, 설정 등)가 존재하지 않을 때 발생합니다.
    404 HTTP 상태 코드와 유사한 개념입니다.
    """
    
    def __init__(
        self,
        message: str,
        resource_type: Optional[str] = None,
        resource_id: Optional[str] = None,
        data: Optional[Dict[str, Any]] = None
    ):
        """
        Args:
            message: 에러 메시지
            resource_type: 리소스 타입 (예: "tool", "user", "config", 선택사항)
            resource_id: 리소스 식별자 (선택사항)
            data: 추가 정보
        """
        if data is None:
            data = {}
        if resource_type:
            data["resource_type"] = resource_type
        if resource_id:
            data["resource_id"] = resource_id
        
        super().__init__(
            message=message,
            code=ErrorCode.RESOURCE_NOT_FOUND,
            data=data
        )


class ServiceUnavailableError(MCPError):
    """
    서비스 이용 불가 에러
    
    서비스가 일시적으로 사용할 수 없는 상태일 때 발생합니다.
    유지보수, 과부하, 외부 서비스 중단 등의 경우에 사용됩니다.
    503 HTTP 상태 코드와 유사합니다.
    """
    
    def __init__(
        self,
        message: str = "Service temporarily unavailable",
        service_name: Optional[str] = None,
        retry_after: Optional[int] = None,
        data: Optional[Dict[str, Any]] = None
    ):
        """
        Args:
            message: 에러 메시지 (기본값: "Service temporarily unavailable")
            service_name: 이용 불가한 서비스 이름 (선택사항)
            retry_after: 재시도 가능 시간 (초 단위, 선택사항)
            data: 추가 정보 (예: 원인, 예상 복구 시간 등)
        """
        if data is None:
            data = {}
        if service_name:
            data["service"] = service_name
        if retry_after:
            data["retry_after"] = retry_after
        
        super().__init__(
            message=message,
            code=ErrorCode.SERVICE_UNAVAILABLE,
            data=data
        )


class ErrorHandler:
    """
    중앙 집중식 에러 처리기
    
    모든 예외를 JSON-RPC 형식의 에러 응답으로 변환하고
    에러 컨텍스트를 생성하는 유틸리티 클래스입니다.
    """
    
    @staticmethod
    def handle_error(error: Exception, request_id: Optional[str] = None) -> Dict[str, Any]:
        """
        모든 예외를 JSON-RPC 에러 응답으로 변환
        
        다양한 타입의 예외를 적절한 MCP 에러로 매핑하고
        JSON-RPC 2.0 형식의 에러 응답을 생성합니다.
        
        Args:
            error: 처리할 예외
            request_id: 요청 추적을 위한 ID (선택사항)
            
        Returns:
            Dict[str, Any]: JSON-RPC 에러 응답
                - jsonrpc: "2.0" (고정값)
                - error: 에러 객체 (code, message, data)
                - id: 요청 ID (null일 수 있음)
        """
        if isinstance(error, MCPError):
            # MCP 사용자 정의 에러는 그대로 사용
            error_response = {
                "jsonrpc": "2.0",
                "error": error.to_dict(),
                "id": request_id
            }
        elif isinstance(error, asyncio.TimeoutError):
            # asyncio 타임아웃을 MCP 타임아웃 에러로 변환
            timeout_error = TimeoutError("Operation timed out")
            error_response = {
                "jsonrpc": "2.0",
                "error": timeout_error.to_dict(),
                "id": request_id
            }
        elif isinstance(error, ValueError):
            # ValueError를 검증 에러로 변환 (잘못된 입력값)
            validation_error = ValidationError(str(error))
            error_response = {
                "jsonrpc": "2.0",
                "error": validation_error.to_dict(),
                "id": request_id
            }
        else:
            # 예상치 못한 예외는 내부 에러로 처리
            # 보안을 위해 상세 정보는 data 필드에만 포함
            internal_error = MCPError(
                message="Internal server error",
                code=ErrorCode.INTERNAL_ERROR,
                data={
                    "exception_type": type(error).__name__,
                    "exception_message": str(error)
                }
            )
            error_response = {
                "jsonrpc": "2.0",
                "error": internal_error.to_dict(),
                "id": request_id
            }
        
        return error_response
    
    @staticmethod
    def create_error_context(
        error: Exception,
        method: Optional[str] = None,
        user_id: Optional[str] = None,
        tool_name: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        로깅을 위한 에러 컨텍스트 생성
        
        구조화된 로깅에 사용할 수 있도록 에러와 관련된
        모든 컨텍스트 정보를 수집합니다.
        
        Args:
            error: 발생한 예외
            method: 호출된 MCP 메서드 (예: "tools/list", "tools/call")
            user_id: 에러를 발생시킨 사용자 ID
            tool_name: 에러가 발생한 도구 이름
            
        Returns:
            Dict[str, Any]: 에러 컨텍스트 딕셔너리
                - error_type: 예외 클래스 이름
                - error_message: 에러 메시지
                - method: MCP 메서드 (제공된 경우)
                - user_id: 사용자 ID (제공된 경우)
                - tool_name: 도구 이름 (제공된 경우)
                - error_code: MCP 에러 코드 (MCPError인 경우)
                - error_data: 추가 에러 데이터 (MCPError인 경우)
        """
        context = {
            "error_type": type(error).__name__,
            "error_message": str(error)
        }
        
        # 선택적 컨텍스트 정보 추가
        if method:
            context["method"] = method
        if user_id:
            context["user_id"] = user_id
        if tool_name:
            context["tool_name"] = tool_name
        
        # MCPError의 경우 추가 정보 포함
        if isinstance(error, MCPError):
            context["error_code"] = error.code.value
            context["error_data"] = error.data
        
        return context