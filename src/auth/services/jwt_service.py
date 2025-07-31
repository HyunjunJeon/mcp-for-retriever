"""
JWT 토큰 관리 서비스

이 모듈은 JWT(JSON Web Token) 기반 인증 시스템의 핵심 기능을 제공합니다.
액세스 토큰과 리프레시 토큰의 생성, 검증, 갱신을 담당합니다.

주요 기능:
    - JWT 액세스 토큰 생성 (단기 수명)
    - JWT 리프레시 토큰 생성 (장기 수명)
    - 토큰 서명 검증 및 디코딩
    - 토큰 만료 시간 관리
    - 리프레시 토큰을 통한 액세스 토큰 갱신

보안 특징:
    - HMAC SHA-256 서명 알고리즘 (HS256)
    - 토큰 타입별 분리된 검증 로직
    - 안전한 만료 시간 관리
    - 구조화된 로깅으로 감사 추적

JWT 표준 준수:
    - RFC 7519 JWT 표준 준수
    - 표준 클레임 사용 (sub, exp, iat)
    - 커스텀 클레임 지원 (roles, type)

의존성:
    - python-jose: JWT 생성 및 검증
    - structlog: 구조화된 로깅

작성일: 2024-01-30
"""

from datetime import datetime, timedelta, UTC
from typing import Any, Optional

from jose import JWTError, jwt
import structlog

from ..models import TokenData


# 구조화된 로깅을 위한 로거
logger = structlog.get_logger()


class JWTService:
    """
    JWT 토큰 생성 및 검증 서비스
    
    JWT 기반 인증 시스템의 핵심 컴포넌트로 토큰의 전체 생명주기를 관리합니다.
    액세스 토큰과 리프레시 토큰을 구분하여 처리하며, 보안을 위해
    각 토큰 타입별로 다른 만료 시간과 검증 로직을 적용합니다.
    
    토큰 설계 철학:
        - 액세스 토큰: 짧은 수명(30분), API 접근용
        - 리프레시 토큰: 긴 수명(7일), 토큰 갱신용
        - 서명 검증: HMAC-SHA256으로 무결성 보장
        - 페이로드: 최소한의 사용자 정보만 포함
    
    사용 예시:
        ```python
        jwt_service = JWTService(
            secret_key="your-secret-key",
            access_token_expire_minutes=30,
            refresh_token_expire_minutes=7*24*60
        )
        
        # 토큰 생성
        access_token = jwt_service.create_access_token(
            user_id="123", email="user@example.com", roles=["user"]
        )
        
        # 토큰 검증
        token_data = jwt_service.decode_token(access_token)
        ```
    
    Attributes:
        secret_key (str): JWT 서명용 비밀 키
        algorithm (str): 서명 알고리즘 (기본값: HS256)
        access_token_expire_minutes (int): 액세스 토큰 만료 시간 (분)
        refresh_token_expire_minutes (int): 리프레시 토큰 만료 시간 (분)
    """
    
    def __init__(
        self,
        secret_key: str,
        algorithm: str = "HS256",
        access_token_expire_minutes: int = 30,
        refresh_token_expire_minutes: int = 60 * 24 * 7,  # 7일
    ) -> None:
        """
        JWT 서비스 초기화
        
        JWT 토큰 생성 및 검증에 필요한 설정을 초기화합니다.
        보안을 위해 강력한 비밀 키와 적절한 만료 시간을 설정해야 합니다.
        
        Args:
            secret_key (str): JWT 서명에 사용할 비밀 키
                최소 32자 이상의 무작위 문자열 권장
                production에서는 환경 변수나 비밀 관리 시스템에서 로드
            algorithm (str): JWT 서명 알고리즘 (기본값: "HS256")
                지원 알고리즘: HS256, HS384, HS512
                대칭키 알고리즘으로 성능과 보안의 균형
            access_token_expire_minutes (int): 액세스 토큰 만료 시간 (분, 기본값: 30)
                짧은 수명으로 설정하여 보안 위험 최소화
                일반적으로 15분~2시간 사이로 설정
            refresh_token_expire_minutes (int): 리프레시 토큰 만료 시간 (분, 기본값: 7일)
                장기간 유효하지만 재사용 가능한 토큰
                일반적으로 1주일~1개월 사이로 설정
                
        보안 고려사항:
            - secret_key는 충분히 길고 무작위여야 함
            - production 환경에서는 secret_key를 코드에 하드코딩 금지
            - 토큰 만료 시간은 보안과 사용성의 균형을 고려하여 설정
        """
        self.secret_key = secret_key
        self.algorithm = algorithm
        self.access_token_expire_minutes = access_token_expire_minutes
        self.refresh_token_expire_minutes = refresh_token_expire_minutes
    
    def create_access_token(
        self,
        user_id: str,
        email: str,
        roles: list[str],
        scopes: Optional[list[str]] = None,
        resource_permissions: Optional[dict[str, list[str]]] = None,
        additional_claims: Optional[dict[str, Any]] = None,
    ) -> str:
        """
        JWT 액세스 토큰 생성
        
        사용자 정보를 바탕으로 API 접근용 액세스 토큰을 생성합니다.
        짧은 수명(30분)으로 보안 위험을 최소화하며, 사용자 인증 정보와 권한 스코프를 포함합니다.
        
        Args:
            user_id (str): 사용자 고유 식별자
                JWT의 'sub' (subject) 클레임으로 사용
            email (str): 사용자 이메일 주소
                사용자 식별 및 로깅 목적
            roles (list[str]): 사용자 역할 목록
                권한 검사에 사용되는 역할 정보
                예: ["user", "admin", "moderator"]
            scopes (Optional[list[str]]): OAuth2 스타일 권한 스코프 목록
                세밀한 권한 제어를 위한 스코프 정보
                예: ["read:vectors", "write:database", "admin:users"]
            resource_permissions (Optional[dict[str, list[str]]]): 리소스별 세밀한 권한 매핑
                특정 리소스에 대한 권한 정보 (자주 사용되는 권한만 토큰에 포함)
                예: {"collection1": ["read", "write"], "table1": ["read"]}
            additional_claims (Optional[dict[str, Any]]): 추가 클레임
                특별한 경우 토큰에 추가할 정보
                
        Returns:
            str: JWT 액세스 토큰
                Base64 인코딩된 JWT 문자열
                Format: header.payload.signature
                
        JWT 페이로드 구조:
            - sub: 사용자 ID (JWT 표준)
            - email: 사용자 이메일
            - roles: 역할 목록
            - scopes: 권한 스코프 목록 (신규)
            - resource_permissions: 리소스별 권한 매핑 (신규)
            - type: "access" (토큰 타입 구분)
            - exp: 만료 시각 (JWT 표준)
            - iat: 발급 시각 (JWT 표준)
            
        보안 특징:
            - HMAC-SHA256 서명으로 무결성 보장
            - 짧은 수명으로 탈취 시 피해 최소화
            - 토큰 타입 구분으로 오용 방지
            - 세밀한 권한 제어로 최소 권한 원칙 적용
            
        하위 호환성:
            - 기존 토큰은 scopes, resource_permissions 없이도 정상 동작
            - 새로운 필드들은 Optional로 처리되어 호환성 보장
            
        Example:
            ```python
            token = jwt_service.create_access_token(
                user_id="user123",
                email="user@example.com",
                roles=["user"],
                scopes=["read:vectors", "write:database"],
                resource_permissions={"collection1": ["read", "write"]},
                additional_claims={"department": "engineering"}
            )
            ```
        """
        # UTC 기준 현재 시각과 만료 시각 계산
        now = datetime.now(UTC)
        expire = now + timedelta(minutes=self.access_token_expire_minutes)
        
        # JWT 페이로드 구성 (표준 + 커스텀 클레임)
        payload = {
            "sub": str(user_id),        # Subject (사용자 식별자) - JWT 표준에 따라 문자열이어야 함
            "email": email,        # 사용자 이메일
            "roles": roles,        # 권한 역할 목록
            "type": "access",      # 토큰 타입 (액세스)
            "exp": expire,         # Expiration time
            "iat": now,           # Issued at
        }
        
        # 새로운 권한 필드들 추가 (하위 호환성을 위해 None이 아닌 경우만 포함)
        if scopes is not None:
            payload["scopes"] = scopes
            
        if resource_permissions is not None:
            payload["resource_permissions"] = resource_permissions
        
        # 추가 클레임이 있으면 페이로드에 병합
        if additional_claims:
            payload.update(additional_claims)
        
        # JWT 토큰 생성 (서명 포함)
        token = jwt.encode(payload, self.secret_key, algorithm=self.algorithm)
        
        # 토큰 생성 로깅 (감사 목적)
        logger.info(
            "액세스 토큰 생성",
            user_id=user_id,
            email=email,
            roles=roles,
            scopes=scopes,
            expires_in_minutes=self.access_token_expire_minutes,
        )
        
        return token
    
    def create_refresh_token(self, user_id: str) -> str:
        """리프레시 토큰 생성
        
        Args:
            user_id: 사용자 ID
            
        Returns:
            JWT 리프레시 토큰
        """
        now = datetime.now(UTC)
        expire = now + timedelta(minutes=self.refresh_token_expire_minutes)
        
        payload = {
            "sub": str(user_id),  # JWT sub는 문자열이어야 함
            "type": "refresh",
            "exp": expire,
            "iat": now,
        }
        
        token = jwt.encode(payload, self.secret_key, algorithm=self.algorithm)
        
        logger.info(
            "리프레시 토큰 생성",
            user_id=user_id,
            expires_in_minutes=self.refresh_token_expire_minutes,
        )
        
        return token
    
    def decode_token(self, token: str) -> Optional[TokenData]:
        """
        JWT 토큰 디코딩 및 검증
        
        JWT 토큰의 서명을 검증하고 페이로드를 추출하여 TokenData 객체로 변환합니다.
        토큰의 무결성, 만료 시간, 필수 필드를 모두 검증하며, 새로운 권한 필드들도 안전하게 처리합니다.
        
        Args:
            token (str): 검증할 JWT 토큰
                Format: "eyJ..." (Base64 인코딩된 JWT)
                
        Returns:
            Optional[TokenData]: 검증된 토큰 데이터 또는 None
                성공시: 사용자 정보가 포함된 TokenData 객체
                실패시: None (로그에 실패 원인 기록)
                
        검증 단계:
            1. JWT 구조 검증 (header.payload.signature)
            2. 서명 검증 (HMAC-SHA256)
            3. 만료 시간 검증 (exp 클레임)
            4. 필수 필드 존재 검증 (sub, type)
            5. TokenData 객체 생성 (하위 호환성 고려)
            
        보안 특징:
            - 서명 위변조 검증으로 무결성 보장
            - 자동 만료 시간 검증
            - 안전한 예외 처리로 정보 노출 방지
            - 구조화된 로깅으로 보안 이벤트 추적
            
        하위 호환성:
            - 기존 토큰 (scopes, resource_permissions 없음)도 정상 처리
            - 새로운 필드들은 Optional로 안전하게 처리
            - 필드가 없는 경우 None으로 기본값 설정
            
        실패 원인:
            - 잘못된 서명 (토큰 위변조)
            - 만료된 토큰
            - 잘못된 토큰 형식
            - 필수 필드 누락
            
        Example:
            ```python
            token_data = jwt_service.decode_token(access_token)
            if token_data:
                user_id = token_data.user_id
                roles = token_data.roles
                scopes = token_data.scopes or []  # 하위 호환성
                resource_perms = token_data.resource_permissions or {}
            else:
                # 토큰 검증 실패 처리
                raise AuthenticationError("Invalid token")
            ```
        """
        try:
            # JWT 디코딩 및 서명 검증
            payload = jwt.decode(
                token,
                self.secret_key,
                algorithms=[self.algorithm],  # 허용된 알고리즘만 사용
            )
            
            # 필수 필드 존재 확인
            if "sub" not in payload or "type" not in payload:
                logger.warning("토큰에 필수 필드 누락", payload=payload)
                return None
            
            # TokenData 객체 생성 (안전한 타입 변환 및 하위 호환성 보장)
            token_data = TokenData(
                user_id=payload["sub"],
                email=payload.get("email") if payload.get("email") else None,
                roles=payload.get("roles", []),
                token_type=payload["type"],
                # timestamp를 datetime 객체로 변환
                exp=datetime.fromtimestamp(payload["exp"], UTC) if "exp" in payload else None,
                iat=datetime.fromtimestamp(payload["iat"], UTC) if "iat" in payload else None,
                # 새로운 권한 필드들 (하위 호환성을 위해 안전하게 처리)
                scopes=payload.get("scopes") if "scopes" in payload else None,
                resource_permissions=payload.get("resource_permissions") if "resource_permissions" in payload else None,
            )
            
            return token_data
            
        except JWTError as e:
            # JWT 관련 오류 (서명 실패, 만료, 형식 오류 등)
            logger.warning("JWT 디코드 오류", error=str(e))
            return None
        except Exception as e:
            # 예상치 못한 오류 (timestamp 변환 실패 등)
            logger.error("예상치 못한 토큰 디코드 오류", error=str(e))
            return None
    
    def verify_token(
        self,
        token: str,
        token_type: str = "access",
    ) -> bool:
        """토큰 유효성 검증
        
        Args:
            token: JWT 토큰
            token_type: 토큰 타입 (access 또는 refresh)
            
        Returns:
            토큰이 유효한지 여부
        """
        token_data = self.decode_token(token)
        
        if token_data is None:
            return False
        
        # 토큰 타입 확인
        if token_data.token_type != token_type:
            logger.warning(
                "토큰 타입 불일치",
                expected=token_type,
                actual=token_data.token_type,
            )
            return False
        
        # 만료 시간 확인 (decode_token에서 이미 검증되지만 명시적으로 확인)
        if token_data.exp and token_data.exp < datetime.now(UTC):
            logger.warning("토큰 만료", exp=token_data.exp)
            return False
        
        return True
    
    def refresh_access_token(
        self,
        refresh_token: str,
        email: str,
        roles: list[str],
    ) -> Optional[str]:
        """리프레시 토큰으로 새 액세스 토큰 생성
        
        Args:
            refresh_token: 리프레시 토큰
            email: 사용자 이메일
            roles: 사용자 역할 목록
            
        Returns:
            새 액세스 토큰 또는 None (리프레시 토큰이 유효하지 않은 경우)
        """
        # 리프레시 토큰 검증
        if not self.verify_token(refresh_token, token_type="refresh"):
            logger.warning("유효하지 않은 리프레시 토큰")
            return None
        
        # 리프레시 토큰에서 사용자 ID 추출
        token_data = self.decode_token(refresh_token)
        if token_data is None:
            return None
        
        # 새 액세스 토큰 생성
        new_access_token = self.create_access_token(
            user_id=token_data.user_id,
            email=email,
            roles=roles,
        )
        
        logger.info(
            "액세스 토큰 갱신",
            user_id=token_data.user_id,
            email=email,
            roles=roles,
        )
        
        return new_access_token